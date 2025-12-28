"""
Man Page Generation - Generate Unix man pages for spectra.

Generates man pages in troff/groff format for installation on Unix systems.
"""

import contextlib
import os
import subprocess
from datetime import datetime
from pathlib import Path


# Version and metadata
VERSION = "2.0.0"
DATE = datetime.now().strftime("%B %Y")


def generate_man_page() -> str:
    """
    Generate the spectra man page in troff/groff format.

    Returns:
        The man page content as a string.
    """
    return f""".TH SPECTRA 1 "{DATE}" "spectra {VERSION}" "User Commands"
.SH NAME
spectra \\- sync markdown/YAML user stories to issue trackers
.SH SYNOPSIS
.B spectra
[\\fIOPTIONS\\fR]
.SH DESCRIPTION
.B spectra
is a CLI tool that synchronizes markdown, YAML, or JSON specifications
to issue trackers like Jira, GitHub Issues, Linear, Azure DevOps, and more.
.PP
It uses Clean Architecture with a Hexagonal/Ports-and-Adapters pattern,
enabling easy extension to new trackers and file formats.
.SH OPTIONS
.SS "Input Options"
.TP
.BR \\-f ", " \\-\\-input " " \\fIFILE\\fR
Path to input file (markdown, yaml, json, csv, asciidoc, excel, toml).
.TP
.BR \\-d ", " \\-\\-input\\-dir " " \\fIDIR\\fR
Path to directory containing story files (auto-detects file types).
.TP
.BR \\-e ", " \\-\\-epic " " \\fIKEY\\fR
Epic key in your issue tracker (e.g., PROJ-123).
.TP
.B \\-\\-list\\-files
List which files would be processed from \\-\\-input\\-dir.
.SS "Execution Options"
.TP
.BR \\-x ", " \\-\\-execute
Execute changes. Default behavior is dry-run (preview only).
.TP
.BR \\-n ", " \\-\\-dry\\-run
Preview changes without executing (this is the default).
.TP
.B \\-\\-no\\-confirm
Skip confirmation prompts.
.TP
.B \\-\\-incremental
Only sync changed stories (skip unchanged).
.TP
.B \\-\\-force\\-full\\-sync
Force full sync even when \\-\\-incremental is set.
.TP
.B \\-\\-update\\-source
Write tracker info back to source file after sync.
.SS "Phase Control"
.TP
.B \\-\\-phase " " \\fIPHASE\\fR
Which phase to run. Valid values: all, descriptions, subtasks, comments, statuses.
Default is "all".
.SS "Filters"
.TP
.B \\-\\-story " " \\fIID\\fR
Filter to specific story ID (e.g., STORY-001, US-001, PROJ-123).
.SS "Configuration"
.TP
.BR \\-c ", " \\-\\-config " " \\fIFILE\\fR
Path to config file (.spectra.yaml, .spectra.toml).
.TP
.B \\-\\-jira\\-url " " \\fIURL\\fR
Override Jira URL.
.TP
.B \\-\\-project " " \\fIKEY\\fR
Override Jira project key.
.SS "Output Options"
.TP
.BR \\-v ", " \\-\\-verbose
Verbose output.
.TP
.BR \\-q ", " \\-\\-quiet
Quiet mode - only show errors and final summary (for CI/scripting).
.TP
.BR \\-o ", " \\-\\-output " " \\fIFORMAT\\fR
Output format: text (default), json, yaml, or markdown for CI pipelines.
.TP
.B \\-\\-no\\-color
Disable colored output.
.TP
.B \\-\\-no\\-emoji
Disable emojis in output (use ASCII alternatives).
.TP
.B \\-\\-theme " " \\fINAME\\fR
Color theme for output. Available themes: default, dark, light, monokai,
solarized, nord, dracula, gruvbox, ocean, minimal.
.TP
.B \\-\\-list\\-themes
List available color themes and exit.
.TP
.B \\-\\-export " " \\fIFILE\\fR
Export analysis to JSON file.
.SS "Special Modes"
.TP
.B \\-\\-validate
Validate markdown file format.
.TP
.B \\-\\-strict
Treat warnings as errors during validation.
.TP
.B \\-\\-show\\-guide
Show the expected format guide.
.TP
.B \\-\\-suggest\\-fix
Get an AI prompt to fix validation errors.
.TP
.B \\-\\-auto\\-fix
Auto-fix using an AI CLI tool.
.TP
.BR \\-i ", " \\-\\-interactive
Interactive mode with step-by-step guided sync.
.TP
.B \\-\\-tui
Launch interactive TUI dashboard.
.TP
.B \\-\\-tui\\-demo
Launch TUI with demo data (for testing).
.TP
.B \\-\\-dashboard
Show status dashboard (static).
.SS "Resume Options"
.TP
.B \\-\\-resume
Resume an interrupted sync session.
.TP
.B \\-\\-resume\\-session " " \\fIID\\fR
Resume a specific sync session by ID.
.TP
.B \\-\\-list\\-sessions
List all resumable sync sessions.
.SS "Generation & Import"
.TP
.B \\-\\-generate
Generate markdown template from existing epic in tracker.
.TP
.B \\-\\-preview
Preview generated template before writing.
.TP
.B \\-\\-pull
Pull issues from tracker to local file (reverse sync).
.TP
.B \\-\\-pull\\-output " " \\fIFILE\\fR
Output file for pulled content.
.TP
.B \\-\\-bidirectional, \\-\\-two\\-way
Two-way sync: push local changes AND pull remote changes with conflict detection.
.TP
.B \\-\\-conflict\\-strategy " " \\fISTRATEGY\\fR
How to resolve conflicts: ask (interactive), force-local (take markdown), force-remote (take tracker), skip (skip conflicts), abort (fail on conflicts).
.SS "Watch & Schedule"
.TP
.B \\-\\-watch
Watch mode - auto-sync on file changes.
.TP
.B \\-\\-debounce " " \\fISECONDS\\fR
Debounce time between watch syncs.
.TP
.B \\-\\-schedule " " \\fIINTERVAL\\fR
Scheduled sync (e.g., 5m, 1h, daily:09:00).
.TP
.B \\-\\-run\\-now
Run scheduled sync immediately on start.
.SS "Webhook Server"
.TP
.B \\-\\-webhook
Start webhook server for tracker events.
.TP
.B \\-\\-webhook\\-port " " \\fIPORT\\fR
Port for webhook server.
.TP
.B \\-\\-webhook\\-secret " " \\fISECRET\\fR
Secret for webhook validation.
.SS "Multi-Epic Mode"
.TP
.B \\-\\-multi\\-epic
Sync multiple epics from one file.
.TP
.B \\-\\-epic\\-filter " " \\fIKEYS\\fR
Filter to specific epics (comma-separated).
.TP
.B \\-\\-list\\-epics
List epics in a multi-epic file.
.SS "Diagnostics"
.TP
.B \\-\\-init
Run interactive setup wizard.
.TP
.B \\-\\-doctor
Run diagnostic checks.
.TP
.B \\-\\-stats
Show story statistics.
.TP
.B \\-\\-diff
Show differences between local and remote.
.SS "Telemetry & Monitoring"
.TP
.B \\-\\-otel\\-enable
Enable OpenTelemetry tracing.
.TP
.B \\-\\-otel\\-endpoint " " \\fIURL\\fR
OpenTelemetry collector endpoint.
.TP
.B \\-\\-prometheus
Enable Prometheus metrics.
.TP
.B \\-\\-prometheus\\-port " " \\fIPORT\\fR
Prometheus metrics port.
.TP
.B \\-\\-health
Enable health check endpoint.
.TP
.B \\-\\-health\\-port " " \\fIPORT\\fR
Health check port.
.SS "Shell Completions & Man Pages"
.TP
.B \\-\\-completions " " \\fISHELL\\fR
Generate shell completion script (bash, zsh, fish, powershell).
.TP
.B \\-\\-man
Display this man page.
.TP
.B \\-\\-install\\-man
Install man page to system (requires appropriate permissions).
.SS "General"
.TP
.B \\-\\-version
Show version and exit.
.TP
.BR \\-h ", " \\-\\-help
Show help message.
.SH ENVIRONMENT
.TP
.B JIRA_URL
Jira instance URL (e.g., https://company.atlassian.net).
.TP
.B JIRA_EMAIL
Jira account email.
.TP
.B JIRA_API_TOKEN
Jira API token.
.TP
.B GITHUB_TOKEN
GitHub personal access token (for GitHub Issues).
.TP
.B LINEAR_API_KEY
Linear API key (for Linear issues).
.TP
.B AZURE_DEVOPS_TOKEN
Azure DevOps personal access token.
.SH FILES
.TP
.I .spectra.yaml
Project-level configuration file.
.TP
.I .spectra.toml
Alternative configuration file format.
.TP
.I ~/.config/spectra/config.yaml
User-level configuration file.
.SH EXAMPLES
.SS "First-time Setup"
.nf
.B spectra --init
.fi
.SS "Validate File Format"
.nf
.B spectra --validate -f EPIC.md
.B spectra --validate -f EPIC.md --strict
.fi
.SS "Preview Changes (Dry-Run)"
.nf
.B spectra -f EPIC.md -e PROJ-123
.fi
.SS "Execute Sync"
.nf
.B spectra -f EPIC.md -e PROJ-123 --execute
.B spectra -f EPIC.md -e PROJ-123 -x --no-confirm
.fi
.SS "Interactive Mode"
.nf
.B spectra -f EPIC.md -e PROJ-123 --interactive
.fi
.SS "TUI Dashboard"
.nf
.B spectra --tui -f EPIC.md -e PROJ-123
.fi
.SS "Generate Template from Jira"
.nf
.B spectra --generate --epic PROJ-123 --execute
.fi
.SS "Pull from Tracker"
.nf
.B spectra --pull -e PROJ-123 --pull-output EPIC.md --execute
.fi
.SS "Bidirectional Sync"
.nf
.B spectra --bidirectional -f EPIC.md -e PROJ-123 --execute
.fi
.PP
Two-way sync that pushes local changes AND pulls remote changes with conflict detection:
.nf
.B spectra --bidirectional -f EPIC.md -e PROJ-123 --conflict-strategy force-local --execute
.fi
.SS "Watch Mode"
.nf
.B spectra --watch -f EPIC.md -e PROJ-123 --execute
.fi
.SS "Directory Mode"
.nf
.B spectra -d ./docs/plan -e PROJ-123 --execute
.fi
.SH EXIT STATUS
.TP
.B 0
Success
.TP
.B 1
General error
.TP
.B 2
Configuration error
.TP
.B 3
Authentication error
.TP
.B 4
Validation error
.TP
.B 5
Network error
.TP
.B 10
Partial success (some operations failed)
.TP
.B 130
Interrupted by user (SIGINT)
.SH SEE ALSO
.BR jira (1),
.BR git (1),
.BR curl (1)
.SH BUGS
Report bugs at: https://github.com/yourorg/spectra/issues
.SH AUTHOR
Written by the Spectra contributors.
.SH COPYRIGHT
Copyright \\(co 2024 Spectra Project.
Licensed under the MIT License.
"""


