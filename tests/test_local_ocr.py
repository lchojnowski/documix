"""Local OCR is explicit, bounded, and never accepts a partial document."""

import os
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from documix.local_ocr import (
    OCR_DEFAULTS, OcrError, bounded_run, convert_pdf, validate_config,
)


class TestLocalOcr(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.source = os.path.join(self.directory.name, '-source.pdf')
        with open(self.source, 'wb') as stream:
            stream.write(b'%PDF-1.4 synthetic')
        self.calls = []
        self.page_texts = [b'First real page', b'Second real page']

    def fake_run(self, argv, deadline, max_bytes):
        self.calls.append(argv)
        command = os.path.basename(argv[0])
        if command == 'pdfinfo':
            if '-f' not in argv:
                return b'Pages: 2\nEncrypted: no\n'
            return (b'Page 1 size: 612 x 792 pts\n'
                    b'Page 2 size: 612 x 792 pts\n')
        if command == 'pdftoppm':
            return b'P5\n2 2\n255\n' + bytes([255, 0, 255, 0])
        if '--list-langs' in argv:
            return b'List of available languages (2):\neng\npol\n'
        return self.page_texts.pop(0)

    def run_ocr(self, config=None):
        with patch('documix.local_ocr.shutil.which',
                   side_effect=lambda name: '/tools/' + name), \
             patch('documix.local_ocr.bounded_run', side_effect=self.fake_run):
            return convert_pdf(self.source, config)

    def test_valid_pages_preserve_order_and_source_and_cleanup(self):
        before = os.stat(self.source)
        text = self.run_ocr({'languages': 'pol+eng'})
        self.assertEqual('First real page\n\n---\n\nSecond real page', text)
        self.assertEqual(before.st_size, os.stat(self.source).st_size)
        self.assertEqual(before.st_mtime_ns, os.stat(self.source).st_mtime_ns)
        ocr_calls = [call for call in self.calls
                     if os.path.basename(call[0]) == 'tesseract'
                     and '--list-langs' not in call]
        self.assertEqual(2, len(ocr_calls))
        self.assertTrue(all(call[2] == 'stdout' for call in ocr_calls))
        self.assertTrue(all(not os.path.exists(call[1]) for call in ocr_calls))
        render_calls = [call for call in self.calls
                        if os.path.basename(call[0]) == 'pdftoppm']
        self.assertEqual(['1', '2'], [call[call.index('-f') + 1]
                                     for call in render_calls])
        self.assertTrue(all(call[-1] == self.source for call in render_calls))

    def test_partial_or_empty_document_is_not_success(self):
        for empty in (b'', b'\f \n', '\u200b\ufeff'.encode()):
            with self.subTest(empty=empty):
                self.page_texts = [b'First real page', empty]
                with self.assertRaises(OcrError) as error:
                    self.run_ocr()
                self.assertEqual('empty_page', error.exception.code)

    def test_proven_white_page_does_not_discard_content_from_other_page(self):
        original = self.fake_run

        def with_blank_page(argv, deadline, max_bytes):
            if os.path.basename(argv[0]) == 'pdftoppm' and argv[argv.index('-f') + 1] == '2':
                return b'P5\n2 2\n255\n' + b'\xff' * 4
            return original(argv, deadline, max_bytes)

        self.fake_run = with_blank_page
        self.assertEqual('First real page\n\n---\n\n', self.run_ocr())
        self.assertEqual([b'Second real page'], self.page_texts)

    def test_all_white_pages_are_not_extracted_document_content(self):
        original = self.fake_run

        def only_blank_pages(argv, deadline, max_bytes):
            if os.path.basename(argv[0]) == 'pdftoppm':
                return b'P5\n2 2\n255\n' + b'\xff' * 4
            return original(argv, deadline, max_bytes)

        self.fake_run = only_blank_pages
        with self.assertRaises(OcrError) as error:
            self.run_ocr()
        self.assertEqual('empty_document', error.exception.code)

    def test_missing_language_stops_before_render(self):
        with self.assertRaises(OcrError) as error:
            self.run_ocr({'languages': 'deu'})
        self.assertEqual('language_unavailable', error.exception.code)
        self.assertFalse(any(os.path.basename(c[0]) == 'pdftoppm'
                             for c in self.calls))

    def test_invalid_rasters_never_reach_text_recognition(self):
        original = self.fake_run
        for raster, expected in (
            (b'P6\n2 2\n255\n' + bytes(12), 'invalid_raster'),
            (b'P5\n2 2\n255\n' + bytes(3), 'invalid_raster'),
            (b'P5\n4001 1\n255\n' + bytes(4001), 'pixel_limit'),
        ):
            with self.subTest(expected=expected):
                self.calls.clear()

                def malformed(argv, deadline, max_bytes):
                    if os.path.basename(argv[0]) == 'pdftoppm':
                        return raster
                    return original(argv, deadline, max_bytes)

                self.fake_run = malformed
                with self.assertRaises(OcrError) as error:
                    self.run_ocr()
                self.assertEqual(expected, error.exception.code)
                self.assertFalse(any('stdout' in call for call in self.calls))

    def test_later_tool_failure_discards_partial_output_and_cleans_workspace(self):
        original = self.fake_run
        paths = []

        def fail_second_page(argv, deadline, max_bytes):
            if 'stdout' in argv:
                paths.append(argv[1])
                if len(paths) == 2:
                    raise OcrError('tool_failed')
            return original(argv, deadline, max_bytes)

        self.fake_run = fail_second_page
        with self.assertRaises(OcrError) as error:
            self.run_ocr()
        self.assertEqual('tool_failed', error.exception.code)
        self.assertEqual(2, len(paths))
        self.assertTrue(all(not os.path.exists(os.path.dirname(p)) for p in paths))

    def test_source_changed_during_conversion_refuses_result(self):
        original = self.fake_run

        def changed_source(argv, deadline, max_bytes):
            result = original(argv, deadline, max_bytes)
            if 'stdout' in argv and not self.page_texts:
                with open(self.source, 'ab') as stream:
                    stream.write(b'changed')
            return result

        self.fake_run = changed_source
        with self.assertRaises(OcrError) as error:
            self.run_ocr()
        self.assertEqual('source_changed', error.exception.code)

    def test_page_limit_stops_before_render(self):
        with self.assertRaises(OcrError) as error:
            self.run_ocr({'max_pages': 1})
        self.assertEqual('page_limit', error.exception.code)
        self.assertFalse(any(os.path.basename(c[0]) == 'pdftoppm'
                             for c in self.calls))

    def test_invalid_configuration_never_starts_tools(self):
        invalid = [
            {'max_pages': 101}, {'max_pages': 0}, {'max_pages': True},
            {'dpi': 201}, {'dpi': -1}, {'timeout': 301},
            {'languages': '../eng'}, {'languages': 'eng --help'},
            {'languages': 'eng+'}, {'languages': 'eng\npol'},
            {'unknown': 1}, [],
        ]
        for config in invalid:
            with self.subTest(config=config):
                with self.assertRaises(ValueError):
                    validate_config(config)
        self.assertEqual(OCR_DEFAULTS, validate_config(None))

    def test_missing_tool_does_not_start_any_process(self):
        with patch('documix.local_ocr.shutil.which', return_value=None), \
             patch('documix.local_ocr.bounded_run') as process:
            with self.assertRaises(OcrError) as error:
                convert_pdf(self.source)
        self.assertEqual('tool_unavailable', error.exception.code)
        process.assert_not_called()

    def test_malformed_or_missing_page_geometry_refuses_before_render(self):
        original = self.fake_run
        for metadata in (b'Page 1 size: nan x 792 pts\n',
                         b'Page 1 size: 612 x 792 pts\n',
                         b'Page 1 size: -1 x 792 pts\n'):
            with self.subTest(metadata=metadata):
                def malformed(argv, deadline, max_bytes):
                    if os.path.basename(argv[0]) == 'pdfinfo' and '-f' in argv:
                        return metadata
                    return original(argv, deadline, max_bytes)
                self.fake_run = malformed
                with self.assertRaises(OcrError):
                    self.run_ocr()
        self.fake_run = original


class TestBoundedOcrProcess(unittest.TestCase):
    def test_exact_output_and_nonzero_failure(self):
        self.assertEqual(b'valid', bounded_run(
            [sys.executable, '-c', 'print("valid", end="")'],
            time.monotonic() + 5, 5))
        with self.assertRaises(OcrError) as error:
            bounded_run([sys.executable, '-c', 'raise SystemExit(2)'],
                        time.monotonic() + 5, 10)
        self.assertEqual('tool_failed', error.exception.code)

    def test_timeout_and_output_limit_fail_without_partial_bytes(self):
        for code, limit, budget, expected in (
            ('import time; time.sleep(10)', 100, 0.1, 'timeout'),
            ('print("x" * 10000)', 10, 5, 'output_limit'),
        ):
            with self.subTest(expected=expected):
                before = time.monotonic()
                with self.assertRaises(OcrError) as error:
                    bounded_run([sys.executable, '-c', code],
                                time.monotonic() + budget, limit)
                self.assertEqual(expected, error.exception.code)
                self.assertLess(time.monotonic() - before, 3)
