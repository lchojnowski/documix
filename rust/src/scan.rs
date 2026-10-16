//! File discovery with the exact semantics of `DocumentCompiler._scan()`.
use std::path::{Component, Path, PathBuf};

use crate::textutils::{extension_of, lower_extension};

pub struct Scanner {
    pub source_path: PathBuf,
    pub is_single_file: bool,
    pub source_dir: PathBuf,
    pub recursive: bool,
    pub include_extensions: Vec<String>,
    pub exclude_patterns: Vec<fancy_regex::Regex>,
}

/// `os.path.abspath`: join with the cwd and normalise lexically (`.` and
/// `..` collapsed, duplicate separators removed) without touching symlinks.
pub fn abspath(path: &Path) -> PathBuf {
    let joined = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir().unwrap_or_else(|_| PathBuf::from("/")).join(path)
    };
    let mut parts: Vec<std::ffi::OsString> = Vec::new();
    for component in joined.components() {
        match component {
            Component::RootDir | Component::Prefix(_) => {}
            Component::CurDir => {}
            Component::ParentDir => {
                parts.pop();
            }
            Component::Normal(part) => parts.push(part.to_os_string()),
        }
    }
    let mut out = PathBuf::from("/");
    for part in parts {
        out.push(part);
    }
    out
}

/// `os.path.relpath(path, start)` for a path below `start`.
pub fn relpath(path: &Path, start: &Path) -> String {
    match path.strip_prefix(start) {
        Ok(rel) if rel.as_os_str().is_empty() => ".".to_string(),
        Ok(rel) => rel.to_string_lossy().into_owned(),
        Err(_) => {
            // Fall back to a `..`-based relative path like Python does.
            let base: Vec<_> = start.components().collect();
            let target: Vec<_> = path.components().collect();
            let common = base.iter().zip(target.iter()).take_while(|(a, b)| a == b).count();
            let mut rel = PathBuf::new();
            for _ in common..base.len() {
                rel.push("..");
            }
            for component in &target[common..] {
                rel.push(component.as_os_str());
            }
            rel.to_string_lossy().into_owned()
        }
    }
}

impl Scanner {
    pub fn new(
        source: &Path,
        recursive: bool,
        include_extensions: Option<Vec<String>>,
        exclude_patterns: &[String],
    ) -> Self {
        let source_path = abspath(source);
        let is_single_file = source_path.is_file();
        let source_dir = if is_single_file {
            source_path.parent().map(Path::to_path_buf).unwrap_or_else(|| PathBuf::from("/"))
        } else {
            source_path.clone()
        };
        let include_extensions = include_extensions
            .unwrap_or_else(|| crate::config::DEFAULT_EXTENSIONS.iter().map(|s| s.to_string()).collect())
            .into_iter()
            .map(|e| e.to_lowercase())
            .collect();
        let mut compiled = Vec::new();
        for pattern in exclude_patterns {
            match fancy_regex::Regex::new(pattern) {
                Ok(re) => compiled.push(re),
                Err(_) => println!("WARNING: Invalid exclusion pattern: {pattern}"),
            }
        }
        Scanner { source_path, is_single_file, source_dir, recursive, include_extensions, exclude_patterns: compiled }
    }

    /// `_matches(filename)`: extension in the include list (case-insensitive)
    /// and no exclusion pattern found anywhere in the name (`re.search`).
    pub fn matches(&self, name: &str) -> bool {
        let lower = name.to_lowercase();
        let ext = extension_of(&lower);
        if !self.include_extensions.iter().any(|e| e == ext) {
            return false;
        }
        !self.exclude_patterns.iter().any(|re| re.is_match(name).unwrap_or(false))
    }

    /// Returns `(files_to_process, directory_structure)`.
    pub fn scan(&self) -> std::io::Result<(Vec<PathBuf>, Vec<String>)> {
        let mut files = Vec::new();
        let mut structure = Vec::new();
        if self.is_single_file {
            let name = self.source_path.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
            if self.matches(&name) {
                files.push(self.source_path.clone());
            }
        }
        if self.recursive {
            self.walk(&self.source_dir, &mut files, &mut structure)?;
        } else {
            let mut names: Vec<String> = std::fs::read_dir(&self.source_dir)?
                .filter_map(|e| e.ok())
                .map(|e| e.file_name().to_string_lossy().into_owned())
                .collect();
            names.sort();
            for name in names {
                let path = self.source_dir.join(&name);
                if !path.is_file() || !self.matches(&name) {
                    continue;
                }
                if !self.is_single_file {
                    files.push(path);
                }
                structure.push(format!("  {name}"));
            }
        }
        files.sort();
        Ok((files, structure))
    }

    /// `os.walk` top-down with sorted directory names; hidden directories are
    /// listed in the file set but left out of the printed tree.
    fn walk(&self, root: &Path, files: &mut Vec<PathBuf>, structure: &mut Vec<String>) -> std::io::Result<()> {
        let mut dirs: Vec<String> = Vec::new();
        let mut names: Vec<String> = Vec::new();
        // `os.walk(onerror=None)` silently skips directories it cannot read.
        let Ok(entries) = std::fs::read_dir(root) else { return Ok(()) };
        for entry in entries {
            let Ok(entry) = entry else { continue };
            let name = entry.file_name().to_string_lossy().into_owned();
            // `os.walk` classifies through `DirEntry.is_dir()`, which follows
            // symlinks, but never descends into symlinked directories.
            if entry.path().is_dir() {
                dirs.push(name);
            } else {
                names.push(name);
            }
        }
        dirs.sort();
        names.sort();

        let rel_root = relpath(root, &self.source_dir);
        let hidden = rel_root != "."
            && rel_root.split(std::path::MAIN_SEPARATOR).any(|part| part.starts_with('.'));
        if !hidden && rel_root != "." {
            structure.push(format!("{rel_root}/"));
        }
        for name in names {
            if !self.matches(&name) {
                continue;
            }
            let path = root.join(&name);
            if !self.is_single_file {
                files.push(path.clone());
            }
            if !hidden {
                structure.push(format!("  {}", relpath(&path, &self.source_dir)));
            }
        }
        for dir in dirs {
            let path = root.join(&dir);
            if std::fs::symlink_metadata(&path).map(|m| m.file_type().is_symlink()).unwrap_or(false) {
                continue;
            }
            self.walk(&path, files, structure)?;
        }
        Ok(())
    }
}

/// `lower_extension` re-exported for callers that only have a path.
pub fn ext_of(path: &Path) -> String {
    lower_extension(path)
}
