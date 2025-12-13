# Shell Completions

md2jira provides shell completion scripts for Bash, Zsh, and Fish shells. These enable tab-completion for commands, options, and file paths.

## Quick Setup

### Dynamic Generation (Recommended)

The easiest way to enable completions is to evaluate them dynamically:

**Bash** - Add to `~/.bashrc`:
```bash
eval "$(md2jira --completions bash)"
```

**Zsh** - Add to `~/.zshrc`:
```bash
eval "$(md2jira --completions zsh)"
```

**Fish** - Add to `~/.config/fish/config.fish`:
```fish
md2jira --completions fish | source
```

Then restart your shell or source the config file.

## Manual Installation

### Bash

**Option 1: User-level installation**
```bash
mkdir -p ~/.local/share/bash-completion/completions
md2jira --completions bash > ~/.local/share/bash-completion/completions/md2jira
```

**Option 2: System-wide installation (requires sudo)**
```bash
sudo md2jira --completions bash > /etc/bash_completion.d/md2jira
```

**Option 3: Copy from package**
```bash
cp /path/to/md2jira/completions/md2jira.bash ~/.local/share/bash-completion/completions/md2jira
```

### Zsh

**Option 1: User-level installation**
```bash
mkdir -p ~/.zsh/completions
md2jira --completions zsh > ~/.zsh/completions/_md2jira

# Add to ~/.zshrc (before compinit):
fpath=(~/.zsh/completions $fpath)
autoload -Uz compinit && compinit
```

**Option 2: Oh My Zsh**
```bash
md2jira --completions zsh > ~/.oh-my-zsh/completions/_md2jira
```

### Fish

**Option 1: User-level installation**
```bash
md2jira --completions fish > ~/.config/fish/completions/md2jira.fish
```

**Option 2: Symlink from package**
```bash
ln -s /path/to/md2jira/completions/md2jira.fish ~/.config/fish/completions/
```

## Features

The completion scripts provide intelligent completions for:

### Options
```bash
md2jira --<TAB>
--config      --epic        --execute     --export      --help
--interactive --jira-url    --markdown    --no-color    --no-confirm
--phase       --project     --story       --validate    --verbose
--version     --completions
```

### File Paths
```bash
# Markdown files for --markdown
md2jira --markdown <TAB>
EPIC.md  README.md  docs/

# Config files for --config
md2jira --config <TAB>
.md2jira.yaml  config.toml

# JSON files for --export
md2jira --export <TAB>
results.json  output.json
```

### Phase Choices
```bash
md2jira --phase <TAB>
all  descriptions  subtasks  comments  statuses
```

### Shell Types
```bash
md2jira --completions <TAB>
bash  zsh  fish
```

## Troubleshooting

### Completions not working in Bash

1. Ensure bash-completion is installed:
   ```bash
   # Ubuntu/Debian
   sudo apt install bash-completion
   
   # macOS
   brew install bash-completion@2
   ```

2. Source bash-completion in `~/.bashrc`:
   ```bash
   [[ -r "/usr/share/bash-completion/bash_completion" ]] && \
     source "/usr/share/bash-completion/bash_completion"
   ```

### Completions not working in Zsh

1. Ensure compinit is loaded:
   ```bash
   autoload -Uz compinit && compinit
   ```

2. Rebuild completion cache:
   ```bash
   rm ~/.zcompdump*
   compinit
   ```

### Completions not working in Fish

1. Check the file is in the correct location:
   ```bash
   ls ~/.config/fish/completions/md2jira.fish
   ```

2. Reload completions:
   ```fish
   complete -c md2jira -e  # Clear existing
   source ~/.config/fish/completions/md2jira.fish
   ```

## Updating Completions

When you update md2jira, regenerate completions to get new options:

```bash
# Bash
md2jira --completions bash > ~/.local/share/bash-completion/completions/md2jira

# Zsh
md2jira --completions zsh > ~/.zsh/completions/_md2jira
rm ~/.zcompdump*  # Clear cache

# Fish
md2jira --completions fish > ~/.config/fish/completions/md2jira.fish
```

## Programmatic Access

You can also access completion scripts programmatically:

```python
from md2jira.cli import get_completion_script, SUPPORTED_SHELLS

# Get list of supported shells
print(SUPPORTED_SHELLS)  # ['bash', 'zsh', 'fish']

# Get a specific script
bash_script = get_completion_script('bash')
```

