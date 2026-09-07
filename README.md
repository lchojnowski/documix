# DocuMix

Tool to compile documents from a folder into a single Markdown file, similar to Repomix.

## Features

- Compiles various document types (PDF, EPUB, DOCX, DOC, RTF, TXT, MD, etc.) into a single Markdown file
- Supports ZIP files by automatically extracting and processing their contents
- **Email Mode**: Process .eml files with automatic attachment handling
- **Smart Output Formats**: Automatically detects and uses email-specific format for .eml files
- **Converter Control**: Choose and reorder converters per format (`--pdf-converters`, `--docx-converters`, `--rtf-converters`)
- **PDF Table Extraction**: ML-based (MinerU, PaddleOCR) and rule-based (pdfplumber) table detection with markdown output
- **Built-in Benchmarking**: Compare converter speed and accuracy on your system
- Estimates token counts and provides statistics
- Security checks for potentially suspicious files
- Colorful console output with emojis for better readability

## Installation

You can install documix directly from GitHub:

```bash
pip install git+https://github.com/lchojnowski/documix.git
```

### Optional extras

Install with PDF support (markitdown):
```bash
pip install "documix[pdf] @ git+https://github.com/lchojnowski/documix.git"
```

Install with PDF table extraction (pdfplumber):
```bash
pip install "documix[tables] @ git+https://github.com/lchojnowski/documix.git"
```

Install with PaddleOCR support (ML-based document analysis; heavy dependencies ~1 GB, models downloaded on first run):
```bash
pip install "documix[paddleocr] @ git+https://github.com/lchojnowski/documix.git"
```

You can combine extras:
```bash
pip install "documix[tables,paddleocr] @ git+https://github.com/lchojnowski/documix.git"
```

## Quick Setup (macOS)

Install all dependencies (converters, ML tools, Python packages) in one step:

```bash
git clone https://github.com/lchojnowski/documix.git
cd documix
bin/setup
```

