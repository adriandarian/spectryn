# Contributing to spectryn

First off, thank you for considering contributing to spectryn! 🎉

This document provides guidelines and instructions for contributing. Following these guidelines helps communicate that you respect the time of the developers maintaining this project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Architecture Overview](#architecture-overview)
- [Making Changes](#making-changes)
- [Code Style](#code-style)
- [Testing](#testing)
- [Submitting Changes](#submitting-changes)
- [Reporting Issues](#reporting-issues)
- [Feature Requests](#feature-requests)
- [Community](#community)

---

## Code of Conduct

This project adheres to the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior to the maintainers.

---

## Getting Started

### Prerequisites

- Python 3.10 or higher
- Git
- A GitHub account
- (Optional) A Jira instance for integration testing

### Finding Something to Work On

- Check the [Issues](https://github.com/adriandarian/spectryn/issues) page for open issues
- Look for issues labeled `good first issue` for beginner-friendly tasks
- Feel free to propose new ideas by opening an issue first

### Before You Start

1. **Check existing issues** - Your idea might already be in progress
2. **Open an issue** - For significant changes, discuss your approach first
3. **Claim the issue** - Comment on the issue to let others know you're working on it

---

## Development Setup

### 1. Fork and Clone

```bash
# Fork the repository on GitHub, then:
git clone https://github.com/YOUR_USERNAME/spectryn.git
cd spectryn
```

### 2. Create a Virtual Environment

```bash
# Using venv
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Or using pyenv
pyenv virtualenv 3.10 spectryn
pyenv activate spectryn
```

### 3. Install Dependencies

```bash
# Install with development dependencies
pip install -e ".[dev]"
```

### 4. Set Up Pre-commit Hooks

```bash
pre-commit install
```

This will run linting and formatting checks before each commit.

### 5. Verify Installation

```bash
# Run tests
pytest

# Check types
mypy src/

# Check linting
ruff check src/ tests/

# Check formatting
ruff format --check src/ tests/
```

### 6. Configure Environment (Optional)

For integration testing, create a `.env` file:

```bash
JIRA_URL=https://your-company.atlassian.net
JIRA_EMAIL=your.email@company.com
JIRA_API_TOKEN=your-api-token
```

> ⚠️ Never commit `.env` files or API tokens to the repository.

---

## Architecture Overview

spectryn follows **Clean Architecture** / **Hexagonal Architecture** principles. Understanding this structure is crucial for contributing:

```
src/spectryn/
├── core/                 # Pure domain logic (no external dependencies)
│   ├── domain/           # Entities, value objects, enums, events
│   └── ports/            # Abstract interfaces (protocols)
├── adapters/             # Infrastructure implementations
│   ├── jira/             # Jira API adapter
│   ├── parsers/          # Document parsers (markdown)
│   ├── formatters/       # Output formatters (ADF)
│   └── config/           # Configuration providers
├── application/          # Use cases and orchestration
│   ├── commands/         # Command pattern handlers
│   └── sync/             # Sync orchestrator
├── cli/                  # Command line interface
└── plugins/              # Extension system
```

### Key Principles

1. **Core has no dependencies** - `core/` should never import from `adapters/`, `application/`, or `cli/`
2. **Ports define contracts** - All external interactions go through port interfaces
3. **Adapters implement ports** - Concrete implementations live in `adapters/`
4. **Commands are reversible** - Write operations use the Command pattern

### Adding New Features

- **New tracker?** → See the [Adapter Development Guide](docs/guide/adapter-development.md) for comprehensive instructions
- **New parser?** → Implement `DocumentParserPort` in `adapters/parsers/`
- **New formatter?** → Implement `DocumentFormatterPort` in `adapters/formatters/`
- **New command?** → Add to `application/commands/`

### Adding a New Issue Tracker

If you want to add support for a new issue tracker (e.g., your company's internal tool):

1. **Read the guide** - See [`docs/guide/adapter-development.md`](docs/guide/adapter-development.md) for complete instructions
2. **Create the adapter** - Implement `IssueTrackerPort` interface
3. **Add tests** - Aim for 50+ unit tests with good coverage
4. **Validate** - Run `ruff format`, `ruff check`, `mypy`, and `pytest`
5. **Document** - Add a guide in `docs/guide/`

The adapter development guide includes:
- Complete code templates for client, adapter, and plugin
- Rate limiting and retry patterns
- Status mapping best practices
- Testing examples
- Validation checklist

---

## Making Changes

### Branch Naming

Use descriptive branch names:

```bash
feature/add-github-adapter
fix/handle-empty-description
docs/update-readme
refactor/simplify-parser
chore/update-dependencies
```

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `style`: Formatting, missing semicolons, etc.
- `refactor`: Code change that neither fixes a bug nor adds a feature
- `perf`: Performance improvement
- `test`: Adding or correcting tests
- `chore`: Maintenance tasks

**Examples:**

```bash
feat(parser): add support for nested subtasks
fix(jira): handle rate limiting with exponential backoff
docs(readme): add installation instructions for Windows
test(commands): add unit tests for UpdateDescriptionCommand
```

### Keeping Your Fork Updated

```bash
# Add upstream remote (one-time)
git remote add upstream https://github.com/adriandarian/spectryn.git

# Sync with upstream
git fetch upstream
git checkout main
git merge upstream/main
git push origin main
```

---

## Code Style

### Python Style

We use these tools to maintain consistent code style:

| Tool | Purpose | Config |
|------|---------|--------|
| **Ruff** | Linting & Formatting | `pyproject.toml` |
| **mypy** | Type checking | `pyproject.toml` |

### General Guidelines

```python
# ✅ Good: Use type hints
def get_story(self, story_id: str) -> Optional[UserStory]:
    ...

# ❌ Bad: No type hints
def get_story(self, story_id):
    ...

# ✅ Good: Descriptive names
def calculate_story_points_total(stories: list[UserStory]) -> int:
    ...

# ❌ Bad: Abbreviated names
def calc_sp(s):
    ...

# ✅ Good: Docstrings for public APIs
def sync_epic(self, epic_key: str, options: SyncOptions) -> SyncResult:
    """
    Synchronize an epic from markdown to the issue tracker.

    Args:
        epic_key: The issue tracker key for the epic (e.g., "PROJ-123")
        options: Configuration options for the sync operation

    Returns:
        SyncResult containing success status and any errors

    Raises:
        ValidationError: If the epic key format is invalid
        ConnectionError: If the issue tracker is unreachable
    """
    ...
```

### Import Order

Managed by Ruff/isort:

```python
# Standard library
import os
from pathlib import Path

# Third-party
import requests

# Local
from spectryn.core.domain import Epic, UserStory
from spectryn.core.ports import IssueTrackerPort
```

### Line Length

- Maximum line length: **100 characters**
- Ruff enforces this automatically

### Running Style Checks

```bash
# Format code
ruff format src/ tests/

# Check linting
ruff check src/ tests/

# Fix auto-fixable issues
ruff check --fix src/ tests/

# Type checking
mypy src/
```

---

## Testing

### Test Structure

Tests mirror the source structure:

```
tests/
├── adapters/
│   ├── test_adf_formatter.py
│   └── test_markdown_parser.py
├── application/
│   └── test_commands.py
├── core/
│   └── test_domain.py
└── plugins/
    └── test_hooks.py
```

### Writing Tests

```python
import pytest
from spectryn.core.domain import UserStory, StoryPoints


class TestUserStory:
    """Tests for UserStory entity."""

    def test_create_user_story_with_valid_data(self):
        """User story should be created with valid inputs."""
        story = UserStory(
            id="US-001",
            title="User Authentication",
            points=StoryPoints(5),
        )
        assert story.id == "US-001"
        assert story.points.value == 5

    def test_story_points_must_be_positive(self):
        """Story points should raise error for negative values."""
        with pytest.raises(ValueError, match="must be positive"):
            StoryPoints(-1)

    @pytest.mark.parametrize("points,expected", [
        (1, "XS"),
        (3, "S"),
        (5, "M"),
        (8, "L"),
        (13, "XL"),
    ])
    def test_story_size_labels(self, points, expected):
        """Story points should map to correct size labels."""
        sp = StoryPoints(points)
        assert sp.size_label == expected
```

### Test Markers

```python
@pytest.mark.slow
def test_large_epic_sync():
    """Mark slow tests."""
    ...

@pytest.mark.integration
def test_jira_connection():
    """Mark integration tests (require external services)."""
    ...
```

### Running Tests

```bash
# Run all standard tests (heavy tests are skipped by default)
pytest

# Run with coverage
pytest --cov=src/spectryn

# Run specific test file
pytest tests/core/test_domain.py

# Run specific test
pytest tests/core/test_domain.py::TestUserStory::test_create_user_story_with_valid_data

# Verbose output
pytest -v
```

### Running Heavy/Specialized Tests

By default, slow, stress, chaos, e2e, and benchmark tests are **skipped** to keep the test suite fast.
To run these tests explicitly:

```bash
# Run slow tests (load testing, large data sets)
pytest -m slow

# Run stress tests (high load, resource limits)
pytest -m stress

# Run chaos tests (failure injection, resilience)
pytest -m chaos

# Run end-to-end workflow tests
pytest -m e2e

# Run performance benchmarks
pytest -m benchmark --benchmark-enable

# Run integration tests (mocked external services)
pytest tests/integration/ -v

# Run property-based tests (hypothesis)
pytest tests/property/ -v

# Run ALL tests including heavy ones
pytest -m ""

# Combine markers
pytest -m "slow or stress"
```

### Test Categories

| Marker | Description | Default |
|--------|-------------|---------|
| `slow` | Tests with large data or long runtime | Skipped |
| `stress` | Load and stress tests | Skipped |
| `chaos` | Chaos engineering / failure tests | Skipped |
| `e2e` | End-to-end workflow tests | Skipped |
| `benchmark` | Performance benchmarks | Skipped |
| `integration` | Integration tests (mocked APIs) | Included |

### Coverage Requirements

- Aim for **80%+ coverage** on new code
- Don't sacrifice test quality for coverage numbers
- Focus on testing behavior, not implementation details

---

## Submitting Changes

### Pull Request Process

1. **Update your branch** with the latest main

   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Run all checks locally**

   ```bash
   pytest
   mypy src/
   ruff check src/ tests/
   ruff format --check src/ tests/
   ```

3. **Push your branch**

   ```bash
   git push origin feature/your-feature-name
   ```

4. **Open a Pull Request** on GitHub

### PR Title Format

Use the same format as commit messages:

```
feat(parser): add support for nested subtasks
```

### PR Description Template

```markdown
## Description
Brief description of changes.

## Related Issue
Closes #123

## Type of Change
- [ ] Bug fix (non-breaking change fixing an issue)
- [ ] New feature (non-breaking change adding functionality)
- [ ] Breaking change (fix or feature causing existing functionality to change)
- [ ] Documentation update

## Checklist
- [ ] My code follows the project's style guidelines
- [ ] I have added tests that prove my fix/feature works
- [ ] All new and existing tests pass locally
- [ ] I have updated documentation as needed
- [ ] I have added docstrings to new public APIs
```

### Review Process

1. **Automated checks** must pass (CI/CD)
2. **At least one maintainer** will review your PR
3. **Address feedback** - push additional commits as needed
4. **Squash and merge** - maintainers will merge when approved

### After Your PR is Merged

- Delete your branch
- Update your local main
- Celebrate! 🎉

---

## Reporting Issues

### Bug Reports

Use the bug report template and include:

- **Clear title** describing the bug
- **Environment** (Python version, OS, spectryn version)
- **Steps to reproduce** the issue
- **Expected behavior** vs actual behavior
- **Error messages** and stack traces
- **Minimal reproducible example** if possible

```markdown
## Bug Description
What went wrong?

## Environment
- spectryn version: 2.0.0
- Python version: 3.10.12
- OS: macOS 14.0 / Ubuntu 22.04 / Windows 11

## Steps to Reproduce
1. Create a markdown file with...
2. Run `spectryn --markdown file.md --epic PROJ-123`
3. See error

## Expected Behavior
What should have happened?

## Actual Behavior
What actually happened?

## Error Output
```
Paste error message here
```

## Additional Context
Any other relevant information.
```

---

## Feature Requests

Before requesting a feature:

1. Search existing issues for similar requests
2. Consider if it aligns with project goals
3. Use the feature request issue template

When requesting:

```markdown
## Feature Description
Clear description of the feature.

## Use Case
Why do you need this? What problem does it solve?

## Proposed Solution
How do you envision this working?

## Alternatives Considered
Other approaches you've thought about.

## Additional Context
Mockups, examples, or references.
```

---

## Community

### Getting Help

- **GitHub Issues** - For bugs and feature requests
- **Discussions** - For questions and general discussion
- **README** - For documentation and quick start

### Recognition

Contributors are recognized in:
- Release notes
- README contributors section (for significant contributions)
- GitHub's contributor graph

---

## License

By contributing to spectryn, you agree that your contributions will be licensed under the [MIT License](LICENSE).

---

Thank you for contributing to spectryn! Your help makes this project better for everyone. 💙


