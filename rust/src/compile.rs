//! Orchestration: `DocumentCompiler.compile()`.
use std::collections::HashMap;
use std::io::{BufWriter, Write};
use std::path::{Path, PathBuf};
use std::time::Instant;

use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::mpsc;

use crate::convert::{is_fenced, language_of, process_file, Context, Converted};
use crate::output;
use crate::scan::{relpath, Scanner};
use crate::textutils::{estimate_tokens, py_len, thousands};
use crate::EngineError;

#[derive(Debug)]
pub enum CompileError {
    Engine(EngineError),
    Io(String),
}

impl From<EngineError> for CompileError {
    fn from(error: EngineError) -> Self {
        CompileError::Engine(error)
    }
}

pub struct Compiler {
    pub scanner: Scanner,
    pub ctx: Context,
    pub output_file: PathBuf,
    pub force_format: Option<String>,
    pub version: String,
}

struct Stat {
    path: String,
    chars: usize,
    tokens: usize,
    method: String,
}

impl Compiler {
    pub fn new(
        source: &Path,
        output_file: &Path,
        recursive: bool,
        include_extensions: Option<Vec<String>>,
        exclude_patterns: &[String],
        force_format: Option<String>,
        converter_config: HashMap<String, Vec<String>>,
        office_require_text_only: bool,
        jobs: usize,
    ) -> Self {
        let scanner = Scanner::new(source, recursive, include_extensions, exclude_patterns);
        let ctx = Context {
            include_extensions: scanner.include_extensions.clone(),
            office_require_text_only,
            converter_config,
            jobs,
            ocr_workers: jobs,
        };
        Compiler {
            scanner,
            ctx,
            output_file: output_file.to_path_buf(),
            force_format,
            version: crate::VERSION.to_string(),
        }
    }

