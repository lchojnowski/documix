//! CLI mirroring `documix/cli.py`: same flags, validation order and exit codes.
use std::collections::HashMap;
use std::path::Path;

use clap::Parser;

use crate::compile::{CompileError, Compiler};
use crate::config::{converter_choices, converter_defaults, ENGINE_CONVERTERS, FORMATS};

const LOGO: &str = "
 ██████╗  ██████╗  ██████╗██╗   ██╗███╗   ███╗██╗██╗  ██╗
 ██╔══██╗██╔═══██╗██╔════╝██║   ██║████╗ ████║██║╚██╗██╔╝
 ██║  ██║██║   ██║██║     ██║   ██║██╔████╔██║██║ ╚███╔╝ 
 ██║  ██║██║   ██║██║     ██║   ██║██║╚██╔╝██║██║ ██╔██╗ 
 ██████╔╝╚██████╔╝╚██████╗╚██████╔╝██║ ╚═╝ ██║██║██╔╝ ██╗
 ╚═════╝  ╚═════╝  ╚═════╝ ╚═════╝ ╚═╝     ╚═╝╚═╝╚═╝  ╚═╝
                                                         
    ";

#[derive(Parser, Debug)]
#[command(
    name = "documix",
    disable_version_flag = true,
    about = "Compiles documents from a folder into a single Markdown file, similar to Repomix. Documents are converted with anydoc first and LiteParse second (local OCR for scanned PDFs); PDF, Word, PowerPoint, Excel, OpenDocument, RTF, EPUB, ZIP archives and email files (.eml) with attachments are supported. The legacy converters (MinerU, PaddleOCR, pdfplumber, pandoc, LibreOffice, Tesseract profile, MarkItDown sandbox) and the benchmark subcommand live in the Python implementation: documix-py (python/).",
    after_help = "Email Mode: When processing .eml files, DocuMix will automatically detect and process attachments from an \"attachments\" subfolder if present, or extract them from the email itself."
)]
pub struct Args {
    /// Path to the folder with documents or a single .eml file
    pub folder: Option<String>,
    /// Path to the output file (default: documix-output.md)
    #[arg(short = 'o', long, default_value = "documix-output.md")]
    pub output: String,
    /// Search folders recursively
    #[arg(short = 'r', long)]
    pub recursive: bool,
    /// List of file extensions to process (comma-separated, default includes common document formats and .eml)
    #[arg(short = 'e', long)]
    pub extensions: Option<String>,
    /// File exclusion patterns (regular expressions, comma-separated)
    #[arg(short = 'x', long)]
    pub exclude: Option<String>,
    /// Number of files converted concurrently (default: one per CPU core, bounded by installed memory at about 1.5 GB per job; DOCUMIX_JOBS overrides it; 1 disables parallelism). The output order is always deterministic.
    #[arg(short = 'j', long, allow_hyphen_values = true)]
    pub jobs: Option<i64>,
    /// Display program version
    #[arg(short = 'v', long)]
    pub version: bool,
    /// Force standard format even for emails
    #[arg(long)]
    pub standard_format: bool,
    /// PDF converters to try, in order (comma-separated). Default: anydoc,liteparse.
    #[arg(long)]
    pub pdf_converters: Option<String>,
    /// DOCX/DOCM converters to try, in order (comma-separated). Default: anydoc,liteparse.
    #[arg(long)]
    pub docx_converters: Option<String>,
    /// legacy DOC converters to try, in order (comma-separated). Default: anydoc,liteparse.
    #[arg(long)]
    pub doc_converters: Option<String>,
    /// RTF converters to try, in order (comma-separated). Default: anydoc,liteparse.
    #[arg(long)]
    pub rtf_converters: Option<String>,
    /// EPUB converters to try, in order (comma-separated). Default: anydoc.
    #[arg(long)]
    pub epub_converters: Option<String>,
    /// XLSX/PPTX/ODT and other Office converters to try, in order (comma-separated). Default: anydoc,liteparse.
    #[arg(long)]
    pub office_converters: Option<String>,
    /// Installed Tesseract language codes joined by + (default: eng).
    #[arg(long)]
    pub ocr_languages: Option<String>,
    /// Maximum pages for Tesseract OCR (default: 20; hard maximum: 100).
    #[arg(long)]
    pub ocr_max_pages: Option<i64>,
    /// Tesseract rendering DPI (default: 150; hard maximum: 200).
    #[arg(long)]
    pub ocr_dpi: Option<i64>,
    /// Whole-document Tesseract budget in seconds (default: 180; maximum: 300).
    #[arg(long)]
    pub ocr_timeout: Option<i64>,
    /// Fail XLSX/PPTX conversion when embedded or linked images have not been assessed; opt-in, independent of PDF OCR.
    #[arg(long)]
    pub office_require_text_only: bool,
}

