"""Primary conversion engine: anydoc (``firecrawl-anydoc``, MIT, Rust).

anydoc converts Word, PowerPoint, Excel, OpenDocument, RTF, EPUB, CSV and
text-based PDF locally, in milliseconds, and releases the GIL while doing so.
It never does OCR and never talks to the network from here (the hosted OCR
option is deliberately not exposed).

Failure policy (see ``documix.errors.EngineError``):

* engine failures (package missing, import error, crash) raise ``EngineError``
  and abort the whole run;
* document-level failures (``anydoc.ConvertError`` subclasses such as
  ``NeedsOcrError`` for scans, ``EncryptedError``, ``MalformedError``, or an
  unreadable file) return ``(None, None)`` so the chain moves on to LiteParse.
"""
import os
import re
import zipfile

from .. import local_ocr
from ..errors import EngineError

INSTALL_HINT = 'pip install firecrawl-anydoc'

# Office containers whose embedded media matters for --office-require-text-only.
OFFICE_EXTENSIONS = {
    '.xlsx', '.xlsm', '.xls', '.xlsb', '.pptx', '.pptm', '.ppsx', '.ppsm', '.ppt',
    '.odt', '.ods', '.odp',
}

# OOXML relationship to an embedded or linked picture (what the sandboxed
# MarkItDown path rejects as well); OpenDocument keeps pictures under Pictures/.
_IMAGE_RELATIONSHIP = re.compile(rb'Type="[^"]*/image"')


def has_embedded_media(filepath):
    """True when an Office container references pictures.

    anydoc's document model does not list images for every Office format
    (Excel drawings, for example), so inspect the package itself: any
    ``.rels`` image relationship or an OpenDocument ``Pictures/`` member
    counts. Non-ZIP inputs (binary ``.xls``/``.ppt``) return False and rely
    on the document model.
    """
    try:
        with zipfile.ZipFile(filepath) as archive:
            for name in archive.namelist():
                if name.startswith('Pictures/') or '/media/' in name:
                    return True
                if name.endswith('.rels') and _IMAGE_RELATIONSHIP.search(archive.read(name)):
                    return True
    except (zipfile.BadZipFile, OSError):
        return False
    return False


_UNLOADED = object()
# The imported module, ``None`` when unavailable. Tests patch this attribute.
anydoc = _UNLOADED


def _module():
    """Import anydoc on first use (36 ms) and cache the result."""
    global anydoc
    if anydoc is _UNLOADED:
        try:
            import anydoc as loaded
        except ImportError:
            loaded = None
        anydoc = loaded
    return anydoc


def is_available():
    return _module() is not None


def require():
    """Return the anydoc module or raise ``EngineError`` when it is missing."""
    module = _module()
    if module is None:
        raise EngineError(
            f'anydoc is not installed or failed to import ({INSTALL_HINT})')
    return module


def _label(filepath):
    ext = os.path.splitext(filepath.lower())[1]
    return ext[1:].upper() if ext else 'document'


def convert(filepath, require_text_only=False):
    """Convert ``filepath`` to Markdown with anydoc.

    Returns ``(markdown, 'anydoc')``, a ``('[Failed ...]', 'failed')`` pair
    when ``require_text_only`` rejects an Office file with embedded media,
    or ``(None, None)`` when anydoc declines the document.
    """
    engine = require()
    ext = os.path.splitext(filepath.lower())[1]
    label = _label(filepath)
    try:
        if require_text_only and ext in OFFICE_EXTENSIONS:
            with open(filepath, 'rb') as handle:
                data = handle.read()
            document = engine.to_document(data, engine.format_from_path(filepath))
            if document.assets or has_embedded_media(filepath):
                print(f"anydoc: {filepath} contains embedded media; "
                      f"rejected by --office-require-text-only")
                return f'[Failed to convert {label} file: unassessed_media]', 'failed'
            text = engine.to_markdown_bytes(data, engine.format_from_path(filepath))
        else:
            text = engine.to_markdown(filepath)
    except engine.ConvertError as error:
        print(f"anydoc declined {filepath}: {type(error).__name__}: {error}")
        return None, None
    except OSError as error:
        print(f"anydoc could not read {filepath}: {error}")
        return None, None
    except Exception as error:
        raise EngineError(
            f'anydoc crashed on {filepath}: {type(error).__name__}: {error}') from error
    except BaseException as error:
        # pyo3 panics derive from BaseException; they are engine failures too.
        if type(error).__name__ == 'PanicException':
            raise EngineError(f'anydoc panicked on {filepath}: {error}') from error
        raise

    if not local_ocr.has_content(text):
        print(f"anydoc produced no text for {filepath}")
        return None, None
    print(f"Successfully converted {label} using anydoc: {filepath}")
    return text, 'anydoc'
