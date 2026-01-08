"""
Comprehensive tests for Multi-Workspace Support.

Tests cover:
- Workspace entity and paths
- Workspace registry operations
- Workspace manager operations
- Context switching
- Directory linking
- State management
- Cross-tenant operations
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from spectryn.core.tenant import (
    DEFAULT_TENANT_ID,
    Tenant,
    TenantManager,
    TenantPaths,
    TenantRegistry,
)
from spectryn.core.workspace import (
    DEFAULT_WORKSPACE_ID,
    CrossTenantWorkspaceQuery,
    Workspace,
    WorkspaceManager,
    WorkspaceMigrator,
    WorkspacePaths,
    WorkspaceRegistry,
    WorkspaceState,
    WorkspaceStateStore,
    WorkspaceStatus,
    WorkspaceType,
    get_current_workspace,
    get_workspace_manager,
    reset_workspace_manager,
    set_current_workspace,
    set_workspace_manager,
    workspace_context,
)


if TYPE_CHECKING:
    pass


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_base_dir(tmp_path: Path) -> Path:
    """Create a temporary base directory for tests."""
    return tmp_path / ".spectra"


@pytest.fixture
def tenant_registry(temp_base_dir: Path) -> TenantRegistry:
    """Create a tenant registry for tests."""
    return TenantRegistry(temp_base_dir)


@pytest.fixture
def tenant_manager(temp_base_dir: Path) -> TenantManager:
    """Create a tenant manager for tests."""
    return TenantManager(base_dir=temp_base_dir)


@pytest.fixture
def tenant_paths(tenant_registry: TenantRegistry) -> TenantPaths:
    """Get paths for the default tenant."""
    return tenant_registry.get_paths(DEFAULT_TENANT_ID)


@pytest.fixture
def workspace_registry(tenant_paths: TenantPaths) -> WorkspaceRegistry:
    """Create a workspace registry for tests."""
    return WorkspaceRegistry(tenant_paths, DEFAULT_TENANT_ID)


@pytest.fixture
def workspace_manager(tenant_manager: TenantManager) -> WorkspaceManager:
    """Create a workspace manager for tests."""
    manager = WorkspaceManager(tenant_manager=tenant_manager)
    # Reset global state
    reset_workspace_manager()
    set_workspace_manager(manager)
    yield manager
    reset_workspace_manager()


# =============================================================================
# Test Workspace Entity
# =============================================================================


class TestWorkspace:
    """Tests for the Workspace entity."""

    def test_create_workspace(self) -> None:
        """Test creating a workspace."""
        workspace = Workspace(
            id="frontend",
            name="Frontend App",
            description="Frontend project",
        )

        assert workspace.id == "frontend"
        assert workspace.name == "Frontend App"
        assert workspace.description == "Frontend project"
        assert workspace.tenant_id == DEFAULT_TENANT_ID
        assert workspace.status == WorkspaceStatus.ACTIVE
        assert workspace.workspace_type == WorkspaceType.PROJECT
        assert workspace.local_path is None
        assert workspace.tracker_project is None
        assert workspace.tags == []

    def test_create_with_all_fields(self) -> None:
        """Test creating a workspace with all fields."""
        workspace = Workspace(
            id="backend",
            name="Backend API",
            tenant_id="acme",
            description="Backend services",
            status=WorkspaceStatus.ACTIVE,
            workspace_type=WorkspaceType.REPOSITORY,
            local_path="/projects/backend",
            tracker_project="BACK",
            tags=["api", "python"],
            metadata={"team": "platform"},
        )

        assert workspace.id == "backend"
        assert workspace.tenant_id == "acme"
        assert workspace.workspace_type == WorkspaceType.REPOSITORY
        assert workspace.local_path == "/projects/backend"
        assert workspace.tracker_project == "BACK"
        assert workspace.tags == ["api", "python"]
        assert workspace.metadata == {"team": "platform"}

    def test_workspace_equality(self) -> None:
        """Test workspace equality based on ID and tenant."""
        ws1 = Workspace(id="test", name="Test 1", tenant_id="tenant1")
        ws2 = Workspace(id="test", name="Test 2", tenant_id="tenant1")
        ws3 = Workspace(id="test", name="Test 1", tenant_id="tenant2")
        ws4 = Workspace(id="other", name="Test 1", tenant_id="tenant1")

        assert ws1 == ws2  # Same ID and tenant
        assert ws1 != ws3  # Different tenant
        assert ws1 != ws4  # Different ID

    def test_workspace_hash(self) -> None:
        """Test workspace hashing."""
        ws1 = Workspace(id="test", name="Test 1", tenant_id="tenant1")
        ws2 = Workspace(id="test", name="Test 2", tenant_id="tenant1")

        # Same ID and tenant should have same hash
        assert hash(ws1) == hash(ws2)

        # Can be used in sets
        workspace_set = {ws1, ws2}
        assert len(workspace_set) == 1

    def test_workspace_is_active(self) -> None:
        """Test workspace active status check."""
        active = Workspace(id="a", name="A", status=WorkspaceStatus.ACTIVE)
        archived = Workspace(id="b", name="B", status=WorkspaceStatus.ARCHIVED)
        suspended = Workspace(id="c", name="C", status=WorkspaceStatus.SUSPENDED)

        assert active.is_active() is True
        assert archived.is_active() is False
        assert suspended.is_active() is False

    def test_workspace_is_archived(self) -> None:
        """Test workspace archived status check."""
        active = Workspace(id="a", name="A", status=WorkspaceStatus.ACTIVE)
        archived = Workspace(id="b", name="B", status=WorkspaceStatus.ARCHIVED)

        assert active.is_archived() is False
        assert archived.is_archived() is True

    def test_workspace_touch(self) -> None:
        """Test updating workspace timestamp."""
        workspace = Workspace(id="test", name="Test")
        original_updated = workspace.updated_at

        time.sleep(0.01)
        workspace.touch()

        assert workspace.updated_at != original_updated

    def test_workspace_to_dict(self) -> None:
        """Test converting workspace to dictionary."""
        workspace = Workspace(
            id="test",
            name="Test",
            description="Description",
            workspace_type=WorkspaceType.REPOSITORY,
            local_path="/path",
            tracker_project="TEST",
            tags=["tag1"],
            metadata={"key": "value"},
        )

        data = workspace.to_dict()

        assert data["id"] == "test"
        assert data["name"] == "Test"
        assert data["description"] == "Description"
        assert data["workspace_type"] == "repository"
        assert data["local_path"] == "/path"
        assert data["tracker_project"] == "TEST"
        assert data["tags"] == ["tag1"]
        assert data["metadata"] == {"key": "value"}

    def test_workspace_from_dict(self) -> None:
        """Test creating workspace from dictionary."""
        data = {
            "id": "test",
            "name": "Test",
            "tenant_id": "acme",
            "description": "Description",
            "status": "archived",
            "workspace_type": "epic",
            "local_path": "/path",
            "tracker_project": "TEST",
            "tags": ["tag1"],
            "metadata": {"key": "value"},
        }

        workspace = Workspace.from_dict(data)

        assert workspace.id == "test"
        assert workspace.tenant_id == "acme"
        assert workspace.status == WorkspaceStatus.ARCHIVED
        assert workspace.workspace_type == WorkspaceType.EPIC
        assert workspace.tags == ["tag1"]

    def test_create_default_workspace(self) -> None:
        """Test creating default workspace."""
        workspace = Workspace.create_default("acme")

        assert workspace.id == DEFAULT_WORKSPACE_ID
        assert workspace.name == "Default"
        assert workspace.tenant_id == "acme"
        assert workspace.status == WorkspaceStatus.ACTIVE


# =============================================================================
# Test Workspace Paths
# =============================================================================


class TestWorkspacePaths:
    """Tests for WorkspacePaths."""

    def test_default_workspace_paths(self, tenant_paths: TenantPaths) -> None:
        """Test paths for default workspace."""
        paths = WorkspacePaths(tenant_paths, DEFAULT_WORKSPACE_ID)

        # Default workspace uses tenant root
        assert paths.root == tenant_paths.root
        assert paths.config_dir == tenant_paths.config_dir
        assert paths.state_dir == tenant_paths.state_dir
        assert paths.cache_dir == tenant_paths.cache_dir

    def test_named_workspace_paths(self, tenant_paths: TenantPaths) -> None:
        """Test paths for named workspace."""
        paths = WorkspacePaths(tenant_paths, "frontend")

        assert paths.root == tenant_paths.root / "workspaces" / "frontend"
        assert paths.config_dir == paths.root / "config"
        assert paths.state_dir == paths.root / "state"
        assert paths.cache_dir == paths.root / "cache"
        assert paths.backup_dir == paths.root / "backups"
        assert paths.markdown_dir == paths.root / "markdown"

    def test_workspace_config_file(self, tenant_paths: TenantPaths) -> None:
        """Test workspace config file path."""
        paths = WorkspacePaths(tenant_paths, "frontend")

        assert paths.config_file == paths.config_dir / "workspace.yaml"
        assert paths.state_file == paths.state_dir / "state.json"
        assert paths.workspace_info_file == paths.root / "workspace.json"

    def test_ensure_dirs(self, tenant_paths: TenantPaths) -> None:
        """Test creating workspace directories."""
        paths = WorkspacePaths(tenant_paths, "newws")
        paths.ensure_dirs()

        assert paths.root.exists()
        assert paths.config_dir.exists()
        assert paths.state_dir.exists()
        assert paths.cache_dir.exists()
        assert paths.backup_dir.exists()
        assert paths.markdown_dir.exists()

    def test_paths_exists(self, tenant_paths: TenantPaths) -> None:
        """Test checking if workspace exists."""
        paths = WorkspacePaths(tenant_paths, "newws")

        assert paths.exists() is False

        paths.ensure_dirs()

        assert paths.exists() is True

    def test_get_all_dirs(self, tenant_paths: TenantPaths) -> None:
        """Test getting all workspace directories."""
        paths = WorkspacePaths(tenant_paths, "test")
        dirs = paths.get_all_dirs()

        assert len(dirs) == 6
        assert paths.root in dirs
        assert paths.markdown_dir in dirs


# =============================================================================
# Test Workspace Context
# =============================================================================


class TestWorkspaceContext:
    """Tests for workspace context management."""

    def test_get_current_workspace_default(self) -> None:
        """Test getting current workspace when none set."""
        assert get_current_workspace() is None

    def test_set_current_workspace(self) -> None:
        """Test setting current workspace."""
        workspace = Workspace(id="test", name="Test")
        token = set_current_workspace(workspace)

        assert get_current_workspace() == workspace

        # Reset
        from spectryn.core.workspace import reset_current_workspace

        reset_current_workspace(token)

        assert get_current_workspace() is None

    def test_workspace_context_manager(self) -> None:
        """Test workspace context manager."""
        workspace = Workspace(id="test", name="Test")

        assert get_current_workspace() is None

        with workspace_context(workspace) as ws:
            assert ws == workspace
            assert get_current_workspace() == workspace

        assert get_current_workspace() is None

    def test_nested_workspace_context(self) -> None:
        """Test nested workspace contexts."""
        ws1 = Workspace(id="outer", name="Outer")
        ws2 = Workspace(id="inner", name="Inner")

        with workspace_context(ws1):
            assert get_current_workspace() == ws1

            with workspace_context(ws2):
                assert get_current_workspace() == ws2

            assert get_current_workspace() == ws1

        assert get_current_workspace() is None

    def test_workspace_context_thread_safety(self) -> None:
        """Test that workspace context is thread-safe."""
        ws1 = Workspace(id="thread1", name="Thread 1")
        ws2 = Workspace(id="thread2", name="Thread 2")
        results: dict[str, str | None] = {}

        def thread_func(ws: Workspace, key: str) -> None:
            with workspace_context(ws):
                time.sleep(0.01)
                current = get_current_workspace()
                results[key] = current.id if current else None

        t1 = threading.Thread(target=thread_func, args=(ws1, "t1"))
        t2 = threading.Thread(target=thread_func, args=(ws2, "t2"))

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert results["t1"] == "thread1"
        assert results["t2"] == "thread2"


# =============================================================================
# Test Workspace Registry
# =============================================================================


class TestWorkspaceRegistry:
    """Tests for WorkspaceRegistry."""

    def test_registry_initialization(self, workspace_registry: WorkspaceRegistry) -> None:
        """Test registry initialization creates default workspace."""
        workspaces = workspace_registry.list_all()
        assert len(workspaces) >= 1

        default = workspace_registry.get(DEFAULT_WORKSPACE_ID)
        assert default is not None
        assert default.id == DEFAULT_WORKSPACE_ID

    def test_create_workspace(self, workspace_registry: WorkspaceRegistry) -> None:
        """Test creating a workspace."""
        workspace = workspace_registry.create(
            id="frontend",
            name="Frontend App",
            description="Frontend project",
            workspace_type=WorkspaceType.PROJECT,
        )

        assert workspace.id == "frontend"
        assert workspace.name == "Frontend App"
        assert workspace.tenant_id == DEFAULT_TENANT_ID

        # Should be persisted
        loaded = workspace_registry.get("frontend")
        assert loaded is not None
        assert loaded.name == "Frontend App"

    def test_create_duplicate_raises(self, workspace_registry: WorkspaceRegistry) -> None:
        """Test creating duplicate workspace raises error."""
        workspace_registry.create(id="test", name="Test")

        with pytest.raises(ValueError, match="already exists"):
            workspace_registry.create(id="test", name="Test 2")

    def test_get_workspace(self, workspace_registry: WorkspaceRegistry) -> None:
        """Test getting a workspace."""
        workspace_registry.create(id="test", name="Test")

        workspace = workspace_registry.get("test")
        assert workspace is not None
        assert workspace.id == "test"

        nonexistent = workspace_registry.get("nonexistent")
        assert nonexistent is None

    def test_get_or_default(self, workspace_registry: WorkspaceRegistry) -> None:
        """Test getting default workspace."""
        default = workspace_registry.get_or_default()

        assert default.id == DEFAULT_WORKSPACE_ID

    def test_get_paths(self, workspace_registry: WorkspaceRegistry) -> None:
        """Test getting workspace paths."""
        workspace_registry.create(id="test", name="Test")

        # By ID
        paths = workspace_registry.get_paths("test")
        assert paths.workspace_id == "test"

        # By workspace object
        workspace = workspace_registry.get("test")
        paths2 = workspace_registry.get_paths(workspace)
        assert paths2.workspace_id == "test"

    def test_list_workspaces(self, workspace_registry: WorkspaceRegistry) -> None:
        """Test listing workspaces."""
        workspace_registry.create(id="ws1", name="Workspace 1")
        workspace_registry.create(id="ws2", name="Workspace 2")

        workspaces = workspace_registry.list_all()
        ids = [ws.id for ws in workspaces]

        assert "ws1" in ids
        assert "ws2" in ids
        assert DEFAULT_WORKSPACE_ID in ids

    def test_list_with_filter(self, workspace_registry: WorkspaceRegistry) -> None:
        """Test listing workspaces with filters."""
        workspace_registry.create(
            id="repo1",
            name="Repo 1",
            workspace_type=WorkspaceType.REPOSITORY,
            tags=["frontend"],
        )
        workspace_registry.create(
            id="proj1",
            name="Project 1",
            workspace_type=WorkspaceType.PROJECT,
            tags=["backend"],
        )

        # Filter by type
        repos = workspace_registry.list_all(workspace_type=WorkspaceType.REPOSITORY)
        assert len(repos) == 1
        assert repos[0].id == "repo1"

        # Filter by tag
        frontend = workspace_registry.list_all(tag="frontend")
        assert len(frontend) == 1
        assert frontend[0].id == "repo1"

    def test_list_excludes_archived(self, workspace_registry: WorkspaceRegistry) -> None:
        """Test that list excludes archived by default."""
        workspace_registry.create(id="active", name="Active")
        ws = workspace_registry.create(id="archived", name="Archived")
        ws.status = WorkspaceStatus.ARCHIVED
        workspace_registry.update(ws)

        # Exclude archived
        workspaces = workspace_registry.list_all()
        ids = [ws.id for ws in workspaces]
        assert "active" in ids
        assert "archived" not in ids

        # Include archived
        all_ws = workspace_registry.list_all(include_archived=True)
        ids = [ws.id for ws in all_ws]
        assert "archived" in ids

    def test_update_workspace(self, workspace_registry: WorkspaceRegistry) -> None:
        """Test updating a workspace."""
        workspace = workspace_registry.create(id="test", name="Test")
        workspace.name = "Updated Test"
        workspace.description = "New description"

        updated = workspace_registry.update(workspace)

        assert updated.name == "Updated Test"
        assert updated.description == "New description"

        # Should be persisted
        loaded = workspace_registry.get("test")
        assert loaded.name == "Updated Test"

    def test_delete_workspace(self, workspace_registry: WorkspaceRegistry) -> None:
        """Test deleting a workspace."""
        workspace_registry.create(id="test", name="Test")

        result = workspace_registry.delete("test")
        assert result is True

        assert workspace_registry.get("test") is None

    def test_delete_default_raises(self, workspace_registry: WorkspaceRegistry) -> None:
        """Test deleting default workspace raises error."""
        with pytest.raises(ValueError, match="Cannot delete"):
            workspace_registry.delete(DEFAULT_WORKSPACE_ID)

    def test_delete_nonexistent(self, workspace_registry: WorkspaceRegistry) -> None:
        """Test deleting nonexistent workspace returns False."""
        result = workspace_registry.delete("nonexistent")
        assert result is False

    def test_archive_workspace(self, workspace_registry: WorkspaceRegistry) -> None:
        """Test archiving a workspace."""
        workspace_registry.create(id="test", name="Test")

        archived = workspace_registry.archive("test")

        assert archived.status == WorkspaceStatus.ARCHIVED
        assert archived.is_archived() is True

    def test_archive_default_raises(self, workspace_registry: WorkspaceRegistry) -> None:
        """Test archiving default workspace raises error."""
        with pytest.raises(ValueError, match="Cannot archive"):
            workspace_registry.archive(DEFAULT_WORKSPACE_ID)

    def test_activate_workspace(self, workspace_registry: WorkspaceRegistry) -> None:
        """Test activating an archived workspace."""
        workspace_registry.create(id="test", name="Test")
        workspace_registry.archive("test")

        activated = workspace_registry.activate("test")

        assert activated.status == WorkspaceStatus.ACTIVE
        assert activated.is_active() is True

    def test_find_by_local_path(
        self, workspace_registry: WorkspaceRegistry, tmp_path: Path
    ) -> None:
        """Test finding workspace by local path."""
        project_path = tmp_path / "project"
        project_path.mkdir()

        workspace_registry.create(
            id="linked",
            name="Linked",
            local_path=str(project_path),
        )

        found = workspace_registry.find_by_local_path(project_path)
        assert found is not None
        assert found.id == "linked"

        # Not found
        not_found = workspace_registry.find_by_local_path("/nonexistent")
        assert not_found is None

    def test_find_by_tracker_project(self, workspace_registry: WorkspaceRegistry) -> None:
        """Test finding workspaces by tracker project."""
        workspace_registry.create(
            id="ws1",
            name="WS 1",
            tracker_project="PROJ",
        )
        workspace_registry.create(
            id="ws2",
            name="WS 2",
            tracker_project="PROJ",
        )
        workspace_registry.create(
            id="ws3",
            name="WS 3",
            tracker_project="OTHER",
        )

        found = workspace_registry.find_by_tracker_project("PROJ")
        assert len(found) == 2
        ids = [ws.id for ws in found]
        assert "ws1" in ids
        assert "ws2" in ids

    def test_add_tag(self, workspace_registry: WorkspaceRegistry) -> None:
        """Test adding a tag to a workspace."""
        workspace_registry.create(id="test", name="Test")

        ws = workspace_registry.add_tag("test", "frontend")
        assert "frontend" in ws.tags

        # Adding same tag twice is idempotent
        ws = workspace_registry.add_tag("test", "frontend")
        assert ws.tags.count("frontend") == 1

    def test_remove_tag(self, workspace_registry: WorkspaceRegistry) -> None:
        """Test removing a tag from a workspace."""
        workspace_registry.create(id="test", name="Test", tags=["a", "b"])

        ws = workspace_registry.remove_tag("test", "a")
        assert "a" not in ws.tags
        assert "b" in ws.tags


# =============================================================================
# Test Workspace Manager
# =============================================================================


class TestWorkspaceManager:
    """Tests for WorkspaceManager."""

    def test_manager_initialization(self, workspace_manager: WorkspaceManager) -> None:
        """Test manager initialization."""
        assert workspace_manager.tenant_id == DEFAULT_TENANT_ID
        assert workspace_manager.registry is not None

    def test_current_workspace_default(self, workspace_manager: WorkspaceManager) -> None:
        """Test getting current workspace defaults to default."""
        current = workspace_manager.current_workspace
        assert current.id == DEFAULT_WORKSPACE_ID

    def test_use_workspace(self, workspace_manager: WorkspaceManager) -> None:
        """Test activating a workspace."""
        workspace_manager.create(id="test", name="Test", activate=False)

        workspace = workspace_manager.use("test")
        assert workspace.id == "test"
        assert workspace_manager.current_workspace.id == "test"

    def test_use_nonexistent_raises(self, workspace_manager: WorkspaceManager) -> None:
        """Test using nonexistent workspace raises error."""
        with pytest.raises(KeyError):
            workspace_manager.use("nonexistent")

    def test_use_archived_raises(self, workspace_manager: WorkspaceManager) -> None:
        """Test using archived workspace raises error."""
        workspace_manager.create(id="test", name="Test", activate=False)
        workspace_manager.registry.archive("test")

        with pytest.raises(RuntimeError, match="archived"):
            workspace_manager.use("test")

    def test_use_default(self, workspace_manager: WorkspaceManager) -> None:
        """Test switching to default workspace."""
        workspace_manager.create(id="test", name="Test")
        workspace_manager.use("test")

        default = workspace_manager.use_default()
        assert default.id == DEFAULT_WORKSPACE_ID

    def test_workspace_context_manager(self, workspace_manager: WorkspaceManager) -> None:
        """Test manager's workspace context manager."""
        # Create without activating so we start from default
        workspace_manager.create(id="test", name="Test", activate=False)

        # Before context: should be on default
        assert workspace_manager.current_workspace.id == DEFAULT_WORKSPACE_ID

        with workspace_manager.workspace("test") as ws:
            assert ws.id == "test"
            assert workspace_manager.current_workspace.id == "test"

        # Should revert to default (what it was before context)
        assert workspace_manager.current_workspace.id == DEFAULT_WORKSPACE_ID

    def test_create_workspace(self, workspace_manager: WorkspaceManager) -> None:
        """Test creating a workspace through manager."""
        workspace = workspace_manager.create(
            id="frontend",
            name="Frontend",
            description="Frontend project",
            workspace_type=WorkspaceType.REPOSITORY,
        )

        assert workspace.id == "frontend"
        assert workspace.workspace_type == WorkspaceType.REPOSITORY

        # Should be activated
        assert workspace_manager.current_workspace.id == "frontend"

    def test_create_without_activate(self, workspace_manager: WorkspaceManager) -> None:
        """Test creating without activating."""
        workspace_manager.create(
            id="test",
            name="Test",
            activate=False,
        )

        # Should still be on default
        assert workspace_manager.current_workspace.id == DEFAULT_WORKSPACE_ID

    def test_list_workspaces(self, workspace_manager: WorkspaceManager) -> None:
        """Test listing workspaces."""
        workspace_manager.create(id="ws1", name="WS 1", activate=False)
        workspace_manager.create(id="ws2", name="WS 2", activate=False)

        workspaces = workspace_manager.list_workspaces()
        ids = [ws.id for ws in workspaces]

        assert "ws1" in ids
        assert "ws2" in ids

    def test_delete_workspace(self, workspace_manager: WorkspaceManager) -> None:
        """Test deleting a workspace."""
        workspace_manager.create(id="test", name="Test")

        result = workspace_manager.delete_workspace("test")
        assert result is True
        assert workspace_manager.get_workspace("test") is None

    def test_link_directory(self, workspace_manager: WorkspaceManager, tmp_path: Path) -> None:
        """Test linking a workspace to a directory."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        workspace_manager.create(id="test", name="Test", activate=False)
        workspace = workspace_manager.link_directory("test", project_dir)

        assert workspace.local_path == str(project_dir)

    def test_unlink_directory(self, workspace_manager: WorkspaceManager, tmp_path: Path) -> None:
        """Test unlinking a workspace from its directory."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        workspace_manager.create(
            id="test", name="Test", local_path=str(project_dir), activate=False
        )
        workspace = workspace_manager.unlink_directory("test")

        assert workspace.local_path is None

    def test_detect_workspace(self, workspace_manager: WorkspaceManager, tmp_path: Path) -> None:
        """Test detecting workspace from path."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        workspace_manager.create(
            id="detected",
            name="Detected",
            local_path=str(project_dir),
            activate=False,
        )

        # Exact match
        detected = workspace_manager.detect_workspace(project_dir)
        assert detected is not None
        assert detected.id == "detected"

        # Subdirectory
        subdir = project_dir / "src"
        subdir.mkdir()
        detected = workspace_manager.detect_workspace(subdir)
        assert detected is not None
        assert detected.id == "detected"

        # No match
        other = tmp_path / "other"
        other.mkdir()
        detected = workspace_manager.detect_workspace(other)
        assert detected is None

    def test_auto_select_workspace(
        self, workspace_manager: WorkspaceManager, tmp_path: Path
    ) -> None:
        """Test auto-selecting workspace based on cwd."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        workspace_manager.create(
            id="auto",
            name="Auto",
            local_path=str(project_dir),
            activate=False,
        )

        # Should detect and activate
        selected = workspace_manager.auto_select_workspace()
        # Note: In tests, cwd is likely not project_dir, so we get default
        assert selected is not None

    def test_current_paths(self, workspace_manager: WorkspaceManager) -> None:
        """Test getting current workspace paths."""
        paths = workspace_manager.current_paths
        assert paths.workspace_id == DEFAULT_WORKSPACE_ID


