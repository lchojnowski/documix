//! Port of Python `html2text` 2025.4.15 (as configured by DocuMix:
//! `body_width=0`, links and images kept) on top of a port of CPython 3.13's
//! `html.parser.HTMLParser` with `convert_charrefs=False`.
//!
//! See `docs/html2text-spec.md`. The structure mirrors the Python code
//! deliberately (same method names, same state), because the output has to
//! match byte for byte.
use std::collections::HashMap;
use std::sync::OnceLock;

use fancy_regex::Regex;
use unicode_general_category::{get_general_category, GeneralCategory};

use crate::textutils::is_py_space;

/// Python raised an exception inside html2text (ValueError / AssertionError);
/// the caller falls back to the plain-text body like `get_email_body` does.
#[derive(Debug)]
pub struct Html2TextError(pub String);

// ---------------------------------------------------------------------------
// Tables
// ---------------------------------------------------------------------------

fn html5_entities() -> &'static HashMap<&'static str, &'static str> {
    static TABLE: OnceLock<HashMap<&'static str, &'static str>> = OnceLock::new();
    TABLE.get_or_init(|| {
        entities::ENTITIES
            .iter()
            .map(|e| (e.entity.trim_start_matches('&'), e.characters))
            .collect()
    })
}

/// `config.UNIFIABLE` with the nbsp placeholder installed by `__init__`.
fn unifiable(name: &str) -> Option<&'static str> {
    Some(match name {
        "rsquo" | "lsquo" => "'",
        "rdquo" | "ldquo" => "\"",
        "copy" => "(C)",
        "mdash" => "--",
        "nbsp" => "&nbsp_place_holder;",
        "rarr" => "->",
        "larr" => "<-",
        "middot" => "*",
        "ndash" => "-",
        "oelig" => "oe",
        "aelig" => "ae",
        "agrave" | "aacute" | "acirc" | "atilde" | "auml" | "aring" => "a",
        "egrave" | "eacute" | "ecirc" | "euml" => "e",
        "igrave" | "iacute" | "icirc" | "iuml" => "i",
        "ograve" | "oacute" | "ocirc" | "otilde" | "ouml" => "o",
        "ugrave" | "uacute" | "ucirc" | "uuml" => "u",
        "lrm" | "rlm" => "",
        _ => return None,
    })
}

/// `utils.unifiable_n`: code point -> ASCII replacement (nbsp excluded).
fn unifiable_n(cp: u32) -> Option<&'static str> {
    Some(match cp {
        0x2019 | 0x2018 => "'",
        0x201D | 0x201C => "\"",
        0xA9 => "(C)",
        0x2014 => "--",
        0x2192 => "->",
        0x2190 => "<-",
        0xB7 => "*",
        0x2013 => "-",
        0x153 => "oe",
        0xE6 => "ae",
        0xE0..=0xE5 => "a",
        0xE8..=0xEB => "e",
        0xEC..=0xEF => "i",
        0xF2..=0xF6 => "o",
        0xF9..=0xFC => "u",
        0x200E | 0x200F => "",
        _ => return None,
    })
}

/// `utils.control_character_replacements` (Windows-1252 remap).
fn control_character_replacement(cp: u32) -> u32 {
    match cp {
        0x80 => 0x20AC, 0x82 => 0x201A, 0x83 => 0x0192, 0x84 => 0x201E, 0x85 => 0x2026,
        0x86 => 0x2020, 0x87 => 0x2021, 0x88 => 0x02C6, 0x89 => 0x2030, 0x8A => 0x0160,
        0x8B => 0x2039, 0x8C => 0x0152, 0x8E => 0x017D, 0x91 => 0x2018, 0x92 => 0x2019,
        0x93 => 0x201C, 0x94 => 0x201D, 0x95 => 0x2022, 0x96 => 0x2013, 0x97 => 0x2014,
        0x98 => 0x02DC, 0x99 => 0x2122, 0x9A => 0x0161, 0x9B => 0x203A, 0x9C => 0x0153,
        0x9E => 0x017E, 0x9F => 0x0178,
        other => other,
    }
}

/// Python `html.unescape` for a single `&...;` reference (used for attribute
/// values; `_invalid_charrefs` / `_invalid_codepoints` tables included).
fn py_unescape_ref(reference: &str) -> String {
    let body = &reference[1..];
    if let Some(num) = body.strip_prefix('#') {
        let num = num.trim_end_matches(';');
        let value = if let Some(hex) = num.strip_prefix(['x', 'X']) {
            u32::from_str_radix(hex, 16).ok()
        } else {
            num.parse::<u32>().ok()
        };
        let Some(value) = value else { return reference.to_string() };
        let invalid = [
            (0x00, "\u{fffd}"), (0x0d, "\r"), (0x80, "\u{20ac}"), (0x81, "\u{81}"), (0x82, "\u{201a}"),
            (0x83, "\u{192}"), (0x84, "\u{201e}"), (0x85, "\u{2026}"), (0x86, "\u{2020}"), (0x87, "\u{2021}"),
            (0x88, "\u{2c6}"), (0x89, "\u{2030}"), (0x8a, "\u{160}"), (0x8b, "\u{2039}"), (0x8c, "\u{152}"),
            (0x8d, "\u{8d}"), (0x8e, "\u{17d}"), (0x8f, "\u{8f}"), (0x90, "\u{90}"), (0x91, "\u{2018}"),
            (0x92, "\u{2019}"), (0x93, "\u{201c}"), (0x94, "\u{201d}"), (0x95, "\u{2022}"), (0x96, "\u{2013}"),
            (0x97, "\u{2014}"), (0x98, "\u{2dc}"), (0x99, "\u{2122}"), (0x9a, "\u{161}"), (0x9b, "\u{203a}"),
            (0x9c, "\u{153}"), (0x9d, "\u{9d}"), (0x9e, "\u{17e}"), (0x9f, "\u{178}"),
        ];
        if let Some((_, rep)) = invalid.iter().find(|(k, _)| *k == value) {
            return rep.to_string();
        }
        if (0xD800..=0xDFFF).contains(&value) || value > 0x10FFFF {
            return "\u{fffd}".to_string();
        }
        let invalid_codepoints = (0x1..=0x8).contains(&value)
            || (0xe..=0x1f).contains(&value)
            || (0x7f..=0x9f).contains(&value)
            || (0xfdd0..=0xfdef).contains(&value)
            || matches!(value, 0xb | 0xfffe | 0xffff | 0x1fffe | 0x1ffff | 0x2fffe | 0x2ffff | 0x3fffe | 0x3ffff
                | 0x4fffe | 0x4ffff | 0x5fffe | 0x5ffff | 0x6fffe | 0x6ffff | 0x7fffe | 0x7ffff | 0x8fffe
                | 0x8ffff | 0x9fffe | 0x9ffff | 0xafffe | 0xaffff | 0xbfffe | 0xbffff | 0xcfffe | 0xcffff
                | 0xdfffe | 0xdffff | 0xefffe | 0xeffff | 0xffffe | 0xfffff | 0x10fffe | 0x10ffff);
        if invalid_codepoints {
            return String::new();
        }
        return char::from_u32(value).map(|c| c.to_string()).unwrap_or_else(|| "\u{fffd}".to_string());
    }
    if let Some(value) = html5_entities().get(body) {
        return value.to_string();
    }
    // Longest known prefix (Python falls back to this for names without ';').
    let mut end = body.len();
    while end > 1 {
        end -= 1;
        if !body.is_char_boundary(end) {
            continue;
        }
        if let Some(value) = html5_entities().get(&body[..end]) {
            return format!("{value}{}", &body[end..]);
        }
    }
    reference.to_string()
}

