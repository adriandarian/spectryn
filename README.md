# md2jira

<div align="center">

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

**A production-grade CLI tool for synchronizing markdown documentation with Jira**

[Features](#features) •
[Installation](#installation) •
[Quick Start](#quick-start) •
[Architecture](#architecture) •
[Documentation](#documentation)

</div>

---

## Features

🚀 **Full Epic Sync** - Sync user stories, subtasks, descriptions, and comments from markdown to Jira

📝 **Markdown-Native** - Write your epic documentation in markdown, sync to Jira automatically

🔄 **Smart Matching** - Fuzzy title matching between markdown stories and Jira issues

🛡️ **Safe by Default** - Dry-run mode, confirmations, and detailed previews before any changes

⚡ **Command Pattern** - Undo-capable operations with full audit trail

🔌 **Plugin System** - Extensible architecture for custom parsers, trackers, and formatters

📊 **Rich Output** - Beautiful CLI with progress bars, colored output, and detailed reports

## Installation

### From PyPI (coming soon)

```bash
pip install md2jira
```

### From Source

```bash
git clone https://github.com/adriandarian/md2jira.git
cd md2jira
pip install -e ".[dev]"
```

## Quick Start

### 1. Set up environment variables

Create a `.env` file:

```bash
JIRA_URL=https://your-company.atlassian.net
JIRA_EMAIL=your.email@company.com
JIRA_API_TOKEN=your-api-token
```

### 2. Create your markdown epic

```markdown
### ✅ US-001: User Authentication

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Priority** | 🟡 High |
| **Status** | ✅ Done |

#### Description

**As a** user
**I want** to authenticate securely
**So that** my data is protected

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|----|---------| 
| 1 | Create login form | Build the login UI | 2 | ✅ Done |
| 2 | Implement JWT auth | Add JWT token handling | 3 | ✅ Done |
```

### 3. Sync to Jira

```bash
# Preview changes (dry-run)
md2jira --markdown EPIC.md --epic PROJ-123

# Execute sync
md2jira --markdown EPIC.md --epic PROJ-123 --execute

# Sync specific phase only
md2jira --markdown EPIC.md --epic PROJ-123 --execute --phase descriptions
```

## Architecture

md2jira follows a **Clean Architecture** / **Hexagonal Architecture** pattern for maximum flexibility and testability.

```
src/md2jira/
├── core/                     # Pure domain logic (no external deps)
│   ├── domain/               # Entities, value objects, enums
│   │   ├── entities.py       # Epic, UserStory, Subtask, Comment
│   │   ├── value_objects.py  # StoryId, IssueKey, Description
│   │   ├── enums.py          # Status, Priority, IssueType
│   │   └── events.py         # Domain events for audit trail
│   └── ports/                # Abstract interfaces
│       ├── issue_tracker.py  # IssueTrackerPort interface
│       ├── document_parser.py
│       └── document_formatter.py
├── adapters/                 # Infrastructure implementations
│   ├── jira/                 # Jira API adapter
│   │   ├── adapter.py        # IssueTrackerPort implementation
│   │   └── client.py         # Low-level HTTP client
│   ├── parsers/              # Document parsers
│   │   └── markdown.py       # Markdown parser
│   ├── formatters/           # Output formatters
│   │   └── adf.py            # Atlassian Document Format
│   └── config/               # Configuration providers
│       └── environment.py    # Env vars / .env loader
├── application/              # Use cases / orchestration
│   ├── commands/             # Command pattern handlers
│   │   ├── base.py           # Command, CommandResult, CommandBatch
│   │   └── issue_commands.py # UpdateDescription, CreateSubtask, etc.
│   └── sync/                 # Sync orchestrator
│       └── orchestrator.py   # Main sync logic
├── cli/                      # Command line interface
│   ├── app.py                # Entry point, argument parsing
│   └── output.py             # Rich console output
└── plugins/                  # Extension system
    ├── base.py               # Plugin base classes
    ├── hooks.py              # Hook system for extensibility
    └── registry.py           # Plugin discovery and loading
```

### Key Patterns

- **Ports & Adapters**: Core logic depends only on abstract interfaces (ports), making it easy to swap implementations
- **Command Pattern**: All write operations are encapsulated as commands, enabling undo/redo and audit trails
- **Event-Driven**: Domain events provide loose coupling and enable audit logging
- **Plugin System**: Extend functionality without modifying core code

### Adding a New Tracker (e.g., GitHub Issues)

```python
from md2jira.core.ports import IssueTrackerPort

class GitHubAdapter(IssueTrackerPort):
    @property
    def name(self) -> str:
        return "GitHub"
    
    def get_epic_children(self, epic_key: str) -> list[IssueData]:
        # Implement GitHub API calls
        ...
```

### Using Hooks

```python
from md2jira.plugins import HookPoint, get_registry

hook_manager = get_registry().hook_manager

@hook_manager.hook(HookPoint.BEFORE_SYNC)
def log_sync_start(ctx):
    print(f"Starting sync for epic: {ctx.data['epic_key']}")

@hook_manager.hook(HookPoint.ON_ERROR)
def handle_errors(ctx):
    send_slack_notification(ctx.error)
```

## CLI Reference

```bash
md2jira --help
```

### Common Options

| Option | Description |
|--------|-------------|
| `--markdown, -m` | Path to markdown file (required) |
| `--epic, -e` | Jira epic key (required) |
| `--execute, -x` | Execute changes (default: dry-run) |
| `--no-confirm` | Skip confirmation prompts |
| `--phase` | Run specific phase: `all`, `descriptions`, `subtasks`, `comments`, `statuses` |
| `--story` | Filter to specific story ID |
| `--verbose, -v` | Verbose output |
| `--export` | Export results to JSON |
| `--validate` | Validate markdown only |

### Examples

```bash
# Validate markdown format
md2jira -m EPIC.md -e PROJ-123 --validate

# Preview all changes
md2jira -m EPIC.md -e PROJ-123 -v

# Sync descriptions only
md2jira -m EPIC.md -e PROJ-123 -x --phase descriptions

# Full sync without prompts
md2jira -m EPIC.md -e PROJ-123 -x --no-confirm

# Export results
md2jira -m EPIC.md -e PROJ-123 -x --export sync-results.json
```

## Documentation

- [Markdown Schema](docs/SCHEMA.md) - Detailed specification of expected markdown format
- [Template](docs/TEMPLATE.md) - Blank template to get started
- [Example](docs/EXAMPLE.md) - Full working example
- [AI Prompt](docs/AI_PROMPT.md) - Prompt for AI agents to generate content
- [Configuration](docs/CONFIG.md) - Configuration file format and options
- [Exit Codes](docs/EXIT_CODES.md) - CLI exit codes for scripting and CI/CD
- [Shell Completions](docs/COMPLETIONS.md) - Tab completion for Bash, Zsh, Fish

## Development

### Setup

```bash
# Clone and install
git clone https://github.com/adriandarian/md2jira.git
cd md2jira
pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=src/md2jira

# Type checking
mypy src/

# Linting
ruff check src/ tests/

# Formatting
black src/ tests/
```

### Project Structure

```
md2jira/
├── src/md2jira/      # Source code
├── tests/            # Test suite
├── docs/             # Documentation
├── pyproject.toml    # Project config
└── README.md
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please read our contributing guidelines before submitting PRs.

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Run the test suite
6. Submit a PR

---

<div align="center">
Made with ❤️ by <a href="https://github.com/adriandarian">Adrian Darian</a>
</div>
