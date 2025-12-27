"""Tests for CLI functionality in DocumentCompiler."""

import os
import sys
import tempfile
import unittest
from io import StringIO
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from documix.documix import main


class TestCLI(unittest.TestCase):
    """Test cases for CLI/main function."""

    def test_main_version_flag(self):
        """Test that --version flag displays version and exits."""
        with patch('sys.argv', ['documix', '--version', '/tmp']):
            with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                main()
                output = mock_stdout.getvalue()
                self.assertIn('DocuMix', output)
                self.assertIn('v0.1.0', output)

    def test_main_with_extensions(self):
        """Test -e extensions flag parsing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test file
            test_file = os.path.join(tmpdir, 'test.txt')
            with open(test_file, 'w') as f:
                f.write('Test content')

            output_file = os.path.join(tmpdir, 'output.md')

            with patch('sys.argv', ['documix', tmpdir, '-e', 'txt,md', '-o', output_file]):
                with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                    main()
                    output = mock_stdout.getvalue()
                    # Check that extensions message is printed
                    self.assertIn('.txt', output)

    def test_main_with_exclude(self):
        """Test -x exclude patterns flag parsing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            test_file = os.path.join(tmpdir, 'test.txt')
            with open(test_file, 'w') as f:
                f.write('Test content')

            excluded_file = os.path.join(tmpdir, 'temp_file.txt')
            with open(excluded_file, 'w') as f:
                f.write('Should be excluded')

            output_file = os.path.join(tmpdir, 'output.md')

            with patch('sys.argv', ['documix', tmpdir, '-x', 'temp.*', '-o', output_file]):
                with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                    main()
                    output = mock_stdout.getvalue()
                    # Check that exclusion message is printed
                    self.assertIn('temp.*', output)

    def test_main_standard_format(self):
        """Test --standard-format flag."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test file
            test_file = os.path.join(tmpdir, 'test.txt')
            with open(test_file, 'w') as f:
                f.write('Test content')

            output_file = os.path.join(tmpdir, 'output.md')

            with patch('sys.argv', ['documix', tmpdir, '--standard-format', '-o', output_file]):
                with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                    main()
                    output = mock_stdout.getvalue()
                    # Check that standard format message is printed
                    self.assertIn('standard', output.lower())


if __name__ == '__main__':
    unittest.main()
