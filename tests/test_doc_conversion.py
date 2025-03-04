import os
import sys
import unittest
import tempfile
import shutil

# Add parent directory to sys.path to import documix
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from documix.documix import DocumentCompiler


class TestDocConversion(unittest.TestCase):
    """Tests for DOC to DOCX conversion."""

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
            import subprocess
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


if __name__ == '__main__':
    unittest.main()