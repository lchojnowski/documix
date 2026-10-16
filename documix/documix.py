#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Backwards-compatible facade for the ``documix`` package.

The implementation lives in ``documix.cli``, ``documix.compiler``,
``documix.converters`` and friends; this module re-exports the public API
(``DocumentCompiler``, ``EmailProcessor``, ``main``, ...) so that
``from documix.documix import DocumentCompiler`` and the ``documix``
console script keep working. It can also be run directly as a script.
"""
import os
import sys

if __package__ in (None, ''):
    # Executed as `python documix/documix.py`: make the package importable.
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import shutil  # noqa: E402,F401  (patched by tests as documix.documix.shutil)
import subprocess  # noqa: E402,F401  (patched by tests as documix.documix.subprocess)

from documix import local_ocr, office_documents  # noqa: E402,F401
from documix import deps as _deps  # noqa: E402
from documix.benchmark import _extension_to_format, benchmark_main, run_benchmark  # noqa: E402,F401
from documix.cli import main, print_converter_info, print_logo  # noqa: E402,F401
from documix.compiler import DocumentCompiler  # noqa: E402,F401
from documix.config import CONVERTER_CHOICES, CONVERTER_DEFAULTS  # noqa: E402,F401
from documix.deps import DOCX2TXT_AVAILABLE, PDFPLUMBER_AVAILABLE  # noqa: E402,F401
from documix.email_processor import EmailProcessor  # noqa: E402,F401
from documix.errors import EngineError  # noqa: E402,F401
from documix.textutils import word_similarity  # noqa: E402,F401
from documix.tools import check_converter_availability  # noqa: E402,F401
from documix.version import get_version  # noqa: E402,F401


def __getattr__(name):
    # Lazy optional modules (pdfplumber, docx2txt) stay unimported until used.
    if name in ('pdfplumber', 'docx2txt'):
        return getattr(_deps, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if __name__ == "__main__":
    main()
