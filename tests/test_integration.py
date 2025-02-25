import os
import sys
import tempfile
import unittest
import shutil
import subprocess
from pathlib import Path

# Add parent directory to sys.path to import documix
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


class TestIntegration(unittest.TestCase):
    """Integration tests for DocuMix command-line functionality."""

    def setUp(self):
        """Set up test fixtures."""
        # Create a temporary directory for test files
        self.temp_dir = tempfile.mkdtemp()
        self.output_file = os.path.join(self.temp_dir, 'output.md')
        
        # Create some sample test files
        self.create_test_files()

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

        # Create a nested directory with a file
        nested_dir = os.path.join(self.temp_dir, 'nested')
        os.makedirs(nested_dir, exist_ok=True)
        nested_file = os.path.join(nested_dir, 'nested_sample.py')
        with open(nested_file, 'w') as f:
            f.write('# This is a nested Python file\n')

    def test_command_line_basic(self):
        """Test basic command-line functionality."""
        # Skip this test if we're running in a CI environment without documix installed
        if 'CI' in os.environ:
            self.skipTest("Skipping command-line test in CI environment")
        
        try:
            # Test if documix is installed and available in path
            subprocess.run(['documix', '--version'], check=True, capture_output=True)
        except (subprocess.SubprocessError, FileNotFoundError):
            self.skipTest("documix command not found in PATH. Is it installed?")
        
        # Run the documix command
        result = subprocess.run(
            ['documix', self.temp_dir, '-o', self.output_file, '-r'],
            check=False,
            capture_output=True,
            text=True
        )
        
        # Check that the command completed successfully
        self.assertEqual(result.returncode, 0, f"documix command failed with output: {result.stderr}")
        
        # Check that the output file was created
        self.assertTrue(os.path.exists(self.output_file), "Output file was not created")
        
        # Check content of the output file
        with open(self.output_file, 'r') as f:
            content = f.read()
            
        # Check that the file has the expected sections
        self.assertIn('# File Summary', content)
        self.assertIn('# Files', content)
        
        # Check that all files are included
        self.assertIn('sample.py', content)
        self.assertIn('sample.md', content)
        self.assertIn('sample.txt', content)
        
        # Check that nested files are included when using -r
        self.assertIn('nested_sample.py', content)

    def test_command_line_extensions(self):
        """Test command-line functionality with extension filtering."""
        # Skip this test if we're running in a CI environment without documix installed
        if 'CI' in os.environ:
            self.skipTest("Skipping command-line test in CI environment")
        
        try:
            # Test if documix is installed and available
            subprocess.run(['documix', '--version'], check=True, capture_output=True)
        except (subprocess.SubprocessError, FileNotFoundError):
            self.skipTest("documix command not found in PATH. Is it installed?")
        
        # Run the documix command with extension filtering
        result = subprocess.run(
            ['documix', self.temp_dir, '-o', self.output_file, '-e', 'md,txt'],
            check=False,
            capture_output=True,
            text=True
        )
        
        # Check that the command completed successfully
        self.assertEqual(result.returncode, 0, f"documix command failed with output: {result.stderr}")
        
        # Check that the output file was created
        self.assertTrue(os.path.exists(self.output_file), "Output file was not created")
        
        # Check content of the output file
        with open(self.output_file, 'r') as f:
            content = f.read()
            
        # Check that only MD and TXT files are included
        self.assertIn('sample.md', content)
        self.assertIn('sample.txt', content)
        
        # Python files should not be included
        self.assertNotIn('def hello_world():', content)


if __name__ == '__main__':
    unittest.main()