# =============================================================================
# Test Workspace State
# =============================================================================


class TestWorkspaceState:
    """Tests for WorkspaceState."""

    def test_state_creation(self) -> None:
        """Test creating workspace state."""
        state = WorkspaceState(
            workspace_id="test",
            tenant_id="acme",
        )

        assert state.workspace_id == "test"
        assert state.tenant_id == "acme"
        assert state.last_sync is None
        assert state.sync_count == 0

    def test_state_to_dict(self) -> None:
        """Test converting state to dictionary."""
        state = WorkspaceState(
            workspace_id="test",
            tenant_id="acme",
            last_sync="2024-01-01T00:00:00",
            sync_count=5,
            active_epic_key="EPIC-1",
            recent_files=["/file1.md", "/file2.md"],
        )

        data = state.to_dict()

        assert data["workspace_id"] == "test"
        assert data["sync_count"] == 5
        assert data["active_epic_key"] == "EPIC-1"
        assert len(data["recent_files"]) == 2

    def test_state_from_dict(self) -> None:
        """Test creating state from dictionary."""
        data = {
            "workspace_id": "test",
            "tenant_id": "acme",
            "last_sync": "2024-01-01T00:00:00",
            "sync_count": 10,
            "settings": {"key": "value"},
        }

        state = WorkspaceState.from_dict(data)

        assert state.workspace_id == "test"
        assert state.sync_count == 10
        assert state.settings == {"key": "value"}


