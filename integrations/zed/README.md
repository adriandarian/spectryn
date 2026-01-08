# Spectra Zed Extension

Zed editor extension for Spectra markdown-based user story management.

## Features

- **LSP Integration** - Full language server support via spectryn-lsp
- **Syntax Highlighting** - Custom highlighting for Spectra markdown
- **Tree-sitter Grammar** - Proper parsing of Spectra documents
- **Completions** - Auto-complete status, priority, and tracker IDs
- **Diagnostics** - Real-time validation
- **Go to Definition** - Navigate to story definitions

## Installation

### From Extension Gallery

1. Open Zed
2. Open the Extensions panel (`Cmd+Shift+X` on macOS, `Ctrl+Shift+X` on Linux)
3. Search for "Spectra"
4. Click Install

### Manual Installation

1. Clone this repository to `~/.config/zed/extensions/spectryn`
2. Restart Zed

## Requirements

- Zed 0.130.0 or later
- Spectra LSP server (`pip install spectryn-lsp`)

## Configuration

Add to your Zed settings (`~/.config/zed/settings.json`):

```json
{
  "lsp": {
    "spectryn": {
      "binary": {
        "path": "spectryn-lsp",
        "arguments": ["--stdio"]
      },
      "initialization_options": {
        "spectryn": {
          "tracker": {
            "type": "jira",
            "url": "https://your-org.atlassian.net",
            "projectKey": "PROJ"
          },
          "validation": {
            "validateOnSave": true,
            "validateOnType": true
          }
        }
      }
    }
  }
}
```

## Key Bindings

Add to your keymap (`~/.config/zed/keymap.json`):

```json
[
  {
    "context": "Editor && extension == md",
    "bindings": {
      "ctrl-shift-v": "spectryn::validate",
      "ctrl-shift-s": "spectryn::sync"
    }
  }
]
```

## Development

### Building

```bash
cd integrations/zed
cargo build
```

### Testing

```bash
cargo test
```

### Publishing

```bash
# Package the extension
zed-ext package

# Publish to extension gallery
zed-ext publish
```

## File Structure

```
zed/
├── extension.toml          # Extension manifest
├── languages/
│   └── spectryn/
│       ├── config.toml     # Language configuration
│       ├── highlights.scm  # Syntax highlighting
│       └── injections.scm  # Language injections
├── src/
│   └── lib.rs              # Extension code
└── Cargo.toml
```

## License

MIT - See [LICENSE](../../LICENSE)
