"""
CLI commands for data retention policy management.

Provides commands for:
- Listing and managing retention policies
- Running cleanup operations
- Viewing storage statistics
- Applying policy presets
"""

from __future__ import annotations

import json
import logging
from typing import Any

from spectryn.core.retention import (
    CleanupResult,
    CleanupTrigger,
    DataType,
    PolicyPreset,
    RetentionPolicy,
    RetentionRule,
    RetentionUnit,
    get_retention_manager,
    get_storage_stats,
)


logger = logging.getLogger(__name__)


# =============================================================================
# Table Formatting Helpers
# =============================================================================


def _format_policy_table(policies: list[RetentionPolicy]) -> str:
    """Format policies as an ASCII table."""
    if not policies:
        return "No policies configured."

    # Headers
    headers = ["ID", "Name", "Preset", "Triggers", "Schedule", "Scope", "Status"]
    rows: list[list[str]] = []

    for policy in policies:
        triggers = ", ".join(t.value for t in policy.triggers)
        schedule = (
            f"{policy.schedule_hours}h" if CleanupTrigger.SCHEDULED in policy.triggers else "-"
        )

        scope = "global"
        if policy.workspace_id:
            scope = f"workspace:{policy.workspace_id}"
        elif policy.tenant_id:
            scope = f"tenant:{policy.tenant_id}"

        status = "✓ enabled" if policy.enabled else "✗ disabled"

        rows.append(
            [
                policy.id,
                policy.name,
                policy.preset.value,
                triggers,
                schedule,
                scope,
                status,
            ]
        )

    return _make_table(headers, rows)


def _format_rules_table(rules: list[RetentionRule]) -> str:
    """Format rules as an ASCII table."""
    if not rules:
        return "No rules configured."

    headers = ["Type", "Max Age", "Max Count", "Max Size", "Min Keep", "Pattern", "Status"]
    rows: list[list[str]] = []

    for rule in rules:
        max_age = f"{rule.max_age} {rule.max_age_unit.value}" if rule.max_age else "-"
        max_count = str(rule.max_count) if rule.max_count else "-"
        max_size = f"{rule.max_size_mb} MB" if rule.max_size_mb else "-"
        pattern = rule.pattern or "*"
        status = "✓" if rule.enabled else "✗"

        rows.append(
            [
                rule.data_type.value,
                max_age,
                max_count,
                max_size,
                str(rule.min_keep),
                pattern,
                status,
            ]
        )

    return _make_table(headers, rows)


def _format_storage_table(summary: dict[str, Any]) -> str:
    """Format storage summary as an ASCII table."""
    headers = ["Data Type", "Path", "Items", "Size"]
    rows: list[list[str]] = []

    for data_type, info in summary.get("data_types", {}).items():
        rows.append(
            [
                data_type,
                info.get("path", ""),
                str(info.get("items", 0)),
                info.get("size_human", "0 B"),
            ]
        )

    if not rows:
        return "No data found."

    # Add total row
    rows.append(
        [
            "TOTAL",
            "",
            str(summary.get("total_items", 0)),
            summary.get("total_size_human", "0 B"),
        ]
    )

    return _make_table(headers, rows)


def _format_cleanup_table(result: CleanupResult) -> str:
    """Format cleanup result as an ASCII table."""
    headers = ["Path", "Type", "Size", "Age (days)", "Reason"]
    rows: list[list[str]] = []

    for item in result.items_cleaned[:50]:  # Limit to 50 items
        rows.append(
            [
                str(item.path.name),
                item.data_type.value,
                _format_bytes(item.size_bytes),
                f"{item.age_days:.1f}",
                item.reason[:40] + "..." if len(item.reason) > 40 else item.reason,
            ]
        )

    if not rows:
        return "No items to clean up."

    if len(result.items_cleaned) > 50:
        rows.append(["...", f"({len(result.items_cleaned) - 50} more)", "", "", ""])

    return _make_table(headers, rows)


def _make_table(headers: list[str], rows: list[list[str]]) -> str:
    """Create an ASCII table from headers and rows."""
    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(str(cell)))

    # Build table
    lines: list[str] = []

    # Header
    header_line = " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    lines.append(header_line)
    lines.append("-" * len(header_line))

    # Rows
    for row in rows:
        row_line = " | ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row))
        lines.append(row_line)

    return "\n".join(lines)


