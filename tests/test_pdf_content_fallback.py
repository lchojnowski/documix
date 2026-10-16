"""PDF fallback must require extracted content, not merely a zero exit code."""

import tempfile
import unittest
from unittest.mock import patch

from documix.documix import CONVERTER_DEFAULTS, DocumentCompiler


class TestPDFContentFallback(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        with patch('documix.version.get_version', return_value='test'):
            self.compiler = DocumentCompiler(
                self.directory.name, self.directory.name + '/output.md',
                converter_config={'pdf': ['markitdown', 'pdftotext']},
            )

    def test_empty_first_converter_continues_in_explicit_order(self):
        for empty in ('', ' \n\t\f', '\u00a0\u2003', '\ufeff\u200b\x00'):
            with self.subTest(empty=repr(empty)):
                with patch.object(self.compiler, '_try_pdf_markitdown',
                                  return_value=(empty, 'markitdown')) as first, \
                     patch.object(self.compiler, '_try_pdf_pdftotext',
                                  return_value=('Real scope', 'pdftotext')) as second:
                    self.assertEqual(
                        ('Real scope', 'pdftotext'),
                        self.compiler.convert_pdf_to_text('sample.pdf'),
                    )
                    first.assert_called_once_with('sample.pdf')
                    second.assert_called_once_with('sample.pdf')

    def test_all_empty_keeps_existing_failure_contract(self):
        with patch.object(self.compiler, '_try_pdf_markitdown',
                          return_value=('', 'markitdown')), \
             patch.object(self.compiler, '_try_pdf_pdftotext',
                          return_value=('\f\n', 'pdftotext')):
            text, method = self.compiler.convert_pdf_to_text('sample.pdf')
        self.assertEqual('failed', method)
        self.assertEqual('[Failed to convert PDF file: sample.pdf]', text)

    def test_nonempty_first_result_is_preserved_without_extra_converter(self):
        for content in ('  Actual scope\n', '[Failed examples] are documented.'):
            with self.subTest(content=content):
                with patch.object(self.compiler, '_try_pdf_markitdown',
                                  return_value=(content, 'markitdown')), \
                     patch.object(self.compiler, '_try_pdf_pdftotext') as later:
                    self.assertEqual(
                        (content, 'markitdown'),
                        self.compiler.convert_pdf_to_text('sample.pdf'),
                    )
                    later.assert_not_called()

    def test_default_order_remains_unchanged(self):
        self.assertEqual(['anydoc', 'liteparse'], CONVERTER_DEFAULTS['pdf'])
