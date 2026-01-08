"""
Tenant CLI Commands - CLI interface for multi-tenant management.

Provides commands for:
- Creating and managing tenants
- Switching between tenants
- Viewing tenant information
- Migrating data between tenants
"""

from __future__ import annotations

import argparse
import json
import logging
from typing import TYPE_CHECKING

from spectryn.core.tenant import (
    DEFAULT_TENANT_ID,
    IsolationLevel,
    TenantMigrator,
    get_tenant_manager,
)
from spectryn.core.tenant_cache import TenantCacheStore
from spectryn.core.tenant_config import TenantConfigManager
from spectryn.core.tenant_state import CrossTenantStateQuery


if TYPE_CHECKING:
    from spectryn.cli.output import Console


logger = logging.getLogger(__name__)


# =============================================================================
# Tenant Command Group
# =============================================================================


def register_tenant_commands(
    subparsers: argparse._SubParsersAction,
) -> None:
    """
    Register tenant management commands.

    Args:
        subparsers: Argument parser subparsers
    """
    # Main tenant command
    tenant_parser = subparsers.add_parser(
        "tenant",
        help="Manage tenants (organizations)",
        description="Commands for managing multiple organizations",
    )

    tenant_subparsers = tenant_parser.add_subparsers(
        dest="tenant_command",
        title="tenant commands",
    )

    # tenant list
    list_parser = tenant_subparsers.add_parser(
        "list",
        help="List all tenants",
        description="Show all configured tenants",
    )
    list_parser.add_argument(
        "--all",
        "-a",
        action="store_true",
        help="Include inactive tenants",
    )
    list_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    # tenant create
    create_parser = tenant_subparsers.add_parser(
        "create",
        help="Create a new tenant",
        description="Create a new tenant organization",
    )
    create_parser.add_argument(
        "id",
        help="Tenant identifier (will be slugified)",
    )
    create_parser.add_argument(
        "--name",
        "-n",
        help="Human-readable name (defaults to ID)",
    )
    create_parser.add_argument(
        "--description",
        "-d",
        default="",
        help="Tenant description",
    )
    create_parser.add_argument(
        "--isolation",
        choices=["full", "shared_cache", "shared_config"],
        default="full",
        help="Isolation level (default: full)",
    )
    create_parser.add_argument(
        "--activate",
        action="store_true",
        help="Activate tenant after creation",
    )

    # tenant use
    use_parser = tenant_subparsers.add_parser(
        "use",
        help="Switch to a tenant",
        description="Set the active tenant for subsequent operations",
    )
    use_parser.add_argument(
        "id",
        help="Tenant ID to switch to",
    )

    # tenant show
    show_parser = tenant_subparsers.add_parser(
        "show",
        help="Show tenant details",
        description="Display detailed information about a tenant",
    )
    show_parser.add_argument(
        "id",
        nargs="?",
        help="Tenant ID (defaults to current)",
    )
    show_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    # tenant delete
    delete_parser = tenant_subparsers.add_parser(
        "delete",
        help="Delete a tenant",
        description="Delete a tenant and optionally its data",
    )
    delete_parser.add_argument(
        "id",
        help="Tenant ID to delete",
    )
    delete_parser.add_argument(
        "--delete-data",
        action="store_true",
        help="Also delete tenant data",
    )
    delete_parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Force delete even if active",
    )

    # tenant archive
    archive_parser = tenant_subparsers.add_parser(
        "archive",
        help="Archive a tenant",
        description="Archive a tenant (soft delete)",
    )
    archive_parser.add_argument(
        "id",
        help="Tenant ID to archive",
    )

    # tenant activate
    activate_parser = tenant_subparsers.add_parser(
        "activate",
        help="Activate a tenant",
        description="Activate an archived or suspended tenant",
    )
    activate_parser.add_argument(
        "id",
        help="Tenant ID to activate",
    )

    # tenant migrate
    migrate_parser = tenant_subparsers.add_parser(
        "migrate",
        help="Migrate data between tenants",
        description="Migrate data from one tenant to another",
    )
    migrate_parser.add_argument(
        "--from",
        dest="source",
        default=DEFAULT_TENANT_ID,
        help="Source tenant ID (default: default)",
    )
    migrate_parser.add_argument(
        "--to",
        dest="target",
        required=True,
        help="Target tenant ID",
    )
    migrate_parser.add_argument(
        "--include-state",
        action="store_true",
        default=True,
        help="Include sync state",
    )
    migrate_parser.add_argument(
        "--include-cache",
        action="store_true",
        default=True,
        help="Include cache",
    )
    migrate_parser.add_argument(
        "--include-backups",
        action="store_true",
        default=True,
        help="Include backups",
    )
    migrate_parser.add_argument(
        "--move",
        action="store_true",
        help="Move instead of copy",
    )

    # tenant status
    status_parser = tenant_subparsers.add_parser(
        "status",
        help="Show tenant status",
        description="Show status and statistics for tenants",
    )
    status_parser.add_argument(
        "id",
        nargs="?",
        help="Tenant ID (defaults to all)",
    )
    status_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    # tenant config
    config_parser = tenant_subparsers.add_parser(
        "config",
        help="Manage tenant configuration",
        description="View and manage tenant configurations",
    )
    config_parser.add_argument(
        "id",
        nargs="?",
        help="Tenant ID (defaults to current)",
    )
    config_parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate configuration",
    )
    config_parser.add_argument(
        "--show-path",
        action="store_true",
        help="Show config file paths",
    )

    # tenant cache
    cache_parser = tenant_subparsers.add_parser(
        "cache",
        help="Manage tenant cache",
        description="View and manage tenant cache",
    )
    cache_parser.add_argument(
        "id",
        nargs="?",
        help="Tenant ID (defaults to current)",
    )
    cache_parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear cache",
    )
    cache_parser.add_argument(
        "--stats",
        action="store_true",
        help="Show cache statistics",
    )


