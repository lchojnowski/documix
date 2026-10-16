"""Static configuration: converter chains, default extensions, lookup tables."""

# Primary engines, tried first for every document format.
ENGINE_CONVERTERS = ['anydoc', 'liteparse']

# Default chain per format: anydoc, then LiteParse (where it supports the
# format). The legacy converters are opt-in via --<format>-converters.
CONVERTER_DEFAULTS = {
    'pdf': ['anydoc', 'liteparse'],
    'docx': ['anydoc', 'liteparse'],
    'doc': ['anydoc', 'liteparse'],
    'rtf': ['anydoc', 'liteparse'],
    'epub': ['anydoc'],
    'office': ['anydoc', 'liteparse'],
}

LEGACY_CONVERTERS = {
    'pdf': ['mineru', 'pdfplumber', 'markitdown-uvx', 'markitdown', 'pdftotext',
            'paddleocr', 'tesseract'],
    'docx': ['pandoc', 'docx2txt'],
    'doc': ['soffice'],
    'rtf': ['pandoc', 'unrtf', 'striprtf'],
    'epub': ['ebook-convert'],
    'office': ['markitdown'],
}

CONVERTER_CHOICES = {
    fmt: list(CONVERTER_DEFAULTS[fmt]) + list(LEGACY_CONVERTERS[fmt])
    for fmt in CONVERTER_DEFAULTS
}

# Extension -> converter format key. Anything else is read as text, or is a
# ZIP / EML container handled by the compiler itself.
FORMAT_OF_EXTENSION = {
    '.pdf': 'pdf',
    '.docx': 'docx', '.docm': 'docx',
    '.doc': 'doc',
    '.rtf': 'rtf',
    '.epub': 'epub',
    '.xlsx': 'office', '.xlsm': 'office', '.xlsb': 'office', '.xls': 'office',
    '.pptx': 'office', '.pptm': 'office', '.ppsx': 'office', '.ppsm': 'office',
    '.ppt': 'office', '.pps': 'office', '.pot': 'office',
    '.odt': 'office', '.ods': 'office', '.odp': 'office',
    '.csv': 'office',
}

DEFAULT_EXTENSIONS = [
    '.pdf', '.epub', '.docx', '.docm', '.doc', '.xlsx', '.xlsm', '.xls',
    '.pptx', '.pptm', '.ppt', '.odt', '.ods', '.odp', '.rtf', '.txt', '.md',
    '.py', '.rb', '.js', '.html', '.css', '.json', '.yml', '.yaml', '.zip', '.eml',
]

# Extensions that trigger the lightweight security heuristic in check_security().
SUSPICIOUS_EXTENSIONS = ['.exe', '.bat', '.sh', '.com', '.vbs', '.ps1', '.py', '.rb']

# Extension -> fenced code block language.
LANGUAGE_MAP = {
    '.py': 'python',
    '.rb': 'ruby',
    '.js': 'javascript',
    '.html': 'html',
    '.css': 'css',
    '.json': 'json',
    '.yml': 'yaml',
    '.yaml': 'yaml',
    '.md': 'markdown',
    '.txt': 'text',
    '.sh': 'bash',
    '.java': 'java',
    '.c': 'c',
    '.cpp': 'cpp',
    '.h': 'c',
    '.php': 'php',
    '.sql': 'sql',
    '.xml': 'xml',
    '.go': 'go',
    '.rs': 'rust',
    '.ts': 'typescript',
    '.swift': 'swift',
    '.kt': 'kotlin',
    '.dart': 'dart',
    '.pl': 'perl',
    '.r': 'r',
    '.lua': 'lua',
    '.scala': 'scala',
    '.cs': 'csharp',
    '.vb': 'vb',
}
