"""Secondary conversion engine: LiteParse (LlamaIndex, Apache-2.0).

LiteParse parses PDFs locally with bundled Tesseract OCR, so it is the
fallback for scanned PDFs that anydoc rejects. Office inputs are converted to
PDF through LibreOffice first, which must not run concurrently, hence the
office lock. A worker pool sized like the compiler's job count gives every parse a
hard timeout and lets OCR of several scans run in parallel.
"""
import atexit
import contextlib
import importlib.util
import os
import threading

from .. import local_ocr

PARSE_TIMEOUT = 300  # seconds per document
MAX_POOL = 16  # worker processes (~250 MB RSS each); sized from the job count

_parser = None
_lock = threading.Lock()
_OFFICE_LOCK = threading.Lock()


def is_available():
    return importlib.util.find_spec('liteparse') is not None


def _get_parser(jobs):
    global _parser
    with _lock:
        if _parser is None:
            from liteparse import LiteParse
            pool = max(1, min(int(jobs or 1), MAX_POOL))
            _parser = LiteParse(
                output_format='markdown',
                image_mode='off',
                quiet=True,
                pool_size=pool,
                parse_timeout=PARSE_TIMEOUT,
            )
        return _parser


def shutdown():
    """Close the shared parser (and its worker pool), if any."""
    global _parser
    with _lock:
        parser, _parser = _parser, None
    if parser is not None:
        try:
            parser.close()
        except Exception:
            pass


atexit.register(shutdown)


def convert(filepath, jobs=1):
    """Return ``(markdown, 'liteparse')`` or ``(None, None)``. Never fatal."""
    if not is_available():
        print(f"LiteParse not installed; skipping {filepath}")
        return None, None
    ext = os.path.splitext(filepath.lower())[1]
    label = ext[1:].upper() if ext else 'document'
    try:
        parser = _get_parser(jobs)
        guard = contextlib.nullcontext() if ext == '.pdf' else _OFFICE_LOCK
        with guard:
            result = parser.parse(filepath)
        text = result.text
    except Exception as error:
        print(f"LiteParse failed for {filepath}: {type(error).__name__}: {error}")
        return None, None
    if not local_ocr.has_content(text):
        print(f"LiteParse produced no text for {filepath}")
        return None, None
    print(f"Successfully converted {label} using LiteParse: {filepath}")
    return text, 'liteparse'
