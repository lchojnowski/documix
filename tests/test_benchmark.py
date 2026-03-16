import json
import os
import sys
import tempfile
import shutil
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from documix.documix import (
    check_converter_availability,
    word_similarity,
    benchmark_main,
    run_benchmark,
    _extension_to_format,
    main,
    CONVERTER_DEFAULTS,
)
from tests.conftest import get_fastest_converter_config, RANKING_PATH


class TestWordSimilarity(unittest.TestCase):
    """Tests for the word_similarity function."""

    def test_identical_texts(self):
        self.assertEqual(word_similarity("hello world", "hello world"), 1.0)

    def test_empty_texts(self):
        self.assertEqual(word_similarity("", ""), 1.0)

    def test_one_empty(self):
        self.assertEqual(word_similarity("hello", ""), 0.0)
        self.assertEqual(word_similarity("", "hello"), 0.0)

    def test_partial_overlap(self):
        score = word_similarity("the quick brown fox", "the slow brown fox")
        self.assertGreater(score, 0.0)
        self.assertLess(score, 1.0)

    def test_no_overlap(self):
        score = word_similarity("aaa bbb ccc", "xxx yyy zzz")
        self.assertEqual(score, 0.0)


class TestExtensionToFormat(unittest.TestCase):
    """Tests for _extension_to_format."""

    def test_known_extensions(self):
        self.assertEqual(_extension_to_format('.pdf'), 'pdf')
        self.assertEqual(_extension_to_format('.docx'), 'docx')
        self.assertEqual(_extension_to_format('.rtf'), 'rtf')
        self.assertEqual(_extension_to_format('.doc'), 'doc')

    def test_case_insensitive(self):
        self.assertEqual(_extension_to_format('.PDF'), 'pdf')

    def test_unknown_extension(self):
        self.assertIsNone(_extension_to_format('.xyz'))
        self.assertIsNone(_extension_to_format('.txt'))


class TestCheckConverterAvailability(unittest.TestCase):
    """Tests for check_converter_availability."""

    @patch('documix.documix.PDFPLUMBER_AVAILABLE', False)
    @patch('documix.documix.DOCX2TXT_AVAILABLE', False)
    @patch('shutil.which', return_value=None)
    @patch('subprocess.run', side_effect=FileNotFoundError)
    def test_nothing_available(self, mock_run, mock_which):
        result = check_converter_availability()
        self.assertEqual(result['pdf'], [])
        self.assertEqual(result['docx'], [])
        # striprtf checked via import, not shutil.which
        self.assertNotIn('pandoc', result['rtf'])

    @patch('documix.documix.PDFPLUMBER_AVAILABLE', True)
    @patch('documix.documix.DOCX2TXT_AVAILABLE', True)
    @patch('shutil.which', return_value='/usr/bin/dummy')
    @patch('subprocess.run')
    def test_everything_available(self, mock_run, mock_which):
        result = check_converter_availability()
        self.assertIn('paddleocr', result['pdf'])
        self.assertIn('pdfplumber', result['pdf'])
        self.assertIn('markitdown-uvx', result['pdf'])
        self.assertIn('pandoc', result['docx'])
        self.assertIn('docx2txt', result['docx'])
        self.assertIn('pandoc', result['rtf'])


class TestBenchmarkMain(unittest.TestCase):
    """Tests for benchmark_main argument parsing."""

    @patch('documix.documix.run_benchmark')
    def test_default_args(self, mock_run):
        benchmark_main([])
        mock_run.assert_called_once_with(
            files=[],
            runs=3,
            output_dir='benchmark/',
            formats='all',
        )

    @patch('documix.documix.run_benchmark')
    def test_custom_args(self, mock_run):
        benchmark_main([
            'file1.pdf', 'file2.docx',
            '--runs', '5',
            '--output-dir', '/tmp/bench',
            '--formats', 'pdf',
        ])
        mock_run.assert_called_once_with(
            files=['file1.pdf', 'file2.docx'],
            runs=5,
            output_dir='/tmp/bench',
            formats='pdf',
        )


class TestMainRouting(unittest.TestCase):
    """Test that main() routes to benchmark_main for the benchmark subcommand."""

    @patch('documix.documix.benchmark_main')
    def test_benchmark_subcommand(self, mock_bench):
        with patch.object(sys, 'argv', ['documix', 'benchmark', '--runs', '1']):
            main()
        mock_bench.assert_called_once_with(['--runs', '1'])

    @patch('documix.documix.benchmark_main')
    @patch('documix.documix.print_logo')
    def test_normal_command_no_benchmark(self, mock_logo, mock_bench):
        """Regular usage should NOT call benchmark_main."""
        with patch.object(sys, 'argv', ['documix', '/some/folder']):
            try:
                main()
            except (SystemExit, FileNotFoundError):
                pass
        mock_bench.assert_not_called()


