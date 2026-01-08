"""
SQLite State Store - Database-backed state persistence using SQLite.

SQLite provides better concurrency, atomic operations, and efficient querying
compared to JSON files, while remaining simple to deploy (no external database).

Features:
- ACID transactions for reliable state persistence
- Efficient queries with indexed columns
- Automatic schema migrations
- WAL mode for better concurrent access
- Foreign keys for data integrity
"""

from __future__ import annotations

import contextlib
import json
import logging
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from spectryn.core.ports.state_store import (
    QuerySortField,
    QuerySortOrder,
    StateQuery,
    StateStorePort,
    StateSummary,
    StoreInfo,
)


if TYPE_CHECKING:
    from spectryn.application.sync.state import SyncState

logger = logging.getLogger(__name__)

# Current schema version
SCHEMA_VERSION = 1

# Schema definition
SCHEMA_SQL = """
-- Sync sessions table
CREATE TABLE IF NOT EXISTS sync_sessions (
    session_id TEXT PRIMARY KEY,
    markdown_path TEXT NOT NULL,
    epic_key TEXT NOT NULL,
    phase TEXT NOT NULL,
    config TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    dry_run INTEGER NOT NULL DEFAULT 1,
    matched_stories TEXT DEFAULT '[]',
    unmatched_stories TEXT DEFAULT '[]'
);

-- Operations table (one-to-many with sessions)
CREATE TABLE IF NOT EXISTS operations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    operation_type TEXT NOT NULL,
    issue_key TEXT NOT NULL,
    story_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT,
    timestamp TEXT,
    FOREIGN KEY (session_id) REFERENCES sync_sessions(session_id) ON DELETE CASCADE
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_sessions_epic_key ON sync_sessions(epic_key);
CREATE INDEX IF NOT EXISTS idx_sessions_markdown_path ON sync_sessions(markdown_path);
CREATE INDEX IF NOT EXISTS idx_sessions_phase ON sync_sessions(phase);
CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sync_sessions(updated_at);
CREATE INDEX IF NOT EXISTS idx_sessions_created_at ON sync_sessions(created_at);
CREATE INDEX IF NOT EXISTS idx_operations_session_id ON operations(session_id);
CREATE INDEX IF NOT EXISTS idx_operations_status ON operations(status);

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
"""


