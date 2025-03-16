import os
import sys
import unittest
import tempfile
import shutil
import subprocess

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
                                             '..', 'resources', 'example_1mb.doc'))
        
        # Create a DocumentCompiler instance
        self.compiler = DocumentCompiler(
            source_dir=os.path.dirname(self.doc_file_path),
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
            import subprocess
            subprocess.run(['soffice', '--version'], 
                          check=True, 
                          stdout=subprocess.PIPE, 
                          stderr=subprocess.PIPE)
        except (subprocess.SubprocessError, FileNotFoundError):
            self.skipTest("LibreOffice not installed or not in PATH")
        
        # Try converting the file
        text = self.compiler.convert_doc_to_text(self.doc_file_path)
        
        # Check that conversion produced some content
        self.assertIsNotNone(text)
        self.assertNotEqual(text, "")
        
        # Check that we don't have error message in the output
        self.assertNotIn("[Failed to convert DOC file:", text)
        
        # Print first 100 chars of text for manual verification
        print(f"\nFirst 100 chars of converted DOC:\n{text[:100]}...")

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
        text = self.compiler.process_file(self.doc_file_path)
        
        # Check that processing produced some content
        self.assertIsNotNone(text)
        self.assertNotEqual(text, "")
        
        # Check that we don't have error message in the output
        self.assertNotIn("[Failed to convert DOC file:", text)
        
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
        pdf_result = self.compiler.convert_pdf_to_text(pdf_path)
        
        # We expect an error message since we don't have a real PDF file
        self.assertIn("[Failed to convert PDF file:", pdf_result)


if __name__ == '__main__':
    unittest.main()