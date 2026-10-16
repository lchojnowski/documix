"""Command line interface."""
import argparse
import os
import sys

from . import benchmark, local_ocr, tools, version
from .compiler import DocumentCompiler
from .config import CONVERTER_CHOICES, CONVERTER_DEFAULTS
from .converters import anydoc as anydoc_engine
from .errors import EngineError

FORMAT_HELP = {
    'pdf': 'PDF',
    'docx': 'DOCX/DOCM',
    'doc': 'legacy DOC',
    'rtf': 'RTF',
    'epub': 'EPUB',
    'office': 'XLSX/PPTX/ODT and other Office',
}


def print_converter_info(converter_config):
    """Display which converters are available and will be used."""
    available = tools.check_converter_availability(converter_config)
    if 'tesseract' in converter_config.get('pdf', []) and local_ocr.available():
        available['pdf'].append('tesseract')

    print("Converter Configuration:")
    print("-" * 40)
    for fmt in CONVERTER_DEFAULTS:
        configured = converter_config.get(fmt, CONVERTER_DEFAULTS[fmt])
        avail = available.get(fmt, [])
        active = [c for c in configured if c in avail]
        missing = [c for c in configured if c not in avail]

        print(f"  {fmt.upper():>6}: {', '.join(active) if active else '(none available)'}")
        if missing:
            print(f"          missing: {', '.join(missing)}")
    print()


def print_logo():
    """Displays the program logo."""
    logo = """
 ██████╗  ██████╗  ██████╗██╗   ██╗███╗   ███╗██╗██╗  ██╗
 ██╔══██╗██╔═══██╗██╔════╝██║   ██║████╗ ████║██║╚██╗██╔╝
 ██║  ██║██║   ██║██║     ██║   ██║██╔████╔██║██║ ╚███╔╝ 
 ██║  ██║██║   ██║██║     ██║   ██║██║╚██╔╝██║██║ ██╔██╗ 
 ██████╔╝╚██████╔╝╚██████╗╚██████╔╝██║ ╚═╝ ██║██║██╔╝ ██╗
 ╚═════╝  ╚═════╝  ╚═════╝ ╚═════╝ ╚═╝     ╚═╝╚═╝╚═╝  ╚═╝
                                                         
    """
    print(logo)


def build_parser():
    parser = argparse.ArgumentParser(
        description='Compiles documents from a folder into a single Markdown file, similar to Repomix. '
                    'Documents are converted with anydoc first and LiteParse second (local OCR for '
                    'scanned PDFs); PDF, Word, PowerPoint, Excel, OpenDocument, RTF, EPUB, ZIP archives '
                    'and email files (.eml) with attachments are supported. Legacy converters '
                    '(MinerU, PaddleOCR, pdfplumber, pandoc, LibreOffice, ...) stay available per format.',
        epilog='Email Mode: When processing .eml files, DocuMix will automatically detect and process '
               'attachments from an "attachments" subfolder if present, or extract them from the email itself.\n\n'
               'Subcommands:\n'
               '  documix benchmark          Benchmark available converters for speed and accuracy.\n'
               '                             Run "documix benchmark --help" for options.'
    )
    parser.add_argument('folder', nargs='?', help='Path to the folder with documents or a single .eml file')
    parser.add_argument('-o', '--output', default='documix-output.md', help='Path to the output file (default: documix-output.md)')
    parser.add_argument('-r', '--recursive', action='store_true', help='Search folders recursively')
    parser.add_argument('-e', '--extensions', help='List of file extensions to process (comma-separated, default includes common document formats and .eml)')
    parser.add_argument('-x', '--exclude', help='File exclusion patterns (regular expressions, comma-separated)')
    parser.add_argument('-j', '--jobs', type=int,
        help='Number of files converted concurrently (default: one per CPU core, bounded by '
             'installed memory at about 1.5 GB per job; DOCUMIX_JOBS overrides it; 1 disables '
             'parallelism). The output order is always deterministic.')
    parser.add_argument('-v', '--version', action='store_true', help='Display program version')
    parser.add_argument('--standard-format', action='store_true', help='Force standard format even for emails')
    for fmt in CONVERTER_DEFAULTS:
        extra = ''
        if fmt == 'pdf':
            extra = (' Tesseract is local-only and opt-in; selecting it requires complete-document OCR '
                     'even when another converter returns text.')
        parser.add_argument(f'--{fmt}-converters',
            help=f'{FORMAT_HELP[fmt]} converters to try, in order (comma-separated). '
                 f'Default: {",".join(CONVERTER_DEFAULTS[fmt])}. '
                 f'Choices: {",".join(CONVERTER_CHOICES[fmt])}.{extra}')
    parser.add_argument('--ocr-languages',
        help='Installed Tesseract language codes joined by + (default: eng).')
    parser.add_argument('--ocr-max-pages', type=int,
        help='Maximum pages for Tesseract OCR (default: 20; hard maximum: 100).')
    parser.add_argument('--ocr-dpi', type=int,
        help='Tesseract rendering DPI (default: 150; hard maximum: 200).')
    parser.add_argument('--ocr-timeout', type=int,
        help='Whole-document Tesseract budget in seconds (default: 180; maximum: 300).')
    parser.add_argument('--office-require-text-only', action='store_true',
        help='Fail XLSX/PPTX conversion when embedded or linked images have not '
             'been assessed; opt-in, independent of PDF OCR.')
    return parser


