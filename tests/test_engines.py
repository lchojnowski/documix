"""anydoc / LiteParse engine contract: fail-fast on engine failures, fall
through on document-level failures, LiteParse never fatal."""

import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import anydoc as real_anydoc  # hard dependency of documix

from documix.documix import DocumentCompiler, EngineError, main
from documix.converters import anydoc as anydoc_engine
from documix.converters import liteparse as liteparse_engine

RESOURCES = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'resources')


class _Scan(real_anydoc.NeedsOcrError):
    """A document-level anydoc error that is cheap to construct."""

    def __init__(self):
        Exception.__init__(self, 'scanned pages')


class _Encrypted(real_anydoc.EncryptedError):
    def __init__(self):
        Exception.__init__(self, 'password protected')


class TestAnydocEngine(unittest.TestCase):
    def setUp(self):
        anydoc_engine.require()  # make sure the lazy module is loaded
        self.temp_dir = tempfile.mkdtemp()
        self.output = os.path.join(self.temp_dir, 'out.md')
        self.docx = os.path.join(self.temp_dir, 'report.docx')
        with open(self.docx, 'wb') as handle:
            handle.write(b'not really a docx')
        self.compiler = DocumentCompiler(self.temp_dir, self.output, jobs=1)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_success_is_written_raw_as_markdown(self):
        with patch('documix.converters.anydoc.anydoc.to_markdown', return_value='# Title\n\n|a|b|'):
            self.assertEqual(('# Title\n\n|a|b|', 'anydoc'), self.compiler.process_file(self.docx))
        self.assertFalse(DocumentCompiler._is_fenced(self.docx, 'anydoc'))

    def test_document_level_errors_fall_through_to_liteparse(self):
        for error in (_Scan(), _Encrypted(), FileNotFoundError('gone')):
            with self.subTest(error=type(error).__name__), \
                 patch('documix.converters.anydoc.anydoc.to_markdown', side_effect=error), \
                 patch.object(self.compiler, 'convert_with_liteparse',
                              return_value=('ocr text', 'liteparse')) as fallback:
                self.assertEqual(('ocr text', 'liteparse'), self.compiler.process_file(self.docx))
                fallback.assert_called_once_with(self.docx)

    def test_empty_output_falls_through(self):
        with patch('documix.converters.anydoc.anydoc.to_markdown', return_value=' \n\n'), \
             patch.object(self.compiler, 'convert_with_liteparse', return_value=(None, None)):
            text, method = self.compiler.process_file(self.docx)
        self.assertEqual('failed', method)
        self.assertEqual('[Failed to convert DOCX file: report.docx]', text)

    def test_unexpected_exception_is_an_engine_error(self):
        with patch('documix.converters.anydoc.anydoc.to_markdown', side_effect=RuntimeError('boom')), \
             patch.object(self.compiler, 'convert_with_liteparse') as fallback:
            with self.assertRaises(EngineError):
                self.compiler.process_file(self.docx)
        fallback.assert_not_called()

    def test_engine_error_escapes_zip_and_email_handlers(self):
        archive = os.path.join(self.temp_dir, 'bundle.zip')
        with zipfile.ZipFile(archive, 'w') as bundle:
            bundle.write(self.docx, 'inner.docx')
        eml = os.path.join(self.temp_dir, 'mail.eml')
        with open(eml, 'w', encoding='utf-8') as handle:
            handle.write('From: a@example.com\nTo: b@example.com\nSubject: hi\n'
                         'Content-Type: multipart/mixed; boundary="B"\n\n--B\n'
                         'Content-Type: text/plain\n\nbody\n--B\n'
                         'Content-Type: application/octet-stream\n'
                         'Content-Disposition: attachment; filename="att.docx"\n'
                         'Content-Transfer-Encoding: base64\n\nbm90IGEgZG9jeA==\n--B--\n')
        with patch('documix.converters.anydoc.anydoc.to_markdown', side_effect=RuntimeError('boom')):
            with self.assertRaises(EngineError):
                self.compiler.extract_zip(archive)
            with self.assertRaises(EngineError):
                self.compiler.process_email(eml)

    def test_compile_removes_partial_output_on_engine_error(self):
        with open(os.path.join(self.temp_dir, 'a.txt'), 'w') as handle:
            handle.write('plain text')
        with patch('documix.converters.anydoc.anydoc.to_markdown', side_effect=RuntimeError('boom')):
            with self.assertRaises(EngineError):
                self.compiler.compile()
        self.assertFalse(os.path.exists(self.output))

    def test_missing_engine_fails_require_and_convert(self):
        with patch('documix.converters.anydoc.anydoc', None):
            self.assertFalse(anydoc_engine.is_available())
            with self.assertRaises(EngineError):
                anydoc_engine.require()
            with self.assertRaises(EngineError):
                anydoc_engine.convert(self.docx)

    def test_cli_exits_before_work_when_engine_is_missing(self):
        with patch('documix.converters.anydoc.anydoc', None), \
             patch('documix.cli.DocumentCompiler') as compiler, \
             patch('builtins.print'), \
             patch('sys.argv', ['documix', self.temp_dir, '-o', self.output]):
            with self.assertRaises(SystemExit) as stop:
                main()
        self.assertEqual(1, stop.exception.code)
        compiler.assert_not_called()

    def test_cli_exits_one_and_drops_output_on_engine_crash(self):
        with patch('documix.converters.anydoc.anydoc.to_markdown', side_effect=RuntimeError('boom')), \
             patch('builtins.print'), \
             patch('sys.argv', ['documix', self.temp_dir, '-o', self.output, '-j', '1']):
            with self.assertRaises(SystemExit) as stop:
                main()
        self.assertEqual(1, stop.exception.code)
        self.assertFalse(os.path.exists(self.output))

    def test_require_text_only_rejects_office_media_without_fallback(self):
        pptx = os.path.join(self.temp_dir, 'deck.pptx')
        with open(pptx, 'wb') as handle:
            handle.write(b'pptx bytes')
        compiler = DocumentCompiler(self.temp_dir, self.output, office_require_text_only=True, jobs=1)
        document = MagicMock(assets=[object()])
        with patch('documix.converters.anydoc.anydoc.to_document', return_value=document), \
             patch('documix.converters.anydoc.anydoc.format_from_path', return_value='pptx'), \
             patch.object(compiler, 'convert_with_liteparse') as fallback:
            self.assertEqual(('[Failed to convert PPTX file: unassessed_media]', 'failed'),
                             compiler.process_file(pptx))
        fallback.assert_not_called()

    def test_require_text_only_accepts_media_free_office_files(self):
        xlsx = os.path.join(self.temp_dir, 'sheet.xlsx')
        with open(xlsx, 'wb') as handle:
            handle.write(b'xlsx bytes')
        compiler = DocumentCompiler(self.temp_dir, self.output, office_require_text_only=True, jobs=1)
        with patch('documix.converters.anydoc.anydoc.to_document', return_value=MagicMock(assets=[])), \
             patch('documix.converters.anydoc.anydoc.format_from_path', return_value='xlsx'), \
             patch('documix.converters.anydoc.anydoc.to_markdown_bytes', return_value='|a|b|'):
            self.assertEqual(('|a|b|', 'anydoc'), compiler.process_file(xlsx))