# =============================================================================
# Command Handlers
# =============================================================================


def handle_tenant_command(args: argparse.Namespace, console: Console) -> int:
    """
    Handle tenant commands.

    Args:
        args: Parsed arguments
        console: Output console

    Returns:
        Exit code
    """
    command = args.tenant_command

    if command == "list":
        return _cmd_tenant_list(args, console)
    if command == "create":
        return _cmd_tenant_create(args, console)
    if command == "use":
        return _cmd_tenant_use(args, console)
    if command == "show":
        return _cmd_tenant_show(args, console)
    if command == "delete":
        return _cmd_tenant_delete(args, console)
    if command == "archive":
        return _cmd_tenant_archive(args, console)
    if command == "activate":
        return _cmd_tenant_activate(args, console)
    if command == "migrate":
        return _cmd_tenant_migrate(args, console)
    if command == "status":
        return _cmd_tenant_status(args, console)
    if command == "config":
        return _cmd_tenant_config(args, console)
    if command == "cache":
        return _cmd_tenant_cache(args, console)
    console.error("Unknown tenant command. Use 'spectra tenant --help'")
    return 1


def _cmd_tenant_list(args: argparse.Namespace, console: Console) -> int:
    """List all tenants."""
    manager = get_tenant_manager()
    tenants = manager.list_tenants(include_inactive=args.all)

    if args.json:
        data = [t.to_dict() for t in tenants]
        console.print(json.dumps(data, indent=2))
        return 0

    if not tenants:
        console.info("No tenants configured")
        return 0

    console.section("Tenants")
    console.print()

    # Table header
    headers = ["ID", "Name", "Status", "Created"]
    widths = [20, 30, 12, 20]

    header_row = "  ".join(h.ljust(w) for h, w in zip(headers, widths, strict=True))
    console.print(f"  {header_row}")
    console.print(f"  {'-' * sum(widths)}")

    # Current tenant
    current = manager.current_tenant.id

    for tenant in tenants:
        marker = "→ " if tenant.id == current else "  "

        row = [
            tenant.id[:20].ljust(20),
            tenant.name[:30].ljust(30),
            tenant.status.value.ljust(12),
            tenant.created_at[:19].ljust(20),
        ]
        console.print(f"{marker}{'  '.join(row)}")

    console.print()
    console.info(f"Total: {len(tenants)} tenant(s)")

    return 0


def _cmd_tenant_create(args: argparse.Namespace, console: Console) -> int:
    """Create a new tenant."""
    manager = get_tenant_manager()

    try:
        isolation = IsolationLevel(args.isolation.replace("-", "_"))
        tenant = manager.create(
            id=args.id,
            name=args.name or args.id,
            description=args.description,
            activate=args.activate,
            isolation_level=isolation,
        )

        console.success(f"Created tenant: {tenant.id}")
        console.detail(f"  Name: {tenant.name}")
        console.detail(f"  Status: {tenant.status.value}")
        console.detail(f"  Isolation: {tenant.isolation_level.value}")

        paths = manager.registry.get_paths(tenant)
        console.detail(f"  Directory: {paths.root}")

        if args.activate:
            console.info(f"Tenant '{tenant.id}' is now active")

        return 0

    except ValueError as e:
        console.error(str(e))
        return 1


