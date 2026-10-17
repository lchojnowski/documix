# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Layout

DocuMix is a Rust binary (`documix`) at the repository root. The Python implementation of the same CLI lives in `python/` as the fallback for the legacy converters; it has its own `python/CLAUDE.md`. Both implementations must produce byte-identical output on the default path (anydoc → LiteParse, text/code, ZIP, email).

| Path | What |
| --- | --- |
| `Cargo.toml`, `src/`, `build.rs`, `.cargo/config.toml`, `pgo.sh` | the Rust crate (`documix`); version of record is `[package] version` (ScalVer `1.YYYYMMDD.N`), mirrored into `python/documix/__init__.py` by the version-bump workflow |
| `python/` | Python package `documix` (CLI `documix-py`), its tests (`python/tests`, fixtures included), `setup.py`, `bin/setup` |
| `resources/` | shared sample documents used by both test suites, the parity harness, the benchmark and `pgo.sh` |
| `scripts/parity.py` | runs both CLIs on ~30 cases and diffs the outputs (normalising only date, version and processing-time lines) |
| `scripts/bench_port.py` | Python-vs-Rust benchmark; writes `BENCHMARK.md` |
| `docs/` | `html2text-spec.md` and `output-contract.md`: the specifications the Rust port follows |

## Build & Test Commands

```bash
cargo build --release && cargo test --release      # needs cmake + a C++ toolchain (Tesseract builds from source)
./pgo.sh                                           # profile-guided build (two full LTO builds); use before benchmarking
uv pip install --python .venv/bin/python -e "python/[tables]"   # the Python fallback into the repo venv
cd python && ../.venv/bin/python -m pytest -q      # Python suite; includes tests/test_rust_parity.py when target/release/documix exists
python scripts/parity.py                           # must stay 30/30 after any change on either side
python scripts/bench_port.py --out BENCHMARK.md
```

CI (`.github/workflows/tests.yml`): the Python matrix runs from `python/`; a Rust job builds, runs `cargo test` and the parity harness. The version-bump workflow bumps `Cargo.toml`, `Cargo.lock` and `python/documix/__init__.py` on every push to `main`.

## Rust architecture (`src/`)

| Module | Responsibility |
| --- | --- |
| `cli.rs` | clap mirror of the Python argparse CLI: same flags, validation order and exit codes (2 usage, 1 unknown converter / engine failure, 3 feature only in the Python fallback); logo, `--version`, converter table; worker-process entry (`--internal-ocr-worker`) |
| `compile.rs` | `Compiler`: scan, security check, worker-thread pool pulling files from a shared index, results written strictly in file order while conversion continues, emails on the main thread, `EngineError` removes the partial output |
| `convert.rs` | per-format chains (`run_chain`), `process_file` dispatch, text/code reading with Python's `errors='replace'` + universal-newline semantics, fence rule (`direct_read` only) |
| `engines/anydoc.rs` | primary engine; `ConvertError`/`Io` decline the document, panics are fatal; `--office-require-text-only` (document assets + OOXML relationship scan) |
| `engines/liteparse.rs` | OCR fallback; pool of worker processes (one PDFium per process), in-process for tiny runs, `DOCUMIX_OCR_WORKERS`, office lock for LibreOffice inputs, workers reaped at the end of a compile |
| `archive.rs`, `email/mod.rs`, `email/html2md.rs` | ZIP extraction; `.eml` parsing with `mail-parser` rendered like `email.policy.default`; a port of Python's `html2text` on top of CPython's `html.parser` tokenizer (see `docs/html2text-spec.md`) |
| `scan.rs`, `output.rs`, `textutils.rs`, `config.rs`, `jobs.rs` | `os.walk`-equivalent discovery, the output literals, Python string semantics (`str.split`, `splitext`, `{:,}`, `has_content`), format tables, job heuristics |

Performance choices that must survive refactors: plain worker threads (a rayon `par_iter` nests with pdf-inspector's own rayon pool and starves it), OCR worker processes, fat LTO + `mimalloc` + `target-cpu=native`, PGO via `pgo.sh`, `Cargo.lock` pinning `pdf-inspector` to the version inside the anydoc wheel (output parity).

## Conventions

- Literal output strings are the contract: copy them from `python/documix/output.py` and friends, never paraphrase.
- A behaviour that only the Python side has (legacy converters, `--ocr-*`, `benchmark`) is rejected explicitly with exit code 3 and a message naming `documix-py`; never silently ignored.
- Keep the Python package working: it is the fallback, not dead code. Its conventions (module-call patch targets, thin `DocumentCompiler` delegates, `LEGACY_CONVERTER_CONFIG` in tests) are in `python/CLAUDE.md`.
- Update `README.md`, `python/README.md` and `CHANGELOG.md` with user-visible changes; update `BENCHMARK.md` only through `scripts/bench_port.py`.
