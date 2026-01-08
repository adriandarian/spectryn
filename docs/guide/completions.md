# Shell Completions

spectryn provides shell completion scripts for Bash, Zsh, and Fish shells. These enable tab-completion for commands, options, and file paths.

## Quick Setup

The easiest way to enable completions is to evaluate them dynamically.

::: code-group

```bash [Bash]
# Add to ~/.bashrc
eval "$(spectryn --completions bash)"
```

```bash [Zsh]
# Add to ~/.zshrc
eval "$(spectryn --completions zsh)"
```

```fish [Fish]
# Add to ~/.config/fish/config.fish
spectryn --completions fish | source
```

:::

Then restart your shell or source the config file.

## Manual Installation

### Bash

**Option 1: User-level installation**

```bash
mkdir -p ~/.local/share/bash-completion/completions
spectryn --completions bash > ~/.local/share/bash-completion/completions/spectryn
```

**Option 2: System-wide installation (requires sudo)**

```bash
sudo spectryn --completions bash > /etc/bash_completion.d/spectryn
```

**Option 3: Copy from package**

```bash
cp /path/to/spectryn/completions/spectryn.bash \
   ~/.local/share/bash-completion/completions/spectryn
```

### Zsh

**Option 1: User-level installation**

```bash
mkdir -p ~/.zsh/completions
spectryn --completions zsh > ~/.zsh/completions/_spectryn

# Add to ~/.zshrc (before compinit):
fpath=(~/.zsh/completions $fpath)
autoload -Uz compinit && compinit
```

**Option 2: Oh My Zsh**

```bash
spectryn --completions zsh > ~/.oh-my-zsh/completions/_spectryn
```

### Fish

**Option 1: User-level installation**

```bash
spectryn --completions fish > ~/.config/fish/completions/spectryn.fish
```

**Option 2: Symlink from package**

```bash
ln -s /path/to/spectryn/completions/spectryn.fish \
   ~/.config/fish/completions/
```

## Completion Features

The completion scripts provide intelligent completions for:

### Options

```bash
spectryn --<TAB>
--config      --epic        --execute     --export      --help
--interactive --jira-url    --markdown    --no-color    --no-confirm
--phase       --project     --story       --validate    --verbose
--version     --completions
```

### File Paths

```bash
# Markdown files for --markdown
spectryn --markdown <TAB>
EPIC.md  README.md  docs/

# Config files for --config
spectryn --config <TAB>
.spectryn.yaml  config.toml

# JSON files for --export
spectryn --export <TAB>
results.json  output.json
```

### Phase Choices

```bash
spectryn --phase <TAB>
all  descriptions  subtasks  comments  statuses
```

### Shell Types

```bash
spectryn --completions <TAB>
bash  zsh  fish
```

## Troubleshooting

### Completions Not Working in Bash

1. Ensure bash-completion is installed:

::: code-group

```bash [Ubuntu/Debian]
sudo apt install bash-completion
```

```bash [macOS]
brew install bash-completion@2
```

:::

2. Source bash-completion in `~/.bashrc`:

```bash
[[ -r "/usr/share/bash-completion/bash_completion" ]] && \
  source "/usr/share/bash-completion/bash_completion"
```

### Completions Not Working in Zsh

1. Ensure compinit is loaded:

```bash
autoload -Uz compinit && compinit
```

2. Rebuild completion cache:

```bash
rm ~/.zcompdump*
compinit
```

### Completions Not Working in Fish

1. Check the file is in the correct location:

```bash
ls ~/.config/fish/completions/spectryn.fish
```

2. Reload completions:

```fish
complete -c spectryn -e  # Clear existing
source ~/.config/fish/completions/spectryn.fish
```

## Updating Completions

When you update spectryn, regenerate completions to get new options:

```bash
# Bash
spectryn --completions bash > ~/.local/share/bash-completion/completions/spectryn

# Zsh
spectryn --completions zsh > ~/.zsh/completions/_spectryn
rm ~/.zcompdump*  # Clear cache

# Fish
spectryn --completions fish > ~/.config/fish/completions/spectryn.fish
```

## Programmatic Access

You can also access completion scripts programmatically:

```python
from spectryn.cli import get_completion_script, SUPPORTED_SHELLS

# Get list of supported shells
print(SUPPORTED_SHELLS)  # ['bash', 'zsh', 'fish']

# Get a specific script
bash_script = get_completion_script('bash')
```

