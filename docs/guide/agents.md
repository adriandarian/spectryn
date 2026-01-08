# Working with AI Agents

This guide helps AI coding assistants (Claude, Cursor, GitHub Copilot, Codeium, etc.) effectively work with the spectryn codebase and markdown format.

::: tip Quick Reference
See [`AGENTS.md`](https://github.com/adriandarian/spectryn/blob/main/AGENTS.md) in the project root for the essential commands AI agents should run before completing any task.
:::

::: tip For Humans
If you're looking to use AI tools to **fix** your markdown files, see the [AI Fix Guide](/guide/ai-fix). If you want to **generate** new epic documents, see [AI Prompts](/guide/ai-prompts). This page is context for AI agents working on the spectryn codebase itself.
:::

## Project Overview

**spectryn** is a CLI tool that synchronizes markdown/YAML user story specifications to issue trackers (Jira, GitHub Issues, Linear, Azure DevOps). It follows Clean Architecture with a Hexagonal/Ports-and-Adapters pattern.

### Key Concepts

| Concept | Description |
|---------|-------------|
| **Epic** | A collection of user stories, parsed from a document |
| **UserStory** | Individual work item with description, acceptance criteria, subtasks |
| **Parser** | Converts source documents to domain entities |
| **Adapter** | Connects to external systems (Jira, GitHub, etc.) |
| **Sync** | Bidirectional: push stories to tracker, pull updates back |

## Codebase Structure

```
spectryn/
├── src/spectryn/
│   ├── core/              # Domain layer (entities, enums, ports)
│   │   ├── domain/        # Entity definitions (Epic, UserStory, etc.)
│   │   ├── ports/         # Abstract interfaces (DocumentParser, IssueTracker)
│   │   └── services.py    # Domain services and factories
│   ├── adapters/          # Infrastructure layer
│   │   ├── parsers/       # Document parsers (markdown, yaml, json, etc.)
│   │   ├── jira/          # Jira adapter
│   │   ├── github/        # GitHub Issues adapter
│   │   ├── linear/        # Linear adapter
│   │   └── ...            # Other adapters
│   ├── application/       # Use cases and orchestration
│   └── cli/               # CLI commands and output formatting
├── tests/                 # Test suites (mirrors src structure)
├── docs/                  # VitePress documentation
└── integrations/          # IDE plugins, Terraform, GitHub Action
```

### Key Files

| File | Purpose |
|------|---------|
| `src/spectryn/core/domain/entities.py` | Core domain entities (Epic, UserStory, Subtask, Comment) |
| `src/spectryn/core/domain/enums.py` | Status, Priority enums with parsing logic |
| `src/spectryn/core/ports/document_parser.py` | Parser interface |
| `src/spectryn/adapters/parsers/markdown.py` | Main markdown parser |
| `src/spectryn/cli/app.py` | CLI entry point and command definitions |
| `src/spectryn/cli/validate.py` | Validation logic |
| `src/spectryn/cli/ai_fix.py` | AI-assisted fixing features |

## Markdown Format Reference

When working with spectryn's markdown parsing, understand these exact patterns:

### Story Header Pattern
```python
# Regex: r"### [^\n]* (US-\d+|[A-Z]+-\d+): ([^\n]+)"
### 🔧 STORY-001: Story Title
### PROJ-123: Another Title
```

### Metadata Pattern
```markdown
| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Priority** | 🔴 Critical |
| **Status** | 🔄 In Progress |
```

Or inline format:
```markdown
**Priority**: P0
**Story Points**: 5
**Status**: 🔄 In Progress
```

### User Story Description
```markdown
#### Description

**As a** [role]
**I want** [feature]
**So that** [benefit]
```

### Status Enum Values

```python
# From src/spectryn/core/domain/enums.py
class Status(Enum):
    DONE = "done"          # ✅ Done, Complete, Closed, Resolved
    IN_PROGRESS = "in_progress"  # 🔄 In Progress, In Development
    PLANNED = "planned"    # 📋 Planned, To Do, Backlog, Not Started
    BLOCKED = "blocked"    # ⏸️ Blocked, On Hold
    CANCELLED = "cancelled"  # Cancelled, Won't Fix
```

### Priority Enum Values

```python
class Priority(Enum):
    CRITICAL = "critical"  # 🔴 P0, Blocker, Highest
    HIGH = "high"          # 🟡 P1, Major
    MEDIUM = "medium"      # 🟢 P2
    LOW = "low"            # 🔵 P3, P4, Minor, Trivial
```

## Code Conventions

### Python Style

- **Python 3.11+** with type hints everywhere
- **Dataclasses** for domain entities
- **Enum** for constrained values
- **Protocol** classes for interfaces (structural subtyping)
- **pytest** for testing with fixtures

### Architecture Patterns

1. **Dependency Inversion**: Core depends on abstractions, adapters implement them
2. **Factory Functions**: `create_parser_factory()`, `create_adapter_factory()`
3. **Result Types**: Operations return results with success/error states
4. **Immutable Entities**: Domain entities use frozen dataclasses where possible

### Example: Adding a New Parser

```python
# 1. Create parser in src/spectryn/adapters/parsers/
from spectryn.core.ports.document_parser import DocumentParser

class MyFormatParser(DocumentParser):
    @property
    def name(self) -> str:
        return "MyFormat"

    @property
    def supported_extensions(self) -> list[str]:
        return [".myf"]

    def can_parse(self, source: str | Path) -> bool:
        # Detection logic
        ...

    def parse_stories(self, content: str | Path) -> list[UserStory]:
        # Parsing logic
        ...

# 2. Register in src/spectryn/adapters/parsers/__init__.py
# 3. Add to factory in src/spectryn/core/services.py
# 4. Write tests in tests/adapters/test_myformat_parser.py
```

## Testing Patterns

### Test Structure

```python
class TestMyParser:
    @pytest.fixture
    def parser(self) -> MyParser:
        return MyParser()

    def test_parse_minimal(self, parser):
        """Should parse minimal valid input."""
        ...

    def test_parse_full(self, parser):
        """Should parse input with all fields."""
        ...

    def test_validate_errors(self, parser):
        """Should catch validation errors."""
        ...
```

### Common Test Fixtures

- `tmp_path`: Pytest built-in for temporary directories
- `parser`: Parser instance fixture
- Sample content using `textwrap.dedent()` for multiline strings

## AI Agent Guidelines

### When Editing Code

1. **Preserve Architecture**: Don't bypass ports/adapters pattern
2. **Type Everything**: All function parameters and returns need types
3. **Match Existing Style**: Follow patterns in surrounding code
4. **Update Tests**: New features need tests in `tests/`
5. **Docstrings**: Use Google-style docstrings

### When Fixing Markdown

1. **Don't Invent Content**: Preserve user's story IDs, titles, descriptions
2. **Fix Format Only**: Adjust structure to match schema, keep meaning
3. **Validate Output**: Ensure the result passes `spectryn --validate`

### When Adding Features

1. **Start with Domain**: Define entities/enums in `core/domain/`
2. **Define Ports**: Abstract interfaces in `core/ports/`
3. **Implement Adapters**: Concrete implementations in `adapters/`
4. **Wire CLI**: Commands in `cli/app.py`, handlers in other CLI modules
5. **Document**: Update relevant docs in `docs/guide/`

## Common Tasks

### Task: Fix Validation Error

1. Read the error message from `spectryn --validate`
2. Locate the regex/parsing logic in `adapters/parsers/markdown.py`
3. Check enum parsing in `core/domain/enums.py`
4. Adjust format to match expected patterns

### Task: Add New Issue Tracker

1. Create adapter directory: `src/spectryn/adapters/newtracker/`
2. Implement `IssueTrackerPort` interface
3. Add configuration in CLI
4. Write integration tests
5. Update documentation

### Task: Extend Markdown Schema

1. Update entity in `core/domain/entities.py`
2. Add parsing logic in `adapters/parsers/markdown.py`
3. Update format guide in `cli/ai_fix.py` → `generate_format_guide()`
4. Update docs: `docs/guide/schema.md`
5. Add tests

## Before Completing Any Task

**Always run these quality checks:**

```bash
# All-in-one validation
ruff format src tests && ruff check src tests --fix && mypy src/spectryn && pytest
```

Or individually:

| Task | Command |
|------|---------|
| Format | `ruff format src tests` |
| Lint + Fix | `ruff check src tests --fix` |
| Type Check | `mypy src/spectryn` |
| Test | `pytest` |
| Test + Coverage | `pytest --cov=spectryn` |

## Environment Setup

```bash
# Install in development mode
pip install -e ".[dev]"

# Run CLI
spectryn --help
spectryn --validate --markdown EPIC.md
```

## Useful Commands for Agents

```bash
# Understand the codebase
find src -name "*.py" | head -20
grep -r "def parse_stories" src/
grep -r "class.*Parser" src/

# Check test patterns
pytest tests/adapters/test_markdown_parser.py -v

# Validate changes
spectryn --validate --markdown tests/samples/spacemouse-user-stories.md
```

## Related Documentation

- [Schema Reference](/guide/schema) – Complete markdown format specification
- [AI Fix Guide](/guide/ai-fix) – Fix formatting with AI tools
- [AI Prompts](/guide/ai-prompts) – Generate new epic documents
- [Architecture](/guide/architecture) – System design deep-dive
- [CLI Reference](/reference/cli) – All command options