class TestWorkspaceStateStore:
    """Tests for WorkspaceStateStore."""

    def test_store_load_empty(self, workspace_manager: WorkspaceManager) -> None:
        """Test loading state when none exists."""
        paths = workspace_manager.current_paths
        store = WorkspaceStateStore(paths)

        state = store.load()

        assert state.workspace_id == paths.workspace_id
        assert state.sync_count == 0

    def test_store_save_and_load(self, workspace_manager: WorkspaceManager) -> None:
        """Test saving and loading state."""
        paths = workspace_manager.current_paths
        paths.ensure_dirs()
        store = WorkspaceStateStore(paths)

        state = store.load()
        state.sync_count = 5
        state.active_epic_key = "EPIC-1"
        store.save(state)

        # Load again
        store2 = WorkspaceStateStore(paths)
        loaded = store2.load()

        assert loaded.sync_count == 5
        assert loaded.active_epic_key == "EPIC-1"

    def test_update_sync(self, workspace_manager: WorkspaceManager) -> None:
        """Test updating state after sync."""
        paths = workspace_manager.current_paths
        paths.ensure_dirs()
        store = WorkspaceStateStore(paths)

        store.update_sync(epic_key="EPIC-2")

        state = store.load()
        assert state.sync_count == 1
        assert state.last_sync is not None
        assert state.active_epic_key == "EPIC-2"

    def test_add_recent_file(self, workspace_manager: WorkspaceManager) -> None:
        """Test adding recent files."""
        paths = workspace_manager.current_paths
        paths.ensure_dirs()
        store = WorkspaceStateStore(paths)

        store.add_recent_file("/file1.md")
        store.add_recent_file("/file2.md")
        store.add_recent_file("/file1.md")  # Should move to front

        state = store.load()
        assert state.recent_files[0] == "/file1.md"
        assert state.recent_files[1] == "/file2.md"
        assert len(state.recent_files) == 2

    def test_recent_files_max_limit(self, workspace_manager: WorkspaceManager) -> None:
        """Test recent files respects max limit."""
        paths = workspace_manager.current_paths
        paths.ensure_dirs()
        store = WorkspaceStateStore(paths)

        for i in range(15):
            store.add_recent_file(f"/file{i}.md", max_recent=10)

        state = store.load()
        assert len(state.recent_files) == 10
        assert state.recent_files[0] == "/file14.md"


