pub mod anydoc;
pub mod liteparse;

/// What a converter produced for one document.
pub enum Outcome {
    /// Markdown text plus the method label (`anydoc`, `liteparse`, `failed`).
    Text(String, &'static str),
    /// The converter declined the document; the chain moves on.
    Declined,
}
