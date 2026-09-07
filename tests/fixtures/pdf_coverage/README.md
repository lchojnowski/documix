These small PDF fixtures contain fabricated procurement text only.

- `text_then_scan.pdf`: a native text cover and a second page consisting only of
  a raster image containing “SIEM deployment service”.
- `header_and_scan.pdf`: a native text heading and that raster service text on
  the same page. Nonempty per-page native text is insufficient to detect it.
- `native_text.pdf`: selectable text with amounts, percentages and spacing used
  to verify the original native extraction is retained verbatim.

The PDFs were generated locally with ReportLab and a rendered test image. Tests
do not require ReportLab or Pillow: they use the checked-in PDFs and installed
Poppler/Tesseract tools. Run the native gate explicitly; it fails if required
tools or the English language pack are missing:

```sh
python -m pytest tests/native_pdf_coverage.py
```
