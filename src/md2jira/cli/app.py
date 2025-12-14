"""
CLI App - Main entry point for md2jira command line tool.
"""

import argparse
import logging
import sys
from pathlib import Path

from .output import Console, Symbols
from .exit_codes import ExitCode
from ..adapters import (
    JiraAdapter,
    MarkdownParser,
    ADFFormatter,
    EnvironmentConfigProvider,
)
from ..application import SyncOrchestrator
from ..core.domain.events import EventBus


def create_parser() -> argparse.ArgumentParser:
    """
    Create the command-line argument parser for md2jira.
    
    Defines all CLI arguments including required inputs (markdown file, epic key),
    execution modes, phase control, filters, and output options.
    
    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        prog="md2jira",
        description="Sync markdown epic documentation with Jira",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # First-time setup wizard
  md2jira --init

  # Generate markdown template from existing Jira epic
  md2jira --generate --epic PROJ-123 --execute
  
  # Preview generated template before writing
  md2jira --generate --epic PROJ-123 --preview

  # Validate markdown file format
  md2jira --validate --markdown EPIC.md
  
  # Strict validation (warnings are errors)
  md2jira --validate --markdown EPIC.md --strict

  # Show status dashboard
  md2jira --dashboard --markdown EPIC.md --epic PROJ-123

  # Enable OpenTelemetry tracing
  md2jira --otel-enable --otel-endpoint http://localhost:4317 --markdown EPIC.md --epic PROJ-123

  # Enable Prometheus metrics (exposed on :9090/metrics)
  md2jira --prometheus --prometheus-port 9090 --markdown EPIC.md --epic PROJ-123

  # Enable health check endpoint (for Kubernetes/Docker)
  md2jira --health --health-port 8080 --markdown EPIC.md --epic PROJ-123

  # Analyze without making changes (dry-run)
  md2jira --markdown EPIC.md --epic PROJ-123

  # Execute sync with confirmations
  md2jira --markdown EPIC.md --epic PROJ-123 --execute

  # Full sync without prompts
  md2jira --markdown EPIC.md --epic PROJ-123 --execute --no-confirm

  # Interactive mode - step-by-step guided sync
  md2jira --markdown EPIC.md --epic PROJ-123 --interactive

  # Sync only descriptions
  md2jira --markdown EPIC.md --epic PROJ-123 --execute --phase descriptions

  # Verbose output for debugging
  md2jira --markdown EPIC.md --epic PROJ-123 -v

  # Pull from Jira to markdown (reverse sync)
  md2jira --pull --epic PROJ-123 --pull-output EPIC.md --execute

  # Preview what would be pulled from Jira
  md2jira --pull --epic PROJ-123 --preview

  # Update existing markdown from Jira
  md2jira --pull --epic PROJ-123 --markdown EPIC.md --update-existing --execute

  # Watch mode - auto-sync on file changes
  md2jira --watch --markdown EPIC.md --epic PROJ-123 --execute

  # Watch mode with custom debounce (5 seconds between syncs)
  md2jira --watch --markdown EPIC.md --epic PROJ-123 --execute --debounce 5

  # Scheduled sync - every 5 minutes
  md2jira --schedule 5m --markdown EPIC.md --epic PROJ-123 --execute

  # Scheduled sync - daily at 9:00 AM
  md2jira --schedule daily:09:00 --markdown EPIC.md --epic PROJ-123 --execute

  # Scheduled sync - run immediately, then every hour
  md2jira --schedule 1h --markdown EPIC.md --epic PROJ-123 --execute --run-now

  # Webhook server - receive Jira webhooks for auto reverse sync
  md2jira --webhook --epic PROJ-123 --pull-output EPIC.md --execute

  # Webhook server on custom port with secret
  md2jira --webhook --webhook-port 9000 --webhook-secret mysecret --epic PROJ-123 --pull-output EPIC.md --execute

  # Multi-epic sync - sync all epics from one file
  md2jira --multi-epic --markdown ROADMAP.md --execute

  # Multi-epic with filter - sync only specific epics  
  md2jira --multi-epic --markdown ROADMAP.md --epic-filter PROJ-100,PROJ-200 --execute

  # List epics in a multi-epic file
  md2jira --list-epics --markdown ROADMAP.md

  # Sync cross-project links from markdown
  md2jira --sync-links --markdown EPIC.md --epic PROJ-123 --execute

  # Analyze links without syncing
  md2jira --analyze-links --markdown EPIC.md --epic PROJ-123

Environment Variables:
  JIRA_URL         Jira instance URL (e.g., https://company.atlassian.net)
  JIRA_EMAIL       Jira account email
  JIRA_API_TOKEN   Jira API token
        """
    )
    
    # Required arguments (conditionally required - not needed for --completions)
    parser.add_argument(
        "--markdown", "-m",
        type=str,
        help="Path to markdown epic file"
    )
    parser.add_argument(
        "--epic", "-e",
        type=str,
        help="Jira epic key (e.g., PROJ-123)"
    )
    
    # Execution mode
    parser.add_argument(
        "--execute", "-x",
        action="store_true",
        help="Execute changes (default is dry-run)"
    )
    parser.add_argument(
        "--no-confirm",
        action="store_true",
        help="Skip confirmation prompts"
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Only sync changed stories (skip unchanged)"
    )
    parser.add_argument(
        "--force-full-sync",
        action="store_true",
        help="Force full sync even when --incremental is set"
    )
    
    # Phase control
    parser.add_argument(
        "--phase",
        type=str,
        choices=["all", "descriptions", "subtasks", "comments", "statuses"],
        default="all",
        help="Which phase to run (default: all)"
    )
    
    # Filters
    parser.add_argument(
        "--story",
        type=str,
        help="Filter to specific story ID (e.g., US-001)"
    )
    
    # Configuration
    parser.add_argument(
        "--config", "-c",
        type=str,
        help="Path to config file (.md2jira.yaml, .md2jira.toml)"
    )
    parser.add_argument(
        "--jira-url",
        type=str,
        help="Override Jira URL"
    )
    parser.add_argument(
        "--project",
        type=str,
        help="Override Jira project key"
    )
    
    # Output options
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Quiet mode - only show errors and final summary (for CI/scripting)"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        choices=["text", "json"],
        default="text",
        help="Output format: text (default) or json for programmatic use"
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output"
    )
    parser.add_argument(
        "--log-format",
        type=str,
        choices=["text", "json"],
        default="text",
        help="Log format: text (default) or json for structured log aggregation"
    )
    parser.add_argument(
        "--log-file",
        type=str,
        metavar="PATH",
        help="Write logs to file (in addition to stderr)"
    )
    parser.add_argument(
        "--audit-trail",
        type=str,
        metavar="PATH",
        help="Export audit trail to JSON file (records all operations)"
    )
    parser.add_argument(
        "--export",
        type=str,
        help="Export analysis to JSON file"
    )
    
    # Backup options
    parser.add_argument(
        "--backup",
        action="store_true",
        default=True,
        help="Create backup before sync (default: enabled)"
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Disable automatic backup before sync"
    )
    parser.add_argument(
        "--backup-dir",
        type=str,
        metavar="PATH",
        help="Custom directory for backups (default: ~/.md2jira/backups)"
    )
    parser.add_argument(
        "--list-backups",
        action="store_true",
        help="List available backups for the specified epic"
    )
    parser.add_argument(
        "--restore-backup",
        type=str,
        metavar="BACKUP_ID",
        help="Restore Jira state from a backup (use --list-backups to see available backups)"
    )
    parser.add_argument(
        "--diff-backup",
        type=str,
        metavar="BACKUP_ID",
        help="Show diff between backup and current Jira state"
    )
    parser.add_argument(
        "--diff-latest",
        action="store_true",
        help="Show diff between latest backup and current Jira state"
    )
    parser.add_argument(
        "--rollback",
        action="store_true",
        help="Undo last sync by restoring from most recent backup (requires --epic)"
    )
    
    # Special modes
    parser.add_argument(
        "--init",
        action="store_true",
        help="Run first-time setup wizard to configure md2jira"
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate markdown file format"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Strict validation mode: treat warnings as errors (used with --validate)"
    )
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Show TUI dashboard with sync status overview"
    )
    
    # OpenTelemetry arguments
    parser.add_argument(
        "--otel-enable",
        action="store_true",
        help="Enable OpenTelemetry tracing and metrics"
    )
    parser.add_argument(
        "--otel-endpoint",
        metavar="URL",
        help="OTLP exporter endpoint (e.g., http://localhost:4317)"
    )
    parser.add_argument(
        "--otel-service-name",
        metavar="NAME",
        default="md2jira",
        help="Service name for traces/metrics (default: md2jira)"
    )
    parser.add_argument(
        "--otel-console",
        action="store_true",
        help="Export traces/metrics to console (for debugging)"
    )
    
    # Prometheus metrics arguments
    parser.add_argument(
        "--prometheus",
        action="store_true",
        help="Enable Prometheus metrics HTTP server"
    )
    parser.add_argument(
        "--prometheus-port",
        type=int,
        default=9090,
        metavar="PORT",
        help="Prometheus metrics port (default: 9090)"
    )
    parser.add_argument(
        "--prometheus-host",
        default="0.0.0.0",
        metavar="HOST",
        help="Prometheus metrics host (default: 0.0.0.0)"
    )
    
    # Health check arguments
    parser.add_argument(
        "--health",
        action="store_true",
        help="Enable health check HTTP endpoint"
    )
    parser.add_argument(
        "--health-port",
        type=int,
        default=8080,
        metavar="PORT",
        help="Health check port (default: 8080)"
    )
    parser.add_argument(
        "--health-host",
        default="0.0.0.0",
        metavar="HOST",
        help="Health check host (default: 0.0.0.0)"
    )
    
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Interactive mode with step-by-step guided sync"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume an interrupted sync session"
    )
    parser.add_argument(
        "--resume-session",
        type=str,
        metavar="SESSION_ID",
        help="Resume a specific sync session by ID"
    )
    parser.add_argument(
        "--list-sessions",
        action="store_true",
        help="List all resumable sync sessions"
    )
    parser.add_argument(
        "--completions",
        type=str,
        choices=["bash", "zsh", "fish"],
        metavar="SHELL",
        help="Generate shell completion script (bash, zsh, fish)"
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 2.0.0"
    )
    
    # Template generation
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Generate markdown template from existing Jira epic"
    )
    parser.add_argument(
        "--generate-output",
        type=str,
        dest="generate_output",
        metavar="PATH",
        help="Output path for generated markdown (defaults to EPIC_KEY.md)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite output file without confirmation (used with --generate)"
    )
    parser.add_argument(
        "--no-subtasks",
        action="store_true",
        help="Don't include existing subtasks in generated template"
    )
    parser.add_argument(
        "--no-descriptions",
        action="store_true",
        help="Don't include descriptions in generated template"
    )
    
    # Bidirectional sync (pull from Jira)
    parser.add_argument(
        "--pull",
        action="store_true",
        help="Pull changes FROM Jira to markdown (reverse sync)"
    )
    parser.add_argument(
        "--pull-output",
        type=str,
        dest="pull_output",
        metavar="PATH",
        help="Output path for pulled markdown (used with --pull)"
    )
    parser.add_argument(
        "--update-existing",
        action="store_true",
        help="Update existing markdown file instead of overwriting (used with --pull)"
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Preview what would be pulled without making changes (used with --pull)"
    )
    
    # Conflict detection
    parser.add_argument(
        "--check-conflicts",
        action="store_true",
        help="Check for conflicts before syncing (compares with last sync state)"
    )
    parser.add_argument(
        "--conflict-strategy",
        type=str,
        choices=["ask", "force-local", "force-remote", "skip", "abort"],
        default="ask",
        help="How to resolve conflicts: ask (interactive), force-local (take markdown), "
             "force-remote (take Jira), skip (skip conflicts), abort (fail on conflicts)"
    )
    parser.add_argument(
        "--save-snapshot",
        action="store_true",
        default=True,
        help="Save sync snapshot after successful sync (enables conflict detection)"
    )
    parser.add_argument(
        "--no-snapshot",
        action="store_true",
        help="Don't save sync snapshot after sync"
    )
    parser.add_argument(
        "--list-snapshots",
        action="store_true",
        help="List all stored sync snapshots"
    )
    parser.add_argument(
        "--clear-snapshot",
        action="store_true",
        help="Clear the sync snapshot for the specified epic (resets conflict baseline)"
    )
    
    # Watch mode
    parser.add_argument(
        "--watch", "-w",
        action="store_true",
        help="Watch mode: auto-sync on file changes"
    )
    parser.add_argument(
        "--debounce",
        type=float,
        default=2.0,
        metavar="SECONDS",
        help="Minimum time between syncs in watch mode (default: 2.0)"
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=1.0,
        metavar="SECONDS",
        help="How often to check for file changes (default: 1.0)"
    )
    
    # Scheduled sync
    parser.add_argument(
        "--schedule",
        type=str,
        metavar="SPEC",
        help="Run sync on a schedule. Formats: 30s, 5m, 1h (interval), "
             "daily:HH:MM, hourly:MM, cron:MIN HOUR DOW"
    )
    parser.add_argument(
        "--run-now",
        action="store_true",
        help="Run sync immediately when starting scheduled mode"
    )
    parser.add_argument(
        "--max-runs",
        type=int,
        metavar="N",
        help="Maximum number of scheduled runs (default: unlimited)"
    )
    
    # Webhook receiver
    parser.add_argument(
        "--webhook",
        action="store_true",
        help="Start webhook server to receive Jira events for reverse sync"
    )
    parser.add_argument(
        "--webhook-host",
        type=str,
        default="0.0.0.0",
        metavar="HOST",
        help="Host to bind webhook server to (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--webhook-port",
        type=int,
        default=8080,
        metavar="PORT",
        help="Port for webhook server (default: 8080)"
    )
    parser.add_argument(
        "--webhook-secret",
        type=str,
        metavar="SECRET",
        help="Webhook secret for signature verification"
    )
    
    # Multi-epic support
    parser.add_argument(
        "--multi-epic",
        action="store_true",
        help="Enable multi-epic mode for files containing multiple epics"
    )
    parser.add_argument(
        "--epic-filter",
        type=str,
        metavar="KEYS",
        help="Comma-separated list of epic keys to sync (e.g., PROJ-100,PROJ-200)"
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop syncing on first epic error in multi-epic mode"
    )
    parser.add_argument(
        "--list-epics",
        action="store_true",
        help="List epics found in markdown file without syncing"
    )
    
    # Cross-project linking
    parser.add_argument(
        "--sync-links",
        action="store_true",
        help="Sync issue links across projects"
    )
    parser.add_argument(
        "--analyze-links",
        action="store_true",
        help="Analyze links in markdown without syncing"
    )
    
    return parser


