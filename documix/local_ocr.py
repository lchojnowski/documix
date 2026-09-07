"""Opt-in local PDF OCR. No downloads, shell commands, or source writes."""

import math
import os
import re
import selectors
import shutil
import stat
import subprocess
import tempfile
import time
import unicodedata


OCR_PROFILE_VERSION = 'tesseract-pgm-v1'
OCR_DEFAULTS = {'languages': 'eng', 'max_pages': 20, 'dpi': 150, 'timeout': 180}
OCR_LIMITS = {'max_pages': 100, 'dpi': 200, 'timeout': 300}
MAX_SIDE = 4000
MAX_PIXELS = MAX_SIDE * MAX_SIDE
MAX_TEXT_BYTES = 4 * 1024 * 1024
MAX_INPUT_BYTES = 128 * 1024 * 1024
MAX_METADATA_BYTES = 64 * 1024
TOOL_TIMEOUT = 60
LANGUAGE = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,31}\Z', re.ASCII)


class OcrError(Exception):
    """Only fixed reason codes escape the converter; never tool diagnostics."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def has_content(text):
    return isinstance(text, str) and any(
        not char.isspace() and unicodedata.category(char) not in ('Cc', 'Cf')
        for char in text
    )


def validate_config(config=None):
    if config is None:
        config = {}
    if not isinstance(config, dict) or set(config) - set(OCR_DEFAULTS):
        raise ValueError('invalid_ocr_configuration')
    values = dict(OCR_DEFAULTS, **config)
    for name, maximum in OCR_LIMITS.items():
        value = values[name]
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValueError('invalid_ocr_configuration')
    languages = values['languages']
    if not isinstance(languages, str) or len(languages) > 255:
        raise ValueError('invalid_ocr_configuration')
    parts = languages.split('+')
    if not 1 <= len(parts) <= 8 or any(not LANGUAGE.fullmatch(p) for p in parts):
        raise ValueError('invalid_ocr_configuration')
    return values


def available():
    return os.name == 'posix' and all(
        shutil.which(name) for name in ('pdfinfo', 'pdftoppm', 'tesseract')
    )


def bounded_run(argv, deadline, max_bytes):
    """Capture bounded stdout from a native leaf tool inside the caller's group.

    The caller retains its sandbox/memory limits. Native stderr is discarded,
    and each child is killed and reaped on any interrupted or failed capture.
    """
    if os.name != 'posix':
        raise OcrError('platform_unavailable')
    end = min(deadline, time.monotonic() + TOOL_TIMEOUT)
    if end <= time.monotonic():
        raise OcrError('timeout')
    env = os.environ.copy()
    env.update({'LC_ALL': 'C', 'LANG': 'C', 'OMP_THREAD_LIMIT': '1'})
    process = None
    try:
        process = subprocess.Popen(
            argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, env=env, close_fds=True,
        )
        chunks = []
        size = 0
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                remaining = end - time.monotonic()
                if remaining <= 0:
                    raise OcrError('timeout')
                if not selector.select(min(remaining, 0.1)):
                    continue
                chunk = os.read(process.stdout.fileno(), 64 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise OcrError('output_limit')
                chunks.append(chunk)
        remaining = end - time.monotonic()
        if remaining <= 0:
            raise OcrError('timeout')
        if process.wait(timeout=remaining) != 0:
            raise OcrError('tool_failed')
        return b''.join(chunks)
    except subprocess.TimeoutExpired:
        raise OcrError('timeout') from None
    except OSError:
        raise OcrError('tool_unavailable') from None
    finally:
        if process is not None:
            try:
                if process.poll() is None:
                    process.kill()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        raise OcrError('cleanup_failed') from None
            finally:
                process.stdout.close()


def page_geometry(metadata, page_count):
    sizes = {}
    for line in metadata.decode('utf-8', errors='strict').splitlines():
        match = re.fullmatch(
            r'Page\s+([0-9]+) size:\s+([0-9.]+) x ([0-9.]+) pts(?:\s.*)?',
            line,
        )
        if not match:
            continue
        index = int(match[1])
        try:
            size = (float(match[2]), float(match[3]))
        except ValueError:
            raise OcrError('invalid_geometry') from None
        if index in sizes or not all(math.isfinite(n) and 0 < n <= 1000000 for n in size):
            raise OcrError('invalid_geometry')
        sizes[index] = size
    if set(sizes) != set(range(1, page_count + 1)):
        raise OcrError('invalid_geometry')
    return sizes


def validate_raster(data, side_limit):
    """Validate Poppler's bounded raw PGM; return whether every pixel is white."""
    header = re.match(
        rb'\AP5\s+([0-9]{1,5})\s+([0-9]{1,5})\s+255(?:\r\n|[\n\r ])',
        data[:256],
    )
    if not header:
        raise OcrError('invalid_raster')
    width, height = int(header[1]), int(header[2])
    if not (1 <= width <= side_limit and 1 <= height <= side_limit):
        raise OcrError('pixel_limit')
    if width * height > MAX_PIXELS or len(data) - header.end() != width * height:
        raise OcrError('invalid_raster')
    return data.count(b'\xff', header.end()) == width * height


