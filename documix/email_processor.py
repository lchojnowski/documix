"""Parsing of .eml files and their attachments."""
import datetime
import email
import email.policy
import os
from email.parser import BytesParser

import html2text

from . import textutils


class EmailProcessor:
    """Processes email files (.eml) and their attachments."""

    def __init__(self, eml_path, attachments_dir=None):
        self.eml_path = eml_path
        self.attachments_dir = attachments_dir or self._auto_detect_attachments()
        self.email_obj = None
        self.metadata = {}
        self.attachments = []
        self.use_folder_attachments = False
        self.h2t = html2text.HTML2Text()
        self.h2t.ignore_links = False
        self.h2t.ignore_images = False
        self.h2t.body_width = 0  # No line wrapping

    def _auto_detect_attachments(self):
        """Auto-detect attachments folder near the email file."""
        email_dir = os.path.dirname(self.eml_path)
        possible_names = ['attachments', 'Attachments', 'attachment', 'Attachment']

        for name in possible_names:
            attachments_path = os.path.join(email_dir, name)
            if os.path.exists(attachments_path) and os.path.isdir(attachments_path):
                return attachments_path

        return None

    def _check_attachments_folder(self):
        """Check if attachments folder exists and has files."""
        if self.attachments_dir and os.path.exists(self.attachments_dir):
            files = []
            for f in os.listdir(self.attachments_dir):
                file_path = os.path.join(self.attachments_dir, f)
                if os.path.isfile(file_path):
                    file_size = os.path.getsize(file_path)
                    files.append({
                        'filename': f,
                        'path': file_path,
                        'size': file_size
                    })

            if files:
                self.use_folder_attachments = True
                return files
        return []

    def parse_email(self):
        """Parse .eml file and extract all components."""
        try:
            with open(self.eml_path, 'rb') as f:
                self.email_obj = BytesParser(policy=email.policy.default).parse(f)

            self.metadata = {
                'from': self.email_obj.get('From', ''),
                'to': self.email_obj.get('To', ''),
                'cc': self.email_obj.get('CC', ''),
                'bcc': self.email_obj.get('BCC', ''),
                'subject': self.email_obj.get('Subject', ''),
                'date': self.email_obj.get('Date', ''),
                'message_id': self.email_obj.get('Message-ID', ''),
                'in_reply_to': self.email_obj.get('In-Reply-To', ''),
                'references': self.email_obj.get('References', ''),
                'content_type': self.email_obj.get_content_type()
            }

            if self.email_obj.get('DKIM-Signature'):
                self.metadata['dkim_signature'] = 'Present'
            if self.email_obj.get('Authentication-Results'):
                self.metadata['auth_results'] = self.email_obj.get('Authentication-Results')

            return True

        except Exception as e:
            print(f"ERROR: Failed to parse email {self.eml_path}: {str(e)}")
            return False

    def extract_attachments_from_email(self):
        """Extract attachments from the email object."""
        if not self.email_obj:
            return

        for part in self.email_obj.walk():
            content_disposition = part.get('Content-Disposition', '')
            if 'attachment' in content_disposition:
                filename = part.get_filename()
                if filename:
                    if not self.attachments_dir:
                        email_dir = os.path.dirname(self.eml_path)
                        self.attachments_dir = os.path.join(email_dir, 'attachments')

                    os.makedirs(self.attachments_dir, exist_ok=True)

                    filepath = os.path.join(self.attachments_dir, filename)
                    content = part.get_content()

                    if isinstance(content, bytes):
                        with open(filepath, 'wb') as f:
                            f.write(content)
                    else:
                        with open(filepath, 'w', encoding='utf-8') as f:
                            f.write(content)

                    file_size = os.path.getsize(filepath)
                    self.attachments.append({
                        'filename': filename,
                        'path': filepath,
                        'size': file_size
                    })

    def process_attachments(self):
        """Process attachments with folder priority."""
        folder_files = self._check_attachments_folder()

        if self.use_folder_attachments:
            self.attachments = folder_files
            self.metadata['attachments_source'] = 'Local folder'
            print(f"📎 Using {len(folder_files)} attachments from local folder")
        else:
            self.extract_attachments_from_email()
            self.metadata['attachments_source'] = 'Extracted from email'
            print(f"📎 Extracted {len(self.attachments)} attachments from email")

    def get_email_body(self):
        """Extract and convert email body to markdown."""
        if not self.email_obj:
            return ""

        body_plain = ""
        body_html = ""

        for part in self.email_obj.walk():
            content_type = part.get_content_type()
            content_disposition = part.get('Content-Disposition', '')

            if 'attachment' in content_disposition:
                continue

            try:
                if content_type == 'text/plain':
                    body_plain = part.get_content()
                elif content_type == 'text/html':
                    html_content = part.get_content()
                    body_html = self.h2t.handle(html_content)
            except Exception as e:
                print(f"WARNING: Failed to extract body part: {str(e)}")

        return body_html if body_html else body_plain

    def format_size(self, size_bytes):
        """Format file size in human-readable format."""
        return textutils.format_size(size_bytes)

    def compile_output(self):
        """Generate final consolidated document."""
        output = []

        subject = self.metadata.get('subject', 'No Subject')
        output.append(f"# Email Document: {subject}")
        output.append(f"Generated by DocuMix on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        output.append("")

        output.append("## Email Metadata")
        if self.metadata.get('from'):
            output.append(f"- **From**: {self.metadata['from']}")
        if self.metadata.get('to'):
            output.append(f"- **To**: {self.metadata['to']}")
        if self.metadata.get('cc'):
            output.append(f"- **CC**: {self.metadata['cc']}")
        if self.metadata.get('date'):
            output.append(f"- **Date**: {self.metadata['date']}")
        if self.metadata.get('subject'):
            output.append(f"- **Subject**: {self.metadata['subject']}")
        if self.metadata.get('message_id'):
            output.append(f"- **Message-ID**: {self.metadata['message_id']}")
        if self.metadata.get('attachments_source'):
            output.append(f"- **Attachments Source**: {self.metadata['attachments_source']} ({len(self.attachments)} files found)")
        output.append("")

        output.append("## Email Content")
        output.append("")
        body = self.get_email_body()
        if body:
            output.append(body)
        else:
            output.append("[No email body content found]")
        output.append("")

        if self.attachments:
            output.append(f"## Attachments ({len(self.attachments)} files)")
            output.append("")

            total_size = sum(att['size'] for att in self.attachments)
            output.append(f"Total size: {self.format_size(total_size)}")
            output.append("")

            return "\n".join(output), self.attachments
        else:
            output.append("## Attachments")
            output.append("")
            output.append("No attachments found.")
            output.append("")
            return "\n".join(output), []
