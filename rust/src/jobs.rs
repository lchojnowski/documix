//! `compiler.default_jobs()`: one job per logical CPU, bounded by installed
//! memory at ~1.5 GB per job, `DOCUMIX_JOBS` overrides.
pub const MAX_DEFAULT_JOBS: usize = 32;
pub const MEMORY_PER_JOB_GB: f64 = 1.5;

pub fn physical_memory_gb() -> Option<f64> {
    let mut system = sysinfo::System::new();
    system.refresh_memory();
    let total = system.total_memory();
    if total == 0 { None } else { Some(total as f64 / (1u64 << 30) as f64) }
}

pub fn default_jobs() -> usize {
    if let Ok(value) = std::env::var("DOCUMIX_JOBS") {
        let value = value.trim();
        if !value.is_empty() && value.chars().all(|c| c.is_ascii_digit()) {
            if let Ok(n) = value.parse::<usize>() {
                if n >= 1 {
                    return n;
                }
            }
        }
    }
    let cpus = std::thread::available_parallelism().map(|n| n.get()).unwrap_or(1);
    let budget = match physical_memory_gb() {
        Some(gb) => ((gb / MEMORY_PER_JOB_GB) as usize).max(1),
        None => cpus,
    };
    cpus.min(budget).min(MAX_DEFAULT_JOBS).max(1)
}
