"""RTF converters: pandoc, unrtf, striprtf."""
import subprocess

from .. import tools

PANDOC_TIMEOUT = 120
UNRTF_TIMEOUT = 60


def try_pandoc(filepath):
    """Try converting RTF using pandoc."""
    try:
        with tools.temp_output('.md') as temp_name:
            tools.run_tool(
                ['pandoc', '-f', 'rtf', '-t', 'markdown', filepath, '-o', temp_name],
                timeout=PANDOC_TIMEOUT,
            )
            text = tools.read_text(temp_name)
        print(f"Successfully converted RTF using pandoc: {filepath}")
        return text, "pandoc"
    except (subprocess.SubprocessError, FileNotFoundError):
        print(f"pandoc not available or failed for RTF: {filepath}")
        return None, None


def try_unrtf(filepath):
    """Try converting RTF using unrtf."""
    try:
        result = tools.run_tool(['unrtf', '--text', filepath], timeout=UNRTF_TIMEOUT)
        print(f"Successfully converted RTF using unrtf: {filepath}")
        return result.stdout, "unrtf"
    except (subprocess.SubprocessError, FileNotFoundError):
        print(f"unrtf not available or failed for RTF: {filepath}")
        return None, None


def try_striprtf(filepath):
    """Try converting RTF using striprtf Python library."""
    try:
        from striprtf.striprtf import rtf_to_text
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            rtf_content = f.read()
        text = rtf_to_text(rtf_content)
        print(f"Successfully converted RTF using striprtf: {filepath}")
        return text, "striprtf"
    except ImportError:
        print(f"striprtf not installed: {filepath}")
        return None, None
    except Exception as e:
        print(f"striprtf failed: {str(e)}")
        return None, None