def _cmd_tenant_use(args: argparse.Namespace, console: Console) -> int:
    """Switch to a tenant."""
    manager = get_tenant_manager()

    try:
        tenant = manager.use(args.id)
        console.success(f"Switched to tenant: {tenant.id}")

        # Show config paths
        paths = manager.registry.get_paths(tenant)
        console.detail(f"  Config: {paths.config_file}")
        console.detail(f"  State: {paths.state_dir}")

        return 0

    except KeyError:
        console.error(f"Tenant '{args.id}' not found")
        return 1
    except RuntimeError as e:
        console.error(str(e))
        return 1


def _cmd_tenant_show(args: argparse.Namespace, console: Console) -> int:
    """Show tenant details."""
    manager = get_tenant_manager()

    tenant_id = args.id or manager.current_tenant.id
    tenant = manager.get_tenant(tenant_id)

    if not tenant:
        console.error(f"Tenant '{tenant_id}' not found")
        return 1

    if args.json:
        data = tenant.to_dict()
        paths = manager.registry.get_paths(tenant)
        data["paths"] = paths.get_all_paths()
        data["paths"] = {k: str(v) for k, v in data["paths"].items()}
        console.print(json.dumps(data, indent=2))
        return 0

    paths = manager.registry.get_paths(tenant)

    console.section(f"Tenant: {tenant.id}")
    console.print()
    console.info(f"Name: {tenant.name}")
    console.info(f"Description: {tenant.description or '(none)'}")
    console.info(f"Status: {tenant.status.value}")
    console.info(f"Isolation: {tenant.isolation_level.value}")
    console.print()
    console.info("Timestamps:")
    console.detail(f"  Created: {tenant.created_at}")
    console.detail(f"  Updated: {tenant.updated_at}")
    console.print()
    console.info("Paths:")
    console.detail(f"  Root: {paths.root}")
    console.detail(f"  Config: {paths.config_dir}")
    console.detail(f"  State: {paths.state_dir}")
    console.detail(f"  Cache: {paths.cache_dir}")
    console.detail(f"  Backups: {paths.backup_dir}")

    if tenant.metadata:
        console.print()
        console.info("Metadata:")
        for key, value in tenant.metadata.items():
            console.detail(f"  {key}: {value}")

    return 0


def _cmd_tenant_delete(args: argparse.Namespace, console: Console) -> int:
    """Delete a tenant."""
    manager = get_tenant_manager()

    try:
        # Confirm deletion
        if not args.force:
            console.warning(f"About to delete tenant: {args.id}")
            if args.delete_data:
                console.warning("This will also delete all tenant data!")

            response = input("Type 'yes' to confirm: ")
            if response.lower() != "yes":
                console.info("Cancelled")
                return 0

        manager.delete_tenant(
            args.id,
            delete_data=args.delete_data,
            force=args.force,
        )

        console.success(f"Deleted tenant: {args.id}")
        return 0

    except (KeyError, ValueError, RuntimeError) as e:
        console.error(str(e))
        return 1


def _cmd_tenant_archive(args: argparse.Namespace, console: Console) -> int:
    """Archive a tenant."""
    manager = get_tenant_manager()

    try:
        tenant = manager.registry.archive(args.id)
        console.success(f"Archived tenant: {tenant.id}")
        return 0

    except KeyError:
        console.error(f"Tenant '{args.id}' not found")
        return 1


def _cmd_tenant_activate(args: argparse.Namespace, console: Console) -> int:
    """Activate a tenant."""
    manager = get_tenant_manager()

    try:
        tenant = manager.registry.activate(args.id)
        console.success(f"Activated tenant: {tenant.id}")
        return 0

    except KeyError:
        console.error(f"Tenant '{args.id}' not found")
        return 1


def _cmd_tenant_migrate(args: argparse.Namespace, console: Console) -> int:
    """Migrate data between tenants."""
    manager = get_tenant_manager()
    migrator = TenantMigrator(manager)

    console.section("Tenant Migration")
    console.info(f"Source: {args.source}")
    console.info(f"Target: {args.target}")
    console.print()

    try:
        results = migrator.migrate_from_default(
            target_tenant_id=args.target,
            include_state=args.include_state,
            include_cache=args.include_cache,
            include_backups=args.include_backups,
            copy_mode=not args.move,
        )

        console.success("Migration complete!")
        console.detail(f"  Config files: {results['config_files']}")
        console.detail(f"  State files: {results['state_files']}")
        console.detail(f"  Cache files: {results['cache_files']}")
        console.detail(f"  Backup files: {results['backup_files']}")

        return 0

    except Exception as e:
        console.error(f"Migration failed: {e}")
        return 1


