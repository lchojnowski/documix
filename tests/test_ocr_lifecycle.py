"""Cancellation and uncertain child cleanup must stop the whole conversion."""

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
import zipfile
from unittest.mock import Mock, patch
from types import SimpleNamespace

from documix.documix import DocumentCompiler
from documix.local_ocr import OcrCleanupError, bounded_run


class TestOcrLifecycle(unittest.TestCase):
    def test_unreaped_child_is_fatal_even_when_caller_deadline_expires(self):
        read_fd, write_fd = os.pipe()
        os.close(write_fd)
        stream = os.fdopen(read_fd, 'rb')
        self.addCleanup(stream.close)
        process = SimpleNamespace(
            stdout=stream, poll=Mock(return_value=None), kill=Mock(),
            wait=Mock(side_effect=subprocess.TimeoutExpired('synthetic', 0)),
        )
        with patch('documix.local_ocr.subprocess.Popen', return_value=process):
            with self.assertRaises(OcrCleanupError):
                bounded_run(['synthetic'], time.monotonic() + 0.05, 10)
        process.kill.assert_called_once_with()
        self.assertTrue(stream.closed)

    def test_calls_from_library_threads_preserve_the_callers_signal_handlers(self):
        import signal
        original_handler = signal.getsignal(signal.SIGINT)
        values = []

        def invoke():
            values.append(bounded_run([sys.executable, '-c', 'print("thread")'],
                                      time.monotonic() + 5, 100))

        thread = threading.Thread(target=invoke)
        thread.start()
        thread.join(timeout=10)
        self.assertFalse(thread.is_alive())
        self.assertEqual([b'thread\n'], values)
        self.assertIs(original_handler, signal.getsignal(signal.SIGINT))

    def test_interrupt_during_popen_construction_reaps_created_child(self):
        script = textwrap.dedent('''
            import json, os, signal, subprocess, sys, time
            from unittest.mock import patch
            from documix.local_ocr import bounded_run
            original = subprocess.Popen
            children = []
            def interrupted_construction(*args, **kwargs):
                child = original(*args, **kwargs)
                children.append(child)
                if sys.argv[1] == 'construction':
                    os.kill(os.getpid(), signal.SIGINT)
                else:
                    original_wait = child.wait
                    signalled = []
                    def interrupted_wait(*args, **kwargs):
                        if not signalled:
                            signalled.append(True)
                            os.kill(os.getpid(), signal.SIGINT)
                        return original_wait(*args, **kwargs)
                    child.wait = interrupted_wait
                return child
            interrupted = False
            try:
                with patch('documix.local_ocr.subprocess.Popen',
                           side_effect=interrupted_construction):
                    try:
                        bounded_run([sys.executable, '-c',
                                     'import os,time; os.close(1); time.sleep(30)'],
                                    time.monotonic() + 10, 100)
                    except KeyboardInterrupt:
                        interrupted = True
                stopped = bool(children) and children[0].poll() is not None
                print(json.dumps({'interrupted': interrupted, 'stopped': stopped}))
            finally:
                for child in children:
                    if child.poll() is None:
                        child.kill()
                    child.wait(timeout=2)
        ''')
        for phase in ('construction', 'wait_after_stdout_closed'):
            with self.subTest(phase=phase):
                result = subprocess.run([sys.executable, '-c', script, phase],
                                        capture_output=True, text=True, timeout=15)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual({'interrupted': True, 'stopped': True},
                                 json.loads(result.stdout))

    def test_cleanup_failure_aborts_direct_zip_and_email_compilation(self):
        with tempfile.TemporaryDirectory() as directory:
            pdf = os.path.join(directory, 'source.pdf')
            with open(pdf, 'wb') as stream:
                stream.write(b'%PDF-1.4 synthetic')
            archive = os.path.join(directory, 'source.zip')
            with zipfile.ZipFile(archive, 'w') as stream:
                stream.write(pdf, 'source.pdf')
            email = os.path.join(directory, 'source.eml')
            with open(email, 'w') as stream:
                stream.write('Subject: Synthetic\n\nSynthetic message\n')

            for source in (pdf, archive, email):
                with self.subTest(extension=os.path.splitext(source)[1]), \
                     patch('documix.documix.local_ocr.convert_pdf',
                           side_effect=OcrCleanupError()), \
                     patch('documix.compiler.EmailProcessor') as processor:
                    processor.return_value.metadata = {}
                    processor.return_value.compile_output.return_value = (
                        'Synthetic message', [{'path': pdf, 'filename': 'source.pdf',
                                               'size': 18}],
                    )
                    compiler = DocumentCompiler(
                        source, os.path.join(directory, 'out.md'),
                        converter_config={'pdf': ['tesseract', 'pdftotext']},
                    )
                    with patch.object(compiler, '_try_pdf_pdftotext',
                                      return_value=('Later text', 'pdftotext')) as later:
                        with self.assertRaises(OcrCleanupError):
                            compiler.compile()
                        later.assert_not_called()
                    self.assertEqual([], compiler.file_stats)