def get_man_path() -> Path | None:
    """
    Get the appropriate man page installation path.

    Returns:
        Path to man1 directory, or None if not found.
    """
    # Check common man page locations
    paths = [
        Path("/usr/local/share/man/man1"),
        Path("/usr/share/man/man1"),
        Path.home() / ".local/share/man/man1",
    ]

    for path in paths:
        if path.exists() and os.access(path.parent, os.W_OK):
            return path

    # Try to create user-local man directory
    local_man = Path.home() / ".local/share/man/man1"
    try:
        local_man.mkdir(parents=True, exist_ok=True)
        return local_man
    except OSError:
        pass

    return None


def install_man_page() -> tuple[bool, str]:
    """
    Install the man page to the system.

    Returns:
        Tuple of (success, message).
    """
    man_path = get_man_path()
    if man_path is None:
        return False, "Could not find writable man page directory"

    man_file = man_path / "spectra.1"
    content = generate_man_page()

    try:
        man_file.write_text(content)

        # Try to update man database
        with contextlib.suppress(FileNotFoundError):
            # mandb for most Linux systems
            subprocess.run(["mandb", "-q"], check=False, capture_output=True)
        with contextlib.suppress(FileNotFoundError):
            # makewhatis for some BSD systems
            subprocess.run(["makewhatis", str(man_path.parent)], check=False, capture_output=True)

        return True, f"Man page installed to {man_file}"

    except PermissionError:
        return False, f"Permission denied writing to {man_file}. Try with sudo."
    except OSError as e:
        return False, f"Error installing man page: {e}"


