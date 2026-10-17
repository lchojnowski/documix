"""Parallel compile: deterministic order, bounded window, error propagation."""

import os
import random
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from documix.documix import DocumentCompiler, main
from documix.local_ocr import OcrCleanupError


class TestParallelCompile(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.output = os.path.join(self.temp_dir, 'out.md')
        self.names = [f'doc_{i:02d}.txt' for i in range(12)]
        for name in self.names:
            with open(os.path.join(self.temp_dir, name), 'w') as handle:
                handle.write(f'content of {name}')

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _headers(self):
        with open(self.output, encoding='utf-8') as handle:
            return [line.split(' ')[2] for line in handle if line.startswith('## File: ')]

    def test_output_order_is_sorted_regardless_of_completion_order(self):
        compiler = DocumentCompiler(self.temp_dir, self.output, jobs=4)
        threads = set()

        def slow(path):
            threads.add(threading.current_thread().name)
            time.sleep(random.uniform(0.0, 0.03))
            return f'content of {os.path.basename(path)}', 'direct_read'

        with patch.object(compiler, 'process_file', side_effect=slow), patch('builtins.print'):
            self.assertTrue(compiler.compile())
        self.assertEqual(self.names, self._headers())
        self.assertTrue(any(name.startswith('documix') for name in threads))
        self.assertEqual(12, compiler.total_files)
        self.assertEqual(12, len(compiler.file_stats))

    def test_serial_and_parallel_outputs_match(self):
        out_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, out_dir, True)
        parallel = os.path.join(out_dir, 'parallel.md')
        other = os.path.join(out_dir, 'serial.md')
        with patch('builtins.print'):
            DocumentCompiler(self.temp_dir, parallel, jobs=4).compile()
            DocumentCompiler(self.temp_dir, other, jobs=1).compile()

        def body(path):
            with open(path, encoding='utf-8') as handle:
                return [line for line in handle if not line.startswith('- Compilation Date')]

        self.assertEqual(body(other), body(parallel))

    def test_worker_exception_aborts_compile(self):
        compiler = DocumentCompiler(self.temp_dir, self.output, jobs=4)

        def explode(path):
            if path.endswith('doc_03.txt'):
                raise RuntimeError('converter crashed')
            return 'ok', 'direct_read'

        with patch.object(compiler, 'process_file', side_effect=explode), patch('builtins.print'):
            with self.assertRaises(RuntimeError):
                compiler.compile()

    def test_cleanup_error_from_worker_stays_fatal(self):
        compiler = DocumentCompiler(self.temp_dir, self.output, jobs=3)

        def fatal(path):
            if path.endswith('doc_00.txt'):
                raise OcrCleanupError()
            return 'ok', 'direct_read'

        with patch.object(compiler, 'process_file', side_effect=fatal), patch('builtins.print'):
            with self.assertRaises(OcrCleanupError):
                compiler.compile()
        self.assertEqual([], compiler.file_stats)

    def test_emails_run_on_the_main_thread(self):
        for name in ('a.eml', 'b.eml'):
            with open(os.path.join(self.temp_dir, name), 'w') as handle:
                handle.write('From: x@example.com\nSubject: s\n\nbody\n')
        compiler = DocumentCompiler(self.temp_dir, self.output, jobs=4)
        seen = {}

        def record(path):
            seen[os.path.basename(path)] = threading.current_thread() is threading.main_thread()
            return 'ok', 'direct_read'

        with patch.object(compiler, 'process_file', side_effect=record), patch('builtins.print'):
            compiler.compile()
        self.assertTrue(seen['a.eml'])
        self.assertTrue(seen['b.eml'])
        self.assertFalse(all(seen[name] for name in self.names))

    def test_jobs_validation(self):
        for bad in (0, -1, '2', 2.0):
            with self.subTest(jobs=bad):
                with self.assertRaises(ValueError):
                    DocumentCompiler(self.temp_dir, self.output, jobs=bad)
        self.assertEqual(1, DocumentCompiler(self.temp_dir, self.output, jobs=1).jobs)
        self.assertGreaterEqual(DocumentCompiler(self.temp_dir, self.output).jobs, 1)

    def test_cli_passes_jobs_only_when_given(self):
        with patch('documix.cli.DocumentCompiler') as compiler, patch('builtins.print'), \
             patch('sys.argv', ['documix', self.temp_dir, '-j', '2']):
            main()
        self.assertEqual({'jobs': 2}, compiler.call_args.kwargs)
        with patch('documix.cli.DocumentCompiler') as compiler, patch('builtins.print'), \
             patch('sys.argv', ['documix', self.temp_dir]):
            main()
        self.assertEqual({}, compiler.call_args.kwargs)
        with patch('builtins.print'), patch('sys.stderr'), \
             patch('sys.argv', ['documix', self.temp_dir, '-j', '0']):
            with self.assertRaises(SystemExit):
                main()


if __name__ == '__main__':
    unittest.main()
