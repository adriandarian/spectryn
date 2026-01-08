# spectryn

<div align="center">

[![CI](https://github.com/adriandarian/spectryn/actions/workflows/pr.yml/badge.svg)](https://github.com/adriandarian/spectryn/actions/workflows/pr.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

**The Universal Bridge between Product Specifications and Issue Trackers**

*Synchronize Markdown, YAML, JSON, and Notion specs with Jira, GitHub, Linear, Azure DevOps, Asana, GitLab, Trello, Monday.com, Shortcut, ClickUp, Bitbucket, YouTrack, and Confluence*

[Core Features](#-core-features) •
[Installation](#-installation) •
[Quick Start](#-quick-start) •
[Supported Platforms](#-supported-platforms) •
[AI-Assisted Sync](#-ai-assisted-sync) •
[Architecture](#-architecture)

</div>

---

## 🚀 Overview

**spectryn** is a production-grade CLI tool designed to eliminate the gap between product documentation and issue tracking. It allows teams to maintain their product specifications as "Docs-as-Code" while keeping project management tools perfectly in sync.

Whether you write stories in Markdown, manage roadmaps in YAML, or organize features in Notion, **spectryn** provides a unified command-line interface to synchronize them across multiple enterprise trackers.

---

## ✨ Core Features

- 🔄 **Universal Sync** - Multi-platform support for Jira, GitHub, Linear, Azure DevOps, Asana, GitLab, Trello, Monday.com, Shortcut, ClickUp, Bitbucket, YouTrack, and Confluence.
- 📝 **Rich Input Formats** - Support for Markdown, YAML, TOML, JSON, CSV, and even Notion.
- 🤖 **AI-Assisted Fixing** - Intelligent validation and auto-fixing of specifications using Claude, Ollama, or Aider.
- 🛡️ **Safe by Design** - Mandatory dry-runs, detailed diff previews, and automatic backups.
- ⚡ **Developer Experience** - Watch mode, shell completions, and TUI dashboards.
- 📊 **Enterprise Readiness** - Audit trails, OpenTelemetry tracing, and conflict detection.

---

## 🛠 Supported Platforms

| **Inputs (Parsers)** | **Outputs (Trackers)** |
|:--- |:--- |
| ✅ **Markdown** (Standard & GFM) | ✅ **Jira** (Cloud & Data Center) |
| ✅ **YAML** | ✅ **GitHub Issues** |
| ✅ **TOML** | ✅ **Linear** |
| ✅ **JSON** | ✅ **Azure DevOps** |
| ✅ **CSV/Excel** | ✅ **Confluence** |
| ✅ **AsciiDoc** | ✅ **Asana** |
| ✅ **Notion** | ✅ **GitLab** |
| ✅ **TOON** | ✅ **Trello** |
|  | ✅ **Monday.com** |
|  | ✅ **Shortcut** |
|  | ✅ **ClickUp** |
|  | ✅ **Bitbucket** |
|  | ✅ **YouTrack** |

---

## 📦 Installation

### Using pipx (Recommended)
```bash
pipx install spectryn
```

### Using Homebrew (macOS/Linux)
```bash
brew tap adriandarian/spectra https://github.com/adriandarian/spectra
brew install spectra
```

### From Source
```bash
git clone https://github.com/adriandarian/spectryn.git
cd spectryn
pip install -e ".[dev]"
```

---

## 🏁 Quick Start

### 1. Configure your environment
Create a `.spectryn.yaml` file in your project root:

```yaml
# Tracker Configuration
jira:
  url: https://your-company.atlassian.net
  email: your-email@company.com
  api_token: your-api-token
  project: PROJ

# Sync Preferences
sync:
  execute: false      # Dry-run by default
  no_confirm: false   # Ask for confirmation
  backup_enabled: true
```

### 2. Validate your specifications
Check your markdown or YAML file for formatting issues:

```bash
spectryn --validate --markdown EPIC.md
```

### 3. Synchronize
Preview the changes (dry-run) and then execute when ready:

```bash
# Preview changes
spectryn --markdown EPIC.md --epic PROJ-123

# Execute sync
spectryn --markdown EPIC.md --epic PROJ-123 --execute
```

---

## 🤖 AI-Assisted Sync

**spectryn** integrates with modern LLMs to help you maintain high-quality specifications.

- **Auto-Fix**: Automatically correct formatting errors in your markdown.
- **Guided Generation**: Generate new epic templates from existing tracker data.
- **Smart Matching**: Fuzzy title matching to connect local specs with remote issues.

```bash
# Detect available AI tools
spectryn --list-ai-tools

# Auto-fix markdown formatting
spectryn --validate --markdown EPIC.md --auto-fix --ai-tool claude
```

---

## 🏗 Architecture

Built on **Clean Architecture** principles, spectryn ensures maximum extensibility through its Ports-and-Adapters (Hexagonal) design.

```text
src/spectryn/
├── core/           # Domain Layer (Entities, Enums, Ports)
├── adapters/       # Infrastructure (Parsers, API Clients, Trackers)
├── application/    # Use Cases (Sync Orchestration, Command Handlers)
└── cli/            # Interface (Commands, TUI, Output Formatting)
```

- **Ports & Adapters**: Core logic remains agnostic of external platforms.
- **Command Pattern**: Every write operation is recorded for auditability and rollback.
- **Domain-Driven**: Rich entities like `UserStory` and `Epic` encapsulate business rules.

---

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details on our development workflow and standards.

```bash
# Run quality checks before submitting
ruff format src tests && ruff check src tests --fix && mypy src/spectryn && pytest
```

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

<div align="center">
Made with ❤️ by <a href="https://github.com/adriandarian">Adrian Darian</a>
</div>
