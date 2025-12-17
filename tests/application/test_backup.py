"""Tests for backup functionality."""

from unittest.mock import MagicMock

import pytest

from spectra.application.sync.backup import (
    Backup,
    BackupManager,
    IssueSnapshot,
    RestoreOperation,
    RestoreResult,
    create_pre_sync_backup,
    restore_from_backup,
)
from spectra.core.ports.issue_tracker import IssueData


class TestIssueSnapshot:
    """Tests for IssueSnapshot class."""

    def test_from_issue_data(self):
        """Should create snapshot from IssueData."""
        subtask = IssueData(
            key="PROJ-101",
            summary="Subtask 1",
            status="Open",
            issue_type="Sub-task",
        )
        issue = IssueData(
            key="PROJ-100",
            summary="Test Story",
            description={"type": "doc", "content": []},
            status="In Progress",
            issue_type="Story",
            assignee="user123",
            story_points=5.0,
            subtasks=[subtask],
        )

        snapshot = IssueSnapshot.from_issue_data(issue, comments_count=3)

        assert snapshot.key == "PROJ-100"
        assert snapshot.summary == "Test Story"
        assert snapshot.status == "In Progress"
        assert snapshot.story_points == 5.0
        assert snapshot.comments_count == 3
        assert len(snapshot.subtasks) == 1
        assert snapshot.subtasks[0].key == "PROJ-101"

    def test_to_dict_and_back(self):
        """Should serialize and deserialize correctly."""
        snapshot = IssueSnapshot(
            key="PROJ-100",
            summary="Test Story",
            description="Some description",
            status="Open",
            story_points=3.0,
            subtasks=[
                IssueSnapshot(
                    key="PROJ-101",
                    summary="Subtask",
                    status="Todo",
                )
            ],
        )

        data = snapshot.to_dict()
        restored = IssueSnapshot.from_dict(data)

        assert restored.key == snapshot.key
        assert restored.summary == snapshot.summary
        assert restored.story_points == snapshot.story_points
        assert len(restored.subtasks) == 1
        assert restored.subtasks[0].key == "PROJ-101"


class TestBackup:
    """Tests for Backup class."""

    def test_issue_count(self):
        """Should count issues correctly."""
        backup = Backup(
            backup_id="test123",
            epic_key="PROJ-1",
            markdown_path="/path/to/file.md",
            issues=[
                IssueSnapshot(key="PROJ-100", summary="Story 1"),
                IssueSnapshot(key="PROJ-200", summary="Story 2"),
            ],
        )

        assert backup.issue_count == 2

    def test_subtask_count(self):
        """Should count subtasks across all issues."""
        backup = Backup(
            backup_id="test123",
            epic_key="PROJ-1",
            markdown_path="/path/to/file.md",
            issues=[
                IssueSnapshot(
                    key="PROJ-100",
                    summary="Story 1",
                    subtasks=[
                        IssueSnapshot(key="PROJ-101", summary="Sub 1"),
                        IssueSnapshot(key="PROJ-102", summary="Sub 2"),
                    ],
                ),
                IssueSnapshot(
                    key="PROJ-200",
                    summary="Story 2",
                    subtasks=[
                        IssueSnapshot(key="PROJ-201", summary="Sub 3"),
                    ],
                ),
            ],
        )

        assert backup.subtask_count == 3

    def test_get_issue(self):
        """Should find issue by key."""
        backup = Backup(
            backup_id="test123",
            epic_key="PROJ-1",
            markdown_path="/path/to/file.md",
            issues=[
                IssueSnapshot(
                    key="PROJ-100",
                    summary="Story 1",
                    subtasks=[
                        IssueSnapshot(key="PROJ-101", summary="Sub 1"),
                    ],
                ),
            ],
        )

        # Find parent issue
        issue = backup.get_issue("PROJ-100")
        assert issue is not None
        assert issue.summary == "Story 1"

        # Find subtask
        subtask = backup.get_issue("PROJ-101")
        assert subtask is not None
        assert subtask.summary == "Sub 1"

        # Not found
        assert backup.get_issue("PROJ-999") is None

    def test_to_dict_and_back(self):
        """Should serialize and deserialize correctly."""
        backup = Backup(
            backup_id="test123",
            epic_key="PROJ-1",
            markdown_path="/path/to/file.md",
            issues=[
                IssueSnapshot(key="PROJ-100", summary="Story 1"),
            ],
            metadata={"trigger": "test"},
        )

        data = backup.to_dict()
        restored = Backup.from_dict(data)

        assert restored.backup_id == backup.backup_id
        assert restored.epic_key == backup.epic_key
        assert restored.markdown_path == backup.markdown_path
        assert len(restored.issues) == 1
        assert restored.metadata == {"trigger": "test"}


