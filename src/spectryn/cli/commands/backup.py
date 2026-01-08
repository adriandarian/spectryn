"""
Backup command handlers.

This module contains handlers for backup-related commands:
- list_sessions: List resumable sync sessions
- list_backups: List available backups
- run_restore: Restore from a backup
- run_diff: Show diff between backup and current state
- run_rollback: Rollback to most recent backup
- list_rollback_points: List available rollback points
- run_rollback_to_timestamp: Rollback to a specific timestamp
- run_rollback_preview: Preview a timestamp rollback
"""

import logging
from datetime import datetime
from pathlib import Path

from spectryn.cli.exit_codes import ExitCode
from spectryn.cli.output import Console


__all__ = [
    "list_backups",
    "list_rollback_points",
    "list_sessions",
    "run_diff",
    "run_restore",
    "run_rollback",
    "run_rollback_preview",
    "run_rollback_to_timestamp",
]


def list_sessions(state_store) -> int:
    """
    List all resumable sync sessions.

    Args:
        state_store: StateStore instance.

    Returns:
        Exit code.
    """
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
    from spectryn.adapters import ADFFormatter, EnvironmentConfigProvider, JiraAdapter
    from spectryn.application.sync import BackupManager
    from spectryn.cli.logging import setup_logging

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
        f"  Operations: {result.successful_operations} succeeded, "
        f"{result.failed_operations} failed, {result.skipped_operations} skipped"
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
    from spectryn.adapters import ADFFormatter, EnvironmentConfigProvider, JiraAdapter
    from spectryn.application.sync import BackupManager, compare_backup_to_current
    from spectryn.cli.logging import setup_logging

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
            f"Found changes in {result.changed_issues}/{result.total_issues} issues "
            f"({result.total_changes} field changes)"
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
    from spectryn.adapters import ADFFormatter, EnvironmentConfigProvider, JiraAdapter
    from spectryn.application.sync import BackupManager, compare_backup_to_current
    from spectryn.cli.logging import setup_logging

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


