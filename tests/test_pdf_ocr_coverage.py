"""Explicit OCR must cover mixed pages even when native extraction succeeds."""

import tempfile
import unittest
from unittest.mock import patch

from documix.documix import DocumentCompiler
from documix.local_ocr import OcrCleanupError, OcrError


class TestPdfOcrCoverage(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.source = self.directory.name + '/sample.pdf'
        with open(self.source, 'wb') as source:
            source.write(b'%PDF synthetic source')

    def compiler(self, converters):
        with patch('documix.documix.get_version', return_value='test'):
            return DocumentCompiler(
                self.directory.name, self.directory.name + '/output.md',
                converter_config={'pdf': converters},
            )

    def test_nonempty_native_result_retained_with_complete_ocr_once(self):
        native_text = '  Tender cover\n| Item | Price |\n| A | 1.00 |\n'
        for order in (['pdftotext', 'tesseract'],
                      ['tesseract', 'pdftotext'],
                      ['tesseract', 'pdftotext', 'tesseract']):
            with self.subTest(order=order):
                compiler = self.compiler(order)
                with patch.object(compiler, '_try_pdf_pdftotext',
                                  return_value=(native_text, 'pdftotext')), \
                     patch('documix.documix.local_ocr.convert_pdf',
                           return_value='Tender cover\nSIEM deployment service') as ocr:
                    text, method = compiler.convert_pdf_to_text(self.source)
                self.assertEqual('pdftotext+tesseract', method)
                self.assertTrue(text.startswith(native_text))
                self.assertIn('## Complete-document OCR rendition', text)
                self.assertIn('SIEM deployment service', text)
                ocr.assert_called_once()

    def test_failure_on_any_page_rejects_native_result_in_every_order(self):
        for order in (['pdftotext', 'tesseract'], ['tesseract', 'pdftotext']):
            for code in ('page_limit', 'timeout', 'empty_page', 'output_limit',
                         'tool_failed', 'source_changed'):
                with self.subTest(order=order, code=code):
                    compiler = self.compiler(order)
                    with patch.object(compiler, '_try_pdf_pdftotext',
                                      return_value=('Native cover', 'pdftotext')) as native, \
                         patch('documix.documix.local_ocr.convert_pdf',
                               side_effect=OcrError(code)):
                        text, method = compiler.convert_pdf_to_text(self.source)
                    self.assertEqual('failed', method)
                    self.assertNotIn('Native cover', text)
                    native.assert_not_called()

    def test_combined_output_cap_counts_utf8_and_separator_without_truncation(self):
        compiler = self.compiler(['pdftotext', 'tesseract'])
        with patch.object(compiler, '_try_pdf_pdftotext',
                          return_value=('\u017c' * 50, 'pdftotext')), \
             patch('documix.documix.local_ocr.convert_pdf', return_value='S' * 50), \
             patch('documix.documix.local_ocr.MAX_TEXT_BYTES', 160):
            text, method = compiler.convert_pdf_to_text(self.source)
        self.assertEqual('failed', method)
        self.assertNotIn('\u017c', text)

    def test_native_order_remains_stable_after_successful_mandatory_ocr(self):
        compiler = self.compiler(['markitdown', 'tesseract', 'pdftotext'])
        with patch.object(compiler, '_try_pdf_markitdown',
                          return_value=('Native content', 'markitdown')), \
             patch.object(compiler, '_try_pdf_pdftotext') as later, \
             patch('documix.documix.local_ocr.convert_pdf', return_value='OCR content'):
            text, method = compiler.convert_pdf_to_text(self.source)
        self.assertEqual('markitdown+tesseract', method)
        self.assertIn('OCR content', text)
        later.assert_not_called()

    def test_ocr_only_result_preserved_when_all_native_extractors_empty(self):
        compiler = self.compiler(['pdftotext', 'tesseract'])
        with patch.object(compiler, '_try_pdf_pdftotext', return_value=('\f', 'pdftotext')), \
             patch('documix.documix.local_ocr.convert_pdf', return_value='  OCR text\n'):
            self.assertEqual(('  OCR text\n', 'tesseract'),
                             compiler.convert_pdf_to_text(self.source))

    def test_fatal_ocr_cleanup_cannot_become_native_success(self):
        compiler = self.compiler(['pdftotext', 'tesseract'])
        with patch.object(compiler, '_try_pdf_pdftotext',
                          return_value=('Native text', 'pdftotext')) as native, \
             patch('documix.documix.local_ocr.convert_pdf', side_effect=OcrCleanupError()):
            with self.assertRaises(OcrCleanupError):
                compiler.convert_pdf_to_text(self.source)
        native.assert_not_called()

    def test_no_ocr_selection_keeps_first_native_result_exactly(self):
        compiler = self.compiler(['pdftotext'])
        with patch.object(compiler, '_try_pdf_pdftotext',
                          return_value=('  Original\n', 'pdftotext')), \
             patch('documix.documix.local_ocr.convert_pdf') as ocr:
            self.assertEqual(('  Original\n', 'pdftotext'),
                             compiler.convert_pdf_to_text(self.source))
        ocr.assert_not_called()

    def test_source_change_between_ocr_and_native_extraction_is_rejected(self):
        compiler = self.compiler(['pdftotext', 'tesseract'])

        def native(filepath):
            with open(filepath, 'wb') as source:
                source.write(b'%PDF changed document with additional pages')
            return 'Different document', 'pdftotext'

        with patch.object(compiler, '_try_pdf_pdftotext', side_effect=native), \
             patch('documix.documix.local_ocr.convert_pdf', return_value='Original OCR'):
            text, method = compiler.convert_pdf_to_text(self.source)
        self.assertEqual('failed', method)
        self.assertNotIn('Original OCR', text)
        self.assertNotIn('Different document', text)
