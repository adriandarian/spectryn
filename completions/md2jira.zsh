#compdef md2jira
# Zsh completion script for md2jira
#
# Installation:
#   Option 1: Add to fpath in ~/.zshrc (before compinit)
#     fpath=(/path/to/md2jira/completions $fpath)
#     autoload -Uz compinit && compinit
#
#   Option 2: Copy to zsh completions directory
#     cp md2jira.zsh ~/.zsh/completions/_md2jira
#
#   Option 3: Generate dynamically
#     eval "$(md2jira --completions zsh)"

_md2jira() {
    local curcontext="$curcontext" state line
    typeset -A opt_args
    
    local -a phases
    phases=(
        'all:Run all sync phases'
        'descriptions:Sync story descriptions only'
        'subtasks:Sync subtasks only'
        'comments:Sync comments only'
        'statuses:Sync statuses only'
    )
    
    local -a shells
    shells=(
        'bash:Generate Bash completion script'
        'zsh:Generate Zsh completion script'
        'fish:Generate Fish completion script'
    )
    
    _arguments -C \
        '(-m --markdown)'{-m,--markdown}'[Path to markdown epic file]:markdown file:_files -g "*.md"' \
        '(-e --epic)'{-e,--epic}'[Jira epic key (e.g., PROJ-123)]:epic key:' \
        '(-x --execute)'{-x,--execute}'[Execute changes (default is dry-run)]' \
        '--no-confirm[Skip confirmation prompts]' \
        '--phase[Which phase to run]:phase:->phases' \
        '--story[Filter to specific story ID]:story id:' \
        '(-c --config)'{-c,--config}'[Path to config file]:config file:_files -g "*.{yaml,yml,toml}"' \
        '--jira-url[Override Jira URL]:url:_urls' \
        '--project[Override Jira project key]:project key:' \
        '(-v --verbose)'{-v,--verbose}'[Verbose output]' \
        '--no-color[Disable colored output]' \
        '--export[Export analysis to JSON file]:json file:_files -g "*.json"' \
        '--validate[Validate markdown file format]' \
        '(-i --interactive)'{-i,--interactive}'[Interactive mode with step-by-step guided sync]' \
        '--version[Show version and exit]' \
        '--completions[Generate shell completion script]:shell:->shells' \
        '(-h --help)'{-h,--help}'[Show help message]' \
        '*:markdown file:_files -g "*.md"'
    
    case "$state" in
        phases)
            _describe -t phases 'sync phase' phases
            ;;
        shells)
            _describe -t shells 'shell type' shells
            ;;
    esac
}

_md2jira "$@"

