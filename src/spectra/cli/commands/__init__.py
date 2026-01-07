"""
CLI Commands Package - Command handlers for spectra CLI.

This package contains command handler modules extracted from app.py for
better code organization and maintainability.
"""

from .backup import (
    list_backups,
    list_rollback_points,
    list_sessions,
    run_diff,
    run_restore,
    run_rollback,
    run_rollback_preview,
    run_rollback_to_timestamp,
)
from .fields import run_generate_field_mapping, run_list_custom_fields, run_list_sprints
from .pull import run_bidirectional_sync, run_pull
from .rest_api import run_rest_api
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
from .watch import run_schedule, run_watch, run_webhook, run_websocket


__all__ = [
    "list_backups",
    "list_rollback_points",
    # Backup commands
    "list_sessions",
    "run_attachment_sync",
    "run_bidirectional_sync",
    "run_clear_snapshot",
    "run_diff",
    "run_generate_field_mapping",
    # Field commands
    "run_list_custom_fields",
    # Snapshot commands
    "run_list_snapshots",
    "run_list_sprints",
    "run_multi_epic",
    "run_multi_tracker_sync",
    "run_parallel_files",
    # Pull commands
    "run_pull",
    # API commands
    "run_rest_api",
    "run_restore",
    "run_rollback",
    "run_rollback_preview",
    "run_rollback_to_timestamp",
    "run_schedule",
    # Sync commands
    "run_sync",
    "run_sync_links",
    "run_watch",
    # Watch/Schedule commands
    "run_webhook",
    "run_websocket",
    # Validation
    "validate_markdown",
]
