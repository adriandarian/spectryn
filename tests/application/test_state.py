"""
Tests for sync state persistence.
"""

import pytest

from spectra.application.sync.state import (
    OperationRecord,
    StateStore,
    SyncPhase,
    SyncState,
)


class TestOperationRecord:
    """Tests for OperationRecord dataclass."""

    def test_create_operation(self):
        """Test creating an operation record."""
        op = OperationRecord(
            operation_type="update_description",
            issue_key="PROJ-123",
            story_id="US-001",
        )

        assert op.operation_type == "update_description"
        assert op.issue_key == "PROJ-123"
        assert op.story_id == "US-001"
        assert op.status == "pending"
        assert op.is_pending is True

    def test_mark_completed(self):
        """Test marking an operation as completed."""
        op = OperationRecord("update", "PROJ-1", "US-1")
        assert op.is_pending is True

        op.mark_completed()
        assert op.is_completed is True
        assert op.status == "completed"
        assert op.timestamp is not None

    def test_mark_failed(self):
        """Test marking an operation as failed."""
        op = OperationRecord("update", "PROJ-1", "US-1")

        op.mark_failed("Connection error")
        assert op.status == "failed"
        assert op.error == "Connection error"

    def test_to_dict(self):
        """Test serialization to dict."""
        op = OperationRecord("update", "PROJ-1", "US-1")
        op.mark_completed()

        data = op.to_dict()
        assert data["operation_type"] == "update"
        assert data["issue_key"] == "PROJ-1"
        assert data["status"] == "completed"

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "operation_type": "create",
            "issue_key": "PROJ-2",
            "story_id": "US-2",
            "status": "completed",
            "error": None,
            "timestamp": "2024-01-15T10:00:00",
        }

        op = OperationRecord.from_dict(data)
        assert op.operation_type == "create"
        assert op.is_completed is True


class TestSyncState:
    """Tests for SyncState dataclass."""

    def test_create_state(self):
        """Test creating a sync state."""
        state = SyncState(
            session_id="abc123",
            markdown_path="/path/to/file.md",
            epic_key="PROJ-100",
        )

        assert state.session_id == "abc123"
        assert state.phase == SyncPhase.INITIALIZED.value
        assert state.operations == []
        assert state.dry_run is True

    def test_add_operation(self):
        """Test adding an operation to state."""
        state = SyncState("abc", "/path", "PROJ-1")

        op = state.add_operation("update", "PROJ-1", "US-1")

        assert len(state.operations) == 1
        assert op.operation_type == "update"
        assert state.pending_count == 1

    def test_find_operation(self):
        """Test finding an operation."""
        state = SyncState("abc", "/path", "PROJ-1")
        state.add_operation("update", "PROJ-1", "US-1")
        state.add_operation("create", "PROJ-2", "US-2")

        op = state.find_operation("update", "PROJ-1")
        assert op is not None
        assert op.story_id == "US-1"

        op2 = state.find_operation("delete", "PROJ-1")
        assert op2 is None

    def test_is_operation_completed(self):
        """Test checking if operation is completed."""
        state = SyncState("abc", "/path", "PROJ-1")
        op = state.add_operation("update", "PROJ-1", "US-1")

        assert state.is_operation_completed("update", "PROJ-1") is False

        op.mark_completed()
        assert state.is_operation_completed("update", "PROJ-1") is True

    def test_progress_tracking(self):
        """Test progress tracking."""
        state = SyncState("abc", "/path", "PROJ-1")
        state.add_operation("op1", "KEY-1", "S1").mark_completed()
        state.add_operation("op2", "KEY-2", "S2").mark_completed()
        state.add_operation("op3", "KEY-3", "S3")  # pending

        assert state.completed_count == 2
        assert state.pending_count == 1
        assert state.total_count == 3
        assert state.progress_percent == pytest.approx(66.67, rel=0.1)

    def test_to_dict(self):
        """Test serialization to dict."""
        state = SyncState("abc", "/path", "PROJ-1")
        state.add_operation("update", "PROJ-1", "US-1")

        data = state.to_dict()
        assert data["session_id"] == "abc"
        assert len(data["operations"]) == 1

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "session_id": "xyz",
            "markdown_path": "/test.md",
            "epic_key": "TEST-1",
            "phase": "analyzing",
            "operations": [
                {
                    "operation_type": "update",
                    "issue_key": "K-1",
                    "story_id": "S-1",
                    "status": "pending",
                }
            ],
            "config": {},
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
            "dry_run": False,
            "matched_stories": [],
            "unmatched_stories": [],
        }

        state = SyncState.from_dict(data)
        assert state.session_id == "xyz"
        assert state.phase == "analyzing"
        assert len(state.operations) == 1

    def test_generate_session_id(self):
        """Test session ID generation."""
        import time
        id1 = SyncState.generate_session_id("/path/file.md", "PROJ-1")
        time.sleep(0.001)  # Small delay to ensure timestamp changes
        id2 = SyncState.generate_session_id("/path/file.md", "PROJ-1")

        # Should be different due to timestamp
        assert id1 != id2
        assert len(id1) == 12


