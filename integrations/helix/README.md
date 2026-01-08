# Spectra Helix Configuration

Helix editor configuration for Spectra markdown files with LSP support.

## Features

- **LSP Integration** - Full language server support via spectryn-lsp
- **Syntax Highlighting** - Enhanced markdown highlighting for Spectra
- **Completions** - Auto-complete status, priority, and tracker IDs
- **Diagnostics** - Real-time validation errors
- **Go to Definition** - Navigate to story definitions
- **Hover** - View tracker issue details

## Installation

### 1. Install Spectra LSP

```bash
pip install spectryn-lsp
```

### 2. Configure Helix

Add the following to your Helix configuration:

**`~/.config/helix/languages.toml`**:

```toml
# Add Spectra language server
[language-server.spectryn-lsp]
command = "spectryn-lsp"
args = ["--stdio"]

# Configure for Spectra markdown files
[[language]]
name = "spectryn"
scope = "source.spectryn"
injection-regex = "spectryn"
file-types = [{ glob = "*.spectryn.md" }]
roots = ["spectryn.yaml", "spectryn.toml", ".spectryn"]
language-servers = ["spectryn-lsp"]
indent = { tab-width = 2, unit = "  " }
grammar = "markdown"

# Also enable for regular markdown files
[[language]]
name = "markdown"
language-servers = ["marksman", "spectryn-lsp"]
```

### 3. Copy Query Files (Optional)

For enhanced highlighting, copy the query files:

```bash
mkdir -p ~/.config/helix/runtime/queries/spectryn
cp integrations/helix/queries/* ~/.config/helix/runtime/queries/spectryn/
```

## Key Bindings

The default Helix LSP bindings work automatically:

| Action | Key |
|--------|-----|
| Go to definition | `gd` |
| Hover documentation | `K` |
| Code actions | `<space>a` |
| Show diagnostics | `<space>d` |
| Rename symbol | `<space>r` |
| Format document | `<space>f` |
| Completion | `<C-x><C-o>` or auto |

### Custom Key Bindings

Add to `~/.config/helix/config.toml`:

```toml
[keys.normal]
"<space>sv" = ":sh spectryn --validate --markdown %"
"<space>ss" = ":sh spectryn --sync --markdown %"
"<space>sp" = ":sh spectryn plan --markdown %"

[keys.normal.space.s]
v = ":sh spectryn --validate --markdown %"
s = ":sh spectryn --sync --markdown %"
p = ":sh spectryn plan --markdown %"
```

## LSP Settings

The LSP server can be configured with initialization options:

```toml
[language-server.spectryn-lsp]
command = "spectryn-lsp"
args = ["--stdio"]

[language-server.spectryn-lsp.config]
spectryn.tracker.type = "jira"
spectryn.tracker.url = "https://your-org.atlassian.net"
spectryn.tracker.projectKey = "PROJ"
spectryn.validation.validateOnSave = true
spectryn.validation.validateOnType = true
spectryn.diagnostics.showWarnings = true
spectryn.diagnostics.showHints = true
```

## Verification

After configuration, verify the setup:

1. Open a `.spectryn.md` or `.md` file
2. Check `:log` for LSP connection messages
3. Type `**Status**: ` and check for completions
4. Press `K` on a story header for hover info
5. Check diagnostics with `<space>d`

## Troubleshooting

### LSP Not Starting

1. Verify `spectryn-lsp` is in PATH:
   ```bash
   which spectryn-lsp
   ```

2. Test the server directly:
   ```bash
   spectryn-lsp --stdio
   ```

3. Check Helix logs:
   ```
   :log
   ```

### No Completions

Ensure the cursor is at the right position (after `**Status**: ` etc.)

### Diagnostics Not Showing

Check that `spectryn` CLI is installed:
```bash
spectryn --version
```

## File Structure

```
helix/
├── README.md
├── languages.toml          # Language configuration
├── config.toml             # Editor configuration
└── queries/
    └── spectryn/
        ├── highlights.scm  # Syntax highlighting
        ├── injections.scm  # Language injections
        └── textobjects.scm # Text object definitions
```

## License

MIT - See [LICENSE](../../LICENSE)
