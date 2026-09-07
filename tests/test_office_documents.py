"""Office attachments must yield document text, never raw ZIP bytes."""
import os
import struct
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from documix.documix import DocumentCompiler


class TestOfficeDispatch(unittest.TestCase):
    def test_default_collection_includes_spreadsheets_and_presentations(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = []
            for extension in ('xlsx', 'pptx'):
                path = os.path.join(directory, 'scope.' + extension)
                with zipfile.ZipFile(path, 'w') as archive:
                    archive.writestr('[Content_Types].xml', '<Types/>')
                paths.append(path)
            compiler = DocumentCompiler(directory, os.path.join(directory, 'out.md'))
            self.assertEqual(sorted(paths), sorted(compiler.collect_files()))

    def test_office_dispatch_uses_converter_without_binary_read_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            compiler = DocumentCompiler(directory, os.path.join(directory, 'out.md'))
            for extension in ('xlsx', 'pptx'):
                with self.subTest(extension=extension), \
                     patch('documix.documix.office_documents.convert', return_value='SYNTHETIC REQUIREMENT') as convert, \
                     patch.object(compiler, 'convert_txt_to_text', side_effect=AssertionError('binary fallback')):
                    source = os.path.join(directory, 'scope.' + extension)
                    self.assertEqual(('SYNTHETIC REQUIREMENT', 'markitdown'), compiler.process_file(source))
                    convert.assert_called_once_with(source)

    def test_missing_parser_is_failure_instead_of_apparent_success(self):
        from documix import office_documents
        with tempfile.TemporaryDirectory() as directory:
            compiler = DocumentCompiler(directory, os.path.join(directory, 'out.md'))
            with patch('documix.documix.office_documents.convert', side_effect=office_documents.OfficeError('tool_unavailable')):
                text, method = compiler.process_file(os.path.join(directory, 'scope.xlsx'))
            self.assertEqual('failed', method)
            self.assertEqual('[Failed to convert XLSX file: tool_unavailable]', text)

    def test_cleanup_uncertainty_remains_fatal(self):
        from documix import local_ocr
        with tempfile.TemporaryDirectory() as directory:
            compiler = DocumentCompiler(directory, os.path.join(directory, 'out.md'))
            with patch('documix.documix.office_documents.convert', side_effect=local_ocr.OcrCleanupError()):
                with self.assertRaises(local_ocr.OcrCleanupError):
                    compiler.process_file(os.path.join(directory, 'scope.pptx'))


class TestBoundedOfficeParser(unittest.TestCase):
    def setUp(self):
        from documix import office_documents
        self.office = office_documents
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.source = os.path.join(self.temporary.name, 'scope.xlsx')
        self.write_archive()
        tool_directory = os.path.join(self.temporary.name, 'parser', 'bin')
        os.makedirs(tool_directory)
        tool_directory = os.path.realpath(tool_directory)
        self.interpreter = os.path.join(tool_directory, 'python')
        os.symlink(sys.executable, self.interpreter)
        self.tool = patch.object(self.office.shutil, 'which', return_value=os.path.join(tool_directory, 'markitdown')).start()
        self.run = patch.object(self.office.local_ocr, 'bounded_run', return_value=b'FABRICATED SCOPE').start()
        self.addCleanup(patch.stopall)

    def write_archive(self, additional=(), compression=zipfile.ZIP_STORED):
        with zipfile.ZipFile(self.source, 'w', compression=compression) as archive:
            archive.writestr('[Content_Types].xml', '<Types/>')
            archive.writestr('xl/workbook.xml', '<workbook/>')
            for name, body in additional:
                archive.writestr(name, body)

    def reject(self, code, **options):
        with self.assertRaises(self.office.OfficeError) as error:
            self.office.convert(self.source, **options)
        self.assertEqual(code, error.exception.code)
        self.run.assert_not_called()

    def test_parser_receives_private_read_only_copy_and_original_is_unchanged(self):
        with open(self.source, 'rb') as stream:
            before = stream.read()
        staged = []

        def convert(arguments, deadline, limit):
            self.assertEqual(self.interpreter, arguments[0])
            self.assertEqual(['-I', '-B'], arguments[1:3])
            self.assertEqual('office_parser.py', os.path.basename(arguments[3]))
            self.assertEqual('.xlsx', arguments[4])
            self.assertEqual(6, len(arguments))
            self.assertNotEqual(self.source, arguments[5])
            staged.append(arguments[5])
            self.assertEqual(0o400, os.stat(arguments[5]).st_mode & 0o777)
            with open(arguments[5], 'rb') as stream:
                self.assertEqual(before, stream.read())
            self.assertEqual(self.office.MAX_TEXT_BYTES, limit)
            return b'FABRICATED SCOPE'

        self.run.side_effect = convert
        self.assertEqual('FABRICATED SCOPE', self.office.convert(self.source))
        self.assertFalse(os.path.exists(staged[0]))
        with open(self.source, 'rb') as stream:
            self.assertEqual(before, stream.read())

    def test_missing_parser_does_not_attempt_download_or_fallback(self):
        self.tool.return_value = None
        self.reject('tool_unavailable')

    def test_unknown_console_installation_is_rejected_without_shebang_execution(self):
        os.unlink(self.interpreter)
        self.reject('tool_unavailable')

    def test_rejects_non_office_extension(self):
        self.source = os.path.join(self.temporary.name, 'archive.zip')
        self.reject('unsupported_format')

    def test_rejects_input_symlink(self):
        original = self.source
        self.source = os.path.join(self.temporary.name, 'link.xlsx')
        os.symlink(original, self.source)
        self.reject('invalid_document')

    def test_rejects_input_above_limit_before_parser(self):
        with patch.object(self.office, 'MAX_INPUT_BYTES', 1):
            self.reject('input_limit')

    def test_rejects_member_count_above_limit(self):
        with patch.object(self.office, 'MAX_MEMBERS', 1):
            self.reject('archive_limit')

    def test_rejects_member_size_above_limit(self):
        with patch.object(self.office, 'MAX_MEMBER_BYTES', 2):
            self.reject('archive_limit')

    def test_rejects_total_expanded_size_above_limit(self):
        with patch.object(self.office, 'MAX_EXPANDED_BYTES', 12):
            self.reject('archive_limit')

    def test_rejects_high_compression_ratio(self):
        self.write_archive([('xl/padding.xml', 'A' * 65536)], compression=zipfile.ZIP_DEFLATED)
        with patch.object(self.office, 'MAX_COMPRESSION_RATIO', 10):
            self.reject('archive_limit')

    def test_rejects_traversal_absolute_and_backslash_member_names(self):
        for name in ('../outside.txt', '/outside.txt', 'xl\\outside.txt'):
            with self.subTest(name=name):
                self.write_archive([(name, 'payload')])
                self.reject('invalid_archive')

    def test_rejects_archive_symlink(self):
        member = zipfile.ZipInfo('xl/link.xml')
        member.create_system = 3
        member.external_attr = 0o120777 << 16
        self.write_archive([(member, '/outside')])
        self.reject('invalid_archive')

    def test_rejects_duplicate_member_names(self):
        with self.assertWarns(UserWarning):
            self.write_archive([('xl/workbook.xml', 'different')])
        self.reject('invalid_archive')

    def test_rejects_unsupported_compression(self):
        self.write_archive(compression=zipfile.ZIP_BZIP2)
        self.reject('unsupported_archive')

    def test_rejects_invalid_zip_and_missing_required_office_parts(self):
        with open(self.source, 'wb') as stream:
            stream.write(b'not a zip file')
        self.reject('invalid_document')
        with zipfile.ZipFile(self.source, 'w') as archive:
            archive.writestr('file.txt', 'not an office document')
        self.reject('invalid_archive')

    def test_rejects_corrupt_member_before_starting_parser(self):
        with open(self.source, 'rb') as stream:
            content = stream.read()
        with open(self.source, 'wb') as stream:
            stream.write(content.replace(b'<Types/>', b'<TypXs/>'))
        self.reject('invalid_document')

    def test_rejects_corrupt_deflate_stream_without_leaking_zlib_error(self):
        self.write_archive(compression=zipfile.ZIP_DEFLATED)
        with open(self.source, 'rb') as stream:
            content = bytearray(stream.read())
        start = 30 + struct.unpack_from('<H', content, 26)[0] + struct.unpack_from('<H', content, 28)[0]
        content[start] = 0xFF
        with open(self.source, 'wb') as stream:
            stream.write(content)
        self.reject('invalid_document')

    def test_parser_error_timeout_and_output_limit_are_explicit_failures(self):
        for code in ('tool_failed', 'timeout', 'output_limit'):
            with self.subTest(code=code):
                self.run.side_effect = self.office.local_ocr.OcrError(code)
                with self.assertRaises(self.office.OfficeError) as error:
                    self.office.convert(self.source)
                self.assertEqual(code, error.exception.code)

    def test_empty_invalid_utf8_and_oversized_output_never_succeed(self):
        for body, code in ((b' \n\t', 'empty_document'), (b'\xff', 'invalid_document'), (b'X' * 33, 'output_limit')):
            with self.subTest(code=code), patch.object(self.office, 'MAX_TEXT_BYTES', 32):
                self.run.return_value = body
                with self.assertRaises(self.office.OfficeError) as error:
                    self.office.convert(self.source)
                self.assertEqual(code, error.exception.code)

    def test_source_replacement_during_conversion_is_detected(self):
        def convert(*arguments):
            with open(self.source, 'ab') as stream:
                stream.write(b'changed')
            return b'FABRICATED SCOPE'
        self.run.side_effect = convert
        with self.assertRaises(self.office.OfficeError) as error:
            self.office.convert(self.source)
        self.assertEqual('source_changed', error.exception.code)

    def test_process_cleanup_uncertainty_remains_fatal(self):
        self.run.side_effect = self.office.local_ocr.OcrCleanupError()
        with self.assertRaises(self.office.local_ocr.OcrCleanupError):
            self.office.convert(self.source)

    def test_strictness_must_be_boolean_before_tool_or_source_access(self):
        for value in ('false', 'true', 0, 1, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.office.convert(self.source, require_text_only=value)
        self.tool.assert_not_called()
        self.run.assert_not_called()

    def test_strict_profile_rejects_embedded_spreadsheet_and_presentation_images(self):
        for name in ('xl/media/image1.png', 'ppt/media/image1.png'):
            with self.subTest(name=name):
                self.write_archive([(name, b'fabricated image bytes')])
                self.reject('unassessed_media', require_text_only=True)

    def test_default_profile_keeps_existing_office_text_conversion_with_images(self):
        self.write_archive([('xl/media/image1.png', b'fabricated image bytes')])
        self.assertEqual('FABRICATED SCOPE', self.office.convert(self.source))
        self.run.assert_called_once()

    def test_strict_profile_rejects_internal_and_external_image_relationships(self):
        for external in (False, True):
            for encoding in ('utf-8', 'utf-16'):
                with self.subTest(external=external, encoding=encoding):
                    mode = ' TargetMode="External"' if external else ''
                    body = ('<?xml version="1.0" encoding="{}"?>'
                            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                            '<Relationship Id="rImage" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="https://example.invalid/synthetic.png"{} />'
                            '</Relationships>').format(encoding, mode).encode(encoding)
                    self.write_archive([('xl/_rels/workbook.xml.rels', body)])
                    self.reject('unassessed_media', require_text_only=True)

    def test_strict_profile_rejects_relationship_dtd_before_entity_expansion(self):
        body = ('<!DOCTYPE Relationships [<!ENTITY payload "image">]>'
                '<Relationships><Relationship Type="&payload;"/></Relationships>')
        self.write_archive([('xl/_rels/workbook.xml.rels', body)])
        self.reject('invalid_archive', require_text_only=True)

    def test_strict_profile_rejects_malformed_relationship_xml(self):
        self.write_archive([('xl/_rels/workbook.xml.rels', '<Relationships')])
        self.reject('invalid_document', require_text_only=True)

    def test_strict_profile_allows_non_image_links_without_fetching_them(self):
        body = ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rLink" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://example.invalid/reference" TargetMode="External" />'
                '</Relationships>')
        self.write_archive([('xl/_rels/workbook.xml.rels', body)])
        self.assertEqual('FABRICATED SCOPE', self.office.convert(self.source, require_text_only=True))
        self.run.assert_called_once()


class TestSelectedOfficeParser(unittest.TestCase):
    def test_child_forbids_network_and_additional_processes(self):
        from documix import office_parser
        for event in ('socket.connect', 'socket.getaddrinfo', 'subprocess.Popen', 'os.system', 'os.posix_spawn', 'os.fork'):
            with self.subTest(event=event), self.assertRaises(RuntimeError):
                office_parser._deny_external(event, ())

    def test_format_checks_ignore_non_content_values(self):
        from documix import office_parser
        for value in (None, '', ' \n\t', '\u200b\ufeff'):
            with self.subTest(value=value):
                self.assertFalse(office_parser._has_content(value))
        self.assertTrue(office_parser._has_content(0))
        self.assertTrue(office_parser._has_content('FABRICATED REQUIREMENT'))


if __name__ == '__main__':
    unittest.main()