class TestBackupManager:
    """Tests for BackupManager class."""

    @pytest.fixture
    def backup_dir(self, tmp_path):
        """Create a temporary backup directory."""
        return tmp_path / "backups"

    @pytest.fixture
    def manager(self, backup_dir):
        """Create a BackupManager with temp directory."""
        return BackupManager(
            backup_dir=backup_dir,
            max_backups=3,
            retention_days=7,
        )

    @pytest.fixture
    def mock_tracker(self):
        """Create a mock tracker."""
        tracker = MagicMock()
        tracker.get_epic_children.return_value = [
            IssueData(
                key="PROJ-100",
                summary="Story 1",
                status="Open",
                issue_type="Story",
                subtasks=[
                    IssueData(key="PROJ-101", summary="Sub 1", status="Todo"),
                ],
            ),
            IssueData(
                key="PROJ-200",
                summary="Story 2",
                status="In Progress",
                issue_type="Story",
            ),
        ]
        tracker.get_issue_comments.return_value = [{"id": "1"}, {"id": "2"}]
        return tracker

    def test_create_backup(self, manager, mock_tracker, backup_dir):
        """Should create backup and save to disk."""
        backup = manager.create_backup(
            tracker=mock_tracker,
            epic_key="PROJ-1",
            markdown_path="/path/to/file.md",
            metadata={"test": True},
        )

        # Check backup properties
        assert backup.epic_key == "PROJ-1"
        assert backup.markdown_path == "/path/to/file.md"
        assert backup.issue_count == 2
        assert backup.metadata == {"test": True}

        # Check file was created
        epic_dir = backup_dir / "PROJ-1"
        assert epic_dir.exists()
        backup_files = list(epic_dir.glob("*.json"))
        assert len(backup_files) == 1

    def test_save_and_load_backup(self, manager, backup_dir):
        """Should save and load backup correctly."""
        backup = Backup(
            backup_id="test_backup_123",
            epic_key="PROJ-1",
            markdown_path="/path/to/file.md",
            issues=[
                IssueSnapshot(key="PROJ-100", summary="Story 1"),
            ],
        )

        # Save
        path = manager.save_backup(backup)
        assert path.exists()

        # Load
        loaded = manager.load_backup("test_backup_123", "PROJ-1")
        assert loaded is not None
        assert loaded.backup_id == backup.backup_id
        assert loaded.issue_count == 1

    def test_list_backups(self, manager, mock_tracker):
        """Should list all backups."""
        # Create multiple backups for different epics
        # Manager has max_backups=3 per epic, so within-epic cleanup applies
        manager.create_backup(mock_tracker, "PROJ-1", "/file1.md")
        manager.create_backup(mock_tracker, "PROJ-2", "/file2.md")
        manager.create_backup(mock_tracker, "PROJ-3", "/file3.md")

        # List all - should have 3 (one per epic)
        all_backups = manager.list_backups()
        assert len(all_backups) == 3

        # List by epic - each should have 1
        proj1_backups = manager.list_backups("PROJ-1")
        assert len(proj1_backups) == 1

        proj2_backups = manager.list_backups("PROJ-2")
        assert len(proj2_backups) == 1

    def test_get_latest_backup(self, manager, mock_tracker):
        """Should return most recent backup."""
        # Create backups with slight delay between them
        manager.create_backup(mock_tracker, "PROJ-1", "/file1.md")
        backup2 = manager.create_backup(mock_tracker, "PROJ-1", "/file2.md")

        latest = manager.get_latest_backup("PROJ-1")
        assert latest is not None
        assert latest.backup_id == backup2.backup_id

    def test_delete_backup(self, manager, mock_tracker, backup_dir):
        """Should delete backup file."""
        backup = manager.create_backup(mock_tracker, "PROJ-1", "/file.md")

        # Verify exists
        assert len(manager.list_backups("PROJ-1")) == 1

        # Delete
        result = manager.delete_backup(backup.backup_id, "PROJ-1")
        assert result is True

        # Verify deleted
        assert len(manager.list_backups("PROJ-1")) == 0

    def test_cleanup_over_limit(self, backup_dir, mock_tracker):
        """Should cleanup backups over max limit."""
        # Create manager with max_backups=3
        manager = BackupManager(
            backup_dir=backup_dir,
            max_backups=3,
            retention_days=7,
        )

        # Create more than max_backups (3)
        created_backups = []
        for i in range(5):
            backup = manager.create_backup(mock_tracker, "PROJ-1", f"/file{i}.md")
            created_backups.append(backup)

        # After creating 5, cleanup should have kept only 3 most recent
        backups = manager.list_backups("PROJ-1")
        assert len(backups) == 3

        # The 3 kept should be the most recent ones
        backup_ids = {b["backup_id"] for b in backups}
        # Last 3 created should be kept
        assert created_backups[-1].backup_id in backup_ids

    def test_backup_id_generation(self, manager):
        """Should generate unique backup IDs."""
        import time
        # Generate multiple IDs with small delays to ensure uniqueness
        ids = []
        for _ in range(10):
            ids.append(manager._generate_backup_id("PROJ-1"))
            time.sleep(0.001)  # 1ms delay to ensure timestamp changes

        # All IDs should be unique
        assert len(set(ids)) == 10

        # All IDs should contain epic key
        for id_ in ids:
            assert "PROJ-1" in id_


