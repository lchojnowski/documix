import os
import sys
import unittest
import tempfile
import shutil
import subprocess
from unittest.mock import patch, MagicMock

# Add parent directory to sys.path to import documix
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from documix.documix import DocumentCompiler


class TestDocConversion(unittest.TestCase):
    """Tests for document conversion functionality."""

    def setUp(self):
        """Set up test fixtures."""
        # Create temporary directory for output
        self.temp_dir = tempfile.mkdtemp()
        self.output_file = os.path.join(self.temp_dir, 'output.md')
        
        # Path to sample doc file
        self.doc_file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 
                                             '..', 'resources', 'one_megabyte', 'example_1mb.doc'))
        
        # Create a DocumentCompiler instance
        self.compiler = DocumentCompiler(
            source_path=os.path.dirname(self.doc_file_path),
            output_file=self.output_file,
            recursive=False
        )

    def tearDown(self):
        """Tear down test fixtures."""
        # Clean up temporary directory
        shutil.rmtree(self.temp_dir)

    def test_doc_exists(self):
        """Test that the sample doc file exists."""
        self.assertTrue(os.path.exists(self.doc_file_path), 
                        f"Sample DOC file not found at {self.doc_file_path}")

    def test_doc_to_text_conversion(self):
        """Test conversion of DOC to text."""
        # Skip if LibreOffice is not installed
        try:
            subprocess.run(['soffice', '--version'], 
                          check=True, 
                          stdout=subprocess.PIPE, 
                          stderr=subprocess.PIPE)
        except (subprocess.SubprocessError, FileNotFoundError):
            self.skipTest("LibreOffice not installed or not in PATH")
        
        # Try converting the file
        text, conversion_method = self.compiler.convert_doc_to_text(self.doc_file_path)
        
        # Check that conversion produced some content
        self.assertIsNotNone(text)
        self.assertNotEqual(text, "")
        
        # Check that we don't have error message in the output
        self.assertNotIn("[Failed to convert DOC file:", text)
        
        # Check that conversion method was identified
        self.assertIsNotNone(conversion_method)
        self.assertNotEqual(conversion_method, "")
        self.assertNotEqual(conversion_method, "failed")
        
        # Print first 100 chars of text for manual verification
        print(f"\nFirst 100 chars of converted DOC (using {conversion_method}):\n{text[:100]}...")

    def test_process_doc_file(self):
        """Test that DOC files are correctly processed through the process_file method."""
        # Skip if LibreOffice is not installed
        try:
            subprocess.run(['soffice', '--version'], 
                          check=True, 
                          stdout=subprocess.PIPE, 
                          stderr=subprocess.PIPE)
        except (subprocess.SubprocessError, FileNotFoundError):
            self.skipTest("LibreOffice not installed or not in PATH")
        
        # Process the file
        text, conversion_method = self.compiler.process_file(self.doc_file_path)
        
        # Check that processing produced some content
        self.assertIsNotNone(text)
        self.assertNotEqual(text, "")
        
        # Check that we don't have error message in the output
        self.assertNotIn("[Failed to convert DOC file:", text)
        
        # Check that conversion method was identified
        self.assertIsNotNone(conversion_method)
        self.assertNotEqual(conversion_method, "")
        self.assertTrue("soffice" in conversion_method or conversion_method == "failed")
        
    def test_pdf_to_text_conversion(self):
        """Test conversion of PDF to text with markitdown if available."""
        # Create a simple PDF file for testing
        pdf_path = os.path.join(self.temp_dir, 'test.pdf')
        
        # For testing, we'll just verify the markitdown fallback logic works
        # without actually creating a test PDF file
        
        # Check if markitdown is available
        try:
            subprocess.run(['markitdown', '--version'], 
                          check=True, 
                          stdout=subprocess.PIPE, 
                          stderr=subprocess.PIPE)
            markitdown_available = True
        except (subprocess.SubprocessError, FileNotFoundError):
            markitdown_available = False
            
        # Check if pdftotext is available
        try:
            subprocess.run(['pdftotext', '-v'], 
                          check=True, 
                          stdout=subprocess.PIPE, 
                          stderr=subprocess.PIPE)
            pdftotext_available = True
        except (subprocess.SubprocessError, FileNotFoundError):
            pdftotext_available = False
            
        # If neither tool is available, skip the test
        if not markitdown_available and not pdftotext_available:
            self.skipTest("Neither markitdown nor pdftotext available")
        
        # Mock the PDF file path - this is just to test the function logic
        # without actually creating a PDF file
        pdf_result, conversion_method = self.compiler.convert_pdf_to_text(pdf_path)
        
        # We expect an error message since we don't have a real PDF file
        self.assertIn("[Failed to convert PDF file:", pdf_result)
        
        # Check that conversion method was identified, should be "failed" in this case
        self.assertEqual(conversion_method, "failed")