The script installs everything via Homebrew and pip. If [mise](https://mise.jdx.dev/) is available, it will be used for supported tools. Run it again anytime to check for missing dependencies.

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

With table support via uvx:
```bash
uvx --from 'documix[tables] @ git+https://github.com/lchojnowski/documix.git' documix /path/to/folder -r
```

## Usage

```bash
documix /path/to/folder -r -o output.md
```

### Options

| Flag | Description |
| --- | --- |
| `-o`, `--output` | Path to the output file (default: `documix-output.md`) |
| `-r`, `--recursive` | Search folders recursively |
| `-e`, `--extensions` | File extensions to process, comma-separated (default: pdf, epub, docx, doc, rtf, txt, md, py, rb, js, html, css, json, yml, yaml, zip, eml) |
| `-x`, `--exclude` | File exclusion patterns, comma-separated (regular expressions) |
| `-v`, `--version` | Display program version and available converters |
| `--standard-format` | Force standard output format (even for emails) |
| `--pdf-converters` | PDF converters to try, in order (comma-separated) |
| `--docx-converters` | DOCX converters to try, in order (comma-separated) |
| `--rtf-converters` | RTF converters to try, in order (comma-separated) |
| `--ocr-languages` | Installed Tesseract languages, e.g. `pol+eng` (default: `eng`; requires explicit `tesseract`) |
| `--ocr-max-pages` | Maximum pages per OCR document (default: 20; range: 1–100) |
| `--ocr-dpi` | OCR rendering resolution (default: 150; range: 1–200) |
| `--ocr-timeout` | Total OCR time limit in seconds (default: 180; range: 1–300) |

## Converter Control

You can control which converters are used for each format and in what order they are tried. When a flag is omitted, the default order is used. When provided, only the listed converters are tried, in the listed order.

An empty PDF result now advances to the next selected converter, including results containing only whitespace or invisible control characters. The first result containing text is kept unchanged. Existing default converter order and Markdown output format are preserved.

### Available converters

| Format | Converters (default order) |
| --- | --- |
| PDF | `mineru`, `pdfplumber`, `markitdown-uvx`, `markitdown`, `pdftotext`, `paddleocr` |
| DOCX | `pandoc`, `docx2txt` |
| RTF | `pandoc`, `unrtf`, `striprtf` |

PDF also supports `tesseract` as an explicit opt-in converter; it is never added to the default order or automatic benchmarks.

For non-PDF formats, **pandoc** is always the default first converter due to its high-quality markdown output. Remaining converters are ordered by speed as fallbacks.

### Examples

Use only pdfplumber and pdftotext (skip ML converters for speed):
```bash
documix /path/to/pdfs -r --pdf-converters pdfplumber,pdftotext
```

Prioritize PaddleOCR for best OCR quality:
```bash
documix /path/to/pdfs -r --pdf-converters paddleocr,mineru,pdfplumber
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

Check which converters are installed on your system:
```bash
$ documix -v
DocuMix v1.20260316.0-dev (main)

Converter Configuration:
----------------------------------------
   PDF: pdfplumber, markitdown-uvx, markitdown, pdftotext
        missing: mineru, paddleocr
  DOCX: pandoc, docx2txt
   RTF: pandoc
        missing: unrtf, striprtf
```

## Local OCR for scanned PDFs

To extract text from scans without downloading models during conversion, install Tesseract and Poppler locally, including the language packs you need. On Debian/Ubuntu, for Polish and English:

```bash
sudo apt-get install tesseract-ocr tesseract-ocr-pol tesseract-ocr-eng poppler-utils
```

On macOS, install `tesseract`, `tesseract-lang`, and `poppler` with Homebrew. Check the languages already installed with `tesseract --list-langs`. This converter currently supports POSIX systems (Linux and macOS).

Select local text extractors first, with OCR as the final fallback:

```bash
documix /path/to/pdfs -r --pdf-converters markitdown,pdftotext,tesseract \
  --ocr-languages pol+eng --ocr-max-pages 20 --ocr-dpi 150 --ocr-timeout 180
```

`markitdown` uses an already installed command; `markitdown-uvx` is a separate converter that may install packages. The example above does not select MinerU, PaddleOCR, or `markitdown-uvx`. Tesseract does not download tools or language packs, and an unavailable language causes that converter to fail rather than silently switching languages. OCR flags alone do not enable OCR.

The library accepts the same settings without changing existing calls:

```python
from documix.documix import DocumentCompiler

compiler = DocumentCompiler(
    source_path="/path/to/pdfs",
    output_file="output.md",
    converter_config={"pdf": ["markitdown", "pdftotext", "tesseract"]},
    ocr_config={"languages": "pol+eng", "max_pages": 20, "dpi": 150, "timeout": 180},
)
compiler.compile()
```

OCR processes pages in order and keeps the original PDF unchanged. A completely white rendered page is retained as a page separator. An all-white document, an unreadable nonwhite page, or a failure on any page is not reported as successful extraction of the whole document. If another converter follows Tesseract in your explicit list, DocuMix tries it next. OCR can misread text and does not reconstruct table layout; review important results against the source.

Work is bounded per document: defaults are 20 pages, 150 DPI, and 180 seconds, with maximum settings of 100 pages, 200 DPI, and 300 seconds. Rendering also limits each side to 4,000 pixels and each page to 16 million pixels; oversized pages are scaled down. Each native tool call has a 60-second ceiling within the total time budget. Input PDFs are limited to 128 MiB and recognized text to 4 MiB. Temporary page images are removed on success or failure. These limits do not replace an operating-system sandbox and memory limits when processing untrusted documents.

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

### PaddleOCR (ML-based OCR and document analysis)

[PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) PP-StructureV3 provides ML-based document analysis with OCR, table recognition, and layout detection. It is Apache 2.0 licensed. PaddlePaddle requires Python 3.12 or earlier, so PaddleOCR runs in its own uv-managed venv via subprocess.

Install via the `paddleocr` extra:
```bash
pip install "documix[paddleocr] @ git+https://github.com/lchojnowski/documix.git"
```

Or install PaddleOCR standalone and it will be auto-detected:
```bash
uv tool install paddleocr[doc-parser]
```

PaddleOCR renders tables as HTML internally; documix automatically converts them to markdown tables.

### pdfplumber (rule-based)

Install with table support for rule-based table detection as a fallback:
```bash
pip install 'documix[tables] @ git+https://github.com/lchojnowski/documix.git'
```

Or with uvx:
```bash
uvx --from 'documix[tables] @ git+https://github.com/lchojnowski/documix.git' documix /path/to/folder -r
```

### PDF conversion priority

The default order tries each converter until one succeeds:

1. **MinerU** — ML-based layout/table detection (if installed)
2. **pdfplumber** — rule-based table detection (if installed)
3. **markitdown** (via uvx or direct) — plain text
4. **pdftotext** — plain text with layout preservation
5. **PaddleOCR** — ML-based OCR and document analysis (if installed)

You can override this order with `--pdf-converters`. Without any table-aware tool installed, documix falls back to markitdown or pdftotext for PDF conversion (plain text, no table structure).

## Benchmarking

DocuMix includes a built-in benchmark command to compare converter speed and accuracy on your system.

```bash
documix benchmark
```

This automatically discovers and benchmarks all files in the `resources/` directory using every available converter. Results are saved to the `benchmark/` directory.

### Benchmark Options

| Flag | Description |
| --- | --- |
| `files` (positional) | Additional files to benchmark (on top of `resources/`) |
| `--runs N` | Number of timing iterations per converter (default: 3) |
| `--output-dir DIR` | Results directory (default: `benchmark/`) |
| `--formats FMT` | Which formats to benchmark: `pdf`, `docx`, `rtf`, or `all` (default: `all`) |

### Examples

Benchmark only PDF converters with 5 runs:
```bash
documix benchmark --formats pdf --runs 5
```

Benchmark with an additional file:
```bash
documix benchmark /path/to/my/document.pdf
```

### Output

The benchmark produces:
- `benchmark/results.json` — Full timing, accuracy, and system info
- `benchmark/converter_ranking.json` — Converters ranked by combined speed/accuracy score per format
- `benchmark/outputs/` — Raw converter outputs for manual comparison

The ranking file is informational only — it does not override the default converter order at runtime.

## Supported File Types

| Extension | Converter | External dependency |
| --- | --- | --- |
| `.pdf` | MinerU, pdfplumber, markitdown, pdftotext, PaddleOCR; opt-in Tesseract | See PDF sections above |
| `.epub` | ebook-convert | [Calibre](https://calibre-ebook.com/) |
| `.docx` | pandoc, docx2txt | pandoc (optional, recommended) |
| `.doc` | soffice | [LibreOffice](https://www.libreoffice.org/) |
| `.rtf` | pandoc, unrtf, striprtf | pandoc (optional), unrtf, or `pip install striprtf` |
| `.eml` | built-in | — |
| `.zip` | built-in (auto-extract) | — |
| `.txt`, `.md`, `.py`, `.js`, etc. | direct read | — |

## Dependencies

### Core Dependencies (installed automatically)
- `docx2txt`: For DOCX file processing (fallback method)
- `html2text`: For converting HTML email content to Markdown

### Optional Extras
- `documix[pdf]` — markitdown for PDF text extraction
- `documix[tables]` — pdfplumber for rule-based PDF table detection
- `documix[paddleocr]` — PaddleOCR + PaddlePaddle for ML-based document analysis

### Optional External Tools
- **MinerU** (`pip install magic-pdf[full]`) — ML-based PDF layout/table detection via CLI
- **pandoc** — high-quality DOCX and RTF conversion (primary converter)
- **Calibre** (`ebook-convert` command) — EPUB conversion
- **LibreOffice** (`soffice` command) — DOC conversion
- **poppler-utils** (`pdftotext` command) — plain text PDF extraction; `pdfinfo` and `pdftoppm` are also required for opt-in OCR
- **Tesseract** with local language packs — opt-in scanned PDF text extraction
- **unrtf** — RTF conversion fallback

## License

This project is licensed under the MIT License - see the LICENSE file for details.