pub fn print_logo() {
    println!("{LOGO}");
}

pub fn print_converter_info(config: &HashMap<String, Vec<String>>) {
    println!("Converter Configuration:");
    println!("{}", "-".repeat(40));
    for fmt in FORMATS {
        let configured: Vec<String> = match config.get(*fmt) {
            Some(list) => list.clone(),
            None => converter_defaults(fmt).iter().map(|s| s.to_string()).collect(),
        };
        let active: Vec<&String> = configured.iter().filter(|c| ENGINE_CONVERTERS.contains(&c.as_str())).collect();
        let missing: Vec<&String> = configured.iter().filter(|c| !ENGINE_CONVERTERS.contains(&c.as_str())).collect();
        let shown = if active.is_empty() {
            "(none available)".to_string()
        } else {
            active.iter().map(|s| s.as_str()).collect::<Vec<_>>().join(", ")
        };
        println!("  {:>6}: {shown}", fmt.to_uppercase());
        if !missing.is_empty() {
            println!("          missing: {}", missing.iter().map(|s| s.as_str()).collect::<Vec<_>>().join(", "));
        }
    }
    println!();
}

fn usage_error(message: &str) -> ! {
    eprintln!("usage: documix [-h] [-o OUTPUT] [-r] [-e EXTENSIONS] [-x EXCLUDE] [-j JOBS] [-v] [--standard-format] [--pdf-converters PDF_CONVERTERS] [--docx-converters DOCX_CONVERTERS] [--doc-converters DOC_CONVERTERS] [--rtf-converters RTF_CONVERTERS] [--epub-converters EPUB_CONVERTERS] [--office-converters OFFICE_CONVERTERS] [--ocr-languages OCR_LANGUAGES] [--ocr-max-pages OCR_MAX_PAGES] [--ocr-dpi OCR_DPI] [--ocr-timeout OCR_TIMEOUT] [--office-require-text-only] [folder]");
    eprintln!("documix: error: {message}");
    std::process::exit(2);
}

fn fallback_error(message: &str) -> ! {
    eprintln!("documix: error: {message}");
    std::process::exit(3);
}

fn fail(message: &str, output: Option<&str>) -> ! {
    println!("\n❌ ERROR: anydoc engine failure: {message}");
    println!("DocuMix requires a working anydoc installation; nothing was written.");
    if let Some(output) = output {
        let _ = std::fs::remove_file(output);
    }
    std::process::exit(1);
}