def convert_pdf(filepath, config=None):
    values = validate_config(config)
    deadline = time.monotonic() + values['timeout']
    tools = {name: shutil.which(name) for name in ('pdfinfo', 'pdftoppm', 'tesseract')}
    if not all(tools.values()):
        raise OcrError('tool_unavailable')
    source = os.path.abspath(filepath)
    before = os.lstat(source)
    if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_INPUT_BYTES:
        raise OcrError('input_limit')

    languages = bounded_run([tools['tesseract'], '--list-langs'], deadline, MAX_METADATA_BYTES)
    installed = {line for line in languages.decode('utf-8').splitlines()
                 if LANGUAGE.fullmatch(line)}
    if not set(values['languages'].split('+')).issubset(installed):
        raise OcrError('language_unavailable')
    info = bounded_run([tools['pdfinfo'], source], deadline, MAX_METADATA_BYTES)
    counts = re.findall(rb'^Pages:\s*([0-9]+)\s*$', info, re.MULTILINE)
    if len(counts) != 1:
        raise OcrError('invalid_page_count')
    count = int(counts[0])
    if not 1 <= count <= values['max_pages']:
        raise OcrError('page_limit')
    geometry = bounded_run(
        [tools['pdfinfo'], '-f', '1', '-l', str(count), source],
        deadline, MAX_METADATA_BYTES,
    )
    sizes = page_geometry(geometry, count)
    pages = []
    total_bytes = 0
    with tempfile.TemporaryDirectory(prefix='documix_ocr_') as workspace:
        raster_path = os.path.join(workspace, 'page.pgm')
        for page in range(1, count + 1):
            side = min(MAX_SIDE, math.ceil(max(sizes[page]) * values['dpi'] / 72))
            raster = bounded_run(
                [tools['pdftoppm'], '-f', str(page), '-l', str(page),
                 '-singlefile', '-gray', '-r', str(values['dpi']),
                 '-scale-to', str(side), source],
                deadline, MAX_PIXELS + 256,
            )
            is_white = validate_raster(raster, side)
            if pages:
                total_bytes += len('\n\n---\n\n')
            if total_bytes > MAX_TEXT_BYTES:
                raise OcrError('output_limit')
            if is_white:
                # A fully white rendered page has no pixels to recognize.
                # Other empty OCR results are unresolved, never silently skipped.
                pages.append('')
                continue
            with open(raster_path, 'xb') as stream:
                stream.write(raster)
            del raster
            try:
                text_bytes = bounded_run(
                    [tools['tesseract'], raster_path, 'stdout', '-l',
                     values['languages'], '--dpi', str(values['dpi'])],
                    deadline, MAX_TEXT_BYTES - total_bytes,
                )
            finally:
                os.unlink(raster_path)
            text = text_bytes.decode('utf-8', errors='strict')
            if not has_content(text):
                raise OcrError('empty_page')
            total_bytes += len(text_bytes)
            if total_bytes > MAX_TEXT_BYTES:
                raise OcrError('output_limit')
            pages.append(text)

    after = os.lstat(source)
    signature = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    if signature(before) != signature(after):
        raise OcrError('source_changed')
    if time.monotonic() > deadline:
        raise OcrError('timeout')
    if not any(has_content(page) for page in pages):
        raise OcrError('empty_document')
    return '\n\n---\n\n'.join(pages)
