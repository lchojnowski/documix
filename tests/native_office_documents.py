"""Explicit real Office-parser gate; missing optional runtime is a failure."""
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

from documix.documix import DocumentCompiler


class TestNativeOfficeDocuments(unittest.TestCase):
    def setUp(self):
        tool = shutil.which('markitdown')
        self.assertIsNotNone(tool, 'Install markitdown[xlsx,pptx] in a Python >=3.10 venv and add its bin directory to PATH')
        self.assertTrue(os.access(os.path.join(os.path.dirname(os.path.realpath(tool)), 'python'), os.X_OK))
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.fixtures = Path(__file__).parent / 'fixtures' / 'office_documents'

    def test_default_compilation_extracts_real_spreadsheet_and_presentation_markers(self):
        for extension, marker in (('xlsx', 'FABRICATED SPREADSHEET REQUIREMENT 73219'), ('pptx', 'FABRICATED PRESENTATION REQUIREMENT 85471')):
            with self.subTest(extension=extension):
                source = self.fixtures / ('scope.' + extension)
                checksum = hashlib.sha256(source.read_bytes()).hexdigest()
                output = Path(self.directory.name) / (extension + '.md')
                compiler = DocumentCompiler(str(source), str(output))
                self.assertTrue(compiler.compile())
                text = output.read_text()
                self.assertIn(marker, text)
                self.assertIn('converted with markitdown', text)
                self.assertNotIn('[Failed', text)
                self.assertEqual(checksum, hashlib.sha256(source.read_bytes()).hexdigest())

    def test_empty_and_image_only_documents_do_not_succeed_with_generated_headings(self):
        for name in ('empty.xlsx', 'empty.pptx', 'image_only.pptx'):
            with self.subTest(name=name):
                source = self.fixtures / name
                checksum = hashlib.sha256(source.read_bytes()).hexdigest()
                compiler = DocumentCompiler(str(source), os.path.join(self.directory.name, 'out.md'))
                text, method = compiler.process_file(str(source))
                self.assertEqual('failed', method)
                self.assertTrue(text.startswith('[Failed to convert '))
                self.assertEqual(checksum, hashlib.sha256(source.read_bytes()).hexdigest())

    def test_malformed_office_archive_never_falls_back_to_generic_zip_converter(self):
        for extension, member in (('xlsx', 'xl/workbook.xml'), ('pptx', 'ppt/presentation.xml')):
            with self.subTest(extension=extension):
                source = Path(self.directory.name) / ('malformed.' + extension)
                with zipfile.ZipFile(source, 'w') as archive:
                    archive.writestr('[Content_Types].xml', '<Types/>')
                    archive.writestr(member, '<invalid/>')
                    archive.writestr('readme.txt', 'FABRICATED ARCHIVE DISTRACTOR')
                compiler = DocumentCompiler(str(source), os.path.join(self.directory.name, 'out.md'))
                text, method = compiler.process_file(str(source))
                self.assertEqual('failed', method)
                self.assertTrue(text.startswith('[Failed to convert '))
                self.assertNotIn('DISTRACTOR', text)

    def test_strict_assessment_rejects_requirement_present_only_in_embedded_image(self):
        from documix import office_documents
        for extension in ('xlsx', 'pptx'):
            with self.subTest(extension=extension):
                source = self.fixtures / ('image_requirement.' + extension)
                checksum = hashlib.sha256(source.read_bytes()).hexdigest()
                # Existing clients retain text extraction. The strict profile
                # must not mistake its readable cover for complete assessment.
                text = office_documents.convert(str(source))
                self.assertIn('FABRICATED OFFICE COVER', text)
                self.assertNotIn('SIEM REQUIREMENT 63827', text)
                with self.assertRaises(office_documents.OfficeError) as error:
                    office_documents.convert(str(source), require_text_only=True)
                self.assertEqual('unassessed_media', error.exception.code)
                self.assertEqual(checksum, hashlib.sha256(source.read_bytes()).hexdigest())

    def test_strict_assessment_rejects_external_image_relationship_without_fetch(self):
        from documix import office_documents
        source = Path(self.directory.name) / 'linked.xlsx'
        with zipfile.ZipFile(source, 'w') as archive:
            archive.writestr('[Content_Types].xml', '<Types/>')
            archive.writestr('xl/workbook.xml', '<workbook/>')
            archive.writestr('xl/_rels/workbook.xml.rels',
                            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                            '<Relationship Id="rImage" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" TargetMode="External" Target="https://example.invalid/synthetic.png"/>'
                            '</Relationships>')
        with self.assertRaises(office_documents.OfficeError) as error:
            office_documents.convert(str(source), require_text_only=True)
        self.assertEqual('unassessed_media', error.exception.code)
