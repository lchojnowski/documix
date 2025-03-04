#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import argparse
import re
import subprocess
import tempfile
import datetime
import shutil
import math
import time
import zipfile
from pathlib import Path
from collections import Counter
import string

class DocumentCompiler:
    def __init__(self, source_dir, output_file, recursive=False, include_extensions=None, exclude_patterns=None):
        self.source_dir = os.path.abspath(source_dir)
        self.output_file = output_file
        self.recursive = recursive
        self.version = "0.1.0"
        
        # Statistics data
        self.total_files = 0
        self.total_chars = 0
        self.total_tokens = 0
        self.file_stats = []
        
        # Temporary directory for ZIP extraction
        self.temp_dirs = []
        
        # List of potentially suspicious extensions for security check
        self.suspicious_extensions = ['.exe', '.bat', '.sh', '.com', '.vbs', '.ps1', '.py', '.rb']
        
        # Standard extensions if none provided
        self.include_extensions = include_extensions or ['.pdf', '.epub', '.docx', '.doc', '.txt', '.md', 
                                                        '.py', '.rb', '.js', '.html', '.css', '.json', '.yml', '.yaml', '.zip']
        
        # Convert extensions to lowercase for consistency
        self.include_extensions = [ext.lower() for ext in self.include_extensions]
        
        # Compile exclusion patterns
        self.exclude_patterns = []
        if exclude_patterns:
            for pattern in exclude_patterns:
                try:
                    self.exclude_patterns.append(re.compile(pattern))
                except re.error:
                    print(f"WARNING: Invalid exclusion pattern: {pattern}")
    
    def collect_files(self):
        """Collects all files to process."""
        files_to_process = []
        
        if self.recursive:
            for root, _, files in os.walk(self.source_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    files_to_process.append(file_path)
        else:
            files_to_process = [os.path.join(self.source_dir, f) for f in os.listdir(self.source_dir) 
                              if os.path.isfile(os.path.join(self.source_dir, f))]
        
        # Filter files by extensions and exclusion patterns
        filtered_files = []
        
        for file_path in files_to_process:
            # Check extension
            _, ext = os.path.splitext(file_path.lower())
            if ext not in self.include_extensions:
                continue
            
            # Check exclusion patterns
            filename = os.path.basename(file_path)
            exclude = False
            for pattern in self.exclude_patterns:
                if pattern.search(filename):
                    exclude = True
                    break
            
            if not exclude:
                filtered_files.append(file_path)
        
        # Sort files alphabetically
        return sorted(filtered_files)
    
    def get_directory_structure(self):
        """Creates a directory tree in Repomix format."""
        structure = []
        
        if self.recursive:
            for root, dirs, files in os.walk(self.source_dir):
                # Skip hidden directories
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                
                rel_path = os.path.relpath(root, self.source_dir)
                if rel_path != '.':
                    structure.append(f"{rel_path}/")
                
                for file in sorted(files):
                    file_path = os.path.join(root, file)
                    _, ext = os.path.splitext(file_path.lower())
                    
                    # Check if file has an appropriate extension
                    if ext in self.include_extensions:
                        # Check exclusion patterns
                        exclude = False
                        for pattern in self.exclude_patterns:
                            if pattern.search(file):
                                exclude = True
                                break
                        
                        if not exclude:
                            rel_file_path = os.path.relpath(file_path, self.source_dir)
                            structure.append(f"  {rel_file_path}")
        else:
            for file in sorted(os.listdir(self.source_dir)):
                file_path = os.path.join(self.source_dir, file)
                if os.path.isfile(file_path):
                    _, ext = os.path.splitext(file_path.lower())
                    
                    # Check if file has an appropriate extension
                    if ext in self.include_extensions:
                        # Check exclusion patterns
                        exclude = False
                        for pattern in self.exclude_patterns:
                            if pattern.search(file):
                                exclude = True
                                break
                        
                        if not exclude:
                            structure.append(f"  {file}")
        
        return structure
    
    def get_file_language(self, file_path):
        """Determines programming language based on file extension."""
        ext = os.path.splitext(file_path.lower())[1]
        languages = {
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
            '.vb': 'vb'
        }
        return languages.get(ext, '')
    
    def estimate_tokens(self, text):
        if not text.strip():
            return 0
        tokens = text.strip().split()
        word_count = len(tokens)
        if re.search(r'[.!?]$', text.strip()):
            return word_count + 1
        return word_count

    
    def check_security(self, files):
        """Checks for potential security issues in files."""
        suspicious_files = []
        
        for file_path in files:
            # Check suspicious file extensions
            _, ext = os.path.splitext(file_path.lower())
            if ext in self.suspicious_extensions:
                # Simple heuristic - check file size and sample content
                file_size = os.path.getsize(file_path)
                if file_size > 1024 * 1024:  # Larger than 1MB
                    suspicious_files.append(file_path)
                    continue
                
                # Check content for suspicious patterns
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read(4096)  # Read only first 4KB
                        if re.search(r'(exec|eval|system|subprocess|os\.)', content):
                            suspicious_files.append(file_path)
                except Exception:
                    pass  # Ignore errors reading binary files
        
        return suspicious_files
    
    # Document conversion functions
    def convert_pdf_to_text(self, filepath):
        """Converts PDF to text using pdftotext."""
        try:
            # Try using pdftotext (from poppler-utils package)
            with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as temp:
                temp_name = temp.name
            
            subprocess.run(['pdftotext', '-layout', filepath, temp_name], check=True)
            
            with open(temp_name, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()
            
            os.unlink(temp_name)
            return text
        except (subprocess.SubprocessError, FileNotFoundError):
            print(f"WARNING: Failed to convert PDF: {filepath}")
            print("Make sure you have the poppler-utils package installed")
            return f"[Failed to convert PDF file: {os.path.basename(filepath)}]"

    def convert_epub_to_text(self, filepath):
        """Converts EPUB to text using Calibre's ebook-convert tool."""
        try:
            # Try using calibre (ebook-convert)
            with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as temp:
                temp_name = temp.name
            
            subprocess.run(['ebook-convert', filepath, temp_name], check=True)
            
            with open(temp_name, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()
            
            os.unlink(temp_name)
            return text
        except (subprocess.SubprocessError, FileNotFoundError):
            print(f"WARNING: Failed to convert EPUB: {filepath}")
            print("Make sure you have Calibre installed")
            return f"[Failed to convert EPUB file: {os.path.basename(filepath)}]"

    def convert_docx_to_text(self, filepath):
        """Converts DOCX to text using pandoc."""
        try:
            # Try using pandoc
            with tempfile.NamedTemporaryFile(suffix='.md', delete=False) as temp:
                temp_name = temp.name
            
            subprocess.run(['pandoc', '-f', 'docx', '-t', 'markdown', filepath, '-o', temp_name], check=True)
            
            with open(temp_name, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()
            
            os.unlink(temp_name)
            return text
        except (subprocess.SubprocessError, FileNotFoundError):
            print(f"WARNING: Failed to convert DOCX: {filepath}")
            print("Make sure you have pandoc installed")
            return f"[Failed to convert DOCX file: {os.path.basename(filepath)}]"

    def convert_doc_to_text(self, filepath):
        """Converts DOC to text using doc2docx if available, or antiword/catdoc as fallback."""
        try:
            # Try using doc2docx first to convert to docx, then process as docx
            try:
                with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as temp:
                    temp_docx = temp.name
                
                # Check if doc2docx command exists
                subprocess.run(['which', 'doc2docx'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                # Convert DOC to DOCX
                subprocess.run(['doc2docx', filepath, temp_docx], check=True)
                
                # Process the DOCX file
                text = self.convert_docx_to_text(temp_docx)
                
                # Clean up
                os.unlink(temp_docx)
                return text
                
            except (subprocess.SubprocessError, FileNotFoundError):
                # Fallback to antiword or catdoc
                try:
                    text = subprocess.check_output(['antiword', filepath], stderr=subprocess.DEVNULL)
                    return text.decode('utf-8', errors='replace')
                except (subprocess.SubprocessError, FileNotFoundError):
                    text = subprocess.check_output(['catdoc', filepath], stderr=subprocess.DEVNULL)
                    return text.decode('utf-8', errors='replace')
        except (subprocess.SubprocessError, FileNotFoundError):
            print(f"WARNING: Failed to convert DOC: {filepath}")
            print("Make sure you have doc2docx, antiword, or catdoc installed")
            return f"[Failed to convert DOC file: {os.path.basename(filepath)}]"

    def convert_txt_to_text(self, filepath):
        """Reads text from TXT/MD/other text files."""
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                return f.read()
        except Exception as e:
            print(f"WARNING: Failed to read file: {filepath}")
            print(f"Error: {e}")
            return f"[Failed to read file: {os.path.basename(filepath)}]"
    
    def extract_zip(self, filepath):
        """Extracts a ZIP file and processes its contents."""
        try:
            # Create a temporary directory for ZIP extraction
            temp_dir = tempfile.mkdtemp()
            self.temp_dirs.append(temp_dir)
            
            print(f"📦 Extracting ZIP: {os.path.basename(filepath)}")
            
            # Extract the ZIP file
            with zipfile.ZipFile(filepath, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            
            # Create a summary of ZIP contents
            file_list = []
            zip_content_summary = f"# ZIP Archive Contents: {os.path.basename(filepath)}\n\n"
            zip_content_summary += "## Files in archive:\n\n"
            
            # Walk through the extracted directory
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, temp_dir)
                    file_list.append(rel_path)
            
            # Sort the file list for a clean representation
            file_list.sort()
            for file in file_list:
                zip_content_summary += f"- {file}\n"
            
            # Process each file in the ZIP archive
            zip_content_summary += "\n## Extracted file contents:\n\n"
            
            for file_path in file_list:
                full_path = os.path.join(temp_dir, file_path)
                _, ext = os.path.splitext(file_path.lower())
                
                # Process only if file extension is in include list
                if ext in self.include_extensions:
                    zip_content_summary += f"### File: {file_path}\n\n"
                    
                    # Get file content
                    try:
                        content = self.process_file(full_path)
                        
                        # Add file content as a code block with appropriate language
                        file_language = self.get_file_language(file_path)
                        if file_language:
                            zip_content_summary += f"```{file_language}\n{content}\n```\n\n"
                        else:
                            zip_content_summary += f"```\n{content}\n```\n\n"
                    except Exception as e:
                        zip_content_summary += f"[Error processing file: {str(e)}]\n\n"
            
            return zip_content_summary
            
        except zipfile.BadZipFile:
            return f"[Error: {os.path.basename(filepath)} is not a valid ZIP file]"
        except Exception as e:
            return f"[Error processing ZIP file: {str(e)}]"
    
    def process_file(self, file_path):
        """Processes a single file and returns its content."""
        ext = os.path.splitext(file_path.lower())[1]
        
        if ext == '.pdf':
            return self.convert_pdf_to_text(file_path)
        elif ext == '.epub':
            return self.convert_epub_to_text(file_path)
        elif ext == '.docx':
            return self.convert_docx_to_text(file_path)
        elif ext == '.doc':
            return self.convert_doc_to_text(file_path)
        elif ext == '.zip':
            return self.extract_zip(file_path)
        else:  # .txt, .md, .py, etc.
            return self.convert_txt_to_text(file_path)
    
    def compile(self):
        """Compiles all documents into a single Markdown file."""
        # Start time measurement
        start_time = time.time()
        
        # Display header
        print(f"📦 DocuMix v{self.version}")
        
        filtered_files = self.collect_files()
        
        if not filtered_files:
            print("❌ No files found to process.")
            return False
        
        # Set number of files
        self.total_files = len(filtered_files)
        
        # Security check
        print("🔎 Checking files for security issues...")
        suspicious_files = self.check_security(filtered_files)
        
        # Collecting file statistics
        print("📊 Collecting file statistics...")
        
        structure = self.get_directory_structure()
        
        try:
            with open(self.output_file, 'w', encoding='utf-8') as out_file:
                # File header
                out_file.write("This file is a merged representation of all documents, combined into a single document.\n\n")
                
                # Summary
                out_file.write("# File Summary\n\n")
                out_file.write("## Purpose\n")
                out_file.write("This file contains a packed representation of the entire directory's contents.\n")
                out_file.write("It is designed to be easily consumable by AI systems for analysis, review,\n")
                out_file.write("or other automated processes.\n\n")
                
                out_file.write("## File Format\n")
                out_file.write("The content is organized as follows:\n")
                out_file.write("1. This summary section\n")
                out_file.write("2. Directory information\n")
                out_file.write("3. Directory structure\n")
                out_file.write("4. Multiple file entries, each consisting of:\n")
                out_file.write("  a. A header with the file path (## File: path/to/file)\n")
                out_file.write("  b. The full contents of the file in a code block\n\n")
                
                out_file.write("## Usage Guidelines\n")
                out_file.write("- This file should be treated as read-only. Any changes should be made to the\n")
                out_file.write("  original files, not this packed version.\n")
                out_file.write("- When processing this file, use the file path to distinguish\n")
                out_file.write("  between different files in the directory.\n\n")
                
                out_file.write("## Notes\n")
                out_file.write("- Some files may have been excluded based on extension filters or exclusion patterns\n")
                out_file.write("- Binary files are only partially supported (PDF, EPUB, DOCX) and conversion quality may vary\n")
                out_file.write("- ZIP files are automatically extracted and their contents are included\n")
                out_file.write("- Files matching specified exclude patterns are skipped\n\n")
                
                # Directory information
                out_file.write("# Directory Information\n")
                out_file.write(f"- Source Directory: {self.source_dir}\n")
                out_file.write(f"- Compilation Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                out_file.write(f"- Total Files Processed: {len(filtered_files)}\n\n")
                
                # Directory structure
                out_file.write("# Directory Structure\n")
                out_file.write("```\n")
                for item in structure:
                    out_file.write(f"{item}\n")
                out_file.write("```\n\n")
                
                # File contents
                out_file.write("# Files\n\n")
                
                for file_path in filtered_files:
                    rel_path = os.path.relpath(file_path, self.source_dir)
                    file_language = self.get_file_language(file_path)
                    
                    print(f"⚙️  Processing: {rel_path}")
                    
                    # File header
                    out_file.write(f"## File: {rel_path}\n")
                    
                    # File content
                    content = self.process_file(file_path)
                    
                    # Collecting statistics
                    char_count = len(content)
                    token_count = self.estimate_tokens(content)
                    
                    self.total_chars += char_count
                    self.total_tokens += token_count
                    
                    self.file_stats.append({
                        'path': rel_path,
                        'chars': char_count,
                        'tokens': token_count
                    })
                    
                    # Adding content as a code block with appropriate language
                    # For ZIP files, content is already formatted in Markdown so we don't wrap it in code block
                    if os.path.splitext(file_path.lower())[1] == '.zip':
                        out_file.write(content)
                    else:
                        # Adding content as a code block with appropriate language
                        backticks = "````"  # Using four to maintain compatibility with Repomix format
                        if file_language:
                            out_file.write(f"{backticks}{file_language}\n")
                        else:
                            out_file.write(f"{backticks}\n")
                        
                        out_file.write(content)
                        
                        # Closing code block
                        out_file.write(f"\n{backticks}\n\n")
            
            # Sort file statistics by character count
            self.file_stats.sort(key=lambda x: x['chars'], reverse=True)
            
            # End time measurement
            elapsed_time = time.time() - start_time
            
            # Display summary
            print("\n✔ Packing completed successfully!")
            
            # Top 5 files by character and token count
            print("\n📈 Top 5 Files by Character Count and Token Count:")
            print("──────────────────────────────────────────────────")
            for i, stat in enumerate(self.file_stats[:5], 1):
                print(f"{i}. {stat['path']} ({stat['chars']:,} chars, {stat['tokens']:,} tokens)")
            
            # Security check result
            print("\n🔎 Security Check:")
            print("─────────────────────")
            if suspicious_files:
                print("❌ Suspicious files detected:")
                for sus_file in suspicious_files:
                    print(f"  - {os.path.relpath(sus_file, self.source_dir)}")
            else:
                print("✔ No suspicious files detected.")
            
            # Packing summary
            print("\n📊 Pack Summary:")
            print("─────────────────────")
            print(f"  Total Files: {self.total_files:,} files")
            print(f"  Total Chars: {self.total_chars:,} chars")
            print(f" Total Tokens: {self.total_tokens:,} tokens")
            print(f"       Output: {self.output_file}")
            print(f"     Security: {'❌ Suspicious files detected' if suspicious_files else '✔ No suspicious files detected'}")
            print(f"        Time: {elapsed_time:.2f} seconds")
            
            print("\n🎉 All Done! Your documents have been successfully packed.")
            
            return True
            
        finally:
            # Clean up temporary directories
            for temp_dir in self.temp_dirs:
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass

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

def main():
    # Display logo
    print_logo()
    
    parser = argparse.ArgumentParser(description='Compiles documents from a folder into a single Markdown file, similar to Repomix.')
    parser.add_argument('folder', help='Path to the folder with documents')
    parser.add_argument('-o', '--output', default='documix-output.md', help='Path to the output file (default: documix-output.md)')
    parser.add_argument('-r', '--recursive', action='store_true', help='Search folders recursively')
    parser.add_argument('-e', '--extensions', help='List of file extensions to process (comma-separated)')
    parser.add_argument('-x', '--exclude', help='File exclusion patterns (regular expressions, comma-separated)')
    parser.add_argument('-v', '--version', action='store_true', help='Display program version')
    
    args = parser.parse_args()
    
    # Display version and exit if --version argument is provided
    if args.version:
        print("DocuMix v0.1.0")
        return
    
    # Check if folder is provided
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
    
    compiler = DocumentCompiler(
        args.folder, 
        args.output, 
        args.recursive, 
        include_extensions, 
        exclude_patterns
    )
    
    compiler.compile()

if __name__ == "__main__":
    main()