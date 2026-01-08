"""Tests for CLI backup commands."""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

import pytest

from spectryn.cli.commands.backup import (
    list_backups,
    list_sessions,
    run_diff,
    run_restore,
    run_rollback,
)
from spectryn.cli.exit_codes import ExitCode


# =============================================================================
# list_sessions Tests
# =============================================================================


class TestListSessions:
    """Tests for list_sessions command."""

    def test_list_sessions_empty(self):
        """Test listing when no sessions exist."""
        mock_state_store = MagicMock()
        mock_state_store.list_sessions.return_value = []
        mock_state_store.state_dir = "/path/to/state"

        result = list_sessions(mock_state_store)

        assert result == ExitCode.SUCCESS

    def test_list_sessions_with_data(self):
        """Test listing sessions with data."""
        mock_state_store = MagicMock()
        mock_state_store.list_sessions.return_value = [
            {
                "session_id": "session-123456789012",
                "epic_key": "EPIC-123",
                "phase": "completed",
                "progress": "5/5",
                "updated_at": "2024-01-01T00:00:00Z",
            },
            {
                "session_id": "session-987654321098",
                "epic_key": "EPIC-456",
                "phase": "in_progress",
                "progress": "3/5",
                "updated_at": "2024-01-02T00:00:00Z",
            },
        ]
        mock_state_store.state_dir = "/path/to/state"

        result = list_sessions(mock_state_store)

        assert result == ExitCode.SUCCESS


# =============================================================================
# list_backups Tests
# =============================================================================


class TestListBackups:
    """Tests for list_backups command."""

    def test_list_backups_empty(self):
        """Test listing when no backups exist."""
        mock_manager = MagicMock()
        mock_manager.list_backups.return_value = []
        mock_manager.backup_dir = "/path/to/backups"

        result = list_backups(mock_manager)

        assert result == ExitCode.SUCCESS

    def test_list_backups_with_data(self):
        """Test listing backups with data."""
        mock_manager = MagicMock()
        mock_manager.list_backups.return_value = [
            {
                "backup_id": "backup-12345678901234567890123456789012345678",
                "epic_key": "EPIC-123",
                "issue_count": 10,
                "created_at": "2024-01-01T00:00:00Z",
            },
        ]
        mock_manager.backup_dir = "/path/to/backups"

        result = list_backups(mock_manager)

        assert result == ExitCode.SUCCESS

    def test_list_backups_with_epic_filter(self):
        """Test listing backups with epic filter."""
        mock_manager = MagicMock()
        mock_manager.list_backups.return_value = []
        mock_manager.backup_dir = "/path/to/backups"

        result = list_backups(mock_manager, epic_key="EPIC-123")

        assert result == ExitCode.SUCCESS
        mock_manager.list_backups.assert_called_once_with("EPIC-123")


# =============================================================================
# run_restore Tests
# =============================================================================


