import re
from setuptools import setup, find_packages

def get_version():
    with open("documix/__init__.py") as f:
        match = re.search(r'__version__\s*=\s*["\']([^"\']+)', f.read())
        return match.group(1)

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="documix",
    version=get_version(),
    author="Your Name",
    author_email="your.email@example.com",
    description="Tool to compile documents into a single Markdown file",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/documix",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    entry_points={
        'console_scripts': [
            'documix-py=documix.documix:main',
        ],
    },
    python_requires=">=3.10",
    install_requires=[
        "firecrawl-anydoc>=0.2.4",
        "liteparse>=2.16",
        "docx2txt>=0.8",
        "html2text>=2020.1.16",
    ],
    extras_require={
        "pdf": ["markitdown"],
        "office": ["markitdown[xlsx,pptx]"],
        "tables": ["pdfplumber"],
        "paddleocr": ["paddleocr[doc-parser]", "paddlepaddle>=3.0.0"],
    },
)