class TestDOCConversionEdgeCases(unittest.TestCase):
    """Test cases for DOC conversion edge cases."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.output_file = os.path.join(self.temp_dir, 'output.md')

    def tearDown(self):
        """Clean up temp files."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_doc_conversion_empty_file(self):
        """Test that empty DOC files are handled gracefully."""
        from unittest.mock import patch

        # Create an empty DOC file
        empty_doc = os.path.join(self.temp_dir, 'empty.doc')
        with open(empty_doc, 'wb') as f:
            pass  # Create empty file

        compiler = DocumentCompiler(self.temp_dir, self.output_file)
        content, method = compiler.convert_doc_to_text(empty_doc)

        # Should return failure message
        self.assertIn('Failed to convert DOC', content)
        self.assertEqual(method, 'failed')

    def test_doc_conversion_soffice_stderr(self):
        """Test handling of LibreOffice stderr output."""
        from unittest.mock import patch, MagicMock

        # Create a minimal DOC file
        doc_file = os.path.join(self.temp_dir, 'test.doc')
        with open(doc_file, 'wb') as f:
            f.write(b'DOC file content')

        compiler = DocumentCompiler(self.temp_dir, self.output_file)

        # Mock subprocess.run to raise CalledProcessError with stderr
        error = subprocess.CalledProcessError(1, 'soffice')
        error.stderr = 'LibreOffice error: conversion failed'
        error.stdout = ''

        with patch('subprocess.run', side_effect=error):
            content, method = compiler.convert_doc_to_text(doc_file)

        # Should handle the error gracefully
        self.assertIn('Failed to convert DOC', content)
        self.assertEqual(method, 'failed')

    def test_doc_conversion_missing_output(self):
        """Test when LibreOffice runs but doesn't create output file."""
        from unittest.mock import patch, MagicMock

        # Create a minimal DOC file
        doc_file = os.path.join(self.temp_dir, 'test.doc')
        with open(doc_file, 'wb') as f:
            f.write(b'DOC file content')

        compiler = DocumentCompiler(self.temp_dir, self.output_file)

        # Mock subprocess.run to succeed but don't create output file
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = 'Conversion completed'
        mock_result.stderr = ''

        with patch('subprocess.run', return_value=mock_result):
            content, method = compiler.convert_doc_to_text(doc_file)

        # Should fail because output file doesn't exist
        self.assertIn('Failed to convert DOC', content)
        self.assertEqual(method, 'failed')


class TestPaddleOCRConversion(unittest.TestCase):
    """Tests for PaddleOCR PDF conversion."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.output_file = os.path.join(self.temp_dir, 'output.md')
        self.compiler = DocumentCompiler(
            source_path=self.temp_dir,
            output_file=self.output_file,
            recursive=False
        )
        # Create a dummy PDF file
        self.pdf_file = os.path.join(self.temp_dir, 'test.pdf')
        with open(self.pdf_file, 'wb') as f:
            f.write(b'%PDF-1.4 dummy')

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_paddleocr_unavailable_returns_none(self):
        """Test that converter returns (None, None) when PaddleOCR is not installed."""
        with patch.object(self.compiler, 'is_paddleocr_available', return_value=False):
            text, method = self.compiler.convert_pdf_with_paddleocr(self.pdf_file)
            self.assertIsNone(text)
            self.assertIsNone(method)

    def test_paddleocr_successful_conversion(self):
        """Test successful conversion with mocked PaddleOCR subprocess."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = '# Page 1\nContent of page 1\n\n---\n\n# Page 2\nContent of page 2'
        mock_proc.stderr = ''

        with patch.object(self.compiler, 'is_paddleocr_available', return_value=True):
            self.compiler._paddleocr_python = '/usr/bin/python3'
            with patch('subprocess.run', return_value=mock_proc):
                text, method = self.compiler.convert_pdf_with_paddleocr(self.pdf_file)

        self.assertIsNotNone(text)
        self.assertEqual(method, "paddleocr")
        self.assertIn("Page 1", text)
        self.assertIn("Page 2", text)

    def test_paddleocr_empty_output(self):
        """Test that empty output returns (None, None)."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ''
        mock_proc.stderr = ''

        with patch.object(self.compiler, 'is_paddleocr_available', return_value=True):
            self.compiler._paddleocr_python = '/usr/bin/python3'
            with patch('subprocess.run', return_value=mock_proc):
                text, method = self.compiler.convert_pdf_with_paddleocr(self.pdf_file)

        self.assertIsNone(text)
        self.assertIsNone(method)

    def test_paddleocr_exception_handling(self):
        """Test graceful failure when PaddleOCR subprocess fails."""
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = ''
        mock_proc.stderr = 'GPU error'

        with patch.object(self.compiler, 'is_paddleocr_available', return_value=True):
            self.compiler._paddleocr_python = '/usr/bin/python3'
            with patch('subprocess.run', return_value=mock_proc):
                text, method = self.compiler.convert_pdf_with_paddleocr(self.pdf_file)

        self.assertIsNone(text)
        self.assertIsNone(method)

    def test_paddleocr_in_dispatch_table(self):
        """Test that paddleocr appears in the converter dispatch."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = 'Converted content'
        mock_proc.stderr = ''

        compiler = DocumentCompiler(
            source_path=self.temp_dir,
            output_file=self.output_file,
            recursive=False,
            converter_config={'pdf': ['paddleocr']}
        )
        with patch.object(compiler, 'is_paddleocr_available', return_value=True):
            compiler._paddleocr_python = '/usr/bin/python3'
            with patch('subprocess.run', return_value=mock_proc):
                text, method = compiler.convert_pdf_to_text(self.pdf_file)

        self.assertEqual(method, "paddleocr")
        self.assertIn("Converted content", text)


if __name__ == '__main__':
    unittest.main()