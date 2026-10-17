#!/usr/bin/env python3
"""Benchmark the Python CLI against the Rust port.

Scenarios: (1) cold start on single files, (2) the 220-file corpus with -j 1
and the auto default, (3) a ~2000-file folder with 10% scanned PDFs.
Measures wall time, user+sys CPU and peak RSS through `/usr/bin/time -l`.

Usage: python scripts/bench_port.py [--out BENCHMARK.md] [--quick]
"""
import argparse
import json
import os
import platform
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESOURCES = os.path.join(REPO, 'resources')
PYTHON_DIR = os.path.join(REPO, 'python')
FIXTURES = os.path.join(PYTHON_DIR, 'tests', 'fixtures')
PY = os.path.join(REPO, '.venv', 'bin', 'python')
RS = os.path.join(REPO, 'target', 'release', 'documix')
TIME = '/usr/bin/time'

SAMPLES = {
    'big_pdf': ('one_megabyte/example_pdf.pdf', 40),
    'invoices': ('invoice_with_tables/digitalocean_invoice_with_tables.pdf', 40),
    'doc': ('one_megabyte/example_1mb.doc', 40),
    'docx': ('sample_test.docx', 40),
}
SCAN = os.path.join(FIXTURES, 'pdf_coverage', 'text_then_scan.pdf')


def build_corpus(root, multiplier, scans):
    for sub, (rel, n) in SAMPLES.items():
        src = os.path.join(RESOURCES, rel)
        ext = os.path.splitext(rel)[1]
        for m in range(multiplier):
            d = os.path.join(root, f'{sub}_{m}')
            os.makedirs(d, exist_ok=True)
            for i in range(n):
                shutil.copyfile(src, os.path.join(d, f'{sub}_{i:03d}{ext}'))
    d = os.path.join(root, 'scans')
    os.makedirs(d, exist_ok=True)
    for i in range(scans):
        shutil.copyfile(SCAN, os.path.join(d, f'scan_{i:03d}.pdf'))
    d = os.path.join(root, 'text')
    os.makedirs(d, exist_ok=True)
    for m in range(multiplier):
        for i in range(40):
            with open(os.path.join(d, f'note_{m}_{i:03d}.md'), 'w') as fh:
                fh.write(f'# Note {m}-{i}\n\n' + ('Lorem ipsum dolor sit amet. ' * 200) + '\n')
    return sum(len(f) for _, _, f in os.walk(root))


def tree_rss_mb(pgid):
    """Sum of RSS over every process in the process group (MB)."""
    try:
        out = subprocess.run(['ps', '-axo', 'pgid=,rss='], capture_output=True, text=True).stdout
    except OSError:
        return 0.0
    total = 0
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] == str(pgid):
            total += int(parts[1])
    return total / 1024.0


def timed(cmd, cwd=PYTHON_DIR):
    """Run under /usr/bin/time -l in its own process group. Wall time is
    measured around the process itself (stdout/stderr go to files so the
    child never blocks on a full pipe); a sampler thread records the peak RSS
    of the whole process tree every 50 ms, so Python's LiteParse OCR worker
    processes are counted. Short runs fall back to the direct child's RSS."""
    import threading
    with tempfile.NamedTemporaryFile(delete=False) as out_f, tempfile.NamedTemporaryFile(delete=False) as err_f:
        out_path, err_path = out_f.name, err_f.name
    peak = [0.0]
    stop = threading.Event()
    with open(out_path, 'w') as out_fh, open(err_path, 'w') as err_fh:
        t = time.perf_counter()
        proc = subprocess.Popen([TIME, '-l'] + cmd, cwd=cwd, stdout=out_fh, stderr=err_fh, start_new_session=True)

        def sample():
            while not stop.is_set():
                peak[0] = max(peak[0], tree_rss_mb(proc.pid))
                stop.wait(0.05)

        sampler = threading.Thread(target=sample, daemon=True)
        sampler.start()
        proc.wait()
        wall = time.perf_counter() - t
        stop.set()
        sampler.join(timeout=2)
    stdout = open(out_path, errors='replace').read()
    stderr = open(err_path, errors='replace').read()
    os.unlink(out_path)
    os.unlink(err_path)
    user = sys_ = None
    child_rss = None
    for line in stderr.splitlines():
        m = re.match(r'\s*([\d.]+)\s+real\s+([\d.]+)\s+user\s+([\d.]+)\s+sys', line)
        if m:
            user, sys_ = float(m.group(2)), float(m.group(3))
        m = re.match(r'\s*(\d+)\s+maximum resident set size', line)
        if m:
            child_rss = int(m.group(1)) / (1024 * 1024)
    rss = max(peak[0], child_rss or 0.0)
    return {'wall': wall, 'user': user, 'sys': sys_, 'rss_mb': rss, 'rc': proc.returncode,
            'compile_s': float(re.search(r'Time: ([0-9.]+) seconds', stdout).group(1)) if 'Time:' in stdout else None}


