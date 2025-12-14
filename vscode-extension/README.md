# md2jira for VS Code

Sync markdown documentation with Jira directly from VS Code.

## ✨ Features

### 🔍 Validation
- Validate markdown syntax on save
- See errors in the Problems panel
- Quick fixes and suggestions

### 🔄 Sync
- Preview changes with dry-run mode
- Execute sync with confirmation
- View results in a panel

### 📊 Dashboard
- View sync status at a glance
- Track story counts and points
- Monitor sync history

### 🎨 Editor Integration
- **Story highlighting** - Story IDs are highlighted in the editor
- **CodeLens** - Action buttons above stories (Copy ID, Open in Jira)
- **Tree View** - Browse stories in the Explorer sidebar
- **Status Bar** - Story count and epic key display

### ⌨️ Commands

| Command | Description | Keybinding |
|---------|-------------|------------|
| `md2jira: Validate` | Validate markdown | `Ctrl+Shift+V` |
| `md2jira: Sync` | Sync (dry-run) | `Ctrl+Shift+S` |
| `md2jira: Sync Execute` | Sync (execute) | - |
| `md2jira: Dashboard` | Show dashboard | - |
| `md2jira: Go to Story` | Jump to story | `Ctrl+Shift+G` |
| `md2jira: Setup Wizard` | Run init | - |

## 📦 Installation

### From VSIX
1. Download the `.vsix` file
2. Run `code --install-extension md2jira-1.0.0.vsix`

### From Source
```bash
cd vscode-extension
npm install
npm run compile
# Press F5 in VS Code to launch Extension Development Host
```

## ⚙️ Configuration

Open Settings (`Ctrl+,`) and search for "md2jira":

| Setting | Default | Description |
|---------|---------|-------------|
| `md2jira.executable` | `md2jira` | Path to md2jira CLI |
| `md2jira.jiraUrl` | - | Jira instance URL |
| `md2jira.autoValidate` | `true` | Validate on save |
| `md2jira.showStoryDecorations` | `true` | Highlight story IDs |
| `md2jira.showCodeLens` | `true` | Show action buttons |
| `md2jira.showStatusBar` | `true` | Show status bar item |

## 🎯 Usage

### Quick Start

1. Open a markdown file with stories
2. The extension auto-detects epic keys from the content
3. Use `Ctrl+Shift+V` to validate
4. Use `Ctrl+Shift+S` to preview sync changes

### Story Format

The extension recognizes stories in this format:

```markdown
# 🚀 PROJ-100: Epic Title

### 📋 US-001: Story Title

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Status** | To Do |

**As a** user
**I want** to do something
**So that** I get value
```

### Status Indicators

| Emoji | Status |
|-------|--------|
| 📋 | Planned/To Do |
| ✅ | Done |
| 🔄 | In Progress |
| ⏸️ | Blocked |

## 🔧 Requirements

- VS Code 1.80.0 or higher
- md2jira CLI installed and in PATH

## 📝 Release Notes

### 1.0.0

- Initial release
- Validation with diagnostics
- Sync with dry-run and execute modes
- Dashboard view
- CodeLens for stories
- Tree view in Explorer
- Status bar integration
- Story highlighting

## 📄 License

MIT License - see [LICENSE](../LICENSE)

