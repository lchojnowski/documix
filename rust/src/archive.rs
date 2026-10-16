//! ZIP archives (`converters/archive.py`).
use std::path::Path;

use crate::convert::{is_fenced, language_of, process_file, Context, Converted};
use crate::textutils::lower_extension;
use crate::EngineError;

fn walk_all(dir: &Path, base: &Path, out: &mut Vec<String>) {
    let Ok(entries) = std::fs::read_dir(dir) else { return };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            walk_all(&path, base, out);
        } else {
            out.push(crate::scan::relpath(&path, base));
        }
    }
}

pub fn extract_zip(ctx: &Context, path: &Path) -> Result<Converted, EngineError> {
    let name = path.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
    let temp = match tempfile::tempdir() {
        Ok(dir) => dir,
        Err(error) => return Ok((format!("[Error processing ZIP file: {error}]"), "failed-exception".to_string())),
    };
    println!("📦 Extracting ZIP: {name}");

    let file = match std::fs::File::open(path) {
        Ok(file) => file,
        Err(error) => return Ok((format!("[Error processing ZIP file: {error}]"), "failed-exception".to_string())),
    };
    let mut archive = match zip::ZipArchive::new(file) {
        Ok(archive) => archive,
        Err(zip::result::ZipError::InvalidArchive(_)) | Err(zip::result::ZipError::UnsupportedArchive(_)) => {
            return Ok((format!("[Error: {name} is not a valid ZIP file]"), "failed-bad_zip".to_string()));
        }
        Err(error) => return Ok((format!("[Error processing ZIP file: {error}]"), "failed-exception".to_string())),
    };
    if let Err(error) = archive.extract(temp.path()) {
        return Ok((format!("[Error processing ZIP file: {error}]"), "failed-exception".to_string()));
    }

    let mut file_list = Vec::new();
    walk_all(temp.path(), temp.path(), &mut file_list);
    file_list.sort();

    let mut parts: Vec<String> = vec![
        format!("# ZIP Archive Contents: {name}\n\n"),
        "## Files in archive:\n\n".to_string(),
    ];
    for file in &file_list {
        parts.push(format!("- {file}\n"));
    }
    parts.push("\n## Extracted file contents:\n\n".to_string());

    let mut methods: Vec<String> = Vec::new();
    for rel in &file_list {
        let full = temp.path().join(rel);
        let ext = lower_extension(&full);
        if !ctx.includes(&ext) {
            continue;
        }
        parts.push(format!("### File: {rel}\n\n"));
        let (content, method) = process_file(ctx, &full)?;
        if !methods.contains(&method) {
            methods.push(method.clone());
        }
        if !is_fenced(&method) {
            parts.push(format!("{content}\n\n"));
        } else {
            let language = language_of(&full);
            if language.is_empty() {
                parts.push(format!("```\n{content}\n```\n\n"));
            } else {
                parts.push(format!("```{language}\n{content}\n```\n\n"));
            }
        }
    }
    // Python joins a `set()` here, whose order is hash-randomised per process;
    // the port sorts the names so its own output is stable.
    methods.sort();
    let conversion_method = format!("zip_extract+{}", methods.join("+"));
    println!("Successfully processed ZIP using extraction methods: {conversion_method}: {}", path.display());
    Ok((parts.concat(), conversion_method))
}
