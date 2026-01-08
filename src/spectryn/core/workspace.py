"""
Multi-Workspace Support - Manage multiple workspaces within tenants.

This module provides multi-workspace capabilities for Spectra,
allowing users to manage separate workspaces (projects, repos) within
each tenant. Each workspace has isolated:
- Configuration (tracker settings, field mappings)
- State (sync history, issue mappings)
- Cache (tracker metadata)

Key Features:
- Workspace isolation: Separation of data between workspaces
- Tenant integration: Workspaces exist within tenants
- Context switching: Easy switching between workspaces
- Default workspace: Automatic fallback for simple usage
- Linked directories: Associate with local project directories
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import logging
import shutil
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from spectryn.core.tenant import (
    DEFAULT_TENANT_ID,
    TenantManager,
    TenantPaths,
    get_tenant_manager,
)


if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

DEFAULT_WORKSPACE_ID = "default"
WORKSPACE_CONFIG_FILE = "workspace.json"
WORKSPACE_REGISTRY_FILE = "workspaces.json"


# =============================================================================
# Enums
# =============================================================================


class WorkspaceStatus(Enum):
    """Status of a workspace."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"
    DELETED = "deleted"


class WorkspaceType(Enum):
    """Type of workspace based on primary use case."""

    PROJECT = "project"  # General project workspace
    REPOSITORY = "repository"  # Git repository workspace
    EPIC = "epic"  # Single epic workspace
    SPRINT = "sprint"  # Sprint-focused workspace
    SANDBOX = "sandbox"  # Testing/experimentation


# =============================================================================
# Workspace Entity
# =============================================================================


