# AI Agent Instructions

This file provides instructions for AI coding assistants (Claude, Cursor, Copilot, etc.) working on the spectra codebase.

## Before Submitting Changes

**For quick iterations, use the "Quick Check" task (no tests):**

```bash
# Fast validation (~5 seconds): Format, lint, type check
ruff format src tests && ruff check src tests --fix && mypy src/spectra
```

**For full validation with tests (~40 seconds):**

```bash
# Full checks with parallel tests
ruff format src tests && ruff check src tests --fix && mypy src/spectra && pytest
```

## ⚡ Performance Notes

- Tests run in **parallel** using `pytest-xdist` (auto-detects CPU cores)
- Tests have a **30-second timeout** to prevent hangs
- Heavy tests (slow, stress, chaos, e2e, benchmark) are **skipped by default**
- Use "Quick Check" task for rapid iteration, "All Checks" for final validation

## Command Reference

| Task | Command |
|------|---------|
| **Quick Check** | `ruff format src tests && ruff check src tests --fix && mypy src/spectra` |
| Format | `ruff format src tests` |
| Lint | `ruff check src tests` |
| Lint + Fix | `ruff check src tests --fix` |
| Type Check | `mypy src/spectra` |
| Test | `pytest` |
| Test + Coverage | `pytest --cov=spectra` |
| Test Specific | `pytest tests/adapters/test_markdown_parser.py -v` |
| Test Slow | `pytest -m slow` |
| Test Chaos | `pytest -m chaos` |
| Test E2E | `pytest -m e2e` |
| Test Benchmark | `pytest -m benchmark --benchmark-enable` |
| Test All (incl. heavy) | `pytest -m ""` |
| Install Dev | `pip install -e ".[dev]"` |

**Note:** Heavy tests (slow, stress, chaos, e2e, benchmark) are skipped by default.
Use the specific marker commands above to run them.

**⚠️ AI Agent Rule:** Do NOT automatically run heavy tests. After standard tests pass,
ASK the user if they want to run heavy tests before executing them. Heavy tests can
take significant time and resources.

## Code Standards

### Python
- Python 3.11+ with full type hints on all functions
- Use `dataclass` for entities, `Enum` for constrained values
- Use `Protocol` for interfaces (structural subtyping)
- Absolute imports only: `from spectra.core.domain.entities import UserStory`

### Architecture
- Core depends on abstractions, adapters implement them
- Don't bypass ports layer for external systems
- New features need tests in `tests/` mirroring `src/` structure

### Testing
- Use pytest fixtures
- Use `tmp_path` for file operations
- Use `textwrap.dedent()` for multiline test strings

## Common Issues

### Ruff Errors
```bash
# See all errors
ruff check src tests

# Auto-fix what's possible
ruff check src tests --fix
```

### Mypy Errors
```bash
# Check specific file
mypy src/spectra/path/to/file.py

# Ignore missing imports (if needed)
mypy src/spectra --ignore-missing-imports
```

### Test Failures
```bash
# Run specific test with output
pytest tests/path/to/test.py -v -s

# Run tests matching pattern
pytest -k "test_parse" -v
```

## File Structure

```
src/spectra/
├── core/           # Domain (entities, enums, ports)
├── adapters/       # Infrastructure (parsers, API clients)
├── application/    # Use cases
└── cli/            # Commands

tests/              # Mirrors src structure
```

## Key Files

- `src/spectra/core/domain/entities.py` - Epic, UserStory, Subtask
- `src/spectra/core/domain/enums.py` - Status, Priority parsing
- `src/spectra/adapters/parsers/markdown.py` - Main parser
- `src/spectra/cli/app.py` - CLI entry point

