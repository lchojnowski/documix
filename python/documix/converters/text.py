"""Plain text and code files."""
import os


def convert(filepath):
    """Reads text from TXT/MD/other text files."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            text = f.read()
        print(f"Successfully read text file using direct read: {filepath}")
        return text, "direct_read"
    except Exception as e:
        print(f"WARNING: Failed to read file: {filepath}")
        print(f"Error: {e}")
        return f"[Failed to read file: {os.path.basename(filepath)}]", "failed"
