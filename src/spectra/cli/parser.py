"""
CLI Argument Parser - Defines all CLI arguments for spectra.

This module contains the argument parser definition, separated from the main
app module for better maintainability. The parser defines ~200 CLI arguments
organized into logical groups.
"""

import argparse

__all__ = ["create_parser"]


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
        epilog=_get_epilog(),
    )

    # Add argument groups
    _add_input_arguments(parser)
    _add_execution_arguments(parser)
    _add_phase_arguments(parser)
    _add_filter_arguments(parser)
    _add_config_arguments(parser)
    _add_output_arguments(parser)
    _add_backup_arguments(parser)
    _add_transactional_arguments(parser)
    _add_idempotency_arguments(parser)
    _add_special_mode_arguments(parser)
    _add_telemetry_arguments(parser)
    _add_analytics_arguments(parser)
    _add_session_arguments(parser)
    _add_generation_arguments(parser)
    _add_bidirectional_arguments(parser)
    _add_conflict_arguments(parser)
    _add_watch_arguments(parser)
    _add_schedule_arguments(parser)
    _add_webhook_arguments(parser)
    _add_notification_arguments(parser)
    _add_llm_arguments(parser)
    _add_multi_epic_arguments(parser)
    _add_multi_tracker_arguments(parser)
    _add_attachment_arguments(parser)
    _add_field_mapping_arguments(parser)
    _add_time_tracking_arguments(parser)
    _add_sprint_arguments(parser)
    _add_dependency_arguments(parser)
    _add_hierarchy_arguments(parser)
    _add_workflow_arguments(parser)
    _add_command_arguments(parser)

    return parser


def _get_epilog() -> str:
    """Return the epilog text with usage examples."""
    return """
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

  # AI story generation from high-level description
  spectra --generate-stories --description "Build user authentication with OAuth"

  # AI story generation with context and output file
  spectra --generate-stories --description-file feature.txt --project-context "E-commerce app" --generation-output stories.md --execute

  # AI story generation with detailed style
  spectra --generate-stories --description "Implement checkout flow" --generation-style detailed --max-stories 8

  # AI story refinement - analyze stories for quality issues
  spectra --refine -f EPIC.md

  # AI story point estimation
  spectra --estimate -f EPIC.md

  # AI labeling - suggest labels based on content
  spectra --label -f EPIC.md

  # AI smart splitting - suggest splitting large stories
  spectra --split -f EPIC.md

  # AI acceptance criteria generation
  spectra --generate-ac -f EPIC.md

  # AI dependency detection
  spectra --dependencies -f EPIC.md

  # AI story quality scoring
  spectra --quality -f EPIC.md

  # AI duplicate detection
  spectra --duplicates -f EPIC.md

  # AI gap analysis
  spectra --gaps -f EPIC.md

  # Preview changes without executing (dry-run is default)
  spectra -f EPIC.md -e PROJ-123 --dry-run

  # Execute sync with confirmations
  spectra -f EPIC.md -e PROJ-123 --execute

  # Full sync without prompts
  spectra -f EPIC.md -e PROJ-123 --execute --no-confirm

  # Interactive mode - step-by-step guided sync
  spectra -f EPIC.md -e PROJ-123 --interactive

  # Pull from Jira to file (reverse sync)
  spectra --pull -e PROJ-123 --pull-output EPIC.md --execute

  # Watch mode - auto-sync on file changes
  spectra --watch -f EPIC.md -e PROJ-123 --execute

  # Scheduled sync - every 5 minutes
  spectra --schedule 5m -f EPIC.md -e PROJ-123 --execute

  # Multi-epic sync - sync all epics from one file
  spectra --multi-epic -f ROADMAP.md --execute

  # Parallel file processing - process multiple files concurrently
  spectra --parallel-files -d ./docs/epics --workers 8

Environment Variables:
  JIRA_URL         Jira instance URL (e.g., https://company.atlassian.net)
  JIRA_EMAIL       Jira account email
  JIRA_API_TOKEN   Jira API token
        """