def validate_markdown(
    console: Console,
    markdown_path: str,
    strict: bool = False,
) -> int:
    """
    Validate a markdown file's format and structure.
    
    Performs comprehensive validation including structure checks,
    story content validation, and best practice suggestions.
    
    Args:
        console: Console instance for output.
        markdown_path: Path to the markdown file to validate.
        strict: If True, treat warnings as errors.
        
    Returns:
        Exit code (0 for success, non-zero for errors).
    """
    from .validate import run_validate
    return run_validate(console, markdown_path, strict=strict)


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
            print(f"\033[1m{session_id:<14} {epic:<12} {phase:<12} {progress:<10} {updated:<20}\033[0m")
        else:
            print(f"{session_id:<14} {epic:<12} {phase:<12} {progress:<10} {updated:<20}")
    
    print()
    print("To resume a session:")
    print("  md2jira --resume-session <SESSION_ID> --execute")
    
    return ExitCode.SUCCESS


def list_backups(backup_manager, epic_key: str = None) -> int:
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
    from .exit_codes import ExitCode
    from .logging import setup_logging
    from ..application.sync import BackupManager
    from ..adapters import JiraAdapter, ADFFormatter, EnvironmentConfigProvider
    
    # Setup logging
    log_level = logging.DEBUG if getattr(args, 'verbose', False) else logging.INFO
    log_format = getattr(args, "log_format", "text")
    setup_logging(level=log_level, log_format=log_format)
    
    # Create console
    console = Console(
        color=not getattr(args, 'no_color', False),
        verbose=getattr(args, 'verbose', False),
        quiet=getattr(args, 'quiet', False),
    )
    
    backup_id = args.restore_backup
    epic_key = getattr(args, 'epic', None)
    dry_run = not getattr(args, 'execute', False)
    
    console.header("md2jira Restore")
    
    # Load backup first to get epic key if not provided
    backup_dir = Path(args.backup_dir) if getattr(args, 'backup_dir', None) else None
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
    config_file = Path(args.config) if getattr(args, 'config', None) else None
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
    if not dry_run and not getattr(args, 'no_confirm', False):
        console.warning("This will restore Jira issues to their backed-up state!")
        console.detail(f"  {backup.issue_count} issues and {backup.subtask_count} subtasks may be modified")
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
    console.detail(f"  Operations: {result.successful_operations} succeeded, {result.failed_operations} failed, {result.skipped_operations} skipped")
    
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
    from .exit_codes import ExitCode
    from .logging import setup_logging
    from ..application.sync import BackupManager, compare_backup_to_current
    from ..adapters import JiraAdapter, ADFFormatter, EnvironmentConfigProvider
    
    # Setup logging
    log_level = logging.DEBUG if getattr(args, 'verbose', False) else logging.INFO
    log_format = getattr(args, "log_format", "text")
    setup_logging(level=log_level, log_format=log_format)
    
    # Create console
    console = Console(
        color=not getattr(args, 'no_color', False),
        verbose=getattr(args, 'verbose', False),
        quiet=getattr(args, 'quiet', False),
    )
    
    backup_id = getattr(args, 'diff_backup', None)
    diff_latest = getattr(args, 'diff_latest', False)
    epic_key = getattr(args, 'epic', None)
    
    console.header("md2jira Diff View")
    
    # Load backup
    backup_dir = Path(args.backup_dir) if getattr(args, 'backup_dir', None) else None
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
    config_file = Path(args.config) if getattr(args, 'config', None) else None
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
        console.warning(f"Found changes in {result.changed_issues}/{result.total_issues} issues ({result.total_changes} field changes)")
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
    from .exit_codes import ExitCode
    from .logging import setup_logging
    from ..application.sync import BackupManager, compare_backup_to_current
    from ..adapters import JiraAdapter, ADFFormatter, EnvironmentConfigProvider
    
    # Setup logging
    log_level = logging.DEBUG if getattr(args, 'verbose', False) else logging.INFO
    log_format = getattr(args, "log_format", "text")
    setup_logging(level=log_level, log_format=log_format)
    
    # Create console
    console = Console(
        color=not getattr(args, 'no_color', False),
        verbose=getattr(args, 'verbose', False),
        quiet=getattr(args, 'quiet', False),
    )
    
    epic_key = getattr(args, 'epic', None)
    dry_run = not getattr(args, 'execute', False)
    
    if not epic_key:
        console.error("--rollback requires --epic to be specified")
        return ExitCode.CONFIG_ERROR
    
    console.header("md2jira Rollback")
    
    # Find latest backup
    backup_dir = Path(args.backup_dir) if getattr(args, 'backup_dir', None) else None
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
    config_file = Path(args.config) if getattr(args, 'config', None) else None
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
    if not dry_run and not getattr(args, 'no_confirm', False):
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
    from .logging import setup_logging
    from ..application.sync import SyncOrchestrator, LinkSyncOrchestrator
    from ..adapters import JiraAdapter, ADFFormatter, EnvironmentConfigProvider
    from ..adapters.parsers import MarkdownParser
    
    # Setup logging
    log_level = logging.DEBUG if getattr(args, 'verbose', False) else logging.INFO
    log_format = getattr(args, "log_format", "text")
    setup_logging(level=log_level, log_format=log_format)
    
    # Create console
    console = Console(
        color=not getattr(args, 'no_color', False),
        verbose=getattr(args, 'verbose', False),
        quiet=getattr(args, 'quiet', False),
    )
    
    markdown_path = args.markdown
    epic_key = args.epic
    dry_run = not getattr(args, 'execute', False)
    analyze_only = getattr(args, 'analyze_links', False)
    
    # Check markdown file exists
    if not Path(markdown_path).exists():
        console.error(f"Markdown file not found: {markdown_path}")
        return ExitCode.FILE_NOT_FOUND
    
    console.header("md2jira Link Sync")
    
    if analyze_only:
        console.info("Analyze mode - no changes will be made")
    elif dry_run:
        console.dry_run_banner()
    
    # Load configuration
    config_file = Path(args.config) if getattr(args, 'config', None) else None
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
    
    if analysis['link_types']:
        print()
        console.info("Link types:")
        for link_type, count in analysis['link_types'].items():
            console.item(f"{link_type}: {count}", "info")
    
    if analysis['target_projects']:
        print()
        console.info("Target projects:")
        for project, count in analysis['target_projects'].items():
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
    console.item(f"Links created: {result.links_created}", "success" if result.links_created else "info")
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
    from .logging import setup_logging
    from ..application.sync import MultiEpicSyncOrchestrator
    from ..adapters import JiraAdapter, ADFFormatter, EnvironmentConfigProvider
    from ..adapters.parsers import MarkdownParser
    
    # Setup logging
    log_level = logging.DEBUG if getattr(args, 'verbose', False) else logging.INFO
    log_format = getattr(args, "log_format", "text")
    setup_logging(level=log_level, log_format=log_format)
    
    # Create console
    console = Console(
        color=not getattr(args, 'no_color', False),
        verbose=getattr(args, 'verbose', False),
        quiet=getattr(args, 'quiet', False),
    )
    
    markdown_path = args.markdown
    dry_run = not getattr(args, 'execute', False)
    list_only = getattr(args, 'list_epics', False)
    epic_filter_str = getattr(args, 'epic_filter', None)
    stop_on_error = getattr(args, 'stop_on_error', False)
    
    # Parse epic filter
    epic_filter = None
    if epic_filter_str:
        epic_filter = [k.strip() for k in epic_filter_str.split(',')]
    
    # Check markdown file exists
    if not Path(markdown_path).exists():
        console.error(f"Markdown file not found: {markdown_path}")
        return ExitCode.FILE_NOT_FOUND
    
    console.header("md2jira Multi-Epic Sync")
    
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
    config_file = Path(args.config) if getattr(args, 'config', None) else None
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
    
    for epic_info in summary['epics']:
        console.item(f"{epic_info['key']}: {epic_info['title']} ({epic_info['stories']} stories)", "info")
    
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
    console.info(f"Stories: {result.total_stories_matched} matched, {result.total_stories_updated} updated")
    console.info(f"Subtasks: {result.total_subtasks_created} created")
    
    if result.errors:
        print()
        console.error(f"Errors ({len(result.errors)}):")
        for error in result.errors[:5]:
            console.item(error, "fail")
    
    return ExitCode.SUCCESS if result.success else ExitCode.SYNC_ERROR


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
    from .logging import setup_logging
    from ..application import WebhookServer, WebhookDisplay
    from ..application.sync import ReverseSyncOrchestrator
    from ..adapters import JiraAdapter, ADFFormatter, EnvironmentConfigProvider
    from ..adapters.formatters import MarkdownWriter
    
    # Setup logging
    log_level = logging.DEBUG if getattr(args, 'verbose', False) else logging.INFO
    log_format = getattr(args, "log_format", "text")
    setup_logging(level=log_level, log_format=log_format)
    
    # Create console
    console = Console(
        color=not getattr(args, 'no_color', False),
        verbose=getattr(args, 'verbose', False),
        quiet=getattr(args, 'quiet', False),
    )
    
    epic_key = args.epic
    output_path = getattr(args, 'pull_output', None) or f"{epic_key}.md"
    host = getattr(args, 'webhook_host', '0.0.0.0')
    port = getattr(args, 'webhook_port', 8080)
    secret = getattr(args, 'webhook_secret', None)
    dry_run = not getattr(args, 'execute', False)
    
    # Load configuration
    config_file = Path(args.config) if getattr(args, 'config', None) else None
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
    console.header("md2jira Webhook Server")
    
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
        color=not getattr(args, 'no_color', False),
        quiet=getattr(args, 'quiet', False),
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
    from .logging import setup_logging
    from ..application import (
        SyncOrchestrator,
        ScheduledSyncRunner,
        ScheduleDisplay,
        parse_schedule,
    )
    from ..adapters import JiraAdapter, MarkdownParser, ADFFormatter, EnvironmentConfigProvider
    
    # Setup logging
    log_level = logging.DEBUG if getattr(args, 'verbose', False) else logging.INFO
    log_format = getattr(args, "log_format", "text")
    setup_logging(level=log_level, log_format=log_format)
    
    # Create console
    console = Console(
        color=not getattr(args, 'no_color', False),
        verbose=getattr(args, 'verbose', False),
        quiet=getattr(args, 'quiet', False),
    )
    
    markdown_path = args.markdown
    epic_key = args.epic
    schedule_spec = args.schedule
    run_now = getattr(args, 'run_now', False)
    max_runs = getattr(args, 'max_runs', None)
    dry_run = not getattr(args, 'execute', False)
    
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
    config_file = Path(args.config) if getattr(args, 'config', None) else None
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
    console.header("md2jira Scheduled Sync")
    
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
        color=not getattr(args, 'no_color', False),
        quiet=getattr(args, 'quiet', False),
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
    from .logging import setup_logging
    from ..application import SyncOrchestrator, WatchOrchestrator, WatchDisplay
    from ..adapters import JiraAdapter, MarkdownParser, ADFFormatter, EnvironmentConfigProvider
    
    # Setup logging
    log_level = logging.DEBUG if getattr(args, 'verbose', False) else logging.INFO
    log_format = getattr(args, "log_format", "text")
    setup_logging(level=log_level, log_format=log_format)
    
    # Create console
    console = Console(
        color=not getattr(args, 'no_color', False),
        verbose=getattr(args, 'verbose', False),
        quiet=getattr(args, 'quiet', False),
    )
    
    markdown_path = args.markdown
    epic_key = args.epic
    debounce = getattr(args, 'debounce', 2.0)
    poll_interval = getattr(args, 'poll_interval', 1.0)
    dry_run = not getattr(args, 'execute', False)
    
    # Validate markdown exists
    if not Path(markdown_path).exists():
        console.error(f"Markdown file not found: {markdown_path}")
        return ExitCode.FILE_NOT_FOUND
    
    # Load configuration
    config_file = Path(args.config) if getattr(args, 'config', None) else None
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
    console.header("md2jira Watch Mode")
    
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
        color=not getattr(args, 'no_color', False),
        quiet=getattr(args, 'quiet', False),
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
    from ..application.sync import SnapshotStore
    
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
    from ..application.sync import SnapshotStore
    
    store = SnapshotStore()
    
    if store.delete(epic_key):
        print(f"✓ Cleared snapshot for {epic_key}")
        print("  Next sync will not detect conflicts (fresh baseline)")
        return ExitCode.SUCCESS
    else:
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
    from .logging import setup_logging
    from ..application.sync import ReverseSyncOrchestrator
    from ..adapters import JiraAdapter, ADFFormatter, EnvironmentConfigProvider
    from ..adapters.formatters import MarkdownWriter
    
    # Setup logging
    log_level = logging.DEBUG if getattr(args, 'verbose', False) else logging.INFO
    log_format = getattr(args, "log_format", "text")
    setup_logging(level=log_level, log_format=log_format)
    
    # Create console
    console = Console(
        color=not getattr(args, 'no_color', False),
        verbose=getattr(args, 'verbose', False),
        quiet=getattr(args, 'quiet', False),
    )
    
    epic_key = args.epic
    output_path = getattr(args, 'pull_output', None)
    existing_markdown = getattr(args, 'markdown', None)
    preview_only = getattr(args, 'preview', False)
    update_existing = getattr(args, 'update_existing', False)
    dry_run = not getattr(args, 'execute', False)
    
    # Determine output path
    if not output_path:
        if existing_markdown and update_existing:
            output_path = existing_markdown
        else:
            output_path = f"{epic_key}.md"
    
    console.header("md2jira Pull (Reverse Sync)")
    console.info(f"Epic: {epic_key}")
    console.info(f"Output: {output_path}")
    
    if dry_run:
        console.dry_run_banner()
    
    # Load configuration
    config_file = Path(args.config) if getattr(args, 'config', None) else None
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
    if not dry_run and not getattr(args, 'no_confirm', False):
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
    
    # Validate markdown exists
    markdown_path = Path(args.markdown)
    if not markdown_path.exists():
        console.error_rich(FileNotFoundError(markdown_path))
        return ExitCode.FILE_NOT_FOUND
    
    # Show header
    console.header(f"md2jira {Symbols.ROCKET}")
    
    if config.sync.dry_run:
        console.dry_run_banner()

    # Show config source if loaded from file
    if config_provider.config_file_path:
        console.info(f"Config: {config_provider.config_file_path}")

    console.info(f"Markdown: {markdown_path}")
    console.info(f"Epic: {args.epic}")
    console.info(f"Mode: {'Execute' if args.execute else 'Dry-run'}")
    if getattr(args, 'incremental', False):
        console.info(f"Incremental: Enabled (only changed stories)")
    if args.execute and config.sync.backup_enabled:
        console.info(f"Backup: Enabled")
    
    # Initialize components
    event_bus = EventBus()
    formatter = ADFFormatter()
    parser = MarkdownParser()
    
    # Setup audit trail if requested
    audit_trail = None
    audit_recorder = None
    audit_trail_path = getattr(args, "audit_trail", None)
    if audit_trail_path and isinstance(audit_trail_path, str):
        from ..application.sync.audit import create_audit_trail, AuditTrailRecorder
        from ..application.sync.state import SyncState
        
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
    
    # Create state store for persistence
    from ..application.sync import StateStore
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
            resume_state = state_store.find_latest_resumable(
                str(markdown_path), args.epic
            )
        
        if resume_state:
            console.info(f"Resuming session: {resume_state.session_id}")
            console.detail(f"Progress: {resume_state.completed_count}/{resume_state.total_count} operations")
            console.detail(f"Phase: {resume_state.phase}")
        elif args.resume:
            console.info("No resumable session found, starting fresh")
    
    # Confirmation
    if args.execute and not args.no_confirm:
        action = "Resume sync" if resume_state else "Proceed with sync"
        if not console.confirm(f"{action} execution?"):
            console.warning("Cancelled by user")
            return ExitCode.CANCELLED
    
    # Run sync with progress callback
    def progress_callback(phase: str, current: int, total: int) -> None:
        console.progress(current, total, phase)
    
    console.section("Running Sync")
    
    # Use resumable sync for state persistence
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
    elif hasattr(result, 'failed_operations') and result.failed_operations:
        # Partial success - some operations failed but sync completed
        return ExitCode.PARTIAL_SUCCESS
    else:
        return ExitCode.ERROR


