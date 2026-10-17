//! Secondary conversion engine: LiteParse (LlamaIndex, Apache-2.0).
//!
//! LiteParse parses PDFs locally with bundled Tesseract OCR, so it is the
//! fallback for scanned PDFs that anydoc rejects. PDFium is serialised behind
//! a process-global lock inside the crate, so parsing in one process cannot
//! use more than about one core for rendering. Like the Python version, the
//! port therefore runs OCR in a pool of worker processes (this same binary
//! with `--internal-ocr-worker`), one PDFium instance each. Set
//! `DOCUMIX_OCR_WORKERS=0` to parse in-process instead, or to another number
//! to size the pool.
use std::io::{BufRead, BufReader, BufWriter, Read, Write};
use std::path::Path;
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::{Condvar, Mutex, OnceLock};
use std::time::{Duration, Instant};

use crate::engines::Outcome;
use crate::textutils::{has_content, label_of, lower_extension};

pub const PARSE_TIMEOUT: Duration = Duration::from_secs(300);
/// In-process mode: concurrent parses beyond this do not finish sooner
/// (PDFium rendering is serialised) but each one costs ~80 MB, so cap them.
pub const MAX_CONCURRENT_OCR: usize = 8;
pub const MAX_WORKERS: usize = 16;
pub const WORKER_FLAG: &str = "--internal-ocr-worker";

static RUNTIME: OnceLock<tokio::runtime::Runtime> = OnceLock::new();
static PARSER: OnceLock<liteparse::LiteParse> = OnceLock::new();
/// LibreOffice conversions (every non-PDF input) must not overlap.
static OFFICE_LOCK: Mutex<()> = Mutex::new(());
static GATE: OnceLock<Gate> = OnceLock::new();
static POOL: OnceLock<Pool> = OnceLock::new();

// ---------------------------------------------------------------------------
// In-process parsing
// ---------------------------------------------------------------------------

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
        let config = parser_config(std::env::var("DOCUMIX_OCR_LANGUAGE").ok());
        liteparse::LiteParse::new(config)
    })
}

fn parser_config(language: Option<String>) -> liteparse::config::LiteParseConfig {
    liteparse::config::LiteParseConfig {
        output_format: liteparse::config::OutputFormat::Markdown,
        image_mode: liteparse::config::ImageMode::Off,
        quiet: true,
        ocr_language: language.filter(|value| !value.is_empty()).unwrap_or_else(|| "eng".to_string()),
        ..Default::default()
    }
}

#[cfg(test)]
mod config_tests {
    #[test]
    fn ocr_language_is_preserved_including_multilingual_models() {
        assert_eq!(super::parser_config(Some("pol+eng".to_string())).ocr_language, "pol+eng");
        assert_eq!(super::parser_config(None).ocr_language, "eng");
        assert_eq!(super::parser_config(Some(String::new())).ocr_language, "eng");
    }
}

/// Parse one document here; `Err(message)` is a document-level failure.
fn parse_in_process(input: &str) -> Result<String, String> {
    let result = runtime().block_on(async {
        tokio::time::timeout(PARSE_TIMEOUT, parser().parse(input)).await
    });
    match result {
        Ok(Ok(result)) => Ok(result.text),
        Ok(Err(error)) => Err(error.to_string()),
        Err(_) => Err(format!("timeout after {PARSE_TIMEOUT:?}")),
    }
}

/// Counting semaphore bounding concurrent in-process parses.
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

// ---------------------------------------------------------------------------
// Worker processes
// ---------------------------------------------------------------------------

