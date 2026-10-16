"""EPUB via Calibre's ebook-convert."""
import os
import subprocess

from .. import tools

EBOOK_CONVERT_TIMEOUT = 600


def convert(filepath):
    """Converts EPUB to text using Calibre's ebook-convert tool."""
    try:
        with tools.temp_output('.txt') as temp_name:
            tools.run_tool(['ebook-convert', filepath, temp_name], timeout=EBOOK_CONVERT_TIMEOUT)
            text = tools.read_text(temp_name)
        print(f"Successfully converted EPUB using ebook-convert: {filepath}")
        return text, "ebook-convert"
    except (subprocess.SubprocessError, FileNotFoundError):
        print(f"WARNING: Failed to convert EPUB: {filepath}")
        print("Make sure you have Calibre installed")
        return f"[Failed to convert EPUB file: {os.path.basename(filepath)}]", "failed"
