# AI Agent Guidelines for Spectra

This document provides guidelines for AI coding assistants (GitHub Copilot, Cursor, Claude, ChatGPT, etc.) when working on the Spectra codebase.

---

## 🎯 Core Principles

1. **Test Everything** - No change is complete without tests
2. **Type Safety** - All code must be fully typed
3. **Documentation** - Update docs alongside code changes
4. **Backwards Compatibility** - Don't break existing APIs without discussion

---

## 🧪 Testing Requirements

### Before ANY Change is Complete

You MUST run and verify:

```bash
# 1. Unit tests (REQUIRED)
make test

# 2. Type checking (REQUIRED)
make typecheck

# 3. Linting (REQUIRED)
make lint

# 4. Full check (combines all above)
make check
```

### Test Coverage Requirements

| Change Type | Test Requirement |
|-------------|------------------|
| Bug fix | Add regression test that fails without fix |
| New feature | Unit tests + integration test if applicable |
| Refactor | Existing tests must pass, add tests if coverage drops |
| API change | Update all affected tests |
| CLI change | CLI test + help text verification |

### Running Specific Tests

```bash
# Run tests for a specific module
pytest tests/core/test_domain.py -v

# Run tests matching a pattern
pytest -k "test_sync" -v

# Run with coverage for specific file
pytest tests/adapters/test_jira_batch.py --cov=src/spectryn/adapters/jira/batch.py

# Run only fast tests (skip integration/property)
make test-fast

# Run benchmarks (for performance changes)
make bench
```

### Test File Locations

| Source File | Test File |
|-------------|-----------|
| `src/spectryn/core/domain.py` | `tests/core/test_domain.py` |
| `src/spectryn/adapters/jira/adapter.py` | `tests/adapters/test_jira_adapter.py` |
| `src/spectryn/cli/app.py` | `tests/cli/test_cli.py` |

---

## 📝 Code Style

### Python Style

```python
# ✅ Good: Fully typed, documented
def sync_epic(
    epic_key: str,
    *,
    dry_run: bool = True,
    phase: SyncPhase = SyncPhase.ALL,
) -> Result[SyncResult, SyncError]:
    """
    Synchronize an epic from markdown to issue tracker.
    
    Args:
        epic_key: The epic identifier (e.g., "PROJ-123")
        dry_run: If True, preview changes without executing
        phase: Which sync phase to run
        
    Returns:
        Result containing SyncResult on success, SyncError on failure
        
    Raises:
        ConfigurationError: If required config is missing
    """
    ...

# ❌ Bad: No types, no docs
def sync_epic(epic_key, dry_run=True, phase=None):
    ...
```

### Import Order

```python
# Standard library
from __future__ import annotations
import json
from pathlib import Path
from typing import TYPE_CHECKING

# Third-party
import requests

# Local - absolute imports preferred
from spectryn.core.domain import Epic, Story
from spectryn.core.result import Result, Ok, Err

if TYPE_CHECKING:
    from spectryn.core.ports import IssueTrackerPort
```

### Architecture Layers

```
┌─────────────────────────────────────────┐
│              CLI (cli/)                  │  ← User interface
├─────────────────────────────────────────┤
│         Application (application/)       │  ← Use cases, orchestration
├─────────────────────────────────────────┤
│              Core (core/)                │  ← Domain logic, ports
├─────────────────────────────────────────┤
│           Adapters (adapters/)           │  ← External integrations
└─────────────────────────────────────────┘

Rules:
- Core has NO external dependencies
- Adapters implement Core ports
- Application orchestrates Core + Adapters
- CLI only calls Application layer
```

---

## 🔧 Common Tasks

### Adding a New Feature

1. **Design**: Consider which layer it belongs to
2. **Tests First**: Write failing tests
3. **Implement**: Make tests pass
4. **Types**: Ensure full type coverage
5. **Docs**: Update relevant documentation
6. **Verify**: Run `make check`

### Adding a New Adapter

```python
# 1. Create adapter package
src/spectryn/adapters/my_tracker/
├── __init__.py
├── adapter.py      # IssueTrackerPort implementation
├── client.py       # Low-level API client
└── plugin.py       # Plugin registration

# 2. Implement the port interface
from spectryn.core.ports import IssueTrackerPort

class MyTrackerAdapter(IssueTrackerPort):
    @property
    def name(self) -> str:
        return "MyTracker"
    
    def get_epic(self, epic_key: str) -> Result[Epic, TrackerError]:
        ...

# 3. Add tests
tests/adapters/test_my_tracker_adapter.py

# 4. Register as plugin (optional)
# In plugin.py, create TrackerPlugin subclass
```

