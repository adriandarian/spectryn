"""
Tenant-Aware State - State management with tenant isolation.

Extends the existing sync state system to support multi-tenant
data isolation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from spectryn.application.sync.state import (
    StateStore,
    SyncPhase,
    SyncState,
)
from spectryn.core.tenant import (
    Tenant,
    TenantManager,
    get_current_tenant,
    get_tenant_manager,
)


if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


# =============================================================================
# Tenant-Aware State Store
# =============================================================================


class TenantStateStore(StateStore):
    """
    State store with tenant isolation.

    Extends StateStore to automatically use the current tenant's
    state directory.
    """

    def __init__(
        self,
        state_dir: Path | None = None,
        tenant_manager: TenantManager | None = None,
        tenant_id: str | None = None,
    ):
        """
        Initialize the tenant-aware state store.

        Args:
            state_dir: Explicit state directory (overrides tenant)
            tenant_manager: Tenant manager to use
            tenant_id: Explicit tenant ID (overrides context)
        """
        self._tenant_manager = tenant_manager
        self._explicit_tenant_id = tenant_id
        self._explicit_state_dir = state_dir

        # Initialize with resolved state directory
        resolved_dir = self._resolve_state_dir()
        super().__init__(state_dir=resolved_dir)

    def _resolve_state_dir(self) -> Path:
        """Resolve the state directory based on tenant context."""
        # Explicit directory takes precedence
        if self._explicit_state_dir:
            return self._explicit_state_dir

        # Get tenant manager
        manager = self._tenant_manager or get_tenant_manager()

        # Resolve tenant
        if self._explicit_tenant_id:
            tenant = manager.registry.get(self._explicit_tenant_id)
            if tenant:
                paths = manager.registry.get_paths(tenant)
                return paths.state_dir

        # Use current tenant from context
        current = get_current_tenant()
        if current:
            paths = manager.registry.get_paths(current)
            return paths.state_dir

        # Fall back to manager's current tenant
        paths = manager.current_paths
        return paths.state_dir

    @property
    def tenant_id(self) -> str:
        """Get the tenant ID for this state store."""
        if self._explicit_tenant_id:
            return self._explicit_tenant_id

        current = get_current_tenant()
        if current:
            return current.id

        manager = self._tenant_manager or get_tenant_manager()
        return manager.current_tenant.id

    def save_with_tenant(
        self,
        state: SyncState,
        tenant_id: str | None = None,
    ) -> Path:
        """
        Save state for a specific tenant.

        Args:
            state: Sync state to save
            tenant_id: Optional tenant ID override

        Returns:
            Path to saved state file
        """
        if tenant_id and tenant_id != self.tenant_id:
            # Create a temporary store for the other tenant
            store = TenantStateStore(
                tenant_manager=self._tenant_manager,
                tenant_id=tenant_id,
            )
            return store.save(state)

        return self.save(state)

    def list_sessions_with_tenant(
        self,
        tenant_id: str | None = None,
    ) -> list[dict]:
        """
        List sessions for a specific tenant.

        Args:
            tenant_id: Optional tenant ID override

        Returns:
            List of session summaries
        """
        if tenant_id and tenant_id != self.tenant_id:
            store = TenantStateStore(
                tenant_manager=self._tenant_manager,
                tenant_id=tenant_id,
            )
            return store.list_sessions()

        return self.list_sessions()


# =============================================================================
# Cross-Tenant State Query
# =============================================================================


@dataclass
class TenantSessionInfo:
    """Information about a sync session including tenant context."""

    session_id: str
    tenant_id: str
    tenant_name: str
    markdown_path: str
    epic_key: str
    phase: str
    created_at: str
    updated_at: str
    dry_run: bool
    operation_count: int
    completed_count: int
    failed_count: int

    @classmethod
    def from_state(
        cls,
        state: SyncState,
        tenant: Tenant,
    ) -> TenantSessionInfo:
        """Create from a SyncState and Tenant."""
        completed = sum(1 for op in state.operations if op.is_completed)
        failed = sum(1 for op in state.operations if op.status == "failed")

        return cls(
            session_id=state.session_id,
            tenant_id=tenant.id,
            tenant_name=tenant.name,
            markdown_path=state.markdown_path,
            epic_key=state.epic_key,
            phase=state.phase,
            created_at=state.created_at,
            updated_at=state.updated_at,
            dry_run=state.dry_run,
            operation_count=len(state.operations),
            completed_count=completed,
            failed_count=failed,
        )


class CrossTenantStateQuery:
    """
    Query sync state across multiple tenants.

    Useful for:
    - Finding all recent syncs across organizations
    - Migrating state between tenants
    - Administrative reporting
    """

    def __init__(self, tenant_manager: TenantManager | None = None):
        """
        Initialize the cross-tenant query.

        Args:
            tenant_manager: Tenant manager to use
        """
        self.manager = tenant_manager or get_tenant_manager()

    def list_all_sessions(
        self,
        include_inactive_tenants: bool = False,
        limit: int | None = None,
    ) -> list[TenantSessionInfo]:
        """
        List all sync sessions across all tenants.

        Args:
            include_inactive_tenants: Include sessions from inactive tenants
            limit: Maximum number of sessions to return

        Returns:
            List of session info, sorted by updated_at descending
        """
        all_sessions: list[TenantSessionInfo] = []

        for tenant in self.manager.list_tenants(include_inactive=include_inactive_tenants):
            try:
                store = TenantStateStore(
                    tenant_manager=self.manager,
                    tenant_id=tenant.id,
                )

                for session_summary in store.list_sessions():
                    session_id = session_summary.get("session_id", "")
                    if not session_id:
                        continue

                    state = store.load(session_id)
                    if state:
                        info = TenantSessionInfo.from_state(state, tenant)
                        all_sessions.append(info)

            except Exception as e:
                logger.warning(f"Failed to load sessions for tenant '{tenant.id}': {e}")

        # Sort by updated_at descending
        all_sessions.sort(key=lambda s: s.updated_at, reverse=True)

        if limit:
            return all_sessions[:limit]

        return all_sessions

    def find_sessions_by_epic(
        self,
        epic_key: str,
        tenant_ids: list[str] | None = None,
    ) -> list[TenantSessionInfo]:
        """
        Find all sync sessions for a specific epic across tenants.

        Args:
            epic_key: Epic key to search for
            tenant_ids: Optional list of tenant IDs to search

        Returns:
            List of matching session info
        """
        results: list[TenantSessionInfo] = []

        tenants = self.manager.list_tenants()
        if tenant_ids:
            tenants = [t for t in tenants if t.id in tenant_ids]

        for tenant in tenants:
            try:
                store = TenantStateStore(
                    tenant_manager=self.manager,
                    tenant_id=tenant.id,
                )

                for session_summary in store.list_sessions():
                    if session_summary.get("epic_key") == epic_key:
                        session_id = session_summary.get("session_id", "")
                        state = store.load(session_id)
                        if state:
                            results.append(TenantSessionInfo.from_state(state, tenant))

            except Exception as e:
                logger.warning(f"Failed to search tenant '{tenant.id}': {e}")

        return results

    def get_tenant_stats(self, tenant_id: str) -> dict[str, Any]:
        """
        Get statistics for a tenant's sync history.

        Args:
            tenant_id: Tenant ID to get stats for

        Returns:
            Dictionary with statistics
        """
        tenant = self.manager.get_tenant(tenant_id)
        if not tenant:
            return {}

        store = TenantStateStore(
            tenant_manager=self.manager,
            tenant_id=tenant_id,
        )

        sessions = store.list_sessions()
        total_sessions = len(sessions)
        completed_sessions = sum(1 for s in sessions if s.get("phase") == SyncPhase.COMPLETED.value)
        failed_sessions = sum(1 for s in sessions if s.get("phase") == SyncPhase.FAILED.value)

        # Get unique epics and files
        unique_epics = {s.get("epic_key", "") for s in sessions}
        unique_files = {s.get("markdown_path", "") for s in sessions}

        return {
            "tenant_id": tenant_id,
            "tenant_name": tenant.name,
            "total_sessions": total_sessions,
            "completed_sessions": completed_sessions,
            "failed_sessions": failed_sessions,
            "in_progress_sessions": total_sessions - completed_sessions - failed_sessions,
            "unique_epics": len(unique_epics),
            "unique_files": len(unique_files),
        }


# =============================================================================
# State Migration
# =============================================================================


class TenantStateMigrator:
    """
    Migrate sync state between tenants.

    Supports:
    - Moving state from one tenant to another
    - Copying state (for cloning)
    - Bulk operations
    """

    def __init__(self, tenant_manager: TenantManager | None = None):
        """
        Initialize the state migrator.

        Args:
            tenant_manager: Tenant manager to use
        """
        self.manager = tenant_manager or get_tenant_manager()

    def migrate_session(
        self,
        session_id: str,
        source_tenant_id: str,
        target_tenant_id: str,
        delete_source: bool = False,
    ) -> bool:
        """
        Migrate a single session between tenants.

        Args:
            session_id: Session ID to migrate
            source_tenant_id: Source tenant
            target_tenant_id: Target tenant
            delete_source: Delete from source after migration

        Returns:
            True if successful
        """
        source_store = TenantStateStore(
            tenant_manager=self.manager,
            tenant_id=source_tenant_id,
        )

        target_store = TenantStateStore(
            tenant_manager=self.manager,
            tenant_id=target_tenant_id,
        )

        # Load from source
        state = source_store.load(session_id)
        if not state:
            logger.error(f"Session '{session_id}' not found in tenant '{source_tenant_id}'")
            return False

        # Save to target
        target_store.save(state)
        logger.info(
            f"Migrated session '{session_id}' from '{source_tenant_id}' to '{target_tenant_id}'"
        )

        # Optionally delete from source
        if delete_source:
            source_store.delete(session_id)
            logger.info(f"Deleted source session '{session_id}'")

        return True

    def migrate_all_sessions(
        self,
        source_tenant_id: str,
        target_tenant_id: str,
        delete_source: bool = False,
    ) -> dict[str, int]:
        """
        Migrate all sessions from one tenant to another.

        Args:
            source_tenant_id: Source tenant
            target_tenant_id: Target tenant
            delete_source: Delete from source after migration

        Returns:
            Dictionary with migration counts
        """
        source_store = TenantStateStore(
            tenant_manager=self.manager,
            tenant_id=source_tenant_id,
        )

        results = {"migrated": 0, "failed": 0, "skipped": 0}

        for session_summary in source_store.list_sessions():
            session_id = session_summary.get("session_id", "")
            if not session_id:
                results["skipped"] += 1
                continue

            try:
                if self.migrate_session(
                    session_id=session_id,
                    source_tenant_id=source_tenant_id,
                    target_tenant_id=target_tenant_id,
                    delete_source=delete_source,
                ):
                    results["migrated"] += 1
                else:
                    results["failed"] += 1
            except Exception as e:
                logger.error(f"Failed to migrate session '{session_id}': {e}")
                results["failed"] += 1

        return results


# =============================================================================
# Factory Function
# =============================================================================


def create_tenant_state_store(
    tenant_id: str | None = None,
    state_dir: Path | None = None,
) -> TenantStateStore:
    """
    Create a tenant-aware state store.

    Args:
        tenant_id: Explicit tenant ID
        state_dir: Explicit state directory

    Returns:
        Configured TenantStateStore
    """
    return TenantStateStore(
        state_dir=state_dir,
        tenant_id=tenant_id,
    )


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "CrossTenantStateQuery",
    "TenantSessionInfo",
    "TenantStateMigrator",
    "TenantStateStore",
    "create_tenant_state_store",
]
