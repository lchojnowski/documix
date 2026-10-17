"""Pure text helpers shared by the compiler, email processor and benchmark."""
import difflib
import os
import re

import html2text

from .config import LANGUAGE_MAP

_SENTENCE_END = re.compile(r'[.!?]$')

# Matches PaddleOCR's wrapper or bare <table> blocks.
_HTML_TABLE = re.compile(
    r'(?:<div[^>]*>\s*<html>\s*<body>\s*)?'
    r'<table.*?</table>'
    r'(?:\s*</body>\s*</html>\s*</div>)?',
    re.DOTALL,
)


def estimate_tokens(text):
    """Rough token count: whitespace-separated words, +1 for a closing stop."""
    stripped = text.strip()
    if not stripped:
        return 0
    word_count = len(stripped.split())
    if _SENTENCE_END.search(stripped):
        return word_count + 1
    return word_count


def format_size(size_bytes):
    """Format file size in human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def get_file_language(file_path):
    """Determines programming language based on file extension."""
    ext = os.path.splitext(file_path.lower())[1]
    return LANGUAGE_MAP.get(ext, '')


def table_to_markdown(table_data):
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
    lines.append("| " + " | ".join(rows[0]) + " |")
    lines.append("| " + " | ".join("---" for _ in range(max_cols)) + " |")
    for row in rows[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def cell_density(table_data):
    """Compute fraction of non-empty cells in a 2D table."""
    total = sum(len(row) for row in table_data)
    if total == 0:
        return 0.0
    nonempty = sum(
        1 for row in table_data
        for cell in row if cell and str(cell).strip()
    )
    return nonempty / total


def html_tables_to_markdown(text):
    """Convert HTML <table> blocks in *text* to markdown pipe tables.

    Handles both bare ``<table>…</table>`` and PaddleOCR's wrapper
    ``<div …><html><body><table>…</table></body></html></div>``.
    """
    if '<table' not in text:
        return text

    def _convert(match):
        # html2text instances are single-use; build one per table.
        h = html2text.HTML2Text()
        h.body_width = 0
        h.protect_links = True
        return h.handle(match.group(0)).strip()

    return _HTML_TABLE.sub(_convert, text)


def word_similarity(text_a, text_b):
    """Compute word-level similarity between two texts (0.0-1.0)."""
    if not text_a and not text_b:
        return 1.0
    if not text_a or not text_b:
        return 0.0
    words_a = text_a.split()
    words_b = text_b.split()
    return difflib.SequenceMatcher(None, words_a, words_b).ratio()
