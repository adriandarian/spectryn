"""
Backup command handlers.

This module contains handlers for backup-related commands:
- list_sessions: List resumable sync sessions
- list_backups: List available backups
- run_restore: Restore from a backup
- run_diff: Show diff between backup and current state
- run_rollback: Rollback to most recent backup
"""

import logging
from pathlib import Path

from ..exit_codes import ExitCode
from ..output import Console

__all__ = [
    "list_sessions",
    "list_backups",
    "run_restore",
    "run_diff",
    "run_rollback",
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
    from spectra.adapters import ADFFormatter, EnvironmentConfigProvider, JiraAdapter
    from spectra.application.sync import BackupManager

    from ..logging import setup_logging

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
    from spectra.adapters import ADFFormatter, EnvironmentConfigProvider, JiraAdapter
    from spectra.application.sync import BackupManager, compare_backup_to_current

    from ..logging import setup_logging

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
    from spectra.adapters import ADFFormatter, EnvironmentConfigProvider, JiraAdapter
    from spectra.application.sync import BackupManager, compare_backup_to_current

    from ..logging import setup_logging

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