class TestCreatePreSyncBackup:
    """Tests for create_pre_sync_backup convenience function."""

    def test_creates_backup(self, tmp_path):
        """Should create backup with pre_sync metadata."""
        tracker = MagicMock()
        tracker.get_epic_children.return_value = [
            IssueData(key="PROJ-100", summary="Story 1", status="Open"),
        ]
        tracker.get_issue_comments.return_value = []

        backup = create_pre_sync_backup(
            tracker=tracker,
            epic_key="PROJ-1",
            markdown_path="/path/to/epic.md",
            backup_dir=tmp_path / "backups",
        )

        assert backup.epic_key == "PROJ-1"
        assert backup.metadata.get("trigger") == "pre_sync"
        assert backup.issue_count == 1


class TestRestoreResult:
    """Tests for RestoreResult class."""

    def test_add_operation_success(self):
        """Should track successful operations."""
        result = RestoreResult(backup_id="test", epic_key="PROJ-1")

        result.add_operation(
            RestoreOperation(
                issue_key="PROJ-100",
                field="description",
                success=True,
            )
        )

        assert result.success is True
        assert result.total_operations == 1
        assert result.successful_operations == 1
        assert result.failed_operations == 0

    def test_add_operation_failure(self):
        """Should track failed operations and mark result as failed."""
        result = RestoreResult(backup_id="test", epic_key="PROJ-1")

        result.add_operation(
            RestoreOperation(
                issue_key="PROJ-100",
                field="description",
                success=False,
                error="Permission denied",
            )
        )

        assert result.success is False
        assert result.failed_operations == 1
        assert len(result.errors) == 1
        assert "Permission denied" in result.errors[0]

    def test_skipped_operations(self):
        """Should track skipped operations."""
        result = RestoreResult(backup_id="test", epic_key="PROJ-1")

        result.add_operation(
            RestoreOperation(
                issue_key="PROJ-100",
                field="description",
                skipped=True,
                skip_reason="No changes needed",
            )
        )

        # Skipped operations don't affect success status
        assert result.success is True
        assert result.skipped_operations == 1

    def test_summary(self):
        """Should generate readable summary."""
        result = RestoreResult(
            backup_id="test123",
            epic_key="PROJ-1",
            dry_run=False,
        )
        result.issues_restored = 3
        result.subtasks_restored = 5

        summary = result.summary()

        assert "test123" in summary
        assert "PROJ-1" in summary
        assert "Issues restored: 3" in summary
        assert "Subtasks restored: 5" in summary


