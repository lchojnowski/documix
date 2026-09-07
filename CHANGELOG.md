# Changelog

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
