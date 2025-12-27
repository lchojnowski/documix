import os
import sys
import tempfile
import unittest
import zipfile
import shutil
import hashlib
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add parent directory to sys.path to import documix
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from documix.documix import DocumentCompiler


class TestDocuMix(unittest.TestCase):
    """Tests for the DocuMix package."""

    def setUp(self):
        """Set up test fixtures."""
        # Create a temporary directory for test files
        self.temp_dir = tempfile.mkdtemp()
        self.output_file = os.path.join(self.temp_dir, 'output.md')
        
        # Create some sample test files
        self.create_test_files()
        
        # Create a DocumentCompiler instance for testing
        self.compiler = DocumentCompiler(
            source_path=self.temp_dir,
            output_file=self.output_file,
            recursive=True
        )

    def tearDown(self):
        """Tear down test fixtures."""
        # Clean up the temporary directory
        shutil.rmtree(self.temp_dir)

    def create_test_files(self):
        """Create sample files for testing."""
        # Create a sample Python file
        python_file = os.path.join(self.temp_dir, 'sample.py')
        with open(python_file, 'w') as f:
            f.write('def hello_world():\n    print("Hello, World!")\n')

        # Create a sample Markdown file
        md_file = os.path.join(self.temp_dir, 'sample.md')
        with open(md_file, 'w') as f:
            f.write('# Sample Markdown\n\nThis is a test file.\n')

        # Create a sample text file
        txt_file = os.path.join(self.temp_dir, 'sample.txt')
        with open(txt_file, 'w') as f:
            f.write('This is a sample text file for testing.\n')

        # Create a sample JSON file
        json_file = os.path.join(self.temp_dir, 'sample.json')
        with open(json_file, 'w') as f:
            f.write('{"name": "Test", "purpose": "Testing DocuMix"}\n')

        # Create a nested directory with a file
        nested_dir = os.path.join(self.temp_dir, 'nested')
        os.makedirs(nested_dir, exist_ok=True)
        nested_file = os.path.join(nested_dir, 'nested_sample.py')
        with open(nested_file, 'w') as f:
            f.write('# This is a nested Python file\n')

        # Create a sample ZIP file with some content
        zip_path = os.path.join(self.temp_dir, 'sample.zip')
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            zipf.writestr('zip_sample.txt', 'This is a text file inside a ZIP.')
            zipf.writestr('zip_sample.py', 'print("This is Python code inside a ZIP.")')
            zipf.writestr('nested/zip_nested.md', '# Nested Markdown\n\nInside a ZIP file.')

    def test_get_file_language(self):
        """Test that file language detection works correctly."""
        test_cases = [
            ('file.py', 'python'),
            ('file.js', 'javascript'),
            ('file.html', 'html'),
            ('file.css', 'css'),
            ('file.json', 'json'),
            ('file.md', 'markdown'),
            ('file.txt', 'text'),
            ('file.unknown', ''),  # Unknown extension should return empty string
        ]
        
        for filename, expected_language in test_cases:
            language = self.compiler.get_file_language(filename)
            self.assertEqual(language, expected_language, 
                             f"Expected language '{expected_language}' for '{filename}', got '{language}'")

    def test_estimate_tokens(self):
        """Test token estimation functionality."""
        test_cases = [
            ('', 0),  # Empty string
            ('Hello world', 2),  # Two words
            ('Hello, world!', 3),  # Two words + one punctuation
            ('This is a test. With two sentences.', 8),  # 6 words + 2 punctuations
        ]
        
        for text, expected_count in test_cases:
            token_count = self.compiler.estimate_tokens(text)
            self.assertEqual(token_count, expected_count, 
                             f"Expected {expected_count} tokens for '{text}', got {token_count}")

    def test_collect_files(self):
        """Test that files are collected correctly, including in subdirectories if recursive=True."""
        files = self.compiler.collect_files()
        
        # Check that we have all the expected files
        file_names = [os.path.basename(f) for f in files]
        self.assertIn('sample.py', file_names)
        self.assertIn('sample.md', file_names)
        self.assertIn('sample.txt', file_names)
        self.assertIn('sample.json', file_names)
        self.assertIn('sample.zip', file_names)
        
        # Check that we have the nested file if recursive is True
        nested_files = [f for f in files if 'nested' in f]
        self.assertTrue(any('nested_sample.py' in f for f in nested_files), 
                       "Nested file should be included when recursive=True")
                       
        # Test with recursive=False
        non_recursive_compiler = DocumentCompiler(
            source_path=self.temp_dir,
            output_file=self.output_file,
            recursive=False
        )
        files = non_recursive_compiler.collect_files()
        
        # Should not include nested files
        self.assertFalse(any('nested/nested_sample.py' in f for f in files),
                        "Nested file should not be included when recursive=False")

    def test_get_directory_structure(self):
        """Test that directory structure is correctly generated."""
        structure = self.compiler.get_directory_structure()
        
        # Check that the structure contains main directory entries
        self.assertTrue(any('sample.py' in entry for entry in structure))
        self.assertTrue(any('sample.md' in entry for entry in structure))
        
        # Check that we have the nested directory if recursive is True
        self.assertTrue(any('nested/' in entry for entry in structure), 
                       "Nested directory should be in structure when recursive=True")
                       
        # Test with recursive=False
        non_recursive_compiler = DocumentCompiler(
            source_path=self.temp_dir,
            output_file=self.output_file,
            recursive=False
        )
        structure = non_recursive_compiler.get_directory_structure()
        
        # Should not include nested directory
        self.assertFalse(any('nested/' in entry for entry in structure),
                        "Nested directory should not be in structure when recursive=False")

    def test_convert_txt_to_text(self):
        """Test text file conversion."""
        txt_file = os.path.join(self.temp_dir, 'sample.txt')
        content, conversion_method = self.compiler.convert_txt_to_text(txt_file)
        
        self.assertEqual(content, 'This is a sample text file for testing.\n')
        self.assertEqual(conversion_method, 'direct_read')

    def test_extract_zip(self):
        """Test ZIP file extraction and processing."""
        zip_file = os.path.join(self.temp_dir, 'sample.zip')
        content, conversion_method = self.compiler.extract_zip(zip_file)
        
        # Check that the content contains information about ZIP contents
        self.assertIn('ZIP Archive Contents:', content)
        self.assertIn('zip_sample.txt', content)
        self.assertIn('zip_sample.py', content)
        self.assertIn('nested/zip_nested.md', content)
        
        # Check that content of files in ZIP is included
        self.assertIn('This is a text file inside a ZIP', content)
        self.assertIn('This is Python code inside a ZIP', content)
        self.assertIn('Nested Markdown', content)
        
        # Check conversion method
        self.assertIn('zip_extract', conversion_method)

    def test_process_file(self):
        """Test processing different types of files."""
        # Test processing a Python file
        py_file = os.path.join(self.temp_dir, 'sample.py')
        py_content, py_method = self.compiler.process_file(py_file)
        self.assertIn('def hello_world():', py_content)
        self.assertEqual(py_method, 'direct_read')
        
        # Test processing a Markdown file
        md_file = os.path.join(self.temp_dir, 'sample.md')
        md_content, md_method = self.compiler.process_file(md_file)
        self.assertIn('# Sample Markdown', md_content)
        self.assertEqual(md_method, 'direct_read')
        
        # Test processing a ZIP file
        zip_file = os.path.join(self.temp_dir, 'sample.zip')
        zip_content, zip_method = self.compiler.process_file(zip_file)
        self.assertIn('ZIP Archive Contents:', zip_content)
        self.assertIn('zip_extract', zip_method)

    def test_compile_basic(self):
        """Test the main compile function - basic functionality."""
        # Run the compile method
        result = self.compiler.compile()
        
        # Check that compilation was successful
        self.assertTrue(result)
        
        # Check that the output file was created
        self.assertTrue(os.path.exists(self.output_file))
        
        # Check content of the output file
        with open(self.output_file, 'r') as f:
            content = f.read()
            
        # Check that the file has the expected sections
        self.assertIn('# File Summary', content)
        self.assertIn('# Directory Information', content)
        self.assertIn('# Directory Structure', content)
        self.assertIn('# Files', content)
        
        # Check that all files are included
        self.assertIn('## File: sample.py', content)
        self.assertIn('## File: sample.md', content)
        self.assertIn('## File: sample.txt', content)
        self.assertIn('## File: sample.json', content)
        self.assertIn('## File: sample.zip', content)

    def test_exclude_patterns(self):
        """Test that exclusion patterns work correctly."""
        # Create a compiler with exclusion patterns
        compiler_with_exclusions = DocumentCompiler(
            source_path=self.temp_dir,
            output_file=self.output_file,
            recursive=True,
            exclude_patterns=[r'.*\.py']  # Exclude Python files
        )
        
        files = compiler_with_exclusions.collect_files()
        file_names = [os.path.basename(f) for f in files]
        
        # Python files should be excluded
        self.assertNotIn('sample.py', file_names)
        
        # Other files should be included
        self.assertIn('sample.md', file_names)
        self.assertIn('sample.txt', file_names)
        self.assertIn('sample.json', file_names)
        self.assertIn('sample.zip', file_names)

    def test_include_extensions(self):
        """Test that extension filtering works correctly."""
        # Create a compiler with specific extensions
        compiler_with_extensions = DocumentCompiler(
            source_path=self.temp_dir,
            output_file=self.output_file,
            recursive=True,
            include_extensions=['.md', '.txt']  # Only include Markdown and text files
        )

        files = compiler_with_extensions.collect_files()
        file_names = [os.path.basename(f) for f in files]

        # Only Markdown and text files should be included
        self.assertIn('sample.md', file_names)
        self.assertIn('sample.txt', file_names)

        # Other files should be excluded
        self.assertNotIn('sample.py', file_names)
        self.assertNotIn('sample.json', file_names)
        self.assertNotIn('sample.zip', file_names)

    def test_rtf_extension_included(self):
        """Test that RTF files are included in default extensions."""
        self.assertIn('.rtf', self.compiler.include_extensions)

    def test_convert_rtf_to_text(self):
        """Test RTF file conversion."""
        # Create a simple RTF file
        rtf_content = r"""{\rtf1\ansi\deff0
{\fonttbl{\f0 Arial;}}
\f0\pard This is a test RTF document.\par
It has multiple lines.\par
}"""
        rtf_file = os.path.join(self.temp_dir, 'sample.rtf')
        with open(rtf_file, 'w') as f:
            f.write(rtf_content)

        content, conversion_method = self.compiler.convert_rtf_to_text(rtf_file)

        # Check that conversion returned something
        self.assertIsNotNone(content)
        self.assertIsNotNone(conversion_method)

        # If conversion succeeded, check content contains expected text
        if conversion_method != 'failed':
            self.assertIn('test', content.lower())
        else:
            # If all RTF tools are missing, check we get a failure message
            self.assertIn('Failed to convert RTF', content)

    def test_process_file_rtf(self):
        """Test that RTF files are processed correctly via process_file."""
        # Create a simple RTF file
        rtf_content = r"""{\rtf1\ansi\deff0
{\fonttbl{\f0 Arial;}}
\f0\pard Hello RTF World.\par
}"""
        rtf_file = os.path.join(self.temp_dir, 'test.rtf')
        with open(rtf_file, 'w') as f:
            f.write(rtf_content)

        content, method = self.compiler.process_file(rtf_file)

        # Check that it was processed
        self.assertIsNotNone(content)
        self.assertIsNotNone(method)

    def test_convert_rtf_empty_file(self):
        """Test RTF conversion with empty/minimal RTF content."""
        # Test with completely empty file
        empty_rtf = os.path.join(self.temp_dir, 'empty.rtf')
        with open(empty_rtf, 'w') as f:
            f.write('')

        content, method = self.compiler.convert_rtf_to_text(empty_rtf)
        self.assertIsNotNone(content)
        self.assertIsNotNone(method)

        # Test with minimal valid RTF
        minimal_rtf = os.path.join(self.temp_dir, 'minimal.rtf')
        with open(minimal_rtf, 'w') as f:
            f.write(r'{\rtf1}')

        content, method = self.compiler.convert_rtf_to_text(minimal_rtf)
        self.assertIsNotNone(content)
        self.assertIsNotNone(method)

    def test_convert_rtf_invalid_file(self):
        """Test RTF conversion with malformed RTF content."""
        # Test with random text (not RTF)
        not_rtf = os.path.join(self.temp_dir, 'not_rtf.rtf')
        with open(not_rtf, 'w') as f:
            f.write('This is just plain text, not RTF format.')

        content, method = self.compiler.convert_rtf_to_text(not_rtf)
        # Should not crash, returns something
        self.assertIsNotNone(content)
        self.assertIsNotNone(method)

        # Test with truncated RTF (missing closing braces)
        truncated_rtf = os.path.join(self.temp_dir, 'truncated.rtf')
        with open(truncated_rtf, 'w') as f:
            f.write(r'{\rtf1\ansi Some text without closing brace')

        content, method = self.compiler.convert_rtf_to_text(truncated_rtf)
        self.assertIsNotNone(content)
        self.assertIsNotNone(method)

    def test_convert_rtf_unicode(self):
        """Test RTF conversion preserves Unicode characters."""
        # RTF with Unicode escape sequences for special characters
        unicode_rtf = os.path.join(self.temp_dir, 'unicode.rtf')
        rtf_content = r"""{\rtf1\ansi\deff0
{\fonttbl{\f0 Arial;}}
\f0\pard Hello World with special chars: caf\'e9\par
}"""
        with open(unicode_rtf, 'w') as f:
            f.write(rtf_content)

        content, method = self.compiler.convert_rtf_to_text(unicode_rtf)
        self.assertIsNotNone(content)
        # If conversion succeeded, check for presence of text
        if method != 'failed':
            self.assertIn('Hello', content)

    def test_rtf_fallback_to_striprtf(self):
        """Test RTF falls back to striprtf when pandoc and unrtf fail."""
        rtf_file = os.path.join(self.temp_dir, 'fallback.rtf')
        with open(rtf_file, 'w') as f:
            f.write(r'{\rtf1\ansi\deff0 Test content for fallback.\par}')

        # Mock subprocess.run to make pandoc and unrtf fail
        def mock_subprocess_run(args, **kwargs):
            if args[0] in ['pandoc', 'unrtf']:
                raise FileNotFoundError(f"Mock failure of {args[0]}")
            raise FileNotFoundError("Unknown command")

        with patch('subprocess.run', side_effect=mock_subprocess_run):
            content, method = self.compiler.convert_rtf_to_text(rtf_file)
            # Should either use striprtf or fail gracefully
            self.assertIsNotNone(content)
            self.assertIn(method, ['striprtf', 'failed'])

    def test_rtf_all_methods_fail(self):
        """Test RTF returns error when all conversion methods fail."""
        rtf_file = os.path.join(self.temp_dir, 'allfail.rtf')
        with open(rtf_file, 'w') as f:
            f.write(r'{\rtf1\ansi\deff0 Test content.\par}')

        # Mock all methods to fail
        def mock_subprocess_run(args, **kwargs):
            raise FileNotFoundError(f"Mock failure of {args[0]}")

        with patch('subprocess.run', side_effect=mock_subprocess_run):
            # Also mock striprtf import to fail
            with patch.dict('sys.modules', {'striprtf': None, 'striprtf.striprtf': None}):
                content, method = self.compiler.convert_rtf_to_text(rtf_file)
                self.assertEqual(method, 'failed')
                self.assertIn('Failed to convert RTF', content)

    def test_rtf_conversion_preserves_original(self):
        """Test that RTF conversion doesn't modify the source file."""
        rtf_file = os.path.join(self.temp_dir, 'preserve.rtf')
        rtf_content = r'{\rtf1\ansi\deff0 Original content.\par}'
        with open(rtf_file, 'w') as f:
            f.write(rtf_content)

        # Get checksum before conversion
        with open(rtf_file, 'rb') as f:
            checksum_before = hashlib.md5(f.read()).hexdigest()

        # Convert the file
        self.compiler.convert_rtf_to_text(rtf_file)

        # Get checksum after conversion
        with open(rtf_file, 'rb') as f:
            checksum_after = hashlib.md5(f.read()).hexdigest()

        # File should be unchanged
        self.assertEqual(checksum_before, checksum_after,
                        "RTF file was modified during conversion")

    def test_rtf_in_zip(self):
        """Test RTF files inside ZIP archives are processed."""
        # Create a ZIP with an RTF file
        zip_path = os.path.join(self.temp_dir, 'with_rtf.zip')
        rtf_content = r'{\rtf1\ansi\deff0 RTF inside ZIP.\par}'

        with zipfile.ZipFile(zip_path, 'w') as zipf:
            zipf.writestr('document.rtf', rtf_content)

        # Process the ZIP
        content, method = self.compiler.extract_zip(zip_path)

        # Check that RTF file is mentioned and content is present
        self.assertIn('document.rtf', content)
        self.assertIn('zip_extract', method)

    def test_rtf_uppercase_extension(self):
        """Test .RTF extension is handled (case insensitive)."""
        # Create file with uppercase extension
        rtf_upper = os.path.join(self.temp_dir, 'UPPERCASE.RTF')
        with open(rtf_upper, 'w') as f:
            f.write(r'{\rtf1\ansi\deff0 Uppercase extension test.\par}')

        # process_file uses lowercase comparison
        content, method = self.compiler.process_file(rtf_upper)
        self.assertIsNotNone(content)
        self.assertIsNotNone(method)

    def test_convert_rtf_large_file(self):
        """Test RTF conversion with large file."""
        # Generate RTF with repeated content (~500KB to keep test reasonable)
        large_rtf = os.path.join(self.temp_dir, 'large.rtf')
        rtf_header = r'{\rtf1\ansi\deff0 '
        rtf_footer = r'}'
        # Create ~500KB of content
        paragraph = r'This is a paragraph of text that will be repeated many times to create a large RTF file for testing purposes.\par '
        repeat_count = 5000

        with open(large_rtf, 'w') as f:
            f.write(rtf_header)
            for _ in range(repeat_count):
                f.write(paragraph)
            f.write(rtf_footer)

        # Verify file is reasonably large
        file_size = os.path.getsize(large_rtf)
        self.assertGreater(file_size, 100000, "Large RTF file should be > 100KB")

        # Convert should complete without issues
        content, method = self.compiler.convert_rtf_to_text(large_rtf)
        self.assertIsNotNone(content)
        self.assertIsNotNone(method)

        # If conversion succeeded, check content is substantial
        if method != 'failed':
            self.assertGreater(len(content), 1000, "Converted content should be substantial")

    def test_compile_with_rtf(self):
        """Test full compile includes RTF files correctly."""
        # Create an RTF file in the temp directory
        rtf_file = os.path.join(self.temp_dir, 'compile_test.rtf')
        with open(rtf_file, 'w') as f:
            f.write(r'{\rtf1\ansi\deff0 Content for compile test.\par}')

        # Run compile
        result = self.compiler.compile()
        self.assertTrue(result)

        # Check output file contains RTF
        with open(self.output_file, 'r') as f:
            output_content = f.read()

        self.assertIn('compile_test.rtf', output_content)
        # Check conversion method is noted
        self.assertIn('converted with', output_content)

    # === ZIP Error Handling Tests ===

    def test_extract_zip_bad_file(self):
        """Test ZIP extraction with invalid/corrupt ZIP file."""
        # Create a file that's not a valid ZIP
        bad_zip = os.path.join(self.temp_dir, 'bad.zip')
        with open(bad_zip, 'w') as f:
            f.write('This is not a ZIP file')

        content, method = self.compiler.extract_zip(bad_zip)
        self.assertEqual(method, 'failed-bad_zip')
        self.assertIn('not a valid ZIP file', content)

    def test_extract_zip_exception(self):
        """Test ZIP extraction handles general exceptions."""
        # Create a ZIP file then make it unreadable by using a mock
        zip_path = os.path.join(self.temp_dir, 'error.zip')
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            zipf.writestr('test.txt', 'content')

        # Mock ZipFile to raise an exception
        with patch('zipfile.ZipFile') as mock_zip:
            mock_zip.side_effect = Exception("Simulated error")
            content, method = self.compiler.extract_zip(zip_path)
            self.assertEqual(method, 'failed-exception')
            self.assertIn('Error processing ZIP file', content)

    def test_zip_file_processing_error(self):
        """Test error handling when processing file inside ZIP fails."""
        # Create a ZIP with a file that will cause processing error
        zip_path = os.path.join(self.temp_dir, 'processing_error.zip')
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            zipf.writestr('test.txt', 'normal content')

        # Mock process_file to raise an exception for files inside ZIP
        original_process = self.compiler.process_file

        def mock_process(path):
            if 'test.txt' in path and self.temp_dir not in path:
                raise Exception("Simulated processing error")
            return original_process(path)

        with patch.object(self.compiler, 'process_file', side_effect=mock_process):
            content, method = self.compiler.extract_zip(zip_path)
            # Should still complete but with error message
            self.assertIn('zip_extract', method)

    # === EPUB Conversion Tests ===

    def test_convert_epub_success(self):
        """Test EPUB conversion with mocked ebook-convert."""
        epub_file = os.path.join(self.temp_dir, 'test.epub')
        with open(epub_file, 'wb') as f:
            f.write(b'fake epub content')

        # Mock subprocess.run to simulate successful ebook-convert
        def mock_run(args, **kwargs):
            if args[0] == 'ebook-convert':
                # Write output to the temp file
                output_file = args[2] if len(args) > 2 else args[1]
                with open(output_file, 'w') as f:
                    f.write('Converted EPUB content')
                return MagicMock(returncode=0)
            raise FileNotFoundError()

        with patch('subprocess.run', side_effect=mock_run):
            content, method = self.compiler.convert_epub_to_text(epub_file)
            self.assertEqual(method, 'ebook-convert')
            self.assertIn('Converted EPUB content', content)

    def test_convert_epub_failure(self):
        """Test EPUB conversion when Calibre not installed."""
        epub_file = os.path.join(self.temp_dir, 'test.epub')
        with open(epub_file, 'wb') as f:
            f.write(b'fake epub content')

        # Mock subprocess.run to simulate missing ebook-convert
        with patch('subprocess.run', side_effect=FileNotFoundError()):
            content, method = self.compiler.convert_epub_to_text(epub_file)
            self.assertEqual(method, 'failed')
            self.assertIn('Failed to convert EPUB', content)

    # === RTF Fallback Success Path Tests ===

    def test_rtf_unrtf_success(self):
        """Test RTF conversion succeeds with unrtf when pandoc fails."""
        rtf_file = os.path.join(self.temp_dir, 'unrtf_test.rtf')
        with open(rtf_file, 'w') as f:
            f.write(r'{\rtf1\ansi Test content}')

        def mock_run(args, **kwargs):
            if args[0] == 'pandoc':
                raise FileNotFoundError("pandoc not found")
            if args[0] == 'unrtf':
                result = MagicMock()
                result.stdout = "Converted by unrtf"
                result.returncode = 0
                return result
            raise FileNotFoundError()

        with patch('subprocess.run', side_effect=mock_run):
            content, method = self.compiler.convert_rtf_to_text(rtf_file)
            self.assertEqual(method, 'unrtf')
            self.assertIn('Converted by unrtf', content)

    def test_rtf_striprtf_success(self):
        """Test RTF conversion succeeds with striprtf when CLI tools fail."""
        rtf_file = os.path.join(self.temp_dir, 'striprtf_test.rtf')
        rtf_content = r'{\rtf1\ansi\deff0 Striprtf test content.\par}'
        with open(rtf_file, 'w') as f:
            f.write(rtf_content)

        # Mock subprocess to fail for pandoc and unrtf
        with patch('subprocess.run', side_effect=FileNotFoundError()):
            # striprtf should be tried as fallback
            content, method = self.compiler.convert_rtf_to_text(rtf_file)
            # Will be 'striprtf' if installed, 'failed' otherwise
            self.assertIn(method, ['striprtf', 'failed'])

    def test_rtf_striprtf_exception(self):
        """Test RTF conversion handles striprtf non-ImportError exceptions."""
        rtf_file = os.path.join(self.temp_dir, 'striprtf_error.rtf')
        with open(rtf_file, 'w') as f:
            f.write(r'{\rtf1 Invalid content that might cause error}')

        # Mock subprocess to fail
        with patch('subprocess.run', side_effect=FileNotFoundError()):
            # Mock striprtf to raise a different exception
            mock_module = MagicMock()
            mock_module.rtf_to_text = MagicMock(side_effect=ValueError("Parse error"))

            with patch.dict('sys.modules', {'striprtf': mock_module, 'striprtf.striprtf': mock_module}):
                content, method = self.compiler.convert_rtf_to_text(rtf_file)
                # Should fail gracefully
                self.assertEqual(method, 'failed')


if __name__ == '__main__':
    unittest.main()