"""Legacy PDF converters: pdfplumber, MinerU, PaddleOCR, markitdown, pdftotext,
Tesseract (complete-document OCR)."""
import os
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

from .. import deps, local_ocr, textutils, tools

MINERU_TIMEOUT = 120
PADDLEOCR_TIMEOUT = 300
MARKITDOWN_TIMEOUT = 600
PDFTOTEXT_TIMEOUT = 120

# PaddleOCR's wrapper phones home unless told not to; also used for probes.
PADDLE_ENV = {'PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK': 'True'}


def _inside(obj, bbox):
    top = obj.get("top", 0)
    x0 = obj.get("x0", 0)
    return bbox[1] <= top <= bbox[3] and bbox[0] <= x0 <= bbox[2]


def convert_with_tables(filepath):
    """Converts PDF to markdown with table detection using pdfplumber.

    Uses line-based detection first (bordered tables). Falls back to
    text-based detection but validates quality (cell density >= 30%)
    to avoid gridifying entire pages. Pages without quality tables
    use layout-preserving text extraction.

    Returns (markdown_text, 'pdfplumber-tables') on success,
    or (None, None) if pdfplumber is unavailable or fails.
    """
    if not deps.PDFPLUMBER_AVAILABLE:
        return None, None
    pdfplumber = deps.pdfplumber
    if pdfplumber is None:
        return None, None

    try:
        pages_output = []
        found_any_table = False

        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                # (table, extracted rows) pairs; each table is extracted once.
                extracted = [(t, t.extract()) for t in page.find_tables()]

                if not extracted:
                    text_tables = page.find_tables(
                        table_settings={
                            "vertical_strategy": "text",
                            "horizontal_strategy": "text",
                        }
                    )
                    # Reject low-density text-strategy tables: those are
                    # usually the whole page gridified.
                    for t in text_tables:
                        data = t.extract()
                        if data and textutils.cell_density(data) >= 0.3:
                            extracted.append((t, data))

                if not extracted:
                    text = page.extract_text(layout=True)
                    if text:
                        pages_output.append(text)
                    continue

                found_any_table = True

                table_items = []
                table_bboxes = []
                for table, data in extracted:
                    if data:
                        md = textutils.table_to_markdown(data)
                        if md:
                            bbox = table.bbox  # (x0, top, x1, bottom)
                            table_items.append((bbox[1], md))
                            table_bboxes.append(bbox)

                # Drop characters inside table areas (one filter pass), then
                # extract the remaining text.
                filtered_page = page
                if table_bboxes:
                    filtered_page = page.filter(
                        lambda obj, boxes=tuple(table_bboxes): not any(
                            _inside(obj, b) for b in boxes
                        )
                    )

                remaining_text = (
                    filtered_page.extract_text(layout=True) or ""
                )

                page_parts = []
                if remaining_text.strip():
                    page_parts.append((0, remaining_text.strip()))
                page_parts.extend(table_items)
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


