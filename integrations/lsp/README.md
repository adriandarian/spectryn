# Spectra Language Server

A Language Server Protocol (LSP) implementation for Spectra markdown files, providing intelligent IDE support for user story documents.

## Features

- **Diagnostics** - Real-time validation errors and warnings
- **Hover** - Show tracker issue details on hover
- **Go to Definition** - Navigate to epic/story definitions
- **Code Actions** - Quick fixes and story creation
- **Document Symbols** - Outline view of epics and stories
- **Completions** - Auto-complete status, priority, and tracker IDs
- **Document Links** - Clickable links to trackers

## Installation

### From PyPI

```bash
pip install spectryn-lsp
```

### From Source

```bash
cd integrations/lsp
pip install -e .
```

## Usage

### Start the Server

```bash
# TCP mode (default)
spectryn-lsp --tcp --port 2087

# Stdio mode (for editor integration)
spectryn-lsp --stdio
```

### Editor Configuration

See the editor-specific guides below:

- [VS Code](../vscode/README.md) - Built-in support
- [Neovim](../neovim/README.md) - Native LSP
- [Emacs](../emacs/README.md) - lsp-mode/eglot
- [Helix](../helix/README.md) - Built-in LSP
- [Sublime Text](../sublime/README.md) - LSP package
- [Zed](../zed/README.md) - Native LSP

## Configuration

The LSP server reads configuration from:

1. `spectryn.yaml` or `spectryn.toml` in the workspace
2. Editor-specific settings passed via `workspace/didChangeConfiguration`

### Available Settings

```json
{
  "spectryn": {
    "validation": {
      "enabled": true,
      "validateOnSave": true,
      "validateOnType": true
    },
    "tracker": {
      "type": "jira",
      "url": "https://your-org.atlassian.net",
      "projectKey": "PROJ"
    },
    "diagnostics": {
      "showWarnings": true,
      "showHints": true
    },
    "hover": {
      "showTrackerDetails": true,
      "cacheTimeout": 60
    }
  }
}
```

## Supported File Types

- `*.md` - Markdown files with Spectra headers
- `*.spectryn.md` - Explicit Spectra files

## Protocol Support

The server implements LSP 3.17 and supports:

| Feature | Method | Status |
|---------|--------|--------|
| Initialize | `initialize` | ✅ |
| Text Sync | `textDocument/didOpen`, `didChange`, `didSave` | ✅ |
| Diagnostics | `textDocument/publishDiagnostics` | ✅ |
| Hover | `textDocument/hover` | ✅ |
| Completion | `textDocument/completion` | ✅ |
| Go to Definition | `textDocument/definition` | ✅ |
| Document Symbols | `textDocument/documentSymbol` | ✅ |
| Code Actions | `textDocument/codeAction` | ✅ |
| Document Links | `textDocument/documentLink` | ✅ |
| Formatting | `textDocument/formatting` | ✅ |
| Configuration | `workspace/didChangeConfiguration` | ✅ |

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Type check
mypy src/spectryn_lsp
```

## License

MIT - See [LICENSE](../../LICENSE)
