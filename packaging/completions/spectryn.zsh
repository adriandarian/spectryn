#compdef spectryn
# Zsh completion script for spectryn
#
# Installation:
#   Option 1: Add to fpath in ~/.zshrc (before compinit)
#     fpath=(/path/to/spectryn/completions $fpath)
#     autoload -Uz compinit && compinit
#
#   Option 2: Copy to zsh completions directory
#     cp spectryn.zsh ~/.zsh/completions/_spectryn
#
#   Option 3: Generate dynamically
#     eval "$(spectryn --completions zsh)"

_spectryn() {
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
        '(-f --input)'{-f,--input}'[Path to input file (markdown, yaml, json, etc.)]:input file:_files -g "*.md"' \
        '(-d --input-dir)'{-d,--input-dir}'[Path to directory containing story files]:directory:_files -/' \
        '(-e --epic)'{-e,--epic}'[Jira epic key (e.g., PROJ-123)]:epic key:' \
        '(-x --execute)'{-x,--execute}'[Execute changes (default is dry-run)]' \
        '(-n --dry-run)'{-n,--dry-run}'[Preview changes without executing]' \
        '--no-confirm[Skip confirmation prompts]' \
        '--phase[Which phase to run]:phase:->phases' \
        '--story[Filter to specific story ID]:story id:' \
        '(-c --config)'{-c,--config}'[Path to config file]:config file:_files -g "*.{yaml,yml,toml}"' \
        '--jira-url[Override Jira URL]:url:_urls' \
        '--project[Override Jira project key]:project key:' \
        '(-v --verbose)'{-v,--verbose}'[Verbose output]' \
        '(-q --quiet)'{-q,--quiet}'[Quiet mode - only show errors and summary]' \
        '(-o --output)'{-o,--output}'[Output format]:format:(text json)' \
        '--no-color[Disable colored output]' \
        '--export[Export analysis to JSON file]:json file:_files -g "*.json"' \
        '--validate[Validate markdown file format]' \
        '(-i --interactive)'{-i,--interactive}'[Interactive mode with step-by-step guided sync]' \
        '--resume[Resume an interrupted sync session]' \
        '--resume-session[Resume a specific sync session by ID]:session id:' \
        '--list-sessions[List all resumable sync sessions]' \
        '--update-source[Write tracker info back to source file after sync]' \
        '--list-files[List which files would be processed from --input-dir]' \
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

_spectryn "$@"