_PADDLE_SCRIPT = textwrap.dedent("""\
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


def convert_with_paddleocr(filepath, python_path):
    """Convert PDF using PaddleOCR PP-StructureV3 in its own venv Python.

    PaddleOCR is Apache 2.0 licensed. PaddlePaddle only supports Python
    <=3.12, so it runs as a subprocess, like mineru/pandoc/soffice.
    Returns (text, "paddleocr") on success, (None, None) on failure.
    """
    try:
        env = os.environ.copy()
        env.update(PADDLE_ENV)
        proc = subprocess.run(
            [python_path, '-c', _PADDLE_SCRIPT, filepath],
            capture_output=True, text=True, timeout=PADDLEOCR_TIMEOUT, env=env,
        )
        if proc.returncode != 0:
            print(f"PaddleOCR failed for {filepath}: {proc.stderr[:500]}")
            return None, None

        text = proc.stdout.strip()
        if not text:
            print(f"PaddleOCR produced no output for {filepath}")
            return None, None

        text = textutils.html_tables_to_markdown(text)
        print(f"Successfully converted PDF using PaddleOCR: {filepath}")
        return text, "paddleocr"
    except Exception as e:
        print(f"PaddleOCR failed for {filepath}: {e}")
        return None, None


def convert_with_mineru(filepath):
    """Convert PDF using the MinerU CLI (ML-based layout/table detection).

    MinerU is invoked as a subprocess to keep its AGPL licence separate
    from documix's MIT licence.
    Returns (text, "mineru") on success, (None, None) on failure.
    """
    tmpdir = None
    try:
        tmpdir = tempfile.mkdtemp(prefix="documix_mineru_")
        cmd = [
            'mineru', '-p', filepath, '-o', tmpdir,
            '-b', 'pipeline', '-d', 'cpu',
        ]
        tools.run_tool(cmd, timeout=MINERU_TIMEOUT)

        stem = Path(filepath).stem
        md_path = os.path.join(tmpdir, stem, 'auto', f'{stem}.md')
        if not os.path.exists(md_path):
            print(f"MinerU output not found at {md_path}")
            return None, None

        text = tools.read_text(md_path)
        text = textutils.html_tables_to_markdown(text)
        print(f"Successfully converted PDF using MinerU: {filepath}")
        return text, "mineru"
    except (subprocess.SubprocessError, FileNotFoundError, OSError) as e:
        print(f"MinerU failed for {filepath}: {e}")
        return None, None
    finally:
        if tmpdir and os.path.exists(tmpdir):
            shutil.rmtree(tmpdir, ignore_errors=True)


def try_markitdown_uvx(filepath):
    """Try converting PDF using uvx markitdown."""
    try:
        with tools.temp_output('.md') as temp_name:
            tools.run_tool(['uvx', 'markitdown[pdf]', filepath, '-o', temp_name],
                           timeout=MARKITDOWN_TIMEOUT)
            text = tools.read_text(temp_name)
        print(f"Successfully converted PDF using uvx markitdown: {filepath}")
        return text, "markitdown-uvx"
    except (subprocess.SubprocessError, FileNotFoundError):
        print(f"uvx markitdown failed for: {filepath}")
        return None, None


def try_markitdown(filepath):
    """Try converting PDF using markitdown directly."""
    try:
        with tools.temp_output('.md') as temp_name:
            tools.run_tool(['markitdown', filepath, '-o', temp_name],
                           timeout=MARKITDOWN_TIMEOUT)
            text = tools.read_text(temp_name)
        print(f"Successfully converted PDF using markitdown: {filepath}")
        return text, "markitdown"
    except (subprocess.SubprocessError, FileNotFoundError):
        print(f"markitdown not available or failed for: {filepath}")
        return None, None


def try_pdftotext(filepath):
    """Try converting PDF using pdftotext."""
    try:
        with tools.temp_output('.txt') as temp_name:
            tools.run_tool(['pdftotext', '-layout', filepath, temp_name],
                           timeout=PDFTOTEXT_TIMEOUT)
            text = tools.read_text(temp_name)
        print(f"Successfully converted PDF using pdftotext: {filepath}")
        return text, "pdftotext"
    except (subprocess.SubprocessError, FileNotFoundError):
        print(f"pdftotext not available or failed for: {filepath}")
        return None, None


def convert_with_tesseract(filepath, ocr_config):
    """Explicit local-only OCR; any incomplete page fails the converter."""
    try:
        return local_ocr.convert_pdf(filepath, ocr_config), 'tesseract'
    except local_ocr.OcrError as error:
        print(f"Tesseract OCR unavailable: {error.code}")
    except (OSError, UnicodeError, ValueError):
        print("Tesseract OCR unavailable: invalid_input")
    return None, None


def convert_with_complete_ocr(filepath, converters, dispatch, ocr_convert):
    """Mandatory full-document OCR combined with the first native result.

    A nonempty native result may contain only a cover or page header.
    Mandatory OCR runs once, irrespective of its list position, and its
    failure must never fall back to possibly incomplete native text.
    """
    before = os.lstat(filepath)
    ocr_text, _ = ocr_convert(filepath)
    if not local_ocr.has_content(ocr_text):
        return None, None
    result, result_method = ocr_text, 'tesseract'
    for name in converters:
        if name == 'tesseract':
            continue
        text, method = dispatch[name](filepath)
        if local_ocr.has_content(text):
            separator = '\n\n---\n\n## Complete-document OCR rendition\n\n'
            if (len(text.encode('utf-8')) + len(separator.encode('utf-8'))
                    + len(ocr_text.encode('utf-8')) > local_ocr.MAX_TEXT_BYTES):
                raise local_ocr.OcrError('output_limit')
            result, result_method = text + separator + ocr_text, method + '+tesseract'
            break
    after = os.lstat(filepath)

    def signature(info):
        return (info.st_dev, info.st_ino, info.st_size,
                info.st_mtime_ns, info.st_ctime_ns)

    if signature(before) != signature(after):
        raise local_ocr.OcrError('source_changed')
    return result, result_method
