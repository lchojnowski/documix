# Changelog

## Unreleased

- **Rust is now the primary implementation.** The crate lives at the
  repository root and builds the `documix` binary (fat LTO, mimalloc,
  `target-cpu=native`, optional PGO via `pgo.sh`); OCR runs in a pool of
  worker processes. The Python implementation moved to `python/` as the
  fallback: its command is `documix-py`, it keeps the legacy converters, the
  Tesseract profile, the MarkItDown sandbox, `benchmark` and the library
  API. Both stay byte-identical on the default path (`scripts/parity.py`,
  also run in CI). The version of record is `Cargo.toml`.
- Python fallback: the legacy `soffice` converter now runs LibreOffice
  headless in its own process group with a hard timeout
  (`DOCUMIX_SOFFICE_TIMEOUT`, default 300 s) and kills the whole process
  tree when it hangs on a malformed `.doc`.
- Rust port of the default conversion path with byte-identical output
  (verified by `scripts/parity.py`) and a Python-vs-Rust benchmark
  (`scripts/bench_port.py`, results in `BENCHMARK.md`).
- **New conversion engines.** anydoc (`firecrawl-anydoc`, MIT) is now the
  default converter for PDF, Word (`.doc`/`.docx`/`.docm`), PowerPoint, Excel,
  OpenDocument, RTF, EPUB and CSV; LiteParse (Apache-2.0, bundled Tesseract
  OCR) is the second converter and handles scanned PDFs. Both run locally and
  never send documents over the network. Python 3.10 or newer is required.
- **Fail-fast engine policy.** A missing or crashing anydoc aborts the whole
  run with exit code 1 and no output file. Document-level problems (scans,
  encrypted or malformed files) fall through to LiteParse and then to the
  usual `[Failed to convert ...]` placeholder.
- The previous converters (MinerU, pdfplumber, markitdown, pdftotext,
  PaddleOCR, Tesseract, pandoc, docx2txt, LibreOffice, unrtf, striprtf,
  ebook-convert, sandboxed MarkItDown) remain available as explicit opt-ins
  via `--pdf-converters`, `--docx-converters`, `--rtf-converters` and the new
  `--doc-converters`, `--epub-converters`, `--office-converters`.
- **Parallel conversion.** Files are converted concurrently (`-j/--jobs`;
  the default is one job per CPU core bounded by installed memory, e.g. 10 on
  a 10-core/32 GB Mac, `DOCUMIX_JOBS` overrides it); LiteParse OCR uses a
  matching process pool. The output order stays deterministic.
- Converted documents are written as raw Markdown; only text and code files
  read verbatim are wrapped in code fences. Raw sections now always end with
  a blank line before the next file header.
- Default extensions now include `.docm`, `.ppt`, `.pptm`, `.xls`, `.xlsm`,
  `.odt`, `.ods`, `.odp`.
- Every external tool call has a timeout, temporary files are removed on
  failure, tool availability probes are cached per process, optional
  dependencies import lazily, and the source tree is scanned once.
- Internal: `documix/documix.py` is now a compatibility facade; the code is
  split into `cli`, `compiler`, `converters/*`, `email_processor`, `output`,
  `tools`, `textutils`, `deps`, `benchmark`.

## 1.20260907.1

- Explicit Tesseract selection now processes every PDF page, including scanned
  content alongside selectable text. The original native extraction is retained
  with a separately labeled OCR rendition.
- A failed or over-budget OCR pass now reports the PDF as failed regardless of
  converter order. Even fully selectable PDFs above the selected page budget
  need review or a retry; the default 20-page budget is unchanged. PDF conversion
  without Tesseract keeps its existing behavior.
- XLSX spreadsheets and PPTX presentations are now collected by default and
  converted with an installed MarkItDown parser. Missing tools or unreadable
  documents report a failure instead of returning compressed bytes as text.
- The optional `--office-require-text-only` check leaves documents containing
  unassessed embedded or linked images failed for review, including images
  alongside a readable heading. It works independently of PDF OCR.
