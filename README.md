# DocuMix

Tool to compile documents from a folder into a single Markdown file, similar to Repomix.

## Features

- Compiles various document types (PDF, EPUB, DOCX, DOC, RTF, TXT, MD, etc.) into a single Markdown file
- Supports ZIP files by automatically extracting and processing their contents
- **Email Mode**: Process .eml files with automatic attachment handling
- **Smart Output Formats**: Automatically detects and uses email-specific format for .eml files
- Generates a structured file with detailed document contents
- Estimates token counts and provides statistics
- Security checks for potentially suspicious files
- Colorful console output with emojis for better readability

## Installation

You can install documix directly from GitHub:

```bash
pip install git+https://github.com/lchojnowski/documix.git
```

For the best PDF conversion quality, install with PaddleOCR support (note: heavy dependencies, ~1 GB; models are downloaded on first run):

```bash
pip install "git+https://github.com/lchojnowski/documix.git#egg=documix[paddleocr]"
```

## Quick Start with uvx

Run documix without installing using [uvx](https://docs.astral.sh/uv/):

```bash
uvx --from git+https://github.com/lchojnowski/documix.git documix /path/to/folder -r
```

This always uses the latest version from GitHub without requiring installation.

### uvx Examples

Process documents:
```bash
uvx --from git+https://github.com/lchojnowski/documix.git documix /path/to/documents -r -o output.md
```

Process a single email:
```bash
uvx --from git+https://github.com/lchojnowski/documix.git documix email.eml -o email_output.md
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
- `--standard-format` - Force standard output format (even for emails)
- `--pdf-converters` - PDF converters to try, in order (comma-separated)
- `--docx-converters` - DOCX converters to try, in order (comma-separated)
- `--rtf-converters` - RTF converters to try, in order (comma-separated)

## Converter Control

You can control which converters are used for each format and in what order they are tried. When a flag is omitted, the default order is used. When provided, only the listed converters are tried, in the listed order.

### Available converters

| Format | Converters (default order) |
| --- | --- |
| PDF | `paddleocr`, `mineru`, `pdfplumber`, `markitdown-uvx`, `markitdown`, `pdftotext` |
| DOCX | `pandoc`, `docx2txt` |
| RTF | `pandoc`, `unrtf`, `striprtf` |

### Examples

Skip MinerU (slow on CPU) and use only pdfplumber and pdftotext:
```bash
documix /path/to/pdfs -r --pdf-converters pdfplumber,pdftotext
```

Use only pdftotext for plain text extraction:
```bash
documix /path/to/pdfs -r --pdf-converters pdftotext
```

Use only docx2txt for DOCX files (skip pandoc):
```bash
documix /path/to/docs -r --docx-converters docx2txt
```

Use only striprtf for RTF files:
```bash
documix /path/to/docs -r --rtf-converters striprtf
```

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

## Email Mode

DocuMix provides specialized handling for email files (.eml) with intelligent output formatting.

### Email Processing Features

1. **Automatic Attachment Detection**: If an "attachments" folder exists next to the .eml file, DocuMix will use those files instead of extracting from the email
2. **Email Parsing**: Extracts metadata (From, To, Subject, Date, etc.) and converts HTML content to Markdown
3. **Attachment Processing**: All supported attachment types (PDF, DOCX, etc.) are automatically processed and included
4. **Smart Output Format**: Automatically uses email-specific format that includes:
   - Email metadata display (sender, recipients, date, subject)
   - Authentication information (SPF, DKIM, DMARC)
   - Attachment summaries with file types and sizes
   - Clean, email-focused presentation

### Output Format Detection

DocuMix automatically detects and uses the appropriate output format:
- **Single Email**: Always uses dedicated email analysis format
- **Multiple Emails**: Treats each email as a separate document in standard format
- **Mixed Content**: Uses standard format when processing emails with other documents


### Email Processing Examples

Process a single email file:
```bash
documix email.eml -o email_output.md
```

Process an email directory structure:
```bash
# Directory structure:
# emails/
# ├── message.eml
# └── attachments/
#     ├── document.pdf
#     └── report.docx

documix emails/ -o consolidated_email.md
```

Process multiple emails:
```bash
documix /path/to/emails -r -e eml
```

Force standard format for email processing:
```bash
documix email.eml -o output.md --standard-format
```

## PDF Table Extraction

DocuMix can detect tables in PDFs and output them as markdown tables, preserving structure that would otherwise be lost with plain text extraction. This is especially useful for invoices, reports, and other documents with tabular data.

### MinerU (best quality — ML-based)

If [MinerU](https://github.com/opendatalab/MinerU) is installed, documix uses it as the top-priority PDF converter. MinerU uses ML models (YOLO layout detection, SLANet table recognition, OCR) to correctly detect complex tables — including borderless tables in invoices — and produces structured markdown output.

```bash
pip install magic-pdf[full]
```

MinerU is called via CLI only (subprocess) to keep its AGPL licence separate from documix's MIT licence.

### pdfplumber (rule-based)

Install with table support for rule-based table detection as a fallback:
```bash
pip install 'documix[tables] @ git+https://github.com/lchojnowski/documix.git'
```

Or with uvx:
```bash
uvx --from 'documix[tables] @ git+https://github.com/lchojnowski/documix.git' documix /path/to/folder -r
```

### Conversion priority

1. **MinerU** — ML-based layout/table detection (if installed)
2. **pdfplumber** — rule-based table detection (if installed)
3. **markitdown** (via uvx or direct) — plain text
4. **pdftotext** — plain text with layout preservation

Without any table-aware tool installed, documix falls back to markitdown or pdftotext for PDF conversion (plain text, no table structure).

## Dependencies

### Core Dependencies (installed automatically)
- `docx2txt`: For DOCX file processing (fallback method)
- `html2text`: For converting HTML email content to Markdown

### Optional External Dependencies
- For PDF tables (best): MinerU (`pip install magic-pdf[full]`) — ML-based layout/table detection via CLI
- For PDF tables: pdfplumber (`pip install documix[tables]`) — rule-based table detection
- For PDF files: markitdown (if available) or poppler-utils (`pdftotext` command) — plain text fallback
- For EPUB files: Calibre (`ebook-convert` command)
- For DOCX files: pandoc (primary method)
- For DOC files: LibreOffice (`soffice` command)
- For RTF files: pandoc (primary), unrtf, or striprtf (`pip install striprtf`)

## License

This project is licensed under the MIT License - see the LICENSE file for details.