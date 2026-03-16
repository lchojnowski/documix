#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import argparse
import re
import subprocess
import tempfile
import datetime
import shutil
import math
import time
import zipfile
import email
import email.policy
from email.parser import BytesParser
from pathlib import Path
from collections import Counter
import string
import textwrap
import base64
import quopri
import json
import difflib
import platform
import html2text

# Try to import docx2txt for fallback DOCX processing
try:
    import docx2txt
    DOCX2TXT_AVAILABLE = True
except ImportError:
    DOCX2TXT_AVAILABLE = False

# Try to import pdfplumber for PDF table extraction
try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False

# PaddleOCR availability is checked at runtime via is_paddleocr_available()
# because PaddlePaddle requires Python ≤3.12 and we invoke it via subprocess.

CONVERTER_DEFAULTS = {
    'pdf': ['mineru', 'pdfplumber', 'markitdown-uvx', 'markitdown', 'pdftotext', 'paddleocr'],
    'docx': ['pandoc', 'docx2txt'],
    'rtf': ['pandoc', 'unrtf', 'striprtf'],
}


class EmailProcessor:
    """Processes email files (.eml) and their attachments."""
    
    def __init__(self, eml_path, attachments_dir=None):
        self.eml_path = eml_path
        self.attachments_dir = attachments_dir or self._auto_detect_attachments()
        self.email_obj = None
        self.metadata = {}
        self.attachments = []
        self.use_folder_attachments = False
        self.h2t = html2text.HTML2Text()
        self.h2t.ignore_links = False
        self.h2t.ignore_images = False
        self.h2t.body_width = 0  # No line wrapping
    
    def _auto_detect_attachments(self):
        """Auto-detect attachments folder near the email file."""
        email_dir = os.path.dirname(self.eml_path)
        possible_names = ['attachments', 'Attachments', 'attachment', 'Attachment']
        
        for name in possible_names:
            attachments_path = os.path.join(email_dir, name)
            if os.path.exists(attachments_path) and os.path.isdir(attachments_path):
                return attachments_path
        
        return None
    
    def _check_attachments_folder(self):
        """Check if attachments folder exists and has files."""
        if self.attachments_dir and os.path.exists(self.attachments_dir):
            files = []
            for f in os.listdir(self.attachments_dir):
                file_path = os.path.join(self.attachments_dir, f)
                if os.path.isfile(file_path):
                    file_size = os.path.getsize(file_path)
                    files.append({
                        'filename': f,
                        'path': file_path,
                        'size': file_size
                    })
            
            if files:
                self.use_folder_attachments = True
                return files
        return []
    
    def parse_email(self):
        """Parse .eml file and extract all components."""
        try:
            with open(self.eml_path, 'rb') as f:
                self.email_obj = BytesParser(policy=email.policy.default).parse(f)
            
            # Extract metadata
            self.metadata = {
                'from': self.email_obj.get('From', ''),
                'to': self.email_obj.get('To', ''),
                'cc': self.email_obj.get('CC', ''),
                'bcc': self.email_obj.get('BCC', ''),
                'subject': self.email_obj.get('Subject', ''),
                'date': self.email_obj.get('Date', ''),
                'message_id': self.email_obj.get('Message-ID', ''),
                'in_reply_to': self.email_obj.get('In-Reply-To', ''),
                'references': self.email_obj.get('References', ''),
                'content_type': self.email_obj.get_content_type()
            }
            
            # Extract authentication info if available
            if self.email_obj.get('DKIM-Signature'):
                self.metadata['dkim_signature'] = 'Present'
            if self.email_obj.get('Authentication-Results'):
                self.metadata['auth_results'] = self.email_obj.get('Authentication-Results')
            
            return True
            
        except Exception as e:
            print(f"ERROR: Failed to parse email {self.eml_path}: {str(e)}")
            return False
    
    def extract_attachments_from_email(self):
        """Extract attachments from the email object."""
        if not self.email_obj:
            return
        
        for part in self.email_obj.walk():
            # Check if it's an attachment
            content_disposition = part.get('Content-Disposition', '')
            if 'attachment' in content_disposition:
                filename = part.get_filename()
                if filename:
                    # Create attachments directory if it doesn't exist
                    if not self.attachments_dir:
                        email_dir = os.path.dirname(self.eml_path)
                        self.attachments_dir = os.path.join(email_dir, 'attachments')
                    
                    os.makedirs(self.attachments_dir, exist_ok=True)
                    
                    # Save attachment
                    filepath = os.path.join(self.attachments_dir, filename)
                    content = part.get_content()
                    
                    if isinstance(content, bytes):
                        with open(filepath, 'wb') as f:
                            f.write(content)
                    else:
                        with open(filepath, 'w', encoding='utf-8') as f:
                            f.write(content)
                    
                    file_size = os.path.getsize(filepath)
                    self.attachments.append({
                        'filename': filename,
                        'path': filepath,
                        'size': file_size
                    })
    
    def process_attachments(self):
        """Process attachments with folder priority."""
        folder_files = self._check_attachments_folder()
        
        if self.use_folder_attachments:
            # Use existing files in attachments folder
            self.attachments = folder_files
            self.metadata['attachments_source'] = 'Local folder'
            print(f"📎 Using {len(folder_files)} attachments from local folder")
        else:
            # Extract from email
            self.extract_attachments_from_email()
            self.metadata['attachments_source'] = 'Extracted from email'
            print(f"📎 Extracted {len(self.attachments)} attachments from email")
    
    def get_email_body(self):
        """Extract and convert email body to markdown."""
        if not self.email_obj:
            return ""
        
        body_plain = ""
        body_html = ""
        
        # Walk through email parts
        for part in self.email_obj.walk():
            content_type = part.get_content_type()
            content_disposition = part.get('Content-Disposition', '')
            
            # Skip attachments
            if 'attachment' in content_disposition:
                continue
            
            try:
                # Get text content
                if content_type == 'text/plain':
                    body_plain = part.get_content()
                elif content_type == 'text/html':
                    html_content = part.get_content()
                    # Convert HTML to markdown
                    body_html = self.h2t.handle(html_content)
            except Exception as e:
                print(f"WARNING: Failed to extract body part: {str(e)}")
        
        # Prefer HTML converted to markdown, fallback to plain text
        return body_html if body_html else body_plain
    
    def format_size(self, size_bytes):
        """Format file size in human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
    
    def compile_output(self):
        """Generate final consolidated document."""
        output = []
        
        # Header
        subject = self.metadata.get('subject', 'No Subject')
        output.append(f"# Email Document: {subject}")
        output.append(f"Generated by DocuMix on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        output.append("")
        
        # Metadata section
        output.append("## Email Metadata")
        if self.metadata.get('from'):
            output.append(f"- **From**: {self.metadata['from']}")
        if self.metadata.get('to'):
            output.append(f"- **To**: {self.metadata['to']}")
        if self.metadata.get('cc'):
            output.append(f"- **CC**: {self.metadata['cc']}")
        if self.metadata.get('date'):
            output.append(f"- **Date**: {self.metadata['date']}")
        if self.metadata.get('subject'):
            output.append(f"- **Subject**: {self.metadata['subject']}")
        if self.metadata.get('message_id'):
            output.append(f"- **Message-ID**: {self.metadata['message_id']}")
        if self.metadata.get('attachments_source'):
            output.append(f"- **Attachments Source**: {self.metadata['attachments_source']} ({len(self.attachments)} files found)")
        output.append("")
        
        # Email content
        output.append("## Email Content")
        output.append("")
        body = self.get_email_body()
        if body:
            output.append(body)
        else:
            output.append("[No email body content found]")
        output.append("")
        
        # Attachments section
        if self.attachments:
            output.append(f"## Attachments ({len(self.attachments)} files)")
            output.append("")
            
            total_size = sum(att['size'] for att in self.attachments)
            output.append(f"Total size: {self.format_size(total_size)}")
            output.append("")
            
            # Return both the formatted output and attachment info for processing
            return "\n".join(output), self.attachments
        else:
            output.append("## Attachments")
            output.append("")
            output.append("No attachments found.")
            output.append("")
            return "\n".join(output), []

class DocumentCompiler:
    def __init__(self, source_path, output_file, recursive=False, include_extensions=None, exclude_patterns=None, force_format=None, converter_config=None):
        self.source_path = os.path.abspath(source_path)
        self.is_single_file = os.path.isfile(self.source_path)
        self.source_dir = os.path.dirname(self.source_path) if self.is_single_file else self.source_path
        self.output_file = output_file
        self.recursive = recursive
        self.version = "0.1.0"
        self.force_format = force_format  # Can be 'standard' or None (auto-detect)
        self.converter_config = converter_config or {}

        # Statistics data
        self.total_files = 0
        self.total_chars = 0
        self.total_tokens = 0
        self.file_stats = []

        # Cache for uvx availability check
        self._uvx_available = None
        self._mineru_available = None
        self._paddleocr_available = None
        self._paddleocr_python = None
        
        
        # Temporary directory for ZIP extraction
        self.temp_dirs = []
        
        # List of potentially suspicious extensions for security check
        self.suspicious_extensions = ['.exe', '.bat', '.sh', '.com', '.vbs', '.ps1', '.py', '.rb']
        
        # Standard extensions if none provided
        self.include_extensions = include_extensions or ['.pdf', '.epub', '.docx', '.doc', '.rtf', '.txt', '.md',
                                                        '.py', '.rb', '.js', '.html', '.css', '.json', '.yml', '.yaml', '.zip', '.eml']
        
        # Convert extensions to lowercase for consistency
        self.include_extensions = [ext.lower() for ext in self.include_extensions]
        
        # Compile exclusion patterns
        self.exclude_patterns = []
        if exclude_patterns:
            for pattern in exclude_patterns:
                try:
                    self.exclude_patterns.append(re.compile(pattern))
                except re.error:
                    print(f"WARNING: Invalid exclusion pattern: {pattern}")

    def get_converters(self, fmt):
        """Returns the list of converters to try for a given format."""
        return self.converter_config.get(fmt, CONVERTER_DEFAULTS[fmt])

    def is_uvx_available(self):
        """Check if uvx command is available. Result is cached."""
        if self._uvx_available is None:
            try:
                subprocess.run(
                    ['uvx', '--version'],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                self._uvx_available = True
            except (subprocess.SubprocessError, FileNotFoundError):
                self._uvx_available = False
        return self._uvx_available

    def is_mineru_available(self):
        """Check if mineru command is available. Result is cached."""
        if self._mineru_available is None:
            try:
                subprocess.run(
                    ['mineru', '--version'],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                self._mineru_available = True
            except (subprocess.SubprocessError, FileNotFoundError):
                self._mineru_available = False
        return self._mineru_available

    def is_paddleocr_available(self):
        """Check if PaddleOCR is available via uv tool. Result is cached.

        PaddlePaddle requires Python ≤3.12, so we run PaddleOCR in its own
        uv-managed venv and invoke it as a subprocess, similar to mineru.
        """
        if self._paddleocr_available is None:
            try:
                result = subprocess.run(
                    ['paddleocr', '--version'],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                # Find the Python interpreter in the same venv as paddleocr
                paddleocr_bin = shutil.which('paddleocr')
                if paddleocr_bin:
                    venv_bin = os.path.dirname(os.path.realpath(paddleocr_bin))
                    python_path = os.path.join(venv_bin, 'python')
                    if os.path.exists(python_path):
                        self._paddleocr_python = python_path
                        self._paddleocr_available = True
                    else:
                        self._paddleocr_available = False
                else:
                    self._paddleocr_available = False
            except (subprocess.SubprocessError, FileNotFoundError):
                self._paddleocr_available = False
        return self._paddleocr_available

    def collect_files(self):
        """Collects all files to process."""
        files_to_process = []
        
        # Handle single file input
        if self.is_single_file:
            files_to_process = [self.source_path]
        elif self.recursive:
            for root, _, files in os.walk(self.source_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    files_to_process.append(file_path)
        else:
            files_to_process = [os.path.join(self.source_dir, f) for f in os.listdir(self.source_dir) 
                              if os.path.isfile(os.path.join(self.source_dir, f))]
        
        # Filter files by extensions and exclusion patterns
        filtered_files = []
        
        for file_path in files_to_process:
            # Check extension
            _, ext = os.path.splitext(file_path.lower())
            if ext not in self.include_extensions:
                continue
            
            # Check exclusion patterns
            filename = os.path.basename(file_path)
            exclude = False
            for pattern in self.exclude_patterns:
                if pattern.search(filename):
                    exclude = True
                    break
            
            if not exclude:
                filtered_files.append(file_path)
        
        # Sort files alphabetically
        return sorted(filtered_files)
    
    def detect_processing_mode(self, files):
        """Detect whether to use email-specific output format."""
        if self.force_format:
            return self.force_format
        
        # Check if single file mode
        if len(files) == 1 and files[0].lower().endswith('.eml'):
            return 'single_email'
        
        # For multiple files or non-email files, always use standard format
        return 'standard'
    
    def get_directory_structure(self):
        """Creates a directory tree in Repomix format."""
        structure = []
        
        if self.recursive:
            for root, dirs, files in os.walk(self.source_dir):
                # Skip hidden directories
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                
                rel_path = os.path.relpath(root, self.source_dir)
                if rel_path != '.':
                    structure.append(f"{rel_path}/")
                
                for file in sorted(files):
                    file_path = os.path.join(root, file)
                    _, ext = os.path.splitext(file_path.lower())
                    
                    # Check if file has an appropriate extension
                    if ext in self.include_extensions:
                        # Check exclusion patterns
                        exclude = False
                        for pattern in self.exclude_patterns:
                            if pattern.search(file):
                                exclude = True
                                break
                        
                        if not exclude:
                            rel_file_path = os.path.relpath(file_path, self.source_dir)
                            structure.append(f"  {rel_file_path}")
        else:
            for file in sorted(os.listdir(self.source_dir)):
                file_path = os.path.join(self.source_dir, file)
                if os.path.isfile(file_path):
                    _, ext = os.path.splitext(file_path.lower())
                    
                    # Check if file has an appropriate extension
                    if ext in self.include_extensions:
                        # Check exclusion patterns
                        exclude = False
                        for pattern in self.exclude_patterns:
                            if pattern.search(file):
                                exclude = True
                                break
                        
                        if not exclude:
                            structure.append(f"  {file}")
        
        return structure
    
    def get_file_language(self, file_path):
        """Determines programming language based on file extension."""
        ext = os.path.splitext(file_path.lower())[1]
        languages = {
            '.py': 'python',
            '.rb': 'ruby',
            '.js': 'javascript',
            '.html': 'html',
            '.css': 'css',
            '.json': 'json',
            '.yml': 'yaml',
            '.yaml': 'yaml',
            '.md': 'markdown',
            '.txt': 'text',
            '.sh': 'bash',
            '.java': 'java',
            '.c': 'c',
            '.cpp': 'cpp',
            '.h': 'c',
            '.php': 'php',
            '.sql': 'sql',
            '.xml': 'xml',
            '.go': 'go',
            '.rs': 'rust',
            '.ts': 'typescript',
            '.swift': 'swift',
            '.kt': 'kotlin',
            '.dart': 'dart',
            '.pl': 'perl',
            '.r': 'r',
            '.lua': 'lua',
            '.scala': 'scala',
            '.cs': 'csharp',
            '.vb': 'vb'
        }
        return languages.get(ext, '')
    
    def estimate_tokens(self, text):
        if not text.strip():
            return 0
        tokens = text.strip().split()
        word_count = len(tokens)
        if re.search(r'[.!?]$', text.strip()):
            return word_count + 1
        return word_count

    
    def check_security(self, files):
        """Checks for potential security issues in files."""
        suspicious_files = []
        
        for file_path in files:
            # Check suspicious file extensions
            _, ext = os.path.splitext(file_path.lower())
            if ext in self.suspicious_extensions:
                # Simple heuristic - check file size and sample content
                file_size = os.path.getsize(file_path)
                if file_size > 1024 * 1024:  # Larger than 1MB
                    suspicious_files.append(file_path)
                    continue
                
                # Check content for suspicious patterns
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read(4096)  # Read only first 4KB
                        if re.search(r'(exec|eval|system|subprocess|os\.)', content):
                            suspicious_files.append(file_path)
                except Exception:
                    pass  # Ignore errors reading binary files
        
        return suspicious_files
    
    # Document conversion functions
    def _format_table_as_markdown(self, table_data):
        """Converts a 2D list (from pdfplumber) to a markdown pipe table."""
        if not table_data or not table_data[0]:
            return ""

        # Normalize column count across rows
        max_cols = max(len(row) for row in table_data)
        rows = []
        for row in table_data:
            cleaned = []
            for i in range(max_cols):
                cell = row[i] if i < len(row) else ""
                if cell is None:
                    cell = ""
                # Strip whitespace and escape pipe/newline characters
                cell = str(cell).strip()
                cell = cell.replace("|", "\\|")
                cell = cell.replace("\n", " ")
                cleaned.append(cell)
            rows.append(cleaned)

        lines = []
        # Header row
        lines.append("| " + " | ".join(rows[0]) + " |")
        # Separator row
        lines.append("| " + " | ".join("---" for _ in range(max_cols)) + " |")
        # Data rows
        for row in rows[1:]:
            lines.append("| " + " | ".join(row) + " |")

        return "\n".join(lines)

    def _table_cell_density(self, table_data):
        """Compute fraction of non-empty cells in a 2D table."""
        total = sum(len(row) for row in table_data)
        if total == 0:
            return 0.0
        nonempty = sum(
            1 for row in table_data
            for cell in row if cell and str(cell).strip()
        )
        return nonempty / total

    def convert_pdf_with_tables(self, filepath):
        """Converts PDF to markdown with table detection using pdfplumber.

        Uses line-based detection first (bordered tables). Falls back to
        text-based detection but validates quality (cell density >= 30%)
        to avoid gridifying entire pages. Pages without quality tables
        use layout-preserving text extraction.

        Returns (markdown_text, 'pdfplumber-tables') on success,
        or (None, None) if pdfplumber is unavailable or fails.
        """
        if not PDFPLUMBER_AVAILABLE:
            return None, None

        try:
            pages_output = []
            found_any_table = False

            with pdfplumber.open(filepath) as pdf:
                for page in pdf.pages:
                    # Try default (lines-based) strategy for bordered tables
                    tables = page.find_tables()
                    used_text_strategy = False

                    # If no bordered tables, try text-based strategy
                    if not tables:
                        text_tables = page.find_tables(
                            table_settings={
                                "vertical_strategy": "text",
                                "horizontal_strategy": "text",
                            }
                        )
                        # Validate text-strategy tables: reject low-density
                        # ones that are just the whole page gridified
                        quality_tables = []
                        for t in text_tables:
                            data = t.extract()
                            if data and self._table_cell_density(data) >= 0.3:
                                quality_tables.append(t)
                        if quality_tables:
                            tables = quality_tables
                            used_text_strategy = True

                    if not tables:
                        # No quality tables — use layout-preserving text
                        text = page.extract_text(layout=True)
                        if text:
                            pages_output.append(text)
                        continue

                    found_any_table = True

                    # Collect table bounding boxes and markdown
                    table_items = []
                    table_bboxes = []
                    for table in tables:
                        data = table.extract()
                        if data:
                            md = self._format_table_as_markdown(data)
                            if md:
                                bbox = table.bbox  # (x0, top, x1, bottom)
                                table_items.append((bbox[1], md))
                                table_bboxes.append(bbox)

                    # Filter out characters within table areas to avoid
                    # duplication, then extract remaining text
                    filtered_page = page
                    for bbox in table_bboxes:
                        filtered_page = filtered_page.filter(
                            lambda obj, b=bbox: not (
                                obj.get("top", 0) >= b[1]
                                and obj.get("top", 0) <= b[3]
                                and obj.get("x0", 0) >= b[0]
                                and obj.get("x0", 0) <= b[2]
                            )
                        )

                    remaining_text = (
                        filtered_page.extract_text(layout=True) or ""
                    )

                    page_parts = []
                    if remaining_text.strip():
                        page_parts.append((0, remaining_text.strip()))

                    page_parts.extend(table_items)

                    # Sort by vertical position
                    page_parts.sort(key=lambda x: x[0])

                    page_content = "\n\n".join(part[1] for part in page_parts)
                    if page_content:
                        pages_output.append(page_content)

            if pages_output:
                result = "\n\n---\n\n".join(pages_output)
                method = "pdfplumber-tables" if found_any_table else "pdfplumber"
                print(f"Successfully converted PDF using {method}: {filepath}")
                return result, method

            return None, None
        except Exception as e:
            print(f"pdfplumber failed for {filepath}: {e}")
            return None, None

    @staticmethod
    def _html_tables_to_markdown(text):
        """Convert HTML <table> blocks in *text* to markdown pipe tables.

        Handles both bare ``<table>…</table>`` and PaddleOCR's wrapper
        ``<div …><html><body><table>…</table></body></html></div>``.
        """
        import re

        # Match PaddleOCR wrapper or bare <table> blocks
        pattern = re.compile(
            r'(?:<div[^>]*>\s*<html>\s*<body>\s*)?'
            r'<table.*?</table>'
            r'(?:\s*</body>\s*</html>\s*</div>)?',
            re.DOTALL,
        )

        def _convert(match):
            h = html2text.HTML2Text()
            h.body_width = 0
            h.protect_links = True
            return h.handle(match.group(0)).strip()

        return pattern.sub(_convert, text)

    def convert_pdf_with_paddleocr(self, filepath):
        """Convert PDF using PaddleOCR PP-StructureV3 (ML-based document analysis).

        PaddleOCR is Apache 2.0 licensed.  PaddlePaddle only supports
        Python ≤3.12, so we invoke PaddleOCR in its uv-managed venv via
        subprocess — same isolation pattern as mineru/pandoc/soffice.

        Returns (text, "paddleocr") on success, (None, None) on failure.
        """
        if not self.is_paddleocr_available():
            return None, None

        try:
            # Inline script executed in the paddleocr tool's Python env
            script = textwrap.dedent(f"""\
                import json, sys, os
                os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'
                from paddleocr import PPStructureV3
                pipeline = PPStructureV3(
                    device='cpu',
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_seal_recognition=False,
                )
                result = pipeline.predict(input=sys.argv[1])
                pages = []
                for page_result in result:
                    md = getattr(page_result, 'markdown', None)
                    if md and md.get('markdown_texts'):
                        pages.append(md)
                if not pages:
                    sys.exit(1)
                try:
                    merged = pipeline.concatenate_markdown_pages(pages)
                    text = merged['markdown_texts']
                except (AttributeError, TypeError, KeyError):
                    text = '\\n\\n---\\n\\n'.join(
                        p['markdown_texts'] for p in pages
                    )
                print(text)
            """)
            env = os.environ.copy()
            env['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'
            proc = subprocess.run(
                [self._paddleocr_python, '-c', script, filepath],
                capture_output=True, text=True, timeout=300, env=env,
            )
            if proc.returncode != 0:
                print(f"PaddleOCR failed for {filepath}: {proc.stderr[:500]}")
                return None, None

            text = proc.stdout.strip()
            if not text:
                print(f"PaddleOCR produced no output for {filepath}")
                return None, None

            # PaddleOCR renders tables as HTML; convert to markdown
            text = self._html_tables_to_markdown(text)

            print(f"Successfully converted PDF using PaddleOCR: {filepath}")
            return text, "paddleocr"
        except Exception as e:
            print(f"PaddleOCR failed for {filepath}: {e}")
            return None, None

    def convert_pdf_with_mineru(self, filepath):
        """Convert PDF using the MinerU CLI (ML-based layout/table detection).

        MinerU is invoked as a subprocess to keep its AGPL licence separate
        from documix's MIT licence — same isolation pattern as pandoc/soffice.

        Returns (text, "mineru") on success, (None, None) on failure.
        """
        if not self.is_mineru_available():
            return None, None

        tmpdir = None
        try:
            tmpdir = tempfile.mkdtemp(prefix="documix_mineru_")
            cmd = [
                'mineru', '-p', filepath, '-o', tmpdir,
                '-b', 'pipeline', '-d', 'cpu',
            ]
            subprocess.run(
                cmd, check=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=120,
            )

            stem = Path(filepath).stem
            md_path = os.path.join(tmpdir, stem, 'auto', f'{stem}.md')
            if not os.path.exists(md_path):
                print(f"MinerU output not found at {md_path}")
                return None, None

            with open(md_path, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()

            text = self._html_tables_to_markdown(text)
            print(f"Successfully converted PDF using MinerU: {filepath}")
            return text, "mineru"
        except (subprocess.SubprocessError, subprocess.TimeoutExpired,
                FileNotFoundError, OSError) as e:
            print(f"MinerU failed for {filepath}: {e}")
            return None, None
        finally:
            if tmpdir and os.path.exists(tmpdir):
                shutil.rmtree(tmpdir, ignore_errors=True)

    def _try_pdf_markitdown_uvx(self, filepath):
        """Try converting PDF using uvx markitdown."""
        if not self.is_uvx_available():
            return None, None
        try:
            with tempfile.NamedTemporaryFile(suffix='.md', delete=False) as temp:
                temp_name = temp.name
            subprocess.run(['uvx', 'markitdown[pdf]', filepath, '-o', temp_name], check=True)
            with open(temp_name, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()
            os.unlink(temp_name)
            print(f"Successfully converted PDF using uvx markitdown: {filepath}")
            return text, "markitdown-uvx"
        except (subprocess.SubprocessError, FileNotFoundError):
            print(f"uvx markitdown failed for: {filepath}")
            return None, None

    def _try_pdf_markitdown(self, filepath):
        """Try converting PDF using markitdown directly."""
        try:
            with tempfile.NamedTemporaryFile(suffix='.md', delete=False) as temp:
                temp_name = temp.name
            subprocess.run(['markitdown', filepath, '-o', temp_name], check=True)
            with open(temp_name, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()
            os.unlink(temp_name)
            print(f"Successfully converted PDF using markitdown: {filepath}")
            return text, "markitdown"
        except (subprocess.SubprocessError, FileNotFoundError):
            print(f"markitdown not available or failed for: {filepath}")
            return None, None

    def _try_pdf_pdftotext(self, filepath):
        """Try converting PDF using pdftotext."""
        try:
            with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as temp:
                temp_name = temp.name
            subprocess.run(['pdftotext', '-layout', filepath, temp_name], check=True)
            with open(temp_name, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()
            os.unlink(temp_name)
            print(f"Successfully converted PDF using pdftotext: {filepath}")
            return text, "pdftotext"
        except (subprocess.SubprocessError, FileNotFoundError):
            print(f"pdftotext not available or failed for: {filepath}")
            return None, None

    def convert_pdf_to_text(self, filepath):
        """Converts PDF to text using configured converters.
        Default order: MinerU, pdfplumber, uvx markitdown,
        markitdown, pdftotext, PaddleOCR."""
        dispatch = {
            'paddleocr': self.convert_pdf_with_paddleocr,
            'mineru': self.convert_pdf_with_mineru,
            'pdfplumber': self.convert_pdf_with_tables,
            'markitdown-uvx': self._try_pdf_markitdown_uvx,
            'markitdown': self._try_pdf_markitdown,
            'pdftotext': self._try_pdf_pdftotext,
        }
        for name in self.get_converters('pdf'):
            text, method = dispatch[name](filepath)
            if text is not None:
                return text, method
        print(f"WARNING: Failed to convert PDF: {filepath}")
        return f"[Failed to convert PDF file: {os.path.basename(filepath)}]", "failed"

    def convert_epub_to_text(self, filepath):
        """Converts EPUB to text using Calibre's ebook-convert tool."""
        conversion_method = "unknown"
        try:
            # Try using calibre (ebook-convert)
            with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as temp:
                temp_name = temp.name
            
            subprocess.run(['ebook-convert', filepath, temp_name], check=True)
            
            with open(temp_name, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()
            
            os.unlink(temp_name)
            conversion_method = "ebook-convert"
            print(f"Successfully converted EPUB using ebook-convert: {filepath}")
            return text, conversion_method
        except (subprocess.SubprocessError, FileNotFoundError):
            print(f"WARNING: Failed to convert EPUB: {filepath}")
            print("Make sure you have Calibre installed")
            conversion_method = "failed"
            return f"[Failed to convert EPUB file: {os.path.basename(filepath)}]", conversion_method

    def _try_docx_pandoc(self, filepath):
        """Try converting DOCX using pandoc."""
        try:
            with tempfile.NamedTemporaryFile(suffix='.md', delete=False) as temp:
                temp_name = temp.name
            try:
                subprocess.run(
                    ['pandoc', '-f', 'docx', '-t', 'markdown', filepath, '-o', temp_name],
                    check=True,
                    stderr=subprocess.PIPE,
                    text=True
                )
            except subprocess.CalledProcessError as e:
                print(f"WARNING: Pandoc error: {e.stderr}")
                raise
            with open(temp_name, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()
            os.unlink(temp_name)
            print(f"Successfully converted DOCX using pandoc: {filepath}")
            return text, "pandoc"
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            print(f"pandoc not available or failed for DOCX: {filepath}")
            return None, None

    def _try_docx_docx2txt(self, filepath):
        """Try converting DOCX using docx2txt."""
        if not DOCX2TXT_AVAILABLE:
            return None, None
        try:
            print(f"Attempting DOCX conversion with docx2txt for {filepath}")
            text = docx2txt.process(filepath)
            if text and len(text.strip()) > 0:
                print(f"Successfully converted DOCX with docx2txt: {filepath}")
                return text, "docx2txt"
            else:
                print(f"docx2txt produced empty output for {filepath}")
                return None, None
        except Exception as e:
            print(f"docx2txt failed: {str(e)}")
            return None, None

    def convert_docx_to_text(self, filepath):
        """Converts DOCX to text using configured converters.
        Default order: pandoc, docx2txt."""
        dispatch = {
            'pandoc': self._try_docx_pandoc,
            'docx2txt': self._try_docx_docx2txt,
        }
        for name in self.get_converters('docx'):
            text, method = dispatch[name](filepath)
            if text is not None:
                return text, method
        print(f"WARNING: Failed to convert DOCX: {filepath}")
        return f"[Failed to convert DOCX file: {os.path.basename(filepath)}]", "failed"

    def convert_doc_to_text(self, filepath):
        """Converts DOC to DOCX using LibreOffice soffice command, then processes as DOCX."""
        conversion_method = "unknown"
        try:
            # Create a temporary directory for conversion
            temp_dir = tempfile.mkdtemp()
            self.temp_dirs.append(temp_dir)
            
            # Get the filename and create output path
            filename = os.path.basename(filepath)
            output_docx = os.path.join(temp_dir, f"{os.path.splitext(filename)[0]}.docx")
            
            # Copy the file to temp directory
            temp_doc = os.path.join(temp_dir, filename)
            shutil.copy2(filepath, temp_doc)
            
            # Check if file exists and has content
            if not os.path.exists(temp_doc):
                raise FileNotFoundError(f"Failed to copy {filepath} to {temp_doc}")
                
            file_size = os.path.getsize(temp_doc)
            if file_size == 0:
                raise ValueError(f"File {filepath} is empty (0 bytes)")
            
            print(f"Converting DOC file: {temp_doc} (size: {file_size} bytes)")
            
            # Convert DOC to DOCX using LibreOffice with error capturing
            try:
                result = subprocess.run(
                    ['soffice', '--convert-to', 'docx', '--outdir', temp_dir, temp_doc], 
                    check=True,
                    stderr=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    text=True
                )
                print(f"LibreOffice conversion successful: {result.stdout}")
            except subprocess.CalledProcessError as e:
                print(f"WARNING: LibreOffice conversion error: {e.stderr}")
                raise
            
            # Verify the output file exists
            if not os.path.exists(output_docx):
                raise FileNotFoundError(f"LibreOffice did not create expected output file: {output_docx}")
                
            # Process the DOCX file
            text, docx_method = self.convert_docx_to_text(output_docx)
            
            conversion_method = f"soffice+{docx_method}"
            print(f"Successfully converted DOC using {conversion_method}: {filepath}")
            return text, conversion_method
            
        except (subprocess.SubprocessError, FileNotFoundError, ValueError) as e:
            print(f"WARNING: Failed to convert DOC: {filepath}")
            print(f"Error details: {str(e)}")
            print("Make sure you have LibreOffice installed")
            conversion_method = "failed"
            return f"[Failed to convert DOC file: {os.path.basename(filepath)}]", conversion_method

    def _try_rtf_pandoc(self, filepath):
        """Try converting RTF using pandoc."""
        try:
            with tempfile.NamedTemporaryFile(suffix='.md', delete=False) as temp:
                temp_name = temp.name
            subprocess.run(
                ['pandoc', '-f', 'rtf', '-t', 'markdown', filepath, '-o', temp_name],
                check=True,
                stderr=subprocess.PIPE,
                text=True
            )
            with open(temp_name, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()
            os.unlink(temp_name)
            print(f"Successfully converted RTF using pandoc: {filepath}")
            return text, "pandoc"
        except (subprocess.SubprocessError, FileNotFoundError):
            print(f"pandoc not available or failed for RTF: {filepath}")
            return None, None

    def _try_rtf_unrtf(self, filepath):
        """Try converting RTF using unrtf."""
        try:
            result = subprocess.run(
                ['unrtf', '--text', filepath],
                check=True,
                capture_output=True,
                text=True
            )
            print(f"Successfully converted RTF using unrtf: {filepath}")
            return result.stdout, "unrtf"
        except (subprocess.SubprocessError, FileNotFoundError):
            print(f"unrtf not available or failed for RTF: {filepath}")
            return None, None

    def _try_rtf_striprtf(self, filepath):
        """Try converting RTF using striprtf Python library."""
        try:
            from striprtf.striprtf import rtf_to_text
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                rtf_content = f.read()
            text = rtf_to_text(rtf_content)
            print(f"Successfully converted RTF using striprtf: {filepath}")
            return text, "striprtf"
        except ImportError:
            print(f"striprtf not installed: {filepath}")
            return None, None
        except Exception as e:
            print(f"striprtf failed: {str(e)}")
            return None, None

    def convert_rtf_to_text(self, filepath):
        """Converts RTF to text using configured converters.
        Default order: pandoc, unrtf, striprtf."""
        dispatch = {
            'pandoc': self._try_rtf_pandoc,
            'unrtf': self._try_rtf_unrtf,
            'striprtf': self._try_rtf_striprtf,
        }
        for name in self.get_converters('rtf'):
            text, method = dispatch[name](filepath)
            if text is not None:
                return text, method
        print(f"WARNING: Failed to convert RTF: {filepath}")
        return f"[Failed to convert RTF file: {os.path.basename(filepath)}]", "failed"

    def convert_txt_to_text(self, filepath):
        """Reads text from TXT/MD/other text files."""
        conversion_method = "unknown"
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()
            conversion_method = "direct_read"
            print(f"Successfully read text file using direct read: {filepath}")
            return text, conversion_method
        except Exception as e:
            print(f"WARNING: Failed to read file: {filepath}")
            print(f"Error: {e}")
            conversion_method = "failed"
            return f"[Failed to read file: {os.path.basename(filepath)}]", conversion_method
    
    def extract_zip(self, filepath):
        """Extracts a ZIP file and processes its contents."""
        conversion_method = "unknown"
        try:
            # Create a temporary directory for ZIP extraction
            temp_dir = tempfile.mkdtemp()
            self.temp_dirs.append(temp_dir)
            
            print(f"📦 Extracting ZIP: {os.path.basename(filepath)}")
            
            # Extract the ZIP file
            with zipfile.ZipFile(filepath, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            
            # Create a summary of ZIP contents
            file_list = []
            zip_content_summary = f"# ZIP Archive Contents: {os.path.basename(filepath)}\n\n"
            zip_content_summary += "## Files in archive:\n\n"
            
            # Walk through the extracted directory
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, temp_dir)
                    file_list.append(rel_path)
            
            # Sort the file list for a clean representation
            file_list.sort()
            for file in file_list:
                zip_content_summary += f"- {file}\n"
            
            # Process each file in the ZIP archive
            zip_content_summary += "\n## Extracted file contents:\n\n"
            
            extraction_methods = []
            for file_path in file_list:
                full_path = os.path.join(temp_dir, file_path)
                _, ext = os.path.splitext(file_path.lower())
                
                # Process only if file extension is in include list
                if ext in self.include_extensions:
                    zip_content_summary += f"### File: {file_path}\n\n"
                    
                    # Get file content
                    try:
                        content, method = self.process_file(full_path)
                        extraction_methods.append(method)
                        
                        # Add file content as a code block with appropriate language
                        file_language = self.get_file_language(file_path)
                        if file_language:
                            zip_content_summary += f"```{file_language}\n{content}\n```\n\n"
                        else:
                            zip_content_summary += f"```\n{content}\n```\n\n"
                    except Exception as e:
                        zip_content_summary += f"[Error processing file: {str(e)}]\n\n"
            
            conversion_method = "zip_extract+" + "+".join(set(extraction_methods))
            print(f"Successfully processed ZIP using extraction methods: {conversion_method}: {filepath}")
            return zip_content_summary, conversion_method
            
        except zipfile.BadZipFile:
            conversion_method = "failed-bad_zip"
            return f"[Error: {os.path.basename(filepath)} is not a valid ZIP file]", conversion_method
        except Exception as e:
            conversion_method = "failed-exception"
            return f"[Error processing ZIP file: {str(e)}]", conversion_method
    
    
    
    def format_email_single(self, out_file, email_info, content):
        """Format output for single email mode."""
        out_file.write("# Email Analysis Report\n\n")
        out_file.write(f"Generated by DocuMix v{self.version} on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        out_file.write("Processing mode: Single Email\n\n")
        
        out_file.write("## Email Summary\n\n")
        out_file.write("This document contains a complete analysis of an email message, including:\n")
        out_file.write("- Full email headers and metadata\n")
        out_file.write("- Converted email body content (HTML → Markdown)\n")
        out_file.write("- Processed attachments with extracted content\n")
        out_file.write("- Communication context and authentication details\n\n")
        
        out_file.write("## Email Details\n\n")
        out_file.write("### Message Information\n")
        out_file.write(f"- **Subject**: {email_info.get('subject', 'No Subject')}\n")
        out_file.write(f"- **From**: {email_info.get('from', 'Unknown')}\n")
        out_file.write(f"- **To**: {email_info.get('to', 'Unknown')}\n")
        out_file.write(f"- **Date**: {email_info.get('date', 'Unknown')}\n")
        
        if email_info.get('cc'):
            out_file.write(f"- **CC**: {email_info['cc']}\n")
        
        total_size = email_info.get('size', 0) + sum(att.get('size', 0) for att in email_info.get('attachments', []))
        out_file.write(f"- **Size**: {self.format_size(total_size)}\n\n")
        
        # Authentication section if available
        if email_info.get('auth_results') or email_info.get('dkim_signature'):
            out_file.write("### Authentication & Security\n")
            if email_info.get('auth_results'):
                # Parse authentication results
                auth = email_info['auth_results']
                if 'spf=pass' in auth:
                    out_file.write("- **SPF**: Pass\n")
                elif 'spf=fail' in auth:
                    out_file.write("- **SPF**: Fail\n")
                
                if 'dkim=pass' in auth:
                    out_file.write("- **DKIM**: Pass\n")
                elif 'dkim=fail' in auth:
                    out_file.write("- **DKIM**: Fail\n")
                
                if 'dmarc=pass' in auth:
                    out_file.write("- **DMARC**: Pass\n")
                elif 'dmarc=fail' in auth:
                    out_file.write("- **DMARC**: Fail\n")
            out_file.write("\n")
        
        # Attachments summary
        attachments = email_info.get('attachments', [])
        if attachments:
            out_file.write("### Attachments Summary\n")
            out_file.write(f"- **Count**: {len(attachments)} files\n")
            total_att_size = sum(att.get('size', 0) for att in attachments)
            out_file.write(f"- **Total Size**: {self.format_size(total_att_size)}\n")
            
            # Group by type
            types = {}
            for att in attachments:
                ext = os.path.splitext(att['filename'].lower())[1]
                types[ext] = types.get(ext, 0) + 1
            
            type_list = [f"{ext.upper()[1:]} ({count})" for ext, count in types.items()]
            out_file.write(f"- **Types**: {', '.join(type_list)}\n\n")
        
        # Email content section
        out_file.write("## Email Content\n\n")
        out_file.write(content)
        out_file.write("\n\n")
        
        # Processing notes
        out_file.write("## Processing Notes\n")
        out_file.write("- HTML content converted to Markdown using html2text\n")
        if email_info.get('attachments_source'):
            out_file.write(f"- Attachments source: {email_info['attachments_source']}\n")
        out_file.write("\n")
        
        # Statistics
        out_file.write("## Statistics\n")
        out_file.write(f"- Total characters: {len(content):,}\n")
        out_file.write(f"- Estimated tokens: {self.estimate_tokens(content):,}\n")
    
    
    
    def format_size(self, size_bytes):
        """Format file size in human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
    
    def process_email(self, filepath):
        """Process an email file and its attachments."""
        conversion_method = "unknown"
        start_time = time.time()  # Track processing start time
        try:
            print(f"📧 Processing email: {os.path.basename(filepath)}")
            
            # Check if this is actually an email in a directory with attachments
            email_dir = os.path.dirname(filepath)
            
            # Create email processor
            email_processor = EmailProcessor(filepath)
            
            # Parse email
            if not email_processor.parse_email():
                conversion_method = "failed-parse"
                return f"[Failed to parse email file: {os.path.basename(filepath)}]", conversion_method, {}
            
            # Collect email metadata for collection analysis
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
            
            
            # Process attachments (will use folder if exists)
            email_processor.process_attachments()
            
            # Get email content
            email_content, attachments = email_processor.compile_output()
            
            # Store attachment info
            email_info['attachments'] = attachments
            
            # Process each attachment
            if attachments:
                email_content += "\n"
                for i, attachment in enumerate(attachments, 1):
                    att_path = attachment['path']
                    att_name = attachment['filename']
                    att_size = email_processor.format_size(attachment['size'])
                    
                    email_content += f"### {i}. {att_name} ({att_size})\n\n"
                    
                    # Check if attachment can be processed
                    _, ext = os.path.splitext(att_path.lower())
                    if ext in self.include_extensions and ext != '.eml':  # Avoid recursive email processing
                        try:
                            # Process the attachment
                            content, method = self.process_file(att_path)
                            
                            # PDF/ZIP content is already markdown, don't wrap
                            att_ext = os.path.splitext(att_path.lower())[1]
                            if att_ext in ('.pdf', '.zip'):
                                email_content += f"{content}\n\n"
                            else:
                                file_language = self.get_file_language(att_path)
                                if file_language:
                                    email_content += f"```{file_language}\n{content}\n```\n\n"
                                else:
                                    email_content += f"```\n{content}\n```\n\n"
                        except Exception as e:
                            email_content += f"[Error processing attachment: {str(e)}]\n\n"
                    else:
                        email_content += f"[Attachment type '{ext}' not supported for extraction]\n\n"
            
            # Add statistics
            email_content += "\n---\n## Statistics\n"
            email_content += f"- Total attachments: {len(attachments)}\n"
            if attachments:
                total_size = sum(att['size'] for att in attachments)
                email_content += f"- Total size: {email_processor.format_size(total_size)}\n"
            email_content += f"- Processing time: {time.time() - start_time:.2f}s\n"
            
            conversion_method = f"email+{email_processor.metadata.get('attachments_source', 'unknown').lower().replace(' ', '_')}"
            return email_content, conversion_method, email_info
            
        except Exception as e:
            print(f"ERROR: Failed to process email {filepath}: {str(e)}")
            conversion_method = "failed-exception"
            return f"[Error processing email file: {str(e)}]", conversion_method, {}
    
    def process_file(self, file_path):
        """Processes a single file and returns its content and conversion method used."""
        ext = os.path.splitext(file_path.lower())[1]
        
        if ext == '.pdf':
            return self.convert_pdf_to_text(file_path)
        elif ext == '.epub':
            return self.convert_epub_to_text(file_path)
        elif ext == '.docx':
            return self.convert_docx_to_text(file_path)
        elif ext == '.doc':
            return self.convert_doc_to_text(file_path)
        elif ext == '.rtf':
            return self.convert_rtf_to_text(file_path)
        elif ext == '.zip':
            return self.extract_zip(file_path)
        elif ext == '.eml':
            content, method, _ = self.process_email(file_path)
            return content, method
        else:  # .txt, .md, .py, etc.
            return self.convert_txt_to_text(file_path)
    
    def compile(self):
        """Compiles all documents into a single Markdown file."""
        # Start time measurement
        start_time = time.time()
        
        # Display header
        print(f"📦 DocuMix v{self.version}")
        
        filtered_files = self.collect_files()
        
        if not filtered_files:
            print("❌ No files found to process.")
            return False
        
        # Set number of files
        self.total_files = len(filtered_files)
        
        # Detect processing mode
        processing_mode = self.detect_processing_mode(filtered_files)
        print(f"📋 Processing mode: {processing_mode}")
        
        # Security check
        print("🔎 Checking files for security issues...")
        suspicious_files = self.check_security(filtered_files)
        
        # Collecting file statistics
        print("📊 Collecting file statistics...")
        
        structure = self.get_directory_structure()
        
        try:
            with open(self.output_file, 'w', encoding='utf-8') as out_file:
                # Use appropriate format based on mode
                if processing_mode == 'single_email':
                    # Process the single email and use special format
                    file_path = filtered_files[0]
                    content, conversion_method, email_info = self.process_email(file_path)
                    
                    # Use single email format
                    self.format_email_single(out_file, email_info, content)
                    
                    # Update statistics
                    self.total_chars = len(content)
                    self.total_tokens = self.estimate_tokens(content)
                    
                    elapsed_time = time.time() - start_time
                    
                    # Display summary  
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
                    
                else:
                    # Use standard format for mixed content
                    out_file.write("This file is a merged representation of all documents, combined into a single document.\n\n")
                
                # Continue with standard format if not single email mode
                if processing_mode != 'single_email':
                    # Summary
                    out_file.write("# File Summary\n\n")
                out_file.write("## Purpose\n")
                out_file.write("This file contains a packed representation of the entire directory's contents.\n")
                out_file.write("It is designed to be easily consumable by AI systems for analysis, review,\n")
                out_file.write("or other automated processes.\n\n")
                
                out_file.write("## File Format\n")
                out_file.write("The content is organized as follows:\n")
                out_file.write("1. This summary section\n")
                out_file.write("2. Directory information\n")
                out_file.write("3. Directory structure\n")
                out_file.write("4. Multiple file entries, each consisting of:\n")
                out_file.write("  a. A header with the file path (## File: path/to/file)\n")
                out_file.write("  b. The full contents of the file in a code block\n\n")
                
                out_file.write("## Usage Guidelines\n")
                out_file.write("- This file should be treated as read-only. Any changes should be made to the\n")
                out_file.write("  original files, not this packed version.\n")
                out_file.write("- When processing this file, use the file path to distinguish\n")
                out_file.write("  between different files in the directory.\n\n")
                
                out_file.write("## Notes\n")
                out_file.write("- Some files may have been excluded based on extension filters or exclusion patterns\n")
                out_file.write("- Binary files are only partially supported (PDF, EPUB, DOCX) and conversion quality may vary\n")
                out_file.write("- ZIP files are automatically extracted and their contents are included\n")
                out_file.write("- Email files (.eml) are parsed with attachments processed from local folders if available\n")
                out_file.write("- Files matching specified exclude patterns are skipped\n\n")
                
                # Directory information
                out_file.write("# Directory Information\n")
                out_file.write(f"- Source Directory: {self.source_dir}\n")
                out_file.write(f"- Compilation Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                out_file.write(f"- Total Files Processed: {len(filtered_files)}\n\n")
                
                # Directory structure
                out_file.write("# Directory Structure\n")
                out_file.write("```\n")
                for item in structure:
                    out_file.write(f"{item}\n")
                out_file.write("```\n\n")
                
                # File contents
                out_file.write("# Files\n\n")
                
                for file_path in filtered_files:
                    rel_path = os.path.relpath(file_path, self.source_dir)
                    file_language = self.get_file_language(file_path)
                    
                    print(f"⚙️  Processing: {rel_path}")
                    
                    # File content
                    content, conversion_method = self.process_file(file_path)
                    
                    # File header with conversion method
                    out_file.write(f"## File: {rel_path} (converted with {conversion_method})\n")
                    
                    # Collecting statistics
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
                    
                    # Adding content as a code block with appropriate language
                    # For ZIP and EML files, content is already formatted in Markdown so we don't wrap it in code block
                    ext = os.path.splitext(file_path.lower())[1]
                    if ext in ['.zip', '.eml', '.pdf']:
                        out_file.write(content)
                    else:
                        # Adding content as a code block with appropriate language
                        backticks = "````"  # Using four to maintain compatibility with Repomix format
                        if file_language:
                            out_file.write(f"{backticks}{file_language}\n")
                        else:
                            out_file.write(f"{backticks}\n")
                        
                        out_file.write(content)
                        
                        # Closing code block
                        out_file.write(f"\n{backticks}\n\n")

                # Sort file statistics by character count
                self.file_stats.sort(key=lambda x: x['chars'], reverse=True)

                # End time measurement
                elapsed_time = time.time() - start_time

                # Display summary
                print("\n✔ Packing completed successfully!")

                # Top 5 files by character and token count
                print("\n📈 Top 5 Files by Character Count and Token Count:")
                print("──────────────────────────────────────────────────")
                for i, stat in enumerate(self.file_stats[:5], 1):
                    print(f"{i}. {stat['path']} ({stat['chars']:,} chars, {stat['tokens']:,} tokens, via {stat['conversion_method']})")

                # Security check result
                print("\n🔎 Security Check:")
                print("─────────────────────")
                if suspicious_files:
                    print("❌ Suspicious files detected:")
                    for sus_file in suspicious_files:
                        print(f"  - {os.path.relpath(sus_file, self.source_dir)}")
                else:
                    print("✔ No suspicious files detected.")

                # Packing summary
                print("\n📊 Pack Summary:")
                print("─────────────────────")
                print(f"  Total Files: {self.total_files:,} files")
                print(f"  Total Chars: {self.total_chars:,} chars")
                print(f" Total Tokens: {self.total_tokens:,} tokens")
                print(f"       Output: {self.output_file}")
                print(f"     Security: {'❌ Suspicious files detected' if suspicious_files else '✔ No suspicious files detected'}")
                print(f"        Time: {elapsed_time:.2f} seconds")

                print("\n🎉 All Done! Your documents have been successfully packed.")

                return True
            
        finally:
            # Clean up temporary directories
            for temp_dir in self.temp_dirs:
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass

def check_converter_availability():
    """Check which converters are available on this system.

    Returns a dict of {format: [available_converter_names]}.
    """
    available = {'pdf': [], 'docx': [], 'rtf': []}

    # PDF converters
    if shutil.which('paddleocr'):
        available['pdf'].append('paddleocr')
    if shutil.which('mineru'):
        available['pdf'].append('mineru')
    if PDFPLUMBER_AVAILABLE:
        available['pdf'].append('pdfplumber')
    # markitdown-uvx: need uvx
    try:
        subprocess.run(
            ['uvx', '--version'], check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        available['pdf'].append('markitdown-uvx')
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    if shutil.which('markitdown'):
        available['pdf'].append('markitdown')
    if shutil.which('pdftotext'):
        available['pdf'].append('pdftotext')

    # DOCX converters
    if shutil.which('pandoc'):
        available['docx'].append('pandoc')
    if DOCX2TXT_AVAILABLE:
        available['docx'].append('docx2txt')

    # RTF converters
    if shutil.which('pandoc'):
        available['rtf'].append('pandoc')
    if shutil.which('unrtf'):
        available['rtf'].append('unrtf')
    try:
        from striprtf.striprtf import rtf_to_text  # noqa: F401
        available['rtf'].append('striprtf')
    except ImportError:
        pass

    return available


def word_similarity(text_a, text_b):
    """Compute word-level similarity between two texts (0.0-1.0)."""
    if not text_a and not text_b:
        return 1.0
    if not text_a or not text_b:
        return 0.0
    words_a = text_a.split()
    words_b = text_b.split()
    return difflib.SequenceMatcher(None, words_a, words_b).ratio()


def _format_to_extensions():
    """Map format names to file extensions."""
    return {
        'pdf': ['.pdf'],
        'docx': ['.docx'],
        'rtf': ['.rtf'],
        'doc': ['.doc'],
    }


def _extension_to_format(ext):
    """Map a file extension to a format name."""
    ext = ext.lower()
    mapping = {
        '.pdf': 'pdf',
        '.docx': 'docx',
        '.rtf': 'rtf',
        '.doc': 'doc',
    }
    return mapping.get(ext)


def run_benchmark(files, runs=3, output_dir='benchmark/', formats='all'):
    """Run benchmark across converters for the given files.

    Args:
        files: list of file paths to benchmark
        runs: number of timing iterations per converter
        output_dir: directory for results
        formats: 'all' or comma-separated format names to benchmark
    """
    available = check_converter_availability()
    allowed_formats = None
    if formats != 'all':
        allowed_formats = set(f.strip() for f in formats.split(','))

    # Discover resource files
    resources_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'resources'
    )
    resource_files = []
    if os.path.isdir(resources_dir):
        for root, _, fnames in os.walk(resources_dir):
            for fname in fnames:
                resource_files.append(os.path.join(root, fname))

    all_files = resource_files + list(files)

    # Group files by format
    files_by_format = {}
    for fpath in all_files:
        _, ext = os.path.splitext(fpath)
        fmt = _extension_to_format(ext)
        if fmt is None:
            continue
        # doc uses docx converters (via soffice)
        converter_fmt = 'docx' if fmt == 'doc' else fmt
        if allowed_formats and converter_fmt not in allowed_formats:
            continue
        files_by_format.setdefault(converter_fmt, []).append(
            (fpath, fmt)
        )

    # Prepare output directory
    os.makedirs(output_dir, exist_ok=True)
    outputs_dir = os.path.join(output_dir, 'outputs')
    os.makedirs(outputs_dir, exist_ok=True)

    results = {
        'timestamp': datetime.datetime.now().isoformat(),
        'system': {
            'platform': platform.platform(),
            'python': platform.python_version(),
        },
        'runs': runs,
        'files': {},
    }
    rankings = {}  # {format: [converter ordered by speed]}

    # Dispatch map for formats
    convert_methods = {
        'pdf': 'convert_pdf_to_text',
        'docx': 'convert_docx_to_text',
        'rtf': 'convert_rtf_to_text',
        'doc': 'convert_doc_to_text',
    }

    print("\n=== DocuMix Benchmark ===\n")

    for converter_fmt, file_list in sorted(files_by_format.items()):
        converters = available.get(converter_fmt, [])
        if not converters:
            print(f"[{converter_fmt.upper()}] No converters available, skipping")
            continue

        for fpath, actual_fmt in file_list:
            fname = os.path.basename(fpath)
            print(f"\n--- {fname} ({actual_fmt.upper()}) ---")
            print(f"{'Converter':<20} {'Mean (s)':<12} {'Min (s)':<12} "
                  f"{'Max (s)':<12} {'Length':<10} {'Accuracy':<10}")
            print("-" * 76)

            file_results = {}
            converter_outputs = {}

            for conv_name in converters:
                # For doc files, we always use convert_doc_to_text
                method_name = convert_methods[actual_fmt]
                compiler = DocumentCompiler(
                    source_path=fpath,
                    output_file='/dev/null',
                    converter_config={converter_fmt: [conv_name]}
                )
                method = getattr(compiler, method_name)

                timings = []
                output_text = None
                success = False

                for i in range(runs):
                    try:
                        start = time.perf_counter()
                        text, used_method = method(fpath)
                        elapsed = time.perf_counter() - start
                        if text and not text.startswith('[Failed'):
                            timings.append(elapsed)
                            if output_text is None:
                                output_text = text
                            success = True
                    except Exception as e:
                        print(f"  {conv_name}: error - {e}")
                        break

                if success and timings:
                    mean_t = sum(timings) / len(timings)
                    min_t = min(timings)
                    max_t = max(timings)
                    length = len(output_text)
                    file_results[conv_name] = {
                        'mean': round(mean_t, 4),
                        'min': round(min_t, 4),
                        'max': round(max_t, 4),
                        'output_length': length,
                        'success': True,
                    }
                    converter_outputs[conv_name] = output_text

                    # Save raw output
                    safe_fname = re.sub(r'[^\w.]', '_', fname)
                    out_path = os.path.join(
                        outputs_dir, f"{safe_fname}_{conv_name}.md"
                    )
                    with open(out_path, 'w', encoding='utf-8') as f:
                        f.write(output_text)
                else:
                    file_results[conv_name] = {
                        'mean': None, 'min': None, 'max': None,
                        'output_length': 0, 'success': False,
                    }

            # Compute accuracy: reference = longest output
            if converter_outputs:
                reference = max(
                    converter_outputs.values(), key=len
                )
                for conv_name, text in converter_outputs.items():
                    score = word_similarity(reference, text)
                    file_results[conv_name]['accuracy'] = round(score, 4)
            else:
                for conv_name in file_results:
                    file_results[conv_name]['accuracy'] = 0.0

            # Print table rows
            for conv_name in converters:
                r = file_results.get(conv_name)
                if r is None:
                    continue
                if r['success']:
                    print(f"{conv_name:<20} {r['mean']:<12.4f} "
                          f"{r['min']:<12.4f} {r['max']:<12.4f} "
                          f"{r['output_length']:<10} "
                          f"{r['accuracy']:<10.4f}")
                else:
                    print(f"{conv_name:<20} {'FAILED':<12} "
                          f"{'-':<12} {'-':<12} {'-':<10} {'-':<10}")

            results['files'][fpath] = file_results

            # Build ranking for this format (speed-based among successful)
            successful = [
                (name, r) for name, r in file_results.items()
                if r['success']
            ]
            if successful:
                # Rank by combined score: normalize speed and accuracy
                max_mean = max(r['mean'] for _, r in successful)
                for name, r in successful:
                    speed_norm = 1.0 - (r['mean'] / max_mean) if max_mean > 0 else 1.0
                    acc = r.get('accuracy', 0.0)
                    # Weight accuracy higher (0.6 accuracy, 0.4 speed)
                    r['combined_score'] = round(0.4 * speed_norm + 0.6 * acc, 4)

                ranked = sorted(
                    successful,
                    key=lambda x: x[1]['combined_score'],
                    reverse=True
                )
                fmt_ranking = [name for name, _ in ranked]
                # Merge into overall format ranking
                if converter_fmt not in rankings:
                    rankings[converter_fmt] = fmt_ranking
                else:
                    # Keep unique, preserving best order
                    existing = rankings[converter_fmt]
                    for name in fmt_ranking:
                        if name not in existing:
                            existing.append(name)

    # Save results
    results_path = os.path.join(output_dir, 'results.json')
    with open(results_path, 'w') as f:
        json.dump(results, f, indent=2)

    ranking_path = os.path.join(output_dir, 'converter_ranking.json')
    with open(ranking_path, 'w') as f:
        json.dump(rankings, f, indent=2)

    print(f"\nResults saved to {results_path}")
    print(f"Rankings saved to {ranking_path}")
    print(f"Raw outputs saved to {outputs_dir}/")

    return results, rankings


def benchmark_main(argv=None):
    """Entry point for the benchmark subcommand."""
    parser = argparse.ArgumentParser(
        prog='documix benchmark',
        description='Benchmark document converters for speed and accuracy. '
                    'All files in resources/ are benchmarked automatically.'
    )
    parser.add_argument(
        'files', nargs='*', default=[],
        help='Additional files to benchmark (resources/ files are always included)'
    )
    parser.add_argument(
        '--runs', type=int, default=3,
        help='Number of timing iterations per converter (default: 3)'
    )
    parser.add_argument(
        '--output-dir', default='benchmark/',
        help='Directory for benchmark results (default: benchmark/)'
    )
    parser.add_argument(
        '--formats', default='all',
        help='Formats to benchmark: pdf, docx, rtf, or all (default: all)'
    )

    args = parser.parse_args(argv)

    run_benchmark(
        files=args.files,
        runs=args.runs,
        output_dir=args.output_dir,
        formats=args.formats,
    )


def print_logo():
    """Displays the program logo."""
    logo = """
 ██████╗  ██████╗  ██████╗██╗   ██╗███╗   ███╗██╗██╗  ██╗
 ██╔══██╗██╔═══██╗██╔════╝██║   ██║████╗ ████║██║╚██╗██╔╝
 ██║  ██║██║   ██║██║     ██║   ██║██╔████╔██║██║ ╚███╔╝ 
 ██║  ██║██║   ██║██║     ██║   ██║██║╚██╔╝██║██║ ██╔██╗ 
 ██████╔╝╚██████╔╝╚██████╗╚██████╔╝██║ ╚═╝ ██║██║██╔╝ ██╗
 ╚═════╝  ╚═════╝  ╚═════╝ ╚═════╝ ╚═╝     ╚═╝╚═╝╚═╝  ╚═╝
                                                         
    """
    print(logo)

def main():
    # Check for subcommands before main argparse
    if len(sys.argv) > 1 and sys.argv[1] == 'benchmark':
        return benchmark_main(sys.argv[2:])

    # Display logo
    print_logo()

    parser = argparse.ArgumentParser(
        description='Compiles documents from a folder into a single Markdown file, similar to Repomix. '
                    'Supports various document formats including PDF (with ML-based analysis via PaddleOCR/MinerU '
                    'or rule-based detection via pdfplumber), DOCX, EPUB, and email files (.eml) with attachments.',
        epilog='Email Mode: When processing .eml files, DocuMix will automatically detect and process '
               'attachments from an "attachments" subfolder if present, or extract them from the email itself.\n\n'
               'Subcommands:\n'
               '  documix benchmark          Benchmark available converters for speed and accuracy.\n'
               '                             Run "documix benchmark --help" for options.'
    )
    parser.add_argument('folder', help='Path to the folder with documents or a single .eml file')
    parser.add_argument('-o', '--output', default='documix-output.md', help='Path to the output file (default: documix-output.md)')
    parser.add_argument('-r', '--recursive', action='store_true', help='Search folders recursively')
    parser.add_argument('-e', '--extensions', help='List of file extensions to process (comma-separated, default includes common document formats and .eml)')
    parser.add_argument('-x', '--exclude', help='File exclusion patterns (regular expressions, comma-separated)')
    parser.add_argument('-v', '--version', action='store_true', help='Display program version')
    parser.add_argument('--standard-format', action='store_true', help='Force standard format even for emails')
    parser.add_argument('--pdf-converters',
        help='PDF converters to try, in order (comma-separated). '
             'Choices: paddleocr,mineru,pdfplumber,markitdown-uvx,markitdown,pdftotext')
    parser.add_argument('--docx-converters',
        help='DOCX converters to try, in order (comma-separated). '
             'Choices: pandoc,docx2txt')
    parser.add_argument('--rtf-converters',
        help='RTF converters to try, in order (comma-separated). '
             'Choices: pandoc,unrtf,striprtf')

    args = parser.parse_args()
    
    # Display version and exit if --version argument is provided
    if args.version:
        print("DocuMix v0.1.0")
        return
    
    # Check if folder is provided
    if not args.folder:
        parser.print_help()
        return
    
    print(f"🔍 Analyzing folder: {args.folder}")
    
    include_extensions = None
    if args.extensions:
        include_extensions = [f".{ext.strip().lower()}" for ext in args.extensions.split(',')]
        print(f"📋 Included extensions: {', '.join(ext for ext in include_extensions)}")
    
    exclude_patterns = None
    if args.exclude:
        exclude_patterns = [pattern.strip() for pattern in args.exclude.split(',')]
        print(f"🚫 Exclusion patterns: {', '.join(exclude_patterns)}")
    
    # Determine force format
    force_format = None
    if args.standard_format:
        force_format = 'standard'
        print("📄 Forcing standard output format")

    # Parse converter config
    converter_config = {}
    for fmt, flag_name in [('pdf', 'pdf_converters'), ('docx', 'docx_converters'), ('rtf', 'rtf_converters')]:
        flag_value = getattr(args, flag_name)
        if flag_value:
            names = [n.strip() for n in flag_value.split(',')]
            valid = CONVERTER_DEFAULTS[fmt]
            for name in names:
                if name not in valid:
                    print(f"Error: unknown {fmt.upper()} converter '{name}'. "
                          f"Valid choices: {', '.join(valid)}")
                    sys.exit(1)
            converter_config[fmt] = names
            print(f"🔧 {fmt.upper()} converters: {', '.join(names)}")

    compiler = DocumentCompiler(
        args.folder,
        args.output,
        args.recursive,
        include_extensions,
        exclude_patterns,
        force_format,
        converter_config
    )
    
    compiler.compile()

if __name__ == "__main__":
    main()