class TestStateStore:
    """Tests for StateStore class."""

    def test_save_and_load(self, tmp_path):
        """Test saving and loading state."""
        store = StateStore(state_dir=tmp_path)

        state = SyncState("test123", "/path/file.md", "PROJ-1")
        state.add_operation("update", "PROJ-1", "US-1")

        # Save
        path = store.save(state)
        assert path.exists()

        # Load
        loaded = store.load("test123")
        assert loaded is not None
        assert loaded.session_id == "test123"
        assert len(loaded.operations) == 1

    def test_load_nonexistent(self, tmp_path):
        """Test loading nonexistent state returns None."""
        store = StateStore(state_dir=tmp_path)

        loaded = store.load("nonexistent")
        assert loaded is None

    def test_delete(self, tmp_path):
        """Test deleting state."""
        store = StateStore(state_dir=tmp_path)

        state = SyncState("to_delete", "/path", "PROJ-1")
        store.save(state)

        assert store.delete("to_delete") is True
        assert store.load("to_delete") is None
        assert store.delete("to_delete") is False  # Already deleted

    def test_list_sessions(self, tmp_path):
        """Test listing sessions."""
        store = StateStore(state_dir=tmp_path)

        # Initially empty
        assert store.list_sessions() == []

        # Add sessions
        state1 = SyncState("sess1", "/path1.md", "PROJ-1")
        state2 = SyncState("sess2", "/path2.md", "PROJ-2")
        store.save(state1)
        store.save(state2)

        sessions = store.list_sessions()
        assert len(sessions) == 2
        assert any(s["session_id"] == "sess1" for s in sessions)
        assert any(s["session_id"] == "sess2" for s in sessions)

    def test_find_resumable(self, tmp_path):
        """Test finding resumable sessions."""
        store = StateStore(state_dir=tmp_path)

        # Add completed session
        completed = SyncState("done", "/path.md", "PROJ-1")
        completed.set_phase(SyncPhase.COMPLETED)
        store.save(completed)

        # Add in-progress session
        in_progress = SyncState("active", "/path.md", "PROJ-1")
        in_progress.set_phase(SyncPhase.SUBTASKS)
        store.save(in_progress)

        resumable = store.find_resumable()
        assert len(resumable) == 1
        assert resumable[0]["session_id"] == "active"

    def test_find_latest_resumable(self, tmp_path):
        """Test finding latest resumable session."""
        store = StateStore(state_dir=tmp_path)

        state = SyncState("latest", "/path.md", "PROJ-1")
        state.set_phase(SyncPhase.DESCRIPTIONS)
        store.save(state)

        found = store.find_latest_resumable("/path.md", "PROJ-1")
        assert found is not None
        assert found.session_id == "latest"

        # Different path - should not find
        not_found = store.find_latest_resumable("/other.md", "PROJ-1")
        assert not_found is None