def _cmd_tenant_status(args: argparse.Namespace, console: Console) -> int:
    """Show tenant status and statistics."""
    manager = get_tenant_manager()
    state_query = CrossTenantStateQuery(manager)

    if args.id:
        # Show status for specific tenant
        stats = state_query.get_tenant_stats(args.id)
        if not stats:
            console.error(f"Tenant '{args.id}' not found")
            return 1

        if args.json:
            console.print(json.dumps(stats, indent=2))
            return 0

        console.section(f"Tenant Status: {stats['tenant_name']}")
        console.print()
        console.info(f"Total sync sessions: {stats['total_sessions']}")
        console.detail(f"  Completed: {stats['completed_sessions']}")
        console.detail(f"  Failed: {stats['failed_sessions']}")
        console.detail(f"  In progress: {stats['in_progress_sessions']}")
        console.print()
        console.info(f"Unique epics: {stats['unique_epics']}")
        console.info(f"Unique files: {stats['unique_files']}")

        return 0

    # Show status for all tenants
    all_stats = []
    for tenant in manager.list_tenants():
        stats = state_query.get_tenant_stats(tenant.id)
        if stats:
            all_stats.append(stats)

    if args.json:
        console.print(json.dumps(all_stats, indent=2))
        return 0

    console.section("All Tenants Status")
    console.print()

    headers = ["Tenant", "Sessions", "Completed", "Failed", "Epics"]
    widths = [20, 10, 10, 10, 10]

    header_row = "  ".join(h.ljust(w) for h, w in zip(headers, widths, strict=True))
    console.print(f"  {header_row}")
    console.print(f"  {'-' * sum(widths)}")

    for stats in all_stats:
        row = [
            stats["tenant_name"][:20].ljust(20),
            str(stats["total_sessions"]).ljust(10),
            str(stats["completed_sessions"]).ljust(10),
            str(stats["failed_sessions"]).ljust(10),
            str(stats["unique_epics"]).ljust(10),
        ]
        console.print(f"  {'  '.join(row)}")

    return 0


def _cmd_tenant_config(args: argparse.Namespace, console: Console) -> int:
    """Manage tenant configuration."""
    manager = get_tenant_manager()
    config_manager = TenantConfigManager(manager)

    tenant_id = args.id or manager.current_tenant.id

    if args.show_path:
        paths = manager.registry.get_paths(tenant_id)
        console.info(f"Config file: {paths.config_file}")
        console.info(f"Env file: {paths.env_file}")
        return 0

    if args.validate:
        from spectryn.core.tenant_config import TenantConfigProvider

        provider = TenantConfigProvider(tenant_id=tenant_id)
        errors = provider.validate()

        if errors:
            console.error("Configuration validation failed:")
            for error in errors:
                console.detail(f"  - {error}")
            return 1
        console.success("Configuration is valid")
        return 0

    # Show config status
    statuses = config_manager.list_tenant_configs()
    status = next((s for s in statuses if s["tenant_id"] == tenant_id), None)

    if not status:
        console.error(f"Tenant '{tenant_id}' not found")
        return 1

    console.section(f"Configuration: {tenant_id}")
    console.print()
    console.info(f"Config file: {status['config_file_path']}")
    console.detail(f"  Exists: {status['has_config_file']}")
    console.info(f"Env file: {status['env_file_path']}")
    console.detail(f"  Exists: {status['has_env_file']}")
    console.print()
    console.info(f"Valid: {status['is_valid']}")
    if status["validation_errors"]:
        console.warning("Validation errors:")
        for error in status["validation_errors"]:
            console.detail(f"  - {error}")

    return 0


def _cmd_tenant_cache(args: argparse.Namespace, console: Console) -> int:
    """Manage tenant cache."""
    manager = get_tenant_manager()
    tenant_id = args.id or manager.current_tenant.id

    cache_store = TenantCacheStore(
        tenant_manager=manager,
        tenant_id=tenant_id,
    )

    if args.clear:
        count = cache_store.clear()
        console.success(f"Cleared {count} cache entries")
        return 0

    if args.stats:
        stats = cache_store.get_stats()
        console.section(f"Cache Statistics: {tenant_id}")
        console.print()
        console.info(f"Memory entries: {stats['memory_entries']}")
        console.info(f"Disk entries: {stats['disk_entries']}")
        console.info(f"Total hits: {stats['total_hits']}")
        console.info(f"Disk usage: {stats['disk_usage_bytes']:,} bytes")
        console.info(f"Max entries: {stats['max_entries']}")
        console.info(f"Default TTL: {stats['default_ttl']}s")
        return 0

    # Show basic cache info
    stats = cache_store.get_stats()
    console.info(f"Cache for tenant: {tenant_id}")
    console.detail(f"  Entries: {stats['disk_entries']}")
    console.detail(f"  Directory: {cache_store.cache_dir}")

    return 0


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "handle_tenant_command",
    "register_tenant_commands",
]
