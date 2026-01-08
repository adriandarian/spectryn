# Spectra Emacs Integration

Emacs configuration for Spectra markdown files with LSP support via lsp-mode or eglot.

## Features

- **LSP Integration** - Full language server support via spectryn-lsp
- **Syntax Highlighting** - Enhanced markdown highlighting for Spectra
- **Completions** - Auto-complete via company-mode
- **Diagnostics** - Real-time validation via flycheck/flymake
- **Go to Definition** - Navigate to story definitions
- **Hover** - View tracker issue details
- **Code Actions** - Quick fixes and story creation
- **Custom Commands** - Validate, sync, and preview changes

## Installation

### 1. Install Spectra LSP

```bash
pip install spectryn-lsp
```

### 2. Choose Your LSP Client

#### Option A: lsp-mode (Recommended)

Add to your Emacs config (`~/.emacs.d/init.el` or `~/.emacs`):

```elisp
;; Install required packages
(use-package lsp-mode
  :ensure t
  :hook ((markdown-mode . lsp-deferred))
  :commands (lsp lsp-deferred))

(use-package lsp-ui
  :ensure t
  :commands lsp-ui-mode)

;; Load Spectra configuration
(load "~/.emacs.d/spectryn/spectryn-lsp.el")
```

#### Option B: eglot (Built-in from Emacs 29)

```elisp
(use-package eglot
  :hook ((markdown-mode . eglot-ensure)))

;; Load Spectra configuration
(load "~/.emacs.d/spectryn/spectryn-eglot.el")
```

### 3. Copy Configuration Files

```bash
mkdir -p ~/.emacs.d/spectryn
cp integrations/emacs/*.el ~/.emacs.d/spectryn/
```

## Configuration

### lsp-mode Settings

The `spectryn-lsp.el` file provides full configuration. Key settings:

```elisp
;; Customize these in your init.el
(setq spectryn-tracker-type "jira")
(setq spectryn-tracker-url "https://your-org.atlassian.net")
(setq spectryn-project-key "PROJ")
```

### eglot Settings

```elisp
;; Customize in your init.el
(setq spectryn-eglot-server-args '("--stdio"))
```

## Key Bindings

Default key bindings (with `C-c s` prefix):

| Key | Action |
|-----|--------|
| `C-c s v` | Validate current file |
| `C-c s s` | Sync to tracker |
| `C-c s p` | Preview changes (plan) |
| `C-c s d` | Show diff with tracker |
| `C-c s i` | Import from tracker |
| `C-c s o` | Open story in browser |

LSP bindings (lsp-mode):

| Key | Action |
|-----|--------|
| `s-l g d` | Go to definition |
| `s-l g r` | Find references |
| `s-l r r` | Rename |
| `s-l a a` | Code actions |
| `K` or `s-l h h` | Hover documentation |

## Hydra Menu

If you have `hydra` installed, use `C-c s h` to open the Spectra hydra menu:

```
Spectra Commands
────────────────
_v_: Validate    _s_: Sync       _p_: Plan
_d_: Diff        _i_: Import     _o_: Open in Tracker
_e_: Export      _r_: Report     _q_: Quit
```

## Major Mode

The package provides `spectryn-mode`, a derived mode from `markdown-mode`:

```elisp
;; Enable for specific files
(add-to-list 'auto-mode-alist '("\\.spectryn\\.md\\'" . spectryn-mode))
(add-to-list 'auto-mode-alist '("user-stories\\.md\\'" . spectryn-mode))
(add-to-list 'auto-mode-alist '("backlog\\.md\\'" . spectryn-mode))
```

## Org-mode Integration

For org-mode users, see `spectryn-org.el` for integration that allows:

- Export org files to Spectra markdown format
- Import Spectra markdown to org files
- Sync org headlines to trackers

## Troubleshooting

### LSP Not Starting

1. Check spectryn-lsp is installed:
   ```bash
   which spectryn-lsp
   spectryn-lsp --version
   ```

2. Check lsp-mode logs:
   ```
   M-x lsp-workspace-show-log
   ```

3. Verify executable path:
   ```elisp
   (executable-find "spectryn-lsp")
   ```

### No Completions

Ensure company-mode is enabled:
```elisp
(company-mode 1)
```

### Diagnostics Not Showing

Check flycheck/flymake is enabled and lsp checker is active:
```elisp
M-x flycheck-verify-setup
```

## File Structure

```
emacs/
├── README.md
├── spectryn-lsp.el      # lsp-mode configuration
├── spectryn-eglot.el    # eglot configuration
├── spectryn-mode.el     # Major mode definition
├── spectryn-commands.el # Interactive commands
└── spectryn-org.el      # Org-mode integration
```

## License

MIT - See [LICENSE](../../LICENSE)