def _format_bytes(bytes_val: int) -> str:
    """Format bytes to human-readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f} TB"


# =============================================================================
# CLI Command Handlers
# =============================================================================


def cmd_retention_list(
    output_format: str = "table",
) -> int:
    """
    List all retention policies.

    Args:
        output_format: Output format (table, json).

    Returns:
        Exit code (0 for success).
    """
    manager = get_retention_manager()
    policies = manager.registry.list_all()

    if output_format == "json":
        data = [p.to_dict() for p in policies]
        print(json.dumps(data, indent=2))
    elif not policies:
        print("No retention policies configured.")
        print("\nUse 'spectra retention apply <preset>' to configure a policy.")
        print("Available presets: minimal, standard, extended, archive")
    else:
        print("Retention Policies:")
        print()
        print(_format_policy_table(policies))

    return 0


def cmd_retention_show(
    policy_id: str,
    output_format: str = "table",
) -> int:
    """
    Show details of a retention policy.

    Args:
        policy_id: Policy ID to show.
        output_format: Output format (table, json).

    Returns:
        Exit code (0 for success, 1 for error).
    """
    manager = get_retention_manager()
    policy = manager.registry.get(policy_id)

    if policy is None:
        print(f"Error: Policy not found: {policy_id}")
        return 1

    if output_format == "json":
        print(json.dumps(policy.to_dict(), indent=2))
    else:
        print(f"Policy: {policy.name}")
        print(f"  ID: {policy.id}")
        print(f"  Preset: {policy.preset.value}")
        print(f"  Description: {policy.description or '(none)'}")
        print(f"  Enabled: {'yes' if policy.enabled else 'no'}")
        print(f"  Created: {policy.created_at}")
        print(f"  Updated: {policy.updated_at}")
        print()

        scope = "global"
        if policy.workspace_id:
            scope = f"workspace:{policy.workspace_id}"
        elif policy.tenant_id:
            scope = f"tenant:{policy.tenant_id}"
        print(f"  Scope: {scope}")

        triggers = ", ".join(t.value for t in policy.triggers)
        print(f"  Triggers: {triggers}")

        if CleanupTrigger.SCHEDULED in policy.triggers:
            print(f"  Schedule: every {policy.schedule_hours} hours")

        print()
        print("Rules:")
        print(_format_rules_table(policy.rules))

    return 0


def cmd_retention_apply(
    preset: str,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
) -> int:
    """
    Apply a preset retention policy.

    Args:
        preset: Preset name (minimal, standard, extended, archive).
        tenant_id: Optional tenant scope.
        workspace_id: Optional workspace scope.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    try:
        preset_enum = PolicyPreset(preset)
    except ValueError:
        print(f"Error: Invalid preset '{preset}'")
        print("Available presets: minimal, standard, extended, archive")
        return 1

    manager = get_retention_manager()

    # Import and use the preset function
    from spectryn.core.retention import get_preset_policy

    policy = get_preset_policy(preset_enum, tenant_id, workspace_id)

    # Generate unique ID for scoped policies
    if tenant_id or workspace_id:
        parts = [preset]
        if tenant_id:
            parts.append(f"tenant-{tenant_id}")
        if workspace_id:
            parts.append(f"workspace-{workspace_id}")
        policy.id = "-".join(parts)

    # Try to create or update
    try:
        policy = manager.registry.create(policy)
        print(f"✓ Created retention policy: {policy.id}")
    except ValueError:
        policy = manager.registry.update(policy)
        print(f"✓ Updated retention policy: {policy.id}")

    print()
    print(f"  Preset: {preset}")
    scope = "global"
    if workspace_id:
        scope = f"workspace:{workspace_id}"
    elif tenant_id:
        scope = f"tenant:{tenant_id}"
    print(f"  Scope: {scope}")
    print()
    print("Rules:")
    print(_format_rules_table(policy.rules))

    return 0


def cmd_retention_delete(
    policy_id: str,
    force: bool = False,
) -> int:
    """
    Delete a retention policy.

    Args:
        policy_id: Policy ID to delete.
        force: Skip confirmation.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    manager = get_retention_manager()
    policy = manager.registry.get(policy_id)

    if policy is None:
        print(f"Error: Policy not found: {policy_id}")
        return 1

    if not force:
        print(f"Delete policy '{policy.name}' ({policy_id})?")
        response = input("Type 'yes' to confirm: ")
        if response.lower() != "yes":
            print("Cancelled.")
            return 1

    if manager.registry.delete(policy_id):
        print(f"✓ Deleted policy: {policy_id}")
        return 0
    print(f"Error: Failed to delete policy: {policy_id}")
    return 1


def cmd_retention_enable(
    policy_id: str,
) -> int:
    """
    Enable a retention policy.

    Args:
        policy_id: Policy ID to enable.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    manager = get_retention_manager()
    policy = manager.registry.get(policy_id)

    if policy is None:
        print(f"Error: Policy not found: {policy_id}")
        return 1

    policy.enabled = True
    manager.registry.update(policy)
    print(f"✓ Enabled policy: {policy_id}")
    return 0


