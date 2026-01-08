"""
SQLite Sync History Store - Database-backed sync history persistence.

Provides a complete audit trail of all sync operations with:
- Efficient SQLite storage with WAL mode
- Full-text search capabilities
- Analytics queries
- Rollback tracking

Schema:
- sync_history: Main history entries
- sync_changes: Individual change records for rollback
- Indexes for common query patterns
"""

from __future__ import annotations

import contextlib
import json
import logging
import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from spectryn.core.ports.sync_history import (
    ChangeRecord,
    HistoryQuery,
    HistoryStoreInfo,
    RollbackError,
    RollbackPlan,
    SyncHistoryEntry,
    SyncHistoryError,
    SyncHistoryPort,
    SyncOutcome,
    SyncStatistics,
    VelocityMetrics,
)


logger = logging.getLogger(__name__)

# Current schema version
SCHEMA_VERSION = 1

# Schema definition
SCHEMA_SQL = """
-- Sync history entries table
CREATE TABLE IF NOT EXISTS sync_history (
    entry_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    markdown_path TEXT NOT NULL,
    epic_key TEXT NOT NULL,
    tracker_type TEXT NOT NULL,
    outcome TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    duration_seconds REAL NOT NULL,
    operations_total INTEGER DEFAULT 0,
    operations_succeeded INTEGER DEFAULT 0,
    operations_failed INTEGER DEFAULT 0,
    operations_skipped INTEGER DEFAULT 0,
    dry_run INTEGER NOT NULL DEFAULT 0,
    user TEXT,
    config_snapshot TEXT DEFAULT '{}',
    changes_snapshot TEXT DEFAULT '[]',
    error_message TEXT,
    metadata TEXT DEFAULT '{}'
);

-- Change records table for rollback tracking
CREATE TABLE IF NOT EXISTS sync_changes (
    change_id TEXT PRIMARY KEY,
    entry_id TEXT NOT NULL,
    operation_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    story_id TEXT NOT NULL,
    field_name TEXT,
    old_value TEXT,
    new_value TEXT,
    timestamp TEXT NOT NULL,
    rolled_back INTEGER DEFAULT 0,
    rollback_entry_id TEXT,
    FOREIGN KEY (entry_id) REFERENCES sync_history(entry_id) ON DELETE CASCADE
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_history_session_id ON sync_history(session_id);
CREATE INDEX IF NOT EXISTS idx_history_markdown_path ON sync_history(markdown_path);
CREATE INDEX IF NOT EXISTS idx_history_epic_key ON sync_history(epic_key);
CREATE INDEX IF NOT EXISTS idx_history_tracker_type ON sync_history(tracker_type);
CREATE INDEX IF NOT EXISTS idx_history_outcome ON sync_history(outcome);
CREATE INDEX IF NOT EXISTS idx_history_completed_at ON sync_history(completed_at);
CREATE INDEX IF NOT EXISTS idx_history_started_at ON sync_history(started_at);
CREATE INDEX IF NOT EXISTS idx_history_dry_run ON sync_history(dry_run);
CREATE INDEX IF NOT EXISTS idx_history_user ON sync_history(user);

CREATE INDEX IF NOT EXISTS idx_changes_entry_id ON sync_changes(entry_id);
CREATE INDEX IF NOT EXISTS idx_changes_entity_id ON sync_changes(entity_id);
CREATE INDEX IF NOT EXISTS idx_changes_rolled_back ON sync_changes(rolled_back);
CREATE INDEX IF NOT EXISTS idx_changes_operation_type ON sync_changes(operation_type);

-- Schema version tracking
CREATE TABLE IF NOT EXISTS history_schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
"""