/// Entry point of a worker process: one request per line on stdin (a file
/// path), one reply per request on stdout (`OK <bytes>\n<markdown>` or
/// `ERR <message>\n`). Exits on EOF, i.e. when the parent goes away.
pub fn worker_main() -> ! {
    let stdin = std::io::stdin();
    let mut out = BufWriter::new(std::io::stdout().lock());
    let mut line = String::new();
    loop {
        line.clear();
        match stdin.lock().read_line(&mut line) {
            Ok(0) | Err(_) => std::process::exit(0),
            Ok(_) => {}
        }
        let path = line.trim_end_matches(['\r', '\n']);
        let reply = parse_in_process(path);
        let written = match reply {
            Ok(text) => out
                .write_all(format!("OK {}\n", text.len()).as_bytes())
                .and_then(|_| out.write_all(text.as_bytes())),
            Err(message) => out.write_all(format!("ERR {}\n", message.replace(['\r', '\n'], " ")).as_bytes()),
        };
        if written.is_err() || out.flush().is_err() {
            std::process::exit(0);
        }
    }
}

struct Worker {
    child: Child,
    /// `None` once the worker has been told to finish (EOF on its stdin).
    stdin: Option<BufWriter<ChildStdin>>,
    stdout: BufReader<ChildStdout>,
}

enum WorkerFailure {
    /// The worker died or the protocol broke; the worker is discarded.
    Broken(String),
}

impl Worker {
    fn spawn() -> std::io::Result<Worker> {
        let exe = std::env::current_exe()?;
        let mut child = Command::new(exe)
            .arg(WORKER_FLAG)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()?;
        let stdin = Some(BufWriter::new(child.stdin.take().expect("piped stdin")));
        let stdout = BufReader::new(child.stdout.take().expect("piped stdout"));
        Ok(Worker { child, stdin, stdout })
    }

    /// Run one request; a document-level failure comes back as `Ok(Err)`.
    fn request(&mut self, path: &str, timeout: Duration) -> Result<Result<String, String>, WorkerFailure> {
        let pid = self.child.id();
        let done = std::sync::Arc::new(std::sync::atomic::AtomicBool::new(false));
        let watchdog_done = done.clone();
        // Watchdog: kill the worker if it exceeds the timeout.
        let watchdog = std::thread::spawn(move || {
            let started = Instant::now();
            while started.elapsed() < timeout {
                if watchdog_done.load(std::sync::atomic::Ordering::SeqCst) {
                    return;
                }
                std::thread::sleep(Duration::from_millis(50));
            }
            // SAFETY: plain libc call on a pid we spawned.
            unsafe { libc::kill(pid as i32, libc::SIGKILL) };
        });
        let result = self.exchange(path);
        done.store(true, std::sync::atomic::Ordering::SeqCst);
        let _ = watchdog.join();
        result
    }

    fn exchange(&mut self, path: &str) -> Result<Result<String, String>, WorkerFailure> {
        let io = |e: std::io::Error| WorkerFailure::Broken(e.to_string());
        let stdin = self.stdin.as_mut().ok_or_else(|| WorkerFailure::Broken("worker already finished".to_string()))?;
        stdin.write_all(path.as_bytes()).map_err(io)?;
        stdin.write_all(b"\n").map_err(io)?;
        stdin.flush().map_err(io)?;
        let mut header = String::new();
        if self.stdout.read_line(&mut header).map_err(io)? == 0 {
            return Err(WorkerFailure::Broken("worker exited (timeout or crash)".to_string()));
        }
        let header = header.trim_end_matches(['\r', '\n']);
        if let Some(len) = header.strip_prefix("OK ") {
            let len: usize = len.parse().map_err(|_| WorkerFailure::Broken(format!("bad reply {header:?}")))?;
            let mut body = vec![0u8; len];
            self.stdout.read_exact(&mut body).map_err(io)?;
            Ok(Ok(String::from_utf8_lossy(&body).into_owned()))
        } else if let Some(message) = header.strip_prefix("ERR ") {
            Ok(Err(message.to_string()))
        } else {
            Err(WorkerFailure::Broken(format!("bad reply {header:?}")))
        }
    }
}

