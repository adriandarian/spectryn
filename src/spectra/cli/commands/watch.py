"""
Watch and schedule command handlers.

This module contains handlers for watch and schedule-related commands:
- run_watch: Watch mode (auto-sync on file changes)
- run_schedule: Scheduled sync mode
- run_webhook: Webhook server mode
"""

import logging
from pathlib import Path

from spectra.adapters import (
    ADFFormatter,
    EnvironmentConfigProvider,
    JiraAdapter,
    MarkdownParser,
)

from ..exit_codes import ExitCode
from ..logging import setup_logging
from ..output import Console

__all__ = [
    "run_watch",
    "run_schedule",
    "run_webhook",
]


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
    from spectra.application import SyncOrchestrator, WatchDisplay, WatchOrchestrator

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


def run_schedule(args) -> int:
    """
    Run scheduled sync mode.

    Runs sync operations on a configurable schedule.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code.
    """
    from spectra.application import ScheduleDisplay, ScheduleRunner, SyncOrchestrator

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
    schedule = getattr(args, "schedule", "*/5 * * * *")  # Default: every 5 minutes
    run_now = getattr(args, "run_now", False)
    max_runs = getattr(args, "max_runs", None)
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

    # Create schedule runner
    runner = ScheduleRunner(
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
    from spectra.adapters.formatters import MarkdownWriter
    from spectra.application import WebhookDisplay, WebhookServer
    from spectra.application.sync import ReverseSyncOrchestrator

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
        dry_run=dry_run,
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

    # Create markdown writer
    writer = MarkdownWriter()

    # Create reverse sync orchestrator
    reverse_sync = ReverseSyncOrchestrator(
        tracker=tracker,
        writer=writer,
        dry_run=dry_run,
    )

    # Create display handler
    display = WebhookDisplay(
        color=not getattr(args, "no_color", False),
        quiet=getattr(args, "quiet", False),
    )

    # Create webhook server
    server = WebhookServer(
        orchestrator=reverse_sync,
        epic_key=epic_key,
        output_path=output_path,
        host=host,
        port=port,
        secret=secret,
        on_event_received=display.show_event_received,
        on_sync_triggered=display.show_sync_triggered,
        on_sync_completed=display.show_sync_completed,
    )

    # Show start message
    display.show_start(host, port, epic_key, output_path)

    try:
        # Run webhook server (blocks until Ctrl+C)
        server.start()
    except KeyboardInterrupt:
        pass
    finally:
        display.show_stop(server.stats)

    return ExitCode.SUCCESS
