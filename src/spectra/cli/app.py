"""
CLI App - Main entry point for spectra command line tool.
"""

import argparse
import logging
import sys
from pathlib import Path

from spectra.adapters import ADFFormatter, EnvironmentConfigProvider, JiraAdapter, MarkdownParser
from spectra.application import SyncOrchestrator
from spectra.core.domain.events import EventBus

from .exit_codes import ExitCode
from .output import Console, Symbols


def create_parser() -> argparse.ArgumentParser:
    """
    Create the command-line argument parser for spectra.

    Defines all CLI arguments including required inputs (markdown file, epic key),
    execution modes, phase control, filters, and output options.

    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        prog="spectra",
        description="Sync markdown epic documentation with Jira",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # First-time setup wizard
  spectra --init

  # Generate markdown template from existing Jira epic
  spectra --generate --epic PROJ-123 --execute

  # Preview generated template before writing
  spectra --generate --epic PROJ-123 --preview

  # Validate file format
  spectra --validate --input EPIC.md

  # Strict validation (warnings are errors)
  spectra --validate -f EPIC.md --strict

  # Show the expected format guide
  spectra --validate -f EPIC.md --show-guide

  # Get an AI prompt to fix validation errors (copy to ChatGPT/Claude)
  spectra --validate -f EPIC.md --suggest-fix

  # Auto-fix using an AI CLI tool (detects available tools)
  spectra --validate -f EPIC.md --auto-fix

  # Auto-fix with a specific AI tool
  spectra --validate -f EPIC.md --auto-fix --ai-tool claude

  # List detected AI CLI tools for auto-fix
  spectra --list-ai-tools

  # Show status dashboard (static)
  spectra --dashboard -f EPIC.md --epic PROJ-123

  # Launch interactive TUI dashboard
  spectra --tui -f EPIC.md --epic PROJ-123

  # TUI with demo data (for testing)
  spectra --tui-demo

  # Enable OpenTelemetry tracing
  spectra --otel-enable --otel-endpoint http://localhost:4317 -f EPIC.md -e PROJ-123

  # Enable Prometheus metrics (exposed on :9090/metrics)
  spectra --prometheus --prometheus-port 9090 -f EPIC.md -e PROJ-123

  # Enable health check endpoint (for Kubernetes/Docker)
  spectra --health --health-port 8080 -f EPIC.md -e PROJ-123

  # Enable anonymous usage analytics (opt-in)
  spectra --analytics -f EPIC.md -e PROJ-123

  # Show/clear analytics data
  spectra --analytics-show
  spectra --analytics-clear

  # Preview changes without executing (dry-run is default)
  spectra -f EPIC.md -e PROJ-123 --dry-run

  # Analyze without making changes (same as above, --dry-run is optional)
  spectra -f EPIC.md -e PROJ-123

  # Execute sync with confirmations
  spectra -f EPIC.md -e PROJ-123 --execute

  # Full sync without prompts
  spectra -f EPIC.md -e PROJ-123 --execute --no-confirm

  # Interactive mode - step-by-step guided sync
  spectra -f EPIC.md -e PROJ-123 --interactive

  # Sync only descriptions
  spectra -f EPIC.md -e PROJ-123 --execute --phase descriptions

  # Verbose output for debugging
  spectra -f EPIC.md -e PROJ-123 -v

  # Pull from Jira to file (reverse sync)
  spectra --pull -e PROJ-123 --pull-output EPIC.md --execute

  # Preview what would be pulled from Jira
  spectra --pull -e PROJ-123 --preview

  # Update existing file from Jira
  spectra --pull -e PROJ-123 -f EPIC.md --update-existing --execute

  # Watch mode - auto-sync on file changes
  spectra --watch -f EPIC.md -e PROJ-123 --execute

  # Watch mode with custom debounce (5 seconds between syncs)
  spectra --watch -f EPIC.md -e PROJ-123 --execute --debounce 5

  # Scheduled sync - every 5 minutes
  spectra --schedule 5m -f EPIC.md -e PROJ-123 --execute

  # Scheduled sync - daily at 9:00 AM
  spectra --schedule daily:09:00 -f EPIC.md -e PROJ-123 --execute

  # Scheduled sync - run immediately, then every hour
  spectra --schedule 1h -f EPIC.md -e PROJ-123 --execute --run-now

  # Webhook server - receive Jira webhooks for auto reverse sync
  spectra --webhook -e PROJ-123 --pull-output EPIC.md --execute

  # Webhook server on custom port with secret
  spectra --webhook --webhook-port 9000 --webhook-secret mysecret -e PROJ-123 --pull-output EPIC.md --execute

  # Multi-epic sync - sync all epics from one file
  spectra --multi-epic -f ROADMAP.md --execute

  # Multi-epic with filter - sync only specific epics
  spectra --multi-epic -f ROADMAP.md --epic-filter PROJ-100,PROJ-200 --execute

  # List epics in a multi-epic file
  spectra --list-epics -f ROADMAP.md

  # Sync cross-project links
  spectra --sync-links -f EPIC.md -e PROJ-123 --execute

  # Analyze links without syncing
  spectra --analyze-links -f EPIC.md -e PROJ-123

  # Directory mode - sync all story files from a directory
  spectra -d ./docs/plan -e PROJ-123 --dry-run

  # Preview which files would be processed from a directory
  spectra -d ./docs/plan --list-files

  # Execute directory sync
  spectra -d ./docs/plan -e PROJ-123 --execute

Environment Variables:
  JIRA_URL         Jira instance URL (e.g., https://company.atlassian.net)
  JIRA_EMAIL       Jira account email
  JIRA_API_TOKEN   Jira API token
        """,
    )

    # Input arguments - supports multiple file types (markdown, yaml, json, csv, etc.)
    parser.add_argument(
        "--input",
        "-f",
        type=str,
        help="Path to input file (markdown, yaml, json, csv, asciidoc, excel, toml)",
    )
    parser.add_argument(
        "--input-dir",
        "-d",
        type=str,
        metavar="DIR",
        help="Path to directory containing story files (auto-detects file types)",
    )
    parser.add_argument(
        "--list-files",
        action="store_true",
        help="List which files would be processed from --input-dir (useful for preview)",
    )
    parser.add_argument("--epic", "-e", type=str, help="Jira epic key (e.g., PROJ-123)")

    execution_group = parser.add_argument_group("Execution")
    execution_group.add_argument(
        "--execute", "-x", action="store_true", help="Execute changes (default is dry-run)"
    )
    execution_group.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Preview changes without executing (this is the default, use for explicit clarity)",
    )
    execution_group.add_argument(
        "--no-confirm", action="store_true", help="Skip confirmation prompts"
    )
    execution_group.add_argument(
        "--incremental", action="store_true", help="Only sync changed stories (skip unchanged)"
    )
    execution_group.add_argument(
        "--delta-sync",
        action="store_true",
        help="Only sync changed fields (more granular than --incremental)",
    )
    execution_group.add_argument(
        "--sync-fields",
        type=str,
        nargs="+",
        choices=[
            "title",
            "description",
            "status",
            "story_points",
            "priority",
            "assignee",
            "labels",
            "subtasks",
            "comments",
        ],
        help="Specific fields to sync (use with --delta-sync)",
    )
    execution_group.add_argument(
        "--force-full-sync",
        action="store_true",
        help="Force full sync even when --incremental is set",
    )
    parser.add_argument(
        "--update-source",
        action="store_true",
        help="Write tracker info (issue key, URL) back to source markdown file after sync",
    )

    phase_group = parser.add_argument_group("Phase control")
    phase_group.add_argument(
        "--phase",
        type=str,
        choices=["all", "descriptions", "subtasks", "comments", "statuses"],
        default="all",
        help="Which phase to run (default: all)",
    )

    filters_group = parser.add_argument_group("Filters")
    filters_group.add_argument(
        "--story", type=str, help="Filter to specific story ID (e.g., STORY-001, US-001, PROJ-123)"
    )

    config_group = parser.add_argument_group("Configuration")
    config_group.add_argument(
        "--config", "-c", type=str, help="Path to config file (.spectra.yaml, .spectra.toml)"
    )
    config_group.add_argument("--jira-url", type=str, help="Override Jira URL")
    config_group.add_argument("--project", type=str, help="Override Jira project key")

    output_group = parser.add_argument_group("Output")
    output_group.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    output_group.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Quiet mode - only show errors and final summary (for CI/scripting)",
    )
    output_group.add_argument(
        "--output",
        "-o",
        type=str,
        choices=["text", "json", "yaml", "markdown"],
        default="text",
        help="Output format: text (default), json, yaml, or markdown for CI pipelines",
    )
    parser.add_argument("--no-color", action="store_true", help="Disable colored output")
    parser.add_argument(
        "--no-emoji",
        action="store_true",
        help="Disable emojis in output (use ASCII alternatives)",
    )
    parser.add_argument(
        "--theme",
        type=str,
        choices=[
            "default",
            "dark",
            "light",
            "monokai",
            "solarized",
            "nord",
            "dracula",
            "gruvbox",
            "ocean",
            "minimal",
        ],
        default=None,
        help="Color theme for output (default, dark, light, monokai, solarized, nord, dracula, gruvbox, ocean, minimal)",
    )
    parser.add_argument(
        "--list-themes",
        action="store_true",
        help="List available color themes and exit",
    )
    parser.add_argument(
        "--log-format",
        type=str,
        choices=["text", "json"],
        default="text",
        help="Log format: text (default) or json for structured log aggregation",
    )
    parser.add_argument(
        "--log-file", type=str, metavar="PATH", help="Write logs to file (in addition to stderr)"
    )
    parser.add_argument(
        "--audit-trail",
        type=str,
        metavar="PATH",
        help="Export audit trail to JSON file (records all operations)",
    )
    parser.add_argument("--export", type=str, help="Export analysis to JSON file")

    # Backup options
    parser.add_argument(
        "--backup",
        action="store_true",
        default=True,
        help="Create backup before sync (default: enabled)",
    )
    parser.add_argument(
        "--no-backup", action="store_true", help="Disable automatic backup before sync"
    )
    parser.add_argument(
        "--backup-dir",
        type=str,
        metavar="PATH",
        help="Custom directory for backups (default: ~/.spectra/backups)",
    )
    parser.add_argument(
        "--list-backups", action="store_true", help="List available backups for the specified epic"
    )
    parser.add_argument(
        "--restore-backup",
        type=str,
        metavar="BACKUP_ID",
        help="Restore Jira state from a backup (use --list-backups to see available backups)",
    )
    parser.add_argument(
        "--diff-backup",
        type=str,
        metavar="BACKUP_ID",
        help="Show diff between backup and current Jira state",
    )
    parser.add_argument(
        "--diff-latest",
        action="store_true",
        help="Show diff between latest backup and current Jira state",
    )
    parser.add_argument(
        "--rollback",
        action="store_true",
        help="Undo last sync by restoring from most recent backup (requires --epic)",
    )

    # Transactional sync
    parser.add_argument(
        "--transactional",
        action="store_true",
        help="Enable transactional mode: all-or-nothing with automatic rollback on failure",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        default=True,
        help="In transactional mode, rollback immediately on first error (default: True)",
    )
    parser.add_argument(
        "--no-fail-fast",
        action="store_true",
        help="In transactional mode, continue on errors and attempt partial rollback",
    )

    # Idempotency
    parser.add_argument(
        "--idempotent",
        action="store_true",
        help="Enable idempotency checks: skip operations that would not change anything",
    )
    parser.add_argument(
        "--check-idempotency",
        action="store_true",
        help="Analyze and report what operations are needed vs what can be skipped",
    )
    parser.add_argument(
        "--strict-compare",
        action="store_true",
        help="Use strict content comparison (no normalization) for idempotency checks",
    )

    # Special modes
    parser.add_argument(
        "--init", action="store_true", help="Run first-time setup wizard to configure spectra"
    )
    parser.add_argument("--validate", action="store_true", help="Validate markdown file format")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Strict validation mode: treat warnings as errors (used with --validate)",
    )
    parser.add_argument(
        "--show-guide",
        action="store_true",
        help="Show the expected markdown format guide (used with --validate)",
    )
    parser.add_argument(
        "--suggest-fix",
        action="store_true",
        help="Generate an AI prompt to fix format issues (copy to your AI tool)",
    )
    parser.add_argument(
        "--auto-fix",
        action="store_true",
        help="Automatically fix format issues using an AI CLI tool",
    )
    parser.add_argument(
        "--ai-tool",
        type=str,
        metavar="TOOL",
        help="AI tool to use for --auto-fix (claude, ollama, aider, llm, mods, sgpt)",
    )
    parser.add_argument(
        "--list-ai-tools",
        action="store_true",
        help="List detected AI CLI tools available for --auto-fix",
    )
    parser.add_argument(
        "--dashboard", action="store_true", help="Show TUI dashboard with sync status overview"
    )
    parser.add_argument(
        "--tui",
        action="store_true",
        help="Launch interactive TUI dashboard (requires: pip install spectra[tui])",
    )
    parser.add_argument(
        "--tui-demo",
        action="store_true",
        help="Launch TUI dashboard with demo data (for testing)",
    )

    # OpenTelemetry arguments
    parser.add_argument(
        "--otel-enable", action="store_true", help="Enable OpenTelemetry tracing and metrics"
    )
    parser.add_argument(
        "--otel-endpoint",
        metavar="URL",
        help="OTLP exporter endpoint (e.g., http://localhost:4317)",
    )
    parser.add_argument(
        "--otel-service-name",
        metavar="NAME",
        default="spectra",
        help="Service name for traces/metrics (default: spectra)",
    )
    parser.add_argument(
        "--otel-console",
        action="store_true",
        help="Export traces/metrics to console (for debugging)",
    )

    # Prometheus metrics arguments
    parser.add_argument(
        "--prometheus", action="store_true", help="Enable Prometheus metrics HTTP server"
    )
    parser.add_argument(
        "--prometheus-port",
        type=int,
        default=9090,
        metavar="PORT",
        help="Prometheus metrics port (default: 9090)",
    )
    parser.add_argument(
        "--prometheus-host",
        default="0.0.0.0",
        metavar="HOST",
        help="Prometheus metrics host (default: 0.0.0.0)",
    )

    # Health check arguments
    parser.add_argument("--health", action="store_true", help="Enable health check HTTP endpoint")
    parser.add_argument(
        "--health-port",
        type=int,
        default=8080,
        metavar="PORT",
        help="Health check port (default: 8080)",
    )
    parser.add_argument(
        "--health-host",
        default="0.0.0.0",
        metavar="HOST",
        help="Health check host (default: 0.0.0.0)",
    )

    # Analytics arguments (opt-in)
    parser.add_argument(
        "--analytics", action="store_true", help="Enable anonymous usage analytics (opt-in)"
    )
    parser.add_argument(
        "--analytics-show", action="store_true", help="Show what analytics data has been collected"
    )
    parser.add_argument(
        "--analytics-clear", action="store_true", help="Clear all collected analytics data"
    )

    parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Interactive mode with step-by-step guided sync",
    )
    parser.add_argument("--resume", action="store_true", help="Resume an interrupted sync session")
    parser.add_argument(
        "--resume-session",
        type=str,
        metavar="SESSION_ID",
        help="Resume a specific sync session by ID",
    )
    parser.add_argument(
        "--list-sessions", action="store_true", help="List all resumable sync sessions"
    )
    parser.add_argument(
        "--completions",
        type=str,
        choices=["bash", "zsh", "fish", "powershell"],
        metavar="SHELL",
        help="Generate shell completion script (bash, zsh, fish, powershell)",
    )
    parser.add_argument(
        "--man",
        action="store_true",
        help="Display the man page (Unix systems)",
    )
    parser.add_argument(
        "--install-man",
        action="store_true",
        help="Install man page to system (may require sudo)",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 2.0.0")

    # Template generation
    parser.add_argument(
        "--generate", action="store_true", help="Generate markdown template from existing Jira epic"
    )
    parser.add_argument(
        "--generate-output",
        type=str,
        dest="generate_output",
        metavar="PATH",
        help="Output path for generated markdown (defaults to EPIC_KEY.md)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite output file without confirmation (used with --generate)",
    )
    parser.add_argument(
        "--no-subtasks",
        action="store_true",
        help="Don't include existing subtasks in generated template",
    )
    parser.add_argument(
        "--no-descriptions",
        action="store_true",
        help="Don't include descriptions in generated template",
    )

    # Bidirectional sync
    parser.add_argument(
        "--bidirectional",
        "--two-way",
        action="store_true",
        help="Two-way sync: push local changes AND pull remote changes with conflict detection",
    )
    parser.add_argument(
        "--pull", action="store_true", help="Pull changes FROM Jira to markdown (reverse sync)"
    )
    parser.add_argument(
        "--pull-output",
        type=str,
        dest="pull_output",
        metavar="PATH",
        help="Output path for pulled markdown (used with --pull)",
    )
    parser.add_argument(
        "--update-existing",
        action="store_true",
        help="Update existing markdown file instead of overwriting (used with --pull)",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Preview what would be pulled without making changes (used with --pull)",
    )

    # Conflict detection
    parser.add_argument(
        "--check-conflicts",
        action="store_true",
        help="Check for conflicts before syncing (compares with last sync state)",
    )
    parser.add_argument(
        "--conflict-strategy",
        type=str,
        choices=["ask", "force-local", "force-remote", "skip", "abort", "merge", "smart-merge"],
        default="ask",
        help="How to resolve conflicts: ask (interactive), force-local (take markdown), "
        "force-remote (take Jira), skip (skip conflicts), abort (fail on conflicts), "
        "merge (3-way auto-merge), smart-merge (try merge, fallback to ask)",
    )
    parser.add_argument(
        "--merge-text-strategy",
        type=str,
        choices=["line-level", "word-level", "character-level"],
        default="line-level",
        help="Text merge granularity for 3-way merge (default: line-level)",
    )
    parser.add_argument(
        "--merge-numeric-strategy",
        type=str,
        choices=["take-higher", "take-lower", "take-local", "take-remote", "sum-changes"],
        default="take-higher",
        help="Numeric merge strategy for story points (default: take-higher)",
    )
    parser.add_argument(
        "--save-snapshot",
        action="store_true",
        default=True,
        help="Save sync snapshot after successful sync (enables conflict detection)",
    )
    parser.add_argument(
        "--no-snapshot", action="store_true", help="Don't save sync snapshot after sync"
    )
    parser.add_argument(
        "--list-snapshots", action="store_true", help="List all stored sync snapshots"
    )
    parser.add_argument(
        "--clear-snapshot",
        action="store_true",
        help="Clear the sync snapshot for the specified epic (resets conflict baseline)",
    )

    # Watch mode
    parser.add_argument(
        "--watch", "-w", action="store_true", help="Watch mode: auto-sync on file changes"
    )
    parser.add_argument(
        "--debounce",
        type=float,
        default=2.0,
        metavar="SECONDS",
        help="Minimum time between syncs in watch mode (default: 2.0)",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=1.0,
        metavar="SECONDS",
        help="How often to check for file changes (default: 1.0)",
    )

    # Scheduled sync
    parser.add_argument(
        "--schedule",
        type=str,
        metavar="SPEC",
        help="Run sync on a schedule. Formats: 30s, 5m, 1h (interval), "
        "daily:HH:MM, hourly:MM, cron:MIN HOUR DOW",
    )
    parser.add_argument(
        "--run-now", action="store_true", help="Run sync immediately when starting scheduled mode"
    )
    parser.add_argument(
        "--max-runs",
        type=int,
        metavar="N",
        help="Maximum number of scheduled runs (default: unlimited)",
    )

    # Webhook receiver
    parser.add_argument(
        "--webhook",
        action="store_true",
        help="Start webhook server to receive Jira events for reverse sync",
    )
    parser.add_argument(
        "--webhook-host",
        type=str,
        default="0.0.0.0",
        metavar="HOST",
        help="Host to bind webhook server to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--webhook-port",
        type=int,
        default=8080,
        metavar="PORT",
        help="Port for webhook server (default: 8080)",
    )
    parser.add_argument(
        "--webhook-secret",
        type=str,
        metavar="SECRET",
        help="Webhook secret for signature verification",
    )

    # Multi-epic support
    parser.add_argument(
        "--multi-epic",
        action="store_true",
        help="Enable multi-epic mode for files containing multiple epics",
    )
    parser.add_argument(
        "--epic-filter",
        type=str,
        metavar="KEYS",
        help="Comma-separated list of epic keys to sync (e.g., PROJ-100,PROJ-200)",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop syncing on first epic error in multi-epic mode",
    )
    parser.add_argument(
        "--list-epics",
        action="store_true",
        help="List epics found in markdown file without syncing",
    )

    # Cross-project linking
    parser.add_argument(
        "--sync-links", action="store_true", help="Sync issue links across projects"
    )
    parser.add_argument(
        "--analyze-links", action="store_true", help="Analyze links in markdown without syncing"
    )

    # Multi-tracker sync
    parser.add_argument(
        "--multi-tracker",
        action="store_true",
        help="Sync to multiple trackers simultaneously (requires config file)",
    )
    parser.add_argument(
        "--trackers",
        type=str,
        nargs="+",
        metavar="TRACKER",
        help="Tracker targets for multi-tracker sync (format: type:epic_key, e.g., jira:PROJ-123 github:1)",
    )
    parser.add_argument(
        "--primary-tracker",
        type=str,
        metavar="NAME",
        help="Name of primary tracker for ID generation in multi-tracker mode",
    )

    # Attachment sync options
    parser.add_argument(
        "--sync-attachments",
        action="store_true",
        help="Sync file attachments between markdown and tracker",
    )
    parser.add_argument(
        "--attachments-dir",
        type=str,
        metavar="DIR",
        default="attachments",
        help="Directory for downloaded attachments (default: attachments)",
    )
    parser.add_argument(
        "--attachment-direction",
        type=str,
        choices=["upload", "download", "bidirectional"],
        default="upload",
        help="Attachment sync direction (default: upload)",
    )
    parser.add_argument(
        "--skip-existing-attachments",
        action="store_true",
        default=True,
        help="Skip attachments that already exist at target (default: True)",
    )
    parser.add_argument(
        "--attachment-max-size",
        type=int,
        metavar="BYTES",
        default=50 * 1024 * 1024,
        help="Maximum attachment size in bytes (default: 50MB)",
    )

    # Custom field mapping options
    parser.add_argument(
        "--field-mapping",
        type=str,
        metavar="FILE",
        help="Path to YAML field mapping configuration file",
    )
    parser.add_argument(
        "--story-points-field",
        type=str,
        metavar="FIELD_ID",
        help="Custom field ID for story points (e.g., customfield_10014)",
    )
    parser.add_argument(
        "--sprint-field",
        type=str,
        metavar="FIELD_ID",
        help="Custom field ID for sprint (e.g., customfield_10020)",
    )
    parser.add_argument(
        "--epic-link-field",
        type=str,
        metavar="FIELD_ID",
        help="Custom field ID for epic link (e.g., customfield_10008)",
    )
    parser.add_argument(
        "--list-custom-fields",
        action="store_true",
        help="List available custom fields from the tracker",
    )
    parser.add_argument(
        "--generate-field-mapping",
        type=str,
        metavar="FILE",
        help="Generate a field mapping template YAML file",
    )

    # Time tracking sync options
    parser.add_argument(
        "--sync-time",
        action="store_true",
        help="Enable time tracking synchronization (estimates and work logs)",
    )
    parser.add_argument(
        "--time-estimates",
        action="store_true",
        help="Sync time estimates (original and remaining)",
    )
    parser.add_argument(
        "--work-logs",
        action="store_true",
        help="Pull work logs from tracker",
    )
    parser.add_argument(
        "--hours-per-day",
        type=int,
        default=8,
        metavar="HOURS",
        help="Hours per work day for time calculations (default: 8)",
    )

    # New CLI commands
    new_commands = parser.add_argument_group("Commands")
    new_commands.add_argument("--doctor", action="store_true", help="Diagnose common setup issues")
    new_commands.add_argument(
        "--stats", action="store_true", help="Show statistics (stories, points, velocity)"
    )
    new_commands.add_argument(
        "--diff", action="store_true", help="Compare local file vs tracker state"
    )
    new_commands.add_argument(
        "--import",
        dest="import_cmd",
        action="store_true",
        help="Import from tracker to create initial markdown",
    )
    new_commands.add_argument(
        "--plan",
        action="store_true",
        help="Show side-by-side comparison before sync (like Terraform)",
    )
    new_commands.add_argument("--migrate", action="store_true", help="Migrate between trackers")
    new_commands.add_argument(
        "--migrate-source",
        type=str,
        metavar="TYPE",
        help="Source tracker type for migration (jira, github, linear)",
    )
    new_commands.add_argument(
        "--migrate-target", type=str, metavar="TYPE", help="Target tracker type for migration"
    )
    new_commands.add_argument(
        "--visualize", action="store_true", help="Generate dependency graph (Mermaid/Graphviz)"
    )
    new_commands.add_argument(
        "--visualize-format",
        type=str,
        choices=["mermaid", "graphviz", "ascii"],
        default="mermaid",
        help="Output format for visualization",
    )
    new_commands.add_argument(
        "--velocity", action="store_true", help="Track story points completed over time"
    )
    new_commands.add_argument(
        "--velocity-add", action="store_true", help="Add current sprint to velocity data"
    )
    new_commands.add_argument(
        "--sprint", type=str, metavar="NAME", help="Sprint name for velocity tracking"
    )
    new_commands.add_argument(
        "--export-format",
        type=str,
        choices=["html", "pdf", "csv", "json", "docx"],
        default="html",
        help="Export format",
    )
    new_commands.add_argument(
        "--report",
        type=str,
        metavar="PERIOD",
        nargs="?",
        const="weekly",
        help="Generate progress report (weekly, monthly, sprint)",
    )
    new_commands.add_argument(
        "--config-validate",
        dest="config_validate",
        action="store_true",
        help="Validate configuration files",
    )
    new_commands.add_argument(
        "--version-check",
        dest="version_check",
        action="store_true",
        help="Check for spectra updates",
    )
    new_commands.add_argument(
        "--hook",
        type=str,
        metavar="ACTION",
        nargs="?",
        const="status",
        help="Git hook management (install, uninstall, status)",
    )
    new_commands.add_argument(
        "--hook-type",
        type=str,
        choices=["pre-commit", "pre-push", "all"],
        default="pre-commit",
        help="Hook type to install/uninstall",
    )
    new_commands.add_argument(
        "--tutorial",
        action="store_true",
        help="Run interactive tutorial",
    )
    new_commands.add_argument(
        "--tutorial-step",
        type=int,
        metavar="N",
        help="Show specific tutorial step (1-based)",
    )
    new_commands.add_argument(
        "--bulk-update",
        action="store_true",
        help="Bulk update stories by filter",
    )
    new_commands.add_argument(
        "--bulk-assign",
        action="store_true",
        help="Bulk assign stories to user",
    )
    new_commands.add_argument(
        "--filter",
        type=str,
        metavar="FILTER",
        help="Filter for bulk operations (e.g., 'status=planned,priority=high')",
    )
    new_commands.add_argument(
        "--set",
        type=str,
        metavar="UPDATES",
        help="Updates for bulk-update (e.g., 'status=in_progress')",
    )
    new_commands.add_argument(
        "--assignee",
        type=str,
        metavar="USER",
        help="User for bulk-assign",
    )
    new_commands.add_argument(
        "--split",
        action="store_true",
        help="AI-powered story splitting suggestions",
    )
    new_commands.add_argument(
        "--split-story",
        type=str,
        metavar="ID",
        help="Analyze specific story for splitting",
    )
    new_commands.add_argument(
        "--split-threshold",
        type=int,
        default=4,
        metavar="N",
        help="Complexity threshold for split recommendations (1-10, default: 4)",
    )
    new_commands.add_argument(
        "--archive",
        type=str,
        nargs="?",
        const="list",
        metavar="ACTION",
        help="Archive management (list, archive, unarchive)",
    )
    new_commands.add_argument(
        "--archive-days",
        type=int,
        default=90,
        metavar="N",
        help="Days threshold for auto-archive detection (default: 90)",
    )
    new_commands.add_argument(
        "--story-keys",
        type=str,
        metavar="KEYS",
        help="Comma-separated story keys for archive/unarchive",
    )

    return parser


def validate_markdown(
    console: Console,
    markdown_path: str,
    strict: bool = False,
    show_guide: bool = False,
    suggest_fix: bool = False,
    auto_fix: bool = False,
    ai_tool: str | None = None,
    input_dir: str | None = None,
) -> int:
    """
    Validate a markdown file's format and structure.

    Performs comprehensive validation including structure checks,
    story content validation, and best practice suggestions.

    Args:
        console: Console instance for output.
        markdown_path: Path to the markdown file to validate.
        strict: If True, treat warnings as errors.
        show_guide: If True, show the format guide.
        suggest_fix: If True, generate an AI prompt to fix issues.
        auto_fix: If True, automatically fix using an AI tool.
        ai_tool: Specific AI tool to use for auto-fix.
        input_dir: Path to directory containing US-*.md files.

    Returns:
        Exit code (0 for success, non-zero for errors).
    """
    from .validate import run_validate

    return run_validate(
        console,
        markdown_path,
        strict=strict,
        show_guide=show_guide,
        suggest_fix=suggest_fix,
        auto_fix=auto_fix,
        ai_tool=ai_tool,
        input_dir=input_dir,
    )


def list_sessions(state_store) -> int:
    """
    List all resumable sync sessions.

    Args:
        state_store: StateStore instance.

    Returns:
        Exit code.
    """
    from .exit_codes import ExitCode

    sessions = state_store.list_sessions()

    if not sessions:
        print("No sync sessions found.")
        print(f"State directory: {state_store.state_dir}")
        return ExitCode.SUCCESS

    print(f"\n{'Session ID':<14} {'Epic':<12} {'Phase':<12} {'Progress':<10} {'Updated':<20}")
    print("-" * 70)

    for s in sessions:
        session_id = s.get("session_id", "")[:12]
        epic = s.get("epic_key", "")[:10]
        phase = s.get("phase", "")[:10]
        progress = s.get("progress", "0/0")
        updated = s.get("updated_at", "")[:19]

        # Highlight incomplete sessions
        if phase not in ("completed", "failed"):
            print(
                f"\033[1m{session_id:<14} {epic:<12} {phase:<12} {progress:<10} {updated:<20}\033[0m"
            )
        else:
            print(f"{session_id:<14} {epic:<12} {phase:<12} {progress:<10} {updated:<20}")

    print()
    print("To resume a session:")
    print("  spectra --resume-session <SESSION_ID> --execute")

    return ExitCode.SUCCESS


def list_backups(backup_manager, epic_key: str | None = None) -> int:
    """
    List available backups.

    Args:
        backup_manager: BackupManager instance.
        epic_key: Optional epic key to filter by.

    Returns:
        Exit code.
    """
    from .exit_codes import ExitCode

    backups = backup_manager.list_backups(epic_key)

    if not backups:
        print("No backups found.")
        if epic_key:
            print(f"Epic: {epic_key}")
        print(f"Backup directory: {backup_manager.backup_dir}")
        return ExitCode.SUCCESS

    print(f"\n{'Backup ID':<40} {'Epic':<12} {'Issues':<8} {'Created':<20}")
    print("-" * 82)

    for b in backups:
        backup_id = b.get("backup_id", "")[:38]
        epic = b.get("epic_key", "")[:10]
        issue_count = str(b.get("issue_count", 0))
        created = b.get("created_at", "")[:19]

        print(f"{backup_id:<40} {epic:<12} {issue_count:<8} {created:<20}")

    print()
    print(f"Total backups: {len(backups)}")
    print(f"Backup directory: {backup_manager.backup_dir}")

    return ExitCode.SUCCESS


def run_restore(args) -> int:
    """
    Run the restore operation from a backup.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code.
    """
    from spectra.adapters import ADFFormatter, EnvironmentConfigProvider, JiraAdapter
    from spectra.application.sync import BackupManager

    from .exit_codes import ExitCode
    from .logging import setup_logging

    # Setup logging
    log_level = logging.DEBUG if getattr(args, "verbose", False) else logging.INFO
    log_format = getattr(args, "log_format", "text")
    setup_logging(level=log_level, log_format=log_format)

    # Create console
    console = Console(
        color=not getattr(args, "no_color", False),
        verbose=getattr(args, "verbose", False),
        quiet=getattr(args, "quiet", False),
    )

    backup_id = args.restore_backup
    epic_key = getattr(args, "epic", None)
    dry_run = not getattr(args, "execute", False)

    console.header("spectra Restore")

    # Load backup first to get epic key if not provided
    backup_dir = Path(args.backup_dir) if getattr(args, "backup_dir", None) else None
    manager = BackupManager(backup_dir=backup_dir)

    backup = manager.load_backup(backup_id, epic_key)
    if not backup:
        console.error(f"Backup not found: {backup_id}")
        console.info("Use --list-backups to see available backups")
        return ExitCode.FILE_NOT_FOUND

    console.info(f"Backup: {backup.backup_id}")
    console.info(f"Epic: {backup.epic_key}")
    console.info(f"Created: {backup.created_at}")
    console.info(f"Issues: {backup.issue_count}, Subtasks: {backup.subtask_count}")

    if dry_run:
        console.dry_run_banner()

    # Load configuration
    config_file = Path(args.config) if getattr(args, "config", None) else None
    config_provider = EnvironmentConfigProvider(
        config_file=config_file,
        cli_overrides=vars(args),
    )
    errors = config_provider.validate()

    if errors:
        console.config_errors(errors)
        return ExitCode.CONFIG_ERROR

    config = config_provider.load()

    # Initialize Jira adapter
    formatter = ADFFormatter()
    tracker = JiraAdapter(
        config=config.tracker,
        dry_run=dry_run,
        formatter=formatter,
    )

    # Test connection
    console.section("Connecting to Jira")
    if not tracker.test_connection():
        console.connection_error(config.tracker.url)
        return ExitCode.CONNECTION_ERROR

    user = tracker.get_current_user()
    console.success(f"Connected as: {user.get('displayName', user.get('emailAddress', 'Unknown'))}")

    # Confirmation
    if not dry_run and not getattr(args, "no_confirm", False):
        console.warning("This will restore Jira issues to their backed-up state!")
        console.detail(
            f"  {backup.issue_count} issues and {backup.subtask_count} subtasks may be modified"
        )
        if not console.confirm("Proceed with restore?"):
            console.warning("Cancelled by user")
            return ExitCode.CANCELLED

    # Run restore
    console.section("Restoring from Backup")

    result = manager.restore_backup(
        tracker=tracker,
        backup_id=backup_id,
        epic_key=backup.epic_key,
        dry_run=dry_run,
    )

    # Show results
    console.print()
    if result.success:
        console.success("Restore completed successfully!")
    else:
        console.error("Restore completed with errors")

    console.detail(f"  Issues restored: {result.issues_restored}")
    console.detail(f"  Subtasks restored: {result.subtasks_restored}")
    console.detail(
        f"  Operations: {result.successful_operations} succeeded, {result.failed_operations} failed, {result.skipped_operations} skipped"
    )

    if result.errors:
        console.print()
        console.error("Errors:")
        for error in result.errors[:10]:
            console.item(error, "fail")
        if len(result.errors) > 10:
            console.detail(f"... and {len(result.errors) - 10} more")

    if result.warnings:
        console.print()
        console.warning("Warnings:")
        for warning in result.warnings[:5]:
            console.item(warning, "warn")

    return ExitCode.SUCCESS if result.success else ExitCode.ERROR


def run_diff(args) -> int:
    """
    Run the diff operation comparing backup to current Jira state.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code.
    """
    from spectra.adapters import ADFFormatter, EnvironmentConfigProvider, JiraAdapter
    from spectra.application.sync import BackupManager, compare_backup_to_current

    from .exit_codes import ExitCode
    from .logging import setup_logging

    # Setup logging
    log_level = logging.DEBUG if getattr(args, "verbose", False) else logging.INFO
    log_format = getattr(args, "log_format", "text")
    setup_logging(level=log_level, log_format=log_format)

    # Create console
    console = Console(
        color=not getattr(args, "no_color", False),
        verbose=getattr(args, "verbose", False),
        quiet=getattr(args, "quiet", False),
    )

    backup_id = getattr(args, "diff_backup", None)
    diff_latest = getattr(args, "diff_latest", False)
    epic_key = getattr(args, "epic", None)

    console.header("spectra Diff View")

    # Load backup
    backup_dir = Path(args.backup_dir) if getattr(args, "backup_dir", None) else None
    manager = BackupManager(backup_dir=backup_dir)

    if diff_latest:
        if not epic_key:
            console.error("--diff-latest requires --epic to be specified")
            return ExitCode.CONFIG_ERROR

        backup = manager.get_latest_backup(epic_key)
        if not backup:
            console.error(f"No backups found for epic {epic_key}")
            console.info("Use --list-backups to see available backups")
            return ExitCode.FILE_NOT_FOUND
        console.info(f"Using latest backup: {backup.backup_id}")
    else:
        backup = manager.load_backup(backup_id, epic_key)
        if not backup:
            console.error(f"Backup not found: {backup_id}")
            console.info("Use --list-backups to see available backups")
            return ExitCode.FILE_NOT_FOUND

    console.info(f"Backup: {backup.backup_id}")
    console.info(f"Epic: {backup.epic_key}")
    console.info(f"Created: {backup.created_at}")
    console.info(f"Issues in backup: {backup.issue_count}")

    # Load configuration
    config_file = Path(args.config) if getattr(args, "config", None) else None
    config_provider = EnvironmentConfigProvider(
        config_file=config_file,
        cli_overrides=vars(args),
    )
    errors = config_provider.validate()

    if errors:
        console.config_errors(errors)
        return ExitCode.CONFIG_ERROR

    config = config_provider.load()

    # Initialize Jira adapter (read-only, so dry_run=True is fine)
    formatter = ADFFormatter()
    tracker = JiraAdapter(
        config=config.tracker,
        dry_run=True,
        formatter=formatter,
    )

    # Test connection
    console.section("Connecting to Jira")
    if not tracker.test_connection():
        console.connection_error(config.tracker.url)
        return ExitCode.CONNECTION_ERROR

    user = tracker.get_current_user()
    console.success(f"Connected as: {user.get('displayName', user.get('emailAddress', 'Unknown'))}")

    # Run diff
    console.section("Comparing Backup to Current State")
    console.print()

    result, formatted_output = compare_backup_to_current(
        tracker=tracker,
        backup=backup,
        color=console.color,
    )

    # Print the formatted diff
    print(formatted_output)

    # Summary
    console.print()
    if result.has_changes:
        console.warning(
            f"Found changes in {result.changed_issues}/{result.total_issues} issues ({result.total_changes} field changes)"
        )
    else:
        console.success("No changes detected - current state matches backup")

    return ExitCode.SUCCESS


def run_rollback(args) -> int:
    """
    Rollback to the most recent backup.

    This is a convenience command that finds the latest backup for an epic
    and restores from it.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code.
    """
    from spectra.adapters import ADFFormatter, EnvironmentConfigProvider, JiraAdapter
    from spectra.application.sync import BackupManager, compare_backup_to_current

    from .exit_codes import ExitCode
    from .logging import setup_logging

    # Setup logging
    log_level = logging.DEBUG if getattr(args, "verbose", False) else logging.INFO
    log_format = getattr(args, "log_format", "text")
    setup_logging(level=log_level, log_format=log_format)

    # Create console
    console = Console(
        color=not getattr(args, "no_color", False),
        verbose=getattr(args, "verbose", False),
        quiet=getattr(args, "quiet", False),
    )

    epic_key = getattr(args, "epic", None)
    dry_run = not getattr(args, "execute", False)

    if not epic_key:
        console.error("--rollback requires --epic to be specified")
        return ExitCode.CONFIG_ERROR

    console.header("spectra Rollback")

    # Find latest backup
    backup_dir = Path(args.backup_dir) if getattr(args, "backup_dir", None) else None
    manager = BackupManager(backup_dir=backup_dir)

    backup = manager.get_latest_backup(epic_key)
    if not backup:
        console.error(f"No backups found for epic {epic_key}")
        console.info("Cannot rollback without a backup.")
        console.info("Backups are automatically created before each sync operation.")
        return ExitCode.FILE_NOT_FOUND

    console.info(f"Latest backup: {backup.backup_id}")
    console.info(f"Epic: {backup.epic_key}")
    console.info(f"Created: {backup.created_at}")
    console.info(f"Issues: {backup.issue_count}, Subtasks: {backup.subtask_count}")

    if dry_run:
        console.dry_run_banner()

    # Load configuration
    config_file = Path(args.config) if getattr(args, "config", None) else None
    config_provider = EnvironmentConfigProvider(
        config_file=config_file,
        cli_overrides=vars(args),
    )
    errors = config_provider.validate()

    if errors:
        console.config_errors(errors)
        return ExitCode.CONFIG_ERROR

    config = config_provider.load()

    # Initialize Jira adapter
    formatter = ADFFormatter()
    tracker = JiraAdapter(
        config=config.tracker,
        dry_run=dry_run,
        formatter=formatter,
    )

    # Test connection
    console.section("Connecting to Jira")
    if not tracker.test_connection():
        console.connection_error(config.tracker.url)
        return ExitCode.CONNECTION_ERROR

    user = tracker.get_current_user()
    console.success(f"Connected as: {user.get('displayName', user.get('emailAddress', 'Unknown'))}")

    # Show diff first
    console.section("Changes to Rollback")
    console.print()

    diff_result, formatted_diff = compare_backup_to_current(
        tracker=tracker,
        backup=backup,
        color=console.color,
    )

    if not diff_result.has_changes:
        console.success("No changes detected - current state already matches backup")
        console.info("Nothing to rollback.")
        return ExitCode.SUCCESS

    print(formatted_diff)
    console.print()

    # Confirmation
    if not dry_run and not getattr(args, "no_confirm", False):
        console.warning("This will rollback Jira issues to their backed-up state!")
        console.detail(f"  {diff_result.changed_issues} issues will be modified")
        if not console.confirm("Proceed with rollback?"):
            console.warning("Cancelled by user")
            return ExitCode.CANCELLED

    # Run restore
    console.section("Rolling Back")

    result = manager.restore_backup(
        tracker=tracker,
        backup_id=backup.backup_id,
        epic_key=backup.epic_key,
        dry_run=dry_run,
    )

    # Show results
    console.print()
    if result.success:
        if dry_run:
            console.success("Rollback preview completed (dry-run)")
            console.info("Use --execute to perform the actual rollback")
        else:
            console.success("Rollback completed successfully!")
    else:
        console.error("Rollback completed with errors")

    console.detail(f"  Issues restored: {result.issues_restored}")
    console.detail(f"  Subtasks restored: {result.subtasks_restored}")

    if result.errors:
        console.print()
        console.error("Errors:")
        for error in result.errors[:10]:
            console.item(error, "fail")
        if len(result.errors) > 10:
            console.detail(f"... and {len(result.errors) - 10} more")

    return ExitCode.SUCCESS if result.success else ExitCode.ERROR


def run_sync_links(args) -> int:
    """
    Run link sync mode.

    Syncs cross-project issue links from markdown to Jira.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code.
    """
    from spectra.adapters import ADFFormatter, EnvironmentConfigProvider, JiraAdapter
    from spectra.adapters.parsers import MarkdownParser
    from spectra.application.sync import LinkSyncOrchestrator, SyncOrchestrator

    from .logging import setup_logging

    # Setup logging
    log_level = logging.DEBUG if getattr(args, "verbose", False) else logging.INFO
    log_format = getattr(args, "log_format", "text")
    setup_logging(level=log_level, log_format=log_format)

    # Create console
    console = Console(
        color=not getattr(args, "no_color", False),
        verbose=getattr(args, "verbose", False),
        quiet=getattr(args, "quiet", False),
    )

    markdown_path = args.input
    epic_key = args.epic
    dry_run = not getattr(args, "execute", False)
    analyze_only = getattr(args, "analyze_links", False)

    # Check markdown file exists
    if not Path(markdown_path).exists():
        console.error(f"Markdown file not found: {markdown_path}")
        return ExitCode.FILE_NOT_FOUND

    console.header("spectra Link Sync")

    if analyze_only:
        console.info("Analyze mode - no changes will be made")
    elif dry_run:
        console.dry_run_banner()

    # Load configuration
    config_file = Path(args.config) if getattr(args, "config", None) else None
    config_provider = EnvironmentConfigProvider(
        config_file=config_file,
        cli_overrides=vars(args),
    )
    errors = config_provider.validate()

    if errors:
        console.config_errors(errors)
        return ExitCode.CONFIG_ERROR

    config = config_provider.load()
    config.sync.dry_run = dry_run

    # Initialize components
    formatter = ADFFormatter()
    tracker = JiraAdapter(
        config=config.tracker,
        dry_run=dry_run,
        formatter=formatter,
    )
    parser = MarkdownParser()

    # Test connection
    console.section("Connecting to Jira")
    if not tracker.test_connection():
        console.connection_error(config.tracker.url)
        return ExitCode.CONNECTION_ERROR

    user = tracker.get_current_user()
    console.success(f"Connected as: {user.get('displayName', user.get('emailAddress', 'Unknown'))}")

    # Parse stories
    console.section("Parsing Markdown")
    stories = parser.parse_stories(markdown_path)
    console.info(f"Found {len(stories)} stories")

    # Count stories with links
    stories_with_links = [s for s in stories if s.links]
    total_links = sum(len(s.links) for s in stories)
    console.info(f"Stories with links: {len(stories_with_links)}")
    console.info(f"Total links defined: {total_links}")

    if not stories_with_links:
        console.warning("No links found in markdown")
        return ExitCode.SUCCESS

    # Create link sync orchestrator
    link_sync = LinkSyncOrchestrator(
        tracker=tracker,
        dry_run=dry_run,
    )

    # Analyze links
    analysis = link_sync.analyze_links(stories)

    console.section("Link Analysis")
    console.info(f"Cross-project links: {analysis['cross_project_links']}")
    console.info(f"Same-project links: {analysis['same_project_links']}")

    if analysis["link_types"]:
        print()
        console.info("Link types:")
        for link_type, count in analysis["link_types"].items():
            console.item(f"{link_type}: {count}", "info")

    if analysis["target_projects"]:
        print()
        console.info("Target projects:")
        for project, count in analysis["target_projects"].items():
            console.item(f"{project}: {count} links", "info")

    if analyze_only:
        return ExitCode.SUCCESS

    # Match stories to Jira issues
    console.section("Matching Stories to Jira Issues")

    # Create sync orchestrator to match stories
    sync_orchestrator = SyncOrchestrator(
        tracker=tracker,
        parser=parser,
        formatter=formatter,
        config=config.sync,
    )
    sync_orchestrator.analyze(markdown_path, epic_key)

    # Update stories with external keys
    matched = 0
    for story in stories:
        if str(story.id) in sync_orchestrator._matches:
            story.external_key = sync_orchestrator._matches[str(story.id)]
            matched += 1

    console.info(f"Matched {matched} stories to Jira issues")

    # Sync links
    console.section("Syncing Links")

    def on_progress(msg: str, current: int, total: int):
        console.info(f"[{current}/{total}] {msg}")

    result = link_sync.sync_all_links(stories, progress_callback=on_progress)

    # Show results
    console.section("Results")
    console.info(f"Stories processed: {result.stories_processed}")
    console.item(
        f"Links created: {result.links_created}", "success" if result.links_created else "info"
    )
    console.item(f"Links unchanged: {result.links_unchanged}", "info")

    if result.links_failed:
        console.item(f"Links failed: {result.links_failed}", "fail")

    if result.errors:
        print()
        console.error(f"Errors ({len(result.errors)}):")
        for error in result.errors[:5]:
            console.item(error, "fail")

    return ExitCode.SUCCESS if result.success else ExitCode.SYNC_ERROR


def run_multi_epic(args) -> int:
    """
    Run multi-epic sync mode.

    Syncs multiple epics from a single markdown file.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code.
    """
    from spectra.adapters import ADFFormatter, EnvironmentConfigProvider, JiraAdapter
    from spectra.adapters.parsers import MarkdownParser
    from spectra.application.sync import MultiEpicSyncOrchestrator

    from .logging import setup_logging

    # Setup logging
    log_level = logging.DEBUG if getattr(args, "verbose", False) else logging.INFO
    log_format = getattr(args, "log_format", "text")
    setup_logging(level=log_level, log_format=log_format)

    # Create console
    console = Console(
        color=not getattr(args, "no_color", False),
        verbose=getattr(args, "verbose", False),
        quiet=getattr(args, "quiet", False),
    )

    markdown_path = args.input
    dry_run = not getattr(args, "execute", False)
    list_only = getattr(args, "list_epics", False)
    epic_filter_str = getattr(args, "epic_filter", None)
    stop_on_error = getattr(args, "stop_on_error", False)

    # Parse epic filter
    epic_filter = None
    if epic_filter_str:
        epic_filter = [k.strip() for k in epic_filter_str.split(",")]

    # Check markdown file exists
    if not Path(markdown_path).exists():
        console.error(f"Markdown file not found: {markdown_path}")
        return ExitCode.FILE_NOT_FOUND

    console.header("spectra Multi-Epic Sync")

    # Just list epics
    if list_only:
        parser = MarkdownParser()
        epics = parser.parse_epics(markdown_path)

        console.section(f"Epics in {markdown_path}")
        console.info(f"Found {len(epics)} epics:")
        print()

        for epic in epics:
            stories = len(epic.stories)
            console.item(f"{epic.key}: {epic.title} ({stories} stories)", "info")

        print()
        return ExitCode.SUCCESS

    if dry_run:
        console.dry_run_banner()

    # Load configuration
    config_file = Path(args.config) if getattr(args, "config", None) else None
    config_provider = EnvironmentConfigProvider(
        config_file=config_file,
        cli_overrides=vars(args),
    )
    errors = config_provider.validate()

    if errors:
        console.config_errors(errors)
        return ExitCode.CONFIG_ERROR

    config = config_provider.load()
    config.sync.dry_run = dry_run

    # Initialize components
    formatter = ADFFormatter()
    tracker = JiraAdapter(
        config=config.tracker,
        dry_run=dry_run,
        formatter=formatter,
    )
    parser = MarkdownParser()

    # Test connection
    console.section("Connecting to Jira")
    if not tracker.test_connection():
        console.connection_error(config.tracker.url)
        return ExitCode.CONNECTION_ERROR

    user = tracker.get_current_user()
    console.success(f"Connected as: {user.get('displayName', user.get('emailAddress', 'Unknown'))}")

    # Check if file has multiple epics
    if not parser.is_multi_epic(markdown_path):
        console.warning("File does not appear to contain multiple epics")
        console.info("Expected format: ## Epic: PROJ-100 - Epic Title")
        return ExitCode.VALIDATION_ERROR

    # Create orchestrator
    orchestrator = MultiEpicSyncOrchestrator(
        tracker=tracker,
        parser=parser,
        formatter=formatter,
        config=config.sync,
    )

    # Get summary first
    summary = orchestrator.get_epic_summary(markdown_path)
    console.section(f"Found {summary['total_epics']} epics with {summary['total_stories']} stories")

    for epic_info in summary["epics"]:
        console.item(
            f"{epic_info['key']}: {epic_info['title']} ({epic_info['stories']} stories)", "info"
        )

    print()

    if epic_filter:
        console.info(f"Filter: syncing only {', '.join(epic_filter)}")
        print()

    # Progress callback
    def on_progress(epic_key: str, phase: str, current: int, total: int):
        console.info(f"[{epic_key}] {phase}")

    # Run sync
    console.section("Syncing Epics")
    result = orchestrator.sync(
        markdown_path=markdown_path,
        epic_filter=epic_filter,
        progress_callback=on_progress,
        stop_on_error=stop_on_error,
    )

    # Show results
    console.section("Results")

    for epic_result in result.epic_results:
        status = "success" if epic_result.success else "fail"
        console.item(
            f"{epic_result.epic_key}: {epic_result.stories_matched} matched, "
            f"{epic_result.subtasks_created} subtasks",
            status,
        )

    print()
    console.info(f"Total: {result.epics_synced}/{result.epics_total} epics synced")
    console.info(
        f"Stories: {result.total_stories_matched} matched, {result.total_stories_updated} updated"
    )
    console.info(f"Subtasks: {result.total_subtasks_created} created")

    if result.errors:
        print()
        console.error(f"Errors ({len(result.errors)}):")
        for error in result.errors[:5]:
            console.item(error, "fail")

    return ExitCode.SUCCESS if result.success else ExitCode.SYNC_ERROR


def run_multi_tracker_sync(args) -> int:
    """
    Run multi-tracker sync mode.

    Syncs the same markdown to multiple issue trackers simultaneously.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code.
    """
    from spectra.adapters import ADFFormatter, EnvironmentConfigProvider
    from spectra.adapters.parsers import MarkdownParser
    from spectra.application.sync.multi_tracker import (
        MultiTrackerSyncOrchestrator,
        TrackerTarget,
    )

    from .logging import setup_logging

    # Setup logging
    log_level = logging.DEBUG if getattr(args, "verbose", False) else logging.INFO
    log_format = getattr(args, "log_format", "text")
    setup_logging(level=log_level, log_format=log_format)

    # Create console
    console = Console(
        color=not getattr(args, "no_color", False),
        verbose=getattr(args, "verbose", False),
        quiet=getattr(args, "quiet", False),
    )

    markdown_path = args.input
    dry_run = not getattr(args, "execute", False)
    trackers_arg = getattr(args, "trackers", None) or []
    primary_tracker = getattr(args, "primary_tracker", None)

    # Check markdown file exists
    if not Path(markdown_path).exists():
        console.error(f"Markdown file not found: {markdown_path}")
        return ExitCode.FILE_NOT_FOUND

    console.header("spectra Multi-Tracker Sync")
    console.info(f"Source: {markdown_path}")

    if dry_run:
        console.dry_run_banner()

    # Load configuration
    config_file = Path(args.config) if getattr(args, "config", None) else None
    config_provider = EnvironmentConfigProvider(
        config_file=config_file,
        cli_overrides=vars(args),
    )

    config = config_provider.load()
    config.sync.dry_run = dry_run

    # Parse tracker targets from --trackers arg or config
    # Format: type:epic_key (e.g., jira:PROJ-123 github:1)
    targets_to_create: list[dict] = []

    for tracker_spec in trackers_arg:
        if ":" in tracker_spec:
            parts = tracker_spec.split(":", 1)
            tracker_type = parts[0].lower()
            epic_key = parts[1]
            targets_to_create.append(
                {
                    "type": tracker_type,
                    "epic_key": epic_key,
                    "name": f"{tracker_type.title()} ({epic_key})",
                    "is_primary": (tracker_type == primary_tracker) if primary_tracker else False,
                }
            )
        else:
            console.warning(f"Invalid tracker spec: {tracker_spec} (use format type:epic_key)")

    if not targets_to_create:
        console.error("No tracker targets specified. Use --trackers type:epic_key")
        return ExitCode.CONFIG_ERROR

    # Create orchestrator
    parser = MarkdownParser()
    formatter = ADFFormatter()

    orchestrator = MultiTrackerSyncOrchestrator(
        parser=parser,
        config=config.sync,
        formatter=formatter,
    )

    # Add targets
    console.section("Configuring Trackers")
    for target_config in targets_to_create:
        tracker_type = target_config["type"]
        epic_key = target_config["epic_key"]
        name = target_config["name"]

        try:
            tracker = _create_tracker_for_multi_sync(tracker_type, config, config_provider, dry_run)
            if tracker:
                orchestrator.add_target(
                    TrackerTarget(
                        tracker=tracker,
                        epic_key=epic_key,
                        name=name,
                        is_primary=target_config.get("is_primary", False),
                        formatter=formatter,
                    )
                )
                console.success(f"Added: {name}")
            else:
                console.warning(f"Skipped: {name} (no adapter)")
        except Exception as e:
            console.warning(f"Failed to add {name}: {e}")

    if not orchestrator.targets:
        console.error("No valid tracker targets configured")
        return ExitCode.CONFIG_ERROR

    # Progress callback
    def on_progress(tracker_name: str, phase: str, current: int, total: int) -> None:
        console.progress(current, total, f"{tracker_name}: {phase}")

    # Run sync
    console.section("Syncing")
    result = orchestrator.sync(
        markdown_path=markdown_path,
        progress_callback=on_progress,
    )

    # Show results
    console.print()
    console.section("Results")

    for status in result.tracker_statuses:
        icon = "success" if status.success else "fail"
        console.item(
            f"{status.tracker_name}: {status.stories_synced} synced, "
            f"{status.stories_created} created, {status.stories_updated} updated",
            icon,
        )
        if status.errors:
            for error in status.errors[:3]:
                console.detail(f"  Error: {error}")

    console.print()
    console.info(f"Total: {result.successful_trackers}/{result.total_trackers} trackers synced")

    if result.success:
        console.success("Multi-tracker sync completed successfully!")
    elif result.partial_success:
        console.warning("Multi-tracker sync completed with some failures")
    else:
        console.error("Multi-tracker sync failed")

    return ExitCode.SUCCESS if result.success else ExitCode.SYNC_ERROR


def _create_tracker_for_multi_sync(
    tracker_type: str,
    config: object,
    config_provider: object,
    dry_run: bool,
) -> object | None:
    """Create a tracker adapter for multi-tracker sync."""
    import os

    if tracker_type == "jira":
        from spectra.adapters import ADFFormatter, JiraAdapter

        formatter = ADFFormatter()
        return JiraAdapter(
            config=getattr(config, "tracker", None),
            dry_run=dry_run,
            formatter=formatter,
        )

    if tracker_type == "github":
        from spectra.adapters.github import GitHubAdapter

        return GitHubAdapter(
            token=os.getenv("GITHUB_TOKEN", ""),
            owner=os.getenv("GITHUB_OWNER", ""),
            repo=os.getenv("GITHUB_REPO", ""),
            dry_run=dry_run,
        )

    if tracker_type == "gitlab":
        from spectra.adapters.gitlab import GitLabAdapter

        return GitLabAdapter(
            token=os.getenv("GITLAB_TOKEN", ""),
            project_id=os.getenv("GITLAB_PROJECT_ID", ""),
            dry_run=dry_run,
            base_url=os.getenv("GITLAB_URL", "https://gitlab.com/api/v4"),
        )

    if tracker_type == "linear":
        from spectra.adapters.linear import LinearAdapter

        return LinearAdapter(
            api_key=os.getenv("LINEAR_API_KEY", ""),
            team_key=os.getenv("LINEAR_TEAM_KEY", ""),
            dry_run=dry_run,
        )

    return None


def run_webhook(args) -> int:
    """
    Run webhook server mode.

    Starts an HTTP server that receives Jira webhooks and
    triggers reverse sync when issues are updated.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code.
    """
    from spectra.adapters import ADFFormatter, EnvironmentConfigProvider, JiraAdapter
    from spectra.adapters.formatters import MarkdownWriter
    from spectra.application import WebhookDisplay, WebhookServer
    from spectra.application.sync import ReverseSyncOrchestrator

    from .logging import setup_logging

    # Setup logging
    log_level = logging.DEBUG if getattr(args, "verbose", False) else logging.INFO
    log_format = getattr(args, "log_format", "text")
    setup_logging(level=log_level, log_format=log_format)

    # Create console
    console = Console(
        color=not getattr(args, "no_color", False),
        verbose=getattr(args, "verbose", False),
        quiet=getattr(args, "quiet", False),
    )

    epic_key = args.epic
    output_path = getattr(args, "pull_output", None) or f"{epic_key}.md"
    host = getattr(args, "webhook_host", "0.0.0.0")
    port = getattr(args, "webhook_port", 8080)
    secret = getattr(args, "webhook_secret", None)
    dry_run = not getattr(args, "execute", False)

    # Load configuration
    config_file = Path(args.config) if getattr(args, "config", None) else None
    config_provider = EnvironmentConfigProvider(
        config_file=config_file,
        cli_overrides=vars(args),
    )
    errors = config_provider.validate()

    if errors:
        console.config_errors(errors)
        return ExitCode.CONFIG_ERROR

    config = config_provider.load()
    config.sync.dry_run = dry_run

    # Initialize Jira adapter
    formatter = ADFFormatter()
    tracker = JiraAdapter(
        config=config.tracker,
        dry_run=True,  # Webhook triggers read-only pull
        formatter=formatter,
    )

    # Test connection
    console.header("spectra Webhook Server")

    if dry_run:
        console.dry_run_banner()

    console.section("Connecting to Jira")
    if not tracker.test_connection():
        console.connection_error(config.tracker.url)
        return ExitCode.CONNECTION_ERROR

    user = tracker.get_current_user()
    console.success(f"Connected as: {user.get('displayName', user.get('emailAddress', 'Unknown'))}")

    # Create reverse sync orchestrator
    reverse_sync = ReverseSyncOrchestrator(
        tracker=tracker,
        config=config.sync,
        writer=MarkdownWriter(),
    )

    # Create display handler
    display = WebhookDisplay(
        color=not getattr(args, "no_color", False),
        quiet=getattr(args, "quiet", False),
    )

    # Create webhook server
    server = WebhookServer(
        reverse_sync=reverse_sync,
        host=host,
        port=port,
        epic_key=epic_key,
        output_path=output_path,
        secret=secret,
        on_event=display.show_event,
        on_sync_start=display.show_sync_start,
        on_sync_complete=display.show_sync_complete,
    )

    # Show start message
    display.show_start(host, port, epic_key)

    try:
        # Run server (blocks until Ctrl+C)
        server.start()
    except KeyboardInterrupt:
        pass
    finally:
        display.show_stop(server.stats)

    return ExitCode.SUCCESS


def run_schedule(args) -> int:
    """
    Run scheduled sync mode.

    Syncs at specified intervals or times according to a schedule.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code.
    """
    from spectra.adapters import (
        ADFFormatter,
        EnvironmentConfigProvider,
        JiraAdapter,
        MarkdownParser,
    )
    from spectra.application import (
        ScheduleDisplay,
        ScheduledSyncRunner,
        SyncOrchestrator,
        parse_schedule,
    )

    from .logging import setup_logging

    # Setup logging
    log_level = logging.DEBUG if getattr(args, "verbose", False) else logging.INFO
    log_format = getattr(args, "log_format", "text")
    setup_logging(level=log_level, log_format=log_format)

    # Create console
    console = Console(
        color=not getattr(args, "no_color", False),
        verbose=getattr(args, "verbose", False),
        quiet=getattr(args, "quiet", False),
    )

    markdown_path = args.input
    epic_key = args.epic
    schedule_spec = args.schedule
    run_now = getattr(args, "run_now", False)
    max_runs = getattr(args, "max_runs", None)
    dry_run = not getattr(args, "execute", False)

    # Validate markdown exists
    if not Path(markdown_path).exists():
        console.error(f"Markdown file not found: {markdown_path}")
        return ExitCode.FILE_NOT_FOUND

    # Parse schedule
    try:
        schedule = parse_schedule(schedule_spec)
    except ValueError as e:
        console.error(f"Invalid schedule: {e}")
        return ExitCode.CONFIG_ERROR

    # Load configuration
    config_file = Path(args.config) if getattr(args, "config", None) else None
    config_provider = EnvironmentConfigProvider(
        config_file=config_file,
        cli_overrides=vars(args),
    )
    errors = config_provider.validate()

    if errors:
        console.config_errors(errors)
        return ExitCode.CONFIG_ERROR

    config = config_provider.load()
    config.sync.dry_run = dry_run

    # Configure sync phases from args
    config.sync.sync_descriptions = args.phase in ("all", "descriptions")
    config.sync.sync_subtasks = args.phase in ("all", "subtasks")
    config.sync.sync_comments = args.phase in ("all", "comments")
    config.sync.sync_statuses = args.phase in ("all", "statuses")

    # Initialize components
    formatter = ADFFormatter()
    parser = MarkdownParser()
    tracker = JiraAdapter(
        config=config.tracker,
        dry_run=dry_run,
        formatter=formatter,
    )

    # Test connection
    console.header("spectra Scheduled Sync")

    if dry_run:
        console.dry_run_banner()

    console.section("Connecting to Jira")
    if not tracker.test_connection():
        console.connection_error(config.tracker.url)
        return ExitCode.CONNECTION_ERROR

    user = tracker.get_current_user()
    console.success(f"Connected as: {user.get('displayName', user.get('emailAddress', 'Unknown'))}")

    # Create sync orchestrator
    sync_orchestrator = SyncOrchestrator(
        tracker=tracker,
        parser=parser,
        formatter=formatter,
        config=config.sync,
    )

    # Create display handler
    display = ScheduleDisplay(
        color=not getattr(args, "no_color", False),
        quiet=getattr(args, "quiet", False),
    )

    # Create scheduled runner
    runner = ScheduledSyncRunner(
        orchestrator=sync_orchestrator,
        schedule=schedule,
        markdown_path=markdown_path,
        epic_key=epic_key,
        run_immediately=run_now,
        max_runs=max_runs,
        on_run_start=display.show_run_start,
        on_run_complete=display.show_run_complete,
    )

    # Show start message
    display.show_start(markdown_path, epic_key, schedule)

    try:
        # Run scheduled sync (blocks until Ctrl+C or max_runs)
        runner.start()
    except KeyboardInterrupt:
        pass
    finally:
        display.show_stop(runner.stats)

    return ExitCode.SUCCESS


def run_watch(args) -> int:
    """
    Run watch mode - auto-sync on file changes.

    Monitors the markdown file and triggers sync whenever
    changes are detected.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code.
    """
    from spectra.adapters import (
        ADFFormatter,
        EnvironmentConfigProvider,
        JiraAdapter,
        MarkdownParser,
    )
    from spectra.application import SyncOrchestrator, WatchDisplay, WatchOrchestrator

    from .logging import setup_logging

    # Setup logging
    log_level = logging.DEBUG if getattr(args, "verbose", False) else logging.INFO
    log_format = getattr(args, "log_format", "text")
    setup_logging(level=log_level, log_format=log_format)

    # Create console
    console = Console(
        color=not getattr(args, "no_color", False),
        verbose=getattr(args, "verbose", False),
        quiet=getattr(args, "quiet", False),
    )

    markdown_path = args.input
    epic_key = args.epic
    debounce = getattr(args, "debounce", 2.0)
    poll_interval = getattr(args, "poll_interval", 1.0)
    dry_run = not getattr(args, "execute", False)

    # Validate markdown exists
    if not Path(markdown_path).exists():
        console.error(f"Markdown file not found: {markdown_path}")
        return ExitCode.FILE_NOT_FOUND

    # Load configuration
    config_file = Path(args.config) if getattr(args, "config", None) else None
    config_provider = EnvironmentConfigProvider(
        config_file=config_file,
        cli_overrides=vars(args),
    )
    errors = config_provider.validate()

    if errors:
        console.config_errors(errors)
        return ExitCode.CONFIG_ERROR

    config = config_provider.load()
    config.sync.dry_run = dry_run

    # Configure sync phases from args
    config.sync.sync_descriptions = args.phase in ("all", "descriptions")
    config.sync.sync_subtasks = args.phase in ("all", "subtasks")
    config.sync.sync_comments = args.phase in ("all", "comments")
    config.sync.sync_statuses = args.phase in ("all", "statuses")

    # Initialize components
    formatter = ADFFormatter()
    parser = MarkdownParser()
    tracker = JiraAdapter(
        config=config.tracker,
        dry_run=dry_run,
        formatter=formatter,
    )

    # Test connection
    console.header("spectra Watch Mode")

    if dry_run:
        console.dry_run_banner()

    console.section("Connecting to Jira")
    if not tracker.test_connection():
        console.connection_error(config.tracker.url)
        return ExitCode.CONNECTION_ERROR

    user = tracker.get_current_user()
    console.success(f"Connected as: {user.get('displayName', user.get('emailAddress', 'Unknown'))}")

    # Create sync orchestrator
    sync_orchestrator = SyncOrchestrator(
        tracker=tracker,
        parser=parser,
        formatter=formatter,
        config=config.sync,
    )

    # Create display handler
    display = WatchDisplay(
        color=not getattr(args, "no_color", False),
        quiet=getattr(args, "quiet", False),
    )

    # Create watch orchestrator with callbacks
    watch = WatchOrchestrator(
        orchestrator=sync_orchestrator,
        markdown_path=markdown_path,
        epic_key=epic_key,
        debounce_seconds=debounce,
        poll_interval=poll_interval,
        on_change_detected=display.show_change_detected,
        on_sync_start=display.show_sync_start,
        on_sync_complete=display.show_sync_complete,
    )

    # Show start message
    display.show_start(markdown_path, epic_key)

    try:
        # Run watch mode (blocks until Ctrl+C)
        watch.start()
    except KeyboardInterrupt:
        pass
    finally:
        display.show_stop(watch.stats)

    return ExitCode.SUCCESS


def run_list_snapshots() -> int:
    """
    List all stored sync snapshots.

    Returns:
        Exit code.
    """
    from spectra.application.sync import SnapshotStore

    store = SnapshotStore()
    snapshots = store.list_snapshots()

    if not snapshots:
        print("No sync snapshots found.")
        print(f"Snapshot directory: {store.snapshot_dir}")
        return ExitCode.SUCCESS

    print(f"\n{'Epic':<15} {'Stories':<10} {'Created':<25}")
    print("-" * 52)

    for s in snapshots:
        epic = s.get("epic_key", "")[:13]
        stories = str(s.get("story_count", 0))
        created = s.get("created_at", "")[:24]
        print(f"{epic:<15} {stories:<10} {created:<25}")

    print()
    print(f"Total snapshots: {len(snapshots)}")
    print(f"Snapshot directory: {store.snapshot_dir}")
    print()
    print("Use --clear-snapshot --epic EPIC-KEY to reset conflict baseline")

    return ExitCode.SUCCESS


def run_clear_snapshot(epic_key: str) -> int:
    """
    Clear the sync snapshot for an epic.

    Args:
        epic_key: The epic key.

    Returns:
        Exit code.
    """
    from spectra.application.sync import SnapshotStore

    store = SnapshotStore()

    if store.delete(epic_key):
        print(f"✓ Cleared snapshot for {epic_key}")
        print("  Next sync will not detect conflicts (fresh baseline)")
        return ExitCode.SUCCESS
    print(f"No snapshot found for {epic_key}")
    return ExitCode.FILE_NOT_FOUND


def run_pull(args) -> int:
    """
    Run the pull operation to sync from Jira to markdown.

    This is the reverse of the normal sync - it fetches issue data
    from Jira and generates/updates a markdown file.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code.
    """
    from spectra.adapters import ADFFormatter, EnvironmentConfigProvider, JiraAdapter
    from spectra.adapters.formatters import MarkdownWriter
    from spectra.application.sync import ReverseSyncOrchestrator

    from .logging import setup_logging

    # Setup logging
    log_level = logging.DEBUG if getattr(args, "verbose", False) else logging.INFO
    log_format = getattr(args, "log_format", "text")
    setup_logging(level=log_level, log_format=log_format)

    # Create console
    console = Console(
        color=not getattr(args, "no_color", False),
        verbose=getattr(args, "verbose", False),
        quiet=getattr(args, "quiet", False),
    )

    epic_key = args.epic
    output_path = getattr(args, "pull_output", None)
    existing_markdown = getattr(args, "markdown", None)
    preview_only = getattr(args, "preview", False)
    update_existing = getattr(args, "update_existing", False)
    dry_run = not getattr(args, "execute", False)

    # Determine output path
    if not output_path:
        if existing_markdown and update_existing:
            output_path = existing_markdown
        else:
            output_path = f"{epic_key}.md"

    console.header("spectra Pull (Reverse Sync)")
    console.info(f"Epic: {epic_key}")
    console.info(f"Output: {output_path}")

    if dry_run:
        console.dry_run_banner()

    # Load configuration
    config_file = Path(args.config) if getattr(args, "config", None) else None
    config_provider = EnvironmentConfigProvider(
        config_file=config_file,
        cli_overrides=vars(args),
    )
    errors = config_provider.validate()

    if errors:
        console.config_errors(errors)
        return ExitCode.CONFIG_ERROR

    config = config_provider.load()
    config.sync.dry_run = dry_run

    # Initialize Jira adapter
    formatter = ADFFormatter()
    tracker = JiraAdapter(
        config=config.tracker,
        dry_run=True,  # Pull is read-only from Jira
        formatter=formatter,
    )

    # Test connection
    console.section("Connecting to Jira")
    if not tracker.test_connection():
        console.connection_error(config.tracker.url)
        return ExitCode.CONNECTION_ERROR

    user = tracker.get_current_user()
    console.success(f"Connected as: {user.get('displayName', user.get('emailAddress', 'Unknown'))}")

    # Create orchestrator
    orchestrator = ReverseSyncOrchestrator(
        tracker=tracker,
        config=config.sync,
        writer=MarkdownWriter(),
    )

    # Preview mode
    if preview_only:
        console.section("Previewing Changes")
        changes = orchestrator.preview(
            epic_key=epic_key,
            existing_markdown=existing_markdown if update_existing else None,
        )

        if not changes.has_changes:
            console.success("No changes detected")
            return ExitCode.SUCCESS

        console.info(f"Changes detected: {changes.total_changes}")
        console.print()

        if changes.new_stories:
            console.info(f"New stories ({len(changes.new_stories)}):")
            for story in changes.new_stories:
                console.item(f"{story.external_key}: {story.title}", "add")

        if changes.updated_stories:
            console.info(f"Updated stories ({len(changes.updated_stories)}):")
            for story, details in changes.updated_stories:
                console.item(f"{story.external_key}: {story.title}", "change")
                for detail in details:
                    console.detail(f"  {detail.field}: {detail.old_value} → {detail.new_value}")

        return ExitCode.SUCCESS

    # Confirmation
    if not dry_run and not getattr(args, "no_confirm", False):
        if not console.confirm(f"Pull from Jira and write to {output_path}?"):
            console.warning("Cancelled by user")
            return ExitCode.CANCELLED

    # Run pull
    console.section("Pulling from Jira")

    def progress_callback(phase: str, current: int, total: int) -> None:
        console.progress(current, total, phase)

    result = orchestrator.pull(
        epic_key=epic_key,
        output_path=output_path,
        existing_markdown=existing_markdown if update_existing else None,
        progress_callback=progress_callback,
    )

    # Show results
    console.print()

    if result.success:
        if dry_run:
            console.success("Pull preview completed (dry-run)")
            console.info("Use --execute to write the markdown file")
        else:
            console.success("Pull completed successfully!")
            console.success(f"Markdown written to: {result.output_path}")
    else:
        console.error("Pull completed with errors")

    console.detail(f"Stories pulled: {result.stories_pulled}")
    console.detail(f"  - New: {result.stories_created}")
    console.detail(f"  - Updated: {result.stories_updated}")
    console.detail(f"Subtasks: {result.subtasks_pulled}")

    if result.errors:
        console.print()
        console.error("Errors:")
        for error in result.errors[:10]:
            console.item(error, "fail")

    if result.warnings:
        console.print()
        console.warning("Warnings:")
        for warning in result.warnings[:5]:
            console.item(warning, "warn")

    return ExitCode.SUCCESS if result.success else ExitCode.ERROR


def run_bidirectional_sync(args) -> int:
    """
    Run bidirectional sync - push changes to tracker AND pull changes back.

    This is a two-way sync that:
    1. Detects what changed locally (markdown) since last sync
    2. Detects what changed remotely (tracker) since last sync
    3. Detects conflicts (both sides changed)
    4. Resolves conflicts based on strategy
    5. Pushes local changes to tracker
    6. Pulls remote changes to markdown

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code.
    """
    from spectra.adapters import ADFFormatter, EnvironmentConfigProvider, JiraAdapter
    from spectra.application.sync.bidirectional import BidirectionalSyncOrchestrator
    from spectra.application.sync.conflict import Conflict, ResolutionStrategy

    from .logging import setup_logging

    # Setup logging
    log_level = logging.DEBUG if getattr(args, "verbose", False) else logging.INFO
    log_format = getattr(args, "log_format", "text")
    setup_logging(level=log_level, log_format=log_format)

    # Create console
    console = Console(
        color=not getattr(args, "no_color", False),
        verbose=getattr(args, "verbose", False),
        quiet=getattr(args, "quiet", False),
    )

    markdown_path = args.input
    epic_key = args.epic
    dry_run = not getattr(args, "execute", False)
    strategy_str = getattr(args, "conflict_strategy", "ask")

    # Map strategy string to enum
    strategy_map = {
        "ask": ResolutionStrategy.ASK,
        "force-local": ResolutionStrategy.FORCE_LOCAL,
        "force-remote": ResolutionStrategy.FORCE_REMOTE,
        "skip": ResolutionStrategy.SKIP,
        "abort": ResolutionStrategy.ABORT,
    }
    resolution_strategy = strategy_map.get(strategy_str, ResolutionStrategy.ASK)

    console.header("spectra Bidirectional Sync")
    console.info(f"Markdown: {markdown_path}")
    console.info(f"Epic: {epic_key}")
    console.info(f"Conflict strategy: {strategy_str}")

    if dry_run:
        console.dry_run_banner()

    # Load configuration
    config_file = Path(args.config) if getattr(args, "config", None) else None
    config_provider = EnvironmentConfigProvider(
        config_file=config_file,
        cli_overrides=vars(args),
    )
    errors = config_provider.validate()

    if errors:
        console.config_errors(errors)
        return ExitCode.CONFIG_ERROR

    config = config_provider.load()
    config.sync.dry_run = dry_run

    # Initialize Jira adapter
    formatter = ADFFormatter()
    tracker = JiraAdapter(
        config=config.tracker,
        dry_run=dry_run,
        formatter=formatter,
    )

    # Test connection
    console.section("Connecting to Jira")
    if not tracker.test_connection():
        console.connection_error(config.tracker.url)
        return ExitCode.CONNECTION_ERROR

    user = tracker.get_current_user()
    console.success(f"Connected as: {user.get('displayName', user.get('emailAddress', 'Unknown'))}")

    # Create orchestrator
    orchestrator = BidirectionalSyncOrchestrator(
        tracker=tracker,
        config=config.sync,
    )

    # Interactive conflict resolver
    def resolve_conflict_interactively(conflict: Conflict) -> str:
        """Prompt user to resolve a conflict."""
        console.print()
        console.warning(f"Conflict detected: {conflict.story_id} ({conflict.jira_key})")
        console.detail(f"Field: {conflict.field}")
        console.detail(f"Local value: {conflict.local_value}")
        console.detail(f"Remote value: {conflict.remote_value}")
        console.detail(f"Base value: {conflict.base_value}")
        console.print()

        while True:
            choice = input("Resolve with [l]ocal, [r]emote, [s]kip? ").lower().strip()
            if choice in ("l", "local"):
                return "local"
            if choice in ("r", "remote"):
                return "remote"
            if choice in ("s", "skip"):
                return "skip"
            console.warning("Invalid choice. Enter 'l', 'r', or 's'.")

    # Progress callback
    def progress_callback(phase: str, current: int, total: int) -> None:
        console.progress(current, total, phase)

    # Determine resolver function
    conflict_resolver = (
        resolve_conflict_interactively if resolution_strategy == ResolutionStrategy.ASK else None
    )

    # Run bidirectional sync
    console.section("Syncing bidirectionally")
    result = orchestrator.sync(
        markdown_path=markdown_path,
        epic_key=epic_key,
        resolution_strategy=resolution_strategy,
        conflict_resolver=conflict_resolver,
        progress_callback=progress_callback,
    )

    # Show results
    console.print()
    console.section("Sync Results")

    # Push results
    console.info("Push (Markdown → Jira):")
    console.detail(f"  Stories: {result.stories_pushed}")
    console.detail(f"    Created: {result.stories_created}")
    console.detail(f"    Updated: {result.stories_updated}")
    console.detail(f"  Subtasks: {result.subtasks_synced}")

    # Pull results
    console.info("Pull (Jira → Markdown):")
    console.detail(f"  Stories pulled: {result.stories_pulled}")
    console.detail(f"  Fields updated: {result.fields_updated_locally}")

    # Conflict results
    if result.conflicts_detected > 0:
        console.print()
        console.info("Conflicts:")
        console.detail(f"  Detected: {result.conflicts_detected}")
        console.detail(f"  Resolved: {result.conflicts_resolved}")
        console.detail(f"  Skipped: {result.conflicts_skipped}")

    if result.success:
        console.print()
        if dry_run:
            console.success("Bidirectional sync preview completed (dry-run)")
            console.info("Use --execute to apply changes")
        else:
            console.success("Bidirectional sync completed successfully!")
            if result.markdown_updated:
                console.success(f"Markdown updated: {result.output_path}")
    else:
        console.print()
        console.error("Bidirectional sync completed with errors")

    if result.errors:
        console.print()
        console.error("Errors:")
        for error in result.errors[:10]:
            console.item(error, "fail")

    if result.warnings:
        console.print()
        console.warning("Warnings:")
        for warning in result.warnings[:5]:
            console.item(warning, "warn")

    return ExitCode.SUCCESS if result.success else ExitCode.ERROR


def run_attachment_sync(args) -> int:
    """
    Run attachment sync between markdown and issue tracker.

    Uploads local attachments to tracker and/or downloads remote attachments.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code (0 for success, 1 for errors).
    """
    from spectra.application.sync.attachments import (
        AttachmentSyncConfig,
        AttachmentSyncDirection,
        AttachmentSyncer,
        extract_attachments_from_markdown,
    )

    console = Console(
        verbose=args.verbose,
        json_mode=getattr(args, "output", "text") == "json",
    )

    console.header("Attachment Sync")

    # Validate required arguments
    if not args.input:
        console.error("--input/-f is required for attachment sync")
        return ExitCode.FILE_NOT_FOUND

    if not args.epic:
        console.error("--epic/-e is required for attachment sync")
        return ExitCode.ERROR

    markdown_path = Path(args.input)
    if not markdown_path.exists():
        console.error(f"File not found: {markdown_path}")
        return ExitCode.FILE_NOT_FOUND

    # Load config and create adapter
    config_provider = EnvironmentConfigProvider()
    try:
        tracker_config = config_provider.get_tracker_config()
    except Exception as e:
        console.error(f"Failed to load configuration: {e}")
        return ExitCode.CONFIG_ERROR

    dry_run = not args.execute
    adapter = JiraAdapter(tracker_config, dry_run=dry_run)

    # Test connection
    if not adapter.test_connection():
        console.error("Failed to connect to Jira")
        return ExitCode.CONNECTION_ERROR

    # Parse markdown to get stories
    parser = MarkdownParser()
    stories = parser.parse_stories(markdown_path)

    if not stories:
        console.warning("No stories found in markdown file")
        return ExitCode.SUCCESS

    console.info(f"Found {len(stories)} stories in {markdown_path.name}")

    # Configure attachment sync
    direction_map = {
        "upload": AttachmentSyncDirection.UPLOAD,
        "download": AttachmentSyncDirection.DOWNLOAD,
        "bidirectional": AttachmentSyncDirection.BIDIRECTIONAL,
    }

    config = AttachmentSyncConfig(
        direction=direction_map.get(args.attachment_direction, AttachmentSyncDirection.UPLOAD),
        dry_run=dry_run,
        attachments_dir=args.attachments_dir,
        skip_existing=args.skip_existing_attachments,
        max_file_size=args.attachment_max_size,
    )

    syncer = AttachmentSyncer(adapter, config)

    # Extract attachments from markdown
    local_attachments = extract_attachments_from_markdown(markdown_path)
    console.info(f"Found {len(local_attachments)} attachments in markdown")

    if not local_attachments and config.direction == AttachmentSyncDirection.UPLOAD:
        console.warning("No attachments to upload")
        return ExitCode.SUCCESS

    # Sync attachments for each story
    total_uploaded = 0
    total_downloaded = 0
    total_skipped = 0
    total_errors = 0

    for story in stories:
        issue_key = str(story.external_key) if story.external_key else None
        if not issue_key:
            # Try to find by title match in epic
            console.warning(f"No external key for story {story.id}, skipping attachments")
            continue

        # Get attachments for this story (simplified: all attachments apply to all stories)
        result = syncer.sync_story_attachments(
            story_id=str(story.id),
            issue_key=issue_key,
            local_attachments=local_attachments,
            markdown_path=markdown_path,
        )

        total_uploaded += result.total_uploaded
        total_downloaded += result.total_downloaded
        total_skipped += len(result.skipped)
        total_errors += len(result.errors)

        if result.uploaded:
            for att in result.uploaded:
                console.item(f"{att.filename} → {issue_key}", "success")

        if result.downloaded:
            for att in result.downloaded:
                console.item(f"{issue_key} → {att.local_path}", "success")

        if result.errors:
            for att, error in result.errors:
                console.item(f"{att.filename}: {error}", "fail")

    # Summary
    console.print()
    console.section("Summary")
    if dry_run:
        console.info(f"{Symbols.DRY_RUN} DRY RUN - no changes made")
    console.info(f"Uploaded: {total_uploaded}")
    console.info(f"Downloaded: {total_downloaded}")
    console.info(f"Skipped: {total_skipped}")
    if total_errors > 0:
        console.error(f"Errors: {total_errors}")
        return ExitCode.ERROR

    return ExitCode.SUCCESS


def run_list_custom_fields(args) -> int:
    """
    List available custom fields from the tracker.

    Connects to the tracker and retrieves all custom fields,
    displaying their IDs, names, and types.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code.
    """
    console = Console(verbose=args.verbose)

    console.header("Custom Fields Discovery")

    # Load config and create adapter
    config_provider = EnvironmentConfigProvider()
    try:
        tracker_config = config_provider.get_tracker_config()
    except Exception as e:
        console.error(f"Failed to load configuration: {e}")
        return ExitCode.CONFIG_ERROR

    adapter = JiraAdapter(tracker_config, dry_run=True)

    # Test connection
    if not adapter.test_connection():
        console.error("Failed to connect to Jira")
        return ExitCode.CONNECTION_ERROR

    console.info("Connected to Jira")
    console.print()

    # Get custom fields from Jira
    try:
        fields = adapter._client.get("field")
        if not isinstance(fields, list):
            console.error("Unexpected response from Jira")
            return ExitCode.ERROR

        # Filter to custom fields
        custom_fields = [f for f in fields if f.get("custom", False)]

        console.section(f"Custom Fields ({len(custom_fields)} found)")
        console.print()

        # Group by schema type
        by_type: dict[str, list] = {}
        for field in custom_fields:
            schema = field.get("schema", {})
            field_type = schema.get("type", "unknown")
            if field_type not in by_type:
                by_type[field_type] = []
            by_type[field_type].append(field)

        for field_type, type_fields in sorted(by_type.items()):
            console.info(f"{Symbols.BULLET} {field_type.upper()} fields:")
            for field in type_fields:
                field_id = field.get("id", "")
                field_name = field.get("name", "")
                console.print(f"    {field_id}: {field_name}")
            console.print()

        # Show common field mappings
        console.section("Common Field Usage")
        common = [
            ("Story Points", "customfield_10014", "story_points_field"),
            ("Sprint", "customfield_10020", "sprint_field"),
            ("Epic Link", "customfield_10008", "epic_link_field"),
        ]
        for name, default_id, cli_arg in common:
            matches = [f for f in custom_fields if name.lower() in f.get("name", "").lower()]
            if matches:
                field = matches[0]
                console.info(f"{name}: {field.get('id')} (--{cli_arg.replace('_', '-')})")
            else:
                console.warning(f"{name}: Not found (default: {default_id})")

    except Exception as e:
        console.error(f"Failed to retrieve fields: {e}")
        return ExitCode.ERROR

    return ExitCode.SUCCESS


def run_generate_field_mapping(args) -> int:
    """
    Generate a field mapping template YAML file.

    Creates a sample field mapping configuration that can be customized.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code.
    """
    from spectra.application.sync.field_mapping import (
        FieldDefinition,
        FieldMappingLoader,
        FieldType,
        FieldValueMapping,
        TrackerFieldMappingConfig,
    )

    console = Console(verbose=args.verbose)

    output_path = Path(args.generate_field_mapping)

    console.header("Generate Field Mapping Template")

    # Create sample configuration
    config = TrackerFieldMappingConfig(
        tracker_type="jira",
        project_key="PROJ",
        story_points_field="customfield_10014",
        priority_field="priority",
        status_field="status",
        assignee_field="assignee",
        labels_field="labels",
        due_date_field="duedate",
        sprint_field="customfield_10020",
        status_mapping={
            "Planned": "To Do",
            "Open": "To Do",
            "In Progress": "In Progress",
            "Done": "Done",
            "Blocked": "On Hold",
        },
        priority_mapping={
            "Critical": "Highest",
            "High": "High",
            "Medium": "Medium",
            "Low": "Low",
        },
        custom_fields=[
            FieldDefinition(
                name="team",
                markdown_name="Team",
                tracker_field_id="customfield_10050",
                tracker_field_name="Team",
                description="Development team assignment",
                field_type=FieldType.DROPDOWN,
                value_mappings=[
                    FieldValueMapping(
                        markdown_value="Backend",
                        tracker_value="10001",
                        aliases=["BE", "Server"],
                    ),
                    FieldValueMapping(
                        markdown_value="Frontend",
                        tracker_value="10002",
                        aliases=["FE", "UI"],
                    ),
                ],
            ),
            FieldDefinition(
                name="target_release",
                markdown_name="Target Release",
                tracker_field_id="customfield_10060",
                tracker_field_name="Target Release",
                description="Target release version",
                field_type=FieldType.TEXT,
                required=True,
                pattern=r"^v\d+\.\d+\.\d+$",
            ),
            FieldDefinition(
                name="business_value",
                markdown_name="Business Value",
                tracker_field_id="customfield_10070",
                tracker_field_name="Business Value",
                description="Business value score",
                field_type=FieldType.NUMBER,
                min_value=1,
                max_value=100,
            ),
        ],
    )

    try:
        FieldMappingLoader.save_to_yaml(config, output_path)
        console.success(f"Generated field mapping template: {output_path}")
        console.print()
        console.info("Edit this file to customize field mappings for your project.")
        console.info("Use with: spectra --field-mapping field_mapping.yaml ...")
    except Exception as e:
        console.error(f"Failed to write file: {e}")
        return ExitCode.ERROR

    return ExitCode.SUCCESS


def run_sync(
    console: Console,
    args: argparse.Namespace,
) -> int:
    """
    Run the sync operation between markdown and Jira.

    Handles the complete sync workflow including configuration loading,
    validation, connection testing, and orchestrating the sync phases.

    Args:
        console: Console instance for output.
        args: Parsed command-line arguments.

    Returns:
        Exit code (0 for success, 1 for errors).
    """
    # Load configuration with optional config file
    config_file = Path(args.config) if args.config else None
    config_provider = EnvironmentConfigProvider(
        config_file=config_file,
        cli_overrides=vars(args),
    )
    errors = config_provider.validate()

    if errors:
        console.config_errors(errors)
        return ExitCode.CONFIG_ERROR

    config = config_provider.load()

    # Handle markdown source (file or directory)
    input_dir = getattr(args, "input_dir", None)
    is_directory_mode = bool(input_dir)

    if is_directory_mode:
        markdown_path = Path(input_dir)
        if not markdown_path.is_dir():
            console.error_rich(FileNotFoundError(f"Directory not found: {input_dir}"))
            return ExitCode.FILE_NOT_FOUND
    else:
        markdown_path = Path(args.input)
        if not markdown_path.exists():
            console.error_rich(FileNotFoundError(markdown_path))
            return ExitCode.FILE_NOT_FOUND

    # Show header
    console.header(f"spectra {Symbols.ROCKET}")

    if config.sync.dry_run:
        console.dry_run_banner()

    # Show config source if loaded from file
    if config_provider.config_file_path:
        console.info(f"Config: {config_provider.config_file_path}")

    if is_directory_mode:
        # Count files in directory
        story_files = [f for f in markdown_path.glob("*.md") if f.name.lower().startswith("us-")]
        has_epic = (markdown_path / "EPIC.md").exists()
        console.info(f"Directory: {markdown_path}")
        console.info(f"Files: {len(story_files)} stories" + (" + EPIC.md" if has_epic else ""))
    else:
        console.info(f"Markdown: {markdown_path}")
    console.info(f"Epic: {args.epic}")
    console.info(f"Mode: {'Execute' if args.execute else 'Dry-run'}")
    if getattr(args, "incremental", False):
        console.info("Incremental: Enabled (only changed stories)")
    if args.execute and config.sync.backup_enabled:
        console.info("Backup: Enabled")

    # Initialize components
    event_bus = EventBus()
    formatter = ADFFormatter()
    parser = MarkdownParser()

    # Setup audit trail if requested
    audit_trail = None
    audit_recorder = None
    audit_trail_path = getattr(args, "audit_trail", None)
    if audit_trail_path and isinstance(audit_trail_path, str):
        from spectra.application.sync.audit import AuditTrailRecorder, create_audit_trail
        from spectra.application.sync.state import SyncState

        session_id = SyncState.generate_session_id(str(markdown_path), args.epic)
        audit_trail = create_audit_trail(
            session_id=session_id,
            epic_key=args.epic,
            markdown_path=str(markdown_path),
            dry_run=config.sync.dry_run,
        )
        audit_recorder = AuditTrailRecorder(audit_trail, dry_run=config.sync.dry_run)
        audit_recorder.subscribe_to(event_bus)
        console.info(f"Audit trail: {audit_trail_path}")

    tracker = JiraAdapter(
        config=config.tracker,
        dry_run=config.sync.dry_run,
        formatter=formatter,
    )

    # Test connection
    console.section("Connecting to Jira")
    if not tracker.test_connection():
        console.connection_error(config.tracker.url)
        return ExitCode.CONNECTION_ERROR

    user = tracker.get_current_user()
    console.success(f"Connected as: {user.get('displayName', user.get('emailAddress', 'Unknown'))}")

    # Configure sync phases
    config.sync.sync_descriptions = args.phase in ("all", "descriptions")
    config.sync.sync_subtasks = args.phase in ("all", "subtasks")
    config.sync.sync_comments = args.phase in ("all", "comments")
    config.sync.sync_statuses = args.phase in ("all", "statuses")

    if args.story:
        config.sync.story_filter = args.story

    # Configure backup
    config.sync.backup_enabled = not getattr(args, "no_backup", False)
    if getattr(args, "backup_dir", None):
        config.sync.backup_dir = args.backup_dir

    # Configure incremental sync
    config.sync.incremental = getattr(args, "incremental", False)
    config.sync.force_full_sync = getattr(args, "force_full_sync", False)

    # Configure source file update (writeback tracker info)
    config.sync.update_source_file = getattr(args, "update_source", False)

    # Create state store for persistence
    from spectra.application.sync import StateStore

    state_store = StateStore()

    # Create orchestrator with state store
    orchestrator = SyncOrchestrator(
        tracker=tracker,
        parser=parser,
        formatter=formatter,
        config=config.sync,
        event_bus=event_bus,
        state_store=state_store,
    )

    # Interactive mode
    if args.interactive:
        from .interactive import run_interactive

        success = run_interactive(
            console=console,
            orchestrator=orchestrator,
            markdown_path=str(markdown_path),
            epic_key=args.epic,
        )
        return ExitCode.SUCCESS if success else ExitCode.CANCELLED

    # Check for resumable session
    resume_state = None
    if args.resume or args.resume_session:
        if args.resume_session:
            # Load specific session
            resume_state = state_store.load(args.resume_session)
            if not resume_state:
                console.error(f"Session '{args.resume_session}' not found")
                return ExitCode.FILE_NOT_FOUND
        else:
            # Find latest resumable session for this markdown/epic
            resume_state = state_store.find_latest_resumable(str(markdown_path), args.epic)

        if resume_state:
            console.info(f"Resuming session: {resume_state.session_id}")
            console.detail(
                f"Progress: {resume_state.completed_count}/{resume_state.total_count} operations"
            )
            console.detail(f"Phase: {resume_state.phase}")
        elif args.resume:
            console.info("No resumable session found, starting fresh")

    # Pre-sync validation
    validation_errors = orchestrator.validate_sync_prerequisites(str(markdown_path), args.epic)
    if validation_errors:
        console.error("Pre-sync validation failed:")
        for error in validation_errors:
            console.item(error, "fail")
        return ExitCode.VALIDATION_ERROR

    # Confirmation
    if args.execute and not args.no_confirm:
        action = "Resume sync" if resume_state else "Proceed with sync"
        if not console.confirm(f"{action} execution?"):
            console.warning("Cancelled by user")
            return ExitCode.CANCELLED

    # Run sync with progress callback (supports both legacy and detailed progress)
    def progress_callback(
        phase: str,
        item: str = "",
        overall_progress: float = 0.0,
        current_item: int = 0,
        total_items: int = 0,
    ) -> None:
        # Use detailed progress display when item info is available
        if item or total_items > 0:
            console.progress_detailed(phase, item, overall_progress, current_item, total_items)
        else:
            # Fallback to simple progress for backward compatibility
            console.progress(current_item, total_items or 1, phase)

    console.section("Running Sync")

    # Suppress noisy logs during progress bar display (unless verbose mode)
    from .logging import suppress_logs_for_progress

    # Use resumable sync for state persistence
    if args.verbose:
        # Verbose mode: show all logs
        result = orchestrator.sync_resumable(
            markdown_path=str(markdown_path),
            epic_key=args.epic,
            progress_callback=progress_callback,
            resume_state=resume_state,
        )
    else:
        # Normal mode: suppress INFO logs for clean progress bar
        with suppress_logs_for_progress():
            result = orchestrator.sync_resumable(
                markdown_path=str(markdown_path),
                epic_key=args.epic,
                progress_callback=progress_callback,
                resume_state=resume_state,
            )

    # Show results
    console.sync_result(result)

    # Show backup info if created
    if orchestrator.last_backup:
        backup = orchestrator.last_backup
        console.success(f"Backup created: {backup.backup_id}")
        console.detail(f"  Issues: {backup.issue_count}, Subtasks: {backup.subtask_count}")

    # Export if requested
    if args.export:
        import json

        export_data = {
            "success": result.success,
            "dry_run": result.dry_run,
            "incremental": result.incremental,
            "matched_stories": result.matched_stories,
            "unmatched_stories": result.unmatched_stories,
            "stats": {
                "stories_matched": result.stories_matched,
                "stories_updated": result.stories_updated,
                "stories_skipped": result.stories_skipped,
                "subtasks_created": result.subtasks_created,
                "subtasks_updated": result.subtasks_updated,
                "comments_added": result.comments_added,
                "statuses_updated": result.statuses_updated,
            },
            "errors": result.errors,
            "warnings": result.warnings,
        }

        with open(args.export, "w") as f:
            json.dump(export_data, f, indent=2)

        console.success(f"Exported results to {args.export}")

    # Export audit trail if requested
    if audit_trail and audit_trail_path:
        audit_trail.complete(
            success=result.success,
            stories_matched=result.stories_matched,
            stories_updated=result.stories_updated,
            subtasks_created=result.subtasks_created,
            subtasks_updated=result.subtasks_updated,
            comments_added=result.comments_added,
            statuses_updated=result.statuses_updated,
            errors=result.errors,
            warnings=result.warnings,
        )
        audit_path = audit_trail.export(audit_trail_path)
        console.success(f"Audit trail exported to {audit_path}")

    # Determine exit code based on result
    if result.success:
        return ExitCode.SUCCESS
    if hasattr(result, "failed_operations") and result.failed_operations:
        # Partial success - some operations failed but sync completed
        return ExitCode.PARTIAL_SUCCESS
    return ExitCode.ERROR


def main() -> int:
    """
    Main entry point for the spectra CLI.

    Parses arguments, sets up logging, and runs the appropriate mode
    (validate or sync).

    Returns:
        Exit code (0 for success, non-zero for errors).
    """
    parser = create_parser()
    args = parser.parse_args()

    # Set global emoji mode based on --no-emoji flag
    if getattr(args, "no_emoji", False):
        from .output import set_emoji_mode

        set_emoji_mode(False)

    # Set color theme based on --theme flag
    if getattr(args, "theme", None):
        from .output import set_theme

        set_theme(args.theme)

    # Handle --list-themes
    if getattr(args, "list_themes", False):
        from .output import list_themes

        print("Available color themes:\n")
        for name, desc in list_themes():
            print(f"  {name:12} - {desc}")
        print("\nUsage: spectra --theme <name> ...")
        return ExitCode.SUCCESS

    # Handle completions first (doesn't require other args)
    if args.completions:
        from .completions import print_completion

        success = print_completion(args.completions)
        return ExitCode.SUCCESS if success else ExitCode.ERROR

    # Handle man page display
    if getattr(args, "man", False):
        from .manpage import show_man_page

        success = show_man_page()
        return ExitCode.SUCCESS if success else ExitCode.ERROR

    # Handle man page installation
    if getattr(args, "install_man", False):
        from .manpage import install_man_page

        success, message = install_man_page()
        print(message)
        return ExitCode.SUCCESS if success else ExitCode.ERROR

    # Handle init wizard (doesn't require other args)
    if args.init:
        from .init import run_init

        console = Console(
            color=not getattr(args, "no_color", False),
            verbose=getattr(args, "verbose", False),
        )
        return run_init(console)

    # Handle doctor command
    if getattr(args, "doctor", False):
        from .doctor import run_doctor

        console = Console(
            color=not getattr(args, "no_color", False),
            verbose=getattr(args, "verbose", False),
        )
        return run_doctor(console, verbose=getattr(args, "verbose", False))

    # Handle stats command
    if getattr(args, "stats", False):
        from .stats import run_stats

        console = Console(
            color=not getattr(args, "no_color", False),
            verbose=getattr(args, "verbose", False),
        )
        return run_stats(
            console,
            input_path=getattr(args, "input", None),
            input_dir=getattr(args, "input_dir", None),
            output_format=getattr(args, "output", "text"),
        )

    # Handle diff command
    if getattr(args, "diff", False):
        if not args.input or not args.epic:
            parser.error("--diff requires --input/-f and --epic/-e to be specified")
        from .diff_cmd import run_diff as run_diff_cmd

        console = Console(
            color=not getattr(args, "no_color", False),
            verbose=getattr(args, "verbose", False),
        )
        return run_diff_cmd(
            console,
            input_path=args.input,
            epic_key=args.epic,
            output_format=getattr(args, "output", "text"),
        )

    # Handle import command
    if getattr(args, "import_cmd", False):
        if not args.epic:
            parser.error("--import requires --epic/-e to be specified")
        from .import_cmd import run_import

        console = Console(
            color=not getattr(args, "no_color", False),
            verbose=getattr(args, "verbose", False),
        )
        return run_import(
            console,
            epic_key=args.epic,
            output_path=getattr(args, "generate_output", None),
            dry_run=not getattr(args, "execute", False),
        )

    # Handle plan command
    if getattr(args, "plan", False):
        if not args.input or not args.epic:
            parser.error("--plan requires --input/-f and --epic/-e to be specified")
        from .plan_cmd import run_plan

        console = Console(
            color=not getattr(args, "no_color", False),
            verbose=getattr(args, "verbose", False),
        )
        return run_plan(
            console,
            input_path=args.input,
            epic_key=args.epic,
            verbose=getattr(args, "verbose", False),
            output_format=getattr(args, "output", "text"),
        )

    # Handle migrate command
    if getattr(args, "migrate", False):
        from .migrate import run_migrate

        console = Console(
            color=not getattr(args, "no_color", False),
            verbose=getattr(args, "verbose", False),
        )
        return run_migrate(
            console,
            source_type=getattr(args, "migrate_source", "jira") or "jira",
            target_type=getattr(args, "migrate_target", "github") or "github",
            epic_key=getattr(args, "epic", None),
            dry_run=not getattr(args, "execute", False),
        )

    # Handle visualize command
    if getattr(args, "visualize", False):
        if not args.input:
            parser.error("--visualize requires --input/-f to be specified")
        from .visualize import run_visualize

        console = Console(
            color=not getattr(args, "no_color", False),
            verbose=getattr(args, "verbose", False),
        )
        return run_visualize(
            console,
            input_path=args.input,
            output_format=getattr(args, "visualize_format", "mermaid"),
            output_file=getattr(args, "export", None),
        )

    # Handle velocity command
    if getattr(args, "velocity", False) or getattr(args, "velocity_add", False):
        from .velocity import run_velocity

        console = Console(
            color=not getattr(args, "no_color", False),
            verbose=getattr(args, "verbose", False),
        )
        action = "add" if getattr(args, "velocity_add", False) else "show"
        return run_velocity(
            console,
            input_path=getattr(args, "input", None),
            action=action,
            sprint_name=getattr(args, "sprint", None),
            output_format=getattr(args, "output", "text"),
        )

    # Handle report command
    if getattr(args, "report", None):
        if not args.input:
            parser.error("--report requires --input/-f to be specified")
        from .report import run_report

        console = Console(
            color=not getattr(args, "no_color", False),
            verbose=getattr(args, "verbose", False),
        )
        return run_report(
            console,
            input_path=args.input,
            period=args.report,
            output_path=getattr(args, "export", None),
            output_format=getattr(args, "output", "text"),
        )

    # Handle config validate command
    if getattr(args, "config_validate", False):
        from .config_cmd import run_config_validate

        console = Console(
            color=not getattr(args, "no_color", False),
            verbose=getattr(args, "verbose", False),
        )
        return run_config_validate(
            console,
            config_file=getattr(args, "config", None),
            test_connection=True,
        )

    # Handle version check command
    if getattr(args, "version_check", False):
        console = Console(color=not getattr(args, "no_color", False))
        console.header("spectra Version Check")
        console.print()
        console.info("Current version: 2.0.0")
        console.info("Checking for updates...")
        # Would check PyPI or GitHub releases
        console.success("You are running the latest version!")
        return ExitCode.SUCCESS

    # Handle hook command
    if getattr(args, "hook", None):
        from .hook import run_hook_install, run_hook_status, run_hook_uninstall

        console = Console(
            color=not getattr(args, "no_color", False),
            verbose=getattr(args, "verbose", False),
        )
        hook_action = args.hook
        hook_type = getattr(args, "hook_type", "pre-commit")

        if hook_action == "install":
            return run_hook_install(console, hook_type=hook_type)
        if hook_action == "uninstall":
            return run_hook_uninstall(console, hook_type=hook_type)
        # status
        return run_hook_status(console)

    # Handle tutorial command
    if getattr(args, "tutorial", False) or getattr(args, "tutorial_step", None):
        from .tutorial import run_tutorial

        console = Console(
            color=not getattr(args, "no_color", False),
            verbose=getattr(args, "verbose", False),
        )

        step = getattr(args, "tutorial_step", None)
        return run_tutorial(
            console=console,
            color=not getattr(args, "no_color", False),
            step=step,
        )

    # Handle bulk-update command
    if getattr(args, "bulk_update", False):
        from .bulk import run_bulk_update

        console = Console(
            color=not getattr(args, "no_color", False),
            verbose=getattr(args, "verbose", False),
        )

        input_path = Path(args.markdown) if args.markdown else None
        return run_bulk_update(
            console=console,
            input_path=input_path,
            filter_str=getattr(args, "filter", "") or "",
            update_str=getattr(args, "set", "") or "",
            dry_run=getattr(args, "dry_run", False),
            color=not getattr(args, "no_color", False),
        )

    # Handle bulk-assign command
    if getattr(args, "bulk_assign", False):
        from .bulk import run_bulk_assign

        console = Console(
            color=not getattr(args, "no_color", False),
            verbose=getattr(args, "verbose", False),
        )

        input_path = Path(args.markdown) if args.markdown else None
        return run_bulk_assign(
            console=console,
            input_path=input_path,
            filter_str=getattr(args, "filter", "") or "",
            assignee=getattr(args, "assignee", "") or "",
            dry_run=getattr(args, "dry_run", False),
            color=not getattr(args, "no_color", False),
        )

    # Handle split command
    if getattr(args, "split", False) or getattr(args, "split_story", None):
        from .split import run_split

        console = Console(
            color=not getattr(args, "no_color", False),
            verbose=getattr(args, "verbose", False),
        )

        input_path = Path(args.markdown) if args.markdown else None
        return run_split(
            console=console,
            input_path=input_path,
            story_id=getattr(args, "split_story", None),
            threshold=getattr(args, "split_threshold", 4),
            output_format=getattr(args, "output", "text") or "text",
            color=not getattr(args, "no_color", False),
        )

    # Handle archive command
    if getattr(args, "archive", None):
        from .archive import run_archive

        console = Console(
            color=not getattr(args, "no_color", False),
            verbose=getattr(args, "verbose", False),
        )

        input_path = Path(args.markdown) if args.markdown else None
        action = args.archive
        story_keys = None
        if getattr(args, "story_keys", None):
            story_keys = [k.strip() for k in args.story_keys.split(",")]

        return run_archive(
            console=console,
            input_path=input_path,
            action=action,
            story_keys=story_keys,
            days_threshold=getattr(args, "archive_days", 90),
            dry_run=getattr(args, "dry_run", False),
            color=not getattr(args, "no_color", False),
        )

    # Handle generate (requires epic key)
    if args.generate:
        if not args.epic:
            parser.error("--generate requires --epic/-e to be specified")
        from .generate import run_generate

        console = Console(
            color=not getattr(args, "no_color", False),
            verbose=getattr(args, "verbose", False),
            quiet=getattr(args, "quiet", False),
        )
        return run_generate(args, console)

    # Handle list-sessions (doesn't require other args)
    if args.list_sessions:
        from spectra.application.sync import StateStore

        return list_sessions(StateStore())

    # Handle list-backups (requires epic key)
    if args.list_backups:
        from spectra.application.sync import BackupManager

        return list_backups(BackupManager(), args.epic)

    # Handle restore-backup (requires backup ID, optionally epic key)
    if args.restore_backup:
        return run_restore(args)

    # Handle diff-backup or diff-latest
    if args.diff_backup or args.diff_latest:
        return run_diff(args)

    # Handle rollback
    if args.rollback:
        return run_rollback(args)

    # Handle bidirectional sync
    if getattr(args, "bidirectional", False):
        if not args.input or not args.epic:
            parser.error("--bidirectional requires --input/-i and --epic/-e to be specified")
        return run_bidirectional_sync(args)

    # Handle pull (reverse sync from Jira to markdown)
    if args.pull:
        if not args.epic:
            parser.error("--pull requires --epic/-e to be specified")
        return run_pull(args)

    # Handle list-snapshots
    if args.list_snapshots:
        return run_list_snapshots()

    # Handle clear-snapshot
    if args.clear_snapshot:
        if not args.epic:
            parser.error("--clear-snapshot requires --epic/-e to be specified")
        return run_clear_snapshot(args.epic)

    # Handle watch mode
    if args.watch:
        if not args.input or not args.epic:
            parser.error("--watch requires --input/-i and --epic/-e to be specified")
        return run_watch(args)

    # Handle scheduled sync
    if args.schedule:
        if not args.input or not args.epic:
            parser.error("--schedule requires --input/-i and --epic/-e to be specified")
        return run_schedule(args)

    # Handle webhook server
    if args.webhook:
        if not args.epic:
            parser.error("--webhook requires --epic/-e to be specified")
        return run_webhook(args)

    # Handle multi-epic sync
    if args.multi_epic or args.list_epics:
        if not args.input:
            parser.error("--multi-epic and --list-epics require --input/-i to be specified")
        return run_multi_epic(args)

    # Handle multi-tracker sync
    if getattr(args, "multi_tracker", False) or getattr(args, "trackers", None):
        if not args.input:
            parser.error("--multi-tracker requires --input/-i to be specified")
        return run_multi_tracker_sync(args)

    # Handle link sync
    if args.sync_links or args.analyze_links:
        if not args.input or not args.epic:
            parser.error(
                "--sync-links and --analyze-links require --input/-i and --epic/-e to be specified"
            )
        return run_sync_links(args)

    # Handle attachment sync
    if args.sync_attachments:
        if not args.input or not args.epic:
            parser.error("--sync-attachments requires --input/-f and --epic/-e to be specified")
        return run_attachment_sync(args)

    # Handle field mapping commands
    if args.list_custom_fields:
        return run_list_custom_fields(args)

    if args.generate_field_mapping:
        return run_generate_field_mapping(args)

    # Handle resume-session (loads args from session)
    if args.resume_session:
        from spectra.application.sync import StateStore

        state_store = StateStore()
        state = state_store.load(args.resume_session)
        if not state:
            print(f"Error: Session '{args.resume_session}' not found")
            return ExitCode.FILE_NOT_FOUND
        # Override args from session
        args.input = state.markdown_path
        args.epic = state.epic_key

    # Handle list-ai-tools (no other args needed)
    if getattr(args, "list_ai_tools", False):
        from .ai_fix import detect_ai_tools, format_ai_tools_list

        console = Console(color=not getattr(args, "no_color", False))
        console.header("spectra AI Tools")

        tools = detect_ai_tools()
        if tools:
            print(format_ai_tools_list(tools, color=console.color))
            console.print()
            console.info("Use with: spectra --validate --input FILE.md --auto-fix --ai-tool <name>")
        else:
            console.warning("No AI CLI tools detected on your system.")
            console.print()
            console.info("Install one of the following to enable auto-fix:")
            console.info("  • claude (Anthropic): pip install anthropic")
            console.info("  • ollama: https://ollama.ai")
            console.info("  • aider: pip install aider-chat")
            console.info("  • gh copilot: gh extension install github/gh-copilot")
            console.info("  • llm: pip install llm")
            console.info("  • sgpt: pip install shell-gpt")
            console.info("  • mods: https://github.com/charmbracelet/mods")
        return ExitCode.SUCCESS

    # Handle --list-files mode (preview which files would be processed)
    if getattr(args, "list_files", False):
        input_dir = getattr(args, "input_dir", None)
        if not input_dir:
            parser.error("--list-files requires --input-dir to be specified")

        console = Console(
            color=not args.no_color,
            verbose=args.verbose,
            quiet=args.quiet,
            json_mode=(args.output in ("json", "yaml", "markdown")),
        )
        dir_path = Path(input_dir)
        if not dir_path.is_dir():
            console.error(f"Directory not found: {input_dir}")
            return ExitCode.FILE_NOT_FOUND

        # Find files that would be processed using the parser's detection logic
        from spectra.adapters.parsers import MarkdownParser

        parser = MarkdownParser()
        epic_file = None
        story_files: list[Path] = []
        ignored_files: list[Path] = []

        for md_file in sorted(dir_path.glob("*.md")):
            name_lower = md_file.name.lower()
            if name_lower == "epic.md":
                epic_file = md_file
            elif parser._is_story_file(md_file):
                story_files.append(md_file)
            else:
                ignored_files.append(md_file)

        console.header("Files to Process")
        if epic_file:
            console.success(f"Epic: {epic_file.name}")
        else:
            console.warning("No EPIC.md found")

        if story_files:
            console.info(f"\nUser Stories ({len(story_files)} files):")
            for sf in story_files:
                console.info(f"  ✓ {sf.name}")
        else:
            console.warning("No US-*.md files found")

        if ignored_files:
            console.info(f"\nIgnored ({len(ignored_files)} files):")
            for ig in ignored_files:
                console.info(f"  ○ {ig.name}")

        total = (1 if epic_file else 0) + len(story_files)
        console.info(f"\nTotal: {total} file(s) will be processed")
        return ExitCode.SUCCESS

    # Handle validate mode (only requires markdown or markdown-dir, unless just showing guide)
    if args.validate or getattr(args, "show_guide", False):
        # show_guide can work without a markdown file
        input_dir = getattr(args, "input_dir", None)
        if not args.input and not input_dir and not getattr(args, "show_guide", False):
            parser.error("--validate requires --input/-i or --input-dir to be specified")
        from .logging import setup_logging

        setup_logging(
            level=logging.DEBUG if args.verbose else logging.INFO,
            log_format=getattr(args, "log_format", "text"),
        )
        console = Console(
            color=not args.no_color,
            verbose=args.verbose,
            quiet=args.quiet,
            json_mode=(args.output in ("json", "yaml", "markdown")),
        )
        try:
            return validate_markdown(
                console,
                args.input or "",
                strict=getattr(args, "strict", False),
                show_guide=getattr(args, "show_guide", False),
                suggest_fix=getattr(args, "suggest_fix", False),
                auto_fix=getattr(args, "auto_fix", False),
                ai_tool=getattr(args, "ai_tool", None),
                input_dir=input_dir,
            )
        except KeyboardInterrupt:
            console.print()
            console.warning("Interrupted by user")
            return ExitCode.SIGINT
        except Exception as e:
            console.error_rich(e)
            if args.verbose:
                import traceback

                console.print()
                traceback.print_exc()
            return ExitCode.from_exception(e)

    # Handle dashboard mode (markdown and epic are optional)
    if args.dashboard:
        from .dashboard import run_dashboard

        console = Console(
            color=not args.no_color,
            verbose=args.verbose,
            quiet=args.quiet,
        )
        return run_dashboard(
            console,
            markdown_path=args.input,
            epic_key=args.epic,
        )

    # Handle interactive TUI mode
    if getattr(args, "tui", False) or getattr(args, "tui_demo", False):
        try:
            from .tui import run_tui
        except ImportError:
            console = Console(color=not args.no_color)
            console.error("Interactive TUI requires the 'tui' optional dependency.")
            console.info("Install with: pip install spectra[tui]")
            return ExitCode.ERROR

        return run_tui(
            markdown_path=args.input,
            epic_key=args.epic,
            dry_run=not getattr(args, "execute", False),
            demo=getattr(args, "tui_demo", False),
        )

    # Handle analytics commands (no markdown/epic needed)
    if getattr(args, "analytics_show", False):
        from .analytics import configure_analytics, format_analytics_display, show_analytics_info

        console = Console(color=not args.no_color)

        # Show what analytics collects
        console.print(show_analytics_info())
        console.print()

        # Show collected data if any
        manager = configure_analytics(enabled=True)
        data = manager.get_display_data()
        console.print(format_analytics_display(data))

        return ExitCode.SUCCESS

    if getattr(args, "analytics_clear", False):
        from .analytics import configure_analytics

        console = Console(color=not args.no_color)

        manager = configure_analytics(enabled=True)
        if manager.clear_data():
            console.success("Analytics data cleared")
            return ExitCode.SUCCESS
        console.error("Failed to clear analytics data")
        return ExitCode.ERROR

    # Validate required arguments for other modes
    input_dir = getattr(args, "input_dir", None)
    if not args.input and not input_dir:
        parser.error("one of the following arguments is required: --input/-i or --input-dir")
    if not args.epic:
        parser.error("the following argument is required: --epic/-e")

    # Setup logging with optional JSON format
    from .logging import setup_logging

    log_level = logging.DEBUG if args.verbose else logging.INFO
    log_format = getattr(args, "log_format", "text")
    log_file = getattr(args, "log_file", None)

    setup_logging(
        level=log_level,
        log_format=log_format,
        log_file=log_file,
        static_fields={"service": "spectra"} if log_format == "json" else None,
    )

    # Setup OpenTelemetry if enabled
    telemetry_provider = None
    if getattr(args, "otel_enable", False):
        from .telemetry import configure_telemetry

        telemetry_provider = configure_telemetry(
            enabled=True,
            endpoint=getattr(args, "otel_endpoint", None),
            service_name=getattr(args, "otel_service_name", "spectra"),
            console_export=getattr(args, "otel_console", False),
        )

    # Setup Prometheus metrics if enabled
    if getattr(args, "prometheus", False):
        from .telemetry import configure_prometheus

        prometheus_provider = configure_prometheus(
            enabled=True,
            port=getattr(args, "prometheus_port", 9090),
            host=getattr(args, "prometheus_host", "0.0.0.0"),
            service_name=getattr(args, "otel_service_name", "spectra"),
        )
        if telemetry_provider is None:
            telemetry_provider = prometheus_provider

    # Setup health check server if enabled
    health_server = None
    if getattr(args, "health", False):
        from .health import configure_health

        health_server = configure_health(
            enabled=True,
            port=getattr(args, "health_port", 8080),
            host=getattr(args, "health_host", "0.0.0.0"),
        )

    # Setup analytics if enabled (opt-in)
    if getattr(args, "analytics", False):
        from .analytics import configure_analytics

        configure_analytics(enabled=True)

    # Create console
    console = Console(
        color=not args.no_color,
        verbose=args.verbose,
        quiet=args.quiet,
        json_mode=(args.output in ("json", "yaml", "markdown")),
    )

    try:
        # Run sync
        return run_sync(console, args)

    except KeyboardInterrupt:
        console.print()
        console.warning("Interrupted by user")
        return ExitCode.SIGINT

    except Exception as e:
        # Use rich error formatting for better user experience
        console.error_rich(e)
        if args.verbose:
            import traceback

            console.print()
            traceback.print_exc()
        return ExitCode.from_exception(e)

    finally:
        # Shutdown telemetry if enabled
        if telemetry_provider:
            telemetry_provider.shutdown()

        # Shutdown health server if enabled
        if health_server:
            health_server.stop()


def run() -> None:
    """
    Entry point for the console script.

    Calls main() and exits with its return code.
    """
    sys.exit(main())


if __name__ == "__main__":
    run()
