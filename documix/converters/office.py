"""XLSX/PPTX through the sandboxed MarkItDown parser (office_documents)."""
from .. import office_documents


def convert(filepath, ext, require_text_only=False):
    """Convert an Office document; returns a placeholder on OfficeError."""
    try:
        text = office_documents.convert(
            filepath,
            **({'require_text_only': True} if require_text_only else {}),
        )
        return text, 'markitdown'
    except office_documents.OfficeError as error:
        return ('[Failed to convert {} file: {}]'.format(
            ext[1:].upper(), error.code), 'failed')
