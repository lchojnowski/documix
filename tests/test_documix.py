import os
import sys
import tempfile
import unittest
import zipfile
import shutil
from pathlib import Path

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
            source_dir=self.temp_dir,
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
            source_dir=self.temp_dir,
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
            source_dir=self.temp_dir,
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
            source_dir=self.temp_dir,
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
            source_dir=self.temp_dir,
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


if __name__ == '__main__':
    unittest.main()