def _add_input_arguments(parser: argparse.ArgumentParser) -> None:
    """Add input-related arguments."""
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


def _add_execution_arguments(parser: argparse.ArgumentParser) -> None:
    """Add execution-related arguments."""
    group = parser.add_argument_group("Execution")
    group.add_argument(
        "--execute", "-x", action="store_true", help="Execute changes (default is dry-run)"
    )
    group.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Preview changes without executing (this is the default, use for explicit clarity)",
    )
    group.add_argument("--no-confirm", action="store_true", help="Skip confirmation prompts")
    group.add_argument(
        "--incremental", action="store_true", help="Only sync changed stories (skip unchanged)"
    )
    group.add_argument(
        "--delta-sync",
        action="store_true",
        help="Only sync changed fields (more granular than --incremental)",
    )
    group.add_argument(
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
    group.add_argument(
        "--force-full-sync",
        action="store_true",
        help="Force full sync even when --incremental is set",
    )
    parser.add_argument(
        "--update-source",
        action="store_true",
        help="Write tracker info (issue key, URL) back to source markdown file after sync",
    )


def _add_phase_arguments(parser: argparse.ArgumentParser) -> None:
    """Add phase control arguments."""
    group = parser.add_argument_group("Phase control")
    group.add_argument(
        "--phase",
        type=str,
        choices=["all", "descriptions", "subtasks", "comments", "statuses"],
        default="all",
        help="Which phase to run (default: all)",
    )


def _add_filter_arguments(parser: argparse.ArgumentParser) -> None:
    """Add filter arguments."""
    group = parser.add_argument_group("Filters")
    group.add_argument(
        "--story", type=str, help="Filter to specific story ID (e.g., STORY-001, US-001, PROJ-123)"
    )


def _add_config_arguments(parser: argparse.ArgumentParser) -> None:
    """Add configuration arguments."""
    group = parser.add_argument_group("Configuration")
    group.add_argument(
        "--config", "-c", type=str, help="Path to config file (.spectra.yaml, .spectra.toml)"
    )
    group.add_argument("--jira-url", type=str, help="Override Jira URL")
    group.add_argument("--project", type=str, help="Override Jira project key")


def _add_output_arguments(parser: argparse.ArgumentParser) -> None:
    """Add output-related arguments."""
    group = parser.add_argument_group("Output")
    group.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    group.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Quiet mode - only show errors and final summary (for CI/scripting)",
    )
    group.add_argument(
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
        help="Color theme for output",
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


def _add_backup_arguments(parser: argparse.ArgumentParser) -> None:
    """Add backup-related arguments."""
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


def _add_transactional_arguments(parser: argparse.ArgumentParser) -> None:
    """Add transactional sync arguments."""
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


def _add_idempotency_arguments(parser: argparse.ArgumentParser) -> None:
    """Add idempotency-related arguments."""
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


def _add_special_mode_arguments(parser: argparse.ArgumentParser) -> None:
    """Add special mode arguments (init, validate, dashboard, TUI)."""
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


def _add_telemetry_arguments(parser: argparse.ArgumentParser) -> None:
    """Add OpenTelemetry and Prometheus arguments."""
    # OpenTelemetry
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

    # Prometheus
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

    # Health check
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


def _add_analytics_arguments(parser: argparse.ArgumentParser) -> None:
    """Add analytics arguments (opt-in)."""
    parser.add_argument(
        "--analytics", action="store_true", help="Enable anonymous usage analytics (opt-in)"
    )
    parser.add_argument(
        "--analytics-show", action="store_true", help="Show what analytics data has been collected"
    )
    parser.add_argument(
        "--analytics-clear", action="store_true", help="Clear all collected analytics data"
    )


def _add_session_arguments(parser: argparse.ArgumentParser) -> None:
    """Add session and completion arguments."""
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


def _add_generation_arguments(parser: argparse.ArgumentParser) -> None:
    """Add template generation arguments."""
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


def _add_bidirectional_arguments(parser: argparse.ArgumentParser) -> None:
    """Add bidirectional sync arguments."""
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


def _add_conflict_arguments(parser: argparse.ArgumentParser) -> None:
    """Add conflict detection arguments."""
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


def _add_watch_arguments(parser: argparse.ArgumentParser) -> None:
    """Add watch mode arguments."""
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


def _add_schedule_arguments(parser: argparse.ArgumentParser) -> None:
    """Add scheduled sync arguments."""
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


def _add_webhook_arguments(parser: argparse.ArgumentParser) -> None:
    """Add webhook receiver arguments."""
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
        help="Webhook secret for signature verification (Jira)",
    )
    # Multi-tracker webhook secrets
    parser.add_argument(
        "--github-webhook-secret",
        type=str,
        metavar="SECRET",
        help="GitHub webhook secret for signature verification",
    )
    parser.add_argument(
        "--gitlab-webhook-secret",
        type=str,
        metavar="SECRET",
        help="GitLab webhook secret/token for verification",
    )
    parser.add_argument(
        "--azure-webhook-secret",
        type=str,
        metavar="SECRET",
        help="Azure DevOps webhook secret",
    )
    parser.add_argument(
        "--linear-webhook-secret",
        type=str,
        metavar="SECRET",
        help="Linear webhook secret for signature verification",
    )
    parser.add_argument(
        "--multi-tracker-webhook",
        action="store_true",
        help="Enable multi-tracker webhook mode (listen for multiple sources)",
    )