def _parse_timestamp(timestamp_str: str) -> datetime:
    """
    Parse a timestamp string into a datetime object.

    Supports ISO 8601 formats:
    - Full: 2024-01-15T10:30:00
    - With timezone: 2024-01-15T10:30:00+00:00
    - Date only: 2024-01-15 (assumes end of day)
    - With space: 2024-01-15 10:30:00

    Args:
        timestamp_str: Timestamp string to parse.

    Returns:
        Parsed datetime object.

    Raises:
        ValueError: If the timestamp format is invalid.
    """
    formats = [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(timestamp_str, fmt)
            # If only date was provided, use end of day
            if fmt == "%Y-%m-%d":
                dt = dt.replace(hour=23, minute=59, second=59)
            return dt
        except ValueError:
            continue

    raise ValueError(
        f"Invalid timestamp format: '{timestamp_str}'. "
        "Use ISO 8601 format (e.g., '2024-01-15T10:30:00' or '2024-01-15')"
    )


def list_rollback_points(args) -> int:
    """
    List available rollback points (successful syncs with timestamps).

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code.
    """
    from spectryn.adapters.sync_history import SQLiteSyncHistoryStore
    from spectryn.cli.logging import setup_logging

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
    tracker_type = getattr(args, "tracker", None)

    console.header("spectra Rollback Points")

    # Initialize sync history store
    history_store = SQLiteSyncHistoryStore()

    # Get rollback points
    rollback_points = history_store.list_rollback_points(
        epic_key=epic_key,
        tracker_type=tracker_type,
        limit=20,
    )

    if not rollback_points:
        console.warning("No rollback points found.")
        if epic_key:
            console.info(f"Epic filter: {epic_key}")
        if tracker_type:
            console.info(f"Tracker filter: {tracker_type}")
        console.info("Rollback points are created after each successful sync operation.")
        return ExitCode.SUCCESS

    # Display rollback points
    console.print()
    console.info(f"Found {len(rollback_points)} rollback points:")
    console.print()

    # Table header
    header = f"{'#':<3} {'Timestamp':<22} {'Epic':<15} {'Tracker':<10} {'Outcome':<10} {'Ops':<8}"
    console.print(header)
    console.print("-" * len(header))

    for idx, entry in enumerate(rollback_points, 1):
        timestamp = entry.completed_at.strftime("%Y-%m-%d %H:%M:%S")
        epic = entry.epic_key[:13] + ".." if len(entry.epic_key) > 15 else entry.epic_key
        tracker = entry.tracker_type[:8] if len(entry.tracker_type) > 10 else entry.tracker_type
        outcome = entry.outcome.value[:8]
        ops = f"{entry.operations_succeeded}/{entry.operations_total}"

        console.print(f"{idx:<3} {timestamp:<22} {epic:<15} {tracker:<10} {outcome:<10} {ops:<8}")

    console.print()
    console.info("To roll back to a specific point:")
    console.detail("  spectra --rollback-to-timestamp <TIMESTAMP> --execute")
    console.info("To preview a rollback:")
    console.detail("  spectra --rollback-preview <TIMESTAMP>")

    history_store.close()
    return ExitCode.SUCCESS


def run_rollback_preview(args) -> int:
    """
    Preview what would be rolled back to a specific timestamp.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code.
    """
    from spectryn.adapters.sync_history import SQLiteSyncHistoryStore
    from spectryn.cli.logging import setup_logging

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

    timestamp_str = getattr(args, "rollback_preview", None)
    epic_key = getattr(args, "epic", None)
    tracker_type = getattr(args, "tracker", None)

    console.header("spectra Rollback Preview")

    # Parse timestamp
    try:
        target_timestamp = _parse_timestamp(timestamp_str)
    except ValueError as e:
        console.error(str(e))
        return ExitCode.CONFIG_ERROR

    console.info(f"Target timestamp: {target_timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    if epic_key:
        console.info(f"Epic filter: {epic_key}")
    if tracker_type:
        console.info(f"Tracker filter: {tracker_type}")

    # Initialize sync history store
    history_store = SQLiteSyncHistoryStore()

    # Create rollback plan
    console.section("Creating Rollback Plan")

    try:
        plan = history_store.create_rollback_plan(
            target_timestamp=target_timestamp,
            epic_key=epic_key,
            tracker_type=tracker_type,
        )
    except Exception as e:
        console.error(f"Failed to create rollback plan: {e}")
        history_store.close()
        return ExitCode.ERROR

    # Display plan details
    console.print()

    if plan.target_entry:
        console.success(f"Target entry found: {plan.target_entry.entry_id}")
        console.detail(
            f"  Completed: {plan.target_entry.completed_at.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        console.detail(f"  Epic: {plan.target_entry.epic_key}")
        console.detail(f"  Tracker: {plan.target_entry.tracker_type}")
        console.detail(f"  Outcome: {plan.target_entry.outcome.value}")
    else:
        console.warning("No sync entry found at or before the target timestamp")

    console.print()
    console.info(f"Changes to roll back: {plan.total_changes}")
    console.info(f"Affected entities: {len(plan.affected_entities)}")
    console.info(f"Affected stories: {len(plan.affected_stories)}")

    # Show warnings
    if plan.warnings:
        console.print()
        console.warning("Warnings:")
        for warning in plan.warnings:
            console.item(warning, "warn")

    # Show change details
    if plan.changes_to_rollback:
        console.print()
        console.section("Changes to Undo")

        # Group by operation type
        creates = [c for c in plan.changes_to_rollback if c.operation_type == "create"]
        updates = [c for c in plan.changes_to_rollback if c.operation_type == "update"]
        deletes = [c for c in plan.changes_to_rollback if c.operation_type == "delete"]

        if creates:
            console.info(f"Create operations ({len(creates)}):")
            for change in creates[:5]:
                console.detail(
                    f"  {change.entity_type}: {change.entity_id} (story: {change.story_id})"
                )
            if len(creates) > 5:
                console.detail(f"  ... and {len(creates) - 5} more")

        if updates:
            console.info(f"Update operations ({len(updates)}):")
            for change in updates[:5]:
                field_info = f" [{change.field_name}]" if change.field_name else ""
                console.detail(f"  {change.entity_type}: {change.entity_id}{field_info}")
            if len(updates) > 5:
                console.detail(f"  ... and {len(updates) - 5} more")

        if deletes:
            console.info(f"Delete operations ({len(deletes)}):")
            for change in deletes[:5]:
                console.detail(f"  {change.entity_type}: {change.entity_id}")
            if len(deletes) > 5:
                console.detail(f"  ... and {len(deletes) - 5} more")

    console.print()
    if plan.can_rollback:
        console.success("Rollback plan is valid")
        console.info("To execute this rollback:")
        console.detail(f"  spectra --rollback-to-timestamp '{timestamp_str}' --execute")
    else:
        console.error("Rollback plan cannot be executed")

    history_store.close()
    return ExitCode.SUCCESS


def run_rollback_to_timestamp(args) -> int:
    """
    Roll back to a specific point in time.

    This command:
    1. Creates a rollback plan for the target timestamp
    2. Marks all changes after that timestamp as rolled back
    3. Optionally updates the tracker (requires --execute)

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code.
    """
    from spectryn.adapters.sync_history import SQLiteSyncHistoryStore, generate_entry_id
    from spectryn.cli.logging import setup_logging
    from spectryn.core.ports.sync_history import SyncHistoryEntry, SyncOutcome

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

    timestamp_str = getattr(args, "rollback_to_timestamp", None)
    epic_key = getattr(args, "epic", None)
    tracker_type = getattr(args, "tracker", None)
    dry_run = not getattr(args, "execute", False)

    console.header("spectra Rollback to Timestamp")

    # Parse timestamp
    try:
        target_timestamp = _parse_timestamp(timestamp_str)
    except ValueError as e:
        console.error(str(e))
        return ExitCode.CONFIG_ERROR

    console.info(f"Target timestamp: {target_timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    if epic_key:
        console.info(f"Epic filter: {epic_key}")
    if tracker_type:
        console.info(f"Tracker filter: {tracker_type}")

    if dry_run:
        console.dry_run_banner()

    # Initialize sync history store
    history_store = SQLiteSyncHistoryStore()

    # Create rollback plan
    console.section("Creating Rollback Plan")

    try:
        plan = history_store.create_rollback_plan(
            target_timestamp=target_timestamp,
            epic_key=epic_key,
            tracker_type=tracker_type,
        )
    except Exception as e:
        console.error(f"Failed to create rollback plan: {e}")
        history_store.close()
        return ExitCode.ERROR

    if not plan.can_rollback:
        console.error("Cannot execute rollback:")
        for warning in plan.warnings:
            console.item(warning, "warn")
        history_store.close()
        return ExitCode.ERROR

    # Display plan summary
    console.print()
    console.info(f"Changes to roll back: {plan.total_changes}")
    console.info(f"Affected entities: {len(plan.affected_entities)}")

    # Show warnings
    if plan.warnings:
        console.print()
        console.warning("Warnings:")
        for warning in plan.warnings:
            console.item(warning, "warn")

    # Confirmation
    if not dry_run and not getattr(args, "no_confirm", False):
        console.print()
        console.warning("This will mark changes as rolled back in the sync history!")
        console.detail(f"  {plan.total_changes} changes will be marked as rolled back")
        console.detail("  Note: This does NOT automatically undo changes in the tracker.")
        console.detail("  You may need to manually restore data or use --restore-backup.")
        if not console.confirm("Proceed with rollback?"):
            console.warning("Cancelled by user")
            history_store.close()
            return ExitCode.CANCELLED

    # Execute rollback plan
    console.section("Executing Rollback")
    start_time = datetime.now()

    rollback_entry_id = generate_entry_id()

    if dry_run:
        console.info(f"[DRY-RUN] Would mark {plan.total_changes} changes as rolled back")
        rolled_back_count = plan.total_changes
    else:
        try:
            rolled_back_count = history_store.execute_rollback_plan(plan, rollback_entry_id)
        except Exception as e:
            console.error(f"Failed to execute rollback: {e}")
            history_store.close()
            return ExitCode.ERROR

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    # Record the rollback operation in history
    if not dry_run:
        rollback_record = SyncHistoryEntry(
            entry_id=rollback_entry_id,
            session_id=f"rollback-{rollback_entry_id}",
            markdown_path="<rollback-operation>",
            epic_key=epic_key or "<all>",
            tracker_type=tracker_type or "<all>",
            outcome=SyncOutcome.SUCCESS,
            started_at=start_time,
            completed_at=end_time,
            duration_seconds=duration,
            operations_total=rolled_back_count,
            operations_succeeded=rolled_back_count,
            dry_run=False,
            metadata={
                "operation": "rollback_to_timestamp",
                "target_timestamp": target_timestamp.isoformat(),
                "changes_rolled_back": rolled_back_count,
            },
        )
        history_store.record(rollback_record)

    # Show results
    console.print()
    if dry_run:
        console.success("Rollback preview completed (dry-run)")
        console.info("Use --execute to perform the actual rollback")
    else:
        console.success("Rollback completed successfully!")
        console.detail(f"  Changes rolled back: {rolled_back_count}")
        console.detail(f"  Rollback entry ID: {rollback_entry_id}")
        console.detail(f"  Duration: {duration:.2f}s")

    console.print()
    console.info("Note: The tracker state has NOT been modified.")
    console.info("To restore the actual tracker data, you may need to:")
    console.detail("  1. Use --restore-backup to restore from a backup")
    console.detail("  2. Manually update issues in the tracker")
    console.detail("  3. Re-sync from the original markdown file")

    history_store.close()
    return ExitCode.SUCCESS
