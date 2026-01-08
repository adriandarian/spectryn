# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Nothing yet

---

## [1.0.0] - 2024-12-14

🎉 **Initial release of Spectra** - A production-grade CLI tool for synchronizing markdown specifications with issue trackers.

### Core Features

#### Multi-Platform Issue Tracker Support
- **Jira** - Full support including Jira Cloud and Jira Server
- **GitHub Issues** - Sync to GitHub Issues and Projects
- **Azure DevOps** - Work items and boards integration
- **Linear** - Modern issue tracking sync
- **Confluence** - Documentation page sync

#### Multiple Input Formats
- **Markdown** - Native markdown parsing with structured format
- **YAML** - YAML specification files
- **Notion** - Notion export parsing

#### Sync Capabilities
- Sync epics, stories, tasks, and subtasks
- Story points extraction and sync
- Priority and status mapping
- Description sync with rich formatting
- Acceptance criteria parsing
- Comments sync
- Labels and components

### Architecture

#### Hexagonal/Clean Architecture
- **Core Domain**: Pure business logic with no external dependencies
  - Domain entities: `Epic`, `Story`, `Task`, `Subtask`, `Comment`
  - Value objects: `IssueKey`, `StoryPoints`, `Description`, `Priority`, `Status`
  - Domain events: `IssueCreated`, `IssueUpdated`, `IssueSynced`, etc.
- **Ports**: Abstract interfaces for all external dependencies
  - `IssueTrackerPort` - Issue tracker abstraction
  - `DocumentParserPort` - Document parsing abstraction
  - `DocumentFormatterPort` - Output formatting abstraction
  - `ConfigProviderPort` - Configuration abstraction
- **Adapters**: Concrete implementations
  - Tracker adapters for each platform
  - Markdown, YAML, Notion parsers
  - ADF (Atlassian Document Format) formatter
  - Environment and file-based config

#### Command Pattern
- All write operations encapsulated as commands
- Full undo/redo capability
- Audit trail for all operations
- Batch command execution

#### Plugin System
- Hook-based extensibility
- Plugin registry with entry point discovery
- Lifecycle hooks: `BEFORE_SYNC`, `AFTER_SYNC`, `ON_ERROR`, `ON_CONFLICT`, etc.
- Custom parser, tracker, and formatter plugins

### CLI Features

#### Core Commands
- `spectryn sync` - Sync markdown to issue tracker
- `spectryn validate` - Validate markdown format
- `spectryn init` - Initialize configuration
- `spectryn generate` - Generate markdown from tracker
- `spectryn health` - Check tracker connectivity

#### Execution Modes
- `--dry-run` - Preview changes without executing (default)
- `--execute` / `-x` - Execute changes
- `--interactive` / `-i` - Step-by-step guided mode
- `--watch` - Auto-sync on file changes
- `--schedule` - Cron-like scheduled sync

#### Sync Options
- `--phase` - Sync specific phases: `descriptions`, `subtasks`, `comments`, `statuses`, `all`
- `--story` - Filter to specific story
- `--incremental` - Only sync changed items
- `--multi-epic` - Sync multiple epics from one file
- `--epic-filter` - Filter epics in multi-epic mode

#### Bidirectional Sync
- `--pull` - Pull from tracker to markdown
- `--check-conflicts` - Detect sync conflicts
- `--conflict-strategy` - Resolution: `local`, `remote`, `merge`, `ask`
- `--sync-links` - Cross-project issue linking

#### Backup & Recovery
- `--backup` / `--no-backup` - Control auto-backup
- `--list-backups` - View available backups
- `--restore-backup BACKUP_ID` - Restore previous state
- `--diff-backup BACKUP_ID` - Show before/after diff
- `--rollback` - Undo last sync operation