class TestLiteParseEngine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.pdf = os.path.join(self.temp_dir, 'scan.pdf')
        with open(self.pdf, 'wb') as handle:
            handle.write(b'%PDF-1.4 fake')

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        liteparse_engine.shutdown()

    def test_success(self):
        parser = MagicMock()
        parser.parse.return_value = MagicMock(text='# OCR\n\ntext')
        with patch('documix.converters.liteparse._get_parser', return_value=parser):
            self.assertEqual(('# OCR\n\ntext', 'liteparse'), liteparse_engine.convert(self.pdf, jobs=2))

    def test_parse_failure_is_not_fatal(self):
        parser = MagicMock()
        parser.parse.side_effect = RuntimeError('pdfium exploded')
        with patch('documix.converters.liteparse._get_parser', return_value=parser), \
             patch('builtins.print'):
            self.assertEqual((None, None), liteparse_engine.convert(self.pdf))

    def test_missing_package_is_not_fatal(self):
        with patch('documix.converters.liteparse.is_available', return_value=False), \
             patch('builtins.print'):
            self.assertEqual((None, None), liteparse_engine.convert(self.pdf))

    def test_office_inputs_are_serialised(self):
        parser = MagicMock()
        parser.parse.return_value = MagicMock(text='slides')
        with patch('documix.converters.liteparse._get_parser', return_value=parser), \
             patch.object(liteparse_engine, '_OFFICE_LOCK') as lock:
            liteparse_engine.convert(os.path.join(self.temp_dir, 'deck.pptx'))
        lock.__enter__.assert_called_once()


