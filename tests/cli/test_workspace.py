"""
Tests for CLI workspace management commands.

Tests for:
- cmd_workspace_list: List workspaces
- cmd_workspace_create: Create new workspace
- cmd_workspace_use: Switch workspaces
- cmd_workspace_show: Show workspace details
- cmd_workspace_delete: Delete workspace
- cmd_workspace_archive: Archive workspace
- cmd_workspace_link: Link workspace to directory
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from spectryn.cli.workspace import (
    _print_workspace_detail,
    _print_workspace_table,
    _truncate_path,
    cmd_workspace_archive,
    cmd_workspace_create,
    cmd_workspace_delete,
    cmd_workspace_list,
    cmd_workspace_show,
    cmd_workspace_use,
)


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestTruncatePath:
    """Tests for _truncate_path helper."""

    def test_short_path_unchanged(self):
        """Test that short paths are not truncated."""
        path = "/home/user/project"
        assert _truncate_path(path, max_len=40) == path

    def test_long_path_truncated(self):
        """Test that long paths are truncated with ellipsis."""
        path = "/home/user/very/long/path/to/some/deep/directory/file.md"
        result = _truncate_path(path, max_len=20)
        assert len(result) == 20
        assert result.startswith("...")

    def test_exact_length_path(self):
        """Test path at exactly max_len."""
        path = "a" * 40
        assert _truncate_path(path, max_len=40) == path


class TestPrintWorkspaceTable:
    """Tests for _print_workspace_table helper."""

    def test_empty_workspaces(self, capsys):
        """Test output with no workspaces."""
        _print_workspace_table([])
        captured = capsys.readouterr()
        assert "No workspaces found" in captured.out

    def test_single_workspace(self, capsys):
        """Test output with single workspace."""
        from spectryn.core.workspace import Workspace, WorkspaceStatus, WorkspaceType

        ws = Workspace(
            id="test-ws",
            tenant_id="test-tenant",
            name="Test Workspace",
            workspace_type=WorkspaceType.PROJECT,
            status=WorkspaceStatus.ACTIVE,
        )
        _print_workspace_table([ws])
        captured = capsys.readouterr()
        assert "test-ws" in captured.out
        assert "Test Workspace" in captured.out

    def test_multiple_workspaces_with_tenant(self, capsys):
        """Test output with multiple workspaces showing tenant."""
        from spectryn.core.workspace import Workspace, WorkspaceStatus, WorkspaceType

        workspaces = [
            Workspace(
                id="ws-1",
                tenant_id="tenant-1",
                name="Workspace 1",
                workspace_type=WorkspaceType.PROJECT,
                status=WorkspaceStatus.ACTIVE,
            ),
            Workspace(
                id="ws-2",
                tenant_id="tenant-2",
                name="Workspace 2",
                workspace_type=WorkspaceType.SANDBOX,
                status=WorkspaceStatus.ARCHIVED,
            ),
        ]
        _print_workspace_table(workspaces, show_tenant=True)
        captured = capsys.readouterr()
        assert "tenant-1" in captured.out
        assert "tenant-2" in captured.out


class TestPrintWorkspaceDetail:
    """Tests for _print_workspace_detail helper."""

    def test_minimal_workspace(self, capsys):
        """Test output with minimal workspace info."""
        from spectryn.core.workspace import Workspace, WorkspaceStatus, WorkspaceType

        ws = Workspace(
            id="test-ws",
            tenant_id="test-tenant",
            name="Test Workspace",
            workspace_type=WorkspaceType.PROJECT,
            status=WorkspaceStatus.ACTIVE,
        )
        _print_workspace_detail(ws)
        captured = capsys.readouterr()
        assert "Test Workspace" in captured.out
        assert "test-ws" in captured.out
        assert "test-tenant" in captured.out

    def test_workspace_with_paths(self, capsys):
        """Test output with paths information."""
        from spectryn.core.workspace import Workspace, WorkspaceStatus, WorkspaceType

        ws = Workspace(
            id="test-ws",
            tenant_id="test-tenant",
            name="Test Workspace",
            workspace_type=WorkspaceType.PROJECT,
            status=WorkspaceStatus.ACTIVE,
            tags=["tag1", "tag2"],
            metadata={"key": "value"},
        )
        paths = Mock()
        paths.root = "/root"
        paths.config_dir = "/root/config"
        paths.state_dir = "/root/state"
        paths.cache_dir = "/root/cache"
        paths.backup_dir = "/root/backup"
        paths.markdown_dir = "/root/markdown"

        _print_workspace_detail(ws, paths)
        captured = capsys.readouterr()
        assert "tag1" in captured.out
        assert "Paths:" in captured.out
        assert "/root/config" in captured.out


# =============================================================================
# cmd_workspace_list Tests
# =============================================================================


class TestCmdWorkspaceList:
    """Tests for cmd_workspace_list command."""

    def test_list_workspaces_success(self, capsys):
        """Test successful workspace listing."""
        from spectryn.core.workspace import Workspace, WorkspaceStatus, WorkspaceType

        mock_manager = Mock()
        mock_manager.list_workspaces.return_value = [
            Workspace(
                id="ws-1",
                tenant_id="tenant-1",
                name="Workspace 1",
                workspace_type=WorkspaceType.PROJECT,
                status=WorkspaceStatus.ACTIVE,
            ),
        ]

        with patch("spectryn.cli.workspace.get_workspace_manager", return_value=mock_manager):
            result = cmd_workspace_list()

        assert result == 0
        captured = capsys.readouterr()
        assert "ws-1" in captured.out

    def test_list_workspaces_json_format(self, capsys):
        """Test workspace listing in JSON format."""
        from spectryn.core.workspace import Workspace, WorkspaceStatus, WorkspaceType

        mock_manager = Mock()
        ws = Workspace(
            id="ws-1",
            tenant_id="tenant-1",
            name="Workspace 1",
            workspace_type=WorkspaceType.PROJECT,
            status=WorkspaceStatus.ACTIVE,
        )
        mock_manager.list_workspaces.return_value = [ws]

        with patch("spectryn.cli.workspace.get_workspace_manager", return_value=mock_manager):
            result = cmd_workspace_list(output_format="json")

        assert result == 0
        captured = capsys.readouterr()
        assert '"id": "ws-1"' in captured.out

    def test_list_workspaces_with_filter(self):
        """Test workspace listing with type filter."""
        mock_manager = Mock()
        mock_manager.list_workspaces.return_value = []

        with patch("spectryn.cli.workspace.get_workspace_manager", return_value=mock_manager):
            result = cmd_workspace_list(workspace_type="project", tag="important")

        assert result == 0
        mock_manager.list_workspaces.assert_called_once()

    def test_list_workspaces_all_tenants(self, capsys):
        """Test listing workspaces across all tenants."""
        from spectryn.core.workspace import Workspace, WorkspaceStatus, WorkspaceType

        ws = Workspace(
            id="ws-1",
            tenant_id="tenant-1",
            name="Workspace 1",
            workspace_type=WorkspaceType.PROJECT,
            status=WorkspaceStatus.ACTIVE,
        )

        with patch("spectryn.cli.workspace.CrossTenantWorkspaceQuery") as mock_query_cls:
            mock_query = Mock()
            mock_query.list_all_workspaces.return_value = [("tenant-1", ws)]
            mock_query_cls.return_value = mock_query

            result = cmd_workspace_list(all_tenants=True)

        assert result == 0
        captured = capsys.readouterr()
        assert "ws-1" in captured.out

    def test_list_workspaces_error(self, capsys):
        """Test handling of listing errors."""
        with patch(
            "spectryn.cli.workspace.get_workspace_manager",
            side_effect=Exception("Database error"),
        ):
            result = cmd_workspace_list()

        assert result == 1
        captured = capsys.readouterr()
        assert "Database error" in captured.err


# =============================================================================
# cmd_workspace_create Tests
# =============================================================================


class TestCmdWorkspaceCreate:
    """Tests for cmd_workspace_create command."""

    def test_create_workspace_success(self, capsys):
        """Test successful workspace creation."""
        from spectryn.core.workspace import Workspace, WorkspaceStatus, WorkspaceType

        mock_manager = Mock()
        mock_manager.create.return_value = Workspace(
            id="new-ws",
            tenant_id="test-tenant",
            name="New Workspace",
            workspace_type=WorkspaceType.PROJECT,
            status=WorkspaceStatus.ACTIVE,
        )

        with patch("spectryn.cli.workspace.get_workspace_manager", return_value=mock_manager):
            result = cmd_workspace_create(
                workspace_id="new-ws",
                name="New Workspace",
                description="Test workspace",
            )

        assert result == 0
        captured = capsys.readouterr()
        assert "Created workspace: new-ws" in captured.out

    def test_create_workspace_with_options(self, capsys):
        """Test workspace creation with all options."""
        from spectryn.core.workspace import Workspace, WorkspaceStatus, WorkspaceType

        mock_manager = Mock()
        mock_manager.create.return_value = Workspace(
            id="new-ws",
            tenant_id="test-tenant",
            name="New Workspace",
            workspace_type=WorkspaceType.PROJECT,
            status=WorkspaceStatus.ACTIVE,
            local_path="/home/user/project",
            tracker_project="PROJ-123",
        )

        with patch("spectryn.cli.workspace.get_workspace_manager", return_value=mock_manager):
            result = cmd_workspace_create(
                workspace_id="new-ws",
                name="New Workspace",
                workspace_type="project",
                local_path="/home/user/project",
                tracker_project="PROJ-123",
                tags=["important", "active"],
            )

        assert result == 0
        captured = capsys.readouterr()
        assert "Linked to:" in captured.out
        assert "Tracker project:" in captured.out

    def test_create_workspace_validation_error(self, capsys):
        """Test handling of validation errors."""
        mock_manager = Mock()
        mock_manager.create.side_effect = ValueError("Invalid workspace ID")

        with patch("spectryn.cli.workspace.get_workspace_manager", return_value=mock_manager):
            result = cmd_workspace_create(
                workspace_id="invalid!ws",
                name="Bad Workspace",
            )

        assert result == 1
        captured = capsys.readouterr()
        assert "Invalid workspace ID" in captured.err

    def test_create_workspace_generic_error(self, capsys):
        """Test handling of generic errors."""
        with patch(
            "spectryn.cli.workspace.get_workspace_manager",
            side_effect=Exception("Database error"),
        ):
            result = cmd_workspace_create(
                workspace_id="new-ws",
                name="New Workspace",
            )

        assert result == 1


# =============================================================================
# cmd_workspace_use Tests
# =============================================================================


class TestCmdWorkspaceUse:
    """Tests for cmd_workspace_use command."""

    def test_use_workspace_success(self, capsys):
        """Test successful workspace switch."""
        from spectryn.core.workspace import Workspace, WorkspaceStatus, WorkspaceType

        mock_manager = Mock()
        mock_manager.use.return_value = Workspace(
            id="ws-1",
            tenant_id="test-tenant",
            name="Target Workspace",
            workspace_type=WorkspaceType.PROJECT,
            status=WorkspaceStatus.ACTIVE,
            local_path="/home/user/project",
            tracker_project="PROJ-123",
        )

        with patch("spectryn.cli.workspace.get_workspace_manager", return_value=mock_manager):
            result = cmd_workspace_use("ws-1")

        assert result == 0
        captured = capsys.readouterr()
        assert "Switched to workspace: Target Workspace" in captured.out
        assert "Local path:" in captured.out
        assert "Tracker project:" in captured.out

    def test_use_workspace_not_found(self, capsys):
        """Test handling of workspace not found."""
        mock_manager = Mock()
        mock_manager.use.side_effect = KeyError("ws-not-found")

        with patch("spectryn.cli.workspace.get_workspace_manager", return_value=mock_manager):
            result = cmd_workspace_use("ws-not-found")

        assert result == 1
        captured = capsys.readouterr()
        assert "not found" in captured.err

    def test_use_workspace_runtime_error(self, capsys):
        """Test handling of runtime errors."""
        mock_manager = Mock()
        mock_manager.use.side_effect = RuntimeError("Workspace is archived")

        with patch("spectryn.cli.workspace.get_workspace_manager", return_value=mock_manager):
            result = cmd_workspace_use("ws-archived")

        assert result == 1
        captured = capsys.readouterr()
        assert "archived" in captured.err


# =============================================================================
# cmd_workspace_show Tests
# =============================================================================


class TestCmdWorkspaceShow:
    """Tests for cmd_workspace_show command."""

    def test_show_workspace_by_id(self, capsys):
        """Test showing workspace by ID."""
        from spectryn.core.workspace import Workspace, WorkspaceStatus, WorkspaceType

        ws = Workspace(
            id="ws-1",
            tenant_id="test-tenant",
            name="Test Workspace",
            workspace_type=WorkspaceType.PROJECT,
            status=WorkspaceStatus.ACTIVE,
        )

        mock_manager = Mock()
        mock_manager.get_workspace.return_value = ws
        mock_manager.registry.get_paths.return_value = None

        with patch("spectryn.cli.workspace.get_workspace_manager", return_value=mock_manager):
            result = cmd_workspace_show("ws-1")

        assert result == 0
        captured = capsys.readouterr()
        assert "Test Workspace" in captured.out

    def test_show_current_workspace(self, capsys):
        """Test showing current workspace."""
        from spectryn.core.workspace import Workspace, WorkspaceStatus, WorkspaceType

        ws = Workspace(
            id="current-ws",
            tenant_id="test-tenant",
            name="Current Workspace",
            workspace_type=WorkspaceType.PROJECT,
            status=WorkspaceStatus.ACTIVE,
        )

        mock_manager = Mock()
        mock_manager.current_workspace = ws
        mock_manager.registry.get_paths.return_value = None

        with patch("spectryn.cli.workspace.get_workspace_manager", return_value=mock_manager):
            result = cmd_workspace_show()

        assert result == 0
        captured = capsys.readouterr()
        assert "Current workspace" in captured.out

    def test_show_workspace_not_found(self, capsys):
        """Test handling of workspace not found."""
        mock_manager = Mock()
        mock_manager.get_workspace.return_value = None

        with patch("spectryn.cli.workspace.get_workspace_manager", return_value=mock_manager):
            result = cmd_workspace_show("ws-not-found")

        assert result == 1
        captured = capsys.readouterr()
        assert "not found" in captured.err


# =============================================================================
# cmd_workspace_delete Tests
# =============================================================================


class TestCmdWorkspaceDelete:
    """Tests for cmd_workspace_delete command."""

    def test_delete_workspace_forced(self, capsys):
        """Test forced workspace deletion."""
        from spectryn.core.workspace import Workspace, WorkspaceStatus, WorkspaceType

        ws = Workspace(
            id="ws-to-delete",
            tenant_id="test-tenant",
            name="Delete Me",
            workspace_type=WorkspaceType.PROJECT,
            status=WorkspaceStatus.ACTIVE,
        )

        mock_manager = Mock()
        mock_manager.get_workspace.return_value = ws

        with patch("spectryn.cli.workspace.get_workspace_manager", return_value=mock_manager):
            result = cmd_workspace_delete("ws-to-delete", force=True)

        assert result == 0
        mock_manager.delete_workspace.assert_called_once_with("ws-to-delete", hard_delete=False)
        captured = capsys.readouterr()
        assert "Soft deleted" in captured.out

    def test_delete_workspace_hard(self, capsys):
        """Test hard workspace deletion."""
        from spectryn.core.workspace import Workspace, WorkspaceStatus, WorkspaceType

        ws = Workspace(
            id="ws-to-delete",
            tenant_id="test-tenant",
            name="Delete Me",
            workspace_type=WorkspaceType.PROJECT,
            status=WorkspaceStatus.ACTIVE,
        )

        mock_manager = Mock()
        mock_manager.get_workspace.return_value = ws

        with patch("spectryn.cli.workspace.get_workspace_manager", return_value=mock_manager):
            result = cmd_workspace_delete("ws-to-delete", hard=True, force=True)

        assert result == 0
        mock_manager.delete_workspace.assert_called_once_with("ws-to-delete", hard_delete=True)
        captured = capsys.readouterr()
        assert "Permanently deleted" in captured.out

    def test_delete_workspace_not_found(self, capsys):
        """Test deleting non-existent workspace."""
        mock_manager = Mock()
        mock_manager.get_workspace.return_value = None

        with patch("spectryn.cli.workspace.get_workspace_manager", return_value=mock_manager):
            result = cmd_workspace_delete("ws-not-found", force=True)

        assert result == 1
        captured = capsys.readouterr()
        assert "not found" in captured.err

    def test_delete_default_workspace(self, capsys):
        """Test that default workspace cannot be deleted."""
        from spectryn.core.workspace import (
            DEFAULT_WORKSPACE_ID,
            Workspace,
            WorkspaceStatus,
            WorkspaceType,
        )

        ws = Workspace(
            id=DEFAULT_WORKSPACE_ID,
            tenant_id="test-tenant",
            name="Default",
            workspace_type=WorkspaceType.PROJECT,
            status=WorkspaceStatus.ACTIVE,
        )

        mock_manager = Mock()
        mock_manager.get_workspace.return_value = ws

        with patch("spectryn.cli.workspace.get_workspace_manager", return_value=mock_manager):
            result = cmd_workspace_delete(DEFAULT_WORKSPACE_ID, force=True)

        assert result == 1
        captured = capsys.readouterr()
        assert "Cannot delete the default workspace" in captured.err

    def test_delete_workspace_cancelled(self, capsys):
        """Test workspace deletion cancelled by user."""
        from spectryn.core.workspace import Workspace, WorkspaceStatus, WorkspaceType

        ws = Workspace(
            id="ws-to-delete",
            tenant_id="test-tenant",
            name="Delete Me",
            workspace_type=WorkspaceType.PROJECT,
            status=WorkspaceStatus.ACTIVE,
        )

        mock_manager = Mock()
        mock_manager.get_workspace.return_value = ws

        with patch("spectryn.cli.workspace.get_workspace_manager", return_value=mock_manager):
            with patch("builtins.input", return_value="n"):
                result = cmd_workspace_delete("ws-to-delete")

        assert result == 0
        mock_manager.delete_workspace.assert_not_called()
        captured = capsys.readouterr()
        assert "Cancelled" in captured.out


# =============================================================================
# cmd_workspace_archive Tests
# =============================================================================


class TestCmdWorkspaceArchive:
    """Tests for cmd_workspace_archive command."""

    def test_archive_workspace_success(self, capsys):
        """Test successful workspace archiving."""
        from spectryn.core.workspace import Workspace, WorkspaceStatus, WorkspaceType

        ws = Workspace(
            id="ws-to-archive",
            tenant_id="test-tenant",
            name="Archive Me",
            workspace_type=WorkspaceType.PROJECT,
            status=WorkspaceStatus.ARCHIVED,
        )

        mock_manager = Mock()
        mock_manager.registry.archive.return_value = ws

        with patch("spectryn.cli.workspace.get_workspace_manager", return_value=mock_manager):
            result = cmd_workspace_archive("ws-to-archive")

        assert result == 0
        captured = capsys.readouterr()
        assert "Archived workspace" in captured.out

    def test_archive_workspace_not_found(self, capsys):
        """Test archiving non-existent workspace."""
        mock_manager = Mock()
        mock_manager.registry.archive.side_effect = KeyError("ws-not-found")

        with patch("spectryn.cli.workspace.get_workspace_manager", return_value=mock_manager):
            result = cmd_workspace_archive("ws-not-found")

        assert result == 1

    def test_archive_workspace_already_archived(self, capsys):
        """Test archiving already archived workspace."""
        mock_manager = Mock()
        mock_manager.registry.archive.side_effect = ValueError("Already archived")

        with patch("spectryn.cli.workspace.get_workspace_manager", return_value=mock_manager):
            result = cmd_workspace_archive("ws-archived")

        assert result == 1
        captured = capsys.readouterr()
        assert "Already archived" in captured.err
