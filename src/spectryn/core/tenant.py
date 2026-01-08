"""
Multi-Tenant Support - Manage multiple organizations.

This module provides comprehensive multi-tenant capabilities for Spectra,
allowing users to manage separate organizations with isolated:
- Configuration (credentials, settings)
- State (sync history, backups)
- Cache (tracker metadata)

Key Features:
- Tenant isolation: Complete separation of data between tenants
- Context switching: Easy switching between tenants
- Default tenant: Automatic fallback for single-org usage
- Migration support: Import existing single-tenant data
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import logging
import shutil
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

DEFAULT_TENANT_ID = "default"
TENANT_CONFIG_FILE = "tenant.json"
TENANT_REGISTRY_FILE = "tenants.json"
DEFAULT_SPECTRA_DIR = Path.home() / ".spectra"


# =============================================================================
# Enums
# =============================================================================


class TenantStatus(Enum):
    """Status of a tenant."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"
    DELETED = "deleted"


class IsolationLevel(Enum):
    """Level of isolation between tenants."""

    FULL = "full"  # Complete isolation (separate directories)
    SHARED_CACHE = "shared_cache"  # Share cache across tenants
    SHARED_CONFIG = "shared_config"  # Share base config (override per-tenant)


# =============================================================================
# Tenant Entity
# =============================================================================


@dataclass
class Tenant:
    """
    Represents a tenant (organization) in the multi-tenant system.

    A tenant is an isolated workspace with its own:
    - Configuration files
    - Sync state
    - Cache data
    - Backup history

    Attributes:
        id: Unique tenant identifier (slug format)
        name: Human-readable tenant name
        description: Optional description
        status: Current tenant status
        created_at: Timestamp when tenant was created
        updated_at: Timestamp of last update
        metadata: Additional tenant metadata
        isolation_level: Level of isolation from other tenants
        base_dir: Base directory for tenant data (None = auto-derived)
    """

    __slots__ = (
        "base_dir",
        "created_at",
        "description",
        "id",
        "isolation_level",
        "metadata",
        "name",
        "status",
        "updated_at",
    )

    id: str
    name: str
    description: str
    status: TenantStatus
    created_at: str
    updated_at: str
    metadata: dict[str, Any]
    isolation_level: IsolationLevel
    base_dir: str | None

    def __init__(
        self,
        id: str,
        name: str,
        description: str = "",
        status: TenantStatus = TenantStatus.ACTIVE,
        created_at: str | None = None,
        updated_at: str | None = None,
        metadata: dict[str, Any] | None = None,
        isolation_level: IsolationLevel = IsolationLevel.FULL,
        base_dir: str | None = None,
    ) -> None:
        """Initialize a tenant."""
        self.id = id
        self.name = name
        self.description = description
        self.status = status
        self.created_at = created_at or datetime.now().isoformat()
        self.updated_at = updated_at or datetime.now().isoformat()
        self.metadata = metadata or {}
        self.isolation_level = isolation_level
        self.base_dir = base_dir

    def __hash__(self) -> int:
        """Hash by tenant ID."""
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        """Equality by tenant ID."""
        if not isinstance(other, Tenant):
            return NotImplemented
        return self.id == other.id

    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now().isoformat()

    def is_active(self) -> bool:
        """Check if tenant is active."""
        return self.status == TenantStatus.ACTIVE

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
            "isolation_level": self.isolation_level.value,
            "base_dir": self.base_dir,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Tenant:
        """Create from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            status=TenantStatus(data.get("status", "active")),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            metadata=data.get("metadata", {}),
            isolation_level=IsolationLevel(data.get("isolation_level", "full")),
            base_dir=data.get("base_dir"),
        )

    @classmethod
    def create_default(cls) -> Tenant:
        """Create the default tenant."""
        return cls(
            id=DEFAULT_TENANT_ID,
            name="Default",
            description="Default tenant for single-organization usage",
            status=TenantStatus.ACTIVE,
            isolation_level=IsolationLevel.FULL,
        )


# =============================================================================
# Tenant Paths
# =============================================================================


@dataclass(frozen=True)
class TenantPaths:
    """
    Path configuration for a tenant.

    Provides standardized paths for all tenant data:
    - config_dir: Configuration files
    - state_dir: Sync state files
    - cache_dir: Cache data
    - backup_dir: Backup files
    - logs_dir: Log files
    """

    base_dir: Path
    tenant_id: str

    @property
    def root(self) -> Path:
        """Root directory for this tenant."""
        if self.tenant_id == DEFAULT_TENANT_ID:
            return self.base_dir
        return self.base_dir / "tenants" / self.tenant_id

    @property
    def config_dir(self) -> Path:
        """Configuration directory."""
        return self.root / "config"

    @property
    def state_dir(self) -> Path:
        """State directory for sync operations."""
        return self.root / "state"

    @property
    def cache_dir(self) -> Path:
        """Cache directory."""
        return self.root / "cache"

    @property
    def backup_dir(self) -> Path:
        """Backup directory."""
        return self.root / "backups"

    @property
    def logs_dir(self) -> Path:
        """Logs directory."""
        return self.root / "logs"

    @property
    def config_file(self) -> Path:
        """Main configuration file."""
        return self.config_dir / "spectra.yaml"

    @property
    def env_file(self) -> Path:
        """Environment file for credentials."""
        return self.config_dir / ".env"

    @property
    def tenant_info_file(self) -> Path:
        """Tenant metadata file."""
        return self.root / TENANT_CONFIG_FILE

    def ensure_dirs(self) -> None:
        """Create all directories if they don't exist."""
        for dir_path in [
            self.root,
            self.config_dir,
            self.state_dir,
            self.cache_dir,
            self.backup_dir,
            self.logs_dir,
        ]:
            dir_path.mkdir(parents=True, exist_ok=True)

    def get_all_paths(self) -> dict[str, Path]:
        """Get all paths as a dictionary."""
        return {
            "root": self.root,
            "config_dir": self.config_dir,
            "state_dir": self.state_dir,
            "cache_dir": self.cache_dir,
            "backup_dir": self.backup_dir,
            "logs_dir": self.logs_dir,
            "config_file": self.config_file,
            "env_file": self.env_file,
        }


