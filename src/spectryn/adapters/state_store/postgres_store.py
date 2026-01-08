"""
PostgreSQL State Store - Database-backed state persistence using PostgreSQL.

PostgreSQL provides enterprise-grade features for large-scale deployments:
- Multi-user concurrent access
- Network accessibility for distributed systems
- Advanced query capabilities
- Robust transaction support
- Connection pooling

Requirements:
    pip install psycopg2-binary
    # or for production: pip install psycopg2
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse


try:
    import psycopg2
    from psycopg2 import sql
    from psycopg2.extras import DictCursor, execute_values

    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False
    psycopg2 = None  # type: ignore
    sql = None  # type: ignore
    DictCursor = None  # type: ignore
    execute_values = None  # type: ignore

from spectryn.core.ports.state_store import (
    ConnectionError,
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
    config JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    dry_run BOOLEAN NOT NULL DEFAULT TRUE,
    matched_stories JSONB DEFAULT '[]',
    unmatched_stories JSONB DEFAULT '[]'
);

-- Operations table (one-to-many with sessions)
CREATE TABLE IF NOT EXISTS operations (
    id SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sync_sessions(session_id) ON DELETE CASCADE,
    operation_type TEXT NOT NULL,
    issue_key TEXT NOT NULL,
    story_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT,
    timestamp TIMESTAMPTZ
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
    applied_at TIMESTAMPTZ NOT NULL
);
"""


