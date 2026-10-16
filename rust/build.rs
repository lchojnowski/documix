//! Embed the DocuMix version the same way `documix/version.py` computes it:
//! `__version__` from `documix/__init__.py`, plus `-dev (branch)` when the
//! package lives inside a git checkout on a named branch.
use std::path::Path;
use std::process::Command;

fn main() {
    let manifest = std::env::var("CARGO_MANIFEST_DIR").unwrap();
    let repo = Path::new(&manifest).join("..");
    let init = repo.join("documix").join("__init__.py");
    println!("cargo:rerun-if-changed={}", init.display());
    println!("cargo:rerun-if-changed={}", repo.join(".git/HEAD").display());

    let mut version = String::from("0.0.0");
    if let Ok(text) = std::fs::read_to_string(&init) {
        for line in text.lines() {
            let Some(rest) = line.trim_start().strip_prefix("__version__") else { continue };
            if let Some(start) = rest.find(['"', '\'']) {
                let quote = rest[start..].chars().next().unwrap();
                let after = &rest[start + 1..];
                if let Some(end) = after.find(quote) {
                    version = after[..end].to_string();
                }
            }
        }
    }
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
