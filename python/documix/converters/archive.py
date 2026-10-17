"""ZIP archives: extract and process the members through the compiler."""
import os
import tempfile
import zipfile

from ..errors import EngineError


def extract_zip(filepath, include_extensions, temp_dirs, process_file, get_file_language, is_fenced):
    """Extracts a ZIP file and processes its contents.

    ``process_file``, ``get_file_language`` and ``is_fenced`` are the compiler
    callbacks, so nested archives and emails recurse through the usual
    dispatch and converted Markdown is written raw like at the top level.
    """
    try:
        temp_dir = tempfile.mkdtemp()
        temp_dirs.append(temp_dir)

        print(f"📦 Extracting ZIP: {os.path.basename(filepath)}")

        with zipfile.ZipFile(filepath, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)

        file_list = []
        parts = [f"# ZIP Archive Contents: {os.path.basename(filepath)}\n\n",
                 "## Files in archive:\n\n"]

        for root, dirs, files in os.walk(temp_dir):
            for file in files:
                file_path = os.path.join(root, file)
                file_list.append(os.path.relpath(file_path, temp_dir))

        file_list.sort()
        for file in file_list:
            parts.append(f"- {file}\n")

        parts.append("\n## Extracted file contents:\n\n")

        extraction_methods = []
        for file_path in file_list:
            full_path = os.path.join(temp_dir, file_path)
            _, ext = os.path.splitext(file_path.lower())

            if ext in include_extensions:
                parts.append(f"### File: {file_path}\n\n")
                try:
                    content, method = process_file(full_path)
                    extraction_methods.append(method)

                    if not is_fenced(full_path, method):
                        parts.append(f"{content}\n\n")
                    else:
                        file_language = get_file_language(file_path)
                        if file_language:
                            parts.append(f"```{file_language}\n{content}\n```\n\n")
                        else:
                            parts.append(f"```\n{content}\n```\n\n")
                except EngineError:
                    raise
                except Exception as e:
                    parts.append(f"[Error processing file: {str(e)}]\n\n")

        conversion_method = "zip_extract+" + "+".join(set(extraction_methods))
        print(f"Successfully processed ZIP using extraction methods: {conversion_method}: {filepath}")
        return "".join(parts), conversion_method

    except zipfile.BadZipFile:
        return f"[Error: {os.path.basename(filepath)} is not a valid ZIP file]", "failed-bad_zip"
    except EngineError:
        raise
    except Exception as e:
        return f"[Error processing ZIP file: {str(e)}]", "failed-exception"
