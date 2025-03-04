# DocuMix

Tool to compile documents from a folder into a single Markdown file, similar to Repomix.

## Features

- Compiles various document types (PDF, EPUB, DOCX, DOC, TXT, MD, etc.) into a single Markdown file
- Supports ZIP files by automatically extracting and processing their contents
- Generates a structured file with detailed document contents
- Estimates token counts and provides statistics
- Security checks for potentially suspicious files
- Colorful console output with emojis for better readability

## Installation

You can install documix directly from GitHub:

```bash
pip install git+https://github.com/lchojnowski/documix.git
```

## Usage

```bash
documix /path/to/folder -r -o output.md
```

### Options

- `-o`, `--output` - Path to the output file (default: documix-output.md)
- `-r`, `--recursive` - Search folders recursively
- `-e`, `--extensions` - List of file extensions to process (comma-separated)
- `-x`, `--exclude` - File exclusion patterns (regular expressions, comma-separated)
- `-v`, `--version` - Display program version

## Examples

Process all documents in a folder recursively:
```bash
documix /path/to/documents -r
```

Process only specific file types:
```bash
documix /path/to/documents -e pdf,docx,zip
```

Exclude certain files:
```bash
documix /path/to/documents -x "temp.*,backup.*"
```

## Dependencies

- For PDF files: poppler-utils (`pdftotext` command)
- For EPUB files: Calibre (`ebook-convert` command)
- For DOCX files: pandoc 
- For DOC files: doc2docx (preferred), antiword, or catdoc

## License

This project is licensed under the MIT License - see the LICENSE file for details.