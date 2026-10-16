# DocuMix

Tool to compile documents from a folder into a single Markdown file, similar to Repomix.

## Features

- Compiles various document types (PDF, EPUB, DOC, DOCX, XLS, XLSX, PPT, PPTX, OpenDocument, RTF, CSV, TXT, MD, etc.) into a single Markdown file
- **Fast local engines**: [anydoc](https://github.com/firecrawl/anydoc) converts every office format and text PDFs in milliseconds; [LiteParse](https://developers.llamaindex.ai/liteparse/) adds local OCR for scanned PDFs. No document ever leaves your machine.
- **Parallel conversion**: files are converted concurrently (`-j/--jobs`) with a deterministic output order
- Supports ZIP files by automatically extracting and processing their contents
- **Email Mode**: Process .eml files with automatic attachment handling
- **Smart Output Formats**: Automatically detects and uses email-specific format for .eml files
- **Converter Control**: Choose and reorder converters per format (`--pdf-converters`, `--docx-converters`, `--doc-converters`, `--rtf-converters`, `--epub-converters`, `--office-converters`); the previous converters (MinerU, PaddleOCR, pdfplumber, pandoc, LibreOffice, ...) stay available as opt-ins
- **Built-in Benchmarking**: Compare converter speed and accuracy on your system
- Estimates token counts and provides statistics
- Security checks for potentially suspicious files
- Colorful console output with emojis for better readability

## Installation

DocuMix requires Python 3.10 or newer. Installing it pulls in the two conversion engines (`firecrawl-anydoc` and `liteparse`, both prebuilt wheels with no system dependencies):

```bash
pip install git+https://github.com/lchojnowski/documix.git
```

### Optional extras (legacy converters)

The extras below only matter when you opt into the previous converters with `--<format>-converters`.

Install with PDF support (markitdown):
```bash
pip install "documix[pdf] @ git+https://github.com/lchojnowski/documix.git"
```

Install with PDF table extraction (pdfplumber):
```bash
pip install "documix[tables] @ git+https://github.com/lchojnowski/documix.git"
```

Install with XLSX spreadsheet and PPTX presentation support (Python 3.10 or newer for MarkItDown):
```bash
pip install "documix[office] @ git+https://github.com/lchojnowski/documix.git"
```

Install the Office converter in its own virtual environment or pipx environment and make its `markitdown` command available on `PATH`. Its resolved installation must have an executable `python` beside that command; shell wrappers and other layouts are refused. DocuMix uses that interpreter for the sandboxed Office parser (`--office-converters markitdown`).

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
| `-e`, `--extensions` | File extensions to process, comma-separated (default: pdf, epub, docx, docm, doc, xlsx, xlsm, xls, pptx, pptm, ppt, odt, ods, odp, rtf, txt, md, py, rb, js, html, css, json, yml, yaml, zip, eml) |
| `-x`, `--exclude` | File exclusion patterns, comma-separated (regular expressions) |
| `-j`, `--jobs` | Number of files converted concurrently (default: one per CPU core, bounded by installed memory at about 1.5 GB per job, e.g. 10 on a 10-core/32 GB Mac; `DOCUMIX_JOBS` overrides it; `1` disables parallelism). Output order is always deterministic |
| `-v`, `--version` | Display program version and available converters |
| `--standard-format` | Force standard output format (even for emails) |
| `--pdf-converters` | PDF converters to try, in order (comma-separated) |
| `--docx-converters` | DOCX/DOCM converters to try, in order (comma-separated) |
| `--doc-converters` | Legacy DOC converters to try, in order (comma-separated) |
| `--rtf-converters` | RTF converters to try, in order (comma-separated) |
| `--epub-converters` | EPUB converters to try, in order (comma-separated) |
| `--office-converters` | XLSX/PPTX/OpenDocument/CSV converters to try, in order (comma-separated) |
| `--ocr-languages` | Installed Tesseract languages, e.g. `pol+eng` (default: `eng`; requires explicit `tesseract`) |
| `--ocr-max-pages` | Maximum pages per OCR document (default: 20; range: 1–100) |
| `--ocr-dpi` | OCR rendering resolution (default: 150; range: 1–200) |
| `--ocr-timeout` | Total OCR time limit in seconds (default: 180; range: 1–300) |
| `--office-require-text-only` | Reject XLSX/PPTX with unassessed embedded or linked images (opt-in; independent of PDF OCR) |

## Conversion engines

Every document goes through a converter chain; the first converter that returns text wins.

1. **anydoc** (`firecrawl-anydoc`, MIT, written in Rust) is the default engine for PDF, Word (`.doc`, `.docx`, `.docm`), PowerPoint, Excel, OpenDocument, RTF, EPUB and CSV. It renders every format through one Markdown serializer (headings, tables, lists, footnotes, LaTeX math) in single-digit milliseconds and releases the GIL, so files convert in parallel.
2. **LiteParse** (`liteparse`, Apache-2.0, LlamaIndex) is second. It parses PDFs locally with bundled Tesseract OCR, which is how scanned or image-only PDFs that anydoc rejects (`NeedsOcrError`) still get text. For Office inputs LiteParse needs LibreOffice on `PATH`.

Both engines run entirely on your machine; the hosted OCR option of anydoc is not used and no document is sent anywhere.

### Failure policy

anydoc is mandatory. If it is not installed, fails to import or crashes on a document, DocuMix stops immediately: the message `ERROR: anydoc engine failure: ...` is printed, no output file is left behind (a partial one is removed) and the exit code is 1. Library callers receive `documix.errors.EngineError`.

Problems with a particular document are not fatal. A scanned, encrypted, malformed or unreadable file is declined by anydoc, tried with LiteParse, and finally recorded as `[Failed to convert ... file: ...]` while the rest of the run continues. LiteParse itself is never fatal; without it, such documents simply fail.

### Output format

Everything a converter produced is written as raw Markdown under its `## File:` header, so headings and tables render. Only text and code files that are read verbatim (`.txt`, `.md`, `.py`, ...) are wrapped in four-backtick code blocks.

## Converter Control

You can control which converters are used for each format and in what order they are tried. When a flag is omitted, the default order is used. When provided, only the listed converters are tried, in the listed order. An empty result (whitespace or invisible control characters only) advances to the next selected converter.

### Available converters

| Format (flag) | Default order | Opt-in legacy converters |
| --- | --- | --- |
| PDF (`--pdf-converters`) | `anydoc`, `liteparse` | `mineru`, `pdfplumber`, `markitdown-uvx`, `markitdown`, `pdftotext`, `paddleocr`, `tesseract` |
| DOCX, DOCM (`--docx-converters`) | `anydoc`, `liteparse` | `pandoc`, `docx2txt` |
| DOC (`--doc-converters`) | `anydoc`, `liteparse` | `soffice` (LibreOffice to DOCX, then the DOCX chain) |
| RTF (`--rtf-converters`) | `anydoc`, `liteparse` | `pandoc`, `unrtf`, `striprtf` |
| EPUB (`--epub-converters`) | `anydoc` | `ebook-convert` (Calibre) |
| Office: XLSX, XLSM, XLS, PPTX, PPTM, PPT, ODT, ODS, ODP, CSV (`--office-converters`) | `anydoc`, `liteparse` | `markitdown` (sandboxed MarkItDown parser) |

`tesseract` is never added to the default order or automatic benchmarks. Selecting it requires OCR of the complete document, even when another selected converter returns text.

### Examples

Use the previous rule-based PDF converters instead of the engines:
```bash
documix /path/to/pdfs -r --pdf-converters pdfplumber,pdftotext
```

Prioritize PaddleOCR for ML-based layout analysis:
```bash
documix /path/to/pdfs -r --pdf-converters paddleocr,mineru,anydoc
```

Keep anydoc first but fall back to pandoc for Word files it declines:
```bash
documix /path/to/docs -r --docx-converters anydoc,pandoc
```

Convert legacy `.doc` files through LibreOffice:
```bash
documix /path/to/docs -r --doc-converters soffice
```

Use the sandboxed MarkItDown parser for spreadsheets and presentations:
```bash
documix /path/to/docs -r --office-converters markitdown
```

Convert files one at a time (for example to keep converter logs readable):
```bash
documix /path/to/docs -r -j 1
```

Check which converters are installed on your system:
```bash
$ documix -v
DocuMix v1.20260907.1-dev (main)

Converter Configuration:
----------------------------------------
   PDF: anydoc, liteparse
  DOCX: anydoc, liteparse
   DOC: anydoc, liteparse
   RTF: anydoc, liteparse
  EPUB: anydoc
OFFICE: anydoc, liteparse
```

## Local OCR for scanned and mixed PDFs

To extract text from scans without downloading models during conversion, install Tesseract and Poppler locally, including the language packs you need. On Debian/Ubuntu, for Polish and English:

```bash
sudo apt-get install tesseract-ocr tesseract-ocr-pol tesseract-ocr-eng poppler-utils
```

On macOS, install `tesseract`, `tesseract-lang`, and `poppler` with Homebrew. Check the languages already installed with `tesseract --list-langs`. This converter currently supports POSIX systems (Linux and macOS).

Select local text extractors together with mandatory complete-document OCR:

```bash
documix /path/to/pdfs -r --pdf-converters markitdown,pdftotext,tesseract \
  --ocr-languages pol+eng --ocr-max-pages 20 --ocr-dpi 150 --ocr-timeout 180
```

`markitdown` uses an already installed command; `markitdown-uvx` is a separate converter that may install packages. The example above does not select anydoc, LiteParse, MinerU, PaddleOCR, or `markitdown-uvx`. Tesseract does not download tools or language packs, and an unavailable language makes the PDF conversion fail rather than silently switching languages. OCR flags alone do not enable OCR. For most scanned PDFs the default LiteParse fallback (bundled Tesseract, no extra setup) is enough; this profile is for audited, bounded OCR.

When `tesseract` appears anywhere in your PDF converter list, DocuMix runs it once on every page before trying the other selected converters. It retains the first successful native extraction verbatim and appends a labeled OCR rendition; the reported method is, for example, `markitdown+tesseract`. This includes scanned content after a text cover or beneath a text heading on the same page. If native extractors return no text, the output is the OCR rendition alone. Without `tesseract`, the existing first-success converter behavior is unchanged.

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

OCR processes pages in order and keeps the original PDF unchanged. A completely white rendered page is retained as a page separator. An all-white document, an unreadable nonwhite page, or a failure on any page is not reported as successful extraction of the whole document. A failed or over-budget OCR pass fails the PDF conversion regardless of converter order; native text alone cannot replace the missing OCR coverage. OCR can misread or overlook text and does not reconstruct table layout; review important results against the source. A completed pass describes processing coverage, not a guarantee that every word was recognized.

OCR work is bounded per document: defaults are 20 pages, 150 DPI, and 180 seconds, with maximum settings of 100 pages, 200 DPI, and 300 seconds. Rendering also limits each side to 4,000 pixels and each page to 16 million pixels; oversized pages are scaled down. Each OCR native tool call has a 60-second ceiling within the total OCR time budget. Input PDFs are limited to 128 MiB and recognized text to 4 MiB; the combined native text, label and OCR rendition must also fit within 4 MiB, with no truncation. Temporary page images are removed on success or failure. These limits do not replace an operating-system sandbox and memory limits when processing untrusted documents, and do not change the separate native converters' time limits.

This changes the earlier opt-in fallback behavior: even a fully selectable PDF above your OCR page budget now fails under this profile. Automated pipelines should keep such documents visibly incomplete for review or a separately authorized retry. The default 20-page budget and all hard limits remain unchanged; this mode does not promise automatic coverage of every PDF.

Interrupting OCR cancels the active tool and waits for its cleanup. If cleanup cannot be confirmed, compilation stops, including when the PDF is an email or ZIP attachment. Library callers receive `documix.local_ocr.OcrCleanupError`, a fatal `BaseException` rather than an ordinary conversion failure; do not catch it to continue processing other files.

The three-second cleanup acknowledgement budget does not guarantee termination of a process stuck inside the operating system. Use an external process supervisor with a wall-clock limit for unattended or untrusted inputs; a fatal cleanup error must not be treated as proof that every process has stopped.

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

anydoc renders PDF tables as Markdown pipe tables out of the box, and LiteParse renders tables from its spatial layout. The converters below are the previous, opt-in alternatives (`--pdf-converters ...`) for cases where an ML layout model gives better results.

### MinerU (ML-based)

If [MinerU](https://github.com/opendatalab/MinerU) is installed and selected, documix uses it for PDF conversion. MinerU uses ML models (YOLO layout detection, SLANet table recognition, OCR) to correctly detect complex tables — including borderless tables in invoices — and produces structured markdown output.

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

The default order is **anydoc** (text-based PDFs, tables as Markdown) followed by **LiteParse** (local OCR for scanned pages). Override it with `--pdf-converters`, for example `--pdf-converters mineru,anydoc,liteparse` to prefer MinerU when it is installed. Legacy converters that are not installed are skipped.

## Benchmarking

DocuMix includes a built-in benchmark command to compare converter speed and accuracy on your system.

```bash
documix benchmark
```

This automatically discovers and benchmarks all files in the `resources/` directory using every available converter, engines and legacy ones alike. Results are saved to the `benchmark/` directory.

### Benchmark Options

| Flag | Description |
| --- | --- |
| `files` (positional) | Additional files to benchmark (on top of `resources/`) |
| `--runs N` | Number of timing iterations per converter (default: 3) |
| `--output-dir DIR` | Results directory (default: `benchmark/`) |
| `--formats FMT` | Which formats to benchmark: `pdf`, `docx`, `doc`, `rtf`, `epub`, or `all` (default: `all`) |

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

| Extension | Default converters | Opt-in legacy converters (external dependency) |
| --- | --- | --- |
| `.pdf` | anydoc, LiteParse (OCR) | MinerU, pdfplumber, markitdown, pdftotext, PaddleOCR, Tesseract (see PDF sections above) |
| `.epub` | anydoc | ebook-convert ([Calibre](https://calibre-ebook.com/)) |
| `.docx`, `.docm` | anydoc, LiteParse | pandoc, docx2txt |
| `.doc` | anydoc, LiteParse | soffice ([LibreOffice](https://www.libreoffice.org/)) |
| `.xlsx`, `.xlsm`, `.xls`, `.pptx`, `.pptm`, `.ppt`, `.odt`, `.ods`, `.odp`, `.csv` | anydoc, LiteParse | markitdown (sandboxed MarkItDown parser) |
| `.rtf` | anydoc, LiteParse | pandoc, unrtf, striprtf |
| `.eml` | built-in | — |
| `.zip` | built-in (auto-extract) | — |
| `.txt`, `.md`, `.py`, `.js`, etc. | direct read | — |

LiteParse converts Office inputs through LibreOffice, so without `soffice` on `PATH` an Office file that anydoc declines fails explicitly. Conversion never installs packages or downloads models (LiteParse ships its Tesseract data; set `TESSDATA_PREFIX` for extra languages).

For unattended document screening, select `--office-require-text-only`. This refuses Office documents with embedded or linked images, even when a heading or other selectable text is available, because the image might contain the only relevant requirement. With anydoc the check inspects the document model and the package relationships; with the sandboxed MarkItDown parser it inspects the package relationships. The result is an explicit `failed` conversion with reason `unassessed_media`; keep it incomplete for review. This conservative check can also reject ordinary logos. It does not perform Office image OCR and does not claim general visual or layout coverage. It is independent of PDF OCR and does not change default Office text extraction.

```bash
documix /path/to/documents -r --office-require-text-only
```

The library exposes the same policy with `DocumentCompiler(..., office_require_text_only=True)`; its default is `False`.

The sandboxed MarkItDown parser (`--office-converters markitdown`) checks the ZIP contents without extracting archive paths and passes a private read-only copy to the parser. Limits are 128 MiB input, 10,000 archive members, 32 MiB per expanded member, 256 MiB total expanded content, a 1,000:1 compression ratio, 4 MiB text output and 60 seconds overall. Temporary copies are removed, originals remain unchanged, and unconfirmed cleanup stops compilation. Use an external sandbox, memory limits and supervisor for untrusted documents. Default text extraction does not assess Office images; use the strict option when their omission must leave the document visibly incomplete.

## Performance

Files are converted on a thread pool (`-j/--jobs`). The default is one job per logical CPU core, capped by installed memory at roughly 1.5 GB per job (a 10-core, 32 GB Apple Silicon machine runs 10 jobs; an 8 GB laptop 5); set `DOCUMIX_JOBS` to override it without touching the command line. anydoc releases the GIL and the legacy converters are external processes, so throughput scales with the number of jobs while the output order stays identical to a serial run. LiteParse OCR runs in a process pool sized like the job count (about 250 MB per worker), so scanned PDFs are OCR'd in parallel as well. Email files are processed on the main thread because sibling emails share an `attachments/` folder. Every external tool call has a timeout, temporary files are removed even when a tool fails, and tool availability is probed once per process.

Measured on an Apple M4 Max (14 cores, 36 GB) with a 220-file corpus built from the bundled samples (40 × 22-page PDF, 40 invoice PDFs, 40 `.doc`, 40 `.docx`, 20 scanned PDFs, 40 Markdown files); the output of every parallel run was byte-identical to the serial one:

| Variant | Wall time |
| --- | --- |
| Previous release (serial, pdfplumber / LibreOffice / pandoc) | 149.5 s |
| Engines, `-j 1` | 4.3 s |
| Engines, `-j 4` | 1.3 s |
| Engines, auto default (14 jobs on that machine) | 1.0 s |

## Dependencies

### Core Dependencies (installed automatically)
- `firecrawl-anydoc`: primary conversion engine (Rust, MIT)
- `liteparse`: secondary engine with local OCR (Rust, Apache-2.0)
- `docx2txt`: legacy DOCX converter
- `html2text`: For converting HTML email content to Markdown

### Optional Extras
- `documix[pdf]` — markitdown for PDF text extraction
- `documix[office]` — MarkItDown with XLSX and PPTX parsing dependencies (Python 3.10+)
- `documix[tables]` — pdfplumber for rule-based PDF table detection
- `documix[paddleocr]` — PaddleOCR + PaddlePaddle for ML-based document analysis

### Optional External Tools (legacy converters)
- **MinerU** (`pip install magic-pdf[full]`) — ML-based PDF layout/table detection via CLI
- **pandoc** — DOCX and RTF conversion
- **Calibre** (`ebook-convert` command) — EPUB conversion
- **LibreOffice** (`soffice` command) — DOC conversion; also used by LiteParse for Office inputs
- **poppler-utils** (`pdftotext` command) — plain text PDF extraction; `pdfinfo` and `pdftoppm` are also required for opt-in OCR
- **Tesseract** with local language packs — opt-in scanned PDF text extraction
- **unrtf** — RTF conversion fallback

## License

This project is licensed under the MIT License - see the LICENSE file for details.
