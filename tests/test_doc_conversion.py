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

    def test_paddleocr_availability_no_python_in_venv(self):
        """paddleocr found but no python in venv dir."""
        self.compiler._paddleocr_available = None  # Reset cache
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        with patch('subprocess.run', return_value=mock_proc), \
             patch('shutil.which', return_value='/fake/bin/paddleocr'), \
             patch('os.path.realpath', return_value='/fake/bin/paddleocr'), \
             patch('os.path.dirname', return_value='/fake/bin'), \
             patch('os.path.exists', return_value=False):
            result = self.compiler.is_paddleocr_available()
            self.assertFalse(result)

    def test_paddleocr_availability_which_returns_none(self):
        """paddleocr --version ok but which returns None."""
        self.compiler._paddleocr_available = None  # Reset cache
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        with patch('subprocess.run', return_value=mock_proc), \
             patch('shutil.which', return_value=None):
            result = self.compiler.is_paddleocr_available()
            self.assertFalse(result)

    def test_paddleocr_conversion_generic_exception(self):
        """subprocess raises generic Exception (not SubprocessError)."""
        with patch.object(self.compiler, 'is_paddleocr_available', return_value=True):
            self.compiler._paddleocr_python = '/usr/bin/python3'
            with patch('subprocess.run', side_effect=RuntimeError("unexpected")):
                text, method = self.compiler.convert_pdf_with_paddleocr(self.pdf_file)
                self.assertIsNone(text)
                self.assertIsNone(method)


