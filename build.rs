//! Embed the DocuMix version the same way `python/documix/version.py`
//! computes it: the package version (Cargo.toml, ScalVer `1.YYYYMMDD.N`), plus
//! `-dev (branch)` when built inside a git checkout on a named branch.
use std::path::Path;
use std::process::Command;

fn main() {
    let manifest = std::env::var("CARGO_MANIFEST_DIR").unwrap();
    let repo = Path::new(&manifest).to_path_buf();
    println!("cargo:rerun-if-changed={}", repo.join(".git/HEAD").display());

    let mut version = std::env::var("CARGO_PKG_VERSION").unwrap_or_else(|_| "0.0.0".to_string());
    if repo.join(".git").exists() {
        if let Ok(out) = Command::new("git")
            .args(["rev-parse", "--abbrev-ref", "HEAD"])
            .current_dir(&repo)
            .output()
        {
            if out.status.success() {
                let branch = String::from_utf8_lossy(&out.stdout).trim().to_string();
                if !branch.is_empty() && branch != "HEAD" {
                    version = format!("{version}-dev ({branch})");
                }
            }
        }
    }
    println!("cargo:rustc-env=DOCUMIX_VERSION={version}");
}