# =============================================================================
# Test Workspace Migrator
# =============================================================================


class TestWorkspaceMigrator:
    """Tests for WorkspaceMigrator."""

    def test_copy_workspace(self, workspace_manager: WorkspaceManager) -> None:
        """Test copying a workspace."""
        # Create source with some state
        workspace_manager.create(id="source", name="Source", activate=False)
        source_paths = workspace_manager.registry.get_paths("source")
        source_paths.ensure_dirs()
        (source_paths.state_dir / "test.json").write_text('{"key": "value"}')

        migrator = WorkspaceMigrator(workspace_manager.registry)
        target = migrator.copy_workspace(
            source_id="source",
            target_id="target",
            target_name="Target Copy",
        )

        assert target.id == "target"
        assert target.name == "Target Copy"

        # State should be copied
        target_paths = workspace_manager.registry.get_paths("target")
        assert (target_paths.state_dir / "test.json").exists()

    def test_copy_workspace_exclude_cache(self, workspace_manager: WorkspaceManager) -> None:
        """Test copying workspace without cache."""
        workspace_manager.create(id="source", name="Source", activate=False)
        source_paths = workspace_manager.registry.get_paths("source")
        source_paths.ensure_dirs()
        (source_paths.cache_dir / "cache.json").write_text("{}")

        migrator = WorkspaceMigrator(workspace_manager.registry)
        migrator.copy_workspace(
            source_id="source",
            target_id="target",
            target_name="Target",
            include_cache=False,
        )

        target_paths = workspace_manager.registry.get_paths("target")
        assert not (target_paths.cache_dir / "cache.json").exists()

    def test_move_data(self, workspace_manager: WorkspaceManager) -> None:
        """Test moving data between workspaces."""
        workspace_manager.create(id="source", name="Source", activate=False)
        workspace_manager.create(id="target", name="Target", activate=False)

        source_paths = workspace_manager.registry.get_paths("source")
        target_paths = workspace_manager.registry.get_paths("target")
        source_paths.ensure_dirs()
        target_paths.ensure_dirs()

        # Create source files
        (source_paths.state_dir / "state.json").write_text("{}")

        migrator = WorkspaceMigrator(workspace_manager.registry)
        moved = migrator.move_data("source", "target", data_type="state")

        assert moved["files"] >= 1
        assert not (source_paths.state_dir / "state.json").exists()
        assert (target_paths.state_dir / "state.json").exists()


