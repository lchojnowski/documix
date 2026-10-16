//! Converter chains and per-file dispatch (`compiler.process_file` and the
//! `convert_*_to_text` methods, engines only).
use std::collections::HashMap;
use std::path::Path;

use crate::config::{converter_defaults, format_of_extension};
use crate::engines::{anydoc, liteparse, Outcome};
use crate::textutils::{file_language, lower_extension};
use crate::EngineError;

pub struct Context {
    pub include_extensions: Vec<String>,
    pub office_require_text_only: bool,
    pub converter_config: HashMap<String, Vec<String>>,
    pub jobs: usize,
}

impl Context {
    pub fn converters<'a>(&'a self, fmt: &str) -> Vec<&'a str> {
        match self.converter_config.get(fmt) {
            Some(list) => list.iter().map(String::as_str).collect(),
            None => converter_defaults(fmt).to_vec(),
        }
    }

    pub fn includes(&self, ext: &str) -> bool {
        self.include_extensions.iter().any(|e| e == ext)
    }
}

/// A converted document: text plus the method label.
pub type Converted = (String, String);

/// `_is_fenced`: only verbatim text/code files get a code fence.
pub fn is_fenced(method: &str) -> bool {
    method == "direct_read"
}

fn failure_label(fmt: &str, path: &Path) -> String {
    match fmt {
        "pdf" => "PDF".to_string(),
        "docx" => "DOCX".to_string(),
        "doc" => "DOC".to_string(),
        "rtf" => "RTF".to_string(),
        "epub" => "EPUB".to_string(),
        _ => lower_extension(path).trim_start_matches('.').to_uppercase(),
    }
}

/// `_run_chain` with the engines; every chain accepts the first non-empty text.
pub fn run_chain(ctx: &Context, fmt: &str, path: &Path) -> Result<Converted, EngineError> {
    for name in ctx.converters(fmt) {
        let outcome = match name {
            "anydoc" => anydoc::convert(path, ctx.office_require_text_only)?,
            "liteparse" => liteparse::convert(path, ctx.jobs),
            other => {
                return Err(EngineError(format!("converter '{other}' is not available in the Rust port")));
            }
        };
        if let Outcome::Text(text, method) = outcome {
            return Ok((text, method.to_string()));
        }
    }
    let label = failure_label(fmt, path);
    println!("WARNING: Failed to convert {label}: {}", path.display());
    let name = path.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
    Ok((format!("[Failed to convert {label} file: {name}]"), "failed".to_string()))
}

/// `converters/text.py`: UTF-8 with replacement and universal newlines, as
/// Python's text mode reads it.
pub fn read_text_file(path: &Path) -> Converted {
    let name = path.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
    match std::fs::read(path) {
        Ok(bytes) => {
            let text = String::from_utf8_lossy(&bytes).replace("\r\n", "\n").replace('\r', "\n");
            println!("Successfully read text file using direct read: {}", path.display());
            (text, "direct_read".to_string())
        }
        Err(error) => {
            println!("WARNING: Failed to read file: {}", path.display());
            println!("Error: {error}");
            (format!("[Failed to read file: {name}]"), "failed".to_string())
        }
    }
}

/// `DocumentCompiler.process_file`.
pub fn process_file(ctx: &Context, path: &Path) -> Result<Converted, EngineError> {
    let ext = lower_extension(path);
    if let Some(fmt) = format_of_extension(&ext) {
        return run_chain(ctx, fmt, path);
    }
    match ext.as_str() {
        ".zip" => crate::archive::extract_zip(ctx, path),
        ".eml" => crate::email::process_email(ctx, path).map(|(content, method, _)| (content, method)),
        _ => Ok(read_text_file(path)),
    }
}

pub fn language_of(path: &Path) -> &'static str {
    file_language(path)
}