def show_man_page() -> bool:
    """
    Display the man page using the system's man viewer.

    Returns:
        True if successful, False otherwise.
    """
    import tempfile

    content = generate_man_page()

    # Write to temp file and display with man
    with tempfile.NamedTemporaryFile(mode="w", suffix=".1", delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        # Try to use man to display
        result = subprocess.run(["man", temp_path], check=False)
        return result.returncode == 0
    except FileNotFoundError:
        # man not available, print raw
        print(content)
        return True
    finally:
        # Clean up temp file
        Path(temp_path).unlink(missing_ok=True)


def print_man_page() -> None:
    """Print the raw man page content to stdout."""
    print(generate_man_page())


def get_installation_instructions() -> str:
    """Get man page installation instructions."""
    return """
# Man Page Installation

## Automatic Installation
  spectra --install-man

## Manual Installation

### Linux (system-wide, requires sudo)
  spectra --man > /tmp/spectra.1
  sudo install -m 644 /tmp/spectra.1 /usr/local/share/man/man1/spectra.1
  sudo mandb

### Linux (user-local)
  mkdir -p ~/.local/share/man/man1
  spectra --man > ~/.local/share/man/man1/spectra.1
  # Add to ~/.bashrc or ~/.zshrc:
  export MANPATH="$HOME/.local/share/man:$MANPATH"

### macOS (Homebrew)
  spectra --man > /usr/local/share/man/man1/spectra.1

### macOS (user-local)
  mkdir -p ~/.local/share/man/man1
  spectra --man > ~/.local/share/man/man1/spectra.1
  export MANPATH="$HOME/.local/share/man:$MANPATH"

## Usage
  man spectra
"""
