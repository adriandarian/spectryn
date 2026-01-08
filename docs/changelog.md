# Changelog

All notable changes to spectryn will be documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- VitePress documentation website

## [1.0.0] - 2025-01-XX

### Added
- **Core Features**
  - Full epic sync from markdown to Jira
  - Smart fuzzy matching between markdown stories and Jira issues
  - Description sync with As a/I want/So that format
  - Subtask creation and synchronization
  - Status transition support
  - Comment sync

- **CLI**
  - Rich terminal output with progress bars
  - Dry-run mode (default)
  - Interactive mode (`--interactive`)
  - Phase-specific sync (`--phase`)
  - Story filtering (`--story`)
  - JSON output mode (`--output json`)
  - Export to file (`--export`)
  - Shell completions for Bash, Zsh, Fish

- **Configuration**
  - YAML config file support (`.spectryn.yaml`)
  - TOML config file support (`.spectryn.toml`)
  - pyproject.toml support (`[tool.spectryn]`)
  - Environment variable configuration
  - .env file loading

- **Safety & Recovery**
  - Automatic backup before sync
  - Backup listing (`--list-backups`)
  - Diff view (`--diff-backup`, `--diff-latest`)
  - Rollback capability (`--rollback`)
  - Restore from backup (`--restore-backup`)

- **Resilience**
  - Retry logic with exponential backoff
  - Rate limiting support
  - Connection pooling
  - Configurable timeouts
  - Graceful degradation on partial failures

- **Observability**
  - Structured logging (`--log-format json`)
  - Log file output (`--log-file`)
  - Audit trail export (`--audit-trail`)
  - Exit codes for scripting

- **Plugin System**
  - Hook points for extensibility
  - Custom adapter support
  - Custom parser support

- **Deployment**
  - Docker image
  - Docker Compose example
  - Homebrew formula
  - Chocolatey package
  - Linux packages (RPM, DEB)

### Architecture
- Clean Architecture / Hexagonal Architecture
- Command pattern for undo-capable operations
- Domain events for audit logging
- Ports & Adapters for testability

---

## Version History

For the complete version history, see the [CHANGELOG.md](https://github.com/adriandarian/spectryn/blob/main/CHANGELOG.md) in the repository.