def impl_cmd(impl, args):
    return ([PY, '-m', 'documix'] if impl == 'python' else [RS]) + args


def measure(label, args, reps, out_dir):
    rows = {}
    for impl in ('python', 'rust'):
        samples = []
        for i in range(reps):
            out = os.path.join(out_dir, f'{impl}_{re.sub(r"[^\w]+", "_", label)}_{i}.md')
            if os.path.exists(out):
                os.remove(out)
            r = timed(impl_cmd(impl, args + ['-o', out]))
            if r['rc'] != 0:
                print(f'  {impl} {label}: rc={r["rc"]}', file=sys.stderr)
            samples.append(r)
        walls = [s['wall'] for s in samples]
        rows[impl] = {
            'median_wall': statistics.median(walls),
            'min_wall': min(walls),
            'p95_wall': sorted(walls)[max(0, int(round(0.95 * (len(walls) - 1))))],
            'user': statistics.median([s['user'] for s in samples if s['user'] is not None] or [0]),
            'sys': statistics.median([s['sys'] for s in samples if s['sys'] is not None] or [0]),
            'rss_mb': max(s['rss_mb'] for s in samples if s['rss_mb'] is not None),
            'reps': reps,
            'rc': samples[-1]['rc'],
        }
        print(f"  {impl:6s} {label:42s} median {rows[impl]['median_wall']:7.3f}s  min {rows[impl]['min_wall']:7.3f}s  cpu {rows[impl]['user']+rows[impl]['sys']:7.2f}s  rss {rows[impl]['rss_mb']:7.0f} MB", flush=True)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=None)
    ap.add_argument('--quick', action='store_true', help='fewer repetitions')
    args = ap.parse_args()
    reps_cold = 5 if args.quick else 20
    reps_mid = 2 if args.quick else 5
    reps_big = 1 if args.quick else 2

    root = tempfile.mkdtemp(prefix='documix-bench-')
    outs = os.path.join(root, 'out')
    os.makedirs(outs)
    medium = os.path.join(root, 'medium')
    n_medium = build_corpus(medium, 1, 20)
    large = os.path.join(root, 'large')
    n_large = build_corpus(large, 9, 180)
    print(f'corpora: medium={n_medium} files, large={n_large} files (in {root})')

    results = {'hardware': f"{platform.machine()} {os.cpu_count()} cores, {platform.platform()}", 'scenarios': []}

    print('\n[1] cold start, single files')
    singles = [
        ('docx', os.path.join(RESOURCES, 'sample_test.docx'), []),
        ('doc', os.path.join(RESOURCES, 'one_megabyte', 'example_1mb.doc'), []),
        ('pdf 22 pages', os.path.join(RESOURCES, 'one_megabyte', 'example_pdf.pdf'), []),
        ('scanned pdf (OCR)', SCAN, []),
        ('markdown', os.path.join(large, 'text', 'note_0_000.md'), []),
    ]
    for label, path, extra in singles:
        results['scenarios'].append({'scenario': 'cold start', 'label': label, 'rows': measure(label, [path] + extra, reps_cold, outs)})
    # --version has no output file
    rows = {}
    for impl in ('python', 'rust'):
        walls = [timed(impl_cmd(impl, ['--version']))['wall'] for _ in range(reps_cold)]
        rows[impl] = {'median_wall': statistics.median(walls), 'min_wall': min(walls), 'p95_wall': max(walls), 'user': 0, 'sys': 0, 'rss_mb': 0, 'reps': reps_cold, 'rc': 0}
        print(f"  {impl:6s} {'--version':42s} median {rows[impl]['median_wall']:7.3f}s")
    results['scenarios'].append({'scenario': 'cold start', 'label': '--version', 'rows': rows})

    print(f'\n[2] corpus of {n_medium} files')
    for label, extra in (('-j 1', ['-j', '1']), ('auto jobs', [])):
        results['scenarios'].append({'scenario': f'{n_medium} files', 'label': label, 'rows': measure(f'{n_medium} files {label}', [medium, '-r'] + extra, reps_mid, outs)})

    print(f'\n[3] large folder of {n_large} files (10% scans)')
    for label, extra in (('auto jobs', []), ('-j 1', ['-j', '1'])):
        results['scenarios'].append({'scenario': f'{n_large} files', 'label': label, 'rows': measure(f'{n_large} files {label}', [large, '-r'] + extra, reps_big, outs)})

    # output equivalence on the medium corpus
    py_out = sorted(f for f in os.listdir(outs) if f.startswith(f'python_{n_medium}_files_auto_jobs'))
    rs_out = sorted(f for f in os.listdir(outs) if f.startswith(f'rust_{n_medium}_files_auto_jobs'))
    identical = None
    if py_out and rs_out:
        strip = lambda p: [l for l in open(os.path.join(outs, p), encoding='utf-8') if not l.startswith('- Compilation Date')]
        identical = strip(py_out[0]) == strip(rs_out[0])
    results['medium_output_identical'] = identical
    print(f'\nmedium corpus output identical (python vs rust): {identical}')

    lines = ['| Scenario | Case | Python median | Rust median | Speed-up | Python CPU | Rust CPU | Python RSS | Rust RSS |',
             '| --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for s in results['scenarios']:
        p, r = s['rows']['python'], s['rows']['rust']
        speed = p['median_wall'] / r['median_wall'] if r['median_wall'] else float('inf')
        lines.append(f"| {s['scenario']} | {s['label']} | {p['median_wall']:.3f} s | {r['median_wall']:.3f} s | {speed:.1f}x | "
                     f"{p['user'] + p['sys']:.2f} s | {r['user'] + r['sys']:.2f} s | {p['rss_mb']:.0f} MB | {r['rss_mb']:.0f} MB |")
    table = '\n'.join(lines)
    print('\n' + table)
    results['table'] = table
    with open(os.path.join(root, 'bench_port.json'), 'w') as fh:
        json.dump(results, fh, indent=2)
    print(f'raw results: {os.path.join(root, "bench_port.json")}')
    if args.out:
        header = (f"# Python vs Rust port benchmark\n\nHardware: {results['hardware']}. Engines: firecrawl-anydoc / anydoc crate 0.2.4 "
                  f"(pdf-inspector 1.14.2), liteparse 2.16.0. Corpora built from `resources/` and `python/tests/fixtures/` "
                  f"(medium: {n_medium} files, large: {n_large} files with 10% scanned PDFs). Medians over "
                  f"{reps_cold}/{reps_mid}/{reps_big} repetitions; peak RSS is the whole process tree sampled every 50 ms (so Python's LiteParse OCR worker processes are included).\n\n")
        with open(args.out, 'w') as fh:
            fh.write(header + table + '\n\n' + f"Medium corpus output identical between implementations: {identical}\n")
        print(f'written {args.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
