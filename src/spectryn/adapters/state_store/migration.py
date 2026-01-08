"""
State Store Migration - Utilities for migrating between state store backends.

Provides tools to:
- Migrate from file-based to SQLite
- Migrate from SQLite to PostgreSQL
- Export/import state data
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from spectryn.core.ports.state_store import (
    MigrationError,
    StateQuery,
    StateStorePort,
)


if TYPE_CHECKING:
    from spectryn.application.sync.state import SyncState

logger = logging.getLogger(__name__)


class StateStoreMigrator:
    """
    Migrate state data between different store backends.

    Example:
        # Migrate from files to SQLite
        from spectryn.adapters.state_store import FileStateStore, SQLiteStateStore

        source = FileStateStore("~/.spectra/state")
        target = SQLiteStateStore("~/.spectra/state.db")

        migrator = StateStoreMigrator(source, target)
        result = migrator.migrate()
        print(f"Migrated {result['migrated']} sessions")

        # Verify migration
        if migrator.verify():
            print("Migration verified successfully")
    """

    def __init__(
        self,
        source: StateStorePort,
        target: StateStorePort,
        *,
        batch_size: int = 100,
    ) -> None:
        """
        Initialize the migrator.

        Args:
            source: Source state store to read from.
            target: Target state store to write to.
            batch_size: Number of sessions to process per batch.
        """
        self.source = source
        self.target = target
        self.batch_size = batch_size
        self._migrated: list[str] = []
        self._failed: list[tuple[str, str]] = []

    def migrate(
        self,
        *,
        overwrite: bool = False,
        query: StateQuery | None = None,
    ) -> dict[str, Any]:
        """
        Migrate all or selected states from source to target.

        Args:
            overwrite: If True, overwrite existing states in target.
            query: Optional query to filter which states to migrate.

        Returns:
            Dict with migration results:
                - migrated: Number of successfully migrated sessions
                - skipped: Number of skipped sessions (already exist)
                - failed: Number of failed migrations
                - errors: List of (session_id, error) tuples

        Raises:
            MigrationError: If migration fails critically.
        """
        self._migrated = []
        self._failed = []
        skipped = 0

        try:
            # Get list of sessions to migrate
            summaries = self.source.query(query or StateQuery())
            total = len(summaries)
            logger.info(f"Starting migration of {total} sessions")

            for i, summary in enumerate(summaries, 1):
                session_id = summary.session_id

                # Check if exists in target
                if not overwrite and self.target.exists(session_id):
                    logger.debug(f"Skipping existing session: {session_id}")
                    skipped += 1
                    continue

                # Load full state from source
                state = self.source.load(session_id)
                if not state:
                    logger.warning(f"Could not load session: {session_id}")
                    self._failed.append((session_id, "Failed to load from source"))
                    continue

                # Save to target
                try:
                    self.target.save(state)
                    self._migrated.append(session_id)
                    logger.debug(f"Migrated session: {session_id}")
                except Exception as e:
                    logger.error(f"Failed to save session {session_id}: {e}")
                    self._failed.append((session_id, str(e)))

                # Progress logging
                if i % 100 == 0 or i == total:
                    logger.info(f"Migration progress: {i}/{total}")

            result = {
                "migrated": len(self._migrated),
                "skipped": skipped,
                "failed": len(self._failed),
                "errors": self._failed,
            }
            logger.info(
                f"Migration complete: {result['migrated']} migrated, "
                f"{result['skipped']} skipped, {result['failed']} failed"
            )
            return result

        except Exception as e:
            raise MigrationError(f"Migration failed: {e}") from e

    def verify(self) -> bool:
        """
        Verify that migrated data matches source.

        Returns:
            True if all migrated sessions match, False otherwise.
        """
        mismatches: list[str] = []

        for session_id in self._migrated:
            source_state = self.source.load(session_id)
            target_state = self.target.load(session_id)

            if not source_state or not target_state:
                logger.error(f"Missing state for session {session_id}")
                mismatches.append(session_id)
                continue

            if not self._states_match(source_state, target_state):
                logger.error(f"State mismatch for session {session_id}")
                mismatches.append(session_id)

        if mismatches:
            logger.error(f"Verification failed: {len(mismatches)} mismatches")
            return False

        logger.info(f"Verification passed: {len(self._migrated)} sessions verified")
        return True

    def _states_match(self, state1: SyncState, state2: SyncState) -> bool:
        """Check if two states are equivalent."""
        # Compare key fields
        if state1.session_id != state2.session_id:
            return False
        if state1.markdown_path != state2.markdown_path:
            return False
        if state1.epic_key != state2.epic_key:
            return False
        if state1.phase != state2.phase:
            return False
        if state1.dry_run != state2.dry_run:
            return False
        if len(state1.operations) != len(state2.operations):
            return False

        # Compare operations
        for op1, op2 in zip(state1.operations, state2.operations, strict=True):
            if op1.operation_type != op2.operation_type:
                return False
            if op1.issue_key != op2.issue_key:
                return False
            if op1.story_id != op2.story_id:
                return False
            if op1.status != op2.status:
                return False

        return True

    def rollback(self) -> int:
        """
        Delete migrated sessions from target.

        Useful if migration verification fails.

        Returns:
            Number of sessions deleted.
        """
        deleted = 0
        for session_id in self._migrated:
            if self.target.delete(session_id):
                deleted += 1

        logger.info(f"Rolled back {deleted} sessions from target")
        return deleted


def export_to_json(
    store: StateStorePort,
    output_path: str | Path,
    *,
    query: StateQuery | None = None,
    pretty: bool = True,
) -> int:
    """
    Export state store contents to a JSON file.

    Args:
        store: State store to export from.
        output_path: Path to output JSON file.
        query: Optional query to filter states.
        pretty: If True, format JSON with indentation.

    Returns:
        Number of sessions exported.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    summaries = store.query(query or StateQuery())
    states: list[dict[str, Any]] = []

    for summary in summaries:
        state = store.load(summary.session_id)
        if state:
            states.append(state.to_dict())

    export_data = {
        "exported_at": datetime.now().isoformat(),
        "source_backend": store.info().backend,
        "session_count": len(states),
        "sessions": states,
    }

    with open(output_path, "w") as f:
        if pretty:
            json.dump(export_data, f, indent=2)
        else:
            json.dump(export_data, f)

    logger.info(f"Exported {len(states)} sessions to {output_path}")
    return len(states)


