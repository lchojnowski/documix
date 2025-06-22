# DocuMix

Tool to compile documents from a folder into a single Markdown file, similar to Repomix.

## Features

- Compiles various document types (PDF, EPUB, DOCX, DOC, TXT, MD, etc.) into a single Markdown file
- Supports ZIP files by automatically extracting and processing their contents
- **Email Mode**: Process .eml files with automatic attachment handling
- **Smart Output Formats**: Automatically detects and uses email-specific format for .eml files
- Generates a structured file with detailed document contents
- Estimates token counts and provides statistics
- Security checks for potentially suspicious files
- Colorful console output with emojis for better readability

## Installation

You can install documix directly from GitHub:

```bash
pip install git+https://github.com/lchojnowski/documix.git
```

## Usage

```bash
documix /path/to/folder -r -o output.md
```

### Options

- `-o`, `--output` - Path to the output file (default: documix-output.md)
- `-r`, `--recursive` - Search folders recursively
- `-e`, `--extensions` - List of file extensions to process (comma-separated)
- `-x`, `--exclude` - File exclusion patterns (regular expressions, comma-separated)
- `-v`, `--version` - Display program version
- `--standard-format` - Force standard output format (even for emails)

## Examples

Process all documents in a folder recursively:
```bash
documix /path/to/documents -r
```

Process only specific file types:
```bash
documix /path/to/documents -e pdf,docx,zip
```

Exclude certain files:
```bash
documix /path/to/documents -x "temp.*,backup.*"
```

## Email Mode

DocuMix provides specialized handling for email files (.eml) with intelligent output formatting.

### Email Processing Features

1. **Automatic Attachment Detection**: If an "attachments" folder exists next to the .eml file, DocuMix will use those files instead of extracting from the email
2. **Email Parsing**: Extracts metadata (From, To, Subject, Date, etc.) and converts HTML content to Markdown
3. **Attachment Processing**: All supported attachment types (PDF, DOCX, etc.) are automatically processed and included
4. **Smart Output Format**: Automatically uses email-specific format that includes:
   - Email metadata display (sender, recipients, date, subject)
   - Authentication information (SPF, DKIM, DMARC)
   - Attachment summaries with file types and sizes
   - Clean, email-focused presentation

### Output Format Detection

DocuMix automatically detects and uses the appropriate output format:
- **Single Email**: Always uses dedicated email analysis format
- **Multiple Emails**: Treats each email as a separate document in standard format
- **Mixed Content**: Uses standard format when processing emails with other documents


### Email Processing Examples

Process a single email file:
```bash
documix email.eml -o email_output.md
```

Process an email directory structure:
```bash
# Directory structure:
# emails/
# ├── message.eml
# └── attachments/
#     ├── document.pdf
#     └── report.docx

documix emails/ -o consolidated_email.md
```

Process multiple emails:
```bash
documix /path/to/emails -r -e eml
```

Force standard format for email processing:
```bash
documix email.eml -o output.md --standard-format
```

## Dependencies

### Core Dependencies (installed automatically)
- `docx2txt`: For DOCX file processing (fallback method)
- `html2text`: For converting HTML email content to Markdown

### Optional External Dependencies
- For PDF files: markitdown (if available) or poppler-utils (`pdftotext` command)
- For EPUB files: Calibre (`ebook-convert` command)
- For DOCX files: pandoc (primary method)
- For DOC files: LibreOffice (`soffice` command)

## License

This project is licensed under the MIT License - see the LICENSE file for details.