class TestNativeEngines(unittest.TestCase):
    """Real conversions on the bundled samples (no mocks)."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.output = os.path.join(self.temp_dir, 'out.md')

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        liteparse_engine.shutdown()

    def test_anydoc_converts_sample_documents(self):
        compiler = DocumentCompiler(RESOURCES, self.output, recursive=True, jobs=1)
        for name in ('sample_test.docx', 'one_megabyte/example_1mb.doc',
                     'invoice_with_tables/digitalocean_invoice_with_tables.pdf'):
            with self.subTest(name=name):
                text, method = compiler.process_file(os.path.join(RESOURCES, name))
                self.assertEqual('anydoc', method)
                self.assertGreater(len(text.strip()), 100)

    @unittest.skipUnless(liteparse_engine.is_available(), 'liteparse not installed')
    def test_liteparse_converts_sample_pdf(self):
        compiler = DocumentCompiler(RESOURCES, self.output, recursive=True,
                                    converter_config={'pdf': ['liteparse']}, jobs=1)
        text, method = compiler.process_file(
            os.path.join(RESOURCES, 'invoice_with_tables', 'digitalocean_invoice_with_tables.pdf'))
        self.assertEqual('liteparse', method)
        self.assertIn('invoice', text.lower())

    def test_strict_office_policy_on_real_fixtures(self):
        fixtures = os.path.join(os.path.dirname(__file__), 'fixtures', 'office_documents')
        compiler = DocumentCompiler(fixtures, self.output, office_require_text_only=True, jobs=1)
        for name in ('image_requirement.xlsx', 'image_requirement.pptx'):
            with self.subTest(name=name):
                label = name.rsplit('.', 1)[1].upper()
                self.assertEqual((f'[Failed to convert {label} file: unassessed_media]', 'failed'),
                                 compiler.process_file(os.path.join(fixtures, name)))
        text, method = compiler.process_file(os.path.join(fixtures, 'scope.xlsx'))
        self.assertEqual('anydoc', method)
        self.assertNotIn('[Failed', text)

    def test_scanned_pdf_falls_through_to_liteparse(self):
        if not liteparse_engine.is_available():
            self.skipTest('liteparse not installed')
        scan = os.path.join(os.path.dirname(__file__), 'fixtures', 'pdf_coverage', 'text_then_scan.pdf')
        compiler = DocumentCompiler(os.path.dirname(scan), self.output, jobs=1)
        with patch('builtins.print'):
            text, method = compiler.process_file(scan)
        self.assertEqual('liteparse', method)
        self.assertTrue(text.strip())

    def test_compile_resources_parallel_matches_serial(self):
        serial = os.path.join(self.temp_dir, 'serial.md')
        parallel = os.path.join(self.temp_dir, 'parallel.md')
        with patch('builtins.print'):
            self.assertTrue(DocumentCompiler(RESOURCES, serial, recursive=True, jobs=1).compile())
            self.assertTrue(DocumentCompiler(RESOURCES, parallel, recursive=True, jobs=4).compile())

        def body(path):
            with open(path, encoding='utf-8') as handle:
                return [line for line in handle if not line.startswith('- Compilation Date')]

        self.assertEqual(body(serial), body(parallel))
        self.assertIn('## File: sample_test.docx (converted with anydoc)\n', body(serial))


if __name__ == '__main__':
    unittest.main()
