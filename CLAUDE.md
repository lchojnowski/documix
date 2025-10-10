# DocuMix Development Guide

## Build & Test Commands

```bash
# Install dev dependencies
pip install -e .

# Run all tests
python -m pytest

# Run a single test
python -m pytest tests/test_documix.py::TestDocuMix::test_collect_files -v

# Run tests with coverage
python -m pytest --cov=documix
```

## Code Style Guidelines

- **Naming**: snake_case for functions/variables, PascalCase for classes
- **Imports**: group standard lib, third-party, and local imports with space between
- **Typing**: Type hints encouraged but not strictly enforced
- **Error handling**: Use try/except blocks with specific exceptions
- **Documentation**: Docstrings should follow the existing triple-quote style
- **Line length**: Keep lines to ~80 characters when possible
- **Formatting**: Maintain consistent 4-space indentation

When extending the project, follow existing patterns for file processing and document conversion.

## Documentation

- Always update `README.md` with new features and changes
- Make sure if there are new options we update help text in the code displayed when command is run with --help
- When fixing ALWAYS address the root cause of the problem, not just the symptoms