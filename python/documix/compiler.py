"""DocumentCompiler: discovers files, runs converter chains, writes the pack.

Conversion logic lives in ``documix.converters``; the methods here are thin
delegates so that callers (and tests) can override any single step on an
instance. Dispatch tables are built from ``self.<method>`` on every call for
the same reason.

Concurrency: ``compile()`` converts files on a thread pool (``jobs``) and
writes results in sorted-file order. Only the top level owns a pool; ZIP
members and email attachments are converted serially inside their task.
``.eml`` files run on the main thread because sibling emails share an
``attachments/`` folder next to the source.
"""
import os
import re
import shutil
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from . import config, converters, local_ocr, output, textutils, tools, version
from .converters import anydoc as anydoc_conv, archive, docx as docx_conv
from .converters import epub as epub_conv, liteparse as liteparse_conv
from .converters import office as office_conv, pdf as pdf_conv, rtf as rtf_conv
from .converters import text as text_conv
from .email_processor import EmailProcessor
from .errors import EngineError


# Concurrency defaults: one job per logical CPU, bounded by installed memory
# (LiteParse OCR workers take ~250 MB each, LibreOffice and ML tools more),
# so a 10-core / 32 GB Apple Silicon machine gets 10 jobs and an 8 GB laptop 5.
MAX_DEFAULT_JOBS = 32
MEMORY_PER_JOB_GB = 1.5


def default_jobs():
    """Pick the default number of concurrent conversions for this machine.

    ``DOCUMIX_JOBS`` in the environment overrides the heuristic.
    """
    override = os.environ.get('DOCUMIX_JOBS', '').strip()
    if override.isdigit() and int(override) >= 1:
        return int(override)
    cpus = os.cpu_count() or 1
    memory = tools.physical_memory_gb()
    budget = cpus if memory is None else max(1, int(memory / MEMORY_PER_JOB_GB))
    return max(1, min(cpus, budget, MAX_DEFAULT_JOBS))


def _not_none(text):
    return text is not None