### Modifying CLI

```python
# 1. Update cli/app.py or relevant command file
# 2. Update help text and examples
# 3. Add CLI test in tests/cli/
# 4. Update docs/reference/cli.md
# 5. Update shell completions if new flags added
```

### Changing Domain Models

```python
# 1. Update entity in core/domain/entities.py
# 2. Update tests/core/test_domain.py
# 3. Run property-based tests: pytest tests/property/
# 4. Check all adapters that use the model
# 5. Update documentation
```

---

## 🚫 Things to Avoid

### Never Do This

```python
# ❌ Untyped function
def process(data):
    return data

# ❌ Bare except
try:
    risky_operation()
except:
    pass

# ❌ Mutable default arguments
def add_item(items=[]):
    items.append(1)
    return items

# ❌ Import side effects
import os
os.environ["DEBUG"] = "true"  # Side effect at import!

# ❌ Direct external calls from core
from spectryn.core.domain import Epic
import requests  # ❌ Core shouldn't import requests!

# ❌ Ignoring Result types
result = do_operation()
value = result.unwrap()  # ❌ Could raise!

# ✅ Handle Results properly
result = do_operation()
if result.is_ok():
    value = result.unwrap()
else:
    handle_error(result.unwrap_err())

# ✅ Or use match/map
result.map(process_value).unwrap_or(default_value)
```

### Avoid Without Good Reason

- Adding new dependencies (discuss first)
- Changing public API signatures
- Modifying test fixtures
- Skipping tests with `@pytest.skip`
- Using `# type: ignore` without explanation

---

## 📋 Pre-Commit Checklist

Before considering any change complete, verify:

```
□ All tests pass: make test
□ Type checking passes: make typecheck  
□ Linting passes: make lint
□ New code has tests
□ Tests cover edge cases
□ Docstrings are complete
□ Types are complete (no `Any` without reason)
□ No new linting warnings
□ Documentation updated if needed
□ CHANGELOG.md updated for user-facing changes
```

---

## 🏃 Quick Commands

```bash
# Full validation (run before every commit)
make check

# Just tests
make test

# Fast tests only
make test-fast

# With coverage report
make test-cov

# Type check
make typecheck

# Lint and auto-fix
make format

# Run specific test file
pytest tests/core/test_result.py -v

# Run tests matching pattern
pytest -k "test_sync" -v

# Debug a failing test
pytest tests/path/to/test.py::test_name -v --tb=long

# Run benchmarks
make bench
```

---

## 🔍 Finding Things

### Where is X implemented?

| Feature | Location |
|---------|----------|
| Domain entities | `src/spectryn/core/domain/entities.py` |
| Ports/interfaces | `src/spectryn/core/ports/` |
| Jira adapter | `src/spectryn/adapters/jira/` |
| CLI commands | `src/spectryn/cli/app.py` |
| Sync orchestrator | `src/spectryn/application/sync/orchestrator.py` |
| Plugin system | `src/spectryn/plugins/` |
| Test fixtures | `tests/conftest.py` |

### Understanding the codebase

```bash
# Find implementations of a port
grep -r "IssueTrackerPort" src/spectryn/adapters/

# Find all tests for a module
find tests -name "test_*.py" | xargs grep "from spectryn.core.domain"

# Check what imports a module
grep -r "from spectryn.core.result" src/
```

---

## 💡 Tips for AI Assistants

1. **Always verify context** - Read existing code before making changes
2. **Follow existing patterns** - Match the style of surrounding code
3. **Small changes** - Prefer small, focused changes over large refactors
4. **Run tests locally** - Don't assume tests will pass
5. **Explain changes** - Provide clear commit messages and PR descriptions
6. **Ask for clarification** - If requirements are unclear, ask

---

## 📚 Key Documentation

- [Architecture Guide](../docs/guide/architecture.md)
- [Plugin Development](../docs/guide/plugins.md)
- [CLI Reference](../docs/reference/cli.md)
- [Contributing Guide](../CONTRIBUTING.md)
- [Release Process](.github/RELEASE.md)


