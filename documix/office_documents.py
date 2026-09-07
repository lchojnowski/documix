"""Bounded local XLSX/PPTX conversion through an installed optional parser."""
import os
import shutil
import stat
import time
import zipfile
import zlib
from xml.parsers import expat

if __package__:
    from . import local_ocr
else:
    import local_ocr


MAX_INPUT_BYTES = 128 * 1024 * 1024
MAX_MEMBER_BYTES = 32 * 1024 * 1024
MAX_EXPANDED_BYTES = 256 * 1024 * 1024
MAX_MEMBERS = 10000
MAX_COMPRESSION_RATIO = 1000
MAX_TEXT_BYTES = 4 * 1024 * 1024
TIMEOUT = 60


class OfficeError(Exception):
    """Fixed reason codes only; parser diagnostics never become document text."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _signature(info):
    return (info.st_dev, info.st_ino, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _check_deadline(deadline):
    if time.monotonic() > deadline:
        raise OfficeError('timeout')


def _check_relationships(archive, member, deadline):
    parser = expat.ParserCreate(namespace_separator='}')

    def reject_declaration(*arguments):
        raise OfficeError('invalid_archive')

    def check_element(name, attributes):
        _check_deadline(deadline)
        if name.rsplit('}', 1)[-1] == 'Relationship':
            relationship_type = attributes.get('Type', '')
            if relationship_type.rstrip('/').rsplit('/', 1)[-1] == 'image':
                raise OfficeError('unassessed_media')

    parser.StartDoctypeDeclHandler = reject_declaration
    parser.EntityDeclHandler = reject_declaration
    parser.ExternalEntityRefHandler = reject_declaration
    parser.StartElementHandler = check_element
    with archive.open(member) as stream:
        while True:
            _check_deadline(deadline)
            chunk = stream.read(64 * 1024)
            parser.Parse(chunk, not chunk)
            if not chunk:
                break


def _validate_archive(path, extension, deadline, require_text_only=False):
    """Read and check bounded members in place; never extract archive paths."""
    required = {'[Content_Types].xml',
                'xl/workbook.xml' if extension == '.xlsx'
                else 'ppt/presentation.xml'}
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if not 1 <= len(members) <= MAX_MEMBERS:
            raise OfficeError('archive_limit')
        names = set()
        expanded = 0
        for member in members:
            _check_deadline(deadline)
            name = member.filename
            if (not name or len(name) > 512 or name in names or
                    name.startswith('/') or '\\' in name or '\x00' in name or
                    '..' in name.split('/') or
                    stat.S_ISLNK(member.external_attr >> 16)):
                raise OfficeError('invalid_archive')
            names.add(name)
            if require_text_only and name.lower().startswith(('xl/media/', 'ppt/media/')):
                raise OfficeError('unassessed_media')
            if (member.flag_bits & 1 or member.compress_type not in
                    (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
                raise OfficeError('unsupported_archive')
            expanded += member.file_size
            if (member.file_size > MAX_MEMBER_BYTES or
                    expanded > MAX_EXPANDED_BYTES or
                    member.file_size > max(1, member.compress_size) *
                    MAX_COMPRESSION_RATIO):
                raise OfficeError('archive_limit')
            observed = 0
            with archive.open(member) as stream:
                while True:
                    _check_deadline(deadline)
                    chunk = stream.read(64 * 1024)
                    if not chunk:
                        break
                    observed += len(chunk)
                    if observed > member.file_size or observed > MAX_MEMBER_BYTES:
                        raise OfficeError('archive_limit')
            if observed != member.file_size:
                raise OfficeError('invalid_archive')
            if require_text_only and name.endswith('.rels'):
                _check_relationships(archive, member, deadline)
        if not required.issubset(names):
            raise OfficeError('invalid_archive')


def convert(filepath, require_text_only=False):
    """Return actual text or fail explicitly; never download or read ZIP as text."""
    if type(require_text_only) is not bool:
        raise ValueError('invalid_office_configuration')
    deadline = time.monotonic() + TIMEOUT
    source = os.path.abspath(filepath)
    extension = os.path.splitext(source)[1].lower()
    if extension not in ('.xlsx', '.pptx'):
        raise OfficeError('unsupported_format')
    if os.name != 'posix':
        raise OfficeError('platform_unavailable')
    tool = shutil.which('markitdown')
    if not tool:
        raise OfficeError('tool_unavailable')
    # Support a known venv/pipx installation, without interpreting shell wrappers
    # or requiring its Python >=3.10 dependencies in Documix's Python 3.8 core.
    interpreter = os.path.join(os.path.dirname(os.path.realpath(tool)), 'python')
    if not os.path.isfile(interpreter) or not os.access(interpreter, os.X_OK):
        raise OfficeError('tool_unavailable')
    parser = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'office_parser.py')
    try:
        flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, 'O_NOFOLLOW', 0)
        with os.fdopen(os.open(source, flags), 'rb') as original:
            before = os.fstat(original.fileno())
            if (not stat.S_ISREG(before.st_mode) or
                    not 0 < before.st_size <= MAX_INPUT_BYTES or
                    _signature(before) != _signature(os.lstat(source))):
                raise OfficeError('input_limit')
            with local_ocr.private_workspace() as workspace:
                copied = os.path.join(workspace, 'document' + extension)
                size = 0
                with open(copied, 'xb') as output:
                    while True:
                        _check_deadline(deadline)
                        chunk = original.read(64 * 1024)
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > MAX_INPUT_BYTES or size > before.st_size:
                            raise OfficeError('input_limit')
                        output.write(chunk)
                if size != before.st_size:
                    raise OfficeError('source_changed')
                os.chmod(copied, 0o400)
                _validate_archive(copied, extension, deadline, require_text_only)
                raw = local_ocr.bounded_run(
                    [interpreter, '-I', '-B', parser, extension, copied],
                    deadline, MAX_TEXT_BYTES,
                )
                # Also validate the contract if a future subprocess adapter changes.
                if len(raw) > MAX_TEXT_BYTES:
                    raise OfficeError('output_limit')
                text = raw.decode('utf-8', errors='strict')
                if not local_ocr.has_content(text):
                    raise OfficeError('empty_document')
        if _signature(before) != _signature(os.lstat(source)):
            raise OfficeError('source_changed')
        _check_deadline(deadline)
        return text
    except local_ocr.OcrError as error:
        raise OfficeError(error.code) from None
    except (OSError, ValueError, EOFError, zlib.error, expat.ExpatError, zipfile.BadZipFile,
            zipfile.LargeZipFile, RuntimeError):
        raise OfficeError('invalid_document') from None