impl Drop for Worker {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

impl Worker {
    /// Graceful stop: EOF on stdin makes the worker exit; then reap it.
    fn finish(&mut self) {
        self.stdin = None;
        let _ = self.child.wait();
    }
}

/// Lazily grown pool of idle workers, at most `max` alive.
struct Pool {
    max: usize,
    state: Mutex<PoolState>,
    available: Condvar,
}

struct PoolState {
    idle: Vec<Worker>,
    alive: usize,
}

impl Pool {
    fn new(max: usize) -> Pool {
        Pool { max, state: Mutex::new(PoolState { idle: Vec::new(), alive: 0 }), available: Condvar::new() }
    }

    fn checkout(&self) -> std::io::Result<Worker> {
        let mut state = self.state.lock().unwrap_or_else(|p| p.into_inner());
        loop {
            if let Some(worker) = state.idle.pop() {
                return Ok(worker);
            }
            if state.alive < self.max {
                state.alive += 1;
                drop(state);
                return match Worker::spawn() {
                    Ok(worker) => Ok(worker),
                    Err(error) => {
                        let mut state = self.state.lock().unwrap_or_else(|p| p.into_inner());
                        state.alive -= 1;
                        self.available.notify_one();
                        Err(error)
                    }
                };
            }
            state = self.available.wait(state).unwrap_or_else(|p| p.into_inner());
        }
    }

    fn checkin(&self, worker: Worker) {
        let mut state = self.state.lock().unwrap_or_else(|p| p.into_inner());
        state.idle.push(worker);
        self.available.notify_one();
    }

    fn discard(&self, worker: Worker) {
        drop(worker);
        let mut state = self.state.lock().unwrap_or_else(|p| p.into_inner());
        state.alive -= 1;
        self.available.notify_one();
    }

    fn run(&self, path: &str) -> Result<String, String> {
        let mut worker = match self.checkout() {
            Ok(worker) => worker,
            Err(error) => return Err(format!("cannot start OCR worker: {error}")),
        };
        match worker.request(path, PARSE_TIMEOUT) {
            Ok(reply) => {
                self.checkin(worker);
                reply
            }
            Err(WorkerFailure::Broken(message)) => {
                self.discard(worker);
                Err(message)
            }
        }
    }
}

/// Stop the worker processes: close their stdin (they exit on EOF) and wait
/// for them, so their CPU time is accounted to this process like Python's
/// pool workers are. Called when a compile finishes.
pub fn shutdown() {
    let Some(pool) = POOL.get() else { return };
    let idle = {
        let mut state = pool.state.lock().unwrap_or_else(|p| p.into_inner());
        let idle = std::mem::take(&mut state.idle);
        state.alive -= idle.len();
        idle
    };
    for mut worker in idle {
        worker.finish();
    }
}

/// Worker count: `DOCUMIX_OCR_WORKERS` (0 = in-process) overrides the
/// compiler's hint, which is `jobs` for real folders and 0 for tiny runs.
pub fn worker_count(jobs: usize, hint: usize) -> usize {
    match std::env::var("DOCUMIX_OCR_WORKERS").ok().and_then(|v| v.trim().parse::<usize>().ok()) {
        Some(n) => n.min(MAX_WORKERS),
        None => hint.min(jobs).min(MAX_WORKERS),
    }
}

// ---------------------------------------------------------------------------
// Public entry
// ---------------------------------------------------------------------------

pub fn convert(path: &Path, jobs: usize, worker_hint: usize) -> Outcome {
    let ext = lower_extension(path);
    let label = label_of(path);
    let input = path.to_string_lossy().into_owned();
    let workers = worker_count(jobs, worker_hint);

    let parse = || {
        if workers == 0 {
            let gate = GATE.get_or_init(|| Gate { max: jobs.clamp(1, MAX_CONCURRENT_OCR), active: Mutex::new(0), released: Condvar::new() });
            let _permit = gate.acquire();
            parse_in_process(&input)
        } else {
            POOL.get_or_init(|| Pool::new(workers)).run(&input)
        }
    };
    let result = if ext == ".pdf" {
        parse()
    } else {
        let _guard = OFFICE_LOCK.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
        parse()
    };
    let text = match result {
        Ok(text) => text,
        Err(error) => {
            println!("LiteParse failed for {}: {error}", path.display());
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