// ---------------------------------------------------------------------------
// Regexes from CPython html/parser.py (3.13.12) and html2text/config.py
// ---------------------------------------------------------------------------

struct Res {
    entityref: Regex,
    charref: Regex,
    incomplete: Regex,
    incomplete_charref: Regex,
    attr_charref: Regex,
    starttagopen: Regex,
    endtagopen: Regex,
    commentclose: Regex,
    commentabruptclose: Regex,
    tagfind_tolerant: Regex,
    attrfind_tolerant: Regex,
    locatetagend: Regex,
    absolute_url: Regex,
}

fn res() -> &'static Res {
    static RES: OnceLock<Res> = OnceLock::new();
    RES.get_or_init(|| Res {
        entityref: Regex::new(r"&([a-zA-Z][-.a-zA-Z0-9]*)[^a-zA-Z0-9]").unwrap(),
        charref: Regex::new(r"&#(?:[0-9]+|[xX][0-9a-fA-F]+)[^0-9a-fA-F]").unwrap(),
        incomplete: Regex::new(r"&[a-zA-Z#]").unwrap(),
        incomplete_charref: Regex::new(r"&#(?:[0-9]|[xX][0-9a-fA-F])").unwrap(),
        attr_charref: Regex::new(r"&(#[0-9]+|#[xX][0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]*)[;=]?").unwrap(),
        starttagopen: Regex::new(r"<[a-zA-Z]").unwrap(),
        endtagopen: Regex::new(r"</[a-zA-Z]").unwrap(),
        commentclose: Regex::new(r"--!?>").unwrap(),
        commentabruptclose: Regex::new(r"-?>").unwrap(),
        tagfind_tolerant: Regex::new(r"([a-zA-Z][^\t\n\r\f />]*)(?:[\t\n\r\f ]|/(?!>))*").unwrap(),
        attrfind_tolerant: Regex::new(concat!(
            r#"((?<=['"\t\n\r\f /])[^\t\n\r\f />][^\t\n\r\f /=>]*)"#,
            r#"([\t\n\r\f ]*=[\t\n\r\f ]*('[^']*'|"[^"]*"|(?!['"])[^>\t\n\r\f ]*))?"#,
            r#"(?:[\t\n\r\f ]|/(?!>))*"#,
        ))
        .unwrap(),
        locatetagend: Regex::new(concat!(
            r#"[a-zA-Z][^\t\n\r\f />]*[\t\n\r\f /]*"#,
            r#"(?:(?<=['"\t\n\r\f /])[^\t\n\r\f />][^\t\n\r\f /=>]*"#,
            r#"(?:[\t\n\r\f ]*=[\t\n\r\f ]*(?:'[^']*'|"[^"]*"|(?!['"])[^>\t\n\r\f ]*))?"#,
            r#"[\t\n\r\f /]*)*>?"#,
        ))
        .unwrap(),
        absolute_url: Regex::new(r"^[a-zA-Z+]+://").unwrap(),
    })
}

fn match_at(re: &Regex, text: &str, pos: usize) -> Option<(usize, usize)> {
    // Python `re.match(text, pos)`: anchored at pos.
    re.find_from_pos(text, pos).ok().flatten().filter(|m| m.start() == pos).map(|m| (m.start(), m.end()))
}

fn search_from(re: &Regex, text: &str, pos: usize) -> Option<(usize, usize)> {
    re.find_from_pos(text, pos).ok().flatten().map(|m| (m.start(), m.end()))
}

// ---------------------------------------------------------------------------
// Markdown escaping (html2text/utils.py)
// ---------------------------------------------------------------------------

fn is_py_digit(c: char) -> bool {
    get_general_category(c) == GeneralCategory::DecimalNumber
}

/// `escape_md`: backslash before `\ [ ] ( )`.
pub fn escape_md(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    for c in text.chars() {
        if matches!(c, '\\' | '[' | ']' | '(' | ')') {
            out.push('\\');
        }
        out.push(c);
    }
    out
}

