"""
Sync History Adapters - Implementations of SyncHistoryPort.

Available backends:
- SQLiteSyncHistoryStore: Local SQLite database for audit trail, rollback, analytics
"""

from .sqlite_store import (
    SQLiteSyncHistoryStore,
    generate_change_id,
    generate_entry_id,
)


__all__ = [
    "SQLiteSyncHistoryStore",
    "generate_change_id",
    "generate_entry_id",
]
