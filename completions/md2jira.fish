# Fish completion script for md2jira
#
# Installation:
#   Option 1: Copy to Fish completions directory
#     cp md2jira.fish ~/.config/fish/completions/md2jira.fish
#
#   Option 2: Symlink to Fish completions directory
#     ln -s /path/to/md2jira/completions/md2jira.fish ~/.config/fish/completions/
#
#   Option 3: Generate dynamically (add to config.fish)
#     md2jira --completions fish | source

# Disable file completions by default (we'll enable them for specific options)
complete -c md2jira -f

# Required arguments
complete -c md2jira -s m -l markdown -d 'Path to markdown epic file' -r -F -a '*.md'
complete -c md2jira -s e -l epic -d 'Jira epic key (e.g., PROJ-123)' -x

# Execution mode
complete -c md2jira -s x -l execute -d 'Execute changes (default is dry-run)'
complete -c md2jira -l no-confirm -d 'Skip confirmation prompts'

# Phase control
complete -c md2jira -l phase -d 'Which phase to run' -x -a '
    all\t"Run all sync phases"
    descriptions\t"Sync story descriptions only"
    subtasks\t"Sync subtasks only"
    comments\t"Sync comments only"
    statuses\t"Sync statuses only"
'

# Filters
complete -c md2jira -l story -d 'Filter to specific story ID (e.g., US-001)' -x

# Configuration
complete -c md2jira -s c -l config -d 'Path to config file' -r -F -a '*.yaml *.yml *.toml'
complete -c md2jira -l jira-url -d 'Override Jira URL' -x
complete -c md2jira -l project -d 'Override Jira project key' -x

# Output options
complete -c md2jira -s v -l verbose -d 'Verbose output'
complete -c md2jira -l no-color -d 'Disable colored output'
complete -c md2jira -l export -d 'Export analysis to JSON file' -r -F -a '*.json'

# Special modes
complete -c md2jira -l validate -d 'Validate markdown file format'
complete -c md2jira -s i -l interactive -d 'Interactive mode with step-by-step guided sync'
complete -c md2jira -l version -d 'Show version and exit'
complete -c md2jira -s h -l help -d 'Show help message'

# Shell completions
complete -c md2jira -l completions -d 'Generate shell completion script' -x -a '
    bash\t"Generate Bash completion script"
    zsh\t"Generate Zsh completion script"  
    fish\t"Generate Fish completion script"
'