class DocumentCompiler:
    def __init__(self, source_path, output_file, recursive=False, include_extensions=None,
                 exclude_patterns=None, force_format=None, converter_config=None,
                 ocr_config=None, office_require_text_only=False, jobs=None):
        if type(office_require_text_only) is not bool:
            raise ValueError('invalid_office_configuration')
        if jobs is not None and (type(jobs) is not int or jobs < 1):
            raise ValueError('invalid_jobs_configuration')
        self.office_require_text_only = office_require_text_only
        self.jobs = jobs or default_jobs()
        self.source_path = os.path.abspath(source_path)
        self.is_single_file = os.path.isfile(self.source_path)
        self.source_dir = os.path.dirname(self.source_path) if self.is_single_file else self.source_path
        self.output_file = output_file
        self.recursive = recursive
        self.version = version.get_version()
        self.force_format = force_format  # Can be 'standard' or None (auto-detect)
        self.converter_config = converter_config or {}
        self.ocr_config = local_ocr.validate_config(ocr_config)

        # Statistics data
        self.total_files = 0
        self.total_chars = 0
        self.total_tokens = 0
        self.file_stats = []

        # Per-instance availability overrides (None = ask the process cache)
        self._uvx_available = None
        self._mineru_available = None
        self._paddleocr_available = None
        self._paddleocr_python = None

        # Temporary directories for ZIP extraction / DOC conversion
        self.temp_dirs = []

        self.suspicious_extensions = list(config.SUSPICIOUS_EXTENSIONS)

        self.include_extensions = include_extensions or list(config.DEFAULT_EXTENSIONS)
        self.include_extensions = [ext.lower() for ext in self.include_extensions]

        self.exclude_patterns = []
        if exclude_patterns:
            for pattern in exclude_patterns:
                try:
                    self.exclude_patterns.append(re.compile(pattern))
                except re.error:
                    print(f"WARNING: Invalid exclusion pattern: {pattern}")

    # ------------------------------------------------------------------
    # Configuration and tool availability
    # ------------------------------------------------------------------
    def get_converters(self, fmt):
        """Returns the list of converters to try for a given format."""
        return self.converter_config.get(fmt, config.CONVERTER_DEFAULTS[fmt])

    def is_uvx_available(self):
        """Check if uvx command is available. Result is cached."""
        if self._uvx_available is None:
            self._uvx_available = tools.probe(['uvx', '--version'])
        return self._uvx_available

    def is_mineru_available(self):
        """Check if mineru command is available. Result is cached."""
        if self._mineru_available is None:
            self._mineru_available = tools.probe(['mineru', '--version'])
        return self._mineru_available

    def is_paddleocr_available(self):
        """Check if PaddleOCR is available via uv tool. Result is cached.

        PaddlePaddle requires Python <=3.12, so PaddleOCR runs in its own
        uv-managed venv and is invoked as a subprocess, similar to mineru.
        """
        if self._paddleocr_available is None:
            env = os.environ.copy()
            env.update(pdf_conv.PADDLE_ENV)
            available = False
            if tools.probe(['paddleocr', '--version'], env=env):
                paddleocr_bin = shutil.which('paddleocr')
                if paddleocr_bin:
                    venv_bin = os.path.dirname(os.path.realpath(paddleocr_bin))
                    python_path = os.path.join(venv_bin, 'python')
                    if os.path.exists(python_path):
                        self._paddleocr_python = python_path
                        available = True
            self._paddleocr_available = available
        return self._paddleocr_available

    # ------------------------------------------------------------------
    # File discovery
    # ------------------------------------------------------------------
    def _matches(self, filename):
        _, ext = os.path.splitext(filename.lower())
        if ext not in self.include_extensions:
            return False
        return not any(pattern.search(filename) for pattern in self.exclude_patterns)

    def _scan(self):
        """Walk the source once; return (files_to_process, directory_structure).

        The file list includes hidden directories (as before); the printed
        tree skips them. Directories are visited in sorted order so the output
        is deterministic across filesystems.
        """
        structure = []
        files = []
        if self.is_single_file:
            # A single source file still has to pass the extension/exclusion
            # filter (unsupported extension -> nothing to process).
            if self._matches(os.path.basename(self.source_path)):
                files = [self.source_path]
        if self.recursive:
            for root, dirs, names in os.walk(self.source_dir):
                dirs.sort()
                rel_root = os.path.relpath(root, self.source_dir)
                hidden = rel_root != '.' and any(
                    part.startswith('.') for part in rel_root.split(os.sep))
                if not hidden and rel_root != '.':
                    structure.append(f"{rel_root}/")
                for name in sorted(names):
                    if not self._matches(name):
                        continue
                    path = os.path.join(root, name)
                    if not self.is_single_file:
                        files.append(path)
                    if not hidden:
                        structure.append(f"  {os.path.relpath(path, self.source_dir)}")
        else:
            for name in sorted(os.listdir(self.source_dir)):
                path = os.path.join(self.source_dir, name)
                if not os.path.isfile(path) or not self._matches(name):
                    continue
                if not self.is_single_file:
                    files.append(path)
                structure.append(f"  {name}")
        return sorted(files), structure

    def collect_files(self):
        """Collects all files to process."""
        return self._scan()[0]

    def get_directory_structure(self):
        """Creates a directory tree in Repomix format."""
        return self._scan()[1]

    def detect_processing_mode(self, files):
        """Detect whether to use email-specific output format."""
        if self.force_format:
            return self.force_format
        if len(files) == 1 and files[0].lower().endswith('.eml'):
            return 'single_email'
        return 'standard'

    def check_security(self, files):
        """Checks for potential security issues in files."""
        suspicious_files = []
        for file_path in files:
            _, ext = os.path.splitext(file_path.lower())
            if ext in self.suspicious_extensions:
                file_size = os.path.getsize(file_path)
                if file_size > 1024 * 1024:  # Larger than 1MB
                    suspicious_files.append(file_path)
                    continue
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read(4096)  # Read only first 4KB
                        if re.search(r'(exec|eval|system|subprocess|os\.)', content):
                            suspicious_files.append(file_path)
                except Exception:
                    pass  # Ignore errors reading binary files
        return suspicious_files

    # ------------------------------------------------------------------
    # Text helpers kept as methods for backwards compatibility
    # ------------------------------------------------------------------
    def get_file_language(self, file_path):
        return textutils.get_file_language(file_path)

    def estimate_tokens(self, text):
        return textutils.estimate_tokens(text)

    def format_size(self, size_bytes):
        return textutils.format_size(size_bytes)

    def _format_table_as_markdown(self, table_data):
        return textutils.table_to_markdown(table_data)

    def _table_cell_density(self, table_data):
        return textutils.cell_density(table_data)

    @staticmethod
    def _html_tables_to_markdown(text):
        return textutils.html_tables_to_markdown(text)

    # ------------------------------------------------------------------
    # Engines (shared by every document format)
    # ------------------------------------------------------------------
    def convert_with_anydoc(self, filepath):
        return anydoc_conv.convert(filepath, require_text_only=self.office_require_text_only)

    def convert_with_liteparse(self, filepath):
        return liteparse_conv.convert(filepath, jobs=self.jobs)

    def _engine_dispatch(self):
        return {
            'anydoc': self.convert_with_anydoc,
            'liteparse': self.convert_with_liteparse,
        }

    def _run_chain(self, fmt, dispatch, filepath, accept, label):
        text, method = converters.run_chain(self.get_converters(fmt), dispatch, filepath, accept)
        if text is not None:
            return text, method
        print(f"WARNING: Failed to convert {label}: {filepath}")
        return f"[Failed to convert {label} file: {os.path.basename(filepath)}]", "failed"

    # ------------------------------------------------------------------
    # PDF
    # ------------------------------------------------------------------
    def convert_pdf_with_tables(self, filepath):
        return pdf_conv.convert_with_tables(filepath)

    def convert_pdf_with_paddleocr(self, filepath):
        if not self.is_paddleocr_available():
            return None, None
        return pdf_conv.convert_with_paddleocr(filepath, self._paddleocr_python)

    def convert_pdf_with_mineru(self, filepath):
        if not self.is_mineru_available():
            return None, None
        return pdf_conv.convert_with_mineru(filepath)

    def _try_pdf_markitdown_uvx(self, filepath):
        if not self.is_uvx_available():
            return None, None
        return pdf_conv.try_markitdown_uvx(filepath)

    def _try_pdf_markitdown(self, filepath):
        return pdf_conv.try_markitdown(filepath)

    def _try_pdf_pdftotext(self, filepath):
        return pdf_conv.try_pdftotext(filepath)

    def convert_pdf_with_tesseract(self, filepath):
        return pdf_conv.convert_with_tesseract(filepath, self.ocr_config)

    def _pdf_dispatch(self):
        dispatch = self._engine_dispatch()
        dispatch.update({
            'paddleocr': self.convert_pdf_with_paddleocr,
            'mineru': self.convert_pdf_with_mineru,
            'pdfplumber': self.convert_pdf_with_tables,
            'markitdown-uvx': self._try_pdf_markitdown_uvx,
            'markitdown': self._try_pdf_markitdown,
            'pdftotext': self._try_pdf_pdftotext,
            'tesseract': self.convert_pdf_with_tesseract,
        })
        return dispatch

    def _convert_pdf_with_complete_ocr(self, filepath, converters_, dispatch):
        return pdf_conv.convert_with_complete_ocr(
            filepath, converters_, dispatch, self.convert_pdf_with_tesseract)

    def convert_pdf_to_text(self, filepath):
        """Converts PDF to text using configured converters. Explicit
        Tesseract requires complete-document OCR even when native
        extraction succeeds."""
        dispatch = self._pdf_dispatch()
        order = self.get_converters('pdf')
        if 'tesseract' in order:
            try:
                text, method = self._convert_pdf_with_complete_ocr(filepath, order, dispatch)
                if local_ocr.has_content(text):
                    return text, method
            except local_ocr.OcrError as error:
                print(f"Tesseract OCR unavailable: {error.code}")
            except (OSError, UnicodeError, ValueError):
                print('Tesseract OCR unavailable: invalid_input')
            print(f"WARNING: Failed to convert PDF: {filepath}")
            return f"[Failed to convert PDF file: {os.path.basename(filepath)}]", "failed"
        return self._run_chain('pdf', dispatch, filepath, local_ocr.has_content, 'PDF')

    # ------------------------------------------------------------------
    # Word, RTF, EPUB, Office
    # ------------------------------------------------------------------
    def _try_docx_pandoc(self, filepath):
        return docx_conv.try_pandoc(filepath)

    def _try_docx_docx2txt(self, filepath):
        return docx_conv.try_docx2txt(filepath)

    def convert_docx_to_text(self, filepath):
        """Converts DOCX to text using configured converters."""
        dispatch = self._engine_dispatch()
        dispatch.update({
            'pandoc': self._try_docx_pandoc,
            'docx2txt': self._try_docx_docx2txt,
        })
        return self._run_chain('docx', dispatch, filepath, _not_none, 'DOCX')

    def _try_doc_soffice(self, filepath):
        return docx_conv.convert_doc(filepath, self.temp_dirs, self.convert_docx_to_text)

    def convert_doc_to_text(self, filepath):
        """Converts legacy DOC files (anydoc natively; soffice as opt-in)."""
        dispatch = self._engine_dispatch()
        dispatch['soffice'] = self._try_doc_soffice
        return self._run_chain('doc', dispatch, filepath, _not_none, 'DOC')

    def _try_rtf_pandoc(self, filepath):
        return rtf_conv.try_pandoc(filepath)

    def _try_rtf_unrtf(self, filepath):
        return rtf_conv.try_unrtf(filepath)

    def _try_rtf_striprtf(self, filepath):
        return rtf_conv.try_striprtf(filepath)

    def convert_rtf_to_text(self, filepath):
        """Converts RTF to text using configured converters."""
        dispatch = self._engine_dispatch()
        dispatch.update({
            'pandoc': self._try_rtf_pandoc,
            'unrtf': self._try_rtf_unrtf,
            'striprtf': self._try_rtf_striprtf,
        })
        return self._run_chain('rtf', dispatch, filepath, _not_none, 'RTF')

    def _try_epub_ebook_convert(self, filepath):
        return epub_conv.convert(filepath)

    def convert_epub_to_text(self, filepath):
        """Converts EPUB using configured converters."""
        dispatch = self._engine_dispatch()
        dispatch['ebook-convert'] = self._try_epub_ebook_convert
        return self._run_chain('epub', dispatch, filepath, _not_none, 'EPUB')

    def _try_office_markitdown(self, filepath):
        ext = os.path.splitext(filepath.lower())[1]
        return office_conv.convert(filepath, ext, self.office_require_text_only)

    def convert_office_to_text(self, filepath):
        """Converts XLSX/PPTX/OpenDocument/CSV using configured converters."""
        dispatch = self._engine_dispatch()
        dispatch['markitdown'] = self._try_office_markitdown
        label = os.path.splitext(filepath.lower())[1][1:].upper()
        return self._run_chain('office', dispatch, filepath, _not_none, label)

    def convert_txt_to_text(self, filepath):
        return text_conv.convert(filepath)

    def extract_zip(self, filepath):
        """Extracts a ZIP file and processes its contents."""
        return archive.extract_zip(filepath, self.include_extensions, self.temp_dirs,
                                   self.process_file, self.get_file_language, self._is_fenced)

    # ------------------------------------------------------------------
    # Email
    # ------------------------------------------------------------------
    def format_email_single(self, out_file, email_info, content):
        """Format output for single email mode."""
        output.write_single_email(out_file, self.version, email_info, content)

    def process_email(self, filepath):
        """Process an email file and its attachments."""
        start_time = time.time()
        try:
            print(f"📧 Processing email: {os.path.basename(filepath)}")

            email_processor = EmailProcessor(filepath)

            if not email_processor.parse_email():
                return f"[Failed to parse email file: {os.path.basename(filepath)}]", "failed-parse", {}

            email_info = {
                'filepath': filepath,
                'subject': email_processor.metadata.get('subject', 'No Subject'),
                'from': email_processor.metadata.get('from', ''),
                'to': email_processor.metadata.get('to', ''),
                'cc': email_processor.metadata.get('cc', ''),
                'date': email_processor.metadata.get('date', ''),
                'message_id': email_processor.metadata.get('message_id', ''),
                'in_reply_to': email_processor.metadata.get('in_reply_to', ''),
                'references': email_processor.metadata.get('references', ''),
                'auth_results': email_processor.metadata.get('auth_results', ''),
                'dkim_signature': email_processor.metadata.get('dkim_signature', ''),
                'attachments_source': email_processor.metadata.get('attachments_source', ''),
                'size': os.path.getsize(filepath)
            }

            email_processor.process_attachments()
            email_content, attachments = email_processor.compile_output()
            email_info['attachments'] = attachments

            if attachments:
                email_content += "\n"
                for i, attachment in enumerate(attachments, 1):
                    att_path = attachment['path']
                    att_name = attachment['filename']
                    att_size = email_processor.format_size(attachment['size'])

                    email_content += f"### {i}. {att_name} ({att_size})\n\n"

                    _, ext = os.path.splitext(att_path.lower())
                    if ext in self.include_extensions and ext != '.eml':  # Avoid recursive email processing
                        try:
                            content, method = self.process_file(att_path)
                            if not self._is_fenced(att_path, method):
                                email_content += f"{content}\n\n"
                            else:
                                file_language = self.get_file_language(att_path)
                                if file_language:
                                    email_content += f"```{file_language}\n{content}\n```\n\n"
                                else:
                                    email_content += f"```\n{content}\n```\n\n"
                        except EngineError:
                            raise
                        except Exception as e:
                            email_content += f"[Error processing attachment: {str(e)}]\n\n"
                    else:
                        email_content += f"[Attachment type '{ext}' not supported for extraction]\n\n"

            email_content += "\n---\n## Statistics\n"
            email_content += f"- Total attachments: {len(attachments)}\n"
            if attachments:
                total_size = sum(att['size'] for att in attachments)
                email_content += f"- Total size: {email_processor.format_size(total_size)}\n"
            email_content += f"- Processing time: {time.time() - start_time:.2f}s\n"

            conversion_method = f"email+{email_processor.metadata.get('attachments_source', 'unknown').lower().replace(' ', '_')}"
            return email_content, conversion_method, email_info

        except EngineError:
            raise
        except Exception as e:
            print(f"ERROR: Failed to process email {filepath}: {str(e)}")
            return f"[Error processing email file: {str(e)}]", "failed-exception", {}

    # ------------------------------------------------------------------
    # Dispatch and compile
    # ------------------------------------------------------------------
    @staticmethod
    def _is_fenced(file_path, method):
        """Only text/code files read verbatim get a code fence; everything a
        converter produced is Markdown and is written raw."""
        return method == 'direct_read'

    def process_file(self, file_path):
        """Processes a single file and returns its content and conversion method used."""
        ext = os.path.splitext(file_path.lower())[1]
        fmt = config.FORMAT_OF_EXTENSION.get(ext)

        if fmt == 'pdf':
            return self.convert_pdf_to_text(file_path)
        elif fmt == 'epub':
            return self.convert_epub_to_text(file_path)
        elif fmt == 'docx':
            return self.convert_docx_to_text(file_path)
        elif fmt == 'doc':
            return self.convert_doc_to_text(file_path)
        elif fmt == 'office':
            return self.convert_office_to_text(file_path)
        elif fmt == 'rtf':
            return self.convert_rtf_to_text(file_path)
        elif ext == '.zip':
            return self.extract_zip(file_path)
        elif ext == '.eml':
            content, method, _ = self.process_email(file_path)
            return content, method
        else:  # .txt, .md, .py, etc.
            return self.convert_txt_to_text(file_path)

    def _process_entry(self, file_path):
        rel_path = os.path.relpath(file_path, self.source_dir)
        print(f"⚙️  Processing: {rel_path}")
        return self.process_file(file_path)

    @staticmethod
    def _runs_inline(file_path):
        # Emails extract attachments next to the source; siblings would race.
        return file_path.lower().endswith('.eml')

    def _iter_results(self, files):
        """Yield (file_path, (content, method)) in the order of ``files``.

        Up to ``jobs`` files convert concurrently; at most ``2 * jobs`` results
        are buffered ahead of the writer (a few MB each at most). Any exception (``EngineError``,
        ``OcrCleanupError``, ...) is re-raised at its file's position after
        cancelling the queued work.
        """
        workers = min(self.jobs, len(files))
        if workers <= 1:
            for file_path in files:
                yield file_path, self._process_entry(file_path)
            return

        pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix='documix')
        pending = deque()
        remaining = iter(files)
        window = workers * 2

        def fill():
            while len(pending) < window:
                file_path = next(remaining, None)
                if file_path is None:
                    return
                if self._runs_inline(file_path):
                    pending.append((file_path, None))
                else:
                    pending.append((file_path, pool.submit(self._process_entry, file_path)))

        completed = False
        try:
            fill()
            while pending:
                file_path, future = pending.popleft()
                if future is None:
                    result = self._process_entry(file_path)
                else:
                    result = future.result()
                fill()
                yield file_path, result
            completed = True
        finally:
            if completed:
                pool.shutdown(wait=True)
            else:
                for _, future in pending:
                    if future is not None:
                        future.cancel()
                pool.shutdown(wait=False, cancel_futures=True)

    def _record_stats(self, rel_path, content, conversion_method):
        char_count = len(content)
        token_count = self.estimate_tokens(content)
        self.total_chars += char_count
        self.total_tokens += token_count
        self.file_stats.append({
            'path': rel_path,
            'chars': char_count,
            'tokens': token_count,
            'conversion_method': conversion_method
        })

    def _compile_single_email(self, out_file, file_path, start_time):
        content, conversion_method, email_info = self.process_email(file_path)
        self.format_email_single(out_file, email_info, content)

        self.total_chars = len(content)
        self.total_tokens = self.estimate_tokens(content)
        elapsed_time = time.time() - start_time

        print("\n✔ Email processing completed successfully!")
        print(f"\n📊 Processing Summary:")
        print("─────────────────────")
        print(f"  Email Subject: {email_info.get('subject', 'No Subject')}")
        print(f"  Attachments: {len(email_info.get('attachments', []))} files")
        print(f"  Total Chars: {self.total_chars:,} chars")
        print(f"  Total Tokens: {self.total_tokens:,} tokens")
        print(f"  Output: {self.output_file}")
        print(f"  Time: {elapsed_time:.2f} seconds")
        return True

    def _compile_standard(self, out_file, filtered_files, structure, suspicious_files, start_time):
        output.write_standard_preamble(out_file, self.source_dir, len(filtered_files), structure)

        for file_path, (content, conversion_method) in self._iter_results(filtered_files):
            rel_path = os.path.relpath(file_path, self.source_dir)
            self._record_stats(rel_path, content, conversion_method)
            output.write_file_entry(
                out_file, rel_path, conversion_method, content,
                self.get_file_language(file_path),
                self._is_fenced(file_path, conversion_method),
            )

        self.file_stats.sort(key=lambda x: x['chars'], reverse=True)
        elapsed_time = time.time() - start_time

        print("\n✔ Packing completed successfully!")

        print("\n📈 Top 5 Files by Character Count and Token Count:")
        print("──────────────────────────────────────────────────")
        for i, stat in enumerate(self.file_stats[:5], 1):
            print(f"{i}. {stat['path']} ({stat['chars']:,} chars, {stat['tokens']:,} tokens, via {stat['conversion_method']})")

        print("\n🔎 Security Check:")
        print("─────────────────────")
        if suspicious_files:
            print("❌ Suspicious files detected:")
            for sus_file in suspicious_files:
                print(f"  - {os.path.relpath(sus_file, self.source_dir)}")
        else:
            print("✔ No suspicious files detected.")

        print("\n📊 Pack Summary:")
        print("─────────────────────")
        print(f"  Total Files: {self.total_files:,} files")
        print(f"  Total Chars: {self.total_chars:,} chars")
        print(f" Total Tokens: {self.total_tokens:,} tokens")
        print(f"       Output: {self.output_file}")
        print(f"     Security: {'❌ Suspicious files detected' if suspicious_files else '✔ No suspicious files detected'}")
        print(f"        Time: {elapsed_time:.2f} seconds")
        print(f"        Jobs: {self.jobs}")

        print("\n🎉 All Done! Your documents have been successfully packed.")
        return True

    def _discard_output(self):
        try:
            os.remove(self.output_file)
        except OSError:
            pass

    def compile(self):
        """Compiles all documents into a single Markdown file.

        Raises ``EngineError`` (after removing the partial output) when the
        primary engine fails; document-level problems never abort the run.
        """
        start_time = time.time()
        print(f"📦 DocuMix v{self.version}")

        filtered_files, structure = self._scan()
        if not filtered_files:
            print("❌ No files found to process.")
            return False

        self.total_files = len(filtered_files)

        processing_mode = self.detect_processing_mode(filtered_files)
        print(f"📋 Processing mode: {processing_mode}")

        print("🔎 Checking files for security issues...")
        suspicious_files = self.check_security(filtered_files)

        print("📊 Collecting file statistics...")

        try:
            with open(self.output_file, 'w', encoding='utf-8') as out_file:
                if processing_mode == 'single_email':
                    return self._compile_single_email(out_file, filtered_files[0], start_time)
                return self._compile_standard(out_file, filtered_files, structure,
                                              suspicious_files, start_time)
        except EngineError:
            self._discard_output()
            raise
        finally:
            liteparse_conv.shutdown()
            for temp_dir in self.temp_dirs:
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass
