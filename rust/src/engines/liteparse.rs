//! Secondary engine (`converters/liteparse.py`): local OCR fallback, never fatal.
use std::path::Path;
use std::sync::{Condvar, Mutex, OnceLock};
use std::time::Duration;

use crate::engines::Outcome;
use crate::textutils::{has_content, label_of, lower_extension};

pub const PARSE_TIMEOUT: Duration = Duration::from_secs(300);
/// Concurrent OCR parses beyond this do not finish sooner (PDFium rendering is
/// serialised behind a global lock) but each one costs ~80 MB, so cap them.
pub const MAX_CONCURRENT_OCR: usize = 8;

static RUNTIME: OnceLock<tokio::runtime::Runtime> = OnceLock::new();
static PARSER: OnceLock<liteparse::LiteParse> = OnceLock::new();
/// LibreOffice conversions (every non-PDF input) must not overlap.
static OFFICE_LOCK: Mutex<()> = Mutex::new(());
static GATE: OnceLock<Gate> = OnceLock::new();

/// Counting semaphore bounding concurrent parses.
struct Gate {
    max: usize,
    active: Mutex<usize>,
    released: Condvar,
}

struct Permit<'a>(&'a Gate);

impl Gate {
    fn acquire(&self) -> Permit<'_> {
        let mut active = self.active.lock().unwrap_or_else(|p| p.into_inner());
        while *active >= self.max {
            active = self.released.wait(active).unwrap_or_else(|p| p.into_inner());
        }
        *active += 1;
        Permit(self)
    }
}

impl Drop for Permit<'_> {
    fn drop(&mut self) {
        let mut active = self.0.active.lock().unwrap_or_else(|p| p.into_inner());
        *active -= 1;
        self.0.released.notify_one();
    }
}

fn runtime() -> &'static tokio::runtime::Runtime {
    RUNTIME.get_or_init(|| {
        tokio::runtime::Builder::new_multi_thread()
            .enable_all()
            .thread_name("liteparse")
            .build()
            .expect("tokio runtime")
    })
}

fn parser() -> &'static liteparse::LiteParse {
    PARSER.get_or_init(|| {
        let config = liteparse::config::LiteParseConfig {
            output_format: liteparse::config::OutputFormat::Markdown,
            image_mode: liteparse::config::ImageMode::Off,
            quiet: true,
            ..Default::default()
        };
        liteparse::LiteParse::new(config)
    })
}

pub fn convert(path: &Path, jobs: usize) -> Outcome {
    let ext = lower_extension(path);
    let label = label_of(path);
    let input = path.to_string_lossy().into_owned();
    let gate = GATE.get_or_init(|| Gate { max: jobs.clamp(1, MAX_CONCURRENT_OCR), active: Mutex::new(0), released: Condvar::new() });
    let _permit = gate.acquire();
    let parse = || runtime().block_on(async {
        tokio::time::timeout(PARSE_TIMEOUT, parser().parse(&input)).await
    });
    let result = if ext == ".pdf" {
        parse()
    } else {
        let _guard = OFFICE_LOCK.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
        parse()
    };
    let text = match result {
        Ok(Ok(result)) => result.text,
        Ok(Err(error)) => {
            println!("LiteParse failed for {}: {error}", path.display());
            return Outcome::Declined;
        }
        Err(_) => {
            println!("LiteParse failed for {}: timeout after {:?}", path.display(), PARSE_TIMEOUT);
            return Outcome::Declined;
        }
    };
    if !has_content(&text) {
        println!("LiteParse produced no text for {}", path.display());
        return Outcome::Declined;
    }
    println!("Successfully converted {label} using LiteParse: {}", path.display());
    Outcome::Text(text, "liteparse")
}
