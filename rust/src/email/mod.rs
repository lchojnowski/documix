//! Email (.eml) processing: `documix/email_processor.py` and
//! `DocumentCompiler.process_email`.
pub mod html2md;

use std::path::{Path, PathBuf};
use std::time::Instant;

use chrono::Datelike;
use mail_parser::{Address, HeaderName, HeaderValue, Message, MessagePart, MimeHeaders, PartType};

use crate::convert::{is_fenced, language_of, process_file, Context};
use crate::output::EmailInfo;
use crate::textutils::{format_size, lower_extension};
use crate::EngineError;

fn universal_newlines(raw: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(raw.len());
    let mut i = 0;
    while i < raw.len() {
        match raw[i] {
            b'\r' => {
                out.push(b'\n');
                if raw.get(i + 1) == Some(&b'\n') {
                    i += 1;
                }
            }
            byte => out.push(byte),
        }
        i += 1;
    }
    out
}

/// `_auto_detect_attachments`.
fn auto_detect_attachments(eml: &Path) -> Option<PathBuf> {
    let dir = eml.parent()?;
    for name in ["attachments", "Attachments", "attachment", "Attachment"] {
        let candidate = dir.join(name);
        if candidate.is_dir() {
            return Some(candidate);
        }
    }
    None
}

/// `email.policy.default` renders address headers as `Name <addr>`.
fn quote_display(name: &str) -> String {
    const SPECIALS: &str = "()<>@,:;.\\\"[]";
    if name.chars().any(|c| SPECIALS.contains(c)) {
        format!("\"{}\"", name.replace('\\', "\\\\").replace('"', "\\\""))
    } else {
        name.to_string()
    }
}

fn render_addr(name: Option<&str>, address: Option<&str>) -> String {
    let address = address.unwrap_or("");
    match name {
        Some(name) if !name.is_empty() => format!("{} <{}>", quote_display(name), address),
        _ => address.to_string(),
    }
}

fn render_address(value: Option<&Address<'_>>) -> String {
    let Some(value) = value else { return String::new() };
    match value {
        Address::List(list) => list
            .iter()
            .map(|a| render_addr(a.name.as_deref(), a.address.as_deref()))
            .collect::<Vec<_>>()
            .join(", "),
        Address::Group(groups) => groups
            .iter()
            .map(|g| {
                let members: Vec<String> = g
                    .addresses
                    .iter()
                    .map(|a| render_addr(a.name.as_deref(), a.address.as_deref()))
                    .collect();
                match (&g.name, members.len()) {
                    (None, 1) => members[0].clone(),
                    _ => {
                        let disp = g.name.as_deref().map(quote_display).unwrap_or_default();
                        let joined = members.join(", ");
                        let joined = if joined.is_empty() { joined } else { format!(" {joined}") };
                        format!("{disp}:{joined};")
                    }
                }
            })
            .collect::<Vec<_>>()
            .join(", "),
    }
}

/// `email.utils.format_datetime(parsedate_to_datetime(value))`; the raw
/// (unfolded) value when the date does not parse.
fn render_date(message: &Message<'_>) -> String {
    let raw = unstructured_header(message, "Date");
    if raw.is_empty() {
        return String::new();
    }
    let Some(date) = message.date() else { return raw };
    let Some(naive) = chrono::NaiveDate::from_ymd_opt(date.year as i32, date.month as u32, date.day as u32) else { return raw };
    let weekday = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][naive.weekday().num_days_from_monday() as usize];
    let month = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][(date.month as usize).saturating_sub(1).min(11)];
    let sign = if date.tz_before_gmt { '-' } else { '+' };
    format!(
        "{weekday}, {:02} {month} {:04} {:02}:{:02}:{:02} {sign}{:02}{:02}",
        date.day, date.year, date.hour, date.minute, date.second, date.tz_hour, date.tz_minute
    )
}

/// Unstructured header the way `policy.default` returns it: decoded, with
/// every CR/LF removed and the leading whitespace after the colon stripped.
fn unstructured_header(message: &Message<'_>, name: &str) -> String {
    match message.header(name) {
        Some(HeaderValue::Text(text)) => text.replace(['\r', '\n'], ""),
        Some(HeaderValue::TextList(list)) => list.iter().map(|t| t.replace(['\r', '\n'], "")).collect::<Vec<_>>().join(", "),
        Some(_) => message.header_raw(name).map(|raw| raw.trim_start_matches([' ', '\t']).replace(['\r', '\n'], "")).unwrap_or_default(),
        None => String::new(),
    }
}

