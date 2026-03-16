# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Test Commands

```bash
# Install dev dependencies (all extras)
pip install -e ".[pdf,tables,paddleocr]"

# Install macOS external tools (pandoc, poppler, calibre, libreoffice, unrtf, uv)
bin/setup

# Run all tests
python -m pytest

# Run a single test
python -m pytest tests/test_documix.py::TestDocuMix::test_collect_files -v

# Run tests with coverage
python -m pytest --cov=documix
```

No linter or formatter is configured. No CI beyond GitHub Actions running pytest on Python 3.8–3.12.

## Architecture

### Single-module design

All core logic lives in `documix/documix.py` (~2100 lines). There is no modular package structure — the single file contains:
- `EmailProcessor` class — .eml parsing, attachment extraction, metadata formatting
- `DocumentCompiler` class — main orchestrator for file discovery, conversion, and output generation
- `benchmark_main()` — benchmark subcommand entry point
- `main()` — CLI entry point (registered as `documix` console script in setup.py)

### Converter system

Converters follow a **first-success fallback chain** pattern:

1. Each format (PDF, DOCX, RTF) has a default ordered list in `CONVERTER_DEFAULTS`
2. Users can override order via `--pdf-converters`, `--docx-converters`, `--rtf-converters`
3. Each converter is a private method named `_try_<format>_<tool>()` dispatched via a dict
4. All converters return `(text, method_name)` — text starts with `[Failed` on error
5. `convert_<format>_to_text()` iterates the chain and returns the first success

External tools (pandoc, mineru, pdftotext, soffice, etc.) are invoked via `subprocess.run()`. Availability is checked via `shutil.which()` or `subprocess.run()` with version flags, cached in private attributes (`_uvx_available`, `_mineru_available`, etc.).

**License isolation**: AGPL tools (MinerU) and heavy ML tools (PaddleOCR) are invoked only via subprocess to keep the main package MIT-licensed.

### Output modes

`detect_processing_mode()` selects the output format:
- `'single_email'` — dedicated email analysis format with authentication details
- `'standard'` — Repomix-like format with directory tree, file contents in fenced blocks

### Benchmark system

`documix benchmark` discovers files in `resources/`, runs each available converter N times, measures timing, computes word similarity between outputs, and writes results to `benchmark/`. The `conftest.py` fixture reads `benchmark/converter_ranking.json` to select the fastest converter for test runs.

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
- `unittest.mock.patch` to mock external tool availability
- Tests live in `tests/test_*.py`, organized by concern (core, email, conversion, CLI, benchmark, integration)
