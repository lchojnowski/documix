# DocuMix

Compile a folder of documents into one Markdown file that is easy to feed to an LLM, in the spirit of Repomix. PDF, Word (`.doc`, `.docx`), PowerPoint, Excel, OpenDocument, RTF, EPUB, CSV, text and code files, ZIP archives and `.eml` messages with their attachments all come out as one consistent document with a directory tree and per-file sections.

DocuMix is a single Rust binary. Conversion runs locally through two engines: [anydoc](https://github.com/firecrawl/anydoc) (MIT, Rust) for every office format and text-based PDFs, and [LiteParse](https://developers.llamaindex.ai/liteparse/) (Apache-2.0, bundled Tesseract) for scanned PDFs. Nothing is sent over the network. A Python implementation of the same CLI lives in [`python/`](python/) as the fallback for the legacy converters (MinerU, PaddleOCR, pdfplumber, pandoc, LibreOffice, a bounded Tesseract profile, a sandboxed MarkItDown Office parser) and the benchmark subcommand; both implementations produce byte-identical output on the default path and are kept that way by a parity harness.

## Installation

Prerequisites: Rust 1.88 or newer (`rustup`), a C++ toolchain and `cmake` (the LiteParse crate compiles Tesseract and Leptonica from source; the first build takes several minutes).

```bash
brew install cmake            # macOS; apt-get install cmake on Debian/Ubuntu
cargo install --path .        # installs `documix` into ~/.cargo/bin
```

For the fastest binary run the profile-guided build instead, which rebuilds with a profile collected on the bundled samples (about 20% less CPU on top of LTO):

```bash
rustup component add llvm-tools-preview
./pgo.sh                      # -> target/release/documix
```

The release profile already uses fat LTO, mimalloc and `target-cpu=native` (`.cargo/config.toml`); remove that flag for a binary that must run on older CPUs.

## Usage

```bash
documix /path/to/folder -r -o output.md
documix email.eml -o email_output.md
```

| Flag | Description |
| --- | --- |
| `-o`, `--output` | Output file (default: `documix-output.md`) |
| `-r`, `--recursive` | Search folders recursively |
| `-e`, `--extensions` | File extensions to process, comma-separated (default: pdf, epub, docx, docm, doc, xlsx, xlsm, xls, pptx, pptm, ppt, odt, ods, odp, rtf, txt, md, py, rb, js, html, css, json, yml, yaml, zip, eml) |
| `-x`, `--exclude` | Exclusion patterns for file names, comma-separated regular expressions |
| `-j`, `--jobs` | Files converted concurrently (default: one per CPU core, bounded by RAM at ~1.5 GB per job; `DOCUMIX_JOBS` overrides; `1` disables parallelism). Output order is always deterministic |
| `-v`, `--version` | Version and converter availability |
| `--standard-format` | Standard output format even for a single email |
| `--pdf-converters`, `--docx-converters`, `--doc-converters`, `--rtf-converters`, `--epub-converters`, `--office-converters` | Converter chain per format, comma-separated (`anydoc`, `liteparse`); legacy names are accepted only by the Python fallback |
| `--office-require-text-only` | Fail XLSX/PPTX/OpenDocument files whose embedded or linked images were not assessed (`unassessed_media`) |

### Engines and failure policy

Every document goes through a chain: anydoc first, LiteParse second (EPUB: anydoc only). anydoc is mandatory: if it cannot run, the whole run stops with exit code 1 and no output file. Problems with one document (a scanned PDF, an encrypted or malformed file) are not fatal: LiteParse gets a turn, and if that fails too the file is recorded as `[Failed to convert ... file: ...]` while the rest continues. LiteParse converts Office inputs through LibreOffice, so without `soffice` on `PATH` an Office file that anydoc declines fails explicitly.

Converted documents are written as raw Markdown under their `## File:` header; only text and code files read verbatim are wrapped in four-backtick code blocks. Single `.eml` files get a dedicated email report; attachments are taken from an `attachments/` folder next to the message when one exists, otherwise extracted from the message.

### Performance

Files convert on a thread pool; anydoc releases the GIL-free Rust code to all cores, and OCR runs in a pool of worker processes (this same binary) because PDFium is serialised inside one process. `DOCUMIX_OCR_WORKERS=N` sizes that pool (`0` parses in-process, which single-document runs do anyway).

Measured against the Python implementation on an Apple M4 Max (14 cores): 7–9x faster on startup and single documents (8 ms vs 65 ms for a Word file, 157 ms vs 395 ms for a scanned page), 1.1–1.4x on folders of hundreds or thousands of files, identical OCR throughput. The method and the full tables are in [BENCHMARK.md](BENCHMARK.md).

## Python fallback (`python/`)

The Python package keeps everything the Rust binary deliberately leaves out: the legacy converters (`--pdf-converters mineru,pdfplumber,markitdown,pdftotext,paddleocr,tesseract`, `--docx-converters pandoc,docx2txt`, `--doc-converters soffice`, `--rtf-converters pandoc,unrtf,striprtf`, `--epub-converters ebook-convert`, `--office-converters markitdown`), the bounded Tesseract OCR profile (`--ocr-*`), the sandboxed MarkItDown Office parser, `documix benchmark`, and the library API (`from documix.documix import DocumentCompiler`). When the Rust binary is asked for one of these it exits with code 3 and names the fallback.

```bash
pip install -e "python/[tables]"       # Python >= 3.10; installs anydoc and liteparse too
documix-py /path/to/folder -r -o output.md
documix-py /path/to/pdfs -r --pdf-converters pdfplumber,pdftotext
```

Its own documentation is in [python/README.md](python/README.md).

## Development

```bash
cargo build --release && cargo test --release     # Rust binary and unit tests
cd python && python -m pytest -q                  # Python suite (includes the parity test when the binary exists)
python scripts/parity.py                          # Python vs Rust: ~30 cases, byte-for-byte
python scripts/bench_port.py --out BENCHMARK.md   # Python vs Rust benchmark
```

`docs/html2text-spec.md` and `docs/output-contract.md` are the specifications the Rust port follows (the email HTML converter is a port of Python's `html2text`). Any change to either implementation must keep `scripts/parity.py` green.

## License

MIT — see [LICENSE](LICENSE).
