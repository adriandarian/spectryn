#!/bin/bash
# Bash completion script for spectryn
#
# Installation:
#   Option 1: Source directly in ~/.bashrc
#     source /path/to/spectryn/completions/spectryn.bash
#
#   Option 2: Copy to bash-completion directory
#     sudo cp spectryn.bash /etc/bash_completion.d/spectryn
#
#   Option 3: Generate dynamically
#     eval "$(spectryn --completions bash)"

_spectryn_completions() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    # All available options
    opts="--input -f --input-dir -d --epic -e --execute -x --dry-run -n --no-confirm --phase --story --config -c --jira-url --project --verbose -v --quiet -q --output -o --no-color --export --validate --interactive -i --resume --resume-session --list-sessions --update-source --list-files --version --help -h --completions"

    # Phase choices
    phases="all descriptions subtasks comments statuses"

    # Handle option-specific completions
    case "${prev}" in
        --input|-f)
            # Complete markdown files
            COMPREPLY=( $(compgen -f -X '!*.md' -- "${cur}") )
            # Also complete directories for navigation
            COMPREPLY+=( $(compgen -d -- "${cur}") )
            return 0
            ;;
        --input-dir|-d)
            # Complete directories only
            COMPREPLY=( $(compgen -d -- "${cur}") )
            return 0
            ;;
        --config|-c)
            # Complete config files (.yaml, .toml, .yml)
            COMPREPLY=( $(compgen -f -X '!*.yaml' -- "${cur}") )
            COMPREPLY+=( $(compgen -f -X '!*.yml' -- "${cur}") )
            COMPREPLY+=( $(compgen -f -X '!*.toml' -- "${cur}") )
            COMPREPLY+=( $(compgen -d -- "${cur}") )
            return 0
            ;;
        --export)
            # Complete JSON files
            COMPREPLY=( $(compgen -f -X '!*.json' -- "${cur}") )
            COMPREPLY+=( $(compgen -d -- "${cur}") )
            return 0
            ;;
        --phase)
            # Complete phase choices
            COMPREPLY=( $(compgen -W "${phases}" -- "${cur}") )
            return 0
            ;;
        --epic|-e)
            # No completion for epic key (user-specific)
            return 0
            ;;
        --story)
            # No completion for story ID (user-specific)
            return 0
            ;;
        --jira-url)
            # No completion for URL
            return 0
            ;;
        --project)
            # No completion for project key
            return 0
            ;;
        --completions)
            # Complete shell types
            COMPREPLY=( $(compgen -W "bash zsh fish" -- "${cur}") )
            return 0
            ;;
        --output|-o)
            # Complete output formats
            COMPREPLY=( $(compgen -W "text json" -- "${cur}") )
            return 0
            ;;
    esac

    # Complete options if starting with -
    if [[ "${cur}" == -* ]]; then
        COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
        return 0
    fi

    # Default: complete files
    COMPREPLY=( $(compgen -f -- "${cur}") )
}

# Register the completion function
complete -F _spectryn_completions spectryn

