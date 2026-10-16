# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Test Commands

```bash
# Install in a Python >= 3.10 virtualenv (anydoc and LiteParse are hard dependencies)
pip install -e ".[pdf,tables,paddleocr]"

# Install macOS external tools for the legacy converters (pandoc, poppler, calibre, libreoffice, unrtf, uv)
bin/setup

# Run all tests
python -m pytest

# Run a single test
python -m pytest tests/test_documix.py::TestDocuMix::test_collect_files -v

# Run tests with coverage
python -m pytest --cov=documix
```

No linter or formatter is configured. The only GitHub Actions workflow bumps the version on push to `main`; tests run locally.

## Architecture

### Package layout

`documix/documix.py` is only a backwards-compatible facade (re-exports plus script mode). The implementation is split by responsibility:

| Module | Responsibility |
| --- | --- |
| `cli.py` | `main()`, argparse, `print_converter_info()`, fatal-error exit |
| `compiler.py` | `DocumentCompiler`: file discovery (one scan), security check, converter chains per format, parallel `compile()`, statistics |
| `config.py` | `CONVERTER_DEFAULTS`, `LEGACY_CONVERTERS`, `CONVERTER_CHOICES`, `FORMAT_OF_EXTENSION`, `DEFAULT_EXTENSIONS`, `LANGUAGE_MAP` |
| `converters/anydoc.py` | primary engine (`firecrawl-anydoc`), `require()`, fail policy |
| `converters/liteparse.py` | secondary engine (LiteParse, local OCR), shared parser with worker pool |
| `converters/pdf.py`, `docx.py`, `rtf.py`, `epub.py`, `office.py`, `text.py` | legacy converters as pure functions `convert(path, ...) -> (text, method) \| (None, None)` |
| `converters/archive.py` | ZIP extraction (recurses through the compiler's `process_file`) |
| `email_processor.py` | `EmailProcessor` (.eml parsing, attachments) |
| `output.py` | every output string: standard preamble, file entries, single-email report |
| `tools.py` | `run_tool()` (subprocess with timeout), `temp_output()`, cached `probe()` + `clear_cache()`, `check_converter_availability()` |
| `textutils.py` | token estimate, size formatting, language map, markdown tables, HTML table conversion, `word_similarity` |
| `deps.py` | optional deps (`pdfplumber`, `docx2txt`) resolved lazily; `PDFPLUMBER_AVAILABLE` / `DOCX2TXT_AVAILABLE` |
| `benchmark.py` | `documix benchmark` |
| `errors.py` | `EngineError` |
| `local_ocr.py`, `office_documents.py`, `office_parser.py` | opt-in Tesseract OCR and the sandboxed MarkItDown Office parser (unchanged) |

### Conversion engines and chains

Every document format has a converter chain (first success wins, `converters.run_chain`). Defaults are `anydoc` then `liteparse` (`epub`: anydoc only); the legacy converters are opt-in through `--<format>-converters` and `converter_config`. Format keys: `pdf`, `docx`, `doc`, `rtf`, `epub`, `office` (xlsx/pptx/xls/ppt/OpenDocument/csv).

Fail policy: anydoc is mandatory. `converters.anydoc.require()` runs before any work in `cli.main()`, and any engine failure (missing package, crash) raises `documix.errors.EngineError`, which propagates through `extract_zip`, `process_email` and the thread pool; `compile()` removes the partial output and `main()` exits 1. Document-level failures (`anydoc.ConvertError` subclasses such as `NeedsOcrError` for scans, unreadable file) just move the chain on to LiteParse, then to the `[Failed to convert ...]` placeholder. LiteParse is never fatal. Neither engine sends documents over the network.

Output rule: only `direct_read` text/code files are wrapped in four-backtick fences; everything a converter produced is Markdown and is written raw.

### Concurrency

`compile()` converts files on a `ThreadPoolExecutor` (`jobs`, CLI `-j`; default from `compiler.default_jobs()`: one per CPU core bounded by RAM at ~1.5 GB per job, `DOCUMIX_JOBS` overrides), buffering at most `2 * jobs` results and writing in sorted-file order, so output is deterministic. Only the top level owns a pool; ZIP members and attachments convert serially inside their task. `.eml` files run on the main thread (siblings share an `attachments/` folder). LibreOffice (`soffice`, also used by LiteParse for Office inputs) runs under a lock.

### Conventions that keep tests working

- Cross-module calls go through the module object (`from . import tools; tools.check_converter_availability()`), never `from x import y`. Each function then has exactly one `patch` target (`documix.tools.check_converter_availability`, `documix.version.get_version`, `documix.cli.DocumentCompiler`, `documix.compiler.EmailProcessor`, `documix.deps.pdfplumber`, ...). `documix.documix.subprocess`, `.shutil`, `.local_ocr`, `.office_documents` remain valid patch targets because the facade imports those modules.
- `DocumentCompiler` keeps its historical method names (`convert_pdf_to_text`, `_try_docx_pandoc`, `convert_pdf_with_mineru`, `is_uvx_available`, ...) as thin delegates and builds dispatch tables from `self.<method>` on every call, so tests can `patch.object` any step on an instance.
- Tool probes (`tools.probe`) are cached per process; `tests/conftest.py` clears the cache around every test (autouse fixture) and provides `LEGACY_CONVERTER_CONFIG` for tests that exercise the legacy chains.
- The constructor contract is positional `(source_path, output_file, recursive, include_extensions, exclude_patterns, force_format, converter_config)` plus keyword `ocr_config`, `office_require_text_only`, `jobs`; `main()` passes keyword arguments only when the corresponding flag was given.
- `python documix/documix.py --help` (script mode) must keep working; the facade adds the repo root to `sys.path` when run directly.

**License isolation**: AGPL tools (MinerU) and heavy ML tools (PaddleOCR) are invoked only via subprocess to keep the main package MIT-licensed.

### Rust port (`rust/`)

`rust/` is an experimental standalone port of the default path (`documix-rs`), written to measure Python-vs-Rust performance. It must stay byte-identical with the Python CLI: run `.venv/bin/python scripts/parity.py` after touching either side (`tests/test_rust_parity.py` runs it when the binary exists). Specs it was written against: `rust/docs/html2text-spec.md`, `rust/docs/output-contract.md`. Build needs `cmake` (Tesseract is compiled from source); `Cargo.lock` pins `pdf-inspector` to the version inside the anydoc wheel. `scripts/bench_port.py` regenerates `rust/BENCHMARK.md`.

### Benchmark system

`documix benchmark` discovers files in `resources/`, runs every known converter N times (`check_converter_availability(all_converters=True)`), measures timing, computes word similarity between outputs, and writes results to `benchmark/`. The ranking file is informational only; `tests/conftest.py` does not use it.

## Code Style

- **Naming**: snake_case for functions/variables, PascalCase for classes
- **Imports**: group stdlib, third-party, local with blank lines between
- **Line length**: ~80 characters when possible
- **Indentation**: 4 spaces

## Documentation

- Always update `README.md` with new features and changes
- Update help text in argparse when adding new CLI options
- When fixing bugs, address the root cause, not just the symptoms

## Test Patterns

Tests use `unittest.TestCase` classes with pytest as the runner. Common patterns:
- `tempfile.TemporaryDirectory()` for filesystem isolation
- `unittest.mock.patch` to mock external tool availability; `patch('documix.converters.anydoc.anydoc.to_markdown', ...)` to simulate engine outcomes
- Tests live in `tests/test_*.py`, organized by concern (core, engines, parallel, email, conversion, CLI, benchmark, integration)
- `tests/native_*.py` run real external tools and are not collected by default