class TestRunBenchmark(unittest.TestCase):
    """Tests for run_benchmark with mocked converters."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.output_dir = os.path.join(self.temp_dir, 'bench_out')
        # Create a tiny test PDF (not a real PDF, just for path matching)
        self.test_pdf = os.path.join(self.temp_dir, 'test.pdf')
        with open(self.test_pdf, 'w') as f:
            f.write('%PDF-1.4 fake')

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    @patch('documix.documix.check_converter_availability')
    @patch.object(
        __import__('documix.documix', fromlist=['DocumentCompiler']).DocumentCompiler,
        'convert_pdf_to_text',
        return_value=("Sample extracted text from PDF", "pdftotext")
    )
    def test_benchmark_produces_json(self, mock_convert, mock_avail):
        mock_avail.return_value = {
            'pdf': ['pdftotext'],
            'docx': [],
            'rtf': [],
        }
        results, rankings = run_benchmark(
            files=[self.test_pdf],
            runs=1,
            output_dir=self.output_dir,
            formats='pdf',
        )

        # Check results structure
        self.assertIn('timestamp', results)
        self.assertIn('system', results)
        self.assertIn('files', results)

        # Check JSON files were written
        self.assertTrue(os.path.exists(
            os.path.join(self.output_dir, 'results.json')
        ))
        self.assertTrue(os.path.exists(
            os.path.join(self.output_dir, 'converter_ranking.json')
        ))

        # Validate JSON is parseable
        with open(os.path.join(self.output_dir, 'results.json')) as f:
            loaded = json.load(f)
        self.assertIn('timestamp', loaded)

        with open(os.path.join(self.output_dir, 'converter_ranking.json')) as f:
            loaded_rankings = json.load(f)
        self.assertIsInstance(loaded_rankings, dict)


class TestGetFastestConverterConfig(unittest.TestCase):
    """Tests for conftest.get_fastest_converter_config."""

    def test_no_file_returns_empty(self):
        with patch('tests.conftest.os.path.exists', return_value=False):
            result = get_fastest_converter_config()
        self.assertEqual(result, {})

    def test_reads_ranking_file(self):
        temp_dir = tempfile.mkdtemp()
        try:
            ranking_file = os.path.join(temp_dir, 'converter_ranking.json')
            data = {
                'pdf': ['pdftotext', 'pdfplumber'],
                'docx': ['pandoc'],
                'rtf': [],
            }
            with open(ranking_file, 'w') as f:
                json.dump(data, f)

            with patch('tests.conftest.RANKING_PATH', ranking_file):
                with patch('tests.conftest.os.path.exists', return_value=True):
                    with patch('builtins.open', unittest.mock.mock_open(
                        read_data=json.dumps(data)
                    )):
                        result = get_fastest_converter_config()

            self.assertEqual(result.get('pdf'), ['pdftotext'])
            self.assertEqual(result.get('docx'), ['pandoc'])
            self.assertNotIn('rtf', result)
        finally:
            shutil.rmtree(temp_dir)


class TestBenchmarkEdgePaths(unittest.TestCase):
    """Tests for benchmark edge cases."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.output_dir = os.path.join(self.temp_dir, 'bench_out')
        self.test_pdf = os.path.join(self.temp_dir, 'test.pdf')
        with open(self.test_pdf, 'w') as f:
            f.write('%PDF-1.4 fake')

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    @patch('documix.documix.check_converter_availability')
    def test_benchmark_converter_exception(self, mock_avail):
        """Converter raises during benchmark run."""
        mock_avail.return_value = {
            'pdf': ['pdftotext'],
            'docx': [],
            'rtf': [],
        }
        with patch.object(
            __import__('documix.documix', fromlist=['DocumentCompiler']).DocumentCompiler,
            'convert_pdf_to_text',
            side_effect=RuntimeError("converter crash")
        ):
            results, rankings = run_benchmark(
                files=[self.test_pdf],
                runs=1,
                output_dir=self.output_dir,
                formats='pdf',
            )
            # Should complete without raising
            self.assertIn('files', results)
            # The converter should have failed
            file_results = results['files'].get(self.test_pdf, {})
            if 'pdftotext' in file_results:
                self.assertFalse(file_results['pdftotext']['success'])

    @patch('documix.documix.check_converter_availability')
    def test_benchmark_no_successful_converters(self, mock_avail):
        """All converters fail -> accuracy=0.0."""
        mock_avail.return_value = {
            'pdf': ['pdftotext'],
            'docx': [],
            'rtf': [],
        }
        with patch.object(
            __import__('documix.documix', fromlist=['DocumentCompiler']).DocumentCompiler,
            'convert_pdf_to_text',
            return_value=("[Failed to convert PDF]", "failed")
        ):
            results, rankings = run_benchmark(
                files=[self.test_pdf],
                runs=1,
                output_dir=self.output_dir,
                formats='pdf',
            )
            file_results = results['files'].get(self.test_pdf, {})
            if 'pdftotext' in file_results:
                self.assertEqual(file_results['pdftotext']['accuracy'], 0.0)


if __name__ == '__main__':
    unittest.main()