class SQLiteStateStore(StateStorePort):
    """
    SQLite-based state store implementation.

    Provides reliable, efficient state persistence using SQLite.
    Supports concurrent access through connection pooling and WAL mode.

    Example:
        # Basic usage
        store = SQLiteStateStore("~/.spectra/state.db")
        store.save(sync_state)

        # Query states
        query = StateQuery(epic_key="PROJ-100", phases=["completed"])
        summaries = store.query(query)

        # Context manager
        with SQLiteStateStore("state.db") as store:
            store.save(state)
    """

    DEFAULT_DB_PATH = Path.home() / ".spectra" / "state.db"

    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        wal_mode: bool = True,
        timeout: float = 30.0,
    ) -> None:
        """
        Initialize the SQLite state store.

        Args:
            db_path: Path to the SQLite database file.
                     Defaults to ~/.spectra/state.db
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
        logger.debug(f"SQLite state store initialized at {self.db_path}")

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
            # Enable WAL mode if requested
            if self._wal_mode:
                self._local.connection.execute("PRAGMA journal_mode = WAL")
        conn: sqlite3.Connection = self._local.connection
        return conn

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        """Context manager for database transactions."""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _init_db(self) -> None:
        """Initialize database schema."""
        with self._transaction() as conn:
            conn.executescript(SCHEMA_SQL)

            # Check and record schema version
            cursor = conn.execute(
                "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
            )
            row = cursor.fetchone()
            current_version = row[0] if row else 0

            if current_version < SCHEMA_VERSION:
                self._migrate(conn, current_version, SCHEMA_VERSION)
                conn.execute(
                    "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, datetime.now().isoformat()),
                )

    def _migrate(
        self,
        conn: sqlite3.Connection,
        from_version: int,
        to_version: int,
    ) -> None:
        """
        Run database migrations.

        Args:
            conn: Database connection.
            from_version: Current schema version.
            to_version: Target schema version.
        """
        logger.info(f"Migrating SQLite schema from v{from_version} to v{to_version}")
        # Add migration logic here as schema evolves
        # Example:
        # if from_version < 2:
        #     conn.execute("ALTER TABLE sync_sessions ADD COLUMN tenant_id TEXT")

    def save(self, state: SyncState) -> None:
        """Save or update a sync state."""

        with self._transaction() as conn:
            # Upsert session
            conn.execute(
                """
                INSERT OR REPLACE INTO sync_sessions
                (session_id, markdown_path, epic_key, phase, config, created_at,
                 updated_at, dry_run, matched_stories, unmatched_stories)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    state.session_id,
                    state.markdown_path,
                    state.epic_key,
                    state.phase,
                    json.dumps(state.config),
                    state.created_at,
                    state.updated_at,
                    1 if state.dry_run else 0,
                    json.dumps(state.matched_stories),
                    json.dumps(state.unmatched_stories),
                ),
            )

            # Delete existing operations and re-insert
            conn.execute(
                "DELETE FROM operations WHERE session_id = ?",
                (state.session_id,),
            )

            for op in state.operations:
                conn.execute(
                    """
                    INSERT INTO operations
                    (session_id, operation_type, issue_key, story_id, status, error, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        state.session_id,
                        op.operation_type,
                        op.issue_key,
                        op.story_id,
                        op.status,
                        op.error,
                        op.timestamp,
                    ),
                )

        logger.debug(f"Saved state for session {state.session_id}")

    def load(self, session_id: str) -> SyncState | None:
        """Load a sync state by session ID."""
        from spectryn.application.sync.state import OperationRecord, SyncState

        conn = self._get_connection()

        # Load session
        cursor = conn.execute(
            "SELECT * FROM sync_sessions WHERE session_id = ?",
            (session_id,),
        )
        row = cursor.fetchone()

        if not row:
            return None

        # Load operations
        op_cursor = conn.execute(
            "SELECT * FROM operations WHERE session_id = ? ORDER BY id",
            (session_id,),
        )
        operations = [
            OperationRecord(
                operation_type=op["operation_type"],
                issue_key=op["issue_key"],
                story_id=op["story_id"],
                status=op["status"],
                error=op["error"],
                timestamp=op["timestamp"],
            )
            for op in op_cursor.fetchall()
        ]

        state = SyncState(
            session_id=row["session_id"],
            markdown_path=row["markdown_path"],
            epic_key=row["epic_key"],
            phase=row["phase"],
            config=json.loads(row["config"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            dry_run=bool(row["dry_run"]),
            matched_stories=json.loads(row["matched_stories"]),
            unmatched_stories=json.loads(row["unmatched_stories"]),
        )
        state.operations = operations

        return state

    def delete(self, session_id: str) -> bool:
        """Delete a sync state."""
        with self._transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM sync_sessions WHERE session_id = ?",
                (session_id,),
            )
            deleted = cursor.rowcount > 0

        if deleted:
            logger.debug(f"Deleted state for session {session_id}")
        return deleted

    def query(self, query: StateQuery) -> list[StateSummary]:
        """Query sync states with filters."""
        conn = self._get_connection()

        # Build query
        sql = """
            SELECT
                s.session_id,
                s.markdown_path,
                s.epic_key,
                s.phase,
                s.dry_run,
                s.created_at,
                s.updated_at,
                COUNT(o.id) as operation_count,
                SUM(CASE WHEN o.status = 'completed' THEN 1 ELSE 0 END) as completed_count,
                SUM(CASE WHEN o.status = 'failed' THEN 1 ELSE 0 END) as failed_count
            FROM sync_sessions s
            LEFT JOIN operations o ON s.session_id = o.session_id
        """

        conditions: list[str] = []
        params: list[Any] = []

        if query.session_id:
            conditions.append("s.session_id = ?")
            params.append(query.session_id)

        if query.markdown_path:
            conditions.append("s.markdown_path = ?")
            params.append(query.markdown_path)

        if query.epic_key:
            conditions.append("s.epic_key = ?")
            params.append(query.epic_key)

        if query.phases:
            placeholders = ",".join("?" for _ in query.phases)
            conditions.append(f"s.phase IN ({placeholders})")
            params.extend(query.phases)

        if query.exclude_phases:
            placeholders = ",".join("?" for _ in query.exclude_phases)
            conditions.append(f"s.phase NOT IN ({placeholders})")
            params.extend(query.exclude_phases)

        if query.dry_run is not None:
            conditions.append("s.dry_run = ?")
            params.append(1 if query.dry_run else 0)

        if query.created_after:
            conditions.append("s.created_at >= ?")
            params.append(query.created_after.isoformat())

        if query.created_before:
            conditions.append("s.created_at <= ?")
            params.append(query.created_before.isoformat())

        if query.updated_after:
            conditions.append("s.updated_at >= ?")
            params.append(query.updated_after.isoformat())

        if query.updated_before:
            conditions.append("s.updated_at <= ?")
            params.append(query.updated_before.isoformat())

        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        sql += " GROUP BY s.session_id"

        # Sort
        sort_column = {
            QuerySortField.CREATED_AT: "s.created_at",
            QuerySortField.UPDATED_AT: "s.updated_at",
            QuerySortField.SESSION_ID: "s.session_id",
            QuerySortField.EPIC_KEY: "s.epic_key",
        }.get(query.sort_by, "s.updated_at")

        sort_order = "DESC" if query.sort_order == QuerySortOrder.DESC else "ASC"
        sql += f" ORDER BY {sort_column} {sort_order}"

        # Pagination
        if query.limit:
            sql += f" LIMIT {query.limit}"
        if query.offset:
            sql += f" OFFSET {query.offset}"

        cursor = conn.execute(sql, params)

        return [
            StateSummary(
                session_id=row["session_id"],
                markdown_path=row["markdown_path"],
                epic_key=row["epic_key"],
                phase=row["phase"],
                dry_run=bool(row["dry_run"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
                operation_count=row["operation_count"] or 0,
                completed_count=row["completed_count"] or 0,
                failed_count=row["failed_count"] or 0,
            )
            for row in cursor.fetchall()
        ]

    def count(self, query: StateQuery | None = None) -> int:
        """Count states matching a query."""
        conn = self._get_connection()

        sql = "SELECT COUNT(*) FROM sync_sessions"
        params: list[Any] = []

        if query:
            conditions: list[str] = []

            if query.session_id:
                conditions.append("session_id = ?")
                params.append(query.session_id)

            if query.markdown_path:
                conditions.append("markdown_path = ?")
                params.append(query.markdown_path)

            if query.epic_key:
                conditions.append("epic_key = ?")
                params.append(query.epic_key)

            if query.phases:
                placeholders = ",".join("?" for _ in query.phases)
                conditions.append(f"phase IN ({placeholders})")
                params.extend(query.phases)

            if query.exclude_phases:
                placeholders = ",".join("?" for _ in query.exclude_phases)
                conditions.append(f"phase NOT IN ({placeholders})")
                params.extend(query.exclude_phases)

            if query.dry_run is not None:
                conditions.append("dry_run = ?")
                params.append(1 if query.dry_run else 0)

            if conditions:
                sql += " WHERE " + " AND ".join(conditions)

        cursor = conn.execute(sql, params)
        result: int = cursor.fetchone()[0]
        return result

    def exists(self, session_id: str) -> bool:
        """Check if a state exists."""
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT 1 FROM sync_sessions WHERE session_id = ? LIMIT 1",
            (session_id,),
        )
        return cursor.fetchone() is not None

    def delete_before(self, before: datetime) -> int:
        """Delete states updated before a given time."""
        with self._transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM sync_sessions WHERE updated_at < ?",
                (before.isoformat(),),
            )
            deleted = cursor.rowcount

        logger.info(f"Deleted {deleted} states updated before {before}")
        return deleted

    def info(self) -> StoreInfo:
        """Get information about the state store."""
        conn = self._get_connection()

        # Get session count
        cursor = conn.execute("SELECT COUNT(*) FROM sync_sessions")
        session_count = cursor.fetchone()[0]

        # Get operation count
        cursor = conn.execute("SELECT COUNT(*) FROM operations")
        operation_count = cursor.fetchone()[0]

        # Get schema version
        cursor = conn.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
        row = cursor.fetchone()
        version = str(row[0]) if row else "0"

        # Get storage size
        storage_size: int | None = None
        with contextlib.suppress(OSError):
            storage_size = self.db_path.stat().st_size

        return StoreInfo(
            backend="sqlite",
            version=version,
            session_count=session_count,
            total_operations=operation_count,
            storage_size_bytes=storage_size,
            connection_info={"path": str(self.db_path), "wal_mode": self._wal_mode},
        )

    def close(self) -> None:
        """Close the database connection."""
        if hasattr(self._local, "connection") and self._local.connection:
            self._local.connection.close()
            self._local.connection = None
            logger.debug("SQLite state store connection closed")

    def vacuum(self) -> None:
        """
        Optimize the database by running VACUUM.

        Reclaims space and defragments the database file.
        """
        conn = self._get_connection()
        conn.execute("VACUUM")
        logger.info("SQLite database vacuumed")

    def checkpoint(self) -> None:
        """
        Force a WAL checkpoint.

        Writes WAL changes to the main database file.
        Only useful if WAL mode is enabled.
        """
        if self._wal_mode:
            conn = self._get_connection()
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            logger.debug("WAL checkpoint completed")