/// `escape_md_section` with `snob=False`.
pub fn escape_md_section(text: &str) -> String {
    // 1. RE_MD_BACKSLASH_MATCHER: a backslash followed by one of RE_SLASH_CHARS is doubled.
    let chars: Vec<char> = text.chars().collect();
    let mut step1 = String::with_capacity(text.len() + 8);
    for (i, &c) in chars.iter().enumerate() {
        if c == '\\' && chars.get(i + 1).map_or(false, |n| "\\`*_{}[]()#+-.!".contains(*n)) {
            step1.push('\\');
        }
        step1.push(c);
    }
    // 2-4: line-anchored (MULTILINE) dot / plus / dash escapes.
    let step2 = line_escape(&step1, |line, rest| {
        // ^(\s*\d+)(\.)(?=\s)
        let ws = line.iter().take_while(|c| is_py_space(**c)).count();
        let digits = line[ws..].iter().take_while(|c| is_py_digit(**c)).count();
        if digits == 0 { return None; }
        let dot = ws + digits;
        if line.get(dot) != Some(&'.') { return None; }
        let after = line.get(dot + 1).copied().or(rest);
        after.filter(|c| is_py_space(*c)).map(|_| dot)
    });
    let step3 = line_escape(&step2, |line, rest| {
        // ^(\s*)(\+)(?=\s)
        let ws = line.iter().take_while(|c| is_py_space(**c)).count();
        if line.get(ws) != Some(&'+') { return None; }
        let after = line.get(ws + 1).copied().or(rest);
        after.filter(|c| is_py_space(*c)).map(|_| ws)
    });
    line_escape(&step3, |line, rest| {
        // ^(\s*)(-)(?=\s|\-)
        let ws = line.iter().take_while(|c| is_py_space(**c)).count();
        if line.get(ws) != Some(&'-') { return None; }
        let after = line.get(ws + 1).copied().or(rest);
        after.filter(|c| is_py_space(*c) || *c == '-').map(|_| ws)
    })
}

/// Apply `find(line, next_char_after_line) -> Option<insert_index>` to every
/// `\n`-separated line (Python MULTILINE `^`), inserting a backslash.
fn line_escape(text: &str, find: impl Fn(&[char], Option<char>) -> Option<usize>) -> String {
    let lines: Vec<&str> = text.split('\n').collect();
    let mut out = String::with_capacity(text.len() + 4);
    for (i, line) in lines.iter().enumerate() {
        let chars: Vec<char> = line.chars().collect();
        let rest = if i + 1 < lines.len() { Some('\n') } else { None };
        match find(&chars, rest) {
            Some(idx) => {
                out.extend(chars[..idx].iter());
                out.push('\\');
                out.extend(chars[idx..].iter());
            }
            None => out.push_str(line),
        }
        if i + 1 < lines.len() {
            out.push('\n');
        }
    }
    out
}

fn hn(tag: &str) -> usize {
    let bytes = tag.as_bytes();
    if bytes.len() == 2 && bytes[0] == b'h' && (b'1'..=b'9').contains(&bytes[1]) {
        (bytes[1] - b'0') as usize
    } else {
        0
    }
}

/// Python `int()` on a `start` attribute: accepts surrounding whitespace,
/// a sign, underscores between digits and Unicode decimal digits.
fn py_int(value: &str) -> Option<i64> {
    let trimmed = value.trim_matches(is_py_space);
    let (negative, digits) = match trimmed.strip_prefix('-') {
        Some(rest) => (true, rest),
        None => (false, trimmed.strip_prefix('+').unwrap_or(trimmed)),
    };
    if digits.is_empty() || digits.starts_with('_') || digits.ends_with('_') || digits.contains("__") {
        return None;
    }
    let mut value: i64 = 0;
    for c in digits.chars() {
        if c == '_' { continue; }
        let d = c.to_digit(10).or_else(|| if is_py_digit(c) { unicode_digit_value(c) } else { None })?;
        value = value.checked_mul(10)?.checked_add(d as i64)?;
    }
    Some(if negative { -value } else { value })
}

fn unicode_digit_value(c: char) -> Option<u32> {
    // Decimal digits come in contiguous blocks of ten starting at a code point
    // whose digit value is 0; scan backwards to find it.
    let mut cp = c as u32;
    let mut value = 0;
    while value < 10 {
        let prev = char::from_u32(cp)?;
        if get_general_category(prev) != GeneralCategory::DecimalNumber { return None; }
        if cp == 0 || !char::from_u32(cp - 1).map_or(false, |p| get_general_category(p) == GeneralCategory::DecimalNumber) {
            return Some(value);
        }
        cp -= 1;
        value += 1;
    }
    None
}

// ---------------------------------------------------------------------------
// Renderer
// ---------------------------------------------------------------------------

#[derive(Clone)]
struct ListElement {
    name: String,
    num: i64,
}

type Attrs = HashMap<String, Option<String>>;

pub struct Html2Text {
    // config
    protect_links: bool,
    // parser state
    cdata_elem: Option<String>,
    escapable: bool,
    // renderer state (names follow the Python attributes)
    quiet: i32,
    p_p: usize,
    start: bool,
    space: bool,
    br_toggle: String,
    last_was_nl: bool,
    last_was_list: bool,
    blockquote: usize,
    pre: bool,
    startpre: bool,
    code: bool,
    quote: bool,
    astack: Vec<Option<Attrs>>,
    maybe_automatic_link: Option<String>,
    empty_link: bool,
    list: Vec<ListElement>,
    list_code_indent: String,
    pre_indent: String,
    stressed: bool,
    preceding_stressed: bool,
    preceding_data: String,
    current_tag: String,
    inheader: bool,
    table_start: bool,
    split_next_td: bool,
    td_count: usize,
    abbr_title: Option<String>,
    abbr_data: Option<String>,
    abbr_list: Vec<(String, String)>,
    outtextlist: Vec<String>,
    error: Option<String>,
}

impl Html2Text {
    pub fn new(protect_links: bool) -> Self {
        Html2Text {
            protect_links,
            cdata_elem: None,
            escapable: true,
            quiet: 0,
            p_p: 0,
            start: false,
            space: false,
            br_toggle: String::new(),
            last_was_nl: false,
            last_was_list: false,
            blockquote: 0,
            pre: false,
            startpre: false,
            code: false,
            quote: false,
            astack: Vec::new(),
            maybe_automatic_link: None,
            empty_link: false,
            list: Vec::new(),
            list_code_indent: String::new(),
            pre_indent: String::new(),
            stressed: false,
            preceding_stressed: false,
            preceding_data: String::new(),
            current_tag: String::new(),
            inheader: false,
            table_start: false,
            split_next_td: false,
            td_count: 0,
            abbr_title: None,
            abbr_data: None,
            abbr_list: Vec::new(),
            outtextlist: Vec::new(),
            error: None,
        }
    }