@dataclass
class Workspace:
    """
    Represents a workspace within a tenant.

    A workspace is a logical grouping of work items with:
    - Its own sync state
    - Configuration overrides
    - Local directory association
    - Tracker project mapping

    Attributes:
        id: Unique workspace identifier (slug format)
        name: Human-readable workspace name
        tenant_id: Parent tenant ID
        description: Optional description
        status: Current workspace status
        workspace_type: Type of workspace
        local_path: Associated local directory (optional)
        tracker_project: Associated tracker project key (optional)
        created_at: Timestamp when workspace was created
        updated_at: Timestamp of last update
        metadata: Additional workspace metadata
        tags: Tags for organization
    """

    __slots__ = (
        "created_at",
        "description",
        "id",
        "local_path",
        "metadata",
        "name",
        "status",
        "tags",
        "tenant_id",
        "tracker_project",
        "updated_at",
        "workspace_type",
    )

    id: str
    name: str
    tenant_id: str
    description: str
    status: WorkspaceStatus
    workspace_type: WorkspaceType
    local_path: str | None
    tracker_project: str | None
    created_at: str | None
    updated_at: str | None
    metadata: dict[str, Any]
    tags: list[str]

    def __init__(
        self,
        id: str,
        name: str,
        tenant_id: str = DEFAULT_TENANT_ID,
        description: str = "",
        status: WorkspaceStatus = WorkspaceStatus.ACTIVE,
        workspace_type: WorkspaceType = WorkspaceType.PROJECT,
        local_path: str | None = None,
        tracker_project: str | None = None,
        created_at: str | None = None,
        updated_at: str | None = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> None:
        """Initialize a workspace."""
        self.id = id
        self.name = name
        self.tenant_id = tenant_id
        self.description = description
        self.status = status
        self.workspace_type = workspace_type
        self.local_path = local_path
        self.tracker_project = tracker_project
        self.created_at = created_at or datetime.now().isoformat()
        self.updated_at = updated_at or self.created_at
        self.metadata = metadata or {}
        self.tags = tags or []

    def __eq__(self, other: object) -> bool:
        """Check equality based on ID and tenant."""
        if not isinstance(other, Workspace):
            return NotImplemented
        return self.id == other.id and self.tenant_id == other.tenant_id

    def __hash__(self) -> int:
        """Hash based on ID and tenant."""
        return hash((self.id, self.tenant_id))

    def __repr__(self) -> str:
        """String representation."""
        return f"Workspace(id={self.id!r}, name={self.name!r}, tenant={self.tenant_id!r})"

    def is_active(self) -> bool:
        """Check if workspace is active."""
        return self.status == WorkspaceStatus.ACTIVE

    def is_archived(self) -> bool:
        """Check if workspace is archived."""
        return self.status == WorkspaceStatus.ARCHIVED

    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now().isoformat()

    def to_dict(self) -> dict[str, Any]:
        """Convert workspace to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "tenant_id": self.tenant_id,
            "description": self.description,
            "status": self.status.value,
            "workspace_type": self.workspace_type.value,
            "local_path": self.local_path,
            "tracker_project": self.tracker_project,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Workspace:
        """Create workspace from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            tenant_id=data.get("tenant_id", DEFAULT_TENANT_ID),
            description=data.get("description", ""),
            status=WorkspaceStatus(data.get("status", "active")),
            workspace_type=WorkspaceType(data.get("workspace_type", "project")),
            local_path=data.get("local_path"),
            tracker_project=data.get("tracker_project"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            metadata=data.get("metadata", {}),
            tags=data.get("tags", []),
        )

    @classmethod
    def create_default(cls, tenant_id: str = DEFAULT_TENANT_ID) -> Workspace:
        """Create the default workspace for a tenant."""
        return cls(
            id=DEFAULT_WORKSPACE_ID,
            name="Default",
            tenant_id=tenant_id,
            description="Default workspace for single-project usage",
            status=WorkspaceStatus.ACTIVE,
            workspace_type=WorkspaceType.PROJECT,
        )


# =============================================================================
# Workspace Paths
# =============================================================================


@dataclass(frozen=True)
class WorkspacePaths:
    """
    Path configuration for a workspace.

    Provides standardized paths for all workspace data:
    - config_dir: Workspace-specific configuration
    - state_dir: Sync state files
    - cache_dir: Cache data
    - backup_dir: Backup files
    - markdown_dir: Default markdown location
    """

    tenant_paths: TenantPaths
    workspace_id: str

    @property
    def root(self) -> Path:
        """Root directory for this workspace."""
        if self.workspace_id == DEFAULT_WORKSPACE_ID:
            return self.tenant_paths.root
        return self.tenant_paths.root / "workspaces" / self.workspace_id

    @property
    def config_dir(self) -> Path:
        """Workspace configuration directory."""
        if self.workspace_id == DEFAULT_WORKSPACE_ID:
            return self.tenant_paths.config_dir
        return self.root / "config"

    @property
    def state_dir(self) -> Path:
        """State directory for sync operations."""
        if self.workspace_id == DEFAULT_WORKSPACE_ID:
            return self.tenant_paths.state_dir
        return self.root / "state"

    @property
    def cache_dir(self) -> Path:
        """Cache directory."""
        if self.workspace_id == DEFAULT_WORKSPACE_ID:
            return self.tenant_paths.cache_dir
        return self.root / "cache"

    @property
    def backup_dir(self) -> Path:
        """Backup directory."""
        if self.workspace_id == DEFAULT_WORKSPACE_ID:
            return self.tenant_paths.backup_dir
        return self.root / "backups"

    @property
    def markdown_dir(self) -> Path:
        """Default markdown files directory."""
        return self.root / "markdown"

    @property
    def config_file(self) -> Path:
        """Workspace configuration file."""
        return self.config_dir / "workspace.yaml"

    @property
    def state_file(self) -> Path:
        """Main state file."""
        return self.state_dir / "state.json"

    @property
    def workspace_info_file(self) -> Path:
        """Workspace metadata file."""
        return self.root / WORKSPACE_CONFIG_FILE

    def ensure_dirs(self) -> None:
        """Create all directories if they don't exist."""
        for dir_path in [
            self.root,
            self.config_dir,
            self.state_dir,
            self.cache_dir,
            self.backup_dir,
            self.markdown_dir,
        ]:
            dir_path.mkdir(parents=True, exist_ok=True)

    def exists(self) -> bool:
        """Check if workspace directory exists."""
        return self.root.exists()

    def get_all_dirs(self) -> list[Path]:
        """Get all workspace directories."""
        return [
            self.root,
            self.config_dir,
            self.state_dir,
            self.cache_dir,
            self.backup_dir,
            self.markdown_dir,
        ]


# =============================================================================
# Workspace Context (Thread-safe)
# =============================================================================

# Context variable for current workspace
_current_workspace: contextvars.ContextVar[Workspace | None] = contextvars.ContextVar(
    "current_workspace", default=None
)


def get_current_workspace() -> Workspace | None:
    """Get the current workspace from context."""
    return _current_workspace.get()


def set_current_workspace(workspace: Workspace) -> contextvars.Token[Workspace | None]:
    """Set the current workspace in context."""
    return _current_workspace.set(workspace)


def reset_current_workspace(token: contextvars.Token[Workspace | None]) -> None:
    """Reset the current workspace using a token."""
    _current_workspace.reset(token)


@contextlib.contextmanager
def workspace_context(workspace: Workspace) -> Iterator[Workspace]:
    """
    Context manager for temporarily switching to a workspace.

    Usage:
        with workspace_context(workspace) as ws:
            # Operations run in context of 'workspace'
            pass

    Args:
        workspace: The workspace to activate

    Yields:
        The active workspace
    """
    token = set_current_workspace(workspace)
    try:
        logger.debug(f"Entered workspace context: {workspace.id}")
        yield workspace
    finally:
        reset_current_workspace(token)
        logger.debug(f"Exited workspace context: {workspace.id}")


# =============================================================================
# Workspace Registry
# =============================================================================


class WorkspaceRegistry:
    """
    Registry for managing workspaces within a tenant.

    Provides CRUD operations for workspaces and persists
    workspace metadata to disk.
    """

    def __init__(
        self,
        tenant_paths: TenantPaths,
        tenant_id: str = DEFAULT_TENANT_ID,
    ) -> None:
        """
        Initialize the workspace registry.

        Args:
            tenant_paths: Paths for the parent tenant
            tenant_id: ID of the parent tenant
        """
        self.tenant_paths = tenant_paths
        self.tenant_id = tenant_id
        self._workspaces: dict[str, Workspace] = {}
        self._lock = contextlib.nullcontext()  # Thread safety if needed
        self._load()

    @property
    def registry_file(self) -> Path:
        """Path to the workspaces registry file."""
        return self.tenant_paths.root / WORKSPACE_REGISTRY_FILE

    def _load(self) -> None:
        """Load workspaces from disk."""
        if not self.registry_file.exists():
            # Create default workspace
            default = Workspace.create_default(self.tenant_id)
            self._workspaces[default.id] = default
            self._save()
            return

        try:
            with open(self.registry_file) as f:
                data = json.load(f)

            for ws_data in data.get("workspaces", []):
                workspace = Workspace.from_dict(ws_data)
                self._workspaces[workspace.id] = workspace

            # Ensure default workspace exists
            if DEFAULT_WORKSPACE_ID not in self._workspaces:
                default = Workspace.create_default(self.tenant_id)
                self._workspaces[default.id] = default
                self._save()

            logger.debug(f"Loaded {len(self._workspaces)} workspaces for tenant {self.tenant_id}")

        except Exception as e:
            logger.warning(f"Failed to load workspaces: {e}")
            default = Workspace.create_default(self.tenant_id)
            self._workspaces[default.id] = default

    def _save(self) -> None:
        """Save workspaces to disk."""
        try:
            self.tenant_paths.root.mkdir(parents=True, exist_ok=True)

            data = {
                "version": "1.0",
                "tenant_id": self.tenant_id,
                "workspaces": [ws.to_dict() for ws in self._workspaces.values()],
            }

            with open(self.registry_file, "w") as f:
                json.dump(data, f, indent=2)

            logger.debug(f"Saved {len(self._workspaces)} workspaces")

        except Exception as e:
            logger.error(f"Failed to save workspaces: {e}")
            raise

    def create(
        self,
        id: str,
        name: str,
        description: str = "",
        workspace_type: WorkspaceType = WorkspaceType.PROJECT,
        local_path: str | None = None,
        tracker_project: str | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> Workspace:
        """
        Create a new workspace.

        Args:
            id: Workspace identifier
            name: Human-readable name
            description: Optional description
            workspace_type: Type of workspace
            local_path: Associated local directory
            tracker_project: Associated tracker project
            tags: Tags for organization
            **kwargs: Additional metadata

        Returns:
            The created workspace

        Raises:
            ValueError: If workspace ID already exists
        """
        if id in self._workspaces:
            raise ValueError(f"Workspace '{id}' already exists in tenant '{self.tenant_id}'")

        workspace = Workspace(
            id=id,
            name=name,
            tenant_id=self.tenant_id,
            description=description,
            workspace_type=workspace_type,
            local_path=local_path,
            tracker_project=tracker_project,
            tags=tags,
            metadata=kwargs.get("metadata", {}),
        )

        # Create directories
        paths = self.get_paths(workspace)
        paths.ensure_dirs()

        # Save workspace info
        self._save_workspace_info(workspace, paths)

        # Add to registry
        self._workspaces[id] = workspace
        self._save()

        logger.info(f"Created workspace: {id} in tenant {self.tenant_id}")
        return workspace

    def _save_workspace_info(self, workspace: Workspace, paths: WorkspacePaths) -> None:
        """Save workspace info to its directory."""
        try:
            with open(paths.workspace_info_file, "w") as f:
                json.dump(workspace.to_dict(), f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save workspace info: {e}")

    def get(self, workspace_id: str) -> Workspace | None:
        """Get a workspace by ID."""
        return self._workspaces.get(workspace_id)

    def get_or_default(self) -> Workspace:
        """Get the default workspace."""
        return self._workspaces.get(
            DEFAULT_WORKSPACE_ID,
            Workspace.create_default(self.tenant_id),
        )

    def get_paths(self, workspace: Workspace | str) -> WorkspacePaths:
        """
        Get paths for a workspace.

        Args:
            workspace: Workspace or workspace ID

        Returns:
            WorkspacePaths for the workspace
        """
        workspace_id = workspace if isinstance(workspace, str) else workspace.id

        return WorkspacePaths(
            tenant_paths=self.tenant_paths,
            workspace_id=workspace_id,
        )

    def list_all(
        self,
        include_archived: bool = False,
        workspace_type: WorkspaceType | None = None,
        tag: str | None = None,
    ) -> list[Workspace]:
        """
        List workspaces.

        Args:
            include_archived: Include archived workspaces
            workspace_type: Filter by workspace type
            tag: Filter by tag

        Returns:
            List of workspaces
        """
        result = []

        for workspace in self._workspaces.values():
            # Filter by status
            if not include_archived and workspace.status == WorkspaceStatus.ARCHIVED:
                continue

            # Filter by type
            if workspace_type and workspace.workspace_type != workspace_type:
                continue

            # Filter by tag
            if tag and tag not in workspace.tags:
                continue

            result.append(workspace)

        return sorted(result, key=lambda w: w.name)

    def update(self, workspace: Workspace) -> Workspace:
        """
        Update an existing workspace.

        Args:
            workspace: The workspace to update

        Returns:
            The updated workspace
        """
        if workspace.id not in self._workspaces:
            raise KeyError(f"Workspace '{workspace.id}' not found")

        workspace.touch()
        self._workspaces[workspace.id] = workspace

        # Update workspace info file
        paths = self.get_paths(workspace)
        self._save_workspace_info(workspace, paths)

        self._save()
        return workspace

    def delete(
        self,
        workspace_id: str,
        hard_delete: bool = False,
    ) -> bool:
        """
        Delete a workspace.

        Args:
            workspace_id: Workspace ID to delete
            hard_delete: If True, remove all files

        Returns:
            True if deleted
        """
        if workspace_id == DEFAULT_WORKSPACE_ID:
            raise ValueError("Cannot delete the default workspace")

        if workspace_id not in self._workspaces:
            return False

        workspace = self._workspaces[workspace_id]
        paths = self.get_paths(workspace)

        if hard_delete and paths.exists():
            shutil.rmtree(paths.root)
            logger.info(f"Hard deleted workspace: {workspace_id}")
        else:
            # Soft delete - mark as deleted
            workspace.status = WorkspaceStatus.DELETED
            workspace.touch()
            self._save_workspace_info(workspace, paths)
            logger.info(f"Soft deleted workspace: {workspace_id}")

        del self._workspaces[workspace_id]
        self._save()
        return True

    def archive(self, workspace_id: str) -> Workspace:
        """Archive a workspace."""
        if workspace_id == DEFAULT_WORKSPACE_ID:
            raise ValueError("Cannot archive the default workspace")

        workspace = self._workspaces.get(workspace_id)
        if not workspace:
            raise KeyError(f"Workspace '{workspace_id}' not found")

        workspace.status = WorkspaceStatus.ARCHIVED
        workspace.touch()
        self._save()

        logger.info(f"Archived workspace: {workspace_id}")
        return workspace

    def activate(self, workspace_id: str) -> Workspace:
        """Activate an archived workspace."""
        workspace = self._workspaces.get(workspace_id)
        if not workspace:
            raise KeyError(f"Workspace '{workspace_id}' not found")

        workspace.status = WorkspaceStatus.ACTIVE
        workspace.touch()
        self._save()

        logger.info(f"Activated workspace: {workspace_id}")
        return workspace

    def find_by_local_path(self, local_path: str | Path) -> Workspace | None:
        """Find a workspace by its local path."""
        local_path = str(Path(local_path).resolve())

        for workspace in self._workspaces.values():
            if workspace.local_path and str(Path(workspace.local_path).resolve()) == local_path:
                return workspace

        return None

    def find_by_tracker_project(self, project_key: str) -> list[Workspace]:
        """Find workspaces by tracker project key."""
        return [
            ws
            for ws in self._workspaces.values()
            if ws.tracker_project == project_key and ws.is_active()
        ]

    def add_tag(self, workspace_id: str, tag: str) -> Workspace:
        """Add a tag to a workspace."""
        workspace = self._workspaces.get(workspace_id)
        if not workspace:
            raise KeyError(f"Workspace '{workspace_id}' not found")

        if tag not in workspace.tags:
            workspace.tags.append(tag)
            workspace.touch()
            self._save()

        return workspace

    def remove_tag(self, workspace_id: str, tag: str) -> Workspace:
        """Remove a tag from a workspace."""
        workspace = self._workspaces.get(workspace_id)
        if not workspace:
            raise KeyError(f"Workspace '{workspace_id}' not found")

        if tag in workspace.tags:
            workspace.tags.remove(tag)
            workspace.touch()
            self._save()

        return workspace


# =============================================================================
# Workspace Manager
# =============================================================================


class WorkspaceManager:
    """
    High-level workspace management.

    Provides operations for:
    - Creating and managing workspaces
    - Switching between workspaces
    - Linking workspaces to local directories
    """

    def __init__(
        self,
        tenant_manager: TenantManager | None = None,
        tenant_id: str | None = None,
    ) -> None:
        """
        Initialize the workspace manager.

        Args:
            tenant_manager: Optional tenant manager
            tenant_id: Specific tenant ID (uses current if not specified)
        """
        self._tenant_manager = tenant_manager or get_tenant_manager()
        self._tenant_id = tenant_id
        self._active_workspace: Workspace | None = None
        self._registries: dict[str, WorkspaceRegistry] = {}

    @property
    def tenant_id(self) -> str:
        """Get the current tenant ID."""
        if self._tenant_id:
            return self._tenant_id
        return self._tenant_manager.current_tenant.id

    @property
    def registry(self) -> WorkspaceRegistry:
        """Get the workspace registry for the current tenant."""
        tenant_id = self.tenant_id

        if tenant_id not in self._registries:
            tenant_paths = self._tenant_manager.registry.get_paths(tenant_id)
            self._registries[tenant_id] = WorkspaceRegistry(
                tenant_paths=tenant_paths,
                tenant_id=tenant_id,
            )

        return self._registries[tenant_id]

    @property
    def current_workspace(self) -> Workspace:
        """
        Get the current active workspace.

        Returns the workspace from context if set, otherwise
        the explicitly activated workspace, or the default.
        """
        # Check context first
        ctx_workspace = get_current_workspace()
        if ctx_workspace and ctx_workspace.tenant_id == self.tenant_id:
            return ctx_workspace

        # Check explicitly set active workspace
        if self._active_workspace and self._active_workspace.tenant_id == self.tenant_id:
            return self._active_workspace

        # Fall back to default
        return self.registry.get_or_default()

    @property
    def current_paths(self) -> WorkspacePaths:
        """Get paths for the current workspace."""
        return self.registry.get_paths(self.current_workspace)

    def use(self, workspace_id: str) -> Workspace:
        """
        Activate a workspace for subsequent operations.

        Args:
            workspace_id: Workspace ID to activate

        Returns:
            The activated workspace

        Raises:
            KeyError: If workspace not found
            RuntimeError: If workspace is not active
        """
        workspace = self.registry.get(workspace_id)
        if not workspace:
            raise KeyError(f"Workspace '{workspace_id}' not found")

        if not workspace.is_active():
            raise RuntimeError(
                f"Workspace '{workspace_id}' is {workspace.status.value}. "
                "Only active workspaces can be used."
            )

        self._active_workspace = workspace
        logger.info(f"Switched to workspace: {workspace_id}")
        return workspace

    def use_default(self) -> Workspace:
        """Activate the default workspace."""
        return self.use(DEFAULT_WORKSPACE_ID)

    @contextlib.contextmanager
    def workspace(self, workspace_id: str) -> Iterator[Workspace]:
        """
        Context manager for temporarily using a different workspace.

        Usage:
            with manager.workspace("frontend") as ws:
                # Operations run in context of 'frontend'
                pass

        Args:
            workspace_id: Workspace ID to use

        Yields:
            The workspace
        """
        workspace = self.registry.get(workspace_id)
        if not workspace:
            raise KeyError(f"Workspace '{workspace_id}' not found")

        if not workspace.is_active():
            raise RuntimeError(f"Workspace '{workspace_id}' is {workspace.status.value}")

        # Save the current active workspace
        previous_active = self._active_workspace
        self._active_workspace = workspace

        with workspace_context(workspace) as ws:
            try:
                yield ws
            finally:
                # Restore the previous active workspace
                self._active_workspace = previous_active

    def create(
        self,
        id: str,
        name: str,
        description: str = "",
        workspace_type: WorkspaceType = WorkspaceType.PROJECT,
        local_path: str | None = None,
        tracker_project: str | None = None,
        activate: bool = True,
        **kwargs: Any,
    ) -> Workspace:
        """
        Create a new workspace and optionally activate it.

        Args:
            id: Workspace identifier
            name: Human-readable name
            description: Optional description
            workspace_type: Type of workspace
            local_path: Associated local directory
            tracker_project: Associated tracker project
            activate: Activate the workspace after creation
            **kwargs: Additional arguments

        Returns:
            The created workspace
        """
        workspace = self.registry.create(
            id=id,
            name=name,
            description=description,
            workspace_type=workspace_type,
            local_path=local_path,
            tracker_project=tracker_project,
            **kwargs,
        )

        if activate:
            self._active_workspace = workspace

        return workspace

    def list_workspaces(self, **kwargs: Any) -> list[Workspace]:
        """List all workspaces."""
        return self.registry.list_all(**kwargs)

    def get_workspace(self, workspace_id: str) -> Workspace | None:
        """Get a workspace by ID."""
        return self.registry.get(workspace_id)

    def delete_workspace(self, workspace_id: str, **kwargs: Any) -> bool:
        """Delete a workspace."""
        # If deleting the active workspace, clear it
        if self._active_workspace and self._active_workspace.id == workspace_id:
            self._active_workspace = None
        return self.registry.delete(workspace_id, **kwargs)

    def link_directory(
        self,
        workspace_id: str,
        local_path: str | Path,
    ) -> Workspace:
        """
        Link a workspace to a local directory.

        Args:
            workspace_id: Workspace ID
            local_path: Local directory path

        Returns:
            Updated workspace
        """
        workspace = self.registry.get(workspace_id)
        if not workspace:
            raise KeyError(f"Workspace '{workspace_id}' not found")

        workspace.local_path = str(Path(local_path).resolve())
        return self.registry.update(workspace)

    def unlink_directory(self, workspace_id: str) -> Workspace:
        """Unlink a workspace from its local directory."""
        workspace = self.registry.get(workspace_id)
        if not workspace:
            raise KeyError(f"Workspace '{workspace_id}' not found")

        workspace.local_path = None
        return self.registry.update(workspace)

    def detect_workspace(self, path: str | Path | None = None) -> Workspace | None:
        """
        Detect the workspace for a given path.

        Checks the path hierarchy for an associated workspace.

        Args:
            path: Path to check (defaults to cwd)

        Returns:
            Detected workspace or None
        """
        path = Path.cwd() if path is None else Path(path).resolve()

        # Check exact match first
        workspace = self.registry.find_by_local_path(path)
        if workspace:
            return workspace

        # Check parent directories
        for parent in path.parents:
            workspace = self.registry.find_by_local_path(parent)
            if workspace:
                return workspace

        return None

    def auto_select_workspace(self) -> Workspace:
        """
        Automatically select workspace based on current directory.

        Returns:
            Selected workspace (detected or default)
        """
        detected = self.detect_workspace()
        if detected:
            self._active_workspace = detected
            return detected
        return self.registry.get_or_default()


# =============================================================================
# Workspace State
# =============================================================================


@dataclass
class WorkspaceState:
    """
    Persisted state for a workspace.

    Tracks sync history, active sessions, and workspace metadata.
    """

    workspace_id: str
    tenant_id: str
    last_sync: str | None = None
    sync_count: int = 0
    active_epic_key: str | None = None
    active_markdown_file: str | None = None
    recent_files: list[str] = field(default_factory=list)
    settings: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "workspace_id": self.workspace_id,
            "tenant_id": self.tenant_id,
            "last_sync": self.last_sync,
            "sync_count": self.sync_count,
            "active_epic_key": self.active_epic_key,
            "active_markdown_file": self.active_markdown_file,
            "recent_files": self.recent_files,
            "settings": self.settings,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkspaceState:
        """Create from dictionary."""
        return cls(
            workspace_id=data["workspace_id"],
            tenant_id=data.get("tenant_id", DEFAULT_TENANT_ID),
            last_sync=data.get("last_sync"),
            sync_count=data.get("sync_count", 0),
            active_epic_key=data.get("active_epic_key"),
            active_markdown_file=data.get("active_markdown_file"),
            recent_files=data.get("recent_files", []),
            settings=data.get("settings", {}),
        )


class WorkspaceStateStore:
    """
    Store for workspace state.

    Persists workspace-specific state including sync history.
    """

    def __init__(self, workspace_paths: WorkspacePaths) -> None:
        """Initialize the state store."""
        self.paths = workspace_paths
        self._state: WorkspaceState | None = None

    @property
    def state_file(self) -> Path:
        """Path to the state file."""
        return self.paths.state_dir / "workspace_state.json"

    def load(self) -> WorkspaceState:
        """Load workspace state."""
        if self._state:
            return self._state

        if not self.state_file.exists():
            self._state = WorkspaceState(
                workspace_id=self.paths.workspace_id,
                tenant_id=self.paths.tenant_paths.tenant_id,
            )
            return self._state

        try:
            with open(self.state_file) as f:
                data = json.load(f)
            self._state = WorkspaceState.from_dict(data)
            return self._state
        except Exception as e:
            logger.warning(f"Failed to load workspace state: {e}")
            self._state = WorkspaceState(
                workspace_id=self.paths.workspace_id,
                tenant_id=self.paths.tenant_paths.tenant_id,
            )
            return self._state

    def save(self, state: WorkspaceState | None = None) -> None:
        """Save workspace state."""
        if state:
            self._state = state

        if not self._state:
            return

        try:
            self.paths.state_dir.mkdir(parents=True, exist_ok=True)
            with open(self.state_file, "w") as f:
                json.dump(self._state.to_dict(), f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save workspace state: {e}")
            raise

    def update_sync(self, epic_key: str | None = None) -> None:
        """Update state after a sync."""
        state = self.load()
        state.last_sync = datetime.now().isoformat()
        state.sync_count += 1
        if epic_key:
            state.active_epic_key = epic_key
        self.save()

    def add_recent_file(self, file_path: str, max_recent: int = 10) -> None:
        """Add a file to recent files."""
        state = self.load()

        # Remove if already in list
        if file_path in state.recent_files:
            state.recent_files.remove(file_path)

        # Add to front
        state.recent_files.insert(0, file_path)

        # Trim to max
        state.recent_files = state.recent_files[:max_recent]

        self.save()


# =============================================================================
# Workspace Migrator
# =============================================================================


class WorkspaceMigrator:
    """
    Migrate data between workspaces.

    Supports copying state, cache, and configuration
    from one workspace to another.
    """

    def __init__(self, registry: WorkspaceRegistry) -> None:
        """Initialize the migrator."""
        self.registry = registry

    def copy_workspace(
        self,
        source_id: str,
        target_id: str,
        target_name: str,
        include_state: bool = True,
        include_cache: bool = False,
        include_config: bool = True,
    ) -> Workspace:
        """
        Copy a workspace.

        Args:
            source_id: Source workspace ID
            target_id: Target workspace ID
            target_name: Name for the new workspace
            include_state: Copy sync state
            include_cache: Copy cache data
            include_config: Copy configuration

        Returns:
            The new workspace
        """
        source = self.registry.get(source_id)
        if not source:
            raise KeyError(f"Source workspace '{source_id}' not found")

        # Create target workspace
        target = self.registry.create(
            id=target_id,
            name=target_name,
            description=f"Copied from {source_id}",
            workspace_type=source.workspace_type,
            tags=source.tags.copy(),
        )

        source_paths = self.registry.get_paths(source_id)
        target_paths = self.registry.get_paths(target_id)

        # Copy data
        if include_state and source_paths.state_dir.exists():
            shutil.copytree(
                source_paths.state_dir,
                target_paths.state_dir,
                dirs_exist_ok=True,
            )

        if include_cache and source_paths.cache_dir.exists():
            shutil.copytree(
                source_paths.cache_dir,
                target_paths.cache_dir,
                dirs_exist_ok=True,
            )

        if include_config and source_paths.config_dir.exists():
            shutil.copytree(
                source_paths.config_dir,
                target_paths.config_dir,
                dirs_exist_ok=True,
            )

        logger.info(f"Copied workspace {source_id} to {target_id}")
        return target

    def move_data(
        self,
        source_id: str,
        target_id: str,
        data_type: str = "all",
    ) -> dict[str, int]:
        """
        Move data between workspaces.

        Args:
            source_id: Source workspace ID
            target_id: Target workspace ID
            data_type: Type of data to move (state, cache, config, all)

        Returns:
            Summary of moved items
        """
        source_paths = self.registry.get_paths(source_id)
        target_paths = self.registry.get_paths(target_id)

        moved = {"files": 0, "dirs": 0}

        dirs_to_move: list[tuple[Path, Path]] = []

        if data_type in ("state", "all"):
            dirs_to_move.append((source_paths.state_dir, target_paths.state_dir))

        if data_type in ("cache", "all"):
            dirs_to_move.append((source_paths.cache_dir, target_paths.cache_dir))

        if data_type in ("config", "all"):
            dirs_to_move.append((source_paths.config_dir, target_paths.config_dir))

        for source_dir, target_dir in dirs_to_move:
            if source_dir.exists():
                target_dir.mkdir(parents=True, exist_ok=True)
                for item in source_dir.iterdir():
                    target_item = target_dir / item.name
                    if item.is_file():
                        shutil.move(str(item), str(target_item))
                        moved["files"] += 1
                    elif item.is_dir():
                        shutil.move(str(item), str(target_item))
                        moved["dirs"] += 1

        return moved


# =============================================================================
# Cross-Tenant Workspace Operations
# =============================================================================


class CrossTenantWorkspaceQuery:
    """Query workspaces across all tenants."""

    def __init__(self, tenant_manager: TenantManager | None = None) -> None:
        """Initialize the query."""
        self._tenant_manager = tenant_manager or get_tenant_manager()

    def list_all_workspaces(
        self,
        include_archived: bool = False,
    ) -> list[tuple[str, Workspace]]:
        """
        List all workspaces across all tenants.

        Returns:
            List of (tenant_id, workspace) tuples
        """
        results: list[tuple[str, Workspace]] = []

        for tenant in self._tenant_manager.list_tenants():
            if not tenant.is_active():
                continue

            tenant_paths = self._tenant_manager.registry.get_paths(tenant)
            registry = WorkspaceRegistry(tenant_paths, tenant.id)

            for workspace in registry.list_all(include_archived=include_archived):
                results.append((tenant.id, workspace))

        return results

    def find_by_tracker_project(
        self,
        project_key: str,
    ) -> list[tuple[str, Workspace]]:
        """
        Find workspaces by tracker project across all tenants.

        Returns:
            List of (tenant_id, workspace) tuples
        """
        results: list[tuple[str, Workspace]] = []

        for tenant in self._tenant_manager.list_tenants():
            if not tenant.is_active():
                continue

            tenant_paths = self._tenant_manager.registry.get_paths(tenant)
            registry = WorkspaceRegistry(tenant_paths, tenant.id)

            for workspace in registry.find_by_tracker_project(project_key):
                results.append((tenant.id, workspace))

        return results

    def get_workspace_summary(self) -> dict[str, Any]:
        """
        Get summary of all workspaces.

        Returns:
            Summary dictionary with counts
        """
        summary: dict[str, Any] = {
            "total_workspaces": 0,
            "by_tenant": {},
            "by_type": {},
            "by_status": {},
        }

        for tenant in self._tenant_manager.list_tenants():
            tenant_paths = self._tenant_manager.registry.get_paths(tenant)
            registry = WorkspaceRegistry(tenant_paths, tenant.id)
            workspaces = registry.list_all(include_archived=True)

            summary["total_workspaces"] += len(workspaces)
            summary["by_tenant"][tenant.id] = len(workspaces)

            for workspace in workspaces:
                # By type
                type_name = workspace.workspace_type.value
                summary["by_type"][type_name] = summary["by_type"].get(type_name, 0) + 1

                # By status
                status_name = workspace.status.value
                summary["by_status"][status_name] = summary["by_status"].get(status_name, 0) + 1

        return summary


# =============================================================================
# Global Workspace Manager
# =============================================================================

_global_workspace_manager: WorkspaceManager | None = None
_workspace_manager_lock = contextlib.nullcontext()


def get_workspace_manager() -> WorkspaceManager:
    """Get the global workspace manager instance."""
    global _global_workspace_manager

    if _global_workspace_manager is None:
        _global_workspace_manager = WorkspaceManager()

    return _global_workspace_manager


def set_workspace_manager(manager: WorkspaceManager) -> None:
    """Set the global workspace manager instance."""
    global _global_workspace_manager
    _global_workspace_manager = manager


def reset_workspace_manager() -> None:
    """Reset the global workspace manager."""
    global _global_workspace_manager
    _global_workspace_manager = None


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    # Constants
    "DEFAULT_WORKSPACE_ID",
    "WORKSPACE_CONFIG_FILE",
    "WORKSPACE_REGISTRY_FILE",
    # Cross-tenant
    "CrossTenantWorkspaceQuery",
    # Entities
    "Workspace",
    # Manager
    "WorkspaceManager",
    # Migrator
    "WorkspaceMigrator",
    "WorkspacePaths",
    # Registry
    "WorkspaceRegistry",
    "WorkspaceState",
    # State
    "WorkspaceStateStore",
    # Enums
    "WorkspaceStatus",
    "WorkspaceType",
    # Context
    "get_current_workspace",
    # Global
    "get_workspace_manager",
    "reset_current_workspace",
    "reset_workspace_manager",
    "set_current_workspace",
    "set_workspace_manager",
    "workspace_context",
]