def _add_notification_arguments(parser: argparse.ArgumentParser) -> None:
    """Add notification arguments."""
    parser.add_argument(
        "--slack-webhook",
        type=str,
        metavar="URL",
        help="Slack incoming webhook URL for sync notifications",
    )
    parser.add_argument(
        "--discord-webhook",
        type=str,
        metavar="URL",
        help="Discord webhook URL for sync notifications",
    )
    parser.add_argument(
        "--teams-webhook",
        type=str,
        metavar="URL",
        help="Microsoft Teams webhook URL for sync notifications",
    )
    parser.add_argument(
        "--notify-webhook",
        type=str,
        metavar="URL",
        help="Generic webhook URL for sync notifications",
    )
    parser.add_argument(
        "--notify-on-success",
        action="store_true",
        default=True,
        help="Send notifications on successful sync (default: True)",
    )
    parser.add_argument(
        "--notify-on-failure",
        action="store_true",
        default=True,
        help="Send notifications on failed sync (default: True)",
    )
    parser.add_argument(
        "--no-notify-on-success",
        action="store_true",
        help="Disable notifications on successful sync",
    )


def _add_llm_arguments(parser: argparse.ArgumentParser) -> None:
    """Add native LLM integration arguments."""
    parser.add_argument(
        "--llm-provider",
        type=str,
        choices=[
            "anthropic",
            "openai",
            "google",
            "ollama",
            "lm-studio",
            "openai-compatible",
        ],
        metavar="PROVIDER",
        help="LLM provider: anthropic, openai, google (cloud) or ollama, lm-studio (local)",
    )
    parser.add_argument(
        "--anthropic-api-key",
        type=str,
        metavar="KEY",
        help="Anthropic API key (or set ANTHROPIC_API_KEY env var)",
    )
    parser.add_argument(
        "--openai-api-key",
        type=str,
        metavar="KEY",
        help="OpenAI API key (or set OPENAI_API_KEY env var)",
    )
    parser.add_argument(
        "--google-api-key",
        type=str,
        metavar="KEY",
        help="Google API key (or set GOOGLE_API_KEY env var)",
    )
    parser.add_argument(
        "--llm-model",
        type=str,
        metavar="MODEL",
        help="LLM model (e.g., claude-3-5-sonnet, gpt-4o, llama3.2, codellama)",
    )
    parser.add_argument(
        "--llm-temperature",
        type=float,
        default=0.7,
        metavar="TEMP",
        help="LLM temperature (0.0-1.0, default: 0.7)",
    )
    parser.add_argument(
        "--list-llm-providers",
        action="store_true",
        help="List available LLM providers and models",
    )
    # Local LLM options
    parser.add_argument(
        "--ollama-host",
        type=str,
        metavar="URL",
        help="Ollama server URL (default: http://localhost:11434)",
    )
    parser.add_argument(
        "--ollama-model",
        type=str,
        metavar="MODEL",
        help="Ollama model (e.g., llama3.2, mistral, codellama)",
    )
    parser.add_argument(
        "--openai-compatible-url",
        type=str,
        metavar="URL",
        help="OpenAI-compatible server URL (e.g., http://localhost:1234/v1 for LM Studio)",
    )
    parser.add_argument(
        "--prefer-local-llm",
        action="store_true",
        help="Prefer local LLM providers (Ollama, LM Studio) over cloud providers",
    )


