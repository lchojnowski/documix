#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest
import tempfile
import os
import shutil
from documix.documix import EmailProcessor, DocumentCompiler

class TestEmailProcessing(unittest.TestCase):
    """Test email processing functionality."""
    
    def setUp(self):
        """Set up test environment."""
        self.test_dir = tempfile.mkdtemp()
        self.email_content = """From: test@example.com
To: recipient@example.com
Subject: Test Email
Date: Mon, 1 Jan 2025 12:00:00 +0000
Message-ID: <test123@example.com>
Content-Type: multipart/mixed; boundary="boundary123"

--boundary123
Content-Type: text/plain

This is a test email body.

--boundary123
Content-Type: text/html

<html><body><p>This is a <b>test</b> email body.</p></body></html>

--boundary123
Content-Type: application/pdf; name="test.pdf"
Content-Disposition: attachment; filename="test.pdf"
Content-Transfer-Encoding: base64

JVBERi0xLjQKJeLjz9MKCg==

--boundary123--
"""
        
    def tearDown(self):
        """Clean up test environment."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def test_email_parsing(self):
        """Test basic email parsing."""
        # Create test email file
        email_path = os.path.join(self.test_dir, "test.eml")
        with open(email_path, 'w') as f:
            f.write(self.email_content)
        
        # Test email parsing
        processor = EmailProcessor(email_path)
        self.assertTrue(processor.parse_email())
        
        # Check metadata extraction
        self.assertEqual(processor.metadata['from'], 'test@example.com')
        self.assertEqual(processor.metadata['to'], 'recipient@example.com')
        self.assertEqual(processor.metadata['subject'], 'Test Email')
        self.assertEqual(processor.metadata['message_id'], '<test123@example.com>')
    
    def test_attachment_folder_detection(self):
        """Test attachment folder auto-detection."""
        # Create email and attachments folder
        email_path = os.path.join(self.test_dir, "test.eml")
        with open(email_path, 'w') as f:
            f.write(self.email_content)
        
        attachments_dir = os.path.join(self.test_dir, "attachments")
        os.makedirs(attachments_dir)
        
        # Create a dummy attachment
        attachment_path = os.path.join(attachments_dir, "document.txt")
        with open(attachment_path, 'w') as f:
            f.write("Test attachment content")
        
        # Test auto-detection
        processor = EmailProcessor(email_path)
        self.assertIsNotNone(processor.attachments_dir)
        self.assertTrue(os.path.exists(processor.attachments_dir))
        
        # Process attachments
        processor.parse_email()
        processor.process_attachments()
        
        # Check that folder attachments were used
        self.assertTrue(processor.use_folder_attachments)
        self.assertEqual(len(processor.attachments), 1)
        self.assertEqual(processor.attachments[0]['filename'], 'document.txt')
    
    def test_email_body_extraction(self):
        """Test email body extraction and HTML conversion."""
        email_path = os.path.join(self.test_dir, "test.eml")
        with open(email_path, 'w') as f:
            f.write(self.email_content)
        
        processor = EmailProcessor(email_path)
        processor.parse_email()
        
        body = processor.get_email_body()
        self.assertIn("test", body.lower())
        self.assertIn("**test**", body)  # HTML bold should convert to markdown
    
    def test_compile_output(self):
        """Test email output compilation."""
        email_path = os.path.join(self.test_dir, "test.eml")
        with open(email_path, 'w') as f:
            f.write(self.email_content)
        
        processor = EmailProcessor(email_path)
        processor.parse_email()
        processor.process_attachments()
        
        output, attachments = processor.compile_output()
        
        # Check output structure
        self.assertIn("# Email Document:", output)
        self.assertIn("## Email Metadata", output)
        self.assertIn("## Email Content", output)
        self.assertIn("From**: test@example.com", output)
    
    def test_document_compiler_integration(self):
        """Test integration with DocumentCompiler."""
        # Create test email
        email_path = os.path.join(self.test_dir, "test.eml")
        with open(email_path, 'w') as f:
            f.write(self.email_content)
        
        # Create output file path
        output_path = os.path.join(self.test_dir, "output.md")
        
        # Test compilation
        compiler = DocumentCompiler(
            self.test_dir,
            output_path,
            recursive=False
        )
        
        # Process the email
        content, method, email_info = compiler.process_email(email_path)

        # Check results
        self.assertIsNotNone(content)
        self.assertIn("email", method)
        self.assertIn("Email Document:", content)
        self.assertIsInstance(email_info, dict)
    
    def test_mode_detection(self):
        """Test processing mode detection."""
        # Single email
        compiler = DocumentCompiler(self.test_dir, "output.md")
        email_file = os.path.join(self.test_dir, "test.eml")
        self.assertEqual(compiler.detect_processing_mode([email_file]), "single_email")

        # Multiple emails (now returns 'standard' after email_collection mode was removed)
        email1 = os.path.join(self.test_dir, "test1.eml")
        email2 = os.path.join(self.test_dir, "test2.eml")
        self.assertEqual(compiler.detect_processing_mode([email1, email2]), "standard")

        # Mixed content
        email_file = os.path.join(self.test_dir, "test.eml")
        pdf_file = os.path.join(self.test_dir, "doc.pdf")
        self.assertEqual(compiler.detect_processing_mode([email_file, pdf_file]), "standard")

        # Multiple files (returns 'standard' for any multiple files)
        files = [
            os.path.join(self.test_dir, "test1.eml"),
            os.path.join(self.test_dir, "test2.eml"),
            os.path.join(self.test_dir, "test3.eml"),
            os.path.join(self.test_dir, "test4.eml"),
            os.path.join(self.test_dir, "doc.pdf")
        ]
        self.assertEqual(compiler.detect_processing_mode(files), "standard")
    
    def test_email_specific_format(self):
        """Test email-specific output format."""
        # Create test email
        email_path = os.path.join(self.test_dir, "test.eml")
        with open(email_path, 'w') as f:
            f.write(self.email_content)
        
        output_path = os.path.join(self.test_dir, "output.md")
        
        # Test single email format
        compiler = DocumentCompiler(email_path, output_path)
        compiler.compile()
        
        # Check output
        with open(output_path, 'r') as f:
            content = f.read()
        
        # Should have email-specific headers
        self.assertIn("# Email Analysis Report", content)
        self.assertIn("Processing mode: Single Email", content)
        self.assertIn("## Email Summary", content)
        self.assertIn("## Email Details", content)
        self.assertIn("### Message Information", content)
        
        # Should NOT have standard format headers
        self.assertNotIn("merged representation of all documents", content)
        self.assertNotIn("## Purpose", content)
        self.assertNotIn("packed representation", content)
    
    def test_force_format_flags(self):
        """Test forcing output format with flags."""
        email_path = os.path.join(self.test_dir, "test.eml")
        with open(email_path, 'w') as f:
            f.write(self.email_content)

        output_path = os.path.join(self.test_dir, "output.md")

        # Force standard format for single email (overrides auto-detection)
        compiler = DocumentCompiler(email_path, output_path, force_format='standard')
        mode = compiler.detect_processing_mode([email_path])
        self.assertEqual(mode, 'standard')

        # Without force_format, single email should use 'single_email' mode
        compiler2 = DocumentCompiler(email_path, output_path)
        mode2 = compiler2.detect_processing_mode([email_path])
        self.assertEqual(mode2, 'single_email')

if __name__ == '__main__':
    unittest.main()