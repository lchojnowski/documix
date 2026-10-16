//! Primary engine (`converters/anydoc.py`). Document-level failures decline;
//! panics are engine failures that abort the run.
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::path::Path;

use crate::engines::Outcome;
use crate::textutils::{has_content, label_of, lower_extension};
use crate::EngineError;

/// `has_embedded_media`: any OOXML `.rels` image relationship, OpenDocument
/// `Pictures/` member or `/media/` member means pictures are present.
pub fn has_embedded_media(path: &Path) -> bool {
    let Ok(file) = std::fs::File::open(path) else { return false };
    let Ok(mut archive) = zip::ZipArchive::new(file) else { return false };
    let names: Vec<String> = archive.file_names().filter_map(|n| n.ok()).map(|n| n.into_owned()).collect();
    for name in names {
        if name.starts_with("Pictures/") || name.contains("/media/") {
            return true;
        }
        if name.ends_with(".rels") {
            if let Ok(mut member) = archive.by_name(&name) {
                let mut bytes = Vec::new();
                if std::io::Read::read_to_end(&mut member, &mut bytes).is_ok() && rels_has_image(&bytes) {
                    return true;
                }
            }
        }
    }
    false
}

/// Python: `re.compile(rb'Type="[^"]*/image"')`.
fn rels_has_image(bytes: &[u8]) -> bool {
    let needle = b"Type=\"";
    let mut i = 0;
    while let Some(pos) = find(&bytes[i..], needle) {
        let start = i + pos + needle.len();
        let Some(end_rel) = bytes[start..].iter().position(|&b| b == b'"') else { break };
        let value = &bytes[start..start + end_rel];
        if value.ends_with(b"/image") {
            return true;
        }
        i = start + end_rel + 1;
    }
    false
}

fn find(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    haystack.windows(needle.len()).position(|w| w == needle)
}

pub fn convert(path: &Path, require_text_only: bool) -> Result<Outcome, EngineError> {
    let ext = lower_extension(path);
    let label = label_of(path);
    let strict = require_text_only && crate::config::OFFICE_MEDIA_EXTENSIONS.contains(&ext.as_str());

    let attempt = catch_unwind(AssertUnwindSafe(|| -> Result<Result<String, ::anydoc::ConvertError>, Outcome> {
        if strict {
            let data = match std::fs::read(path) {
                Ok(data) => data,
                Err(error) => {
                    println!("anydoc could not read {}: {error}", path.display());
                    return Err(Outcome::Declined);
                }
            };
            let format = ::anydoc::Format::from_path(path);
            let document = match ::anydoc::to_document(&data, format) {
                Ok(document) => document,
                Err(error) => return Ok(Err(error)),
            };
            if !document.assets.is_empty() || has_embedded_media(path) {
                println!("anydoc: {} contains embedded media; rejected by --office-require-text-only", path.display());
                return Err(Outcome::Text(format!("[Failed to convert {label} file: unassessed_media]"), "failed"));
            }
            Ok(::anydoc::to_markdown_bytes(&data, format))
        } else {
            Ok(::anydoc::to_markdown(path))
        }
    }));

    let text = match attempt {
        Err(panic) => {
            let detail = panic
                .downcast_ref::<String>()
                .cloned()
                .or_else(|| panic.downcast_ref::<&str>().map(|s| s.to_string()))
                .unwrap_or_else(|| "panic".to_string());
            return Err(EngineError(format!("anydoc panicked on {}: {detail}", path.display())));
        }
        Ok(Err(outcome)) => return Ok(outcome),
        Ok(Ok(Err(error))) => {
            println!("anydoc declined {}: {error:?}", path.display());
            return Ok(Outcome::Declined);
        }
        Ok(Ok(Ok(text))) => text,
    };
    if !has_content(&text) {
        println!("anydoc produced no text for {}", path.display());
        return Ok(Outcome::Declined);
    }
    println!("Successfully converted {label} using anydoc: {}", path.display());
    Ok(Outcome::Text(text, "anydoc"))
}