    /// `HTML2Text.handle(data)`; state carries over between calls like the
    /// shared instance in `EmailProcessor`.
    pub fn handle(&mut self, html: &str) -> Result<String, Html2TextError> {
        self.start = true;
        self.error = None;
        let data = html.replace("</' + 'script>", "</ignore>");
        self.goahead(&data);
        if let Some(error) = self.error.take() {
            return Err(Html2TextError(error));
        }
        // finish()
        self.pbr();
        self.o("", false, Force::End);
        let text = self.outtextlist.concat().replace("&nbsp_place_holder;", " ");
        self.outtextlist.clear();
        Ok(text)
    }

    // ----- tokenizer (HTMLParser.goahead with end=True) --------------------

    fn set_cdata_mode(&mut self, elem: &str, escapable: bool) {
        self.cdata_elem = Some(elem.to_lowercase());
        self.escapable = escapable;
    }

    fn clear_cdata_mode(&mut self) {
        self.cdata_elem = None;
        self.escapable = true;
    }

    /// Position of the next "interesting" character from `i`, like
    /// `self.interesting.search(rawdata, i)`.
    fn find_interesting(&self, rawdata: &str, i: usize) -> Option<usize> {
        match &self.cdata_elem {
            None => rawdata[i..].find(['&', '<']).map(|p| i + p),
            Some(elem) if elem == "plaintext" => None,
            Some(elem) => {
                let needle = format!("</{elem}");
                let lower = rawdata.to_ascii_lowercase();
                let mut pos = i;
                loop {
                    let found_tag = lower[pos..].find(&needle).map(|p| pos + p).filter(|&p| {
                        rawdata[p + needle.len()..].chars().next().map_or(false, |c| matches!(c, '\t' | '\n' | '\r' | '\u{c}' | ' ' | '/' | '>'))
                    });
                    let found_amp = if self.escapable { rawdata[pos..].find('&').map(|p| pos + p) } else { None };
                    let candidate_tag = lower[pos..].find(&needle).map(|p| pos + p);
                    match (found_tag, found_amp, candidate_tag) {
                        (Some(t), Some(a), _) => return Some(t.min(a)),
                        (Some(t), None, _) => return Some(t),
                        (None, Some(a), Some(c)) if a < c => return Some(a),
                        (None, Some(a), None) => return Some(a),
                        (None, _, Some(c)) => { pos = c + needle.len(); if pos >= rawdata.len() { return found_amp; } }
                        (None, None, None) => return None,
                    }
                }
            }
        }
    }

    fn goahead(&mut self, rawdata: &str) {
        let n = rawdata.len();
        let mut i = 0;
        let r = res();
        while i < n {
            if self.error.is_some() {
                return;
            }
            let j = match self.find_interesting(rawdata, i) {
                Some(j) => j,
                None => {
                    if self.cdata_elem.is_some() {
                        break;
                    }
                    n
                }
            };
            if i < j {
                self.handle_data(&rawdata[i..j], false);
            }
            i = j;
            if i == n {
                break;
            }
            let rest = &rawdata[i..];
            if rest.starts_with('<') {
                let k: Option<usize> = if match_at(&r.starttagopen, rawdata, i).is_some() {
                    self.parse_starttag(rawdata, i)
                } else if rest.starts_with("</") {
                    self.parse_endtag(rawdata, i)
                } else if rest.starts_with("<!--") {
                    self.parse_comment(rawdata, i)
                } else if rest.starts_with("<?") {
                    rawdata[i + 2..].find('>').map(|p| i + 2 + p + 1)
                } else if rest.starts_with("<!") {
                    self.parse_html_declaration(rawdata, i)
                } else {
                    self.handle_data("<", false);
                    Some(i + 1)
                };
                match k {
                    Some(k) => i = k,
                    None => {
                        // end=True: incomplete markup swallows the rest.
                        if rest.starts_with("</") && i + 2 == n {
                            self.handle_data("</", false);
                        }
                        i = n;
                    }
                }
            } else if rest.starts_with("&#") {
                if let Some((_, end)) = match_at(&r.charref, rawdata, i) {
                    let mut k = end;
                    let name = &rawdata[i + 2..end - 1];
                    self.handle_charref(name);
                    if !rawdata[..k].ends_with(';') {
                        k -= 1;
                    }
                    i = k;
                    continue;
                }
                if match_at(&r.incomplete_charref, rawdata, i).is_some() {
                    let name = rawdata[i + 2..].to_string();
                    self.handle_charref(&name);
                    i = n;
                    break;
                } else if i + 3 < n {
                    self.handle_data("&#", false);
                    i += 2;
                } else {
                    break;
                }
            } else if rest.starts_with('&') {
                if let Some((_, end)) = match_at(&r.entityref, rawdata, i) {
                    let mut k = end;
                    let name = &rawdata[i + 1..end - 1];
                    self.handle_entityref(name);
                    if !rawdata[..k].ends_with(';') {
                        k -= 1;
                    }
                    i = k;
                    continue;
                }
                if match_at(&r.incomplete, rawdata, i).is_some() {
                    let name = rawdata[i + 1..].to_string();
                    self.handle_entityref(&name);
                    i = n;
                    break;
                } else if i + 1 < n {
                    self.handle_data("&", false);
                    i += 1;
                } else {
                    break;
                }
            } else {
                unreachable!("interesting.search() lied");
            }
        }
        if i < n && self.error.is_none() {
            self.handle_data(&rawdata[i..n], false);
        }
    }

    fn parse_html_declaration(&mut self, rawdata: &str, i: usize) -> Option<usize> {
        let rest = &rawdata[i..];
        if rest.starts_with("<!--") {
            self.parse_comment(rawdata, i)
        } else if rest.starts_with("<![CDATA[") {
            rawdata[i + 9..].find("]]>").map(|p| i + 9 + p + 3)
        } else if rest.len() >= 9 && rest[..9].eq_ignore_ascii_case("<!doctype") {
            rawdata[i + 9..].find('>').map(|p| i + 9 + p + 1)
        } else {
            rawdata[i + 2..].find('>').map(|p| i + 2 + p + 1)
        }
    }

