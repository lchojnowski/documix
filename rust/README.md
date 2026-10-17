# documix-rs — Rust port of the DocuMix default path (experimental)

A standalone binary that reproduces the Python CLI byte for byte on the
default conversion path: anydoc first, LiteParse (local OCR) second, plain
text/code files, ZIP archives and `.eml` messages, both output formats, the
same flags and exit codes. It exists to answer one question with numbers:
how much faster is a Rust implementation than the Python one? See
[BENCHMARK.md](BENCHMARK.md) for the measurements.

## Build

Prerequisites: Rust 1.88+ (`rustup`), a C++ toolchain and `cmake` — the
`liteparse` crate compiles Tesseract and Leptonica from source for its
bundled OCR (`brew install cmake` on macOS; the first build takes several
minutes, later builds are incremental).

```bash
cd rust
cargo build --release                       # fat LTO, mimalloc, target-cpu=native
./target/release/documix-rs ../resources -r -o /tmp/out.md

rustup component add llvm-tools-preview
./pgo.sh                                    # profile-guided build: ~20% less CPU again
```

The release profile uses fat LTO and a single codegen unit, `mimalloc`
replaces the system allocator, and `.cargo/config.toml` targets the CPU of
the build machine (the binary is not portable to older CPUs; remove the
flag for a generic build). `pgo.sh` runs an instrumented build over a
corpus generated from `resources/` and `tests/fixtures/`, then rebuilds with
the merged profile. These three steps are where the port gains over the
Python wheels, which have to ship generic, non-PGO code.

OCR (LiteParse) runs in a pool of worker processes — this same binary with
`--internal-ocr-worker` — because PDFium is serialised behind a global lock
inside one process. The pool size follows `-j`; `DOCUMIX_OCR_WORKERS=N`
overrides it and `0` parses in-process (what single-document runs do
anyway, since spawning a worker costs more than it saves there).

`Cargo.lock` pins `pdf-inspector` to 1.14.2, the version embedded in the
`firecrawl-anydoc` 0.2.4 wheel, so PDF output matches the Python engine
exactly. `build.rs` reads the version from `../documix/__init__.py`.

## What is ported

| Area | Status |
| --- | --- |
| anydoc / LiteParse chains for pdf, docx, doc, rtf, epub, office | identical output |
| `--office-require-text-only` (document assets + OOXML relationship scan) | identical |
| text/code files (UTF-8 with replacement, universal newlines) | identical |
| ZIP archives (nested, unsupported members, corrupt archives) | identical (method list sorted; Python's own order is hash-randomised) |
| `.eml` single-email report and standard mode, attachments inline or from `attachments/`, HTML bodies | identical on the harness corpus (`src/email/html2md.rs` ports html2text 2025.4.15 and CPython's `html.parser`) |
| parallel conversion (`-j`, `DOCUMIX_JOBS`, deterministic order) | same semantics, plain worker threads |
| engine failure policy (exit 1, partial output removed) | same |
| legacy converters (`mineru`, `pdfplumber`, `pandoc`, `soffice`, `tesseract`, …), `--ocr-*` with tesseract, `documix benchmark` | **not ported**: rejected with exit code 3 and a clear message |
| Python library API (`DocumentCompiler`) | not applicable |

## Verification

```bash
.venv/bin/python scripts/parity.py        # Python vs Rust on ~30 cases, byte-for-byte after normalising dates
.venv/bin/python -m pytest tests/test_rust_parity.py
.venv/bin/python scripts/bench_port.py --out rust/BENCHMARK.md
cd rust && cargo test --release
```

The parity harness normalises only the compilation date, the version line,
the email processing time and the order of the `zip_extract+...` method
list. `docs/html2text-spec.md` and `docs/output-contract.md` are the
specifications the port was written against.