def cmd_retention_disable(
    policy_id: str,
) -> int:
    """
    Disable a retention policy.

    Args:
        policy_id: Policy ID to disable.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    manager = get_retention_manager()
    policy = manager.registry.get(policy_id)

    if policy is None:
        print(f"Error: Policy not found: {policy_id}")
        return 1

    policy.enabled = False
    manager.registry.update(policy)
    print(f"✓ Disabled policy: {policy_id}")
    return 0


def cmd_retention_cleanup(
    dry_run: bool = True,
    policy_id: str | None = None,
    data_types: list[str] | None = None,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
    output_format: str = "table",
) -> int:
    """
    Run cleanup based on retention policy.

    Args:
        dry_run: If True, only preview what would be cleaned.
        policy_id: Specific policy to use (or effective policy).
        data_types: Specific data types to clean.
        tenant_id: Tenant scope.
        workspace_id: Workspace scope.
        output_format: Output format (table, json).

    Returns:
        Exit code (0 for success, 1 for error).
    """
    manager = get_retention_manager()

    # Get policy
    policy = None
    if policy_id:
        policy = manager.registry.get(policy_id)
        if policy is None:
            print(f"Error: Policy not found: {policy_id}")
            return 1

    # Parse data types
    dt_list: list[DataType] | None = None
    if data_types:
        try:
            dt_list = [DataType(dt) for dt in data_types]
        except ValueError as e:
            print(f"Error: Invalid data type: {e}")
            print("Available types: backup, state, cache, logs")
            return 1

    # Run cleanup
    result = manager.run_cleanup(
        policy=policy,
        dry_run=dry_run,
        data_types=dt_list,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
    )

    if output_format == "json":
        print(json.dumps(result.to_dict(), indent=2))
    else:
        if dry_run:
            print("DRY RUN - No changes made")
            print()

        print(result.summary())

        if result.items_cleaned:
            print()
            print("Items to clean:")
            print(_format_cleanup_table(result))

    return 0 if result.success else 1


def cmd_retention_stats(
    tenant_id: str | None = None,
    workspace_id: str | None = None,
    output_format: str = "table",
) -> int:
    """
    Show storage statistics.

    Args:
        tenant_id: Tenant scope.
        workspace_id: Workspace scope.
        output_format: Output format (table, json).

    Returns:
        Exit code (0 for success).
    """
    summary = get_storage_stats(tenant_id, workspace_id)

    if output_format == "json":
        print(json.dumps(summary, indent=2))
    else:
        scope = "global"
        if workspace_id:
            scope = f"workspace:{workspace_id}"
        elif tenant_id:
            scope = f"tenant:{tenant_id}"

        print(f"Storage Statistics ({scope})")
        print()
        print(_format_storage_table(summary))

    return 0


def cmd_retention_presets() -> int:
    """
    Show available policy presets.

    Returns:
        Exit code (0 for success).
    """
    print("Available Retention Policy Presets:")
    print()

    presets = [
        ("minimal", "Aggressive cleanup, minimal storage", "3 days, max 3 backups"),
        ("standard", "Balanced defaults", "30 days, max 10 backups"),
        ("extended", "Extended retention for compliance", "90 days, max 30 backups"),
        ("archive", "Long-term archival", "365 days, max 100 backups"),
    ]

    headers = ["Preset", "Description", "Backup Retention"]
    rows = [[p[0], p[1], p[2]] for p in presets]
    print(_make_table(headers, rows))

    print()
    print("Use 'spectra retention apply <preset>' to apply a preset.")
    print("Add --tenant or --workspace to scope the policy.")

    return 0


def cmd_retention_create(
    policy_id: str,
    name: str,
    backup_days: int | None = None,
    backup_count: int | None = None,
    state_days: int | None = None,
    state_count: int | None = None,
    cache_days: int | None = None,
    cache_size_mb: float | None = None,
    logs_days: int | None = None,
    logs_size_mb: float | None = None,
    triggers: list[str] | None = None,
    schedule_hours: int = 24,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
) -> int:
    """
    Create a custom retention policy.

    Args:
        policy_id: Unique policy identifier.
        name: Human-readable name.
        backup_days: Max age for backups in days.
        backup_count: Max number of backups.
        state_days: Max age for state files in days.
        state_count: Max number of state files.
        cache_days: Max age for cache in days.
        cache_size_mb: Max cache size in MB.
        logs_days: Max age for logs in days.
        logs_size_mb: Max logs size in MB.
        triggers: Cleanup triggers (manual, startup, after_sync, scheduled).
        schedule_hours: Hours between scheduled cleanups.
        tenant_id: Tenant scope.
        workspace_id: Workspace scope.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    manager = get_retention_manager()

    # Parse triggers
    trigger_list: list[CleanupTrigger] = [CleanupTrigger.MANUAL]
    if triggers:
        try:
            trigger_list = [CleanupTrigger(t) for t in triggers]
        except ValueError as e:
            print(f"Error: Invalid trigger: {e}")
            print("Available triggers: manual, startup, after_sync, scheduled")
            return 1

    # Build rules
    rules: list[RetentionRule] = []

    if backup_days or backup_count:
        rules.append(
            RetentionRule(
                data_type=DataType.BACKUP,
                max_age=backup_days,
                max_count=backup_count,
                min_keep=1,
                description=f"Backups: {backup_days or '-'} days, {backup_count or '-'} max",
            )
        )

    if state_days or state_count:
        rules.append(
            RetentionRule(
                data_type=DataType.STATE,
                max_age=state_days,
                max_count=state_count,
                min_keep=1,
                description=f"State: {state_days or '-'} days, {state_count or '-'} max",
            )
        )

    if cache_days or cache_size_mb:
        rules.append(
            RetentionRule(
                data_type=DataType.CACHE,
                max_age=cache_days,
                max_size_mb=cache_size_mb,
                min_keep=0,
                description=f"Cache: {cache_days or '-'} days, {cache_size_mb or '-'} MB max",
            )
        )

    if logs_days or logs_size_mb:
        rules.append(
            RetentionRule(
                data_type=DataType.LOGS,
                max_age=logs_days,
                max_size_mb=logs_size_mb,
                min_keep=1,
                description=f"Logs: {logs_days or '-'} days, {logs_size_mb or '-'} MB max",
            )
        )

    if not rules:
        print("Error: At least one retention rule is required.")
        print("Use --backup-days, --state-days, --cache-days, or --logs-days.")
        return 1

    # Create policy
    policy = RetentionPolicy(
        id=policy_id,
        name=name,
        preset=PolicyPreset.CUSTOM,
        rules=rules,
        triggers=trigger_list,
        schedule_hours=schedule_hours,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
    )

    try:
        policy = manager.registry.create(policy)
        print(f"✓ Created retention policy: {policy.id}")
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    print()
    print("Rules:")
    print(_format_rules_table(policy.rules))

    return 0