fn raw_header(message: &Message<'_>, name: &str) -> String {
    message.header_raw(name).map(|raw| raw.trim_start_matches([' ', '\t']).replace(['\r', '\n'], "")).unwrap_or_default()
}

/// `msg.walk()` order: pre-order, root first.
fn walk<'a>(message: &'a Message<'a>) -> Vec<&'a MessagePart<'a>> {
    let mut order = Vec::new();
    fn visit<'a>(message: &'a Message<'a>, id: usize, order: &mut Vec<&'a MessagePart<'a>>) {
        let Some(part) = message.parts.get(id) else { return };
        order.push(part);
        if let PartType::Multipart(children) = &part.body {
            for child in children {
                visit(message, *child as usize, order);
            }
        }
    }
    visit(message, 0, &mut order);
    order
}

fn is_attachment(part: &MessagePart<'_>, raw: &[u8]) -> bool {
    // Python: 'attachment' in str(part.get('Content-Disposition', ''))
    for header in part.headers() {
        if header.name == HeaderName::ContentDisposition {
            let slice = &raw[header.offset_start as usize..header.offset_end as usize];
            return String::from_utf8_lossy(slice).replace(['\r', '\n'], "").contains("attachment");
        }
    }
    false
}

fn content_type_of(part: &MessagePart<'_>) -> (String, String) {
    match part.content_type() {
        Some(ct) => (ct.c_type.to_lowercase(), ct.c_subtype.as_deref().unwrap_or("").to_lowercase()),
        None => ("text".to_string(), "plain".to_string()),
    }
}

struct Attachment {
    filename: String,
    path: PathBuf,
    size: u64,
}

