//! DocuMix: compile a folder of documents into one Markdown file.
//! The Python implementation under `python/` is the fallback for the legacy
//! converters; both must stay byte-identical on the default path.
pub mod archive;
pub mod cli;
pub mod compile;
pub mod config;
pub mod convert;
pub mod email;
pub mod engines;
pub mod jobs;
pub mod output;
pub mod scan;
pub mod textutils;

/// Version string embedded by build.rs (mirrors `documix.version.get_version`).
pub const VERSION: &str = env!("DOCUMIX_VERSION");

/// Fatal failure of the primary engine (`documix.errors.EngineError`).
#[derive(Debug, Clone, thiserror::Error)]
#[error("{0}")]
pub struct EngineError(pub String);
