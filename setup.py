from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="documix",
    version="0.1.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="Tool to compile documents into a single Markdown file",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/documix",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    entry_points={
        'console_scripts': [
            'documix=documix.documix:main',
        ],
    },
    python_requires=">=3.6",
    install_requires=[
        "docx2txt>=0.8",
        "html2text>=2020.1.16",
    ],
    extras_require={
        "pdf": ["markitdown"]
    },
)