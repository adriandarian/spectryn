# Fish completion script for spectryn
#
# Installation:
#   Option 1: Copy to Fish completions directory
#     cp spectryn.fish ~/.config/fish/completions/spectryn.fish
#
#   Option 2: Symlink to Fish completions directory
#     ln -s /path/to/spectryn/completions/spectryn.fish ~/.config/fish/completions/
#
#   Option 3: Generate dynamically (add to config.fish)
#     spectryn --completions fish | source

# Disable file completions by default (we'll enable them for specific options)
complete -c spectryn -f

# Input arguments
complete -c spectryn -s f -l input -d 'Path to input file (markdown, yaml, json, etc.)' -r -F -a '*.md'
complete -c spectryn -s d -l input-dir -d 'Path to directory containing story files' -r -a '(__fish_complete_directories)'
complete -c spectryn -s e -l epic -d 'Jira epic key (e.g., PROJ-123)' -x

# Execution mode
complete -c spectryn -s x -l execute -d 'Execute changes (default is dry-run)'
complete -c spectryn -s n -l dry-run -d 'Preview changes without executing'
complete -c spectryn -l no-confirm -d 'Skip confirmation prompts'
complete -c spectryn -l update-source -d 'Write tracker info back to source file after sync'
complete -c spectryn -l list-files -d 'List which files would be processed from --input-dir'

# Phase control
complete -c spectryn -l phase -d 'Which phase to run' -x -a '
    all\t"Run all sync phases"
    descriptions\t"Sync story descriptions only"
    subtasks\t"Sync subtasks only"
    comments\t"Sync comments only"
    statuses\t"Sync statuses only"
'

# Filters
complete -c spectryn -l story -d 'Filter to specific story ID (e.g., US-001)' -x

# Configuration
complete -c spectryn -s c -l config -d 'Path to config file' -r -F -a '*.yaml *.yml *.toml'
complete -c spectryn -l jira-url -d 'Override Jira URL' -x
complete -c spectryn -l project -d 'Override Jira project key' -x

# Output options
complete -c spectryn -s v -l verbose -d 'Verbose output'
complete -c spectryn -s q -l quiet -d 'Quiet mode - only show errors and summary'
complete -c spectryn -s o -l output -d 'Output format' -x -a 'text json'
complete -c spectryn -l no-color -d 'Disable colored output'
complete -c spectryn -l export -d 'Export analysis to JSON file' -r -F -a '*.json'

# Special modes
complete -c spectryn -l validate -d 'Validate markdown file format'
complete -c spectryn -s i -l interactive -d 'Interactive mode with step-by-step guided sync'
complete -c spectryn -l resume -d 'Resume an interrupted sync session'
complete -c spectryn -l resume-session -d 'Resume a specific sync session by ID' -x
complete -c spectryn -l list-sessions -d 'List all resumable sync sessions'
complete -c spectryn -l version -d 'Show version and exit'
complete -c spectryn -s h -l help -d 'Show help message'

# Shell completions
complete -c spectryn -l completions -d 'Generate shell completion script' -x -a '
    bash\t"Generate Bash completion script"
    zsh\t"Generate Zsh completion script"
    fish\t"Generate Fish completion script"
'