/// Returns `(content, method, Some(info))`, or a placeholder with `None`.
pub fn process_email(ctx: &Context, path: &Path) -> Result<(String, String, Option<EmailInfo>), EngineError> {
    let started = Instant::now();
    let name = path.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
    println!("📧 Processing email: {name}");

    let Ok(raw) = std::fs::read(path) else {
        println!("ERROR: Failed to parse email {}", path.display());
        return Ok((format!("[Failed to parse email file: {name}]"), "failed-parse".to_string(), None));
    };
    // BytesParser wraps the file in a TextIOWrapper with universal newlines:
    // every CRLF and lone CR becomes LF before the message is parsed.
    let raw = universal_newlines(&raw);
    let Some(message) = mail_parser::MessageParser::default().parse(&raw) else {
        println!("ERROR: Failed to parse email {}", path.display());
        return Ok((format!("[Failed to parse email file: {name}]"), "failed-parse".to_string(), None));
    };

    let subject = unstructured_header(&message, "Subject");
    let from = render_address(message.from());
    let to = render_address(message.to());
    let cc = render_address(message.cc());
    let date = render_date(&message);
    let message_id = message.message_id().map(|id| format!("<{id}>")).unwrap_or_default();
    let dkim_signature = if message.header_raw("DKIM-Signature").is_some() { "Present".to_string() } else { String::new() };
    let auth_results = raw_header(&message, "Authentication-Results");
    let size = std::fs::metadata(path).map(|m| m.len()).unwrap_or(0);

    // process_attachments
    let mut attachments_dir = auto_detect_attachments(path);
    let mut attachments: Vec<Attachment> = Vec::new();
    let mut use_folder = false;
    if let Some(dir) = &attachments_dir {
        if let Ok(entries) = std::fs::read_dir(dir) {
            for entry in entries.flatten() {
                let file_path = entry.path();
                if file_path.is_file() {
                    let size = std::fs::metadata(&file_path).map(|m| m.len()).unwrap_or(0);
                    attachments.push(Attachment { filename: entry.file_name().to_string_lossy().into_owned(), path: file_path, size });
                }
            }
        }
        if !attachments.is_empty() {
            use_folder = true;
        }
    }
    let parts = walk(&message);
    let attachments_source = if use_folder {
        println!("📎 Using {} attachments from local folder", attachments.len());
        "Local folder"
    } else {
        for part in &parts {
            if !is_attachment(part, &raw) {
                continue;
            }
            let Some(filename) = part.attachment_name() else { continue };
            let dir = attachments_dir.get_or_insert_with(|| path.parent().unwrap_or(Path::new(".")).join("attachments"));
            let _ = std::fs::create_dir_all(&*dir);
            let filepath = dir.join(filename);
            let (ctype, _) = content_type_of(part);
            let written = if ctype == "text" {
                std::fs::write(&filepath, part.text_contents().unwrap_or(""))
            } else {
                std::fs::write(&filepath, part.contents())
            };
            if written.is_err() {
                continue;
            }
            let size = std::fs::metadata(&filepath).map(|m| m.len()).unwrap_or(0);
            attachments.push(Attachment { filename: filename.to_string(), path: filepath, size });
        }
        println!("📎 Extracted {} attachments from email", attachments.len());
        "Extracted from email"
    };

    // get_email_body
    let mut body_plain = String::new();
    let mut body_html = String::new();
    let mut converter = html2md::Html2Text::new(false);
    for part in &parts {
        if is_attachment(part, &raw) {
            continue;
        }
        let (ctype, subtype) = content_type_of(part);
        if ctype != "text" {
            continue;
        }
        let Some(text) = part.text_contents() else { continue };
        if subtype == "plain" {
            body_plain = text.to_string();
        } else if subtype == "html" {
            match converter.handle(text) {
                Ok(markdown) => body_html = markdown,
                Err(error) => println!("WARNING: Failed to extract body part: {}", error.0),
            }
        }
    }
    let body = if !body_html.is_empty() { body_html } else { body_plain };

    // compile_output
    let mut lines: Vec<String> = Vec::new();
    lines.push(format!("# Email Document: {}", if subject.is_empty() { "No Subject".to_string() } else { subject.clone() }));
    lines.push(format!("Generated by DocuMix on {}", crate::output::now_stamp()));
    lines.push(String::new());
    lines.push("## Email Metadata".to_string());
    if !from.is_empty() { lines.push(format!("- **From**: {from}")); }
    if !to.is_empty() { lines.push(format!("- **To**: {to}")); }
    if !cc.is_empty() { lines.push(format!("- **CC**: {cc}")); }
    if !date.is_empty() { lines.push(format!("- **Date**: {date}")); }
    if !subject.is_empty() { lines.push(format!("- **Subject**: {subject}")); }
    if !message_id.is_empty() { lines.push(format!("- **Message-ID**: {message_id}")); }
    lines.push(format!("- **Attachments Source**: {attachments_source} ({} files found)", attachments.len()));
    lines.push(String::new());
    lines.push("## Email Content".to_string());
    lines.push(String::new());
    lines.push(if body.is_empty() { "[No email body content found]".to_string() } else { body });
    lines.push(String::new());
    if !attachments.is_empty() {
        lines.push(format!("## Attachments ({} files)", attachments.len()));
        lines.push(String::new());
        let total: u64 = attachments.iter().map(|a| a.size).sum();
        lines.push(format!("Total size: {}", format_size(total)));
        lines.push(String::new());
    } else {
        lines.push("## Attachments".to_string());
        lines.push(String::new());
        lines.push("No attachments found.".to_string());
        lines.push(String::new());
    }
    let mut content = lines.join("\n");

    // process_email: attachment contents
    if !attachments.is_empty() {
        content.push('\n');
        for (i, attachment) in attachments.iter().enumerate() {
            content.push_str(&format!("### {}. {} ({})\n\n", i + 1, attachment.filename, format_size(attachment.size)));
            let ext = lower_extension(&attachment.path);
            if ctx.includes(&ext) && ext != ".eml" {
                let (text, method) = process_file(ctx, &attachment.path)?;
                if !is_fenced(&method) {
                    content.push_str(&format!("{text}\n\n"));
                } else {
                    let language = language_of(&attachment.path);
                    if language.is_empty() {
                        content.push_str(&format!("```\n{text}\n```\n\n"));
                    } else {
                        content.push_str(&format!("```{language}\n{text}\n```\n\n"));
                    }
                }
            } else {
                content.push_str(&format!("[Attachment type '{ext}' not supported for extraction]\n\n"));
            }
        }
    }
    content.push_str("\n---\n## Statistics\n");
    content.push_str(&format!("- Total attachments: {}\n", attachments.len()));
    if !attachments.is_empty() {
        let total: u64 = attachments.iter().map(|a| a.size).sum();
        content.push_str(&format!("- Total size: {}\n", format_size(total)));
    }
    content.push_str(&format!("- Processing time: {:.2}s\n", started.elapsed().as_secs_f64()));

    let method = format!("email+{}", attachments_source.to_lowercase().replace(' ', "_"));
    let info = EmailInfo {
        subject,
        from,
        to,
        cc,
        date,
        auth_results,
        dkim_signature,
        // Built before process_attachments() in Python, so always empty there.
        attachments_source: String::new(),
        size,
        attachments: attachments.iter().map(|a| (a.filename.clone(), a.size)).collect(),
    };
    Ok((content, method, Some(info)))
}