# =============================================================================
# Tenant Context
# =============================================================================

# Context variable for current tenant (thread-safe)
_current_tenant: contextvars.ContextVar[Tenant | None] = contextvars.ContextVar(
    "current_tenant", default=None
)

# Lock for tenant registry operations
_registry_lock = threading.Lock()


def get_current_tenant() -> Tenant | None:
    """Get the current tenant from context."""
    return _current_tenant.get()


def set_current_tenant(tenant: Tenant | None) -> contextvars.Token[Tenant | None]:
    """Set the current tenant in context. Returns a token for reset."""
    return _current_tenant.set(tenant)


def reset_current_tenant(token: contextvars.Token[Tenant | None]) -> None:
    """Reset the current tenant using a token."""
    _current_tenant.reset(token)


@contextlib.contextmanager
def tenant_context(tenant: Tenant) -> Iterator[Tenant]:
    """
    Context manager for temporarily switching to a tenant.

    Usage:
        with tenant_context(tenant) as t:
            # Operations run in context of 'tenant'
            pass

    Args:
        tenant: The tenant to activate

    Yields:
        The active tenant
    """
    token = set_current_tenant(tenant)
    try:
        logger.debug(f"Entered tenant context: {tenant.id}")
        yield tenant
    finally:
        reset_current_tenant(token)
        logger.debug(f"Exited tenant context: {tenant.id}")


# =============================================================================
# Tenant Registry
# =============================================================================


