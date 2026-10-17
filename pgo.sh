#!/usr/bin/env bash
# Profile-guided optimisation build of documix.
#
# 1. builds an instrumented binary into a scratch target dir,
# 2. runs it over a corpus generated from resources/ and python/tests/fixtures/,
# 3. merges the profiles and rebuilds target/release/documix with them.
#
# Needs: rustup component add llvm-tools-preview. Takes two full LTO builds.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$HERE"
SCRATCH="${PGO_DIR:-$(mktemp -d -t documix-pgo)}"
PROFDATA="$(rustc --print sysroot)/lib/rustlib/$(rustc -vV | sed -n 's/^host: //p')/bin/llvm-profdata"
[ -x "$PROFDATA" ] || { echo "llvm-profdata not found; run: rustup component add llvm-tools-preview" >&2; exit 1; }
NATIVE="-C target-cpu=native"

echo "[pgo] instrumented build -> $SCRATCH/target"
mkdir -p "$SCRATCH/data"
(cd "$HERE" && RUSTFLAGS="$NATIVE -C profile-generate=$SCRATCH/data" cargo build --release --target-dir "$SCRATCH/target")
BIN="$SCRATCH/target/release/documix"

echo "[pgo] building the training corpus"
CORPUS="$SCRATCH/corpus"
mkdir -p "$CORPUS/pdf" "$CORPUS/office" "$CORPUS/scans" "$CORPUS/text"
for i in $(seq -w 1 30); do
  cp "$REPO/resources/one_megabyte/example_pdf.pdf" "$CORPUS/pdf/big_$i.pdf"
  cp "$REPO/resources/invoice_with_tables/digitalocean_invoice_with_tables.pdf" "$CORPUS/pdf/invoice_$i.pdf"
  cp "$REPO/resources/one_megabyte/example_1mb.doc" "$CORPUS/office/doc_$i.doc"
  cp "$REPO/resources/sample_test.docx" "$CORPUS/office/docx_$i.docx"
  cp "$REPO/python/tests/fixtures/office_documents/scope.xlsx" "$CORPUS/office/sheet_$i.xlsx"
  cp "$REPO/python/tests/fixtures/office_documents/scope.pptx" "$CORPUS/office/deck_$i.pptx"
  printf '# Note %s\n\n%s\n' "$i" "$(yes 'Lorem ipsum dolor sit amet.' | head -200 | tr '\n' ' ')" > "$CORPUS/text/note_$i.md"
done
for i in $(seq -w 1 20); do cp "$REPO/python/tests/fixtures/pdf_coverage/text_then_scan.pdf" "$CORPUS/scans/scan_$i.pdf"; done

echo "[pgo] profiling runs"
"$BIN" "$CORPUS" -r -o "$SCRATCH/out1.md" >/dev/null 2>&1
"$BIN" "$CORPUS" -r -j 1 -o "$SCRATCH/out2.md" >/dev/null 2>&1
"$BIN" "$CORPUS/scans" -o "$SCRATCH/out3.md" >/dev/null 2>&1
DOCUMIX_OCR_WORKERS=0 "$BIN" "$CORPUS/scans" -j 4 -o "$SCRATCH/out4.md" >/dev/null 2>&1
"$BIN" "$REPO/resources" -r --office-require-text-only -o "$SCRATCH/out5.md" >/dev/null 2>&1
"$BIN" "$REPO/resources/sample_test.docx" -o "$SCRATCH/out6.md" >/dev/null 2>&1

echo "[pgo] merging $(ls "$SCRATCH/data" | wc -l | tr -d ' ') profiles"
"$PROFDATA" merge -o "$SCRATCH/merged.profdata" "$SCRATCH"/data/*.profraw

echo "[pgo] optimised build -> $HERE/target/release/documix"
(cd "$HERE" && RUSTFLAGS="$NATIVE -C profile-use=$SCRATCH/merged.profdata -C llvm-args=-pgo-warn-missing-function" cargo build --release)
echo "[pgo] done (profiles in $SCRATCH)"
