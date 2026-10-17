"""DOCX converters (pandoc, docx2txt) and legacy DOC via LibreOffice."""
import os
import shutil
import signal
import subprocess
import tempfile
import threading

from .. import deps, tools

PANDOC_TIMEOUT = 120
SOFFICE_TIMEOUT = 300

# LibreOffice shares one user profile; concurrent launches fail.
_SOFFICE_LOCK = threading.Lock()


def soffice_timeout():
    """Hard cap for one LibreOffice conversion, in seconds."""
    try:
        return int(os.environ.get('DOCUMIX_SOFFICE_TIMEOUT', SOFFICE_TIMEOUT))
    except ValueError:
        return SOFFICE_TIMEOUT


def run_soffice(temp_dir, temp_doc):
    """Convert ``temp_doc`` to DOCX with LibreOffice; returns its stdout.

    soffice can hang forever on malformed .doc files, so it runs headless in
    its own process group with a hard timeout; on expiry the whole tree is
    killed (the soffice.bin grandchild would otherwise survive as an orphan)
    and the document is reported as failed instead of stalling the run.
    """
    timeout = soffice_timeout()
    proc = subprocess.Popen(
        ['soffice', '--headless', '--convert-to', 'docx', '--outdir', temp_dir, temp_doc],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        proc.communicate()
        raise subprocess.SubprocessError(
            f"soffice conversion timed out after {timeout}s "
            f"(likely a malformed .doc): {temp_doc}"
        )
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, 'soffice', output=stdout, stderr=stderr)
    return stdout


def try_pandoc(filepath):
    """Try converting DOCX using pandoc."""
    try:
        with tools.temp_output('.md') as temp_name:
            try:
                tools.run_tool(
                    ['pandoc', '-f', 'docx', '-t', 'markdown', filepath, '-o', temp_name],
                    timeout=PANDOC_TIMEOUT,
                )
            except subprocess.CalledProcessError as e:
                print(f"WARNING: Pandoc error: {e.stderr}")
                raise
            text = tools.read_text(temp_name)
        print(f"Successfully converted DOCX using pandoc: {filepath}")
        return text, "pandoc"
    except (subprocess.SubprocessError, FileNotFoundError):
        print(f"pandoc not available or failed for DOCX: {filepath}")
        return None, None


def try_docx2txt(filepath):
    """Try converting DOCX using docx2txt."""
    if not deps.DOCX2TXT_AVAILABLE:
        return None, None
    docx2txt = deps.docx2txt
    if docx2txt is None:
        return None, None
    try:
        print(f"Attempting DOCX conversion with docx2txt for {filepath}")
        text = docx2txt.process(filepath)
        if text and len(text.strip()) > 0:
            print(f"Successfully converted DOCX with docx2txt: {filepath}")
            return text, "docx2txt"
        print(f"docx2txt produced empty output for {filepath}")
        return None, None
    except Exception as e:
        print(f"docx2txt failed: {str(e)}")
        return None, None


def convert_doc(filepath, temp_dirs, convert_docx):
    """Converts DOC to DOCX using LibreOffice, then runs ``convert_docx``."""
    try:
        temp_dir = tempfile.mkdtemp()
        temp_dirs.append(temp_dir)

        filename = os.path.basename(filepath)
        output_docx = os.path.join(temp_dir, f"{os.path.splitext(filename)[0]}.docx")

        temp_doc = os.path.join(temp_dir, filename)
        shutil.copy2(filepath, temp_doc)

        if not os.path.exists(temp_doc):
            raise FileNotFoundError(f"Failed to copy {filepath} to {temp_doc}")

        file_size = os.path.getsize(temp_doc)
        if file_size == 0:
            raise ValueError(f"File {filepath} is empty (0 bytes)")

        print(f"Converting DOC file: {temp_doc} (size: {file_size} bytes)")

        try:
            with _SOFFICE_LOCK:
                stdout = run_soffice(temp_dir, temp_doc)
            print(f"LibreOffice conversion successful: {stdout}")
        except subprocess.CalledProcessError as e:
            print(f"WARNING: LibreOffice conversion error: {e.stderr}")
            raise

        if not os.path.exists(output_docx):
            raise FileNotFoundError(f"LibreOffice did not create expected output file: {output_docx}")

        text, docx_method = convert_docx(output_docx)

        conversion_method = f"soffice+{docx_method}"
        print(f"Successfully converted DOC using {conversion_method}: {filepath}")
        return text, conversion_method

    except (subprocess.SubprocessError, FileNotFoundError, ValueError) as e:
        print(f"WARNING: Failed to convert DOC: {filepath}")
        print(f"Error details: {str(e)}")
        print("Make sure you have LibreOffice installed")
        return f"[Failed to convert DOC file: {os.path.basename(filepath)}]", "failed"