class TestRunRestore:
    """Tests for run_restore command."""

    @pytest.fixture
    def mock_args(self):
        """Create mock arguments."""
        args = argparse.Namespace(
            restore_backup="backup-123",
            epic=None,
            execute=False,
            backup_dir=None,
            config=None,
            verbose=False,
            log_format="text",
            no_color=False,
            quiet=False,
            no_confirm=True,
        )
        return args

    @pytest.fixture
    def mock_backup(self):
        """Create a mock backup."""
        backup = MagicMock()
        backup.backup_id = "backup-123"
        backup.epic_key = "EPIC-123"
        backup.created_at = "2024-01-01T00:00:00Z"
        backup.issue_count = 5
        backup.subtask_count = 10
        return backup

    @pytest.fixture
    def mock_restore_result(self):
        """Create mock restore result."""
        result = MagicMock()
        result.success = True
        result.issues_restored = 5
        result.subtasks_restored = 10
        result.successful_operations = 15
        result.failed_operations = 0
        result.skipped_operations = 0
        result.errors = []
        result.warnings = []
        return result

    def test_restore_backup_not_found(self, mock_args):
        """Test restore with backup not found."""
        mock_manager = MagicMock()
        mock_manager.load_backup.return_value = None

        with patch("spectryn.application.sync.BackupManager", return_value=mock_manager):
            with patch("spectryn.cli.logging.setup_logging"):
                result = run_restore(mock_args)

        assert result == ExitCode.FILE_NOT_FOUND

    def test_restore_config_error(self, mock_args, mock_backup):
        """Test restore with config validation error."""
        mock_manager = MagicMock()
        mock_manager.load_backup.return_value = mock_backup

        mock_provider = MagicMock()
        mock_provider.validate.return_value = ["Missing JIRA_URL"]

        with patch("spectryn.application.sync.BackupManager", return_value=mock_manager):
            with patch("spectryn.adapters.EnvironmentConfigProvider", return_value=mock_provider):
                with patch("spectryn.adapters.JiraAdapter"):
                    with patch("spectryn.adapters.ADFFormatter"):
                        with patch("spectryn.cli.logging.setup_logging"):
                            result = run_restore(mock_args)

        assert result == ExitCode.CONFIG_ERROR

    def test_restore_connection_error(self, mock_args, mock_backup):
        """Test restore with connection error."""
        mock_manager = MagicMock()
        mock_manager.load_backup.return_value = mock_backup

        mock_provider = MagicMock()
        mock_provider.validate.return_value = []
        mock_provider.load.return_value = MagicMock()

        mock_adapter = MagicMock()
        mock_adapter.test_connection.return_value = False

        with patch("spectryn.application.sync.BackupManager", return_value=mock_manager):
            with patch("spectryn.adapters.EnvironmentConfigProvider", return_value=mock_provider):
                with patch("spectryn.adapters.JiraAdapter", return_value=mock_adapter):
                    with patch("spectryn.adapters.ADFFormatter"):
                        with patch("spectryn.cli.logging.setup_logging"):
                            result = run_restore(mock_args)

        assert result == ExitCode.CONNECTION_ERROR

    def test_restore_dry_run_success(self, mock_args, mock_backup, mock_restore_result):
        """Test successful dry-run restore."""
        mock_manager = MagicMock()
        mock_manager.load_backup.return_value = mock_backup
        mock_manager.restore_backup.return_value = mock_restore_result

        mock_provider = MagicMock()
        mock_provider.validate.return_value = []
        mock_provider.load.return_value = MagicMock()

        mock_adapter = MagicMock()
        mock_adapter.test_connection.return_value = True
        mock_adapter.get_current_user.return_value = {"displayName": "Test"}

        with patch("spectryn.application.sync.BackupManager", return_value=mock_manager):
            with patch("spectryn.adapters.EnvironmentConfigProvider", return_value=mock_provider):
                with patch("spectryn.adapters.JiraAdapter", return_value=mock_adapter):
                    with patch("spectryn.adapters.ADFFormatter"):
                        with patch("spectryn.cli.logging.setup_logging"):
                            result = run_restore(mock_args)

        assert result == ExitCode.SUCCESS


# =============================================================================
# run_diff Tests
# =============================================================================


