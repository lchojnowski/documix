//! Static configuration mirrored from `documix/config.py`.

pub const ENGINE_CONVERTERS: &[&str] = &["anydoc", "liteparse"];

/// Format keys in the order `documix/config.py` declares them.
pub const FORMATS: &[&str] = &["pdf", "docx", "doc", "rtf", "epub", "office"];

pub fn converter_defaults(fmt: &str) -> &'static [&'static str] {
    match fmt {
        "epub" => &["anydoc"],
        _ => &["anydoc", "liteparse"],
    }
}

/// Every converter name the Python CLI accepts (defaults + legacy), used to
/// reproduce its validation messages. Legacy names are rejected explicitly.
pub fn converter_choices(fmt: &str) -> &'static [&'static str] {
    match fmt {
        "pdf" => &["anydoc", "liteparse", "mineru", "pdfplumber", "markitdown-uvx", "markitdown",
                   "pdftotext", "paddleocr", "tesseract"],
        "docx" => &["anydoc", "liteparse", "pandoc", "docx2txt"],
        "doc" => &["anydoc", "liteparse", "soffice"],
        "rtf" => &["anydoc", "liteparse", "pandoc", "unrtf", "striprtf"],
        "epub" => &["anydoc", "ebook-convert"],
        "office" => &["anydoc", "liteparse", "markitdown"],
        _ => &[],
    }
}

/// Extension (lower case, with dot) -> converter format key.
pub fn format_of_extension(ext: &str) -> Option<&'static str> {
    Some(match ext {
        ".pdf" => "pdf",
        ".docx" | ".docm" => "docx",
        ".doc" => "doc",
        ".rtf" => "rtf",
        ".epub" => "epub",
        ".xlsx" | ".xlsm" | ".xlsb" | ".xls" | ".pptx" | ".pptm" | ".ppsx" | ".ppsm" | ".ppt"
        | ".pps" | ".pot" | ".odt" | ".ods" | ".odp" | ".csv" => "office",
        _ => return None,
    })
}

pub const DEFAULT_EXTENSIONS: &[&str] = &[
    ".pdf", ".epub", ".docx", ".docm", ".doc", ".xlsx", ".xlsm", ".xls",
    ".pptx", ".pptm", ".ppt", ".odt", ".ods", ".odp", ".rtf", ".txt", ".md",
    ".py", ".rb", ".js", ".html", ".css", ".json", ".yml", ".yaml", ".zip", ".eml",
];

pub const SUSPICIOUS_EXTENSIONS: &[&str] = &[".exe", ".bat", ".sh", ".com", ".vbs", ".ps1", ".py", ".rb"];

pub fn language_for_extension(ext: &str) -> &'static str {
    match ext {
        ".py" => "python",
        ".rb" => "ruby",
        ".js" => "javascript",
        ".html" => "html",
        ".css" => "css",
        ".json" => "json",
        ".yml" | ".yaml" => "yaml",
        ".md" => "markdown",
        ".txt" => "text",
        ".sh" => "bash",
        ".java" => "java",
        ".c" | ".h" => "c",
        ".cpp" => "cpp",
        ".php" => "php",
        ".sql" => "sql",
        ".xml" => "xml",
        ".go" => "go",
        ".rs" => "rust",
        ".ts" => "typescript",
        ".swift" => "swift",
        ".kt" => "kotlin",
        ".dart" => "dart",
        ".pl" => "perl",
        ".r" => "r",
        ".lua" => "lua",
        ".scala" => "scala",
        ".cs" => "csharp",
        ".vb" => "vb",
        _ => "",
    }
}

/// Office containers whose embedded media matters for --office-require-text-only
/// (`converters/anydoc.py: OFFICE_EXTENSIONS`).
pub const OFFICE_MEDIA_EXTENSIONS: &[&str] = &[
    ".xlsx", ".xlsm", ".xls", ".xlsb", ".pptx", ".pptm", ".ppsx", ".ppsm", ".ppt",
    ".odt", ".ods", ".odp",
];