class SQLiteSyncHistoryStore(SyncHistoryPort):
    """
    SQLite-based sync history store implementation.

    Provides durable, efficient storage for sync history with full
    analytics capabilities and rollback tracking.

    Features:
    - WAL mode for better concurrency
    - Indexed queries for fast lookups
    - Transaction support
    - Automatic schema migrations
    - Change tracking for rollback

    Example:
        # Basic usage
        store = SQLiteSyncHistoryStore("~/.spectra/history.db")
        store.record(entry)

        # Query history
        entries = store.query(HistoryQuery(epic_key="PROJ-100"))

        # Get statistics
        stats = store.get_statistics()

        # Context manager
        with SQLiteSyncHistoryStore("history.db") as store:
            store.record(entry)
    """

    DEFAULT_DB_PATH = Path.home() / ".spectra" / "sync_history.db"

    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        wal_mode: bool = True,
        timeout: float = 30.0,
    ) -> None:
        """
        Initialize the SQLite sync history store.

        Args:
            db_path: Path to the SQLite database file.
                     Defaults to ~/.spectra/sync_history.db
            wal_mode: Enable WAL mode for better concurrency.
            timeout: Connection timeout in seconds.
        """
        self.db_path = Path(db_path).expanduser() if db_path else self.DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._timeout = timeout
        self._wal_mode = wal_mode
        self._local = threading.local()
        self._lock = threading.Lock()

        # Initialize database
        self._init_db()
        logger.debug(f"SQLite sync history store initialized at {self.db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, "connection") or self._local.connection is None:
            self._local.connection = sqlite3.connect(
                str(self.db_path),
                timeout=self._timeout,
                check_same_thread=False,
            )
            self._local.connection.row_factory = sqlite3.Row
            # Enable foreign keys
            self._local.connection.execute("PRAGMA foreign_keys = ON")
            if self._wal_mode:
                self._local.connection.execute("PRAGMA journal_mode = WAL")
        conn: sqlite3.Connection = self._local.connection
        return conn

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Cursor]:
        """Context manager for database transactions."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()

    def _init_db(self) -> None:
        """Initialize the database schema."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            try:
                # Create tables
                cursor.executescript(SCHEMA_SQL)

                # Check/update schema version
                cursor.execute(
                    "SELECT version FROM history_schema_version ORDER BY version DESC LIMIT 1"
                )
                row = cursor.fetchone()
                current_version = row[0] if row else 0

                if current_version < SCHEMA_VERSION:
                    # Apply migrations here if needed
                    cursor.execute(
                        "INSERT OR REPLACE INTO history_schema_version (version, applied_at) VALUES (?, ?)",
                        (SCHEMA_VERSION, datetime.now().isoformat()),
                    )

                conn.commit()
            finally:
                cursor.close()

    # =========================================================================
    # Core Operations
    # =========================================================================

    def record(self, entry: SyncHistoryEntry) -> None:
        """Record a sync history entry."""
        try:
            with self._transaction() as cursor:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO sync_history (
                        entry_id, session_id, markdown_path, epic_key, tracker_type,
                        outcome, started_at, completed_at, duration_seconds,
                        operations_total, operations_succeeded, operations_failed,
                        operations_skipped, dry_run, user, config_snapshot,
                        changes_snapshot, error_message, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry.entry_id,
                        entry.session_id,
                        entry.markdown_path,
                        entry.epic_key,
                        entry.tracker_type,
                        entry.outcome.value,
                        entry.started_at.isoformat(),
                        entry.completed_at.isoformat(),
                        entry.duration_seconds,
                        entry.operations_total,
                        entry.operations_succeeded,
                        entry.operations_failed,
                        entry.operations_skipped,
                        1 if entry.dry_run else 0,
                        entry.user,
                        json.dumps(entry.config_snapshot),
                        json.dumps(entry.changes_snapshot),
                        entry.error_message,
                        json.dumps(entry.metadata),
                    ),
                )
            logger.debug(f"Recorded sync history entry {entry.entry_id}")
        except sqlite3.Error as e:
            raise SyncHistoryError(f"Failed to record history entry: {e}") from e

    def record_change(self, change: ChangeRecord) -> None:
        """Record an individual change for rollback tracking."""
        try:
            with self._transaction() as cursor:
                cursor.execute(
                    """
                    INSERT INTO sync_changes (
                        change_id, entry_id, operation_type, entity_type,
                        entity_id, story_id, field_name, old_value, new_value,
                        timestamp, rolled_back, rollback_entry_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        change.change_id,
                        change.entry_id,
                        change.operation_type,
                        change.entity_type,
                        change.entity_id,
                        change.story_id,
                        change.field_name,
                        change.old_value,
                        change.new_value,
                        change.timestamp.isoformat(),
                        1 if change.rolled_back else 0,
                        change.rollback_entry_id,
                    ),
                )
        except sqlite3.Error as e:
            raise SyncHistoryError(f"Failed to record change: {e}") from e

    def record_changes(self, changes: list[ChangeRecord]) -> None:
        """Record multiple changes in a batch."""
        if not changes:
            return

        try:
            with self._transaction() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO sync_changes (
                        change_id, entry_id, operation_type, entity_type,
                        entity_id, story_id, field_name, old_value, new_value,
                        timestamp, rolled_back, rollback_entry_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            c.change_id,
                            c.entry_id,
                            c.operation_type,
                            c.entity_type,
                            c.entity_id,
                            c.story_id,
                            c.field_name,
                            c.old_value,
                            c.new_value,
                            c.timestamp.isoformat(),
                            1 if c.rolled_back else 0,
                            c.rollback_entry_id,
                        )
                        for c in changes
                    ],
                )
            logger.debug(f"Recorded {len(changes)} change records")
        except sqlite3.Error as e:
            raise SyncHistoryError(f"Failed to record changes: {e}") from e

    def get_entry(self, entry_id: str) -> SyncHistoryEntry | None:
        """Get a specific history entry."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM sync_history WHERE entry_id = ?",
                (entry_id,),
            )
            row = cursor.fetchone()
            cursor.close()

            if row is None:
                return None

            return self._row_to_entry(row)
        except sqlite3.Error as e:
            raise SyncHistoryError(f"Failed to get entry: {e}") from e

    def query(self, query: HistoryQuery) -> list[SyncHistoryEntry]:
        """Query sync history entries."""
        try:
            sql, params = self._build_query_sql(query)
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            cursor.close()

            return [self._row_to_entry(row) for row in rows]
        except sqlite3.Error as e:
            raise SyncHistoryError(f"Failed to query history: {e}") from e

    def count(self, query: HistoryQuery | None = None) -> int:
        """Count entries matching a query."""
        try:
            if query is None:
                query = HistoryQuery()

            sql, params = self._build_count_sql(query)
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(sql, params)
            result: int = cursor.fetchone()[0]
            cursor.close()
            return result
        except sqlite3.Error as e:
            raise SyncHistoryError(f"Failed to count entries: {e}") from e

    # =========================================================================
    # Change Tracking & Rollback
    # =========================================================================

    def get_changes(self, entry_id: str) -> list[ChangeRecord]:
        """Get all changes for a history entry."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM sync_changes WHERE entry_id = ? ORDER BY timestamp",
                (entry_id,),
            )
            rows = cursor.fetchall()
            cursor.close()

            return [self._row_to_change(row) for row in rows]
        except sqlite3.Error as e:
            raise SyncHistoryError(f"Failed to get changes: {e}") from e

    def get_rollbackable_changes(self, entry_id: str) -> list[ChangeRecord]:
        """Get changes that can be rolled back."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM sync_changes
                WHERE entry_id = ? AND rolled_back = 0
                ORDER BY timestamp DESC
                """,
                (entry_id,),
            )
            rows = cursor.fetchall()
            cursor.close()

            return [self._row_to_change(row) for row in rows]
        except sqlite3.Error as e:
            raise SyncHistoryError(f"Failed to get rollbackable changes: {e}") from e

    def mark_rolled_back(
        self,
        entry_id: str,
        rollback_entry_id: str,
        change_ids: list[str] | None = None,
    ) -> int:
        """Mark changes as rolled back."""
        try:
            with self._transaction() as cursor:
                if change_ids:
                    # Mark specific changes
                    placeholders = ",".join("?" for _ in change_ids)
                    cursor.execute(
                        f"""
                        UPDATE sync_changes
                        SET rolled_back = 1, rollback_entry_id = ?
                        WHERE entry_id = ? AND change_id IN ({placeholders})
                        """,
                        [rollback_entry_id, entry_id, *change_ids],
                    )
                else:
                    # Mark all changes for entry
                    cursor.execute(
                        """
                        UPDATE sync_changes
                        SET rolled_back = 1, rollback_entry_id = ?
                        WHERE entry_id = ? AND rolled_back = 0
                        """,
                        (rollback_entry_id, entry_id),
                    )

                count = cursor.rowcount
                logger.debug(f"Marked {count} changes as rolled back for entry {entry_id}")
                return count
        except sqlite3.Error as e:
            raise RollbackError(f"Failed to mark changes as rolled back: {e}") from e

    # =========================================================================
    # Analytics
    # =========================================================================

    def get_statistics(
        self,
        query: HistoryQuery | None = None,
    ) -> SyncStatistics:
        """Get aggregated statistics."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Build base WHERE clause
            where_clause, params = self._build_where_clause(query or HistoryQuery())

            # Get main stats
            cursor.execute(
                f"""
                SELECT
                    COUNT(*) as total_syncs,
                    SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) as successful_syncs,
                    SUM(CASE WHEN outcome = 'failed' THEN 1 ELSE 0 END) as failed_syncs,
                    SUM(CASE WHEN outcome = 'partial' THEN 1 ELSE 0 END) as partial_syncs,
                    SUM(CASE WHEN outcome = 'dry_run' THEN 1 ELSE 0 END) as dry_run_syncs,
                    SUM(operations_total) as total_operations,
                    SUM(operations_succeeded) as successful_operations,
                    SUM(operations_failed) as failed_operations,
                    AVG(duration_seconds) as avg_duration,
                    SUM(duration_seconds) as total_duration,
                    MIN(completed_at) as first_sync,
                    MAX(completed_at) as last_sync
                FROM sync_history
                {where_clause}
                """,
                params,
            )
            row = cursor.fetchone()

            stats = SyncStatistics(
                total_syncs=row["total_syncs"] or 0,
                successful_syncs=row["successful_syncs"] or 0,
                failed_syncs=row["failed_syncs"] or 0,
                partial_syncs=row["partial_syncs"] or 0,
                dry_run_syncs=row["dry_run_syncs"] or 0,
                total_operations=row["total_operations"] or 0,
                successful_operations=row["successful_operations"] or 0,
                failed_operations=row["failed_operations"] or 0,
                average_duration_seconds=row["avg_duration"] or 0.0,
                total_duration_seconds=row["total_duration"] or 0.0,
                first_sync_at=(
                    datetime.fromisoformat(row["first_sync"]) if row["first_sync"] else None
                ),
                last_sync_at=(
                    datetime.fromisoformat(row["last_sync"]) if row["last_sync"] else None
                ),
            )

            # Get breakdown by tracker
            cursor.execute(
                f"""
                SELECT tracker_type, COUNT(*) as count
                FROM sync_history
                {where_clause}
                GROUP BY tracker_type
                """,
                params,
            )
            stats.syncs_by_tracker = {
                row["tracker_type"]: row["count"] for row in cursor.fetchall()
            }

            # Get breakdown by epic
            cursor.execute(
                f"""
                SELECT epic_key, COUNT(*) as count
                FROM sync_history
                {where_clause}
                GROUP BY epic_key
                ORDER BY count DESC
                LIMIT 20
                """,
                params,
            )
            stats.syncs_by_epic = {row["epic_key"]: row["count"] for row in cursor.fetchall()}

            # Get breakdown by outcome
            cursor.execute(
                f"""
                SELECT outcome, COUNT(*) as count
                FROM sync_history
                {where_clause}
                GROUP BY outcome
                """,
                params,
            )
            stats.syncs_by_outcome = {row["outcome"]: row["count"] for row in cursor.fetchall()}

            cursor.close()
            return stats
        except sqlite3.Error as e:
            raise SyncHistoryError(f"Failed to get statistics: {e}") from e

    def get_velocity(
        self,
        start: datetime,
        end: datetime,
        interval_days: int = 7,
    ) -> list[VelocityMetrics]:
        """Get velocity metrics over time."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            metrics: list[VelocityMetrics] = []
            current = start

            while current < end:
                period_end = min(current + timedelta(days=interval_days), end)

                cursor.execute(
                    """
                    SELECT
                        COUNT(*) as total_syncs,
                        SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) as successful_syncs,
                        SUM(operations_succeeded) as operations_completed,
                        COUNT(DISTINCT epic_key) as epics_touched
                    FROM sync_history
                    WHERE completed_at >= ? AND completed_at < ?
                    AND dry_run = 0
                    """,
                    (current.isoformat(), period_end.isoformat()),
                )
                row = cursor.fetchone()

                # Count unique stories (from changes table)
                cursor.execute(
                    """
                    SELECT COUNT(DISTINCT story_id) as stories_synced
                    FROM sync_changes c
                    JOIN sync_history h ON c.entry_id = h.entry_id
                    WHERE h.completed_at >= ? AND h.completed_at < ?
                    AND h.dry_run = 0
                    """,
                    (current.isoformat(), period_end.isoformat()),
                )
                stories_row = cursor.fetchone()

                total_syncs = row["total_syncs"] or 0
                ops_completed = row["operations_completed"] or 0

                metrics.append(
                    VelocityMetrics(
                        period_start=current,
                        period_end=period_end,
                        total_syncs=total_syncs,
                        successful_syncs=row["successful_syncs"] or 0,
                        operations_completed=ops_completed,
                        stories_synced=stories_row["stories_synced"] or 0,
                        epics_touched=row["epics_touched"] or 0,
                        average_ops_per_sync=ops_completed / total_syncs
                        if total_syncs > 0
                        else 0.0,
                    )
                )

                current = period_end

            cursor.close()
            return metrics
        except sqlite3.Error as e:
            raise SyncHistoryError(f"Failed to get velocity metrics: {e}") from e

    def get_recent_activity(
        self,
        days: int = 7,
        limit: int = 50,
    ) -> list[SyncHistoryEntry]:
        """Get recent sync activity."""
        cutoff = datetime.now() - timedelta(days=days)
        query = HistoryQuery(
            after=cutoff,
            limit=limit,
            order_desc=True,
        )
        return self.query(query)

    # =========================================================================
    # Maintenance
    # =========================================================================

    def delete_before(self, before: datetime) -> int:
        """Delete entries before a timestamp."""
        try:
            with self._transaction() as cursor:
                # Delete changes first (foreign key)
                cursor.execute(
                    """
                    DELETE FROM sync_changes
                    WHERE entry_id IN (
                        SELECT entry_id FROM sync_history
                        WHERE completed_at < ?
                    )
                    """,
                    (before.isoformat(),),
                )
                changes_deleted = cursor.rowcount

                # Delete entries
                cursor.execute(
                    "DELETE FROM sync_history WHERE completed_at < ?",
                    (before.isoformat(),),
                )
                entries_deleted = cursor.rowcount

                logger.info(
                    f"Deleted {entries_deleted} history entries and {changes_deleted} "
                    f"change records before {before.isoformat()}"
                )
                return entries_deleted
        except sqlite3.Error as e:
            raise SyncHistoryError(f"Failed to delete old entries: {e}") from e

    def info(self) -> HistoryStoreInfo:
        """Get information about the history store."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Get entry count
            cursor.execute("SELECT COUNT(*) FROM sync_history")
            entry_count = cursor.fetchone()[0]

            # Get change count
            cursor.execute("SELECT COUNT(*) FROM sync_changes")
            change_count = cursor.fetchone()[0]

            # Get date range
            cursor.execute(
                """
                SELECT MIN(completed_at) as oldest, MAX(completed_at) as newest
                FROM sync_history
                """
            )
            row = cursor.fetchone()
            oldest = datetime.fromisoformat(row["oldest"]) if row["oldest"] else None
            newest = datetime.fromisoformat(row["newest"]) if row["newest"] else None

            # Get schema version
            cursor.execute(
                "SELECT version FROM history_schema_version ORDER BY version DESC LIMIT 1"
            )
            version_row = cursor.fetchone()
            version = str(version_row[0]) if version_row else "0"

            cursor.close()

            # Get file size
            storage_size = self.db_path.stat().st_size if self.db_path.exists() else None

            return HistoryStoreInfo(
                backend="sqlite",
                version=version,
                entry_count=entry_count,
                change_count=change_count,
                storage_size_bytes=storage_size,
                oldest_entry=oldest,
                newest_entry=newest,
            )
        except sqlite3.Error as e:
            raise SyncHistoryError(f"Failed to get store info: {e}") from e

    def close(self) -> None:
        """Close the store and release resources."""
        if hasattr(self._local, "connection") and self._local.connection is not None:
            with contextlib.suppress(sqlite3.Error):
                self._local.connection.close()
            self._local.connection = None
        logger.debug("SQLite sync history store closed")

    def vacuum(self) -> None:
        """Reclaim unused space in the database."""
        try:
            conn = self._get_connection()
            conn.execute("VACUUM")
            logger.debug("Database vacuumed")
        except sqlite3.Error as e:
            raise SyncHistoryError(f"Failed to vacuum database: {e}") from e

    def checkpoint(self) -> None:
        """Force a WAL checkpoint."""
        if self._wal_mode:
            try:
                conn = self._get_connection()
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                logger.debug("WAL checkpoint completed")
            except sqlite3.Error as e:
                raise SyncHistoryError(f"Failed to checkpoint: {e}") from e

    # =========================================================================
    # Timestamp-Based Rollback
    # =========================================================================

    def get_state_at_timestamp(
        self,
        timestamp: datetime,
        epic_key: str | None = None,
        tracker_type: str | None = None,
    ) -> list[ChangeRecord]:
        """Get the cumulative state of changes at a specific point in time."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Build WHERE clause for filters
            conditions = ["c.timestamp <= ?", "c.rolled_back = 0"]
            params: list[Any] = [timestamp.isoformat()]

            if epic_key:
                conditions.append("h.epic_key = ?")
                params.append(epic_key)

            if tracker_type:
                conditions.append("h.tracker_type = ?")
                params.append(tracker_type)

            where_clause = " AND ".join(conditions)

            cursor.execute(
                f"""
                SELECT c.*
                FROM sync_changes c
                JOIN sync_history h ON c.entry_id = h.entry_id
                WHERE {where_clause}
                ORDER BY c.timestamp ASC
                """,
                params,
            )
            rows = cursor.fetchall()
            cursor.close()

            return [self._row_to_change(row) for row in rows]
        except sqlite3.Error as e:
            raise SyncHistoryError(f"Failed to get state at timestamp: {e}") from e

    def get_changes_since_timestamp(
        self,
        timestamp: datetime,
        epic_key: str | None = None,
        tracker_type: str | None = None,
    ) -> list[ChangeRecord]:
        """Get all changes made after a specific timestamp."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Build WHERE clause for filters
            conditions = ["c.timestamp > ?", "c.rolled_back = 0"]
            params: list[Any] = [timestamp.isoformat()]

            if epic_key:
                conditions.append("h.epic_key = ?")
                params.append(epic_key)

            if tracker_type:
                conditions.append("h.tracker_type = ?")
                params.append(tracker_type)

            where_clause = " AND ".join(conditions)

            cursor.execute(
                f"""
                SELECT c.*
                FROM sync_changes c
                JOIN sync_history h ON c.entry_id = h.entry_id
                WHERE {where_clause}
                ORDER BY c.timestamp DESC
                """,
                params,
            )
            rows = cursor.fetchall()
            cursor.close()

            return [self._row_to_change(row) for row in rows]
        except sqlite3.Error as e:
            raise SyncHistoryError(f"Failed to get changes since timestamp: {e}") from e

    def get_entry_at_timestamp(
        self,
        timestamp: datetime,
        epic_key: str | None = None,
        tracker_type: str | None = None,
    ) -> SyncHistoryEntry | None:
        """Get the most recent sync entry before or at a timestamp."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Build WHERE clause for filters
            conditions = ["completed_at <= ?"]
            params: list[Any] = [timestamp.isoformat()]

            if epic_key:
                conditions.append("epic_key = ?")
                params.append(epic_key)

            if tracker_type:
                conditions.append("tracker_type = ?")
                params.append(tracker_type)

            where_clause = " AND ".join(conditions)

            cursor.execute(
                f"""
                SELECT * FROM sync_history
                WHERE {where_clause}
                ORDER BY completed_at DESC
                LIMIT 1
                """,
                params,
            )
            row = cursor.fetchone()
            cursor.close()

            if row is None:
                return None

            return self._row_to_entry(row)
        except sqlite3.Error as e:
            raise SyncHistoryError(f"Failed to get entry at timestamp: {e}") from e

    def list_rollback_points(
        self,
        epic_key: str | None = None,
        tracker_type: str | None = None,
        limit: int = 20,
    ) -> list[SyncHistoryEntry]:
        """List available rollback points (successful syncs)."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Build WHERE clause for filters
            conditions = ["outcome IN ('success', 'partial')", "dry_run = 0"]
            params: list[Any] = []

            if epic_key:
                conditions.append("epic_key = ?")
                params.append(epic_key)

            if tracker_type:
                conditions.append("tracker_type = ?")
                params.append(tracker_type)

            where_clause = " AND ".join(conditions)
            params.append(limit)

            cursor.execute(
                f"""
                SELECT * FROM sync_history
                WHERE {where_clause}
                ORDER BY completed_at DESC
                LIMIT ?
                """,
                params,
            )
            rows = cursor.fetchall()
            cursor.close()

            return [self._row_to_entry(row) for row in rows]
        except sqlite3.Error as e:
            raise SyncHistoryError(f"Failed to list rollback points: {e}") from e

    def create_rollback_plan(
        self,
        target_timestamp: datetime,
        epic_key: str | None = None,
        tracker_type: str | None = None,
    ) -> RollbackPlan:
        """Create a plan for rolling back to a specific timestamp."""
        try:
            # Get the target entry (the state we want to restore to)
            target_entry = self.get_entry_at_timestamp(
                timestamp=target_timestamp,
                epic_key=epic_key,
                tracker_type=tracker_type,
            )

            # Get all changes that need to be rolled back
            changes = self.get_changes_since_timestamp(
                timestamp=target_timestamp,
                epic_key=epic_key,
                tracker_type=tracker_type,
            )

            # Build the plan
            plan = RollbackPlan(
                target_timestamp=target_timestamp,
                target_entry=target_entry,
                changes_to_rollback=changes,
                epic_key=epic_key,
                tracker_type=tracker_type,
            )

            # Add warnings if applicable
            if not target_entry:
                plan.warnings.append(
                    f"No sync entry found before {target_timestamp.isoformat()}. "
                    "Rolling back will undo all changes up to the first sync."
                )

            if not changes:
                plan.warnings.append(
                    "No changes found after the target timestamp. Nothing to roll back."
                )
                plan.can_rollback = False

            # Check for create operations that may not be fully reversible
            create_ops = [c for c in changes if c.operation_type == "create"]
            if create_ops:
                plan.warnings.append(
                    f"{len(create_ops)} create operations found. "
                    "Created entities may need manual deletion in the tracker."
                )

            # Check for delete operations that cannot be undone
            delete_ops = [c for c in changes if c.operation_type == "delete"]
            if delete_ops:
                plan.warnings.append(
                    f"{len(delete_ops)} delete operations found. "
                    "Deleted entities cannot be automatically restored."
                )

            logger.debug(
                f"Created rollback plan: {len(changes)} changes, "
                f"{len(plan.affected_entities)} entities affected"
            )

            return plan
        except sqlite3.Error as e:
            raise RollbackError(f"Failed to create rollback plan: {e}") from e

    def execute_rollback_plan(
        self,
        plan: RollbackPlan,
        rollback_entry_id: str,
    ) -> int:
        """Execute a rollback plan by marking changes as rolled back."""
        if not plan.can_rollback:
            raise RollbackError("Rollback plan cannot be executed: " + "; ".join(plan.warnings))

        if not plan.changes_to_rollback:
            logger.debug("No changes to roll back")
            return 0

        try:
            change_ids = [c.change_id for c in plan.changes_to_rollback]

            with self._transaction() as cursor:
                # Mark all changes in the plan as rolled back
                placeholders = ",".join("?" for _ in change_ids)
                cursor.execute(
                    f"""
                    UPDATE sync_changes
                    SET rolled_back = 1, rollback_entry_id = ?
                    WHERE change_id IN ({placeholders})
                    """,
                    [rollback_entry_id, *change_ids],
                )
                count = cursor.rowcount

            logger.info(
                f"Executed rollback plan: marked {count} changes as rolled back "
                f"(rollback_entry_id={rollback_entry_id})"
            )
            return count
        except sqlite3.Error as e:
            raise RollbackError(f"Failed to execute rollback plan: {e}") from e

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _row_to_entry(self, row: sqlite3.Row) -> SyncHistoryEntry:
        """Convert a database row to a SyncHistoryEntry."""
        return SyncHistoryEntry(
            entry_id=row["entry_id"],
            session_id=row["session_id"],
            markdown_path=row["markdown_path"],
            epic_key=row["epic_key"],
            tracker_type=row["tracker_type"],
            outcome=SyncOutcome(row["outcome"]),
            started_at=datetime.fromisoformat(row["started_at"]),
            completed_at=datetime.fromisoformat(row["completed_at"]),
            duration_seconds=row["duration_seconds"],
            operations_total=row["operations_total"],
            operations_succeeded=row["operations_succeeded"],
            operations_failed=row["operations_failed"],
            operations_skipped=row["operations_skipped"],
            dry_run=bool(row["dry_run"]),
            user=row["user"],
            config_snapshot=json.loads(row["config_snapshot"]),
            changes_snapshot=json.loads(row["changes_snapshot"]),
            error_message=row["error_message"],
            metadata=json.loads(row["metadata"]),
        )

    def _row_to_change(self, row: sqlite3.Row) -> ChangeRecord:
        """Convert a database row to a ChangeRecord."""
        return ChangeRecord(
            change_id=row["change_id"],
            entry_id=row["entry_id"],
            operation_type=row["operation_type"],
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            story_id=row["story_id"],
            field_name=row["field_name"],
            old_value=row["old_value"],
            new_value=row["new_value"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            rolled_back=bool(row["rolled_back"]),
            rollback_entry_id=row["rollback_entry_id"],
        )

    def _build_where_clause(self, query: HistoryQuery) -> tuple[str, list[Any]]:
        """Build WHERE clause from query parameters."""
        conditions: list[str] = []
        params: list[Any] = []

        if query.entry_id:
            conditions.append("entry_id = ?")
            params.append(query.entry_id)

        if query.session_id:
            conditions.append("session_id = ?")
            params.append(query.session_id)

        if query.markdown_path:
            conditions.append("markdown_path = ?")
            params.append(query.markdown_path)

        if query.epic_key:
            conditions.append("epic_key = ?")
            params.append(query.epic_key)

        if query.tracker_type:
            conditions.append("tracker_type = ?")
            params.append(query.tracker_type)

        if query.outcomes:
            placeholders = ",".join("?" for _ in query.outcomes)
            conditions.append(f"outcome IN ({placeholders})")
            params.extend(query.outcomes)

        if query.dry_run is not None:
            conditions.append("dry_run = ?")
            params.append(1 if query.dry_run else 0)

        if query.after:
            conditions.append("completed_at >= ?")
            params.append(query.after.isoformat())

        if query.before:
            conditions.append("completed_at < ?")
            params.append(query.before.isoformat())

        if query.user:
            conditions.append("user = ?")
            params.append(query.user)

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        return where_clause, params

    def _build_query_sql(self, query: HistoryQuery) -> tuple[str, list[Any]]:
        """Build full SELECT SQL from query parameters."""
        where_clause, params = self._build_where_clause(query)

        order_dir = "DESC" if query.order_desc else "ASC"
        sql = f"""
            SELECT * FROM sync_history
            {where_clause}
            ORDER BY completed_at {order_dir}
        """

        if query.limit is not None:
            sql += " LIMIT ?"
            params.append(query.limit)

        if query.offset > 0:
            sql += " OFFSET ?"
            params.append(query.offset)

        return sql, params

    def _build_count_sql(self, query: HistoryQuery) -> tuple[str, list[Any]]:
        """Build COUNT SQL from query parameters."""
        where_clause, params = self._build_where_clause(query)
        sql = f"SELECT COUNT(*) FROM sync_history {where_clause}"
        return sql, params


def generate_entry_id() -> str:
    """Generate a unique entry ID."""
    return f"hist-{uuid.uuid4().hex[:12]}"


def generate_change_id() -> str:
    """Generate a unique change ID."""
    return f"chg-{uuid.uuid4().hex[:12]}"
