# Python vs Rust port benchmark

Hardware: arm64 14 cores, macOS-26.6.2-arm64-arm-64bit-Mach-O. Engines: firecrawl-anydoc / anydoc crate 0.2.4 (pdf-inspector 1.14.2), liteparse 2.16.0. Corpora built from `resources/` and `python/tests/fixtures/` (medium: 220 files, large: 1980 files with 10% scanned PDFs). Medians over 20/5/2 repetitions; peak RSS is the whole process tree sampled every 50 ms (so Python's LiteParse OCR worker processes are included).

| Scenario | Case | Python median | Rust median | Speed-up | Python CPU | Rust CPU | Python RSS | Rust RSS |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cold start | docx | 0.065 s | 0.008 s | 8.2x | 0.05 s | 0.00 s | 33 MB | 11 MB |
| cold start | doc | 0.062 s | 0.008 s | 7.5x | 0.05 s | 0.00 s | 36 MB | 14 MB |
| cold start | pdf 22 pages | 0.108 s | 0.038 s | 2.9x | 0.10 s | 0.04 s | 46 MB | 31 MB |
| cold start | scanned pdf (OCR) | 0.395 s | 0.157 s | 2.5x | 0.90 s | 0.25 s | 590 MB | 208 MB |
| cold start | markdown | 0.064 s | 0.009 s | 7.2x | 0.05 s | 0.00 s | 31 MB | 9 MB |
| cold start | --version | 0.062 s | 0.007 s | 9.1x | 0.00 s | 0.00 s | 0 MB | 0 MB |
| 220 files | -j 1 | 4.389 s | 3.733 s | 1.2x | 6.56 s | 5.92 s | 325 MB | 351 MB |
| 220 files | auto jobs | 1.069 s | 0.780 s | 1.4x | 9.34 s | 7.98 s | 3309 MB | 3184 MB |
| 1980 files | auto jobs | 6.155 s | 5.331 s | 1.2x | 70.53 s | 62.99 s | 3805 MB | 3940 MB |
| 1980 files | -j 1 | 38.534 s | 33.597 s | 1.1x | 58.29 s | 53.48 s | 349 MB | 415 MB |

Medium corpus output identical between implementations: True

## What was optimised, step by step

Measured on the 1980-file corpus without the scans (`-x 'scan_.*'`, anydoc only) and on the 180 scans alone, 14 jobs unless noted. CPU is user+sys of the whole run.

| Step | no scans, wall | no scans, CPU | `-j 1`, wall | 180 scans, wall |
| --- | --- | --- | --- | --- |
| first port (rayon `par_iter`, system malloc, in-process OCR) | 5.98 s | 22.0 s | 17.3 s | 5.08 s |
| plain worker threads instead of a rayon iterator (pdf-inspector uses rayon internally; nesting starved both pools) | 1.86 s | 22.1 s | 17.3 s | 5.08 s |
| OCR in a pool of worker processes (one PDFium instance each, like the Python version) | – | – | – | 4.12 s |
| fat LTO + one codegen unit + `mimalloc` as the global allocator | 1.42 s | 16.5 s | 13.9 s | – |
| `target-cpu=native`, output streamed while converting, in-process OCR for 1–2 documents | 1.40 s | 16.5 s | 14.5 s | 4.05 s (single scan: 182 → 164 ms) |
| profile-guided optimisation (`pgo.sh`) | 1.15 s | 13.1 s | 11.2 s | 4.05 s |
| **Python, same corpus** | **1.81 s** | **21.1 s** | **17.3 s** | **4.10 s** |

Thread-count sweeps (`-j 8…20`) and OCR worker counts (8…16) change results by a few percent at most; the defaults (jobs = cores, OCR workers = jobs) stay.

## Reading the numbers

- **Startup and single documents: 7–9x.** A Word or Markdown file takes 8 ms instead of ~65 ms, a 22-page text PDF 38 ms instead of 108 ms, a scanned page 157 ms instead of 395 ms. Python's interpreter start plus imports (~55 ms) dominate every short invocation.
- **Bulk throughput: 1.1–1.4x.** The conversion work is the same anydoc and LiteParse code in both, so the gain comes from what a locally built binary can do and a generic wheel cannot: a scalable allocator, fat LTO, CPU-specific code generation and PGO cut the anydoc CPU time by 40%. OCR throughput is identical (same Tesseract, both sides use a worker-process pool); on the scan-heavy corpus that caps the end-to-end gain at ~1.2x.
- **Memory:** a quarter of Python's for single documents (worker pools excluded); comparable on OCR-heavy folders, where both implementations keep one Tesseract instance per worker process.
- Output of every run was byte-identical between implementations and between serial and parallel runs.

## What a switch would cost

- The port covers only the default path: anydoc, LiteParse, text/code, ZIP, email. MinerU, pdfplumber, PaddleOCR, the Tesseract profile (`--ocr-*`), pandoc/LibreOffice/unrtf/striprtf/docx2txt/ebook-convert, the sandboxed MarkItDown Office parser and `documix benchmark` are not ported (they exit with code 3). The Python library API (`DocumentCompiler`) disappears.
- Building needs a C++ toolchain and `cmake` (Tesseract and Leptonica from source), and the fast numbers need the PGO build (`pgo.sh`, two full LTO builds) on the target CPU family; a generic binary is the "LTO + mimalloc" row above.
- `src/email/html2md.rs` is a faithful but bespoke reimplementation of Python's `html2text` and `html.parser`; it passes the harness corpus, but real-world HTML mail will keep finding corners that need the Python behaviour copied.

## Suggested decision rule

Switch if startup latency, memory per process or single-binary distribution matter (per-file invocations from other tools, serverless, constrained machines), or if 10–40% on bulk folders is worth losing the legacy converters, the library API and the Office/OCR safety profiles. Keep Python if those features matter more than the bulk gain: the engines are already native there.