    fn parse_comment(&mut self, rawdata: &str, i: usize) -> Option<usize> {
        let r = res();
        if let Some((_, end)) = search_from(&r.commentclose, rawdata, i + 4) {
            return Some(end);
        }
        match_at(&r.commentabruptclose, rawdata, i + 4).map(|(_, end)| end)
    }

    fn parse_starttag(&mut self, rawdata: &str, i: usize) -> Option<usize> {
        let r = res();
        let (_, j) = match_at(&r.locatetagend, rawdata, i + 1)?;
        if !rawdata[..j].ends_with('>') {
            return None;
        }
        let endpos = j;
        let (_, mut k) = match_at(&r.tagfind_tolerant, rawdata, i + 1)?;
        let tag_match = r.tagfind_tolerant.captures_from_pos(rawdata, i + 1).ok().flatten()?;
        let tag = tag_match.get(1)?.as_str().to_lowercase();
        let mut attrs: Vec<(String, Option<String>)> = Vec::new();
        while k < endpos {
            let Some(caps) = r.attrfind_tolerant.captures_from_pos(rawdata, k).ok().flatten() else { break };
            let whole = caps.get(0)?;
            if whole.start() != k {
                break;
            }
            let attrname = caps.get(1).map(|m| m.as_str()).unwrap_or("");
            let rest = caps.get(2).map(|m| m.as_str());
            let mut attrvalue = caps.get(3).map(|m| m.as_str().to_string());
            if rest.map_or(true, |s| s.is_empty()) {
                attrvalue = None;
            } else if let Some(v) = &attrvalue {
                let bytes = v.as_bytes();
                if bytes.len() >= 2 && ((bytes[0] == b'\'' && bytes[bytes.len() - 1] == b'\'') || (bytes[0] == b'"' && bytes[bytes.len() - 1] == b'"')) {
                    attrvalue = Some(v[1..v.len() - 1].to_string());
                } else if bytes.len() == 1 && (bytes[0] == b'\'' || bytes[0] == b'"') {
                    // Python: value[:1] == '\'' == value[-1:] is true for a lone quote
                    attrvalue = Some(String::new());
                }
            }
            if let Some(v) = &attrvalue {
                if !v.is_empty() {
                    attrvalue = Some(self.unescape_attrvalue(v));
                }
            }
            attrs.push((attrname.to_lowercase(), attrvalue));
            k = whole.end();
        }
        let end = rawdata[k..endpos].trim_matches(|c: char| is_py_space(c));
        if end != ">" && end != "/>" {
            let text = rawdata[i..endpos].to_string();
            self.handle_data(&text, false);
            return Some(endpos);
        }
        let attr_map: Attrs = attrs.into_iter().collect();
        if end.ends_with("/>") {
            self.handle_tag(&tag, Some(attr_map), true);
            self.handle_tag(&tag, None, false);
        } else {
            self.handle_tag(&tag, Some(attr_map), true);
            if matches!(tag.as_str(), "script" | "style" | "xmp" | "iframe" | "noembed" | "noframes" | "plaintext") {
                self.set_cdata_mode(&tag, false);
            } else if matches!(tag.as_str(), "textarea" | "title") {
                self.set_cdata_mode(&tag, true);
            }
        }
        Some(endpos)
    }

    fn unescape_attrvalue(&self, value: &str) -> String {
        let r = res();
        let mut out = String::with_capacity(value.len());
        let mut last = 0;
        let mut pos = 0;
        while let Some(m) = r.attr_charref.find_from_pos(value, pos).ok().flatten() {
            out.push_str(&value[last..m.start()]);
            let reference = m.as_str();
            let replaced = if reference.starts_with("&#") {
                py_unescape_ref(reference)
            } else if !reference.ends_with('=') && html5_entities().contains_key(&reference[1..]) {
                py_unescape_ref(reference)
            } else {
                reference.to_string()
            };
            out.push_str(&replaced);
            last = m.end();
            pos = m.end();
            if pos >= value.len() {
                break;
            }
        }
        out.push_str(&value[last..]);
        out
    }

    fn parse_endtag(&mut self, rawdata: &str, i: usize) -> Option<usize> {
        let r = res();
        rawdata[i + 2..].find('>')?;
        if match_at(&r.endtagopen, rawdata, i).is_none() {
            if rawdata[i + 2..].starts_with('>') {
                return Some(i + 3);
            }
            return rawdata[i + 2..].find('>').map(|p| i + 2 + p + 1);
        }
        let (_, j) = match_at(&r.locatetagend, rawdata, i + 2)?;
        if !rawdata[..j].ends_with('>') {
            return None;
        }
        let caps = r.tagfind_tolerant.captures_from_pos(rawdata, i + 2).ok().flatten()?;
        let tag = caps.get(1)?.as_str().to_lowercase();
        self.handle_tag(&tag, None, false);
        self.clear_cdata_mode();
        Some(j)
    }

    // ----- entity handling ---------------------------------------------------

    fn handle_charref(&mut self, name: &str) {
        let value = if name.starts_with(['x', 'X']) {
            i64::from_str_radix(&name[1..].replace('_', ""), 16).ok().filter(|_| !name[1..].is_empty())
        } else {
            py_int(name)
        };
        let Some(value) = value else {
            self.error = Some(format!("invalid literal for int() with base 10: '{name}'"));
            return;
        };
        let mut c = if !(0 < value && value < 0x110000) || (0xD800..0xE000).contains(&value) { 0xFFFD } else { value as u32 };
        c = control_character_replacement(c);
        let text = match unifiable_n(c) {
            Some(rep) => rep.to_string(),
            None => char::from_u32(c).map(|ch| ch.to_string()).unwrap_or_else(|| "\u{fffd}".to_string()),
        };
        self.handle_data(&text, true);
    }