def _add_multi_epic_arguments(parser: argparse.ArgumentParser) -> None:
    """Add multi-epic support arguments."""
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


def _add_multi_tracker_arguments(parser: argparse.ArgumentParser) -> None:
    """Add multi-tracker sync arguments."""
    parser.add_argument(
        "--sync-links", action="store_true", help="Sync issue links across projects"
    )
    parser.add_argument(
        "--analyze-links", action="store_true", help="Analyze links in markdown without syncing"
    )
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


def _add_attachment_arguments(parser: argparse.ArgumentParser) -> None:
    """Add attachment sync arguments."""
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


def _add_field_mapping_arguments(parser: argparse.ArgumentParser) -> None:
    """Add custom field mapping arguments."""
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


def _add_time_tracking_arguments(parser: argparse.ArgumentParser) -> None:
    """Add time tracking sync arguments."""
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
    parser.add_argument(
        "--sync-worklogs",
        action="store_true",
        help="Enable worklog/time log synchronization",
    )
    parser.add_argument(
        "--push-worklogs",
        action="store_true",
        help="Push local worklogs to tracker",
    )
    parser.add_argument(
        "--pull-worklogs",
        action="store_true",
        help="Pull worklogs from tracker to markdown",
    )
    parser.add_argument(
        "--worklog-author",
        type=str,
        metavar="NAME",
        help="Filter worklogs by author name",
    )


def _add_sprint_arguments(parser: argparse.ArgumentParser) -> None:
    """Add sprint sync arguments."""
    parser.add_argument(
        "--sync-sprints",
        action="store_true",
        help="Enable sprint/iteration synchronization",
    )
    parser.add_argument(
        "--list-sprints",
        action="store_true",
        help="List available sprints from the tracker",
    )
    parser.add_argument(
        "--sprint-board",
        type=str,
        metavar="BOARD_ID",
        help="Jira board ID for sprint operations",
    )
    parser.add_argument(
        "--default-sprint",
        type=str,
        metavar="NAME",
        help="Default sprint for stories without one",
    )
    parser.add_argument(
        "--use-active-sprint",
        action="store_true",
        help="Assign to active sprint if none specified",
    )


def _add_dependency_arguments(parser: argparse.ArgumentParser) -> None:
    """Add dependency sync arguments."""
    parser.add_argument(
        "--sync-dependencies",
        action="store_true",
        help="Enable dependency/relationship synchronization (blocks, depends-on)",
    )
    parser.add_argument(
        "--validate-dependencies",
        action="store_true",
        help="Validate dependency graph for cycles without syncing",
    )
    parser.add_argument(
        "--detect-cycles",
        action="store_true",
        help="Detect circular dependencies in the graph",
    )
    parser.add_argument(
        "--fail-on-cycle",
        action="store_true",
        help="Fail if circular dependencies are detected",
    )


def _add_hierarchy_arguments(parser: argparse.ArgumentParser) -> None:
    """Add epic hierarchy arguments."""
    parser.add_argument(
        "--sync-hierarchy",
        action="store_true",
        help="Enable epic hierarchy synchronization (parent/child epics)",
    )
    parser.add_argument(
        "--parent-epic",
        type=str,
        metavar="KEY",
        help="Parent epic key for this epic (creates hierarchy)",
    )
    parser.add_argument(
        "--epic-level",
        type=str,
        choices=["portfolio", "initiative", "theme", "epic", "feature"],
        default="epic",
        help="Hierarchy level of this epic (default: epic)",
    )
    parser.add_argument(
        "--show-hierarchy",
        action="store_true",
        help="Display epic hierarchy as a tree",
    )


