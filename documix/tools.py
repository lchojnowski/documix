"""External tool helpers: bounded execution, availability probes, temp files."""
import contextlib
import os
import shutil
import subprocess
import tempfile
import threading

from . import deps
from .config import CONVERTER_CHOICES, CONVERTER_DEFAULTS
from .converters import anydoc as anydoc_engine
from .converters import liteparse as liteparse_engine

PROBE_TIMEOUT = 15


def physical_memory_gb():
    """Installed RAM in GiB, or None when the platform does not say."""
    try:
        return os.sysconf('SC_PHYS_PAGES') * os.sysconf('SC_PAGE_SIZE') / 2 ** 30
    except (AttributeError, ValueError, OSError):
        return None

_probe_cache = {}
_probe_lock = threading.Lock()


def run_tool(argv, timeout, check=True, env=None):
    """Run an external tool with captured output and a hard timeout.

    Raises ``subprocess.SubprocessError`` (including ``TimeoutExpired`` and
    ``CalledProcessError``) or ``OSError`` exactly like ``subprocess.run``.
    """
    kwargs = {
        'check': check,
        'stdout': subprocess.PIPE,
        'stderr': subprocess.PIPE,
        'text': True,
        'timeout': timeout,
    }
    if env is not None:
        kwargs['env'] = env
    return subprocess.run(argv, **kwargs)


def probe(argv, timeout=PROBE_TIMEOUT, env=None):
    """Return True when ``argv`` exits successfully. Cached per process.

    Used for expensive ``<tool> --version`` checks so that several compiler
    instances (e.g. in the benchmark) do not repeat them.
    """
    key = tuple(argv)
    with _probe_lock:
        if key in _probe_cache:
            return _probe_cache[key]
    try:
        subprocess.run(
            list(argv), check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout, env=env,
        )
        available = True
    except (subprocess.SubprocessError, OSError):
        available = False
    with _probe_lock:
        _probe_cache[key] = available
    return available


def clear_cache():
    """Forget cached probe results (tests call this between cases)."""
    with _probe_lock:
        _probe_cache.clear()


@contextlib.contextmanager
def temp_output(suffix):
    """Yield a temporary file path for a tool to write; always removed."""
    fd, path = tempfile.mkstemp(suffix=suffix, prefix='documix_')
    os.close(fd)
    try:
        yield path
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def read_text(path):
    with open(path, 'r', encoding='utf-8', errors='replace') as handle:
        return handle.read()


def check_converter_availability(converter_config=None, all_converters=False):
    """Check which converters are available on this system.

    Returns ``{format: [available_converter_names]}`` for every format in
    ``CONVERTER_DEFAULTS``. Explicit format profiles limit probes to their
    selected converters; omitted formats retain their defaults. With
    ``all_converters=True`` every known converter is probed (benchmark).
    Deliberately uncached: callers expect a fresh look at the system.
    """
    converter_config = converter_config or {}

    def selected(fmt, name):
        if all_converters:
            return True
        return name in converter_config.get(fmt, CONVERTER_DEFAULTS[fmt])

    probes = {}

    def have(name, check):
        if name not in probes:
            probes[name] = bool(check())
        return probes[name]

    def uvx():
        try:
            subprocess.run(
                ['uvx', '--version'], check=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            return True
        except (subprocess.SubprocessError, OSError):
            return False

    def striprtf():
        try:
            from striprtf.striprtf import rtf_to_text  # noqa: F401
            return True
        except ImportError:
            return False

    checks = {
        'anydoc': anydoc_engine.is_available,
        'liteparse': liteparse_engine.is_available,
        'paddleocr': lambda: shutil.which('paddleocr'),
        'mineru': lambda: shutil.which('mineru'),
        'pdfplumber': lambda: deps.PDFPLUMBER_AVAILABLE,
        'markitdown-uvx': uvx,
        'markitdown': lambda: shutil.which('markitdown'),
        'pdftotext': lambda: shutil.which('pdftotext'),
        'pandoc': lambda: shutil.which('pandoc'),
        'docx2txt': lambda: deps.DOCX2TXT_AVAILABLE,
        'unrtf': lambda: shutil.which('unrtf'),
        'striprtf': striprtf,
        'soffice': lambda: shutil.which('soffice'),
        'ebook-convert': lambda: shutil.which('ebook-convert'),
        # tesseract is reported by the CLI only when explicitly configured.
        'tesseract': lambda: False,
    }

    available = {}
    for fmt, choices in CONVERTER_CHOICES.items():
        available[fmt] = [
            name for name in choices
            if name != 'tesseract' and selected(fmt, name) and have(name, checks[name])
        ]
    return available