    fn handle_entityref(&mut self, name: &str) {
        let text = if let Some(rep) = unifiable(name) {
            rep.to_string()
        } else {
            match html5_entities().get(format!("{name};").as_str()) {
                Some(value) => value.to_string(),
                None => format!("&{name};"),
            }
        };
        if !text.is_empty() {
            self.handle_data(&text, true);
        }
    }

    // ----- output engine (o / pbr / p / soft_br) -----------------------------

    fn out(&mut self, s: &str) {
        if !s.is_empty() {
            self.last_was_nl = s.ends_with('\n');
        }
        self.outtextlist.push(s.to_string());
    }

    fn pbr(&mut self) {
        if self.p_p == 0 {
            self.p_p = 1;
        }
    }

    fn p(&mut self) {
        self.p_p = 2;
    }

    fn soft_br(&mut self) {
        self.pbr();
        self.br_toggle = "  ".to_string();
    }

    fn o(&mut self, data: &str, puredata: bool, force: Force) {
        if let Some(abbr) = &mut self.abbr_data {
            abbr.push_str(data);
        }
        if self.quiet != 0 {
            return;
        }
        let mut data = data.to_string();
        if puredata && !self.pre {
            data = collapse_whitespace(&data);
            if data.starts_with(' ') {
                self.space = true;
                data.remove(0);
            }
        }
        if data.is_empty() && matches!(force, Force::No) {
            return;
        }
        if self.startpre && !data.starts_with('\n') && !data.starts_with("\r\n") {
            data = format!("\n{data}");
        }
        let mut bq = ">".repeat(self.blockquote);
        let forced = !matches!(force, Force::No);
        if !(forced && !data.is_empty() && data.starts_with('>')) && self.blockquote > 0 {
            bq.push(' ');
        }
        if self.pre {
            if !self.list.is_empty() {
                bq.push_str(&self.list_code_indent);
            }
            bq.push_str("    ");
            data = data.replace('\n', &format!("\n{bq}"));
            self.pre_indent = bq.clone();
        }
        if self.startpre {
            self.startpre = false;
            if !self.list.is_empty() {
                let strip: Vec<char> = format!("\n{}", self.pre_indent).chars().collect();
                data = data.trim_start_matches(|c: char| strip.contains(&c)).to_string();
            }
        }
        if self.start {
            self.space = false;
            self.p_p = 0;
            self.start = false;
        }
        if matches!(force, Force::End) {
            self.p_p = 0;
            self.out("\n");
            self.space = false;
        }
        if self.p_p > 0 {
            let unit = format!("{}\n{bq}", self.br_toggle);
            let repeated = unit.repeat(self.p_p);
            self.out(&repeated);
            self.space = false;
            self.br_toggle.clear();
        }
        if self.space {
            if !self.last_was_nl {
                self.out(" ");
            }
            self.space = false;
        }
        if matches!(force, Force::End) && !self.abbr_list.is_empty() {
            let items = self.abbr_list.clone();
            for (abbr, definition) in items {
                self.out(&format!("  *[{abbr}]: {definition}\n"));
            }
        }
        self.p_p = 0;
        self.out(&data);
    }

    // ----- data ----------------------------------------------------------------

    fn handle_data(&mut self, data: &str, entity_char: bool) {
        if data.is_empty() {
            return;
        }
        let mut data = data.to_string();
        if self.stressed {
            data = data.trim_matches(|c: char| is_py_space(c)).to_string();
            self.stressed = false;
            self.preceding_stressed = true;
        } else if self.preceding_stressed {
            let first = data.chars().next().unwrap();
            let punct_or_space = matches!(first, ']' | '[' | '(' | ')' | '{' | '}' | '.' | '!' | '?') || is_py_space(first);
            if !punct_or_space && hn(&self.current_tag) == 0 && !matches!(self.current_tag.as_str(), "a" | "code" | "pre") {
                data = format!(" {data}");
            }
            self.preceding_stressed = false;
        }
        if let Some(href) = self.maybe_automatic_link.clone() {
            if href == data && res().absolute_url.is_match(&href).unwrap_or(false) {
                self.o(&format!("<{data}>"), false, Force::No);
                self.empty_link = false;
                return;
            }
            self.o("[", false, Force::No);
            self.maybe_automatic_link = None;
            self.empty_link = false;
        }
        if !self.code && !self.pre && !entity_char {
            data = escape_md_section(&data);
        }
        self.preceding_data = data.clone();
        self.o(&data, true, Force::No);
    }

    // ----- tags ------------------------------------------------------------------