class TestBackupManagerRestore:
    """Tests for BackupManager restore functionality."""

    @pytest.fixture
    def backup_dir(self, tmp_path):
        """Create a temporary backup directory."""
        return tmp_path / "backups"

    @pytest.fixture
    def manager(self, backup_dir):
        """Create a BackupManager with temp directory."""
        return BackupManager(backup_dir=backup_dir)

    @pytest.fixture
    def mock_tracker(self):
        """Create a mock tracker for backup creation."""
        tracker = MagicMock()
        tracker.get_epic_children.return_value = [
            IssueData(
                key="PROJ-100",
                summary="Story 1",
                description={
                    "type": "doc",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "Original description"}],
                        }
                    ],
                },
                status="Open",
                issue_type="Story",
                subtasks=[
                    IssueData(key="PROJ-101", summary="Sub 1", status="Todo", story_points=3.0),
                ],
            ),
        ]
        tracker.get_issue_comments.return_value = []
        return tracker

    @pytest.fixture
    def mock_restore_tracker(self):
        """Create a mock tracker for restore operations."""
        tracker = MagicMock()
        tracker.update_issue_description.return_value = True
        tracker.update_subtask.return_value = True
        return tracker

    def test_restore_backup_dry_run(self, manager, mock_tracker, mock_restore_tracker):
        """Should simulate restore in dry-run mode."""
        # Create a backup first
        backup = manager.create_backup(mock_tracker, "PROJ-1", "/file.md")

        # Restore in dry-run mode
        result = manager.restore_backup(
            tracker=mock_restore_tracker,
            backup_id=backup.backup_id,
            epic_key="PROJ-1",
            dry_run=True,
        )

        assert result.success is True
        assert result.dry_run is True
        # No actual API calls should be made
        mock_restore_tracker.update_issue_description.assert_not_called()
        mock_restore_tracker.update_subtask.assert_not_called()

    def test_restore_backup_execute(self, manager, mock_tracker, mock_restore_tracker):
        """Should execute restore operations."""
        # Create a backup first
        backup = manager.create_backup(mock_tracker, "PROJ-1", "/file.md")

        # Restore with execute
        result = manager.restore_backup(
            tracker=mock_restore_tracker,
            backup_id=backup.backup_id,
            epic_key="PROJ-1",
            dry_run=False,
        )

        assert result.success is True
        assert result.dry_run is False
        # API calls should be made
        mock_restore_tracker.update_issue_description.assert_called()
        mock_restore_tracker.update_subtask.assert_called()

    def test_restore_backup_not_found(self, manager, mock_restore_tracker):
        """Should return error when backup not found."""
        result = manager.restore_backup(
            tracker=mock_restore_tracker,
            backup_id="nonexistent",
            epic_key="PROJ-1",
            dry_run=True,
        )

        assert result.success is False
        assert "not found" in result.errors[0].lower()

    def test_restore_with_issue_filter(self, manager, mock_tracker, mock_restore_tracker):
        """Should only restore filtered issues."""
        # Create a backup first
        backup = manager.create_backup(mock_tracker, "PROJ-1", "/file.md")

        # Restore with filter - only PROJ-100, not subtasks
        result = manager.restore_backup(
            tracker=mock_restore_tracker,
            backup_id=backup.backup_id,
            epic_key="PROJ-1",
            dry_run=False,
            issue_filter=["PROJ-100"],  # Only parent, not subtask
        )

        assert result.success is True
        # Only parent issue should be restored, not subtask
        mock_restore_tracker.update_issue_description.assert_called_once()
        mock_restore_tracker.update_subtask.assert_not_called()

    def test_restore_handles_api_error(self, manager, mock_tracker):
        """Should handle API errors gracefully."""
        # Create a backup first
        backup = manager.create_backup(mock_tracker, "PROJ-1", "/file.md")

        # Create tracker that raises an error
        error_tracker = MagicMock()
        error_tracker.update_issue_description.side_effect = Exception("API Error")
        error_tracker.update_subtask.side_effect = Exception("API Error")

        result = manager.restore_backup(
            tracker=error_tracker,
            backup_id=backup.backup_id,
            epic_key="PROJ-1",
            dry_run=False,
        )

        assert result.success is False
        assert len(result.errors) > 0
        assert "API Error" in result.errors[0]


class TestRestoreFromBackup:
    """Tests for restore_from_backup convenience function."""

    def test_restore_from_backup(self, tmp_path):
        """Should restore using convenience function."""
        backup_dir = tmp_path / "backups"

        # Create a backup first
        create_tracker = MagicMock()
        create_tracker.get_epic_children.return_value = [
            IssueData(key="PROJ-100", summary="Story 1", status="Open", description="Test"),
        ]
        create_tracker.get_issue_comments.return_value = []

        manager = BackupManager(backup_dir=backup_dir)
        backup = manager.create_backup(create_tracker, "PROJ-1", "/file.md")

        # Restore using convenience function
        restore_tracker = MagicMock()
        restore_tracker.update_issue_description.return_value = True

        result = restore_from_backup(
            tracker=restore_tracker,
            backup_id=backup.backup_id,
            epic_key="PROJ-1",
            dry_run=True,
            backup_dir=backup_dir,
        )

        assert result.backup_id == backup.backup_id
        assert result.epic_key == "PROJ-1"
        assert result.dry_run is True
