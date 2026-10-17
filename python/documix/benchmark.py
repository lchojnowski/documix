"""``documix benchmark``: time every available converter on sample files."""
import argparse
import datetime
import json
import os
import platform
import re
import time

from . import textutils, tools
from .compiler import DocumentCompiler


def _extension_to_format(ext):
    """Map a file extension to a format name."""
    ext = ext.lower()
    mapping = {
        '.pdf': 'pdf',
        '.docx': 'docx',
        '.rtf': 'rtf',
        '.doc': 'doc',
        '.epub': 'epub',
    }
    return mapping.get(ext)


def run_benchmark(files, runs=3, output_dir='benchmark/', formats='all'):
    """Run benchmark across converters for the given files.

    Args:
        files: list of file paths to benchmark
        runs: number of timing iterations per converter
        output_dir: directory for results
        formats: 'all' or comma-separated format names to benchmark
    """
    available = tools.check_converter_availability(all_converters=True)
    allowed_formats = None
    if formats != 'all':
        allowed_formats = set(f.strip() for f in formats.split(','))

    # Discover resource files
    # Shared sample documents live at the repository root (python/ is a subdir).
    resources_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        'resources'
    )
    resource_files = []
    if os.path.isdir(resources_dir):
        for root, _, fnames in os.walk(resources_dir):
            for fname in fnames:
                resource_files.append(os.path.join(root, fname))

    all_files = resource_files + list(files)

    # Group files by format
    files_by_format = {}
    for fpath in all_files:
        _, ext = os.path.splitext(fpath)
        fmt = _extension_to_format(ext)
        if fmt is None:
            continue
        converter_fmt = fmt
        if allowed_formats and converter_fmt not in allowed_formats:
            continue
        files_by_format.setdefault(converter_fmt, []).append(
            (fpath, fmt)
        )

    os.makedirs(output_dir, exist_ok=True)
    outputs_dir = os.path.join(output_dir, 'outputs')
    os.makedirs(outputs_dir, exist_ok=True)

    results = {
        'timestamp': datetime.datetime.now().isoformat(),
        'system': {
            'platform': platform.platform(),
            'python': platform.python_version(),
        },
        'runs': runs,
        'files': {},
    }
    rankings = {}  # {format: [converter ordered by speed]}

    convert_methods = {
        'pdf': 'convert_pdf_to_text',
        'docx': 'convert_docx_to_text',
        'rtf': 'convert_rtf_to_text',
        'doc': 'convert_doc_to_text',
        'epub': 'convert_epub_to_text',
    }

    print("\n=== DocuMix Benchmark ===\n")

    for converter_fmt, file_list in sorted(files_by_format.items()):
        converters = available.get(converter_fmt, [])
        if not converters:
            print(f"[{converter_fmt.upper()}] No converters available, skipping")
            continue

        for fpath, actual_fmt in file_list:
            fname = os.path.basename(fpath)
            print(f"\n--- {fname} ({actual_fmt.upper()}) ---")
            print(f"{'Converter':<20} {'Mean (s)':<12} {'Min (s)':<12} "
                  f"{'Max (s)':<12} {'Length':<10} {'Accuracy':<10}")
            print("-" * 76)

            file_results = {}
            converter_outputs = {}

            for conv_name in converters:
                method_name = convert_methods[actual_fmt]
                compiler = DocumentCompiler(
                    source_path=fpath,
                    output_file='/dev/null',
                    converter_config={converter_fmt: [conv_name]}
                )
                method = getattr(compiler, method_name)

                timings = []
                output_text = None
                success = False

                for i in range(runs):
                    try:
                        start = time.perf_counter()
                        text, used_method = method(fpath)
                        elapsed = time.perf_counter() - start
                        if text and not text.startswith('[Failed'):
                            timings.append(elapsed)
                            if output_text is None:
                                output_text = text
                            success = True
                    except Exception as e:
                        print(f"  {conv_name}: error - {e}")
                        break

                if success and timings:
                    mean_t = sum(timings) / len(timings)
                    file_results[conv_name] = {
                        'mean': round(mean_t, 4),
                        'min': round(min(timings), 4),
                        'max': round(max(timings), 4),
                        'output_length': len(output_text),
                        'success': True,
                    }
                    converter_outputs[conv_name] = output_text

                    safe_fname = re.sub(r'[^\w.]', '_', fname)
                    out_path = os.path.join(
                        outputs_dir, f"{safe_fname}_{conv_name}.md"
                    )
                    with open(out_path, 'w', encoding='utf-8') as f:
                        f.write(output_text)
                else:
                    file_results[conv_name] = {
                        'mean': None, 'min': None, 'max': None,
                        'output_length': 0, 'success': False,
                    }

            # Compute accuracy: reference = longest output
            if converter_outputs:
                reference = max(converter_outputs.values(), key=len)
                for conv_name, text in converter_outputs.items():
                    score = textutils.word_similarity(reference, text)
                    file_results[conv_name]['accuracy'] = round(score, 4)
            else:
                for conv_name in file_results:
                    file_results[conv_name]['accuracy'] = 0.0

            for conv_name in converters:
                r = file_results.get(conv_name)
                if r is None:
                    continue
                if r['success']:
                    print(f"{conv_name:<20} {r['mean']:<12.4f} "
                          f"{r['min']:<12.4f} {r['max']:<12.4f} "
                          f"{r['output_length']:<10} "
                          f"{r['accuracy']:<10.4f}")
                else:
                    print(f"{conv_name:<20} {'FAILED':<12} "
                          f"{'-':<12} {'-':<12} {'-':<10} {'-':<10}")

            results['files'][fpath] = file_results

            successful = [
                (name, r) for name, r in file_results.items()
                if r['success']
            ]
            if successful:
                max_mean = max(r['mean'] for _, r in successful)
                for name, r in successful:
                    speed_norm = 1.0 - (r['mean'] / max_mean) if max_mean > 0 else 1.0
                    acc = r.get('accuracy', 0.0)
                    # Weight accuracy higher (0.6 accuracy, 0.4 speed)
                    r['combined_score'] = round(0.4 * speed_norm + 0.6 * acc, 4)

                ranked = sorted(
                    successful,
                    key=lambda x: x[1]['combined_score'],
                    reverse=True
                )
                fmt_ranking = [name for name, _ in ranked]
                if converter_fmt not in rankings:
                    rankings[converter_fmt] = fmt_ranking
                else:
                    existing = rankings[converter_fmt]
                    for name in fmt_ranking:
                        if name not in existing:
                            existing.append(name)

    results_path = os.path.join(output_dir, 'results.json')
    with open(results_path, 'w') as f:
        json.dump(results, f, indent=2)

    ranking_path = os.path.join(output_dir, 'converter_ranking.json')
    with open(ranking_path, 'w') as f:
        json.dump(rankings, f, indent=2)

    print(f"\nResults saved to {results_path}")
    print(f"Rankings saved to {ranking_path}")
    print(f"Raw outputs saved to {outputs_dir}/")

    return results, rankings


def benchmark_main(argv=None):
    """Entry point for the benchmark subcommand."""
    parser = argparse.ArgumentParser(
        prog='documix benchmark',
        description='Benchmark document converters for speed and accuracy. '
                    'All files in resources/ are benchmarked automatically.'
    )
    parser.add_argument(
        'files', nargs='*', default=[],
        help='Additional files to benchmark (resources/ files are always included)'
    )
    parser.add_argument(
        '--runs', type=int, default=3,
        help='Number of timing iterations per converter (default: 3)'
    )
    parser.add_argument(
        '--output-dir', default='benchmark/',
        help='Directory for benchmark results (default: benchmark/)'
    )
    parser.add_argument(
        '--formats', default='all',
        help='Formats to benchmark: pdf, docx, doc, rtf, epub, or all (default: all)'
    )

    args = parser.parse_args(argv)

    run_benchmark(
        files=args.files,
        runs=args.runs,
        output_dir=args.output_dir,
        formats=args.formats,
    )