class TestPDFTableConversion(unittest.TestCase):
    """Tests for PDF table conversion functionality."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.output_file = os.path.join(self.temp_dir, 'output.md')
        self.compiler = DocumentCompiler(
            source_path=self.temp_dir,
            output_file=self.output_file,
            recursive=False
        )
        self.pdf_file = os.path.join(self.temp_dir, 'test.pdf')
        with open(self.pdf_file, 'wb') as f:
            f.write(b'%PDF-1.4 dummy')

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_table_cell_density_full(self):
        """All cells filled -> 1.0."""
        data = [['a', 'b'], ['c', 'd']]
        self.assertEqual(self.compiler._table_cell_density(data), 1.0)

    def test_table_cell_density_empty(self):
        """Empty table -> 0.0."""
        self.assertEqual(self.compiler._table_cell_density([]), 0.0)

    def test_table_cell_density_partial(self):
        """Half None cells -> ~0.5."""
        data = [['a', None], [None, 'd']]
        density = self.compiler._table_cell_density(data)
        self.assertAlmostEqual(density, 0.5)

    @patch('documix.documix.PDFPLUMBER_AVAILABLE', False)
    def test_convert_pdf_with_tables_no_pdfplumber(self):
        """Returns (None, None) when pdfplumber not available."""
        text, method = self.compiler.convert_pdf_with_tables(self.pdf_file)
        self.assertIsNone(text)
        self.assertIsNone(method)

    def test_convert_pdf_with_tables_exception(self):
        """pdfplumber.open raises -> returns (None, None)."""
        with patch('documix.documix.PDFPLUMBER_AVAILABLE', True), \
             patch('documix.documix.pdfplumber') as mock_pdfplumber:
            mock_pdfplumber.open.side_effect = Exception("corrupt pdf")
            text, method = self.compiler.convert_pdf_with_tables(self.pdf_file)
            self.assertIsNone(text)
            self.assertIsNone(method)

    def test_convert_pdf_with_tables_no_tables(self):
        """No tables found, falls back to extract_text."""
        mock_page = MagicMock()
        mock_page.find_tables.return_value = []
        mock_page.extract_text.return_value = "Plain text content"

        mock_pdf = MagicMock()
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_pdf.pages = [mock_page]

        with patch('documix.documix.PDFPLUMBER_AVAILABLE', True), \
             patch('documix.documix.pdfplumber') as mock_pdfplumber:
            mock_pdfplumber.open.return_value = mock_pdf
            text, method = self.compiler.convert_pdf_with_tables(self.pdf_file)
            self.assertIn("Plain text content", text)
            self.assertEqual(method, "pdfplumber")

    def test_convert_pdf_with_tables_bordered_tables(self):
        """Mock pdfplumber with bordered tables found."""
        mock_table = MagicMock()
        mock_table.extract.return_value = [['Header1', 'Header2'], ['val1', 'val2']]
        mock_table.bbox = (0, 0, 100, 50)

        mock_page = MagicMock()
        mock_page.find_tables.return_value = [mock_table]
        mock_page.filter.return_value = mock_page
        mock_page.extract_text.return_value = "Surrounding text"

        mock_pdf = MagicMock()
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_pdf.pages = [mock_page]

        with patch('documix.documix.PDFPLUMBER_AVAILABLE', True), \
             patch('documix.documix.pdfplumber') as mock_pdfplumber:
            mock_pdfplumber.open.return_value = mock_pdf
            text, method = self.compiler.convert_pdf_with_tables(self.pdf_file)
            self.assertIsNotNone(text)
            self.assertEqual(method, "pdfplumber-tables")
            self.assertIn("Header1", text)

    def test_convert_pdf_with_tables_text_strategy(self):
        """No bordered tables, text-strategy succeeds with quality tables."""
        # First call: bordered tables (empty). Second call: text-strategy tables.
        text_table = MagicMock()
        text_table.extract.return_value = [['A', 'B'], ['C', 'D']]
        text_table.bbox = (0, 0, 100, 50)

        mock_page = MagicMock()
        # First find_tables (default) returns empty, second (text strategy) returns tables
        mock_page.find_tables.side_effect = [[], [text_table]]
        mock_page.filter.return_value = mock_page
        mock_page.extract_text.return_value = ""

        mock_pdf = MagicMock()
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_pdf.pages = [mock_page]

        with patch('documix.documix.PDFPLUMBER_AVAILABLE', True), \
             patch('documix.documix.pdfplumber') as mock_pdfplumber:
            mock_pdfplumber.open.return_value = mock_pdf
            text, method = self.compiler.convert_pdf_with_tables(self.pdf_file)
            self.assertIsNotNone(text)
            self.assertIn("A", text)

    def test_html_tables_to_markdown_static_basic(self):
        """Basic HTML table conversion."""
        html = "<table><tr><th>H1</th><th>H2</th></tr><tr><td>a</td><td>b</td></tr></table>"
        result = DocumentCompiler._html_tables_to_markdown(html)
        self.assertIn("H1", result)
        self.assertNotIn("<table>", result)

    def test_html_tables_to_markdown_static_no_tables(self):
        """No tables - passthrough."""
        text = "Just plain text with no tables"
        result = DocumentCompiler._html_tables_to_markdown(text)
        self.assertEqual(result, text)

    def test_html_tables_to_markdown_static_paddleocr_wrapper(self):
        """PaddleOCR div wrapper should be handled."""
        html = '<div class="page"><html><body><table><tr><td>cell</td></tr></table></body></html></div>'
        result = DocumentCompiler._html_tables_to_markdown(html)
        self.assertIn("cell", result)
        self.assertNotIn("<div", result)


class TestPDFConverterFallbacks(unittest.TestCase):
    """Tests for PDF converter error paths."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.output_file = os.path.join(self.temp_dir, 'output.md')
        self.compiler = DocumentCompiler(
            source_path=self.temp_dir,
            output_file=self.output_file,
            recursive=False
        )
        self.pdf_file = os.path.join(self.temp_dir, 'test.pdf')
        with open(self.pdf_file, 'wb') as f:
            f.write(b'%PDF-1.4 dummy')

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_markitdown_uvx_not_available(self):
        """uvx not available -> (None, None)."""
        with patch.object(self.compiler, 'is_uvx_available', return_value=False):
            text, method = self.compiler._try_pdf_markitdown_uvx(self.pdf_file)
            self.assertIsNone(text)
            self.assertIsNone(method)

    def test_markitdown_uvx_subprocess_error(self):
        """uvx subprocess fails -> (None, None)."""
        with patch.object(self.compiler, 'is_uvx_available', return_value=True), \
             patch('subprocess.run', side_effect=subprocess.SubprocessError("fail")):
            text, method = self.compiler._try_pdf_markitdown_uvx(self.pdf_file)
            self.assertIsNone(text)
            self.assertIsNone(method)

    def test_markitdown_subprocess_error(self):
        """markitdown subprocess fails -> (None, None)."""
        with patch('subprocess.run', side_effect=FileNotFoundError("not found")):
            text, method = self.compiler._try_pdf_markitdown(self.pdf_file)
            self.assertIsNone(text)
            self.assertIsNone(method)

    def test_pdftotext_subprocess_error(self):
        """pdftotext subprocess fails -> (None, None)."""
        with patch('subprocess.run', side_effect=subprocess.SubprocessError("fail")):
            text, method = self.compiler._try_pdf_pdftotext(self.pdf_file)
            self.assertIsNone(text)
            self.assertIsNone(method)


class TestDOCXEdgeCases(unittest.TestCase):
    """Tests for DOCX converter edge cases."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.output_file = os.path.join(self.temp_dir, 'output.md')
        self.compiler = DocumentCompiler(
            source_path=self.temp_dir,
            output_file=self.output_file,
            recursive=False
        )
        self.docx_file = os.path.join(self.temp_dir, 'test.docx')
        with open(self.docx_file, 'wb') as f:
            f.write(b'PK fake docx')

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    @patch('documix.documix.DOCX2TXT_AVAILABLE', False)
    def test_docx2txt_unavailable(self):
        """DOCX2TXT_AVAILABLE=False -> (None, None)."""
        text, method = self.compiler._try_docx_docx2txt(self.docx_file)
        self.assertIsNone(text)
        self.assertIsNone(method)

    @patch('documix.documix.DOCX2TXT_AVAILABLE', True)
    def test_docx2txt_empty_output(self):
        """docx2txt returns empty string -> (None, None)."""
        with patch('documix.documix.docx2txt') as mock_docx2txt:
            mock_docx2txt.process.return_value = ""
            text, method = self.compiler._try_docx_docx2txt(self.docx_file)
            self.assertIsNone(text)
            self.assertIsNone(method)


if __name__ == '__main__':
    unittest.main()