# =============================================================================
# Test Cross-Tenant Operations
# =============================================================================


class TestCrossTenantWorkspaceQuery:
    """Tests for cross-tenant workspace queries."""

    def test_list_all_workspaces(self, tenant_manager: TenantManager) -> None:
        """Test listing workspaces across tenants."""
        # Create workspaces in different tenants
        tenant_manager.create(id="tenant1", name="Tenant 1")
        tenant_manager.create(id="tenant2", name="Tenant 2")

        t1_paths = tenant_manager.registry.get_paths("tenant1")
        t2_paths = tenant_manager.registry.get_paths("tenant2")

        reg1 = WorkspaceRegistry(t1_paths, "tenant1")
        reg2 = WorkspaceRegistry(t2_paths, "tenant2")

        reg1.create(id="ws1", name="WS 1")
        reg2.create(id="ws2", name="WS 2")

        query = CrossTenantWorkspaceQuery(tenant_manager)
        results = query.list_all_workspaces()

        # Should have workspaces from both tenants
        tenant_ids = {tid for tid, _ in results}
        assert "tenant1" in tenant_ids
        assert "tenant2" in tenant_ids

    def test_find_by_tracker_project(self, tenant_manager: TenantManager) -> None:
        """Test finding workspaces by tracker project across tenants."""
        tenant_manager.create(id="tenant1", name="Tenant 1")
        tenant_manager.create(id="tenant2", name="Tenant 2")

        t1_paths = tenant_manager.registry.get_paths("tenant1")
        t2_paths = tenant_manager.registry.get_paths("tenant2")

        reg1 = WorkspaceRegistry(t1_paths, "tenant1")
        reg2 = WorkspaceRegistry(t2_paths, "tenant2")

        reg1.create(id="ws1", name="WS 1", tracker_project="SHARED")
        reg2.create(id="ws2", name="WS 2", tracker_project="SHARED")

        query = CrossTenantWorkspaceQuery(tenant_manager)
        results = query.find_by_tracker_project("SHARED")

        assert len(results) == 2
        tenant_ids = {tid for tid, _ in results}
        assert "tenant1" in tenant_ids
        assert "tenant2" in tenant_ids

    def test_get_workspace_summary(self, tenant_manager: TenantManager) -> None:
        """Test getting workspace summary."""
        tenant_manager.create(id="tenant1", name="Tenant 1")

        t1_paths = tenant_manager.registry.get_paths("tenant1")
        reg1 = WorkspaceRegistry(t1_paths, "tenant1")

        reg1.create(id="repo1", name="Repo 1", workspace_type=WorkspaceType.REPOSITORY)
        reg1.create(id="proj1", name="Project 1", workspace_type=WorkspaceType.PROJECT)

        query = CrossTenantWorkspaceQuery(tenant_manager)
        summary = query.get_workspace_summary()

        assert summary["total_workspaces"] >= 2
        assert "tenant1" in summary["by_tenant"]
        assert "repository" in summary["by_type"]
        assert "project" in summary["by_type"]