    fn handle_tag(&mut self, tag: &str, attrs: Option<Attrs>, start: bool) {
        self.current_tag = tag.to_string();
        let mut attrs = attrs.unwrap_or_default();

        if start && self.maybe_automatic_link.is_some() && !matches!(tag, "p" | "div" | "style" | "dl" | "dt") && tag != "img" {
            self.o("[", false, Force::No);
            self.maybe_automatic_link = None;
            self.empty_link = false;
        }

        let level = hn(tag);
        if level > 0 {
            if !self.astack.is_empty() {
                if start {
                    self.inheader = true;
                    if self.outtextlist.last().map(|s| s == "[").unwrap_or(false) {
                        self.outtextlist.pop();
                        self.space = false;
                        self.o(&format!("{} ", "#".repeat(level)), false, Force::No);
                        self.o("[", false, Force::No);
                    }
                } else {
                    self.p_p = 0;
                    self.inheader = false;
                    return;
                }
            } else {
                self.p();
                if start {
                    self.inheader = true;
                    self.o(&format!("{} ", "#".repeat(level)), false, Force::No);
                } else {
                    self.inheader = false;
                    return;
                }
            }
        }

        if matches!(tag, "p" | "div") {
            if !self.astack.is_empty() || self.split_next_td {
                // pass
            } else {
                self.p();
            }
        }

        if tag == "br" && start {
            if self.blockquote > 0 {
                self.o("  \n> ", false, Force::No);
            } else {
                self.o("  \n", false, Force::No);
            }
        }

        if tag == "hr" && start {
            self.p();
            self.o("* * *", false, Force::No);
            self.p();
        }

        if matches!(tag, "head" | "style" | "script") {
            if start { self.quiet += 1; } else { self.quiet -= 1; }
        }

        if tag == "body" {
            self.quiet = 0;
        }

        if tag == "blockquote" {
            if start {
                self.p();
                self.o("> ", false, Force::Yes);
                self.start = true;
                self.blockquote += 1;
            } else {
                self.blockquote = self.blockquote.saturating_sub(1);
                self.p();
            }
        }

        if matches!(tag, "em" | "i" | "u") {
            let last = self.preceding_data.chars().last();
            let emphasis = if start && last.map_or(false, |c| !" \t\n\r\u{b}\u{c}".contains(c) && !c.is_ascii_punctuation()) {
                self.preceding_data.push(' ');
                " _"
            } else {
                "_"
            };
            self.o(emphasis, false, Force::No);
            if start { self.stressed = true; }
        }

        if matches!(tag, "strong" | "b") {
            let strong = if start && self.preceding_data.ends_with('*') {
                self.preceding_data.push(' ');
                " **"
            } else {
                "**"
            };
            self.o(strong, false, Force::No);
            if start { self.stressed = true; }
        }

        if matches!(tag, "del" | "strike" | "s") {
            let strike = if start && self.preceding_data.ends_with('~') {
                self.preceding_data.push(' ');
                " ~~"
            } else {
                "~~"
            };
            self.o(strike, false, Force::No);
            if start { self.stressed = true; }
        }

        if matches!(tag, "kbd" | "code" | "tt") && !self.pre {
            self.o("`", false, Force::No);
            self.code = !self.code;
        }

        if tag == "abbr" {
            if start {
                self.abbr_title = None;
                self.abbr_data = Some(String::new());
                if let Some(title) = attrs.get("title") {
                    self.abbr_title = title.clone();
                }
            } else {
                if let Some(title) = self.abbr_title.take() {
                    let data = self.abbr_data.clone().unwrap_or_default();
                    if let Some(entry) = self.abbr_list.iter_mut().find(|(k, _)| *k == data) {
                        entry.1 = title;
                    } else {
                        self.abbr_list.push((data, title));
                    }
                }
                self.abbr_data = None;
            }
        }

        if tag == "q" {
            self.o("\"", false, Force::No);
            self.quote = !self.quote;
        }

        if tag == "a" {
            if start {
                let href = attrs.get("href").cloned().flatten();
                match href {
                    Some(href) if !href.starts_with('#') => {
                        self.maybe_automatic_link = Some(href.clone());
                        self.empty_link = true;
                        if self.protect_links {
                            attrs.insert("href".to_string(), Some(format!("<{href}>")));
                        }
                        self.astack.push(Some(attrs.clone()));
                    }
                    _ => self.astack.push(None),
                }
            } else if let Some(a) = self.astack.pop() {
                if self.maybe_automatic_link.is_some() && !self.empty_link {
                    self.maybe_automatic_link = None;
                } else if let Some(a) = a {
                    if self.empty_link {
                        self.o("[", false, Force::No);
                        self.empty_link = false;
                        self.maybe_automatic_link = None;
                    }
                    self.p_p = 0;
                    let title = escape_md(a.get("title").cloned().flatten().unwrap_or_default().as_str());
                    let href = a.get("href").cloned().flatten().unwrap_or_default();
                    let title_part = if title.trim_matches(|c: char| is_py_space(c)).is_empty() {
                        String::new()
                    } else {
                        format!(" \"{title}\"")
                    };
                    self.o(&format!("]({}{title_part})", escape_md(&href)), false, Force::No);
                }
            }
        }

        if tag == "img" && start {
            if let Some(Some(src)) = attrs.get("src").cloned() {
                let alt = attrs.get("alt").cloned().flatten().unwrap_or_default();
                if self.maybe_automatic_link.is_some() {
                    self.o("[", false, Force::No);
                    self.maybe_automatic_link = None;
                    self.empty_link = false;
                }
                self.o(&format!("![{}]", escape_md(&alt)), false, Force::No);
                self.o(&format!("({})", escape_md(&src)), false, Force::No);
            }
        }

        if tag == "dl" && start { self.p(); }
        if tag == "dt" && !start { self.pbr(); }
        if tag == "dd" && start { self.o("    ", false, Force::No); }
        if tag == "dd" && !start { self.pbr(); }

        if matches!(tag, "ol" | "ul") {
            if self.list.is_empty() && !self.last_was_list {
                self.p();
            }
            if start {
                let numbering_start = match attrs.get("start") {
                    Some(None) => {
                        self.error = Some("AssertionError: <ol start> without a value".to_string());
                        0
                    }
                    Some(Some(value)) => py_int(value).map(|v| v - 1).unwrap_or(0),
                    None => 0,
                };
                self.list.push(ListElement { name: tag.to_string(), num: numbering_start });
            } else if self.list.pop().is_some() && self.list.is_empty() {
                self.o("\n", false, Force::No);
            }
            self.last_was_list = true;
        } else {
            self.last_was_list = false;
        }

        if tag == "li" {
            self.list_code_indent.clear();
            self.pbr();
            if start {
                let mut li = self.list.last().cloned().unwrap_or(ListElement { name: "ul".to_string(), num: 0 });
                let mut parent: Option<&str> = None;
                let mut indent = String::new();
                for element in &self.list {
                    indent.push_str(if parent == Some("ol") { "   " } else { "  " });
                    parent = Some(element.name.as_str());
                }
                self.list_code_indent = indent.clone();
                self.o(&indent, false, Force::No);
                if li.name == "ul" {
                    self.list_code_indent.push_str("  ");
                    self.o("* ", false, Force::No);
                } else if li.name == "ol" {
                    li.num += 1;
                    if let Some(top) = self.list.last_mut() {
                        top.num = li.num;
                    }
                    self.list_code_indent.push_str("   ");
                    self.o(&format!("{}. ", li.num), false, Force::No);
                }
                self.start = true;
            }
        }

        if matches!(tag, "table" | "tr" | "td" | "th") {
            if tag == "table" && start {
                self.table_start = true;
            }
            if matches!(tag, "td" | "th") && start {
                if self.split_next_td {
                    self.o("| ", false, Force::No);
                }
                self.split_next_td = true;
            }
            if tag == "tr" && start {
                self.td_count = 0;
            }
            if tag == "tr" && !start {
                self.split_next_td = false;
                self.soft_br();
            }
            if tag == "tr" && !start && self.table_start {
                let sep = vec!["---"; self.td_count].join("|");
                self.o(&sep, false, Force::No);
                self.soft_br();
                self.table_start = false;
            }
            if matches!(tag, "td" | "th") && start {
                self.td_count += 1;
            }
        }

        if tag == "pre" {
            if start {
                self.startpre = true;
                self.pre = true;
                self.pre_indent.clear();
            } else {
                self.pre = false;
            }
            self.p();
        }
    }
}

