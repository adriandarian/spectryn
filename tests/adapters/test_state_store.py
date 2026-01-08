"""
Tests for state store adapters.

Tests the StateStorePort implementations for:
- FileStateStore (JSON files)
- SQLiteStateStore (SQLite database)
- PostgresStateStore (PostgreSQL - skipped without psycopg2)
"""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from spectryn.adapters.state_store import (
    FileStateStore,
    SQLiteStateStore,
    StateStoreMigrator,
    create_store,
    export_to_json,
    import_from_json,
)
from spectryn.application.sync.state import OperationRecord, SyncPhase, SyncState
from spectryn.core.ports.state_store import (
    QuerySortField,
    QuerySortOrder,
    StateQuery,
    StateSummary,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_state() -> SyncState:
    """Create a sample sync state for testing."""
    state = SyncState(
        session_id="test-session-123",
        markdown_path="/path/to/file.md",
        epic_key="PROJ-100",
        phase=SyncPhase.ANALYZING.value,
        dry_run=False,
    )
    state.add_operation("update_description", "PROJ-101", "US-1")
    state.add_operation("create_subtask", "PROJ-101", "US-1")
    state.operations[0].mark_completed()
    return state


@pytest.fixture
def multiple_states() -> list[SyncState]:
    """Create multiple states for testing queries."""
    states = []

    # Create states with different epics and phases
    for i in range(5):
        state = SyncState(
            session_id=f"session-{i}",
            markdown_path=f"/path/file{i}.md",
            epic_key=f"PROJ-{100 + i}",
            phase=SyncPhase.COMPLETED.value if i % 2 == 0 else SyncPhase.ANALYZING.value,
            dry_run=i % 3 == 0,
        )
        # Add some operations
        for j in range(i + 1):
            op = state.add_operation("update", f"PROJ-{100 + i}-{j}", f"US-{j}")
            if j % 2 == 0:
                op.mark_completed()
            elif j % 3 == 0:
                op.mark_failed("Test error")
        states.append(state)

    return states


@pytest.fixture
def file_store(tmp_path: Path) -> FileStateStore:
    """Create a temporary file state store."""
    return FileStateStore(state_dir=tmp_path)


@pytest.fixture
def sqlite_store(tmp_path: Path) -> SQLiteStateStore:
    """Create a temporary SQLite state store."""
    db_path = tmp_path / "test_state.db"
    return SQLiteStateStore(db_path=db_path)


# =============================================================================
# FileStateStore Tests
# =============================================================================


class TestFileStateStore:
    """Tests for FileStateStore."""

    def test_save_and_load(
        self,
        file_store: FileStateStore,
        sample_state: SyncState,
    ) -> None:
        """Test saving and loading a state."""
        file_store.save(sample_state)
        loaded = file_store.load(sample_state.session_id)

        assert loaded is not None
        assert loaded.session_id == sample_state.session_id
        assert loaded.markdown_path == sample_state.markdown_path
        assert loaded.epic_key == sample_state.epic_key
        assert loaded.phase == sample_state.phase
        assert len(loaded.operations) == len(sample_state.operations)

    def test_load_nonexistent(self, file_store: FileStateStore) -> None:
        """Test loading a non-existent state returns None."""
        loaded = file_store.load("nonexistent")
        assert loaded is None

    def test_delete(
        self,
        file_store: FileStateStore,
        sample_state: SyncState,
    ) -> None:
        """Test deleting a state."""
        file_store.save(sample_state)
        assert file_store.exists(sample_state.session_id)

        deleted = file_store.delete(sample_state.session_id)
        assert deleted is True
        assert not file_store.exists(sample_state.session_id)

        # Delete again returns False
        deleted = file_store.delete(sample_state.session_id)
        assert deleted is False

    def test_exists(
        self,
        file_store: FileStateStore,
        sample_state: SyncState,
    ) -> None:
        """Test checking if state exists."""
        assert not file_store.exists(sample_state.session_id)
        file_store.save(sample_state)
        assert file_store.exists(sample_state.session_id)

    def test_query_all(
        self,
        file_store: FileStateStore,
        multiple_states: list[SyncState],
    ) -> None:
        """Test querying all states."""
        for state in multiple_states:
            file_store.save(state)

        summaries = file_store.query(StateQuery())
        assert len(summaries) == len(multiple_states)

    def test_query_by_epic(
        self,
        file_store: FileStateStore,
        multiple_states: list[SyncState],
    ) -> None:
        """Test filtering by epic key."""
        for state in multiple_states:
            file_store.save(state)

        query = StateQuery(epic_key="PROJ-102")
        summaries = file_store.query(query)
        assert len(summaries) == 1
        assert summaries[0].epic_key == "PROJ-102"

    def test_query_by_phase(
        self,
        file_store: FileStateStore,
        multiple_states: list[SyncState],
    ) -> None:
        """Test filtering by phase."""
        for state in multiple_states:
            file_store.save(state)

        query = StateQuery(phases=["completed"])
        summaries = file_store.query(query)
        # Sessions 0, 2, 4 are completed
        assert len(summaries) == 3

    def test_query_exclude_phases(
        self,
        file_store: FileStateStore,
        multiple_states: list[SyncState],
    ) -> None:
        """Test excluding phases."""
        for state in multiple_states:
            file_store.save(state)

        query = StateQuery(exclude_phases=["completed", "failed"])
        summaries = file_store.query(query)
        # Sessions 1, 3 are analyzing
        assert len(summaries) == 2

    def test_query_pagination(
        self,
        file_store: FileStateStore,
        multiple_states: list[SyncState],
    ) -> None:
        """Test pagination with limit and offset."""
        for state in multiple_states:
            file_store.save(state)

        query = StateQuery(limit=2, offset=1)
        summaries = file_store.query(query)
        assert len(summaries) == 2

    def test_count(
        self,
        file_store: FileStateStore,
        multiple_states: list[SyncState],
    ) -> None:
        """Test counting states."""
        for state in multiple_states:
            file_store.save(state)

        assert file_store.count() == len(multiple_states)
        assert file_store.count(StateQuery(phases=["completed"])) == 3

    def test_info(
        self,
        file_store: FileStateStore,
        sample_state: SyncState,
    ) -> None:
        """Test getting store info."""
        file_store.save(sample_state)

        info = file_store.info()
        assert info.backend == "file"
        assert info.session_count == 1
        assert info.total_operations == 2

    def test_find_resumable(
        self,
        file_store: FileStateStore,
        multiple_states: list[SyncState],
    ) -> None:
        """Test finding resumable sessions."""
        for state in multiple_states:
            file_store.save(state)

        resumable = file_store.find_resumable()
        # Sessions 1, 3 are in analyzing phase
        assert len(resumable) == 2

    def test_context_manager(
        self,
        tmp_path: Path,
        sample_state: SyncState,
    ) -> None:
        """Test using store as context manager."""
        with FileStateStore(state_dir=tmp_path) as store:
            store.save(sample_state)
            assert store.exists(sample_state.session_id)


# =============================================================================
# SQLiteStateStore Tests
# =============================================================================


class TestSQLiteStateStore:
    """Tests for SQLiteStateStore."""

    def test_save_and_load(
        self,
        sqlite_store: SQLiteStateStore,
        sample_state: SyncState,
    ) -> None:
        """Test saving and loading a state."""
        sqlite_store.save(sample_state)
        loaded = sqlite_store.load(sample_state.session_id)

        assert loaded is not None
        assert loaded.session_id == sample_state.session_id
        assert loaded.markdown_path == sample_state.markdown_path
        assert loaded.epic_key == sample_state.epic_key
        assert loaded.phase == sample_state.phase
        assert len(loaded.operations) == len(sample_state.operations)
        assert loaded.operations[0].is_completed

    def test_update_existing(
        self,
        sqlite_store: SQLiteStateStore,
        sample_state: SyncState,
    ) -> None:
        """Test updating an existing state."""
        sqlite_store.save(sample_state)

        # Update the state
        sample_state.set_phase(SyncPhase.COMPLETED)
        sample_state.add_operation("comment", "PROJ-101", "US-1")
        sqlite_store.save(sample_state)

        loaded = sqlite_store.load(sample_state.session_id)
        assert loaded is not None
        assert loaded.phase == SyncPhase.COMPLETED.value
        assert len(loaded.operations) == 3

    def test_load_nonexistent(self, sqlite_store: SQLiteStateStore) -> None:
        """Test loading a non-existent state returns None."""
        loaded = sqlite_store.load("nonexistent")
        assert loaded is None

    def test_delete(
        self,
        sqlite_store: SQLiteStateStore,
        sample_state: SyncState,
    ) -> None:
        """Test deleting a state."""
        sqlite_store.save(sample_state)
        assert sqlite_store.exists(sample_state.session_id)

        deleted = sqlite_store.delete(sample_state.session_id)
        assert deleted is True
        assert not sqlite_store.exists(sample_state.session_id)

    def test_delete_cascades_operations(
        self,
        sqlite_store: SQLiteStateStore,
        sample_state: SyncState,
    ) -> None:
        """Test that deleting a state cascades to operations."""
        sqlite_store.save(sample_state)

        # Verify operations exist by loading
        loaded = sqlite_store.load(sample_state.session_id)
        assert loaded is not None
        assert len(loaded.operations) == 2

        # Delete and verify operations are also gone
        sqlite_store.delete(sample_state.session_id)
        loaded = sqlite_store.load(sample_state.session_id)
        assert loaded is None

    def test_query_all(
        self,
        sqlite_store: SQLiteStateStore,
        multiple_states: list[SyncState],
    ) -> None:
        """Test querying all states."""
        for state in multiple_states:
            sqlite_store.save(state)

        summaries = sqlite_store.query(StateQuery())
        assert len(summaries) == len(multiple_states)

    def test_query_by_epic(
        self,
        sqlite_store: SQLiteStateStore,
        multiple_states: list[SyncState],
    ) -> None:
        """Test filtering by epic key."""
        for state in multiple_states:
            sqlite_store.save(state)

        query = StateQuery(epic_key="PROJ-102")
        summaries = sqlite_store.query(query)
        assert len(summaries) == 1
        assert summaries[0].epic_key == "PROJ-102"

    def test_query_by_phase(
        self,
        sqlite_store: SQLiteStateStore,
        multiple_states: list[SyncState],
    ) -> None:
        """Test filtering by phase."""
        for state in multiple_states:
            sqlite_store.save(state)

        query = StateQuery(phases=["completed"])
        summaries = sqlite_store.query(query)
        assert len(summaries) == 3

    def test_query_exclude_phases(
        self,
        sqlite_store: SQLiteStateStore,
        multiple_states: list[SyncState],
    ) -> None:
        """Test excluding phases."""
        for state in multiple_states:
            sqlite_store.save(state)

        query = StateQuery(exclude_phases=["completed", "failed"])
        summaries = sqlite_store.query(query)
        assert len(summaries) == 2

    def test_query_by_dry_run(
        self,
        sqlite_store: SQLiteStateStore,
        multiple_states: list[SyncState],
    ) -> None:
        """Test filtering by dry_run flag."""
        for state in multiple_states:
            sqlite_store.save(state)

        query = StateQuery(dry_run=True)
        summaries = sqlite_store.query(query)
        # Sessions 0, 3 have dry_run=True
        assert len(summaries) == 2

    def test_query_sorting(
        self,
        sqlite_store: SQLiteStateStore,
        multiple_states: list[SyncState],
    ) -> None:
        """Test sorting query results."""
        for state in multiple_states:
            sqlite_store.save(state)

        # Sort by session_id ascending
        query = StateQuery(
            sort_by=QuerySortField.SESSION_ID,
            sort_order=QuerySortOrder.ASC,
        )
        summaries = sqlite_store.query(query)
        session_ids = [s.session_id for s in summaries]
        assert session_ids == sorted(session_ids)

    def test_query_pagination(
        self,
        sqlite_store: SQLiteStateStore,
        multiple_states: list[SyncState],
    ) -> None:
        """Test pagination with limit and offset."""
        for state in multiple_states:
            sqlite_store.save(state)

        query = StateQuery(
            sort_by=QuerySortField.SESSION_ID,
            sort_order=QuerySortOrder.ASC,
            limit=2,
            offset=1,
        )
        summaries = sqlite_store.query(query)
        assert len(summaries) == 2
        assert summaries[0].session_id == "session-1"
        assert summaries[1].session_id == "session-2"

    def test_query_operation_counts(
        self,
        sqlite_store: SQLiteStateStore,
        multiple_states: list[SyncState],
    ) -> None:
        """Test that query returns correct operation counts."""
        for state in multiple_states:
            sqlite_store.save(state)

        query = StateQuery(session_id="session-4")
        summaries = sqlite_store.query(query)
        assert len(summaries) == 1

        # session-4 has 5 operations (i=4, so j goes 0-4)
        summary = summaries[0]
        assert summary.operation_count == 5
        # j=0,2,4 are completed (3 ops)
        assert summary.completed_count == 3
        # j=3 is failed
        assert summary.failed_count == 1

    def test_count(
        self,
        sqlite_store: SQLiteStateStore,
        multiple_states: list[SyncState],
    ) -> None:
        """Test counting states."""
        for state in multiple_states:
            sqlite_store.save(state)

        assert sqlite_store.count() == len(multiple_states)
        assert sqlite_store.count(StateQuery(phases=["completed"])) == 3
        assert sqlite_store.count(StateQuery(dry_run=True)) == 2

    def test_exists(
        self,
        sqlite_store: SQLiteStateStore,
        sample_state: SyncState,
    ) -> None:
        """Test checking if state exists."""
        assert not sqlite_store.exists(sample_state.session_id)
        sqlite_store.save(sample_state)
        assert sqlite_store.exists(sample_state.session_id)

    def test_delete_before(
        self,
        sqlite_store: SQLiteStateStore,
        sample_state: SyncState,
    ) -> None:
        """Test deleting states by time."""
        sqlite_store.save(sample_state)

        # Delete states before future date - should delete all
        future = datetime.now() + timedelta(days=1)
        deleted = sqlite_store.delete_before(future)
        assert deleted == 1
        assert sqlite_store.count() == 0

    def test_info(
        self,
        sqlite_store: SQLiteStateStore,
        sample_state: SyncState,
    ) -> None:
        """Test getting store info."""
        sqlite_store.save(sample_state)

        info = sqlite_store.info()
        assert info.backend == "sqlite"
        assert info.session_count == 1
        assert info.total_operations == 2
        assert info.storage_size_bytes is not None
        assert info.storage_size_bytes > 0

    def test_find_resumable(
        self,
        sqlite_store: SQLiteStateStore,
        multiple_states: list[SyncState],
    ) -> None:
        """Test finding resumable sessions."""
        for state in multiple_states:
            sqlite_store.save(state)

        resumable = sqlite_store.find_resumable()
        assert len(resumable) == 2

    def test_find_latest_resumable(
        self,
        sqlite_store: SQLiteStateStore,
    ) -> None:
        """Test finding latest resumable session."""
        state1 = SyncState(
            session_id="session-old",
            markdown_path="/path/file.md",
            epic_key="PROJ-100",
            phase=SyncPhase.ANALYZING.value,
        )
        state2 = SyncState(
            session_id="session-new",
            markdown_path="/path/file.md",
            epic_key="PROJ-100",
            phase=SyncPhase.ANALYZING.value,
        )

        # Explicitly set different timestamps to avoid timing issues on Windows
        state1.updated_at = "2024-01-01T10:00:00"
        state2.updated_at = "2024-01-01T11:00:00"

        sqlite_store.save(state1)
        sqlite_store.save(state2)

        latest = sqlite_store.find_latest_resumable("/path/file.md", "PROJ-100")
        assert latest is not None
        assert latest.session_id == "session-new"

    def test_vacuum(
        self,
        sqlite_store: SQLiteStateStore,
        sample_state: SyncState,
    ) -> None:
        """Test vacuum operation."""
        sqlite_store.save(sample_state)
        sqlite_store.delete(sample_state.session_id)

        # Should not raise
        sqlite_store.vacuum()

    def test_checkpoint(
        self,
        sqlite_store: SQLiteStateStore,
        sample_state: SyncState,
    ) -> None:
        """Test WAL checkpoint operation."""
        sqlite_store.save(sample_state)

        # Should not raise
        sqlite_store.checkpoint()

    def test_context_manager(
        self,
        tmp_path: Path,
        sample_state: SyncState,
    ) -> None:
        """Test using store as context manager."""
        db_path = tmp_path / "context_test.db"
        with SQLiteStateStore(db_path=db_path) as store:
            store.save(sample_state)
            assert store.exists(sample_state.session_id)


# =============================================================================
# Migration Tests
# =============================================================================


class TestStateStoreMigrator:
    """Tests for StateStoreMigrator."""

    def test_migrate_file_to_sqlite(
        self,
        tmp_path: Path,
        multiple_states: list[SyncState],
    ) -> None:
        """Test migrating from file store to SQLite."""
        # Setup source store with data
        source = FileStateStore(state_dir=tmp_path / "source")
        for state in multiple_states:
            source.save(state)

        # Setup target store
        target = SQLiteStateStore(db_path=tmp_path / "target.db")

        # Migrate
        migrator = StateStoreMigrator(source, target)
        result = migrator.migrate()

        assert result["migrated"] == len(multiple_states)
        assert result["failed"] == 0
        assert result["skipped"] == 0

        # Verify all states are in target
        assert target.count() == len(multiple_states)

    def test_migrate_with_verify(
        self,
        tmp_path: Path,
        multiple_states: list[SyncState],
    ) -> None:
        """Test migration verification."""
        source = FileStateStore(state_dir=tmp_path / "source")
        for state in multiple_states:
            source.save(state)

        target = SQLiteStateStore(db_path=tmp_path / "target.db")

        migrator = StateStoreMigrator(source, target)
        migrator.migrate()

        assert migrator.verify() is True

    def test_migrate_skip_existing(
        self,
        tmp_path: Path,
        sample_state: SyncState,
    ) -> None:
        """Test skipping existing states during migration."""
        source = FileStateStore(state_dir=tmp_path / "source")
        source.save(sample_state)

        target = SQLiteStateStore(db_path=tmp_path / "target.db")
        target.save(sample_state)  # Pre-populate target

        migrator = StateStoreMigrator(source, target)
        result = migrator.migrate(overwrite=False)

        assert result["migrated"] == 0
        assert result["skipped"] == 1

    def test_migrate_with_overwrite(
        self,
        tmp_path: Path,
        sample_state: SyncState,
    ) -> None:
        """Test overwriting existing states during migration."""
        source = FileStateStore(state_dir=tmp_path / "source")
        source.save(sample_state)

        # Create different state with same ID in target
        target = SQLiteStateStore(db_path=tmp_path / "target.db")
        modified_state = SyncState(
            session_id=sample_state.session_id,
            markdown_path="/different/path.md",
            epic_key="OTHER-1",
        )
        target.save(modified_state)

        migrator = StateStoreMigrator(source, target)
        result = migrator.migrate(overwrite=True)

        assert result["migrated"] == 1
        assert result["skipped"] == 0

        # Verify target has source data
        loaded = target.load(sample_state.session_id)
        assert loaded is not None
        assert loaded.markdown_path == sample_state.markdown_path

    def test_migrate_rollback(
        self,
        tmp_path: Path,
        multiple_states: list[SyncState],
    ) -> None:
        """Test rolling back migration."""
        source = FileStateStore(state_dir=tmp_path / "source")
        for state in multiple_states:
            source.save(state)

        target = SQLiteStateStore(db_path=tmp_path / "target.db")

        migrator = StateStoreMigrator(source, target)
        migrator.migrate()

        # Rollback
        deleted = migrator.rollback()
        assert deleted == len(multiple_states)
        assert target.count() == 0


class TestExportImport:
    """Tests for export/import functions."""

    def test_export_to_json(
        self,
        tmp_path: Path,
        sqlite_store: SQLiteStateStore,
        multiple_states: list[SyncState],
    ) -> None:
        """Test exporting states to JSON."""
        for state in multiple_states:
            sqlite_store.save(state)

        output_path = tmp_path / "export.json"
        count = export_to_json(sqlite_store, output_path)

        assert count == len(multiple_states)
        assert output_path.exists()

        # Verify JSON content
        import json

        with open(output_path) as f:
            data = json.load(f)

        assert data["session_count"] == len(multiple_states)
        assert len(data["sessions"]) == len(multiple_states)

    def test_import_from_json(
        self,
        tmp_path: Path,
        file_store: FileStateStore,
        multiple_states: list[SyncState],
    ) -> None:
        """Test importing states from JSON."""
        # Create export file
        import json

        export_data = {
            "exported_at": datetime.now().isoformat(),
            "source_backend": "test",
            "session_count": len(multiple_states),
            "sessions": [s.to_dict() for s in multiple_states],
        }
        input_path = tmp_path / "import.json"
        with open(input_path, "w") as f:
            json.dump(export_data, f)

        # Import
        result = import_from_json(file_store, input_path)

        assert result["imported"] == len(multiple_states)
        assert result["skipped"] == 0
        assert result["failed"] == 0

    def test_import_skip_existing(
        self,
        tmp_path: Path,
        file_store: FileStateStore,
        sample_state: SyncState,
    ) -> None:
        """Test skipping existing during import."""
        file_store.save(sample_state)

        import json

        export_data = {
            "sessions": [sample_state.to_dict()],
        }
        input_path = tmp_path / "import.json"
        with open(input_path, "w") as f:
            json.dump(export_data, f)

        result = import_from_json(file_store, input_path, overwrite=False)

        assert result["imported"] == 0
        assert result["skipped"] == 1


class TestCreateStore:
    """Tests for create_store factory function."""

    def test_create_file_store(self, tmp_path: Path) -> None:
        """Test creating file store."""
        store = create_store("file", state_dir=tmp_path)
        assert isinstance(store, FileStateStore)

    def test_create_sqlite_store(self, tmp_path: Path) -> None:
        """Test creating SQLite store."""
        store = create_store("sqlite", db_path=tmp_path / "test.db")
        assert isinstance(store, SQLiteStateStore)

    def test_create_unknown_backend(self) -> None:
        """Test error on unknown backend."""
        with pytest.raises(ValueError, match="Unknown state store backend"):
            create_store("unknown")

    def test_create_postgres_without_psycopg2(self) -> None:
        """Test PostgreSQL requires psycopg2."""
        # This test may pass or fail depending on whether psycopg2 is installed
        # Just ensure it doesn't crash unexpectedly
        try:
            create_store("postgresql", connection_string="postgresql://test")
        except (ImportError, ValueError) as e:
            assert "psycopg2" in str(e).lower() or "connection" in str(e).lower()