def cmd_retention_add_rule(
    policy_id: str,
    data_type: str,
    max_age: int | None = None,
    max_age_unit: str = "days",
    max_count: int | None = None,
    max_size_mb: float | None = None,
    min_keep: int = 1,
    pattern: str | None = None,
) -> int:
    """
    Add a rule to an existing policy.

    Args:
        policy_id: Policy ID to modify.
        data_type: Data type for the rule.
        max_age: Maximum age.
        max_age_unit: Unit for max_age (hours, days, weeks, months).
        max_count: Maximum count.
        max_size_mb: Maximum size in MB.
        min_keep: Minimum items to keep.
        pattern: Glob pattern for matching.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    manager = get_retention_manager()
    policy = manager.registry.get(policy_id)

    if policy is None:
        print(f"Error: Policy not found: {policy_id}")
        return 1

    try:
        dt = DataType(data_type)
    except ValueError:
        print(f"Error: Invalid data type: {data_type}")
        print("Available types: backup, state, cache, logs")
        return 1

    try:
        unit = RetentionUnit(max_age_unit)
    except ValueError:
        print(f"Error: Invalid unit: {max_age_unit}")
        print("Available units: hours, days, weeks, months")
        return 1

    rule = RetentionRule(
        data_type=dt,
        max_age=max_age,
        max_age_unit=unit,
        max_count=max_count,
        max_size_mb=max_size_mb,
        min_keep=min_keep,
        pattern=pattern,
    )

    policy.add_rule(rule)
    manager.registry.update(policy)

    print(f"✓ Added rule to policy: {policy_id}")
    print()
    print("Rules:")
    print(_format_rules_table(policy.rules))

    return 0


def cmd_retention_remove_rule(
    policy_id: str,
    data_type: str,
    pattern: str | None = None,
) -> int:
    """
    Remove a rule from a policy.

    Args:
        policy_id: Policy ID to modify.
        data_type: Data type of the rule to remove.
        pattern: Pattern of the rule to remove.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    manager = get_retention_manager()
    policy = manager.registry.get(policy_id)

    if policy is None:
        print(f"Error: Policy not found: {policy_id}")
        return 1

    try:
        dt = DataType(data_type)
    except ValueError:
        print(f"Error: Invalid data type: {data_type}")
        return 1

    if policy.remove_rule(dt, pattern):
        manager.registry.update(policy)
        print(f"✓ Removed rule from policy: {policy_id}")
        return 0
    print(f"Error: Rule not found: {data_type}")
    return 1


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    "cmd_retention_add_rule",
    "cmd_retention_apply",
    "cmd_retention_cleanup",
    "cmd_retention_create",
    "cmd_retention_delete",
    "cmd_retention_disable",
    "cmd_retention_enable",
    "cmd_retention_list",
    "cmd_retention_presets",
    "cmd_retention_remove_rule",
    "cmd_retention_show",
    "cmd_retention_stats",
]
