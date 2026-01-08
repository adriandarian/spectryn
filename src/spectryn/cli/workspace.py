"""
CLI commands for workspace management.

Provides commands for:
- Creating and listing workspaces
- Switching between workspaces
- Linking workspaces to directories
- Managing workspace state
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from spectryn.core.workspace import (
    DEFAULT_WORKSPACE_ID,
    CrossTenantWorkspaceQuery,
    Workspace,
    WorkspaceMigrator,
    WorkspaceStateStore,
    WorkspaceType,
    get_workspace_manager,
)


if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


# =============================================================================
# Output Helpers
# =============================================================================


def _print_workspace_table(workspaces: list[Workspace], show_tenant: bool = False) -> None:
    """Print workspaces in a table format."""
    if not workspaces:
        print("No workspaces found.")
        return

    # Build header
    headers = ["ID", "Name", "Type", "Status"]
    if show_tenant:
        headers.insert(0, "Tenant")
    headers.extend(["Tracker Project", "Local Path"])

    # Calculate column widths
    widths = [len(h) for h in headers]
    rows: list[list[str]] = []

    for ws in workspaces:
        row = [
            ws.id,
            ws.name,
            ws.workspace_type.value,
            ws.status.value,
            ws.tracker_project or "-",
            _truncate_path(ws.local_path) if ws.local_path else "-",
        ]
        if show_tenant:
            row.insert(0, ws.tenant_id)
        rows.append(row)
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    # Print header
    header_line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    print(header_line)
    print("-" * len(header_line))

    # Print rows
    for row in rows:
        print("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)))


def _truncate_path(path: str, max_len: int = 40) -> str:
    """Truncate a path for display."""
    if len(path) <= max_len:
        return path
    return "..." + path[-(max_len - 3) :]


def _print_workspace_detail(workspace: Workspace, paths: Any | None = None) -> None:
    """Print detailed workspace information."""
    print(f"\n{'=' * 50}")
    print(f"Workspace: {workspace.name}")
    print(f"{'=' * 50}")
    print(f"  ID:             {workspace.id}")
    print(f"  Tenant:         {workspace.tenant_id}")
    print(f"  Type:           {workspace.workspace_type.value}")
    print(f"  Status:         {workspace.status.value}")
    print(f"  Description:    {workspace.description or '-'}")
    print(f"  Tracker Project: {workspace.tracker_project or '-'}")
    print(f"  Local Path:     {workspace.local_path or '-'}")
    print(f"  Created:        {workspace.created_at}")
    print(f"  Updated:        {workspace.updated_at}")

    if workspace.tags:
        print(f"  Tags:           {', '.join(workspace.tags)}")

    if workspace.metadata:
        print(f"  Metadata:       {json.dumps(workspace.metadata, indent=2)}")

    if paths:
        print("\n  Paths:")
        print(f"    Root:         {paths.root}")
        print(f"    Config:       {paths.config_dir}")
        print(f"    State:        {paths.state_dir}")
        print(f"    Cache:        {paths.cache_dir}")
        print(f"    Backups:      {paths.backup_dir}")
        print(f"    Markdown:     {paths.markdown_dir}")


# =============================================================================
# CLI Commands
# =============================================================================


def cmd_workspace_list(
    include_archived: bool = False,
    workspace_type: str | None = None,
    tag: str | None = None,
    all_tenants: bool = False,
    output_format: str = "table",
) -> int:
    """
    List workspaces.

    Args:
        include_archived: Include archived workspaces
        workspace_type: Filter by workspace type
        tag: Filter by tag
        all_tenants: List workspaces across all tenants
        output_format: Output format (table, json)

    Returns:
        Exit code
    """
    try:
        if all_tenants:
            query = CrossTenantWorkspaceQuery()
            results = query.list_all_workspaces(include_archived=include_archived)
            workspaces = [ws for _, ws in results]

            if output_format == "json":
                data = [{"tenant_id": tid, **ws.to_dict()} for tid, ws in results]
                print(json.dumps(data, indent=2))
            else:
                _print_workspace_table(workspaces, show_tenant=True)
        else:
            manager = get_workspace_manager()

            ws_type = WorkspaceType(workspace_type) if workspace_type else None
            workspaces = manager.list_workspaces(
                include_archived=include_archived,
                workspace_type=ws_type,
                tag=tag,
            )

            if output_format == "json":
                print(json.dumps([ws.to_dict() for ws in workspaces], indent=2))
            else:
                _print_workspace_table(workspaces)

        return 0

    except Exception as e:
        logger.error(f"Failed to list workspaces: {e}")
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_workspace_create(
    workspace_id: str,
    name: str,
    description: str = "",
    workspace_type: str = "project",
    local_path: str | None = None,
    tracker_project: str | None = None,
    tags: list[str] | None = None,
    activate: bool = True,
) -> int:
    """
    Create a new workspace.

    Args:
        workspace_id: Workspace identifier
        name: Human-readable name
        description: Optional description
        workspace_type: Type of workspace
        local_path: Associated local directory
        tracker_project: Associated tracker project
        tags: Tags for organization
        activate: Activate after creation

    Returns:
        Exit code
    """
    try:
        manager = get_workspace_manager()

        ws_type = WorkspaceType(workspace_type)
        workspace = manager.create(
            id=workspace_id,
            name=name,
            description=description,
            workspace_type=ws_type,
            local_path=local_path,
            tracker_project=tracker_project,
            tags=tags,
            activate=activate,
        )

        print(f"✓ Created workspace: {workspace.id}")
        print(f"  Name: {workspace.name}")
        print(f"  Type: {workspace.workspace_type.value}")
        print(f"  Tenant: {workspace.tenant_id}")

        if local_path:
            print(f"  Linked to: {local_path}")

        if tracker_project:
            print(f"  Tracker project: {tracker_project}")

        if activate:
            print(f"\n  Now using workspace: {workspace.id}")

        return 0

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        logger.error(f"Failed to create workspace: {e}")
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_workspace_use(workspace_id: str) -> int:
    """
    Switch to a workspace.

    Args:
        workspace_id: Workspace ID to activate

    Returns:
        Exit code
    """
    try:
        manager = get_workspace_manager()
        workspace = manager.use(workspace_id)

        print(f"✓ Switched to workspace: {workspace.name} ({workspace.id})")
        print(f"  Type: {workspace.workspace_type.value}")

        if workspace.local_path:
            print(f"  Local path: {workspace.local_path}")

        if workspace.tracker_project:
            print(f"  Tracker project: {workspace.tracker_project}")

        return 0

    except KeyError as e:
        print(f"Error: Workspace not found - {e}", file=sys.stderr)
        return 1
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        logger.error(f"Failed to switch workspace: {e}")
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_workspace_show(workspace_id: str | None = None) -> int:
    """
    Show workspace details.

    Args:
        workspace_id: Workspace ID (defaults to current)

    Returns:
        Exit code
    """
    try:
        manager = get_workspace_manager()

        if workspace_id:
            workspace = manager.get_workspace(workspace_id)
            if not workspace:
                print(f"Error: Workspace '{workspace_id}' not found", file=sys.stderr)
                return 1
        else:
            workspace = manager.current_workspace
            print("Current workspace:")

        paths = manager.registry.get_paths(workspace)
        _print_workspace_detail(workspace, paths)

        return 0

    except Exception as e:
        logger.error(f"Failed to show workspace: {e}")
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_workspace_delete(
    workspace_id: str,
    hard: bool = False,
    force: bool = False,
) -> int:
    """
    Delete a workspace.

    Args:
        workspace_id: Workspace ID to delete
        hard: Remove all files (hard delete)
        force: Skip confirmation

    Returns:
        Exit code
    """
    try:
        manager = get_workspace_manager()

        workspace = manager.get_workspace(workspace_id)
        if not workspace:
            print(f"Error: Workspace '{workspace_id}' not found", file=sys.stderr)
            return 1

        if workspace_id == DEFAULT_WORKSPACE_ID:
            print("Error: Cannot delete the default workspace", file=sys.stderr)
            return 1

        if not force:
            action = "permanently delete" if hard else "soft delete"
            confirm = input(f"Are you sure you want to {action} workspace '{workspace_id}'? [y/N] ")
            if confirm.lower() not in ("y", "yes"):
                print("Cancelled.")
                return 0

        manager.delete_workspace(workspace_id, hard_delete=hard)

        if hard:
            print(f"✓ Permanently deleted workspace: {workspace_id}")
        else:
            print(f"✓ Soft deleted workspace: {workspace_id}")

        return 0

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        logger.error(f"Failed to delete workspace: {e}")
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_workspace_archive(workspace_id: str) -> int:
    """
    Archive a workspace.

    Args:
        workspace_id: Workspace ID to archive

    Returns:
        Exit code
    """
    try:
        manager = get_workspace_manager()
        workspace = manager.registry.archive(workspace_id)

        print(f"✓ Archived workspace: {workspace.name} ({workspace.id})")
        return 0

    except (KeyError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        logger.error(f"Failed to archive workspace: {e}")
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_workspace_activate(workspace_id: str) -> int:
    """
    Activate an archived workspace.

    Args:
        workspace_id: Workspace ID to activate

    Returns:
        Exit code
    """
    try:
        manager = get_workspace_manager()
        workspace = manager.registry.activate(workspace_id)

        print(f"✓ Activated workspace: {workspace.name} ({workspace.id})")
        return 0

    except KeyError as e:
        print(f"Error: Workspace not found - {e}", file=sys.stderr)
        return 1
    except Exception as e:
        logger.error(f"Failed to activate workspace: {e}")
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_workspace_link(
    workspace_id: str,
    local_path: str,
) -> int:
    """
    Link a workspace to a local directory.

    Args:
        workspace_id: Workspace ID
        local_path: Local directory path

    Returns:
        Exit code
    """
    try:
        manager = get_workspace_manager()

        # Resolve and validate path
        path = Path(local_path).resolve()
        if not path.exists():
            print(f"Warning: Path does not exist: {path}")
            confirm = input("Create directory and link anyway? [y/N] ")
            if confirm.lower() in ("y", "yes"):
                path.mkdir(parents=True, exist_ok=True)
            else:
                print("Cancelled.")
                return 0

        workspace = manager.link_directory(workspace_id, path)

        print(f"✓ Linked workspace '{workspace.id}' to: {path}")
        return 0

    except KeyError as e:
        print(f"Error: Workspace not found - {e}", file=sys.stderr)
        return 1
    except Exception as e:
        logger.error(f"Failed to link workspace: {e}")
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_workspace_unlink(workspace_id: str) -> int:
    """
    Unlink a workspace from its local directory.

    Args:
        workspace_id: Workspace ID

    Returns:
        Exit code
    """
    try:
        manager = get_workspace_manager()
        workspace = manager.unlink_directory(workspace_id)

        print(f"✓ Unlinked workspace '{workspace.id}' from local directory")
        return 0

    except KeyError as e:
        print(f"Error: Workspace not found - {e}", file=sys.stderr)
        return 1
    except Exception as e:
        logger.error(f"Failed to unlink workspace: {e}")
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_workspace_detect(path: str | None = None) -> int:
    """
    Detect workspace for a path.

    Args:
        path: Path to check (defaults to cwd)

    Returns:
        Exit code
    """
    try:
        manager = get_workspace_manager()

        check_path = Path(path) if path else Path.cwd()
        workspace = manager.detect_workspace(check_path)

        if workspace:
            print(f"✓ Detected workspace: {workspace.name} ({workspace.id})")
            print(f"  Type: {workspace.workspace_type.value}")
            print(f"  Linked to: {workspace.local_path}")
        else:
            print(f"No workspace found for: {check_path}")
            print("Use 'spectra workspace link' to associate a workspace with this directory.")

        return 0

    except Exception as e:
        logger.error(f"Failed to detect workspace: {e}")
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_workspace_copy(
    source_id: str,
    target_id: str,
    target_name: str,
    include_state: bool = True,
    include_cache: bool = False,
    include_config: bool = True,
) -> int:
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
        Exit code
    """
    try:
        manager = get_workspace_manager()
        migrator = WorkspaceMigrator(manager.registry)

        workspace = migrator.copy_workspace(
            source_id=source_id,
            target_id=target_id,
            target_name=target_name,
            include_state=include_state,
            include_cache=include_cache,
            include_config=include_config,
        )

        print(f"✓ Copied workspace '{source_id}' to '{workspace.id}'")
        print(f"  Name: {workspace.name}")
        print(f"  State copied: {'yes' if include_state else 'no'}")
        print(f"  Cache copied: {'yes' if include_cache else 'no'}")
        print(f"  Config copied: {'yes' if include_config else 'no'}")

        return 0

    except (KeyError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        logger.error(f"Failed to copy workspace: {e}")
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_workspace_status() -> int:
    """
    Show workspace status overview.

    Returns:
        Exit code
    """
    try:
        manager = get_workspace_manager()

        # Current workspace
        current = manager.current_workspace
        print(f"Current Workspace: {current.name} ({current.id})")
        print(f"  Tenant: {manager.tenant_id}")
        print(f"  Type: {current.workspace_type.value}")

        # All workspaces in tenant
        workspaces = manager.list_workspaces(include_archived=True)
        active = sum(1 for ws in workspaces if ws.is_active())
        archived = sum(1 for ws in workspaces if ws.is_archived())

        print(f"\nWorkspaces in tenant '{manager.tenant_id}':")
        print(f"  Total: {len(workspaces)}")
        print(f"  Active: {active}")
        print(f"  Archived: {archived}")

        # By type
        by_type: dict[str, int] = {}
        for ws in workspaces:
            t = ws.workspace_type.value
            by_type[t] = by_type.get(t, 0) + 1

        if by_type:
            print("\n  By Type:")
            for t, count in sorted(by_type.items()):
                print(f"    {t}: {count}")

        # Workspace state
        paths = manager.current_paths
        state_store = WorkspaceStateStore(paths)
        state = state_store.load()

        print("\nCurrent Workspace State:")
        print(f"  Last sync: {state.last_sync or 'never'}")
        print(f"  Sync count: {state.sync_count}")
        if state.active_epic_key:
            print(f"  Active epic: {state.active_epic_key}")
        if state.recent_files:
            print(f"  Recent files: {len(state.recent_files)}")

        return 0

    except Exception as e:
        logger.error(f"Failed to get workspace status: {e}")
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_workspace_tag(
    workspace_id: str,
    tag: str,
    remove: bool = False,
) -> int:
    """
    Add or remove a tag from a workspace.

    Args:
        workspace_id: Workspace ID
        tag: Tag to add/remove
        remove: Remove tag instead of adding

    Returns:
        Exit code
    """
    try:
        manager = get_workspace_manager()

        if remove:
            workspace = manager.registry.remove_tag(workspace_id, tag)
            print(f"✓ Removed tag '{tag}' from workspace '{workspace.id}'")
        else:
            workspace = manager.registry.add_tag(workspace_id, tag)
            print(f"✓ Added tag '{tag}' to workspace '{workspace.id}'")

        print(f"  Current tags: {', '.join(workspace.tags) or 'none'}")
        return 0

    except KeyError as e:
        print(f"Error: Workspace not found - {e}", file=sys.stderr)
        return 1
    except Exception as e:
        logger.error(f"Failed to update tags: {e}")
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_workspace_summary(output_format: str = "table") -> int:
    """
    Show summary across all tenants.

    Args:
        output_format: Output format (table, json)

    Returns:
        Exit code
    """
    try:
        query = CrossTenantWorkspaceQuery()
        summary = query.get_workspace_summary()

        if output_format == "json":
            print(json.dumps(summary, indent=2))
        else:
            print("Workspace Summary (All Tenants)")
            print("=" * 40)
            print(f"Total workspaces: {summary['total_workspaces']}")

            print("\nBy Tenant:")
            for tenant_id, count in sorted(summary["by_tenant"].items()):
                print(f"  {tenant_id}: {count}")

            print("\nBy Type:")
            for ws_type, count in sorted(summary["by_type"].items()):
                print(f"  {ws_type}: {count}")

            print("\nBy Status:")
            for status, count in sorted(summary["by_status"].items()):
                print(f"  {status}: {count}")

        return 0

    except Exception as e:
        logger.error(f"Failed to get summary: {e}")
        print(f"Error: {e}", file=sys.stderr)
        return 1


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    "cmd_workspace_activate",
    "cmd_workspace_archive",
    "cmd_workspace_copy",
    "cmd_workspace_create",
    "cmd_workspace_delete",
    "cmd_workspace_detect",
    "cmd_workspace_link",
    "cmd_workspace_list",
    "cmd_workspace_show",
    "cmd_workspace_status",
    "cmd_workspace_summary",
    "cmd_workspace_tag",
    "cmd_workspace_unlink",
    "cmd_workspace_use",
]
