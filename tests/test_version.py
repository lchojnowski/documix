"""Tests for version management and converter display."""

import os
import re
import sys
import unittest
from io import StringIO
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import documix
from documix.documix import (
    get_version,
    print_converter_info,
    DocumentCompiler,
    CONVERTER_DEFAULTS,
)


class TestVersion(unittest.TestCase):
    """Test cases for version management."""

    def test_version_from_init(self):
        """__version__ matches MAJOR.DATE.PATCH pattern."""
        self.assertRegex(documix.__version__, r'^\d+\.\d+\.\d+$')

    def test_compiler_version_uses_init(self):
        """DocumentCompiler.version contains __version__ (not a stale hardcoded value)."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, 'out.md')
            compiler = DocumentCompiler(tmpdir, output)
            self.assertIn(documix.__version__, compiler.version)

    def test_get_version_in_git_repo(self):
        """get_version() returns dev string with branch name when in a git repo."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = 'feature-branch\n'
        with patch('documix.documix.subprocess.run', return_value=mock_result):
            version = get_version()
            self.assertIn('dev', version)
            self.assertIn('feature-branch', version)
            self.assertIn(documix.__version__, version)

    def test_get_version_no_git(self):
        """get_version() returns plain __version__ when git is not available."""
        with patch('documix.documix.subprocess.run', side_effect=FileNotFoundError):
            version = get_version()
            self.assertEqual(version, documix.__version__)

    def test_get_version_detached_head(self):
        """get_version() returns plain __version__ on detached HEAD."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = 'HEAD\n'
        with patch('documix.documix.subprocess.run', return_value=mock_result):
            version = get_version()
            self.assertEqual(version, documix.__version__)

    def test_get_version_git_failure(self):
        """get_version() returns plain __version__ when git command fails."""
        mock_result = MagicMock()
        mock_result.returncode = 128
        with patch('documix.documix.subprocess.run', return_value=mock_result):
            version = get_version()
            self.assertEqual(version, documix.__version__)

    def test_version_flag_output(self):
        """--version prints version and converter info."""
        from documix.documix import main
        with patch('sys.argv', ['documix', '--version', '/tmp']):
            with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                main()
                output = mock_stdout.getvalue()
                self.assertIn(documix.__version__, output)
                self.assertIn('DocuMix', output)
                self.assertIn('Converter Configuration', output)

    def test_version_flag_shows_converters(self):
        """--version displays PDF, DOCX, and RTF converter availability."""
        from documix.documix import main
        with patch('documix.documix.check_converter_availability',
                   return_value={'pdf': ['pdfplumber'], 'docx': ['pandoc'], 'rtf': ['pandoc']}):
            with patch('sys.argv', ['documix', '--version', '/tmp']):
                with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                    main()
                    output = mock_stdout.getvalue()
                    self.assertIn('PDF', output)
                    self.assertIn('DOCX', output)
                    self.assertIn('RTF', output)


class TestConverterInfo(unittest.TestCase):
    """Test cases for converter display."""

    def test_print_converter_info_default(self):
        """Default config prints all three formats."""
        with patch('documix.documix.check_converter_availability',
                   return_value={'pdf': ['pdfplumber'], 'docx': ['pandoc'], 'rtf': ['pandoc']}):
            with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                print_converter_info({})
                output = mock_stdout.getvalue()
                self.assertIn('PDF', output)
                self.assertIn('DOCX', output)
                self.assertIn('RTF', output)

    def test_print_converter_info_custom(self):
        """Custom config shows configured converters."""
        with patch('documix.documix.check_converter_availability',
                   return_value={'pdf': ['pdfplumber', 'pdftotext'], 'docx': ['pandoc'], 'rtf': ['pandoc']}):
            with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                print_converter_info({'pdf': ['pdfplumber', 'pdftotext']})
                output = mock_stdout.getvalue()
                self.assertIn('pdfplumber', output)
                self.assertIn('pdftotext', output)

    def test_print_converter_info_missing(self):
        """Unavailable converters shown as missing."""
        with patch('documix.documix.check_converter_availability',
                   return_value={'pdf': [], 'docx': ['docx2txt'], 'rtf': []}):
            with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                print_converter_info({})
                output = mock_stdout.getvalue()
                # PDF has no available converters
                self.assertIn('none available', output)
                # Missing converters should be listed
                self.assertIn('missing', output)

    def test_print_converter_info_partial(self):
        """Some configured converters available, some not."""
        with patch('documix.documix.check_converter_availability',
                   return_value={'pdf': ['pdfplumber'], 'docx': ['pandoc'], 'rtf': ['pandoc']}):
            with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                print_converter_info({'pdf': ['pdfplumber', 'mineru']})
                output = mock_stdout.getvalue()
                self.assertIn('pdfplumber', output)
                self.assertIn('missing', output)
                self.assertIn('mineru', output)


if __name__ == '__main__':
    unittest.main()