def _fail(message, output_file=None):
    """Report a fatal engine failure, drop any partial output, exit 1."""
    print(f"\n❌ ERROR: anydoc engine failure: {message}")
    print("DocuMix requires a working anydoc installation; nothing was written.")
    if output_file:
        try:
            os.remove(output_file)
        except OSError:
            pass
    sys.exit(1)


def main():
    # Check for subcommands before main argparse
    if len(sys.argv) > 1 and sys.argv[1] == 'benchmark':
        return benchmark.benchmark_main(sys.argv[2:])

    print_logo()

    parser = build_parser()
    args = parser.parse_args()

    if args.version:
        print(f"DocuMix v{version.get_version()}")
        print()
        print_converter_info({})
        return

    if not args.folder:
        parser.print_help()
        return

    print(f"🔍 Analyzing folder: {args.folder}")

    include_extensions = None
    if args.extensions:
        include_extensions = [f".{ext.strip().lower()}" for ext in args.extensions.split(',')]
        print(f"📋 Included extensions: {', '.join(ext for ext in include_extensions)}")

    exclude_patterns = None
    if args.exclude:
        exclude_patterns = [pattern.strip() for pattern in args.exclude.split(',')]
        print(f"🚫 Exclusion patterns: {', '.join(exclude_patterns)}")

    force_format = None
    if args.standard_format:
        force_format = 'standard'
        print("📄 Forcing standard output format")

    if args.jobs is not None and args.jobs < 1:
        parser.error('--jobs must be at least 1')

    converter_config = {}
    for fmt in CONVERTER_DEFAULTS:
        flag_value = getattr(args, f'{fmt}_converters')
        if flag_value:
            names = [n.strip() for n in flag_value.split(',')]
            valid = CONVERTER_CHOICES[fmt]
            for name in names:
                if name not in valid:
                    print(f"Error: unknown {fmt.upper()} converter '{name}'. "
                          f"Valid choices: {', '.join(valid)}")
                    sys.exit(1)
            converter_config[fmt] = names
            print(f"🔧 {fmt.upper()} converters: {', '.join(names)}")

    ocr_config = {
        key: getattr(args, 'ocr_' + key) for key in local_ocr.OCR_DEFAULTS
        if getattr(args, 'ocr_' + key) is not None
    }
    ocr_enabled = 'tesseract' in converter_config.get('pdf', [])
    if ocr_config and not ocr_enabled:
        parser.error('OCR settings require --pdf-converters including tesseract')
    try:
        ocr_config = local_ocr.validate_config(ocr_config)
    except ValueError:
        parser.error('Invalid OCR settings; see --help for bounded values')

    # The primary engine is mandatory: fail before touching any document.
    try:
        anydoc_engine.require()
    except EngineError as error:
        _fail(error)

    print_converter_info(converter_config)

    compiler = DocumentCompiler(
        args.folder,
        args.output,
        args.recursive,
        include_extensions,
        exclude_patterns,
        force_format,
        converter_config,
        **({'ocr_config': ocr_config} if ocr_enabled else {}),
        **({'office_require_text_only': True} if args.office_require_text_only else {}),
        **({'jobs': args.jobs} if args.jobs is not None else {}),
    )

    try:
        compiler.compile()
    except EngineError as error:
        _fail(error, args.output)
