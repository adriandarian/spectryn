# Spectra Sublime Text Package

Sublime Text package for Spectra markdown user story files with LSP support.

## Features

- **LSP Integration** - Full language server support via spectryn-lsp
- **Syntax Highlighting** - Enhanced markdown highlighting for Spectra
- **Completions** - Auto-complete status, priority, and tracker IDs
- **Diagnostics** - Real-time validation errors in the gutter
- **Go to Definition** - Navigate to story definitions
- **Hover** - View tracker issue details
- **Build System** - Validate and sync commands

## Installation

### 1. Install Dependencies

```bash
# Install Spectra LSP
pip install spectryn-lsp

# Install Spectra CLI
pip install spectryn
```

### 2. Install LSP Package

Install the [LSP](https://packagecontrol.io/packages/LSP) package via Package Control:

1. Open Command Palette (`Cmd+Shift+P` / `Ctrl+Shift+P`)
2. Type "Package Control: Install Package"
3. Search for "LSP" and install it

### 3. Install Spectra Package

#### Via Package Control (Recommended)

1. Open Command Palette
2. Type "Package Control: Install Package"
3. Search for "Spectra" and install it

#### Manual Installation

1. Clone this repository to your Sublime Text packages directory:
   ```bash
   # macOS
   cd ~/Library/Application\ Support/Sublime\ Text/Packages
   git clone https://github.com/spectryn/spectryn-sublime Spectra

   # Linux
   cd ~/.config/sublime-text/Packages
   git clone https://github.com/spectryn/spectryn-sublime Spectra

   # Windows
   cd %APPDATA%\Sublime Text\Packages
   git clone https://github.com/spectryn/spectryn-sublime Spectra
   ```

2. Or copy the files from `integrations/sublime/` to your packages directory.

## Configuration

### LSP Settings

Open **Preferences → Package Settings → LSP → Settings** and add:

```json
{
  "clients": {
    "spectryn": {
      "enabled": true,
      "command": ["spectryn-lsp", "--stdio"],
      "selector": "source.spectryn, text.html.markdown",
      "initializationOptions": {
        "spectryn": {
          "tracker": {
            "type": "jira",
            "url": "https://your-org.atlassian.net",
            "projectKey": "PROJ"
          },
          "validation": {
            "validateOnSave": true,
            "validateOnType": true
          },
          "diagnostics": {
            "showWarnings": true,
            "showHints": true
          }
        }
      }
    }
  }
}
```

### Package Settings

Open **Preferences → Package Settings → Spectra → Settings** and customize:

```json
{
  // Path to spectryn CLI
  "spectryn_cli_path": "spectryn",

  // Validate on save
  "validate_on_save": true,

  // Show status in status bar
  "show_status": true,

  // Auto-format on save
  "format_on_save": false
}
```

## Key Bindings

Default key bindings (can be customized in Key Bindings settings):

| Key | Action |
|-----|--------|
| `Ctrl+Shift+V` | Validate file |
| `Ctrl+Shift+S` | Sync to tracker |
| `Ctrl+Shift+P` | Preview changes (plan) |
| `F12` | Go to definition (LSP) |
| `Ctrl+Space` | Show completions |
| `Ctrl+Shift+O` | Open story in tracker |

### Custom Key Bindings

Add to your **Preferences → Key Bindings**:

```json
[
  { "keys": ["ctrl+shift+v"], "command": "spectryn_validate", "context": [{ "key": "selector", "operand": "source.spectryn, text.html.markdown" }] },
  { "keys": ["ctrl+shift+s"], "command": "spectryn_sync", "context": [{ "key": "selector", "operand": "source.spectryn, text.html.markdown" }] },
  { "keys": ["ctrl+shift+p"], "command": "spectryn_plan", "context": [{ "key": "selector", "operand": "source.spectryn, text.html.markdown" }] },
  { "keys": ["ctrl+shift+o"], "command": "spectryn_open_in_tracker", "context": [{ "key": "selector", "operand": "source.spectryn, text.html.markdown" }] }
]
```

## Commands

Access via Command Palette (`Cmd+Shift+P` / `Ctrl+Shift+P`):

| Command | Description |
|---------|-------------|
| Spectra: Validate | Validate current file |
| Spectra: Sync | Sync to issue tracker |
| Spectra: Plan | Preview changes before sync |
| Spectra: Diff | Show diff with tracker |
| Spectra: Import | Import from tracker |
| Spectra: Export | Export to HTML/PDF/JSON |
| Spectra: Stats | Show file statistics |
| Spectra: Doctor | Run diagnostics |
| Spectra: Open in Tracker | Open story in browser |
| Spectra: New Story | Insert story template |
| Spectra: New Epic | Insert epic template |

## Build System

The package includes a build system for validation:

1. Open a `.spectryn.md` or `.md` file
2. Press `Cmd+B` / `Ctrl+B` to validate
3. Or select **Tools → Build System → Spectra**

## Snippets

Type these triggers and press Tab:

| Trigger | Expands To |
|---------|------------|
| `epic` | Epic template |
| `story` | Story template with metadata |
| `task` | Subtask template |
| `ac` | Acceptance criteria section |
| `status` | Status field |
| `meta` | All metadata fields |

## File Structure

```
sublime/
├── README.md
├── Spectra.sublime-settings      # Package settings
├── Default.sublime-keymap        # Key bindings
├── Spectra.sublime-syntax        # Syntax definition
├── Spectra.sublime-build         # Build system
├── Spectra.sublime-commands      # Command palette entries
├── Spectra.sublime-completions   # Completions
├── snippets/
│   ├── epic.sublime-snippet
│   ├── story.sublime-snippet
│   ├── subtask.sublime-snippet
│   └── ...
└── spectryn_commands.py           # Plugin commands
```

## Troubleshooting

### LSP Not Working

1. Check LSP package is installed
2. Verify spectryn-lsp is in PATH:
   ```bash
   which spectryn-lsp
   ```
3. Check LSP logs: **View → Show Console**
4. Restart Sublime Text

### Syntax Highlighting Not Working

1. Ensure file has `.spectryn.md` extension
2. Or set syntax manually: **View → Syntax → Spectra**

### Commands Not Found

Verify spectryn CLI is installed:
```bash
spectryn --version
```

## License

MIT - See [LICENSE](../../LICENSE)
