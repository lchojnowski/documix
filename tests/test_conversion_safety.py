import os
import sys
import unittest
import tempfile
import shutil
import hashlib
import time
import filecmp
import subprocess
from unittest.mock import patch, MagicMock

# Add parent directory to sys.path to import documix
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from documix.documix import DocumentCompiler, DOCX2TXT_AVAILABLE


class TestConversionSafety(unittest.TestCase):
    """Tests to ensure document conversion methods don't overwrite source files."""

    def setUp(self):
        """Set up test fixtures."""
        # Create temporary directory for output
        self.temp_dir = tempfile.mkdtemp()
        self.output_file = os.path.join(self.temp_dir, 'output.md')
        
        # Path to sample files
        self.resources_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'resources'))
        self.doc_file_path = os.path.join(self.resources_dir, 'example_1mb.doc')
        self.pdf_file_path = os.path.join(self.resources_dir, 'example_pdf.pdf')
        
        # Create a copy of the files to work with
        self.doc_test_file = os.path.join(self.temp_dir, 'test_example.doc')
        self.pdf_test_file = os.path.join(self.temp_dir, 'test_example.pdf')
        
        # Create a test DOCX file for testing DOCX conversion methods
        self.docx_test_file = os.path.join(self.temp_dir, 'test_example.docx')
        
        # Copy files to test directory
        shutil.copy2(self.doc_file_path, self.doc_test_file)
        shutil.copy2(self.pdf_file_path, self.pdf_test_file)
        
        # Try to create a DOCX file by converting from DOC if LibreOffice is available
        try:
            # Use LibreOffice to create a DOCX file for testing
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_doc = os.path.join(tmp_dir, 'temp.doc')
                shutil.copy2(self.doc_file_path, tmp_doc)
                subprocess.run(
                    ['soffice', '--convert-to', 'docx', '--outdir', tmp_dir, tmp_doc],
                    check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
                tmp_docx = os.path.join(tmp_dir, 'temp.docx')
                if os.path.exists(tmp_docx):
                    shutil.copy2(tmp_docx, self.docx_test_file)
        except (subprocess.SubprocessError, FileNotFoundError):
            # If LibreOffice is not available, we'll skip DOCX tests
            print("LibreOffice not available for DOCX preparation")
            self.docx_test_file = None
        
        # Get file checksums before conversion
        self.doc_original_checksum = self.get_file_checksum(self.doc_test_file)
        self.pdf_original_checksum = self.get_file_checksum(self.pdf_test_file)
        if self.docx_test_file and os.path.exists(self.docx_test_file):
            self.docx_original_checksum = self.get_file_checksum(self.docx_test_file)
        
        # Get file modification times
        self.doc_original_mtime = os.path.getmtime(self.doc_test_file)
        self.pdf_original_mtime = os.path.getmtime(self.pdf_test_file)
        if self.docx_test_file and os.path.exists(self.docx_test_file):
            self.docx_original_mtime = os.path.getmtime(self.docx_test_file)
        
        # Create a DocumentCompiler instance
        self.compiler = DocumentCompiler(
            source_path=self.temp_dir,
            output_file=self.output_file,
            recursive=False
        )

    def tearDown(self):
        """Tear down test fixtures."""
        # Clean up temporary directory
        shutil.rmtree(self.temp_dir)
    
    def get_file_checksum(self, filepath):
        """Get MD5 checksum of a file."""
        hasher = hashlib.md5()
        with open(filepath, 'rb') as file:
            buf = file.read()
            hasher.update(buf)
        return hasher.hexdigest()
    
    def test_doc_conversion_with_soffice_preserves_original(self):
        """Test that DOC to DOCX conversion using LibreOffice doesn't modify the original file."""
        # Skip if LibreOffice is not installed
        try:
            subprocess.run(['soffice', '--version'], 
                          check=True, 
                          stdout=subprocess.PIPE, 
                          stderr=subprocess.PIPE)
        except (subprocess.SubprocessError, FileNotFoundError):
            self.skipTest("LibreOffice not installed or not in PATH")
        
        # First ensure the test file exists
        self.assertTrue(os.path.exists(self.doc_test_file), 
                       f"Test DOC file not found at {self.doc_test_file}")
        
        # Process the file
        _, conversion_method = self.compiler.convert_doc_to_text(self.doc_test_file)
        print(f"Used conversion method: {conversion_method}")
        
        # Verify soffice was part of the conversion method
        self.assertTrue("soffice" in conversion_method, 
                       "Expected soffice to be used in conversion")
        
        # Wait a moment to ensure any potential file operations are complete
        time.sleep(1)
        
        # Check that the original file's checksum hasn't changed
        doc_new_checksum = self.get_file_checksum(self.doc_test_file)
        self.assertEqual(self.doc_original_checksum, doc_new_checksum,
                        "DOC file's content was modified during conversion")
        
        # Also check that the file's modification time hasn't changed
        # (small allowance for filesystem timestamp precision differences)
        doc_new_mtime = os.path.getmtime(self.doc_test_file)
        self.assertAlmostEqual(self.doc_original_mtime, doc_new_mtime, 
                             delta=2, msg="DOC file's modification time was changed during conversion")
    
    def test_pdf_conversion_with_markitdown_preserves_original(self):
        """Test that PDF conversion with markitdown doesn't modify the original file."""
        # Check if markitdown is available
        try:
            subprocess.run(['markitdown', '--version'], 
                          check=True, 
                          stdout=subprocess.PIPE, 
                          stderr=subprocess.PIPE)
            markitdown_available = True
        except (subprocess.SubprocessError, FileNotFoundError):
            markitdown_available = False
            self.skipTest("markitdown not available to test")
        
        # First ensure the test file exists
        self.assertTrue(os.path.exists(self.pdf_test_file), 
                       f"Test PDF file not found at {self.pdf_test_file}")
        
        # Get checksum before conversion
        pdf_checksum_before = self.get_file_checksum(self.pdf_test_file)
        pdf_mtime_before = os.path.getmtime(self.pdf_test_file)
        
        # Force markitdown to be used by mocking uvx and pdftotext to fail
        original_run = subprocess.run

        def mock_subprocess_run(args, **kwargs):
            if args[0] == 'uvx':
                # Make uvx fail to force direct markitdown path
                raise FileNotFoundError("Mock failure of uvx")
            if args[0] == 'pdftotext':
                # Make pdftotext fail
                raise FileNotFoundError("Mock failure of pdftotext")
            # Let other calls proceed with the real subprocess.run
            return original_run(args, **kwargs)

        # Reset uvx cache so it re-checks
        self.compiler._uvx_available = None

        # Use the mock to force markitdown path
        with patch('subprocess.run', side_effect=mock_subprocess_run):
            # Process the file
            _, conversion_method = self.compiler.convert_pdf_to_text(self.pdf_test_file)
            print(f"Used conversion method: {conversion_method}")
            
            # Verify markitdown was used
            self.assertEqual(conversion_method, "markitdown", 
                            "Expected markitdown conversion method")
        
        # Wait a moment to ensure any potential file operations are complete
        time.sleep(1)
        
        # Check that the original file's checksum hasn't changed
        pdf_checksum_after = self.get_file_checksum(self.pdf_test_file)
        self.assertEqual(pdf_checksum_before, pdf_checksum_after,
                        "PDF file's content was modified during markitdown conversion")
        
        # Also check that the file's modification time hasn't changed
        pdf_mtime_after = os.path.getmtime(self.pdf_test_file)
        self.assertAlmostEqual(pdf_mtime_before, pdf_mtime_after, 
                             delta=2, msg="PDF file's modification time was changed during markitdown conversion")
    
    def test_pdf_conversion_with_pdftotext_preserves_original(self):
        """Test that PDF conversion with pdftotext doesn't modify the original file."""
        # Check if pdftotext is available
        try:
            subprocess.run(['pdftotext', '-v'], 
                          check=True, 
                          stdout=subprocess.PIPE, 
                          stderr=subprocess.PIPE)
            pdftotext_available = True
        except (subprocess.SubprocessError, FileNotFoundError):
            pdftotext_available = False
            self.skipTest("pdftotext not available to test")
        
        # First ensure the test file exists
        self.assertTrue(os.path.exists(self.pdf_test_file), 
                       f"Test PDF file not found at {self.pdf_test_file}")
        
        # Get checksum before conversion
        pdf_checksum_before = self.get_file_checksum(self.pdf_test_file)
        pdf_mtime_before = os.path.getmtime(self.pdf_test_file)
        
        # Force pdftotext to be used by mocking uvx and markitdown to fail
        original_run = subprocess.run

        def mock_subprocess_run(args, **kwargs):
            if args[0] == 'uvx':
                # Make uvx fail to force fallback paths
                raise FileNotFoundError("Mock failure of uvx")
            if args[0] == 'markitdown':
                # Make markitdown fail
                raise FileNotFoundError("Mock failure of markitdown")
            # Let other calls proceed with the real subprocess.run
            return original_run(args, **kwargs)

        # Reset uvx cache so it re-checks
        self.compiler._uvx_available = None

        # Use the mock to force pdftotext path
        with patch('subprocess.run', side_effect=mock_subprocess_run):
            # Process the file
            _, conversion_method = self.compiler.convert_pdf_to_text(self.pdf_test_file)
            print(f"Used conversion method: {conversion_method}")
            
            # Verify pdftotext was used
            self.assertEqual(conversion_method, "pdftotext", 
                            "Expected pdftotext conversion method")
        
        # Wait a moment to ensure any potential file operations are complete
        time.sleep(1)
        
        # Check that the original file's checksum hasn't changed
        pdf_checksum_after = self.get_file_checksum(self.pdf_test_file)
        self.assertEqual(pdf_checksum_before, pdf_checksum_after,
                        "PDF file's content was modified during pdftotext conversion")
        
        # Also check that the file's modification time hasn't changed
        pdf_mtime_after = os.path.getmtime(self.pdf_test_file)
        self.assertAlmostEqual(pdf_mtime_before, pdf_mtime_after,
                             delta=2, msg="PDF file's modification time was changed during pdftotext conversion")

    def test_pdf_conversion_uvx_markitdown_uses_pdf_extra(self):
        """Test that uvx markitdown is called with [pdf] extra for PDF dependencies."""
        # First ensure the test file exists
        self.assertTrue(os.path.exists(self.pdf_test_file),
                       f"Test PDF file not found at {self.pdf_test_file}")

        # Track the commands that were called
        called_commands = []

        # Mock subprocess.run to capture the uvx command and simulate success
        def mock_subprocess_run(args, **kwargs):
            called_commands.append(list(args))

            # For uvx --version check, return success
            if args[0] == 'uvx' and args[1] == '--version':
                return MagicMock(returncode=0)

            # For uvx markitdown[pdf] command, simulate success by creating output
            if args[0] == 'uvx' and 'markitdown' in args[1]:
                # Find the output file path (-o flag)
                if '-o' in args:
                    output_idx = args.index('-o') + 1
                    output_file = args[output_idx]
                    # Create a mock output file
                    with open(output_file, 'w') as f:
                        f.write("# Converted PDF content\nMock content")
                return MagicMock(returncode=0)

            # Fail other commands to ensure uvx path is tested
            raise FileNotFoundError(f"Mock: command not found: {args[0]}")

        # Force uvx to be "available" by resetting the cache
        self.compiler._uvx_available = None

        with patch('subprocess.run', side_effect=mock_subprocess_run):
            # Process the file
            _, conversion_method = self.compiler.convert_pdf_to_text(self.pdf_test_file)

            # Verify uvx markitdown was used
            self.assertEqual(conversion_method, "markitdown-uvx",
                            "Expected markitdown-uvx conversion method")

        # Verify that uvx markitdown[pdf] was called (not just markitdown)
        uvx_markitdown_calls = [cmd for cmd in called_commands
                                if len(cmd) >= 2 and cmd[0] == 'uvx' and 'markitdown' in cmd[1]]

        self.assertTrue(len(uvx_markitdown_calls) > 0,
                       "Expected uvx markitdown to be called")

        # Check that the [pdf] extra is included
        markitdown_arg = uvx_markitdown_calls[0][1]
        self.assertIn('[pdf]', markitdown_arg,
                     f"Expected 'markitdown[pdf]' but got '{markitdown_arg}'. "
                     "The [pdf] extra is required for PDF conversion support with uvx.")

    def test_docx_conversion_with_pandoc_preserves_original(self):
        """Test that DOCX conversion with pandoc doesn't modify the original file."""
        # Skip if no DOCX test file was created
        if not self.docx_test_file or not os.path.exists(self.docx_test_file):
            self.skipTest("DOCX test file not available")
        
        # Check if pandoc is available
        try:
            subprocess.run(['pandoc', '--version'], 
                          check=True, 
                          stdout=subprocess.PIPE, 
                          stderr=subprocess.PIPE)
            pandoc_available = True
        except (subprocess.SubprocessError, FileNotFoundError):
            pandoc_available = False
            self.skipTest("pandoc not available to test")
        
        # Force pandoc to be used by mocking docx2txt to be unavailable
        with patch('documix.documix.DOCX2TXT_AVAILABLE', False):
            # Process the file
            _, conversion_method = self.compiler.convert_docx_to_text(self.docx_test_file)
            print(f"Used conversion method: {conversion_method}")
            
            # Verify pandoc was used
            self.assertEqual(conversion_method, "pandoc", 
                            "Expected pandoc conversion method")
        
        # Wait a moment to ensure any potential file operations are complete
        time.sleep(1)
        
        # Check that the original file's checksum hasn't changed
        docx_checksum_after = self.get_file_checksum(self.docx_test_file)
        self.assertEqual(self.docx_original_checksum, docx_checksum_after,
                        "DOCX file's content was modified during pandoc conversion")
        
        # Also check that the file's modification time hasn't changed
        docx_mtime_after = os.path.getmtime(self.docx_test_file)
        self.assertAlmostEqual(self.docx_original_mtime, docx_mtime_after, 
                             delta=2, msg="DOCX file's modification time was changed during pandoc conversion")
    
    def test_docx_conversion_with_docx2txt_preserves_original(self):
        """Test that DOCX conversion with docx2txt doesn't modify the original file."""
        # Skip if no DOCX test file was created
        if not self.docx_test_file or not os.path.exists(self.docx_test_file):
            self.skipTest("DOCX test file not available")
        
        # Skip if docx2txt is not available
        if not DOCX2TXT_AVAILABLE:
            self.skipTest("docx2txt not available to test")
        
        # Force docx2txt to be used by mocking pandoc to fail
        def mock_subprocess_run(args, **kwargs):
            if args[0] == 'pandoc':
                # Make pandoc fail
                raise FileNotFoundError("Mock failure of pandoc")
            # Let other calls proceed normally
            return subprocess.run(args, **kwargs)
        
        # Use the mock to force docx2txt path
        with patch('subprocess.run', side_effect=mock_subprocess_run):
            # Process the file
            _, conversion_method = self.compiler.convert_docx_to_text(self.docx_test_file)
            print(f"Used conversion method: {conversion_method}")
            
            # Verify docx2txt was used
            self.assertEqual(conversion_method, "docx2txt", 
                            "Expected docx2txt conversion method")
        
        # Wait a moment to ensure any potential file operations are complete
        time.sleep(1)
        
        # Check that the original file's checksum hasn't changed
        docx_checksum_after = self.get_file_checksum(self.docx_test_file)
        self.assertEqual(self.docx_original_checksum, docx_checksum_after,
                        "DOCX file's content was modified during docx2txt conversion")
        
        # Also check that the file's modification time hasn't changed
        docx_mtime_after = os.path.getmtime(self.docx_test_file)
        self.assertAlmostEqual(self.docx_original_mtime, docx_mtime_after, 
                             delta=2, msg="DOCX file's modification time was changed during docx2txt conversion")
    
    def test_process_file_preserves_original(self):
        """Test that the general process_file method doesn't modify original files."""
        # Make copies of original checksums for comparison after processing
        doc_checksum_before = self.doc_original_checksum
        pdf_checksum_before = self.pdf_original_checksum
        
        # Process the files
        self.compiler.process_file(self.doc_test_file)
        self.compiler.process_file(self.pdf_test_file)
        
        # Process DOCX file if available
        if self.docx_test_file and os.path.exists(self.docx_test_file):
            docx_checksum_before = self.docx_original_checksum
            self.compiler.process_file(self.docx_test_file)
            docx_checksum_after = self.get_file_checksum(self.docx_test_file)
            self.assertEqual(docx_checksum_before, docx_checksum_after,
                            "DOCX file content was modified during processing")
        
        # Wait a moment to ensure any potential file operations are complete
        time.sleep(1)
        
        # Check checksums after processing
        doc_checksum_after = self.get_file_checksum(self.doc_test_file)
        pdf_checksum_after = self.get_file_checksum(self.pdf_test_file)
        
        # Verify files haven't been modified
        self.assertEqual(doc_checksum_before, doc_checksum_after,
                        "DOC file content was modified during processing")
        self.assertEqual(pdf_checksum_before, pdf_checksum_after,
                        "PDF file content was modified during processing")
    
    def test_full_compile_preserves_original_files(self):
        """Test that the full compilation process doesn't modify original files."""
        # Capture original information about all files in the directory
        original_files = {}
        for filename in os.listdir(self.temp_dir):
            filepath = os.path.join(self.temp_dir, filename)
            if os.path.isfile(filepath):
                original_files[filepath] = {
                    'checksum': self.get_file_checksum(filepath),
                    'mtime': os.path.getmtime(filepath),
                    'size': os.path.getsize(filepath)
                }
        
        # Run the compilation
        self.compiler.compile()
        
        # Check that original files are unchanged
        for filepath, original_info in original_files.items():
            if filepath != self.output_file:  # Skip the output file, which is supposed to be created
                # Check file still exists
                self.assertTrue(os.path.exists(filepath), f"File {filepath} was deleted during compilation")
                
                # Check checksum
                current_checksum = self.get_file_checksum(filepath)
                self.assertEqual(original_info['checksum'], current_checksum,
                                f"File {filepath} content was modified during compilation")
                
                # Check file size
                current_size = os.path.getsize(filepath)
                self.assertEqual(original_info['size'], current_size,
                                f"File {filepath} size changed during compilation")


if __name__ == '__main__':
    unittest.main()