class TenantRegistry:
    """
    Registry for managing tenants.

    Provides CRUD operations for tenants and persists
    the registry to disk.
    """

    def __init__(self, base_dir: Path | None = None):
        """
        Initialize the tenant registry.

        Args:
            base_dir: Base directory for spectra data.
                     Defaults to ~/.spectra
        """
        self.base_dir = base_dir or DEFAULT_SPECTRA_DIR
        self._tenants: dict[str, Tenant] = {}
        self._loaded = False
        self._load_registry()

    @property
    def registry_file(self) -> Path:
        """Path to the tenant registry file."""
        return self.base_dir / TENANT_REGISTRY_FILE

    def _load_registry(self) -> None:
        """Load the tenant registry from disk."""
        if self._loaded:
            return

        with _registry_lock:
            if self.registry_file.exists():
                try:
                    with open(self.registry_file) as f:
                        data = json.load(f)
                    for tenant_data in data.get("tenants", []):
                        tenant = Tenant.from_dict(tenant_data)
                        self._tenants[tenant.id] = tenant
                    logger.debug(f"Loaded {len(self._tenants)} tenants from registry")
                except (json.JSONDecodeError, KeyError) as e:
                    logger.error(f"Failed to load tenant registry: {e}")

            # Ensure default tenant exists
            if DEFAULT_TENANT_ID not in self._tenants:
                self._tenants[DEFAULT_TENANT_ID] = Tenant.create_default()

            self._loaded = True

    def _save_registry(self) -> None:
        """Save the tenant registry to disk."""
        with _registry_lock:
            self.base_dir.mkdir(parents=True, exist_ok=True)

            data = {
                "version": "1.0",
                "updated_at": datetime.now().isoformat(),
                "tenants": [t.to_dict() for t in self._tenants.values()],
            }

            with open(self.registry_file, "w") as f:
                json.dump(data, f, indent=2)

            logger.debug(f"Saved {len(self._tenants)} tenants to registry")

    def get(self, tenant_id: str) -> Tenant | None:
        """
        Get a tenant by ID.

        Args:
            tenant_id: The tenant ID to look up

        Returns:
            The tenant, or None if not found
        """
        return self._tenants.get(tenant_id)

    def get_or_default(self, tenant_id: str | None = None) -> Tenant:
        """
        Get a tenant by ID, or return the default tenant.

        Args:
            tenant_id: Optional tenant ID. If None, returns default.

        Returns:
            The requested tenant or the default tenant
        """
        if tenant_id:
            tenant = self.get(tenant_id)
            if tenant:
                return tenant
            logger.warning(f"Tenant '{tenant_id}' not found, using default")

        return self._tenants[DEFAULT_TENANT_ID]

    def list(
        self,
        include_inactive: bool = False,
        status: TenantStatus | None = None,
    ) -> list[Tenant]:
        """
        List all tenants.

        Args:
            include_inactive: Include non-active tenants
            status: Filter by specific status

        Returns:
            List of tenants matching criteria
        """
        tenants = list(self._tenants.values())

        if status:
            tenants = [t for t in tenants if t.status == status]
        elif not include_inactive:
            tenants = [t for t in tenants if t.is_active()]

        return sorted(tenants, key=lambda t: t.name)

    def create(
        self,
        id: str,
        name: str,
        description: str = "",
        metadata: dict[str, Any] | None = None,
        isolation_level: IsolationLevel = IsolationLevel.FULL,
    ) -> Tenant:
        """
        Create a new tenant.

        Args:
            id: Unique tenant identifier (will be slugified)
            name: Human-readable name
            description: Optional description
            metadata: Optional metadata
            isolation_level: Isolation level

        Returns:
            The created tenant

        Raises:
            ValueError: If tenant ID already exists
        """
        tenant_id = self._slugify(id)

        if tenant_id in self._tenants:
            raise ValueError(f"Tenant '{tenant_id}' already exists")

        tenant = Tenant(
            id=tenant_id,
            name=name,
            description=description,
            metadata=metadata or {},
            isolation_level=isolation_level,
        )

        # Create tenant directories
        paths = self.get_paths(tenant)
        paths.ensure_dirs()

        # Save tenant info file
        self._save_tenant_info(tenant, paths)

        self._tenants[tenant_id] = tenant
        self._save_registry()

        logger.info(f"Created tenant: {tenant_id}")
        return tenant

    def update(
        self,
        tenant_id: str,
        name: str | None = None,
        description: str | None = None,
        status: TenantStatus | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Tenant:
        """
        Update an existing tenant.

        Args:
            tenant_id: Tenant ID to update
            name: New name (optional)
            description: New description (optional)
            status: New status (optional)
            metadata: New/updated metadata (merged with existing)

        Returns:
            The updated tenant

        Raises:
            KeyError: If tenant not found
        """
        if tenant_id not in self._tenants:
            raise KeyError(f"Tenant '{tenant_id}' not found")

        tenant = self._tenants[tenant_id]

        if name is not None:
            tenant.name = name
        if description is not None:
            tenant.description = description
        if status is not None:
            tenant.status = status
        if metadata is not None:
            tenant.metadata.update(metadata)

        tenant.touch()

        # Update tenant info file
        paths = self.get_paths(tenant)
        self._save_tenant_info(tenant, paths)

        self._save_registry()

        logger.info(f"Updated tenant: {tenant_id}")
        return tenant

    def delete(
        self,
        tenant_id: str,
        delete_data: bool = False,
        force: bool = False,
    ) -> bool:
        """
        Delete a tenant.

        Args:
            tenant_id: Tenant ID to delete
            delete_data: Also delete tenant data directories
            force: Force delete even if active

        Returns:
            True if deleted

        Raises:
            KeyError: If tenant not found
            ValueError: If trying to delete default tenant
            RuntimeError: If tenant is active and not forced
        """
        if tenant_id == DEFAULT_TENANT_ID:
            raise ValueError("Cannot delete the default tenant")

        if tenant_id not in self._tenants:
            raise KeyError(f"Tenant '{tenant_id}' not found")

        tenant = self._tenants[tenant_id]

        if tenant.is_active() and not force:
            raise RuntimeError(
                f"Tenant '{tenant_id}' is active. Use force=True or deactivate first."
            )

        # Delete data if requested
        if delete_data:
            paths = self.get_paths(tenant)
            if paths.root.exists():
                shutil.rmtree(paths.root)
                logger.info(f"Deleted tenant data: {paths.root}")

        del self._tenants[tenant_id]
        self._save_registry()

        logger.info(f"Deleted tenant: {tenant_id}")
        return True

    def archive(self, tenant_id: str) -> Tenant:
        """
        Archive a tenant (soft delete).

        Args:
            tenant_id: Tenant ID to archive

        Returns:
            The archived tenant
        """
        return self.update(tenant_id, status=TenantStatus.ARCHIVED)

    def activate(self, tenant_id: str) -> Tenant:
        """
        Activate a tenant.

        Args:
            tenant_id: Tenant ID to activate

        Returns:
            The activated tenant
        """
        return self.update(tenant_id, status=TenantStatus.ACTIVE)

    def suspend(self, tenant_id: str) -> Tenant:
        """
        Suspend a tenant.

        Args:
            tenant_id: Tenant ID to suspend

        Returns:
            The suspended tenant
        """
        return self.update(tenant_id, status=TenantStatus.SUSPENDED)

    def get_paths(self, tenant: Tenant | str) -> TenantPaths:
        """
        Get paths for a tenant.

        Args:
            tenant: Tenant or tenant ID

        Returns:
            TenantPaths for the tenant
        """
        if isinstance(tenant, str):
            tenant_obj = self.get(tenant)
            if not tenant_obj:
                raise KeyError(f"Tenant '{tenant}' not found")
            tenant = tenant_obj

        # Use custom base_dir if specified
        base_dir = Path(tenant.base_dir) if tenant.base_dir else self.base_dir

        return TenantPaths(base_dir=base_dir, tenant_id=tenant.id)

    def exists(self, tenant_id: str) -> bool:
        """Check if a tenant exists."""
        return tenant_id in self._tenants

    def _slugify(self, text: str) -> str:
        """Convert text to a valid tenant ID slug."""
        import re

        # Lowercase
        slug = text.lower()
        # Replace spaces and underscores with hyphens
        slug = re.sub(r"[\s_]+", "-", slug)
        # Remove non-alphanumeric (except hyphens)
        slug = re.sub(r"[^a-z0-9-]", "", slug)
        # Remove multiple consecutive hyphens
        slug = re.sub(r"-+", "-", slug)
        # Strip leading/trailing hyphens
        slug = slug.strip("-")

        return slug or "unnamed"

    def _save_tenant_info(self, tenant: Tenant, paths: TenantPaths) -> None:
        """Save tenant metadata to its directory."""
        paths.ensure_dirs()
        with open(paths.tenant_info_file, "w") as f:
            json.dump(tenant.to_dict(), f, indent=2)


# =============================================================================
# Tenant Manager
# =============================================================================


class TenantManager:
    """
    High-level tenant management with context support.

    Provides convenient methods for:
    - Switching between tenants
    - Getting tenant-aware paths
    - Managing tenant lifecycle
    """

    def __init__(
        self,
        base_dir: Path | None = None,
        registry: TenantRegistry | None = None,
    ):
        """
        Initialize the tenant manager.

        Args:
            base_dir: Base directory for spectra data
            registry: Optional pre-configured registry
        """
        self.base_dir = base_dir or DEFAULT_SPECTRA_DIR
        self.registry = registry or TenantRegistry(self.base_dir)
        self._active_tenant: Tenant | None = None

    @property
    def current_tenant(self) -> Tenant:
        """
        Get the current active tenant.

        Returns the tenant from context if set, otherwise
        the explicitly activated tenant, or the default.
        """
        # Check context first
        ctx_tenant = get_current_tenant()
        if ctx_tenant:
            return ctx_tenant

        # Check explicitly set active tenant
        if self._active_tenant:
            return self._active_tenant

        # Fall back to default
        return self.registry.get_or_default()

    @property
    def current_paths(self) -> TenantPaths:
        """Get paths for the current tenant."""
        return self.registry.get_paths(self.current_tenant)

    def use(self, tenant_id: str) -> Tenant:
        """
        Activate a tenant for subsequent operations.

        Args:
            tenant_id: Tenant ID to activate

        Returns:
            The activated tenant

        Raises:
            KeyError: If tenant not found
            RuntimeError: If tenant is not active
        """
        tenant = self.registry.get(tenant_id)
        if not tenant:
            raise KeyError(f"Tenant '{tenant_id}' not found")

        if not tenant.is_active():
            raise RuntimeError(
                f"Tenant '{tenant_id}' is {tenant.status.value}. Only active tenants can be used."
            )

        self._active_tenant = tenant
        logger.info(f"Switched to tenant: {tenant_id}")
        return tenant

    def use_default(self) -> Tenant:
        """Activate the default tenant."""
        return self.use(DEFAULT_TENANT_ID)

    @contextlib.contextmanager
    def tenant(self, tenant_id: str) -> Iterator[Tenant]:
        """
        Context manager for temporarily using a different tenant.

        Usage:
            with manager.tenant("acme-corp") as t:
                # Operations run in context of 'acme-corp'
                pass

        Args:
            tenant_id: Tenant ID to use

        Yields:
            The tenant
        """
        tenant = self.registry.get(tenant_id)
        if not tenant:
            raise KeyError(f"Tenant '{tenant_id}' not found")

        if not tenant.is_active():
            raise RuntimeError(f"Tenant '{tenant_id}' is {tenant.status.value}")

        # Save the current active tenant
        previous_active = self._active_tenant
        self._active_tenant = tenant

        with tenant_context(tenant) as t:
            try:
                yield t
            finally:
                # Restore the previous active tenant
                self._active_tenant = previous_active

    def create(
        self,
        id: str,
        name: str,
        description: str = "",
        activate: bool = True,
        **kwargs: Any,
    ) -> Tenant:
        """
        Create a new tenant and optionally activate it.

        Args:
            id: Tenant identifier
            name: Human-readable name
            description: Optional description
            activate: Activate the tenant after creation
            **kwargs: Additional arguments for Tenant

        Returns:
            The created tenant
        """
        tenant = self.registry.create(
            id=id,
            name=name,
            description=description,
            **kwargs,
        )

        if activate:
            self._active_tenant = tenant

        return tenant

    def list_tenants(self, **kwargs: Any) -> list[Tenant]:
        """List all tenants."""
        return self.registry.list(**kwargs)

    def get_tenant(self, tenant_id: str) -> Tenant | None:
        """Get a tenant by ID."""
        return self.registry.get(tenant_id)

    def delete_tenant(self, tenant_id: str, **kwargs: Any) -> bool:
        """Delete a tenant."""
        # If deleting the active tenant, clear it
        if self._active_tenant and self._active_tenant.id == tenant_id:
            self._active_tenant = None
        return self.registry.delete(tenant_id, **kwargs)


# =============================================================================
# Tenant-Aware Config Resolver
# =============================================================================


class TenantConfigResolver:
    """
    Resolves configuration paths based on current tenant.

    Provides tenant-aware paths for:
    - Config files
    - State directories
    - Cache directories
    - Environment files
    """

    def __init__(self, manager: TenantManager):
        """
        Initialize the resolver.

        Args:
            manager: Tenant manager instance
        """
        self.manager = manager

    @property
    def paths(self) -> TenantPaths:
        """Get paths for current tenant."""
        return self.manager.current_paths

    def get_config_file(self) -> Path:
        """Get the config file path for current tenant."""
        return self.paths.config_file

    def get_env_file(self) -> Path:
        """Get the .env file path for current tenant."""
        return self.paths.env_file

    def get_state_dir(self) -> Path:
        """Get the state directory for current tenant."""
        return self.paths.state_dir

    def get_cache_dir(self) -> Path:
        """Get the cache directory for current tenant."""
        return self.paths.cache_dir

    def get_backup_dir(self) -> Path:
        """Get the backup directory for current tenant."""
        return self.paths.backup_dir

    def resolve_path(self, relative_path: str) -> Path:
        """
        Resolve a relative path within the tenant's directory.

        Args:
            relative_path: Path relative to tenant root

        Returns:
            Absolute path within tenant directory
        """
        return self.paths.root / relative_path


# =============================================================================
# Migration Support
# =============================================================================


class TenantMigrator:
    """
    Migrate existing single-tenant data to a tenant.

    Supports migrating:
    - Config files
    - State files
    - Cache data
    - Backups
    """

    def __init__(self, manager: TenantManager):
        """
        Initialize the migrator.

        Args:
            manager: Tenant manager instance
        """
        self.manager = manager

    def migrate_from_default(
        self,
        target_tenant_id: str,
        include_state: bool = True,
        include_cache: bool = True,
        include_backups: bool = True,
        copy_mode: bool = True,
    ) -> dict[str, int]:
        """
        Migrate data from default tenant to a new tenant.

        Args:
            target_tenant_id: Target tenant ID
            include_state: Include sync state files
            include_cache: Include cache files
            include_backups: Include backup files
            copy_mode: Copy files (True) or move (False)

        Returns:
            Dictionary with counts of migrated items
        """
        default_paths = self.manager.registry.get_paths(DEFAULT_TENANT_ID)
        target_paths = self.manager.registry.get_paths(target_tenant_id)

        results = {
            "config_files": 0,
            "state_files": 0,
            "cache_files": 0,
            "backup_files": 0,
        }

        # Ensure target directories exist
        target_paths.ensure_dirs()

        # Copy operation
        def transfer(src: Path, dst: Path) -> bool:
            if not src.exists():
                return False
            dst.parent.mkdir(parents=True, exist_ok=True)
            if copy_mode:
                if src.is_dir():
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(src, dst)
            else:
                shutil.move(str(src), str(dst))
            return True

        # Migrate config files
        for config_file in default_paths.config_dir.glob("*"):
            if config_file.is_file():
                target_file = target_paths.config_dir / config_file.name
                if transfer(config_file, target_file):
                    results["config_files"] += 1

        # Migrate state
        if include_state and default_paths.state_dir.exists():
            for state_file in default_paths.state_dir.glob("*.json"):
                target_file = target_paths.state_dir / state_file.name
                if transfer(state_file, target_file):
                    results["state_files"] += 1

        # Migrate cache
        if include_cache and default_paths.cache_dir.exists():
            for cache_file in default_paths.cache_dir.glob("*"):
                target_file = target_paths.cache_dir / cache_file.name
                if transfer(cache_file, target_file):
                    results["cache_files"] += 1

        # Migrate backups
        if include_backups and default_paths.backup_dir.exists():
            for backup_file in default_paths.backup_dir.glob("*"):
                target_file = target_paths.backup_dir / backup_file.name
                if transfer(backup_file, target_file):
                    results["backup_files"] += 1

        logger.info(f"Migrated data to tenant '{target_tenant_id}': {results}")
        return results

    def import_config(
        self,
        tenant_id: str,
        config_path: Path,
        env_path: Path | None = None,
    ) -> bool:
        """
        Import configuration files into a tenant.

        Args:
            tenant_id: Target tenant ID
            config_path: Path to config file to import
            env_path: Optional path to .env file to import

        Returns:
            True if successful
        """
        paths = self.manager.registry.get_paths(tenant_id)
        paths.ensure_dirs()

        # Import config file
        if config_path.exists():
            shutil.copy2(config_path, paths.config_file)
            logger.info(f"Imported config to {paths.config_file}")

        # Import env file
        if env_path and env_path.exists():
            shutil.copy2(env_path, paths.env_file)
            logger.info(f"Imported .env to {paths.env_file}")

        return True


# =============================================================================
# Global Instance
# =============================================================================

_global_manager: TenantManager | None = None
_manager_lock = threading.Lock()


def get_tenant_manager(base_dir: Path | None = None) -> TenantManager:
    """
    Get the global tenant manager instance.

    Args:
        base_dir: Optional base directory override

    Returns:
        The global TenantManager instance
    """
    global _global_manager

    if _global_manager is None or (base_dir and base_dir != _global_manager.base_dir):
        with _manager_lock:
            if _global_manager is None or (base_dir and base_dir != _global_manager.base_dir):
                _global_manager = TenantManager(base_dir=base_dir)

    return _global_manager


def reset_tenant_manager() -> None:
    """Reset the global tenant manager (for testing)."""
    global _global_manager
    with _manager_lock:
        _global_manager = None


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "DEFAULT_SPECTRA_DIR",
    "DEFAULT_TENANT_ID",
    "TENANT_CONFIG_FILE",
    "TENANT_REGISTRY_FILE",
    "IsolationLevel",
    "Tenant",
    "TenantConfigResolver",
    "TenantManager",
    "TenantMigrator",
    "TenantPaths",
    "TenantRegistry",
    "TenantStatus",
    "get_current_tenant",
    "get_tenant_manager",
    "reset_current_tenant",
    "reset_tenant_manager",
    "set_current_tenant",
    "tenant_context",
]
