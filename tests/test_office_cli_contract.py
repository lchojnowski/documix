"""Office media completeness is an explicit shared library/CLI policy."""

import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from documix.documix import DocumentCompiler, main
from documix.office_documents import OfficeError


class TestOfficeCliContract(unittest.TestCase):
    def test_invalid_library_policy_fails_before_any_probe(self):
        for invalid in (None, 0, 1, 'true', [], {}):
            with self.subTest(invalid=invalid), \
                 patch('documix.documix.get_version') as version:
                with self.assertRaisesRegex(ValueError, 'invalid_office_configuration'):
                    DocumentCompiler('.', 'output.md', office_require_text_only=invalid)
                version.assert_not_called()

    def test_cli_flag_reaches_library_without_enabling_pdf_ocr(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch('sys.argv', ['documix', directory, '--office-require-text-only']), \
             patch('documix.documix.print_converter_info'), \
             patch('documix.documix.DocumentCompiler') as compiler:
            main()
        self.assertEqual({'office_require_text_only': True}, compiler.call_args.kwargs)
        self.assertEqual({}, compiler.call_args.args[6])

    def test_default_cli_does_not_enable_strict_policy(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch('sys.argv', ['documix', directory]), \
             patch('documix.documix.print_converter_info'), \
             patch('documix.documix.DocumentCompiler') as compiler:
            main()
        self.assertEqual({}, compiler.call_args.kwargs)

    def test_strict_library_policy_reaches_office_core_and_preserves_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            compiler = DocumentCompiler(
                directory, directory + '/output.md', office_require_text_only=True,
            )
            with patch('documix.documix.office_documents.convert',
                       side_effect=OfficeError('unassessed_media')) as convert:
                text, method = compiler.process_file(directory + '/scope.pptx')
            convert.assert_called_once_with(directory + '/scope.pptx', require_text_only=True)
            self.assertEqual('failed', method)
            self.assertEqual('[Failed to convert PPTX file: unassessed_media]', text)

    def test_direct_script_help_describes_opt_in_policy(self):
        script = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                              'documix', 'documix.py')
        result = subprocess.run([sys.executable, script, '--help'],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=10, universal_newlines=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn('--office-require-text-only', result.stdout)