#[derive(Clone, Copy)]
enum Force {
    No,
    Yes,
    End,
}

/// `re.sub(r"\s+", " ", data)` with Python's whitespace set.
fn collapse_whitespace(data: &str) -> String {
    let mut out = String::with_capacity(data.len());
    let mut in_space = false;
    for c in data.chars() {
        if is_py_space(c) {
            if !in_space {
                out.push(' ');
                in_space = true;
            }
        } else {
            out.push(c);
            in_space = false;
        }
    }
    out
}

/// One-shot conversion like `textutils.html_tables_to_markdown` does (fresh
/// instance, `protect_links=True`) is not needed by the port; emails use a
/// shared instance through `Html2Text::handle`.
pub fn convert(html: &str) -> Result<String, String> {
    Html2Text::new(false).handle(html).map_err(|e| e.0)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn h(html: &str) -> String {
        Html2Text::new(false).handle(html).unwrap()
    }

    #[test]
    fn verified_outputs_from_spec() {
        assert_eq!(h("<p>a</p><p>b</p>"), "a\n\nb\n");
        assert_eq!(h("<div>a<div>b</div>c</div>"), "a\n\nb\n\nc\n");
        assert_eq!(h("<p>a</p><p></p><p></p><p>b</p>"), "a\n\nb\n");
        assert_eq!(h("<br><br><br>x"), "  \n  \n  \nx\n");
        assert_eq!(h("x<br><br><br>"), "x  \n  \n  \n\n");
        assert_eq!(h("<p>x</p><br><p>y</p>"), "x\n\n  \n\n\ny\n");
        assert_eq!(h("<h1>A</h1><h2>B</h2>text"), "# A\n\n## B\n\ntext\n");
        assert_eq!(h("a<hr>b"), "a\n\n* * *\n\nb\n");
        assert_eq!(h("foo<i>bar</i>baz"), "foo _bar_ baz\n");
        assert_eq!(h("foo.<i>bar</i>"), "foo._bar_\n");
        assert_eq!(h("<i>x</i>, y; <b>z</b>: w <b>s</b>(t) <b>u</b>!"), "_x_ , y; **z** : w **s**(t) **u**!\n");
        assert_eq!(h("x<b> bold </b>y"), "x**bold** y\n");
        assert_eq!(h("<b>&amp;</b>x"), "**&** x\n");
        assert_eq!(h("<ul><li>a<ul><li>b</li></ul></li><li>c</li></ul>"), "  * a\n    * b\n  * c\n\n\n");
        assert_eq!(h("<ol start=\"5\"><li>a</li><li>b</li></ol>"), "  5. a\n  6. b\n\n\n");
        assert_eq!(h("<ul><li>a</li></ul><p>c</p>"), "  * a\n\n\n\nc\n");
        assert_eq!(h("<blockquote><p>a</p><p>b</p></blockquote>after"), "> a\n> \n> b\n\nafter\n");
        assert_eq!(h("<blockquote>a<br>b</blockquote>"), "> a  \n> b\n");
        assert_eq!(h("<pre>line1\nline2</pre>"), "\n    line1\n    line2\n");
        assert_eq!(h("<ul><li>item<pre>code\nmore</pre></li></ul>"), "  * item\n        \n        code\n        more\n\n\n\n");
        assert_eq!(h("<dl><dt>Term</dt><dd>Def</dd></dl>after"), "Term\n    Def\nafter\n");
        assert_eq!(h("x &#10; y"), "x  y\n");
        assert_eq!(h("+ plus\n- dash\n-- emdash"), "\\+ plus \\- dash \\-- emdash\n");
        assert_eq!(h("back\\slash \\*"), "back\\slash \\\\*\n");
        assert_eq!(h("<html><head><title>T</title></head><body><p>x</p></body></html>"), "x\n");
        assert_eq!(h("<title>T &amp; U</title><p>x</p>"), "T & U\n\nx\n");
        assert_eq!(h("<!--[if mso]><p>m</p><![endif]-->x<![if !mso]>y<![endif]>z"), "xyz\n");
        assert_eq!(h("<p class=MsoNormal>a<o:p></o:p></p><p class=MsoNormal>b<o:p>&nbsp;</o:p></p>"), "a\n\nb \n");
        assert_eq!(h("</head>hidden"), "");
        assert_eq!(h("<a href=\"u\">text</a>"), "[text](u)\n");
        assert_eq!(h("<a href=\"http://x.com/a\">http://x.com/a</a>"), "<http://x.com/a>\n");
        assert_eq!(h("<a href=\"mailto:a@b.com\">a@b.com</a>"), "[a@b.com](mailto:a@b.com)\n");
        assert_eq!(h("<img src=\"i.png\" alt=\"A\">"), "![A](i.png)\n");
        assert_eq!(h("<table><tr><td>A</td><td>B</td></tr><tr><td>1</td><td>2</td></tr></table>"), "A| B  \n---|---  \n1| 2\n");
        assert_eq!(h("AT&T rocks"), "AT&T; rocks\n");
        assert_eq!(h("a &amp; b &mdash; c&nbsp;&nbsp;d"), "a & b -- c  d\n");
        assert_eq!(h("&#8217;&#x92;&#233;"), "''e\n");
        assert_eq!(h(""), "\n");
    }

    #[test]
    fn python_errors_become_errors() {
        assert!(Html2Text::new(false).handle("&#65abc;").is_err());
        assert!(Html2Text::new(false).handle("<ol start><li>a</li></ol>").is_err());
    }
}