def main() -> int:
    """
    Main entry point for the md2jira CLI.
    
    Parses arguments, sets up logging, and runs the appropriate mode
    (validate or sync).
    
    Returns:
        Exit code (0 for success, non-zero for errors).
    """
    parser = create_parser()
    args = parser.parse_args()
    
    # Handle completions first (doesn't require other args)
    if args.completions:
        from .completions import print_completion
        success = print_completion(args.completions)
        return ExitCode.SUCCESS if success else ExitCode.ERROR
    
    # Handle init wizard (doesn't require other args)
    if args.init:
        from .init import run_init
        console = Console(
            color=not getattr(args, 'no_color', False),
            verbose=getattr(args, 'verbose', False),
        )
        return run_init(console)
    
    # Handle generate (requires epic key)
    if args.generate:
        if not args.epic:
            parser.error("--generate requires --epic/-e to be specified")
        from .generate import run_generate
        console = Console(
            color=not getattr(args, 'no_color', False),
            verbose=getattr(args, 'verbose', False),
            quiet=getattr(args, 'quiet', False),
        )
        return run_generate(args, console)
    
    # Handle list-sessions (doesn't require other args)
    if args.list_sessions:
        from ..application.sync import StateStore
        return list_sessions(StateStore())
    
    # Handle list-backups (requires epic key)
    if args.list_backups:
        from ..application.sync import BackupManager
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
        if not args.markdown or not args.epic:
            parser.error("--watch requires --markdown/-m and --epic/-e to be specified")
        return run_watch(args)
    
    # Handle scheduled sync
    if args.schedule:
        if not args.markdown or not args.epic:
            parser.error("--schedule requires --markdown/-m and --epic/-e to be specified")
        return run_schedule(args)
    
    # Handle webhook server
    if args.webhook:
        if not args.epic:
            parser.error("--webhook requires --epic/-e to be specified")
        return run_webhook(args)
    
    # Handle multi-epic sync
    if args.multi_epic or args.list_epics:
        if not args.markdown:
            parser.error("--multi-epic and --list-epics require --markdown/-m to be specified")
        return run_multi_epic(args)
    
    # Handle link sync
    if args.sync_links or args.analyze_links:
        if not args.markdown or not args.epic:
            parser.error("--sync-links and --analyze-links require --markdown/-m and --epic/-e to be specified")
        return run_sync_links(args)
    
    # Handle resume-session (loads args from session)
    if args.resume_session:
        from ..application.sync import StateStore
        state_store = StateStore()
        state = state_store.load(args.resume_session)
        if not state:
            print(f"Error: Session '{args.resume_session}' not found")
            return ExitCode.FILE_NOT_FOUND
        # Override args from session
        args.markdown = state.markdown_path
        args.epic = state.epic_key
    
    # Handle validate mode (only requires markdown)
    if args.validate:
        if not args.markdown:
            parser.error("--validate requires --markdown/-m to be specified")
        from .logging import setup_logging
        setup_logging(
            level=logging.DEBUG if args.verbose else logging.INFO,
            log_format=getattr(args, "log_format", "text"),
        )
        console = Console(
            color=not args.no_color,
            verbose=args.verbose,
            quiet=args.quiet,
            json_mode=(args.output == "json"),
        )
        return validate_markdown(
            console,
            args.markdown,
            strict=getattr(args, 'strict', False),
        )
    
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
            markdown_path=args.markdown,
            epic_key=args.epic,
        )
    
    # Validate required arguments for other modes
    if not args.markdown or not args.epic:
        parser.error("the following arguments are required: --markdown/-m, --epic/-e")
    
    # Setup logging with optional JSON format
    from .logging import setup_logging
    
    log_level = logging.DEBUG if args.verbose else logging.INFO
    log_format = getattr(args, "log_format", "text")
    log_file = getattr(args, "log_file", None)
    
    setup_logging(
        level=log_level,
        log_format=log_format,
        log_file=log_file,
        static_fields={"service": "md2jira"} if log_format == "json" else None,
    )
    
    # Setup OpenTelemetry if enabled
    telemetry_provider = None
    if getattr(args, 'otel_enable', False):
        from .telemetry import configure_telemetry
        telemetry_provider = configure_telemetry(
            enabled=True,
            endpoint=getattr(args, 'otel_endpoint', None),
            service_name=getattr(args, 'otel_service_name', 'md2jira'),
            console_export=getattr(args, 'otel_console', False),
        )
    
    # Setup Prometheus metrics if enabled
    if getattr(args, 'prometheus', False):
        from .telemetry import configure_prometheus
        prometheus_provider = configure_prometheus(
            enabled=True,
            port=getattr(args, 'prometheus_port', 9090),
            host=getattr(args, 'prometheus_host', '0.0.0.0'),
            service_name=getattr(args, 'otel_service_name', 'md2jira'),
        )
        if telemetry_provider is None:
            telemetry_provider = prometheus_provider
    
    # Setup health check server if enabled
    health_server = None
    if getattr(args, 'health', False):
        from .health import configure_health
        health_server = configure_health(
            enabled=True,
            port=getattr(args, 'health_port', 8080),
            host=getattr(args, 'health_host', '0.0.0.0'),
        )
    
    # Create console
    console = Console(
        color=not args.no_color,
        verbose=args.verbose,
        quiet=args.quiet,
        json_mode=(args.output == "json"),
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