def _add_workflow_arguments(parser: argparse.ArgumentParser) -> None:
    """Add workflow automation arguments."""
    parser.add_argument(
        "--apply-workflow",
        action="store_true",
        help="Apply workflow automation rules (auto-complete stories, etc.)",
    )
    parser.add_argument(
        "--auto-complete",
        action="store_true",
        help="Auto-complete parent when all children done",
    )
    parser.add_argument(
        "--auto-start",
        action="store_true",
        help="Auto-start parent when any child starts",
    )
    parser.add_argument(
        "--list-workflow-rules",
        action="store_true",
        help="List available workflow automation rules",
    )


def _add_command_arguments(parser: argparse.ArgumentParser) -> None:
    """Add new CLI command arguments."""
    group = parser.add_argument_group("Commands")
    group.add_argument("--doctor", action="store_true", help="Diagnose common setup issues")
    group.add_argument(
        "--stats", action="store_true", help="Show statistics (stories, points, velocity)"
    )
    group.add_argument(
        "--diff", action="store_true", help="Compare local file vs tracker state"
    )
    group.add_argument(
        "--import",
        dest="import_cmd",
        action="store_true",
        help="Import from tracker to create initial markdown",
    )
    group.add_argument(
        "--plan",
        action="store_true",
        help="Show side-by-side comparison before sync (like Terraform)",
    )
    group.add_argument("--migrate", action="store_true", help="Migrate between trackers")
    group.add_argument(
        "--migrate-source",
        type=str,
        metavar="TYPE",
        help="Source tracker type for migration (jira, github, linear)",
    )
    group.add_argument(
        "--migrate-target", type=str, metavar="TYPE", help="Target tracker type for migration"
    )
    group.add_argument(
        "--visualize", action="store_true", help="Generate dependency graph (Mermaid/Graphviz)"
    )
    group.add_argument(
        "--visualize-format",
        type=str,
        choices=["mermaid", "graphviz", "ascii"],
        default="mermaid",
        help="Output format for visualization",
    )
    group.add_argument(
        "--velocity", action="store_true", help="Track story points completed over time"
    )
    group.add_argument(
        "--velocity-add", action="store_true", help="Add current sprint to velocity data"
    )
    group.add_argument(
        "--sprint", type=str, metavar="NAME", help="Sprint name for velocity tracking"
    )
    group.add_argument(
        "--export-format",
        type=str,
        choices=["html", "pdf", "csv", "json", "docx"],
        default="html",
        help="Export format",
    )
    group.add_argument(
        "--report",
        type=str,
        metavar="PERIOD",
        nargs="?",
        const="weekly",
        help="Generate progress report (weekly, monthly, sprint)",
    )
    group.add_argument(
        "--config-validate",
        dest="config_validate",
        action="store_true",
        help="Validate configuration files",
    )
    group.add_argument(
        "--version-check",
        dest="version_check",
        action="store_true",
        help="Check for spectra updates",
    )
    group.add_argument(
        "--hook",
        type=str,
        metavar="ACTION",
        nargs="?",
        const="status",
        help="Git hook management (install, uninstall, status)",
    )
    group.add_argument(
        "--hook-type",
        type=str,
        choices=["pre-commit", "pre-push", "all"],
        default="pre-commit",
        help="Hook type to install/uninstall",
    )
    group.add_argument(
        "--tutorial",
        action="store_true",
        help="Run interactive tutorial",
    )
    group.add_argument(
        "--tutorial-step",
        type=int,
        metavar="N",
        help="Show specific tutorial step (1-based)",
    )
    group.add_argument(
        "--bulk-update",
        action="store_true",
        help="Bulk update stories by filter",
    )
    group.add_argument(
        "--bulk-assign",
        action="store_true",
        help="Bulk assign stories to user",
    )
    group.add_argument(
        "--filter",
        type=str,
        metavar="FILTER",
        help="Filter for bulk operations (e.g., 'status=planned,priority=high')",
    )
    group.add_argument(
        "--set",
        type=str,
        metavar="UPDATES",
        help="Updates for bulk-update (e.g., 'status=in_progress')",
    )
    group.add_argument(
        "--assignee",
        type=str,
        metavar="USER",
        help="User for bulk-assign",
    )
    group.add_argument(
        "--split",
        action="store_true",
        help="AI-powered story splitting suggestions",
    )
    group.add_argument(
        "--split-story",
        type=str,
        metavar="ID",
        help="Analyze specific story for splitting",
    )
    group.add_argument(
        "--split-threshold",
        type=int,
        default=4,
        metavar="N",
        help="Complexity threshold for split recommendations (1-10, default: 4)",
    )
    group.add_argument(
        "--generate-stories",
        action="store_true",
        help="Generate user stories from a high-level description using AI",
    )
    group.add_argument(
        "--description",
        type=str,
        metavar="TEXT",
        help="High-level feature description for AI story generation",
    )
    group.add_argument(
        "--description-file",
        type=str,
        metavar="FILE",
        help="File containing high-level feature description for AI story generation",
    )
    group.add_argument(
        "--generation-style",
        type=str,
        choices=["detailed", "standard", "minimal"],
        default="standard",
        metavar="STYLE",
        help="Story generation style: detailed, standard, minimal (default: standard)",
    )
    group.add_argument(
        "--max-stories",
        type=int,
        default=5,
        metavar="N",
        help="Maximum number of stories to generate (default: 5)",
    )
    group.add_argument(
        "--story-prefix",
        type=str,
        default="US",
        metavar="PREFIX",
        help="Story ID prefix (default: US)",
    )
    group.add_argument(
        "--project-context",
        type=str,
        metavar="TEXT",
        help="Project context to help AI generate better stories",
    )
    group.add_argument(
        "--tech-stack",
        type=str,
        metavar="TEXT",
        help="Tech stack info for AI story generation (e.g., 'React, Node.js, PostgreSQL')",
    )
    group.add_argument(
        "--generation-output",
        type=str,
        metavar="FILE",
        help="Output file for generated stories (default: stdout)",
    )
    group.add_argument(
        "--refine",
        action="store_true",
        help="AI-powered story quality analysis (ambiguity, missing AC, etc.)",
    )
    group.add_argument(
        "--refine-story",
        type=str,
        metavar="IDS",
        help="Comma-separated story IDs to analyze (default: all stories)",
    )
    group.add_argument(
        "--no-check-ambiguity",
        action="store_true",
        help="Skip ambiguity checks in refinement",
    )
    group.add_argument(
        "--no-check-ac",
        action="store_true",
        help="Skip acceptance criteria checks in refinement",
    )
    group.add_argument(
        "--no-check-scope",
        action="store_true",
        help="Skip scope/size checks in refinement",
    )
    group.add_argument(
        "--min-ac",
        type=int,
        default=2,
        metavar="N",
        help="Minimum acceptance criteria required (default: 2)",
    )
    group.add_argument(
        "--max-sp",
        type=int,
        default=13,
        metavar="N",
        help="Maximum story points before suggesting split (default: 13)",
    )
    group.add_argument(
        "--estimate",
        action="store_true",
        help="AI-powered story point estimation based on complexity",
    )
    group.add_argument(
        "--estimate-story",
        type=str,
        metavar="IDS",
        help="Comma-separated story IDs to estimate (default: all stories)",
    )
    group.add_argument(
        "--estimation-scale",
        type=str,
        choices=["fibonacci", "linear", "tshirt"],
        default="fibonacci",
        metavar="SCALE",
        help="Estimation scale: fibonacci, linear, tshirt (default: fibonacci)",
    )
    group.add_argument(
        "--team-velocity",
        type=int,
        default=0,
        metavar="N",
        help="Team velocity (points/sprint) for context",
    )
    group.add_argument(
        "--apply-estimates",
        action="store_true",
        help="Apply suggested estimates to the markdown file",
    )
    group.add_argument(
        "--no-complexity",
        action="store_true",
        help="Hide complexity breakdown in estimation output",
    )
    group.add_argument(
        "--no-reasoning",
        action="store_true",
        help="Hide estimation reasoning in output",
    )
    group.add_argument(
        "--label",
        action="store_true",
        help="AI-powered label suggestions based on story content",
    )
    group.add_argument(
        "--label-story",
        type=str,
        metavar="IDS",
        help="Comma-separated story IDs to label (default: all stories)",
    )
    group.add_argument(
        "--existing-labels",
        type=str,
        metavar="LABELS",
        help="Comma-separated list of existing labels to prefer",
    )
    group.add_argument(
        "--max-labels",
        type=int,
        default=5,
        metavar="N",
        help="Maximum labels per story (default: 5)",
    )
    group.add_argument(
        "--no-new-labels",
        action="store_true",
        help="Only suggest from existing labels, don't create new ones",
    )
    group.add_argument(
        "--label-style",
        type=str,
        choices=["kebab-case", "snake_case", "camelCase"],
        default="kebab-case",
        metavar="STYLE",
        help="Label formatting style (default: kebab-case)",
    )
    group.add_argument(
        "--apply-labels",
        action="store_true",
        help="Apply suggested labels to the markdown file",
    )
    group.add_argument(
        "--generate-markdown",
        action="store_true",
        help="Generate markdown for suggested split stories",
    )
    group.add_argument(
        "--generate-ac",
        action="store_true",
        help="AI-powered acceptance criteria generation from story descriptions",
    )
    group.add_argument(
        "--ac-story",
        type=str,
        metavar="IDS",
        help="Comma-separated story IDs to generate AC for (default: stories missing AC)",
    )
    group.add_argument(
        "--use-gherkin",
        action="store_true",
        help="Generate AC in Gherkin (Given/When/Then) format",
    )
    group.add_argument(
        "--include-security",
        action="store_true",
        help="Include security-related acceptance criteria",
    )
    group.add_argument(
        "--apply-ac",
        action="store_true",
        help="Apply generated acceptance criteria to the markdown file",
    )
    group.add_argument(
        "--dependencies",
        action="store_true",
        help="AI-powered detection of blocked-by relationships between stories",
    )
    group.add_argument(
        "--no-technical-deps",
        action="store_true",
        help="Skip technical dependency detection",
    )
    group.add_argument(
        "--no-data-deps",
        action="store_true",
        help="Skip data dependency detection",
    )
    group.add_argument(
        "--no-feature-deps",
        action="store_true",
        help="Skip feature dependency detection",
    )
    group.add_argument(
        "--no-circular-check",
        action="store_true",
        help="Skip circular dependency detection",
    )
    group.add_argument(
        "--architecture",
        type=str,
        metavar="ARCH",
        help="Architecture type (e.g., 'microservices', 'monolith')",
    )
    group.add_argument(
        "--show-graph",
        action="store_true",
        help="Show ASCII dependency graph",
    )
    group.add_argument(
        "--quality",
        action="store_true",
        help="AI-powered story quality scoring based on INVEST principles",
    )
    group.add_argument(
        "--quality-story",
        type=str,
        metavar="IDS",
        help="Comma-separated story IDs to score (default: all stories)",
    )
    group.add_argument(
        "--min-score",
        type=int,
        default=50,
        metavar="N",
        help="Minimum passing score threshold (default: 50)",
    )
    group.add_argument(
        "--no-details",
        action="store_true",
        help="Hide detailed dimension scores",
    )
    group.add_argument(
        "--duplicates",
        action="store_true",
        help="AI-powered detection of duplicate/similar stories",
    )
    group.add_argument(
        "--compare-files",
        type=str,
        metavar="FILES",
        help="Comma-separated additional files to compare for duplicates",
    )
    group.add_argument(
        "--min-similarity",
        type=float,
        default=0.40,
        metavar="N",
        help="Minimum similarity threshold 0.0-1.0 (default: 0.40)",
    )
    group.add_argument(
        "--no-llm-duplicates",
        action="store_true",
        help="Use text-based similarity only, skip LLM analysis",
    )
    group.add_argument(
        "--gaps",
        action="store_true",
        help="AI-powered gap analysis to identify missing requirements",
    )
    group.add_argument(
        "--industry",
        type=str,
        metavar="INDUSTRY",
        help="Industry context for gap analysis (e.g., healthcare, fintech)",
    )
    group.add_argument(
        "--expected-personas",
        type=str,
        metavar="PERSONAS",
        help="Comma-separated list of expected user personas",
    )
    group.add_argument(
        "--expected-integrations",
        type=str,
        metavar="INTEGRATIONS",
        help="Comma-separated list of expected integrations",
    )
    group.add_argument(
        "--compliance",
        type=str,
        metavar="REQS",
        help="Comma-separated compliance requirements (e.g., GDPR,HIPAA)",
    )
    group.add_argument(
        "--no-suggestions",
        action="store_true",
        help="Skip generating story suggestions for gaps",
    )
    group.add_argument(
        "--sync-summary",
        action="store_true",
        help="Generate AI-powered human-readable sync summary",
    )
    group.add_argument(
        "--sync-log",
        type=str,
        metavar="PATH",
        help="Path to sync log file (JSON) for summary generation",
    )
    group.add_argument(
        "--audience",
        type=str,
        choices=["technical", "manager", "stakeholder"],
        default="technical",
        help="Target audience for sync summary (default: technical)",
    )
    group.add_argument(
        "--copy-summary",
        action="store_true",
        help="Copy generated summary to clipboard",
    )
    group.add_argument(
        "--prompts",
        type=str,
        nargs="?",
        const="list",
        metavar="ACTION",
        help="Manage AI prompts (list, view, export, init, types)",
    )
    group.add_argument(
        "--prompt-name",
        type=str,
        metavar="NAME",
        help="Name of specific prompt to view",
    )
    group.add_argument(
        "--prompt-type",
        type=str,
        metavar="TYPE",
        help="Type of prompt to filter by",
    )
    group.add_argument(
        "--prompts-config",
        type=str,
        metavar="PATH",
        help="Path to custom prompts configuration file",
    )
    group.add_argument(
        "--export-prompts",
        type=str,
        metavar="PATH",
        help="Export default prompts to file for customization",
    )
    group.add_argument(
        "--parallel",
        action="store_true",
        help="Enable parallel sync for multiple epics",
    )
    group.add_argument(
        "--parallel-files",
        action="store_true",
        help="Enable parallel file processing for multiple files concurrently",
    )
    group.add_argument(
        "--workers",
        type=int,
        default=4,
        metavar="N",
        help="Number of parallel workers for multi-epic/file sync (default: 4)",
    )
    group.add_argument(
        "--file-timeout",
        type=float,
        default=600.0,
        metavar="SECS",
        help="Timeout in seconds per file in parallel mode (default: 600)",
    )
    group.add_argument(
        "--skip-empty",
        action="store_true",
        default=True,
        help="Skip files with no epics in parallel mode (default: True)",
    )
    group.add_argument(
        "--input-files",
        type=str,
        nargs="+",
        metavar="FILE",
        help="Multiple input files for parallel processing",
    )
    group.add_argument(
        "--archive",
        type=str,
        nargs="?",
        const="list",
        metavar="ACTION",
        help="Archive management (list, archive, unarchive)",
    )
    group.add_argument(
        "--archive-days",
        type=int,
        default=90,
        metavar="N",
        help="Days threshold for auto-archive detection (default: 90)",
    )
    group.add_argument(
        "--story-keys",
        type=str,
        metavar="KEYS",
        help="Comma-separated story keys for archive/unarchive",
    )
