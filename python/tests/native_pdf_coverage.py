"""Required native OCR regression gate: python -m pytest tests/native_pdf_coverage.py.

Requires locally installed pdfinfo, pdftoppm, pdftotext and Tesseract with eng.
Kept separate from the portable mocked unit suite; missing tools fail this gate.
Fixtures contain fabricated text only and require no network or model download.
"""

import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from documix.documix import DocumentCompiler


FIXTURES = Path(__file__).parent / 'fixtures' / 'pdf_coverage'


class NativePdfCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for tool in ('pdfinfo', 'pdftoppm', 'pdftotext', 'tesseract'):
            if not shutil.which(tool):
                raise RuntimeError('Native PDF coverage gate requires ' + tool)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def convert(self, name, converters, max_pages=20):
        source = FIXTURES / name
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        compiler = DocumentCompiler(
            self.directory.name, self.directory.name + '/output.md',
            converter_config={'pdf': converters},
            ocr_config={'languages': 'eng', 'max_pages': max_pages},
        )
        result = compiler.convert_pdf_to_text(str(source))
        self.assertEqual(before, hashlib.sha256(source.read_bytes()).hexdigest())
        return result

    def test_text_page_does_not_hide_scanned_service(self):
        for order in (['markitdown', 'pdftotext', 'tesseract'],
                      ['tesseract', 'pdftotext']):
            with self.subTest(order=order):
                text, method = self.convert('text_then_scan.pdf', order)
                self.assertIn(method, ('markitdown+tesseract', 'pdftotext+tesseract'))
                self.assertIn('Procurement notice', text)
                self.assertIn('SIEM deployment service', text)
                self.assertIn('## Complete-document OCR rendition', text)

    def test_text_header_on_same_page_does_not_hide_scanned_service(self):
        text, method = self.convert('header_and_scan.pdf', ['pdftotext', 'tesseract'])
        self.assertEqual('pdftotext+tesseract', method)
        self.assertIn('Procurement notice', text)
        self.assertIn('SIEM deployment service', text)

    def test_page_budget_failure_cannot_return_native_cover_in_any_order(self):
        for order in (['markitdown', 'pdftotext', 'tesseract'],
                      ['tesseract', 'pdftotext']):
            with self.subTest(order=order):
                text, method = self.convert('text_then_scan.pdf', order, max_pages=1)
                self.assertEqual('failed', method)
                self.assertTrue(text.startswith('[Failed to convert PDF file:'))
                self.assertNotIn('Procurement notice', text)

    def test_fully_text_pdf_preserves_exact_native_layout(self):
        source = FIXTURES / 'native_text.pdf'
        native = subprocess.run(
            ['pdftotext', '-layout', str(source), '-'], check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10,
        ).stdout.decode('utf-8')
        self.assertIn('1,234.56', native)
        self.assertIn('23%', native)
        plain, plain_method = self.convert('native_text.pdf', ['pdftotext'])
        self.assertEqual(('pdftotext', native), (plain_method, plain))
        enriched, method = self.convert('native_text.pdf', ['pdftotext', 'tesseract'])
        self.assertEqual('pdftotext+tesseract', method)
        self.assertTrue(enriched.startswith(native))
        self.assertEqual(native, enriched.split('\n\n---\n\n## Complete-document OCR rendition\n\n')[0])

    def test_compiled_document_reports_combined_method_and_scanned_service(self):
        source = Path(self.directory.name) / 'sample.pdf'
        shutil.copyfile(FIXTURES / 'text_then_scan.pdf', source)
        before = source.read_bytes()
        output = Path(self.directory.name) / 'compiled.md'
        compiler = DocumentCompiler(
            self.directory.name, str(output),
            converter_config={'pdf': ['pdftotext', 'tesseract']},
        )
        compiler.compile()
        result = output.read_text(encoding='utf-8')
        self.assertIn('(converted with pdftotext+tesseract)', result)
        self.assertIn('SIEM deployment service', result)
        self.assertEqual(before, source.read_bytes())