class TestRunDiff:
    """Tests for run_diff command."""

    @pytest.fixture
    def mock_args(self):
        """Create mock arguments."""
        args = argparse.Namespace(
            diff_backup="backup-123",
            diff_latest=False,
            epic=None,
            backup_dir=None,
            config=None,
            verbose=False,
            log_format="text",
            no_color=False,
            quiet=False,
        )
        return args

    @pytest.fixture
    def mock_backup(self):
        """Create a mock backup."""
        backup = MagicMock()
        backup.backup_id = "backup-123"
        backup.epic_key = "EPIC-123"
        backup.created_at = "2024-01-01T00:00:00Z"
        backup.issue_count = 5
        return backup

    def test_diff_backup_not_found(self, mock_args):
        """Test diff with backup not found."""
        mock_manager = MagicMock()
        mock_manager.load_backup.return_value = None

        with patch("spectryn.application.sync.BackupManager", return_value=mock_manager):
            with patch("spectryn.cli.logging.setup_logging"):
                result = run_diff(mock_args)

        assert result == ExitCode.FILE_NOT_FOUND

    def test_diff_latest_requires_epic(self, mock_args):
        """Test diff_latest requires epic."""
        mock_args.diff_latest = True
        mock_args.diff_backup = None

        with patch("spectryn.application.sync.BackupManager"):
            with patch("spectryn.cli.logging.setup_logging"):
                result = run_diff(mock_args)

        assert result == ExitCode.CONFIG_ERROR

    def test_diff_latest_no_backup(self, mock_args):
        """Test diff_latest with no backup found."""
        mock_args.diff_latest = True
        mock_args.diff_backup = None
        mock_args.epic = "EPIC-123"

        mock_manager = MagicMock()
        mock_manager.get_latest_backup.return_value = None

        with patch("spectryn.application.sync.BackupManager", return_value=mock_manager):
            with patch("spectryn.cli.logging.setup_logging"):
                result = run_diff(mock_args)

        assert result == ExitCode.FILE_NOT_FOUND

    def test_diff_config_error(self, mock_args, mock_backup):
        """Test diff with config validation error."""
        mock_manager = MagicMock()
        mock_manager.load_backup.return_value = mock_backup

        mock_provider = MagicMock()
        mock_provider.validate.return_value = ["Missing JIRA_URL"]

        with patch("spectryn.application.sync.BackupManager", return_value=mock_manager):
            with patch("spectryn.adapters.EnvironmentConfigProvider", return_value=mock_provider):
                with patch("spectryn.adapters.JiraAdapter"):
                    with patch("spectryn.adapters.ADFFormatter"):
                        with patch("spectryn.cli.logging.setup_logging"):
                            result = run_diff(mock_args)

        assert result == ExitCode.CONFIG_ERROR

    def test_diff_success(self, mock_args, mock_backup):
        """Test successful diff."""
        mock_manager = MagicMock()
        mock_manager.load_backup.return_value = mock_backup

        mock_provider = MagicMock()
        mock_provider.validate.return_value = []
        mock_provider.load.return_value = MagicMock()

        mock_adapter = MagicMock()
        mock_adapter.test_connection.return_value = True
        mock_adapter.get_current_user.return_value = {"displayName": "Test"}

        mock_diff_result = MagicMock()
        mock_diff_result.has_changes = False
        mock_diff_result.changed_issues = 0
        mock_diff_result.total_issues = 5
        mock_diff_result.total_changes = 0

        with patch("spectryn.application.sync.BackupManager", return_value=mock_manager):
            with patch("spectryn.adapters.EnvironmentConfigProvider", return_value=mock_provider):
                with patch("spectryn.adapters.JiraAdapter", return_value=mock_adapter):
                    with patch("spectryn.adapters.ADFFormatter"):
                        with patch(
                            "spectryn.application.sync.compare_backup_to_current"
                        ) as mock_compare:
                            mock_compare.return_value = (mock_diff_result, "No changes")
                            with patch("spectryn.cli.logging.setup_logging"):
                                result = run_diff(mock_args)

        assert result == ExitCode.SUCCESS


# =============================================================================
# run_rollback Tests
# =============================================================================