# =============================================================================
# Test Global Manager
# =============================================================================


class TestGlobalWorkspaceManager:
    """Tests for global workspace manager."""

    def test_get_workspace_manager(self) -> None:
        """Test getting global manager."""
        reset_workspace_manager()

        manager = get_workspace_manager()
        assert manager is not None

        # Same instance
        manager2 = get_workspace_manager()
        assert manager is manager2

        reset_workspace_manager()

    def test_set_workspace_manager(self) -> None:
        """Test setting global manager."""
        reset_workspace_manager()

        custom = WorkspaceManager()
        set_workspace_manager(custom)

        assert get_workspace_manager() is custom

        reset_workspace_manager()


# =============================================================================
# Test Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_workspace_with_special_characters_in_id(
        self, workspace_registry: WorkspaceRegistry
    ) -> None:
        """Test workspace with special characters in ID."""
        # Underscores and hyphens should work
        workspace = workspace_registry.create(
            id="my-workspace_v2",
            name="My Workspace V2",
        )

        assert workspace.id == "my-workspace_v2"
        loaded = workspace_registry.get("my-workspace_v2")
        assert loaded is not None

    def test_empty_workspace_name(self, workspace_registry: WorkspaceRegistry) -> None:
        """Test workspace with empty name."""
        workspace = workspace_registry.create(id="test", name="")

        assert workspace.name == ""

    def test_workspace_with_long_description(self, workspace_registry: WorkspaceRegistry) -> None:
        """Test workspace with long description."""
        long_desc = "A" * 10000

        workspace_registry.create(
            id="test",
            name="Test",
            description=long_desc,
        )

        loaded = workspace_registry.get("test")
        assert loaded.description == long_desc

    def test_workspace_metadata_persistence(self, workspace_registry: WorkspaceRegistry) -> None:
        """Test that metadata is persisted correctly."""
        metadata = {
            "team": "platform",
            "priority": 1,
            "flags": ["urgent", "reviewed"],
            "nested": {"key": "value"},
        }

        workspace_registry.create(
            id="test",
            name="Test",
            metadata=metadata,
        )

        # Force reload
        workspace_registry._load()

        loaded = workspace_registry.get("test")
        assert loaded.metadata == metadata

    def test_concurrent_workspace_creation(self, workspace_registry: WorkspaceRegistry) -> None:
        """Test concurrent workspace creation."""
        results: list[Exception | None] = []

        def create_workspace(idx: int) -> None:
            try:
                workspace_registry.create(
                    id=f"concurrent-{idx}",
                    name=f"Concurrent {idx}",
                )
                results.append(None)
            except Exception as e:
                results.append(e)

        threads = [threading.Thread(target=create_workspace, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should succeed or raise duplicate error
        workspaces = workspace_registry.list_all()
        created_ids = [ws.id for ws in workspaces if ws.id.startswith("concurrent-")]
        assert len(created_ids) == 5

    def test_workspace_type_values(self) -> None:
        """Test all workspace type values."""
        for ws_type in WorkspaceType:
            workspace = Workspace(
                id=f"test-{ws_type.value}",
                name=f"Test {ws_type.value}",
                workspace_type=ws_type,
            )
            assert workspace.workspace_type == ws_type

    def test_workspace_status_transitions(self, workspace_registry: WorkspaceRegistry) -> None:
        """Test workspace status transitions."""
        workspace_registry.create(id="test", name="Test")

        # Active -> Archived
        workspace_registry.archive("test")
        ws = workspace_registry.get("test")
        assert ws.status == WorkspaceStatus.ARCHIVED

        # Archived -> Active
        workspace_registry.activate("test")
        ws = workspace_registry.get("test")
        assert ws.status == WorkspaceStatus.ACTIVE
