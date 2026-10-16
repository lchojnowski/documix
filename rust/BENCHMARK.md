# Python vs Rust port benchmark

Hardware: arm64 14 cores, macOS-26.6.2-arm64-arm-64bit-Mach-O. Engines: firecrawl-anydoc / anydoc crate 0.2.4 (pdf-inspector 1.14.2), liteparse 2.16.0. Corpora built from `resources/` and `tests/fixtures/` (medium: 220 files, large: 1980 files with 10% scanned PDFs). Medians over 20/5/2 repetitions; peak RSS is the whole process tree sampled every 50 ms (so Python's LiteParse OCR worker processes are included).

| Scenario | Case | Python median | Rust median | Speed-up | Python CPU | Rust CPU | Python RSS | Rust RSS |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cold start | docx | 0.065 s | 0.008 s | 7.6x | 0.05 s | 0.00 s | 33 MB | 12 MB |
| cold start | doc | 0.063 s | 0.009 s | 6.8x | 0.05 s | 0.00 s | 36 MB | 15 MB |
| cold start | pdf 22 pages | 0.109 s | 0.054 s | 2.0x | 0.10 s | 0.05 s | 46 MB | 24 MB |
| cold start | scanned pdf (OCR) | 0.407 s | 0.170 s | 2.4x | 0.91 s | 0.27 s | 592 MB | 207 MB |
| cold start | markdown | 0.063 s | 0.009 s | 7.4x | 0.05 s | 0.00 s | 32 MB | 10 MB |
| cold start | --version | 0.060 s | 0.007 s | 8.2x | 0.00 s | 0.00 s | 0 MB | 0 MB |
| 220 files | -j 1 | 4.410 s | 4.447 s | 1.0x | 6.60 s | 6.64 s | 325 MB | 271 MB |
| 220 files | auto jobs | 1.078 s | 0.882 s | 1.2x | 9.30 s | 8.86 s | 3351 MB | 782 MB |
| 1980 files | auto jobs | 6.255 s | 6.937 s | 0.9x | 70.62 s | 76.79 s | 3833 MB | 953 MB |
| 1980 files | -j 1 | 38.357 s | 39.381 s | 1.0x | 57.98 s | 59.52 s | 343 MB | 353 MB |

Medium corpus output identical between implementations: True

## Reading the numbers

- **Startup and single documents: Rust wins clearly.** A small Word/Markdown file or `--version` takes ~8 ms instead of ~63 ms (7–8x), a 22-page text PDF 54 ms instead of 109 ms (2x), a scanned page 170 ms instead of 407 ms (2.4x) with a quarter of the memory. Python's interpreter start plus imports (~55 ms) dominate every short invocation.
- **Serial throughput (`-j 1`) is identical.** The conversion work is the same anydoc and LiteParse Rust code in both implementations; the Python layer adds under 2% at this point.
- **Parallel throughput is a wash.** On 220 files Rust is 1.2x faster; on 1980 files with 10% scanned PDFs it is 10% slower, because its OCR runs in-process and serialises on PDFium's global lock, while the Python version drives a pool of LiteParse worker processes. The Rust process tree uses about a quarter of the memory of the Python one (0.95 GB vs 3.8 GB at 14 jobs; the Python figure includes its OCR workers).
- Output of every parallel run was byte-identical between implementations (and to the serial run).

## What a switch would cost

- The port covers only the default path: anydoc, LiteParse, text/code, ZIP, email. MinerU, pdfplumber, PaddleOCR, the Tesseract profile (`--ocr-*`), pandoc/LibreOffice/unrtf/striprtf/docx2txt/ebook-convert, the sandboxed MarkItDown Office parser and `documix benchmark` are not ported (they exit with code 3). The Python library API (`DocumentCompiler`) disappears.
- Building needs a C++ toolchain and `cmake`; Tesseract and Leptonica compile from source (several minutes the first time). Distribution becomes a single ~30 MB binary.
- `src/email/html2md.rs` is a faithful but bespoke reimplementation of Python's `html2text` and `html.parser`; it passes the harness corpus, but real-world HTML mail will keep finding corners that need the Python behaviour copied.
- Matching Python's OCR throughput on large scan-heavy folders would require an OCR worker-process pool in the Rust port as well.

## Suggested decision rule

Switch if startup latency, memory per process or single-binary distribution matter (per-file invocations from other tools, serverless, constrained machines). Keep Python if bulk throughput on big folders is the goal: the engines are already native there, and the legacy converters, the library API and the Office/OCR safety profiles only exist on the Python side.
