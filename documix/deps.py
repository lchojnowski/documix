"""Optional third-party dependencies, resolved lazily.

``PDFPLUMBER_AVAILABLE`` / ``DOCX2TXT_AVAILABLE`` are cheap presence checks
(no import). The module objects ``pdfplumber`` / ``docx2txt`` are imported on
first attribute access (PEP 562), so a run that never touches a PDF never pays
for importing pdfplumber. Tests patch ``documix.deps.<name>`` directly.
"""
import importlib
import importlib.util

PDFPLUMBER_AVAILABLE = importlib.util.find_spec('pdfplumber') is not None
DOCX2TXT_AVAILABLE = importlib.util.find_spec('docx2txt') is not None

_LAZY_MODULES = ('pdfplumber', 'docx2txt')


def __getattr__(name):
    if name in _LAZY_MODULES:
        try:
            module = importlib.import_module(name)
        except ImportError:
            module = None
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
