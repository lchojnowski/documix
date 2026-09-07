"""OCR selection is additive and explicit in both library and CLI usage."""

import tempfile
import os
import subprocess
import sys
import unittest
from unittest.mock import patch

from documix.documix import DocumentCompiler, main, print_converter_info
from documix.local_ocr import OcrError


class TestOcrCliContract(unittest.TestCase):
    def test_direct_script_help_remains_available(self):
        script = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                              'documix', 'documix.py')
        result = subprocess.run([sys.executable, script, '--help'],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn('--ocr-languages', result.stdout)

    def test_explicit_ocr_order_and_settings_reach_library(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch('documix.documix.print_converter_info'), \
             patch('documix.documix.DocumentCompiler') as compiler, \
             patch('sys.argv', ['documix', directory, '--pdf-converters',
                                'markitdown,pdftotext,tesseract',
                                '--ocr-languages', 'pol+eng', '--ocr-max-pages',
                                '10', '--ocr-dpi', '200', '--ocr-timeout', '120']):
            main()
        self.assertEqual(
            {'pdf': ['markitdown', 'pdftotext', 'tesseract']},
            compiler.call_args.args[6],
        )
        self.assertEqual(
            {'languages': 'pol+eng', 'max_pages': 10, 'dpi': 200, 'timeout': 120},
            compiler.call_args.kwargs['ocr_config'],
        )

    def test_settings_do_not_silently_enable_ocr(self):
        with patch('sys.argv', ['documix', '.', '--ocr-languages', 'pol']), \
             patch('documix.documix.DocumentCompiler') as compiler:
            with self.assertRaises(SystemExit):
                main()
        compiler.assert_not_called()

    def test_invalid_limits_fail_before_compiler_or_tool_probes(self):
        for flag, value in (('--ocr-max-pages', '101'), ('--ocr-dpi', '201'),
                            ('--ocr-timeout', '0'), ('--ocr-dpi', 'invalid')):
            with self.subTest(flag=flag, value=value), \
                 patch('sys.argv', ['documix', '.', '--pdf-converters',
                                    'tesseract', flag, value]), \
                 patch('documix.documix.DocumentCompiler') as compiler, \
                 patch('documix.documix.print_converter_info') as probes:
                with self.assertRaises(SystemExit) as error:
                    main()
                self.assertEqual(2, error.exception.code)
                compiler.assert_not_called()
                probes.assert_not_called()

    def test_failed_ocr_continues_explicit_converter_order(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch('documix.documix.get_version', return_value='test'):
            compiler = DocumentCompiler(
                directory, directory + '/output.md',
                converter_config={'pdf': ['tesseract', 'pdftotext']},
            )
        with patch('documix.documix.local_ocr.convert_pdf',
                   side_effect=OcrError('page_limit')), \
             patch.object(compiler, '_try_pdf_pdftotext',
                          return_value=('Native text', 'pdftotext')) as native:
            self.assertEqual(('Native text', 'pdftotext'),
                             compiler.convert_pdf_to_text('sample.pdf'))
            native.assert_called_once_with('sample.pdf')

    def test_library_ocr_is_only_called_when_explicitly_selected(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch('documix.documix.get_version', return_value='test'):
            compiler = DocumentCompiler(
                directory, directory + '/output.md',
                converter_config={'pdf': ['pdftotext', 'tesseract']},
                ocr_config={'languages': 'pol+eng'},
            )
        with patch.object(compiler, '_try_pdf_pdftotext',
                          return_value=('', 'pdftotext')), \
             patch('documix.documix.local_ocr.convert_pdf',
                   return_value='Scanned scope') as ocr:
            self.assertEqual(('Scanned scope', 'tesseract'),
                             compiler.convert_pdf_to_text('sample.pdf'))
        self.assertEqual('pol+eng', ocr.call_args.args[1]['languages'])

    def test_default_info_does_not_probe_ocr_tools(self):
        with patch('documix.documix.check_converter_availability',
                   return_value={'pdf': [], 'docx': [], 'rtf': []}), \
             patch('documix.documix.local_ocr.available') as available:
            print_converter_info({})
        available.assert_not_called()