#### Output Options
- `--verbose` / `-v` - Verbose output
- `--quiet` / `-q` - Minimal output for CI
- `--output json` - JSON output for automation
- `--export PATH` - Export results to file
- `--log-file PATH` - Write logs to file
- `--log-format json` - Structured JSON logging
- `--audit-trail PATH` - Export operation audit trail

#### Shell Completions
- Bash completion (`spectryn --completions bash`)
- Zsh completion (`spectryn --completions zsh`)
- Fish completion (`spectryn --completions fish`)

### Infrastructure

#### Async & Performance
- Async HTTP client with connection pooling
- Parallel API calls for batch operations
- Rate limiting with token bucket algorithm
- Configurable concurrency limits
- Request queuing and throttling

#### Caching
- Response caching for read operations
- Memory and file-based cache backends
- Configurable TTL and cache invalidation
- Cache key builder for consistent keys

#### Resilience
- Exponential backoff retry logic
- Configurable timeout handling
- Graceful degradation on partial failures
- Circuit breaker pattern

#### Observability
- OpenTelemetry integration
- Prometheus metrics export
- Structured logging with correlation IDs
- Health check endpoints

### Configuration

#### Config Sources (in order of precedence)
1. CLI arguments
2. Environment variables
3. `.env` file
4. Config file (`.spectryn.yaml`, `.spectryn.toml`, `pyproject.toml [tool.spectryn]`)

#### Environment Variables
- `JIRA_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`
- `GITHUB_TOKEN`, `GITHUB_OWNER`, `GITHUB_REPO`
- `AZURE_DEVOPS_URL`, `AZURE_DEVOPS_TOKEN`
- `LINEAR_API_KEY`
- `SPECTRA_*` prefix for all settings

### Editor Integrations

#### VS Code Extension
- CodeLens for inline actions
- Diagnostics for validation errors
- Tree view for epic structure
- Decorations for sync status
- Commands for sync operations

#### Neovim Plugin
- Lua-based plugin
- Telescope integration for epic search
- Commands for sync and validation
- Status line integration

#### GitHub Action
- Sync on push/PR
- Multi-epic support
- Dry-run for PRs, execute on merge
- Result comments on PRs

#### Terraform Provider
- `spectryn_issue` resource
- `spectryn_epic` data source
- `spectryn_project` data source
- Infrastructure-as-code for issue management

### Distribution

#### Package Managers
- **PyPI**: `pip install spectryn`
- **Homebrew**: `brew install adriandarian/spectryn/spectryn`
- **Chocolatey**: `choco install spectryn`
- **pipx**: `pipx install spectryn`

#### Containers
- Docker Hub: `adrianthehactus/spectryn`
- GitHub Container Registry: `ghcr.io/adriandarian/spectryn`
- Docker Compose example included

#### Linux Packages
- Debian package (`.deb`)
- RPM package (`.rpm`)
- Universal installer script

### Documentation

- **VitePress-powered documentation site**
- Getting Started guide
- Installation options
- Configuration reference
- CLI reference with examples
- Architecture overview
- Plugin development guide
- Tutorials:
  - First sync walkthrough
  - Interactive mode guide
  - Backup and restore
  - CI/CD setup
- Cookbook recipes:
  - Sprint planning
  - Multi-team workflows
  - Migration strategies
  - Bug triage
  - Release planning
  - Documentation-driven development
  - AI-assisted spec writing

### Developer Experience

- Type-safe Python with `py.typed` marker
- Complete type annotations
- Comprehensive docstrings
- Pre-commit hooks configuration
- EditorConfig for consistent formatting
- GitHub issue and PR templates
- CODEOWNERS for review assignment

### Testing

- Unit tests with pytest
- Integration tests with mocked APIs
- Property-based tests with Hypothesis
- Mutation testing with mutmut
- Performance benchmarks
- 70%+ code coverage (target: 80%+)

---

## License

MIT License - see [LICENSE](LICENSE) for details.

---

[Unreleased]: https://github.com/adriandarian/spectryn/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/adriandarian/spectryn/releases/tag/v1.0.0
