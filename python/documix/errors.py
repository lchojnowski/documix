"""Exceptions shared across the package."""


class EngineError(RuntimeError):
    """Fatal failure of the primary conversion engine (anydoc).

    Raised when the engine itself is unusable (not installed, import error,
    unexpected crash). It aborts the whole run: ``extract_zip`` and
    ``process_email`` re-raise it instead of writing a placeholder, and the
    CLI exits with status 1 without leaving a partial output file.
    """