class PostgresStateStore(StateStorePort):
    """
    PostgreSQL-based state store implementation.

    Provides enterprise-grade state persistence for distributed deployments.
    Supports connection pooling and concurrent access.

    Example:
        # Using connection string
        store = PostgresStateStore("postgresql://user:pass@host/dbname")

        # Using environment variable
        os.environ["SPECTRA_DATABASE_URL"] = "postgresql://..."
        store = PostgresStateStore()

        # Query states
        query = StateQuery(epic_key="PROJ-100", phases=["completed"])
        summaries = store.query(query)

    Note:
        Requires psycopg2 or psycopg2-binary to be installed:
        pip install psycopg2-binary
    """

    def __init__(
        self,
        connection_string: str | None = None,
        *,
        pool_size: int = 5,
        pool_timeout: float = 30.0,
        schema: str = "public",
    ) -> None:
        """
        Initialize the PostgreSQL state store.

        Args:
            connection_string: PostgreSQL connection string.
                Format: postgresql://user:pass@host:port/dbname
                If not provided, uses SPECTRA_DATABASE_URL environment variable.
            pool_size: Connection pool size (not used directly, for future).
            pool_timeout: Connection timeout in seconds.
            schema: Database schema to use.

        Raises:
            ImportError: If psycopg2 is not installed.
            ConnectionError: If unable to connect to database.
        """
        if not HAS_PSYCOPG2:
            raise ImportError(
                "PostgreSQL support requires psycopg2. Install with: pip install psycopg2-binary"
            )

        self._connection_string = connection_string or os.environ.get("SPECTRA_DATABASE_URL") or ""
        if not self._connection_string:
            raise ConnectionError(
                "PostgreSQL connection string required. "
                "Provide connection_string or set SPECTRA_DATABASE_URL"
            )

        self._pool_timeout = pool_timeout
        self._schema = schema
        self._local = threading.local()
        self._lock = threading.Lock()

        # Validate connection and initialize database
        try:
            self._init_db()
            logger.debug("PostgreSQL state store initialized")
        except Exception as e:
            raise ConnectionError(f"Failed to connect to PostgreSQL: {e}") from e

    def _get_connection(self) -> Any:  # psycopg2.connection
        """Get thread-local database connection."""
        if not hasattr(self._local, "connection") or self._local.connection is None:
            self._local.connection = psycopg2.connect(
                self._connection_string,
                connect_timeout=int(self._pool_timeout),
            )
            self._local.connection.autocommit = False
        return self._local.connection

    @contextmanager
    def _transaction(self) -> Iterator[Any]:
        """Context manager for database transactions."""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    @contextmanager
    def _cursor(self) -> Iterator[Any]:
        """Context manager for cursors with dict results."""
        conn = self._get_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        try:
            yield cursor
        finally:
            cursor.close()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with self._transaction() as conn, conn.cursor() as cursor:
            # Set schema search path
            cursor.execute(f"SET search_path TO {self._schema}")

            # Create tables
            cursor.execute(SCHEMA_SQL)

            # Check and record schema version
            cursor.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
            row = cursor.fetchone()
            current_version = row[0] if row else 0

            if current_version < SCHEMA_VERSION:
                self._migrate(cursor, current_version, SCHEMA_VERSION)
                cursor.execute(
                    "INSERT INTO schema_version (version, applied_at) VALUES (%s, %s)"
                    " ON CONFLICT (version) DO NOTHING",
                    (SCHEMA_VERSION, datetime.now()),
                )

    def _migrate(
        self,
        cursor: Any,
        from_version: int,
        to_version: int,
    ) -> None:
        """Run database migrations."""
        logger.info(f"Migrating PostgreSQL schema from v{from_version} to v{to_version}")
        # Add migration logic here as schema evolves

    def save(self, state: SyncState) -> None:
        """Save or update a sync state."""
        with self._transaction() as conn, conn.cursor() as cursor:
            # Parse timestamps
            created_at = datetime.fromisoformat(state.created_at)
            updated_at = datetime.fromisoformat(state.updated_at)

            # Upsert session
            cursor.execute(
                """
                    INSERT INTO sync_sessions
                    (session_id, markdown_path, epic_key, phase, config, created_at,
                     updated_at, dry_run, matched_stories, unmatched_stories)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (session_id) DO UPDATE SET
                        markdown_path = EXCLUDED.markdown_path,
                        epic_key = EXCLUDED.epic_key,
                        phase = EXCLUDED.phase,
                        config = EXCLUDED.config,
                        updated_at = EXCLUDED.updated_at,
                        dry_run = EXCLUDED.dry_run,
                        matched_stories = EXCLUDED.matched_stories,
                        unmatched_stories = EXCLUDED.unmatched_stories
                    """,
                (
                    state.session_id,
                    state.markdown_path,
                    state.epic_key,
                    state.phase,
                    json.dumps(state.config),
                    created_at,
                    updated_at,
                    state.dry_run,
                    json.dumps(state.matched_stories),
                    json.dumps(state.unmatched_stories),
                ),
            )

            # Delete existing operations and re-insert
            cursor.execute(
                "DELETE FROM operations WHERE session_id = %s",
                (state.session_id,),
            )

            if state.operations:
                values = [
                    (
                        state.session_id,
                        op.operation_type,
                        op.issue_key,
                        op.story_id,
                        op.status,
                        op.error,
                        datetime.fromisoformat(op.timestamp) if op.timestamp else None,
                    )
                    for op in state.operations
                ]
                execute_values(
                    cursor,
                    """
                        INSERT INTO operations
                        (session_id, operation_type, issue_key, story_id, status, error, timestamp)
                        VALUES %s
                        """,
                    values,
                )

        logger.debug(f"Saved state for session {state.session_id}")

    def load(self, session_id: str) -> SyncState | None:
        """Load a sync state by session ID."""
        from spectryn.application.sync.state import OperationRecord, SyncState

        with self._cursor() as cursor:
            # Load session
            cursor.execute(
                "SELECT * FROM sync_sessions WHERE session_id = %s",
                (session_id,),
            )
            row = cursor.fetchone()

            if not row:
                return None

            # Load operations
            cursor.execute(
                "SELECT * FROM operations WHERE session_id = %s ORDER BY id",
                (session_id,),
            )
            operations = [
                OperationRecord(
                    operation_type=op["operation_type"],
                    issue_key=op["issue_key"],
                    story_id=op["story_id"],
                    status=op["status"],
                    error=op["error"],
                    timestamp=op["timestamp"].isoformat() if op["timestamp"] else None,
                )
                for op in cursor.fetchall()
            ]

            state = SyncState(
                session_id=row["session_id"],
                markdown_path=row["markdown_path"],
                epic_key=row["epic_key"],
                phase=row["phase"],
                config=row["config"] or {},
                created_at=row["created_at"].isoformat(),
                updated_at=row["updated_at"].isoformat(),
                dry_run=row["dry_run"],
                matched_stories=row["matched_stories"] or [],
                unmatched_stories=row["unmatched_stories"] or [],
            )
            state.operations = operations

            return state

    def delete(self, session_id: str) -> bool:
        """Delete a sync state."""
        with self._transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM sync_sessions WHERE session_id = %s",
                (session_id,),
            )
            deleted: bool = cursor.rowcount > 0

        if deleted:
            logger.debug(f"Deleted state for session {session_id}")
        return deleted

    def query(self, query: StateQuery) -> list[StateSummary]:
        """Query sync states with filters."""
        with self._cursor() as cursor:
            # Build query
            sql_query = """
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
                conditions.append("s.session_id = %s")
                params.append(query.session_id)

            if query.markdown_path:
                conditions.append("s.markdown_path = %s")
                params.append(query.markdown_path)

            if query.epic_key:
                conditions.append("s.epic_key = %s")
                params.append(query.epic_key)

            if query.phases:
                placeholders = ",".join("%s" for _ in query.phases)
                conditions.append(f"s.phase IN ({placeholders})")
                params.extend(query.phases)

            if query.exclude_phases:
                placeholders = ",".join("%s" for _ in query.exclude_phases)
                conditions.append(f"s.phase NOT IN ({placeholders})")
                params.extend(query.exclude_phases)

            if query.dry_run is not None:
                conditions.append("s.dry_run = %s")
                params.append(query.dry_run)

            if query.created_after:
                conditions.append("s.created_at >= %s")
                params.append(query.created_after)

            if query.created_before:
                conditions.append("s.created_at <= %s")
                params.append(query.created_before)

            if query.updated_after:
                conditions.append("s.updated_at >= %s")
                params.append(query.updated_after)

            if query.updated_before:
                conditions.append("s.updated_at <= %s")
                params.append(query.updated_before)

            if conditions:
                sql_query += " WHERE " + " AND ".join(conditions)

            sql_query += " GROUP BY s.session_id"

            # Sort
            sort_column = {
                QuerySortField.CREATED_AT: "s.created_at",
                QuerySortField.UPDATED_AT: "s.updated_at",
                QuerySortField.SESSION_ID: "s.session_id",
                QuerySortField.EPIC_KEY: "s.epic_key",
            }.get(query.sort_by, "s.updated_at")

            sort_order = "DESC" if query.sort_order == QuerySortOrder.DESC else "ASC"
            sql_query += f" ORDER BY {sort_column} {sort_order}"

            # Pagination
            if query.limit:
                sql_query += f" LIMIT {query.limit}"
            if query.offset:
                sql_query += f" OFFSET {query.offset}"

            cursor.execute(sql_query, params)

            return [
                StateSummary(
                    session_id=row["session_id"],
                    markdown_path=row["markdown_path"],
                    epic_key=row["epic_key"],
                    phase=row["phase"],
                    dry_run=row["dry_run"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    operation_count=row["operation_count"] or 0,
                    completed_count=row["completed_count"] or 0,
                    failed_count=row["failed_count"] or 0,
                )
                for row in cursor.fetchall()
            ]

    def count(self, query: StateQuery | None = None) -> int:
        """Count states matching a query."""
        with self._cursor() as cursor:
            sql_query = "SELECT COUNT(*) FROM sync_sessions"
            params: list[Any] = []

            if query:
                conditions: list[str] = []

                if query.session_id:
                    conditions.append("session_id = %s")
                    params.append(query.session_id)

                if query.markdown_path:
                    conditions.append("markdown_path = %s")
                    params.append(query.markdown_path)

                if query.epic_key:
                    conditions.append("epic_key = %s")
                    params.append(query.epic_key)

                if query.phases:
                    placeholders = ",".join("%s" for _ in query.phases)
                    conditions.append(f"phase IN ({placeholders})")
                    params.extend(query.phases)

                if query.exclude_phases:
                    placeholders = ",".join("%s" for _ in query.exclude_phases)
                    conditions.append(f"phase NOT IN ({placeholders})")
                    params.extend(query.exclude_phases)

                if conditions:
                    sql_query += " WHERE " + " AND ".join(conditions)

            cursor.execute(sql_query, params)
            result: int = cursor.fetchone()[0]
            return result

    def exists(self, session_id: str) -> bool:
        """Check if a state exists."""
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM sync_sessions WHERE session_id = %s LIMIT 1",
                (session_id,),
            )
            return cursor.fetchone() is not None

    def delete_before(self, before: datetime) -> int:
        """Delete states updated before a given time."""
        with self._transaction() as conn, conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM sync_sessions WHERE updated_at < %s",
                (before,),
            )
            deleted: int = cursor.rowcount

        logger.info(f"Deleted {deleted} states updated before {before}")
        return deleted

    def info(self) -> StoreInfo:
        """Get information about the state store."""
        with self._cursor() as cursor:
            # Get session count
            cursor.execute("SELECT COUNT(*) FROM sync_sessions")
            session_count = cursor.fetchone()[0]

            # Get operation count
            cursor.execute("SELECT COUNT(*) FROM operations")
            operation_count = cursor.fetchone()[0]

            # Get schema version
            cursor.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
            row = cursor.fetchone()
            version = str(row[0]) if row else "0"

            # Get table size (PostgreSQL specific)
            cursor.execute(
                """
                SELECT pg_total_relation_size('sync_sessions')
                     + pg_total_relation_size('operations')
                """
            )
            storage_size = cursor.fetchone()[0]

        # Sanitize connection info (hide password)
        parsed = urlparse(self._connection_string)
        safe_host = f"{parsed.hostname}:{parsed.port or 5432}" if parsed.hostname else ""

        return StoreInfo(
            backend="postgresql",
            version=version,
            session_count=session_count,
            total_operations=operation_count,
            storage_size_bytes=storage_size,
            connection_info={
                "host": safe_host,
                "database": parsed.path.lstrip("/") if parsed.path else "",
                "schema": self._schema,
            },
        )

    def close(self) -> None:
        """Close the database connection."""
        if hasattr(self._local, "connection") and self._local.connection:
            self._local.connection.close()
            self._local.connection = None
            logger.debug("PostgreSQL state store connection closed")

    def vacuum(self) -> None:
        """
        Run VACUUM ANALYZE on the tables.

        Updates statistics and reclaims space.
        Must be run outside a transaction.
        """
        conn = self._get_connection()
        old_autocommit = conn.autocommit
        try:
            conn.autocommit = True
            with conn.cursor() as cursor:
                cursor.execute("VACUUM ANALYZE sync_sessions")
                cursor.execute("VACUUM ANALYZE operations")
            logger.info("PostgreSQL tables vacuumed and analyzed")
        finally:
            conn.autocommit = old_autocommit