    fn detect_processing_mode(&self, files: &[PathBuf]) -> &'static str {
        if self.force_format.is_some() {
            return "standard";
        }
        if files.len() == 1 && files[0].to_string_lossy().to_lowercase().ends_with(".eml") {
            return "single_email";
        }
        "standard"
    }

    fn check_security(&self, files: &[PathBuf]) -> Vec<PathBuf> {
        let re = fancy_regex::Regex::new(r"(exec|eval|system|subprocess|os\.)").unwrap();
        let mut suspicious = Vec::new();
        for file in files {
            let ext = crate::textutils::lower_extension(file);
            if !crate::config::SUSPICIOUS_EXTENSIONS.contains(&ext.as_str()) {
                continue;
            }
            let size = std::fs::metadata(file).map(|m| m.len()).unwrap_or(0);
            if size > 1024 * 1024 {
                suspicious.push(file.clone());
                continue;
            }
            if let Ok(bytes) = std::fs::read(file) {
                let text = String::from_utf8_lossy(&bytes);
                let head: String = text.chars().take(4096).collect();
                if re.is_match(&head).unwrap_or(false) {
                    suspicious.push(file.clone());
                }
            }
        }
        suspicious
    }

    fn discard_output(&self) {
        let _ = std::fs::remove_file(&self.output_file);
    }

    pub fn compile(&self) -> Result<bool, CompileError> {
        let started = Instant::now();
        println!("📦 DocuMix v{}", self.version);

        let (files, structure) = self.scanner.scan().map_err(|e| CompileError::Io(e.to_string()))?;
        if files.is_empty() {
            println!("❌ No files found to process.");
            return Ok(false);
        }
        // One or two documents: an OCR worker process costs more than it saves.
        let ocr_workers = if files.len() <= 2 || self.ctx.jobs <= 1 { 0 } else { self.ctx.jobs };
        let ctx = Context {
            include_extensions: self.ctx.include_extensions.clone(),
            office_require_text_only: self.ctx.office_require_text_only,
            converter_config: self.ctx.converter_config.clone(),
            jobs: self.ctx.jobs,
            ocr_workers,
        };
        let mode = self.detect_processing_mode(&files);
        println!("📋 Processing mode: {mode}");
        println!("🔎 Checking files for security issues...");
        let suspicious = self.check_security(&files);
        println!("📊 Collecting file statistics...");

        let file = std::fs::File::create(&self.output_file).map_err(|e| CompileError::Io(e.to_string()))?;
        let mut out = BufWriter::new(file);
        let result = if mode == "single_email" {
            self.compile_single_email(&ctx, &mut out, &files[0], started)
        } else {
            self.compile_standard(&ctx, &mut out, &files, &structure, &suspicious, started)
        };
        crate::engines::liteparse::shutdown();
        match result {
            Ok(ok) => {
                out.flush().map_err(|e| CompileError::Io(e.to_string()))?;
                Ok(ok)
            }
            Err(CompileError::Engine(error)) => {
                drop(out);
                self.discard_output();
                Err(CompileError::Engine(error))
            }
            Err(other) => Err(other),
        }
    }

    fn compile_single_email<W: Write>(&self, ctx: &Context, out: &mut W, path: &Path, started: Instant) -> Result<bool, CompileError> {
        let (content, _method, info) = crate::email::process_email(ctx, path)?;
        let info = info.unwrap_or(output::EmailInfo {
            subject: String::new(), from: String::new(), to: String::new(), cc: String::new(), date: String::new(),
            auth_results: String::new(), dkim_signature: String::new(), attachments_source: String::new(),
            size: 0, attachments: Vec::new(),
        });
        let empty_info = info.subject.is_empty() && info.from.is_empty() && info.to.is_empty() && info.size == 0 && info.attachments.is_empty();
        let info = if empty_info {
            // Python passes `{}` on parse failure: defaults 'No Subject' / 'Unknown'.
            output::EmailInfo { subject: "No Subject".into(), from: "Unknown".into(), to: "Unknown".into(), date: "Unknown".into(), ..info }
        } else {
            info
        };
        output::write_single_email(out, &self.version, &info, &content).map_err(|e| CompileError::Io(e.to_string()))?;
        let total_chars = py_len(&content);
        let total_tokens = estimate_tokens(&content);
        println!("\n✔ Email processing completed successfully!");
        println!("\n📊 Processing Summary:");
        println!("─────────────────────");
        println!("  Email Subject: {}", info.subject);
        println!("  Attachments: {} files", info.attachments.len());
        println!("  Total Chars: {} chars", thousands(total_chars));
        println!("  Total Tokens: {} tokens", thousands(total_tokens));
        println!("  Output: {}", self.output_file.display());
        println!("  Time: {:.2} seconds", started.elapsed().as_secs_f64());
        Ok(true)
    }

    fn convert_one(&self, ctx: &Context, path: &Path) -> Result<Converted, EngineError> {
        println!("⚙️  Processing: {}", relpath(path, &self.scanner.source_dir));
        process_file(ctx, path)
    }

    fn compile_standard<W: Write>(&self, ctx: &Context, out: &mut W, files: &[PathBuf], structure: &[String], suspicious: &[PathBuf], started: Instant) -> Result<bool, CompileError> {
        let source_dir = self.scanner.source_dir.to_string_lossy().into_owned();
        output::write_standard_preamble(out, &source_dir, files.len(), structure).map_err(|e| CompileError::Io(e.to_string()))?;

        let is_email = |p: &Path| p.to_string_lossy().to_lowercase().ends_with(".eml");
        let workers = ctx.jobs.min(files.len()).max(1);
        let mut stats: Vec<Stat> = Vec::with_capacity(files.len());
        let mut total_chars = 0;
        let mut total_tokens = 0;
        let mut record = |out: &mut W, file: &Path, content: String, method: String| -> Result<(), CompileError> {
            let rel = relpath(file, &self.scanner.source_dir);
            let chars = py_len(&content);
            let tokens = estimate_tokens(&content);
            total_chars += chars;
            total_tokens += tokens;
            stats.push(Stat { path: rel.clone(), chars, tokens, method: method.clone() });
            output::write_file_entry(out, &rel, &method, &content, language_of(file), is_fenced(&method))
                .map_err(|e| CompileError::Io(e.to_string()))
        };

        if workers <= 1 {
            for file in files {
                let (content, method) = self.convert_one(ctx, file)?;
                record(out, file, content, method)?;
            }
        } else {
            // Worker threads pull files from a shared index (like Python's
            // ThreadPoolExecutor; a rayon par_iter would nest with the pool
            // pdf-inspector uses inside anydoc). Finished results are handed
            // to the main thread, which writes them strictly in file order
            // while conversions continue. Emails run on the main thread when
            // their turn comes (siblings share an attachments/ folder).
            let next = AtomicUsize::new(0);
            let (tx, rx) = mpsc::channel::<(usize, Result<Converted, EngineError>)>();
            let outcome: Result<(), CompileError> = std::thread::scope(|scope| {
                for _ in 0..workers {
                    let tx = tx.clone();
                    let next = &next;
                    scope.spawn(move || loop {
                        let index = next.fetch_add(1, Ordering::SeqCst);
                        if index >= files.len() {
                            break;
                        }
                        let file = &files[index];
                        if is_email(file) {
                            continue;
                        }
                        let result = self.convert_one(ctx, file);
                        let failed = result.is_err();
                        if tx.send((index, result)).is_err() || failed {
                            break;
                        }
                    });
                }
                drop(tx);
                let mut pending: std::collections::HashMap<usize, Converted> = std::collections::HashMap::new();
                let mut cursor = 0usize;
                let mut flush = |out: &mut W, cursor: &mut usize, pending: &mut std::collections::HashMap<usize, Converted>| -> Result<(), CompileError> {
                    loop {
                        if *cursor >= files.len() {
                            return Ok(());
                        }
                        let file = &files[*cursor];
                        if is_email(file) {
                            // Main thread converts emails once everything before them is written.
                            let (content, method) = self.convert_one(ctx, file)?;
                            record(out, file, content, method)?;
                            *cursor += 1;
                            continue;
                        }
                        match pending.remove(cursor) {
                            Some((content, method)) => {
                                record(out, file, content, method)?;
                                *cursor += 1;
                            }
                            None => return Ok(()),
                        }
                    }
                };
                for (index, result) in rx {
                    match result {
                        Ok(converted) => {
                            pending.insert(index, converted);
                            if index == cursor {
                                flush(out, &mut cursor, &mut pending)?;
                            }
                        }
                        Err(error) => {
                            next.store(files.len(), Ordering::SeqCst);
                            return Err(CompileError::Engine(error));
                        }
                    }
                }
                flush(out, &mut cursor, &mut pending)?;
                if cursor < files.len() {
                    return Err(CompileError::Io("conversion results missing".to_string()));
                }
                Ok(())
            });
            outcome?;
        }

        stats.sort_by(|a, b| b.chars.cmp(&a.chars));

        println!("\n✔ Packing completed successfully!");
        println!("\n📈 Top 5 Files by Character Count and Token Count:");
        println!("──────────────────────────────────────────────────");
        for (i, stat) in stats.iter().take(5).enumerate() {
            println!("{}. {} ({} chars, {} tokens, via {})", i + 1, stat.path, thousands(stat.chars), thousands(stat.tokens), stat.method);
        }
        println!("\n🔎 Security Check:");
        println!("─────────────────────");
        if !suspicious.is_empty() {
            println!("❌ Suspicious files detected:");
            for file in suspicious {
                println!("  - {}", relpath(file, &self.scanner.source_dir));
            }
        } else {
            println!("✔ No suspicious files detected.");
        }
        println!("\n📊 Pack Summary:");
        println!("─────────────────────");
        println!("  Total Files: {} files", thousands(files.len()));
        println!("  Total Chars: {} chars", thousands(total_chars));
        println!(" Total Tokens: {} tokens", thousands(total_tokens));
        println!("       Output: {}", self.output_file.display());
        println!("     Security: {}", if suspicious.is_empty() { "✔ No suspicious files detected" } else { "❌ Suspicious files detected" });
        println!("        Time: {:.2} seconds", started.elapsed().as_secs_f64());
        println!("        Jobs: {}", self.ctx.jobs);
        println!("\n🎉 All Done! Your documents have been successfully packed.");
        Ok(true)
    }
}