pub fn main() {
    // Tesseract (LiteParse OCR) parallelises inside each page with OpenMP;
    // with one document per thread that oversubscribes the cores, so cap it
    // to one OpenMP thread per job unless the user chose otherwise.
    if std::env::var_os("OMP_NUM_THREADS").is_none() {
        // SAFETY: called before any thread is spawned.
        unsafe { std::env::set_var("OMP_NUM_THREADS", "1") };
    }
    let argv: Vec<String> = std::env::args().collect();
    if argv.len() > 1 && argv[1] == crate::engines::liteparse::WORKER_FLAG {
        crate::engines::liteparse::worker_main();
    }
    if argv.len() > 1 && argv[1] == "benchmark" {
        fallback_error("the benchmark subcommand is not available in this build; use the Python implementation: documix-py benchmark");
    }

    print_logo();
    let args = Args::parse();

    if args.version {
        println!("DocuMix v{}", crate::VERSION);
        println!();
        print_converter_info(&HashMap::new());
        return;
    }
    let Some(folder) = args.folder.clone() else {
        use clap::CommandFactory;
        let _ = Args::command().print_help();
        println!();
        return;
    };

    println!("🔍 Analyzing folder: {folder}");

    let mut include_extensions: Option<Vec<String>> = None;
    if let Some(value) = args.extensions.as_deref().filter(|v| !v.is_empty()) {
        let list: Vec<String> = value.split(',').map(|e| format!(".{}", e.trim().to_lowercase())).collect();
        println!("📋 Included extensions: {}", list.join(", "));
        include_extensions = Some(list);
    }
    let mut exclude_patterns: Vec<String> = Vec::new();
    if let Some(value) = args.exclude.as_deref().filter(|v| !v.is_empty()) {
        exclude_patterns = value.split(',').map(|p| p.trim().to_string()).collect();
        println!("🚫 Exclusion patterns: {}", exclude_patterns.join(", "));
    }
    let mut force_format = None;
    if args.standard_format {
        force_format = Some("standard".to_string());
        println!("📄 Forcing standard output format");
    }
    if let Some(jobs) = args.jobs {
        if jobs < 1 {
            usage_error("--jobs must be at least 1");
        }
    }

    let mut converter_config: HashMap<String, Vec<String>> = HashMap::new();
    let flags = [
        ("pdf", &args.pdf_converters), ("docx", &args.docx_converters), ("doc", &args.doc_converters),
        ("rtf", &args.rtf_converters), ("epub", &args.epub_converters), ("office", &args.office_converters),
    ];
    let mut rejected: Option<String> = None;
    for (fmt, value) in flags {
        let Some(value) = value.as_deref().filter(|v| !v.is_empty()) else { continue };
        let names: Vec<String> = value.split(',').map(|n| n.trim().to_string()).collect();
        let valid = converter_choices(fmt);
        for name in &names {
            if !valid.contains(&name.as_str()) {
                println!("Error: unknown {} converter '{name}'. Valid choices: {}", fmt.to_uppercase(), valid.join(", "));
                std::process::exit(1);
            }
        }
        println!("🔧 {} converters: {}", fmt.to_uppercase(), names.join(", "));
        if rejected.is_none() {
            rejected = names.iter().find(|n| !ENGINE_CONVERTERS.contains(&n.as_str())).cloned();
        }
        converter_config.insert(fmt.to_string(), names);
    }

    let ocr_given = args.ocr_languages.is_some() || args.ocr_max_pages.is_some() || args.ocr_dpi.is_some() || args.ocr_timeout.is_some();
    let tesseract_selected = converter_config.get("pdf").map_or(false, |l| l.iter().any(|n| n == "tesseract"));
    if let Some(name) = rejected {
        fallback_error(&format!("converter '{name}' is not available in this build (supported: anydoc, liteparse); use the Python implementation: documix-py"));
    }
    if ocr_given && !tesseract_selected {
        usage_error("OCR settings require --pdf-converters including tesseract");
    }

    print_converter_info(&converter_config);

    let jobs = args.jobs.map(|j| j as usize).unwrap_or_else(crate::jobs::default_jobs);
    let compiler = Compiler::new(
        Path::new(&folder),
        Path::new(&args.output),
        args.recursive,
        include_extensions,
        &exclude_patterns,
        force_format,
        converter_config,
        args.office_require_text_only,
        jobs,
    );
    match compiler.compile() {
        Ok(_) => {}
        Err(CompileError::Engine(error)) => fail(&error.0, Some(&args.output)),
        Err(CompileError::Io(message)) => {
            eprintln!("documix: error: {message}");
            std::process::exit(1);
        }
    }
}
