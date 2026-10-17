//! Text helpers with Python semantics (`documix/textutils.py`,
//! `local_ocr.has_content`, `str.split`, `os.path.splitext`, `{:,}`).
use unicode_general_category::{get_general_category, GeneralCategory};

/// `str.isspace()` for a single character: the fixed set CPython uses.
pub fn is_py_space(c: char) -> bool {
    matches!(
        c,
        '\t' | '\n' | '\u{0b}' | '\u{0c}' | '\r' | '\u{1c}' | '\u{1d}' | '\u{1e}' | '\u{1f}' | ' '
            | '\u{85}' | '\u{a0}' | '\u{1680}' | '\u{2000}'..='\u{200a}' | '\u{2028}' | '\u{2029}'
            | '\u{202f}' | '\u{205f}' | '\u{3000}'
    )
}

/// `text.strip()` with Python's whitespace definition.
pub fn py_strip(text: &str) -> &str {
    text.trim_matches(is_py_space)
}

/// `len(text.split())`.
pub fn py_word_count(text: &str) -> usize {
    text.split(is_py_space).filter(|w| !w.is_empty()).count()
}

/// `textutils.estimate_tokens`.
pub fn estimate_tokens(text: &str) -> usize {
    let stripped = py_strip(text);
    if stripped.is_empty() {
        return 0;
    }
    let words = py_word_count(stripped);
    match stripped.chars().last() {
        Some('.') | Some('!') | Some('?') => words + 1,
        _ => words,
    }
}

/// `textutils.format_size` (`f"{size:.1f} {unit}"`).
pub fn format_size(size_bytes: u64) -> String {
    let mut size = size_bytes as f64;
    for unit in ["B", "KB", "MB", "GB"] {
        if size < 1024.0 {
            return format!("{size:.1} {unit}");
        }
        size /= 1024.0;
    }
    format!("{size:.1} TB")
}

/// Python `{n:,}`.
pub fn thousands(n: usize) -> String {
    let digits = n.to_string();
    let mut out = String::with_capacity(digits.len() + digits.len() / 3);
    for (i, ch) in digits.chars().enumerate() {
        if i > 0 && (digits.len() - i) % 3 == 0 {
            out.push(',');
        }
        out.push(ch);
    }
    out
}

/// `os.path.splitext(name)[1]` on a bare file name: the extension including
/// the dot, empty when the name has none. Leading dots never start an
/// extension (`.bashrc` -> "", `.a.b` -> ".b", `a.` -> ".").
pub fn extension_of(name: &str) -> &str {
    let Some(dot) = name.rfind('.') else { return "" };
    let leading_dots = name.chars().take_while(|&c| c == '.').count();
    if dot < leading_dots {
        return "";
    }
    &name[dot..]
}

/// Lower-cased extension of a path's final component, like
/// `os.path.splitext(path.lower())[1]`.
pub fn lower_extension(path: &std::path::Path) -> String {
    let name = path.file_name().map(|n| n.to_string_lossy().to_lowercase()).unwrap_or_default();
    extension_of(&name).to_string()
}

/// `textutils.get_file_language`.
pub fn file_language(path: &std::path::Path) -> &'static str {
    crate::config::language_for_extension(&lower_extension(path))
}

/// `local_ocr.has_content`: at least one character that is neither Python
/// whitespace nor a control (Cc) / format (Cf) character.
pub fn has_content(text: &str) -> bool {
    text.chars().any(|c| {
        !is_py_space(c)
            && !matches!(get_general_category(c), GeneralCategory::Control | GeneralCategory::Format)
    })
}

/// `len(str)` is a code point count.
pub fn py_len(text: &str) -> usize {
    text.chars().count()
}

/// Upper-cased extension without the dot, used in failure placeholders
/// (`ext[1:].upper()`); "document" when the name has no extension.
pub fn label_of(path: &std::path::Path) -> String {
    let ext = lower_extension(path);
    if ext.is_empty() { "document".to_string() } else { ext[1..].to_uppercase() }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tokens_match_python_examples() {
        assert_eq!(estimate_tokens(""), 0);
        assert_eq!(estimate_tokens("Hello world"), 2);
        assert_eq!(estimate_tokens("Hello, world!"), 3);
        assert_eq!(estimate_tokens("This is a test. With two sentences."), 8);
    }

    #[test]
    fn sizes_and_thousands() {
        assert_eq!(format_size(0), "0.0 B");
        assert_eq!(format_size(1536), "1.5 KB");
        assert_eq!(thousands(0), "0");
        assert_eq!(thousands(999), "999");
        assert_eq!(thousands(1000), "1,000");
        assert_eq!(thousands(1234567), "1,234,567");
    }

    #[test]
    fn splitext_quirks() {
        assert_eq!(extension_of(".bashrc"), "");
        assert_eq!(extension_of("..foo"), "");
        assert_eq!(extension_of(".a.b"), ".b");
        assert_eq!(extension_of("a."), ".");
        assert_eq!(extension_of("archive.tar.gz"), ".gz");
        assert_eq!(extension_of("noext"), "");
    }

    #[test]
    fn content_rules() {
        assert!(!has_content("\u{a0}\n\u{200b}\0"));
        assert!(has_content(" a "));
    }
}