def import_from_json(
    store: StateStorePort,
    input_path: str | Path,
    *,
    overwrite: bool = False,
) -> dict[str, int]:
    """
    Import states from a JSON export file.

    Args:
        store: State store to import into.
        input_path: Path to JSON file to import.
        overwrite: If True, overwrite existing sessions.

    Returns:
        Dict with import results:
            - imported: Number of sessions imported
            - skipped: Number of sessions skipped
            - failed: Number of sessions that failed

    Raises:
        MigrationError: If import file is invalid.
    """
    from spectryn.application.sync.state import SyncState

    input_path = Path(input_path)

    try:
        with open(input_path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise MigrationError(f"Failed to read import file: {e}") from e

    if "sessions" not in data:
        raise MigrationError("Invalid import file: missing 'sessions' key")

    imported = 0
    skipped = 0
    failed = 0

    for session_data in data["sessions"]:
        try:
            session_id = session_data.get("session_id", "")

            if not overwrite and store.exists(session_id):
                skipped += 1
                continue

            state = SyncState.from_dict(session_data)
            store.save(state)
            imported += 1

        except Exception as e:
            logger.error(f"Failed to import session: {e}")
            failed += 1

    logger.info(f"Imported {imported} sessions, skipped {skipped}, failed {failed}")
    return {"imported": imported, "skipped": skipped, "failed": failed}


def create_store(
    backend: str,
    **kwargs: Any,
) -> StateStorePort:
    """
    Factory function to create a state store by backend name.

    Args:
        backend: Backend type ("file", "sqlite", "postgresql")
        **kwargs: Backend-specific configuration options.

    Returns:
        Configured StateStorePort instance.

    Raises:
        ValueError: If backend is not recognized.

    Example:
        # Create SQLite store
        store = create_store("sqlite", db_path="~/.spectra/state.db")

        # Create PostgreSQL store
        store = create_store(
            "postgresql",
            connection_string="postgresql://user:pass@host/db"
        )
    """
    from spectryn.adapters.state_store import FileStateStore, SQLiteStateStore

    if backend == "file":
        return FileStateStore(state_dir=kwargs.get("state_dir"))

    if backend == "sqlite":
        return SQLiteStateStore(
            db_path=kwargs.get("db_path"),
            wal_mode=kwargs.get("wal_mode", True),
            timeout=kwargs.get("timeout", 30.0),
        )

    if backend in ("postgresql", "postgres"):
        try:
            from spectryn.adapters.state_store import PostgresStateStore
        except ImportError:
            raise ValueError(
                "PostgreSQL backend requires psycopg2. Install with: pip install psycopg2-binary"
            )
        return PostgresStateStore(
            connection_string=kwargs.get("connection_string"),
            pool_timeout=kwargs.get("timeout", 30.0),
            schema=kwargs.get("schema", "public"),
        )

    raise ValueError(f"Unknown state store backend: {backend}")
