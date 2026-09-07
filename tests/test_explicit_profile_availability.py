"""Explicit converter profiles must not start unrelated tool probes."""

import tempfile
import unittest
from unittest.mock import patch

from documix.documix import check_converter_availability, main, print_converter_info


class TestExplicitProfileAvailability(unittest.TestCase):
    def test_explicit_pdf_profile_does_not_probe_uvx_or_other_pdf_tools(self):
        with patch('documix.documix.subprocess.run',
                   side_effect=PermissionError('unselected executable denied')) as run, \
             patch('documix.documix.shutil.which', return_value='/local/tool') as which, \
             patch('documix.documix.local_ocr.available') as ocr, \
             patch('builtins.print'):
            print_converter_info({'pdf': ['markitdown', 'pdftotext']})
        run.assert_not_called()
        ocr.assert_not_called()
        checked = [call.args[0] for call in which.call_args_list]
        self.assertIn('markitdown', checked)
        self.assertIn('pdftotext', checked)
        self.assertNotIn('paddleocr', checked)
        self.assertNotIn('mineru', checked)

    def test_each_explicit_format_limits_its_own_availability_checks(self):
        with patch('documix.documix.subprocess.run') as run, \
             patch('documix.documix.shutil.which', return_value='/local/pdftotext') as which, \
             patch('documix.documix.DOCX2TXT_AVAILABLE', True):
            available = check_converter_availability({
                'pdf': ['pdftotext'], 'docx': ['docx2txt'], 'rtf': [],
            })
        self.assertEqual({'pdf': ['pdftotext'], 'docx': ['docx2txt'], 'rtf': []},
                         available)
        which.assert_called_once_with('pdftotext')
        run.assert_not_called()

    def test_cli_doc_profile_survives_denied_unselected_uvx(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch('documix.documix.subprocess.run', side_effect=PermissionError) as run, \
             patch('documix.documix.shutil.which', return_value='/local/tool'), \
             patch('documix.documix.DocumentCompiler') as compiler, \
             patch('builtins.print'), \
             patch('sys.argv', ['documix', directory, '-e', 'doc',
                                '--pdf-converters', 'markitdown,pdftotext']):
            main()
        run.assert_not_called()
        compiler.assert_called_once()

    def test_default_availability_still_probes_uvx_and_handles_denied_execution(self):
        with patch('documix.documix.subprocess.run', side_effect=PermissionError) as run:
            available = check_converter_availability()
        self.assertNotIn('markitdown-uvx', available['pdf'])
        self.assertEqual(['uvx', '--version'], run.call_args.args[0])

    def test_unexpected_probe_failure_is_not_silenced(self):
        with patch('documix.documix.subprocess.run', side_effect=RuntimeError('fatal')):
            with self.assertRaises(RuntimeError):
                check_converter_availability()
