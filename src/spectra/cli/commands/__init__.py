"""
CLI Commands Package - Command handlers for spectra CLI.

This package contains command handler modules extracted from app.py for
better code organization and maintainability.
"""

from .backup import list_backups, list_sessions, run_diff, run_restore, run_rollback
from .fields import run_generate_field_mapping, run_list_custom_fields, run_list_sprints
from .pull import run_bidirectional_sync, run_pull
from .snapshot import run_clear_snapshot, run_list_snapshots
from .sync import (
    run_attachment_sync,
    run_multi_epic,
    run_multi_tracker_sync,
    run_parallel_files,
    run_sync,
    run_sync_links,
)
from .validation import validate_markdown
from .watch import run_schedule, run_watch, run_webhook

__all__ = [
    # Validation
    "validate_markdown",
    # Backup commands
    "list_sessions",
    "list_backups",
    "run_restore",
    "run_diff",
    "run_rollback",
    # Sync commands
    "run_sync",
    "run_sync_links",
    "run_multi_epic",
    "run_parallel_files",
    "run_multi_tracker_sync",
    "run_attachment_sync",
    # Watch/Schedule commands
    "run_webhook",
    "run_schedule",
    "run_watch",
    # Pull commands
    "run_pull",
    "run_bidirectional_sync",
    # Snapshot commands
    "run_list_snapshots",
    "run_clear_snapshot",
    # Field commands
    "run_list_custom_fields",
    "run_generate_field_mapping",
    "run_list_sprints",
]