class TestRunRollback:
    """Tests for run_rollback command."""

    @pytest.fixture
    def mock_args(self):
        """Create mock arguments."""
        args = argparse.Namespace(
            epic="EPIC-123",
            execute=False,
            backup_dir=None,
            config=None,
            verbose=False,
            log_format="text",
            no_color=False,
            quiet=False,
            no_confirm=True,
        )
        return args

    @pytest.fixture
    def mock_backup(self):
        """Create a mock backup."""
        backup = MagicMock()
        backup.backup_id = "backup-123"
        backup.epic_key = "EPIC-123"
        backup.created_at = "2024-01-01T00:00:00Z"
        backup.issue_count = 5
        backup.subtask_count = 10
        return backup

    def test_rollback_requires_epic(self, mock_args):
        """Test rollback requires epic."""
        mock_args.epic = None

        with patch("spectryn.cli.logging.setup_logging"):
            result = run_rollback(mock_args)

        assert result == ExitCode.CONFIG_ERROR

    def test_rollback_no_backup_found(self, mock_args):
        """Test rollback with no backup found."""
        mock_manager = MagicMock()
        mock_manager.get_latest_backup.return_value = None

        with patch("spectryn.application.sync.BackupManager", return_value=mock_manager):
            with patch("spectryn.cli.logging.setup_logging"):
                result = run_rollback(mock_args)

        assert result == ExitCode.FILE_NOT_FOUND

    def test_rollback_config_error(self, mock_args, mock_backup):
        """Test rollback with config validation error."""
        mock_manager = MagicMock()
        mock_manager.get_latest_backup.return_value = mock_backup

        mock_provider = MagicMock()
        mock_provider.validate.return_value = ["Missing JIRA_URL"]

        with patch("spectryn.application.sync.BackupManager", return_value=mock_manager):
            with patch("spectryn.adapters.EnvironmentConfigProvider", return_value=mock_provider):
                with patch("spectryn.adapters.JiraAdapter"):
                    with patch("spectryn.adapters.ADFFormatter"):
                        with patch("spectryn.cli.logging.setup_logging"):
                            result = run_rollback(mock_args)

        assert result == ExitCode.CONFIG_ERROR

    def test_rollback_no_changes(self, mock_args, mock_backup):
        """Test rollback with no changes to make."""
        mock_manager = MagicMock()
        mock_manager.get_latest_backup.return_value = mock_backup

        mock_provider = MagicMock()
        mock_provider.validate.return_value = []
        mock_provider.load.return_value = MagicMock()

        mock_adapter = MagicMock()
        mock_adapter.test_connection.return_value = True
        mock_adapter.get_current_user.return_value = {"displayName": "Test"}

        mock_diff_result = MagicMock()
        mock_diff_result.has_changes = False

        with patch("spectryn.application.sync.BackupManager", return_value=mock_manager):
            with patch("spectryn.adapters.EnvironmentConfigProvider", return_value=mock_provider):
                with patch("spectryn.adapters.JiraAdapter", return_value=mock_adapter):
                    with patch("spectryn.adapters.ADFFormatter"):
                        with patch(
                            "spectryn.application.sync.compare_backup_to_current"
                        ) as mock_compare:
                            mock_compare.return_value = (mock_diff_result, "No changes")
                            with patch("spectryn.cli.logging.setup_logging"):
                                result = run_rollback(mock_args)

        assert result == ExitCode.SUCCESS

    def test_rollback_dry_run_success(self, mock_args, mock_backup):
        """Test successful dry-run rollback."""
        mock_manager = MagicMock()
        mock_manager.get_latest_backup.return_value = mock_backup

        mock_restore_result = MagicMock()
        mock_restore_result.success = True
        mock_restore_result.issues_restored = 5
        mock_restore_result.subtasks_restored = 10
        mock_restore_result.errors = []
        mock_manager.restore_backup.return_value = mock_restore_result

        mock_provider = MagicMock()
        mock_provider.validate.return_value = []
        mock_provider.load.return_value = MagicMock()

        mock_adapter = MagicMock()
        mock_adapter.test_connection.return_value = True
        mock_adapter.get_current_user.return_value = {"displayName": "Test"}

        mock_diff_result = MagicMock()
        mock_diff_result.has_changes = True
        mock_diff_result.changed_issues = 3

        with patch("spectryn.application.sync.BackupManager", return_value=mock_manager):
            with patch("spectryn.adapters.EnvironmentConfigProvider", return_value=mock_provider):
                with patch("spectryn.adapters.JiraAdapter", return_value=mock_adapter):
                    with patch("spectryn.adapters.ADFFormatter"):
                        with patch(
                            "spectryn.application.sync.compare_backup_to_current"
                        ) as mock_compare:
                            mock_compare.return_value = (mock_diff_result, "Changes found")
                            with patch("spectryn.cli.logging.setup_logging"):
                                result = run_rollback(mock_args)

        assert result == ExitCode.SUCCESS
