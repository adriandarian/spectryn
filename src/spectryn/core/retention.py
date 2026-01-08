"""
Data Retention Policies - Automatic cleanup of old data.

This module provides comprehensive data retention management for Spectra,
allowing users to configure automatic cleanup of:
- Backups (sync snapshots)
- State files (sync sessions, issue mappings)
- Cache data (tracker metadata, API responses)
- Logs (application logs)

Key Features:
- Policy types: Different policies for different data types
- Retention rules: Age-based, count-based, size-based cleanup
- Policy presets: Pre-configured policy sets (minimal, standard, extended)
- Scheduling: Automatic cleanup on intervals
- Dry-run mode: Preview what would be cleaned up
- Tenant/workspace awareness: Apply policies per tenant or workspace
- Reporting: Track cleanup operations and space saved
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

RETENTION_CONFIG_FILE = "retention.json"
DEFAULT_SPECTRA_DIR = Path.home() / ".spectra"


# =============================================================================
# Enums
# =============================================================================


class DataType(Enum):
    """Types of data that can be retained/cleaned."""

    BACKUP = "backup"  # Sync backups
    STATE = "state"  # Sync state files
    CACHE = "cache"  # Cache data
    LOGS = "logs"  # Log files
    TEMP = "temp"  # Temporary files
    ALL = "all"  # All data types


class RetentionUnit(Enum):
    """Units for retention periods."""

    HOURS = "hours"
    DAYS = "days"
    WEEKS = "weeks"
    MONTHS = "months"


class CleanupTrigger(Enum):
    """When cleanup should be triggered."""

    MANUAL = "manual"  # Only on explicit request
    STARTUP = "startup"  # On application startup
    AFTER_SYNC = "after_sync"  # After each sync operation
    SCHEDULED = "scheduled"  # On a schedule
    THRESHOLD = "threshold"  # When thresholds are exceeded


class PolicyPreset(Enum):
    """Pre-configured policy presets."""

    MINIMAL = "minimal"  # Aggressive cleanup, minimal storage
    STANDARD = "standard"  # Balanced defaults
    EXTENDED = "extended"  # Keep more history
    ARCHIVE = "archive"  # Keep almost everything
    CUSTOM = "custom"  # User-defined


# =============================================================================
# Retention Rule
# =============================================================================


@dataclass
class RetentionRule:
    """
    A single retention rule for a data type.

    Rules can specify multiple conditions (all are checked):
    - max_age: Maximum age of items
    - max_count: Maximum number of items to keep
    - max_size_mb: Maximum total size in MB
    - min_keep: Minimum items to always keep
    - pattern: Glob pattern for file matching

    Attributes:
        data_type: Type of data this rule applies to
        max_age: Maximum age (None = no age limit)
        max_age_unit: Unit for max_age
        max_count: Maximum number of items (None = no count limit)
        max_size_mb: Maximum total size in MB (None = no size limit)
        min_keep: Minimum items to always keep
        pattern: Glob pattern for file matching (None = all files)
        enabled: Whether this rule is active
        description: Human-readable description
    """

    __slots__ = (
        "data_type",
        "description",
        "enabled",
        "max_age",
        "max_age_unit",
        "max_count",
        "max_size_mb",
        "min_keep",
        "pattern",
    )

    data_type: DataType
    max_age: int | None
    max_age_unit: RetentionUnit
    max_count: int | None
    max_size_mb: float | None
    min_keep: int
    pattern: str | None
    enabled: bool
    description: str

    def __init__(
        self,
        data_type: DataType,
        max_age: int | None = None,
        max_age_unit: RetentionUnit = RetentionUnit.DAYS,
        max_count: int | None = None,
        max_size_mb: float | None = None,
        min_keep: int = 1,
        pattern: str | None = None,
        enabled: bool = True,
        description: str = "",
    ) -> None:
        """Initialize a retention rule."""
        self.data_type = data_type
        self.max_age = max_age
        self.max_age_unit = max_age_unit
        self.max_count = max_count
        self.max_size_mb = max_size_mb
        self.min_keep = min_keep
        self.pattern = pattern
        self.enabled = enabled
        self.description = description

    def __hash__(self) -> int:
        """Hash by data type and pattern."""
        return hash((self.data_type, self.pattern))

    def __eq__(self, other: object) -> bool:
        """Equality by data type and pattern."""
        if not isinstance(other, RetentionRule):
            return NotImplemented
        return self.data_type == other.data_type and self.pattern == other.pattern

    @property
    def max_age_timedelta(self) -> timedelta | None:
        """Get max_age as a timedelta."""
        if self.max_age is None:
            return None

        if self.max_age_unit == RetentionUnit.HOURS:
            return timedelta(hours=self.max_age)
        if self.max_age_unit == RetentionUnit.DAYS:
            return timedelta(days=self.max_age)
        if self.max_age_unit == RetentionUnit.WEEKS:
            return timedelta(weeks=self.max_age)
        if self.max_age_unit == RetentionUnit.MONTHS:
            return timedelta(days=self.max_age * 30)  # Approximate
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "data_type": self.data_type.value,
            "max_age": self.max_age,
            "max_age_unit": self.max_age_unit.value,
            "max_count": self.max_count,
            "max_size_mb": self.max_size_mb,
            "min_keep": self.min_keep,
            "pattern": self.pattern,
            "enabled": self.enabled,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RetentionRule:
        """Create from dictionary."""
        return cls(
            data_type=DataType(data["data_type"]),
            max_age=data.get("max_age"),
            max_age_unit=RetentionUnit(data.get("max_age_unit", "days")),
            max_count=data.get("max_count"),
            max_size_mb=data.get("max_size_mb"),
            min_keep=data.get("min_keep", 1),
            pattern=data.get("pattern"),
            enabled=data.get("enabled", True),
            description=data.get("description", ""),
        )


# =============================================================================
# Retention Policy
# =============================================================================


@dataclass
class RetentionPolicy:
    """
    A complete retention policy with multiple rules.

    A policy combines:
    - Multiple retention rules for different data types
    - Cleanup triggers and schedules
    - Scope (global, per-tenant, per-workspace)

    Attributes:
        id: Unique policy identifier
        name: Human-readable policy name
        description: Policy description
        preset: Policy preset (if based on preset)
        rules: List of retention rules
        triggers: When cleanup should be triggered
        schedule_hours: Hours between scheduled cleanups
        tenant_id: Tenant scope (None = global)
        workspace_id: Workspace scope (None = all workspaces)
        enabled: Whether this policy is active
        created_at: Timestamp when policy was created
        updated_at: Timestamp of last update
    """

    __slots__ = (
        "created_at",
        "description",
        "enabled",
        "id",
        "name",
        "preset",
        "rules",
        "schedule_hours",
        "tenant_id",
        "triggers",
        "updated_at",
        "workspace_id",
    )

    id: str
    name: str
    description: str
    preset: PolicyPreset
    rules: list[RetentionRule]
    triggers: list[CleanupTrigger]
    schedule_hours: int
    tenant_id: str | None
    workspace_id: str | None
    enabled: bool
    created_at: str
    updated_at: str

    def __init__(
        self,
        id: str,
        name: str,
        description: str = "",
        preset: PolicyPreset = PolicyPreset.CUSTOM,
        rules: list[RetentionRule] | None = None,
        triggers: list[CleanupTrigger] | None = None,
        schedule_hours: int = 24,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        enabled: bool = True,
        created_at: str | None = None,
        updated_at: str | None = None,
    ) -> None:
        """Initialize a retention policy."""
        self.id = id
        self.name = name
        self.description = description
        self.preset = preset
        self.rules = rules or []
        self.triggers = triggers or [CleanupTrigger.MANUAL]
        self.schedule_hours = schedule_hours
        self.tenant_id = tenant_id
        self.workspace_id = workspace_id
        self.enabled = enabled
        self.created_at = created_at or datetime.now().isoformat()
        self.updated_at = updated_at or datetime.now().isoformat()

    def __hash__(self) -> int:
        """Hash by policy ID."""
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        """Equality by policy ID."""
        if not isinstance(other, RetentionPolicy):
            return NotImplemented
        return self.id == other.id

    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now().isoformat()

    def add_rule(self, rule: RetentionRule) -> None:
        """Add a retention rule."""
        # Remove existing rule for same data type/pattern
        self.rules = [
            r
            for r in self.rules
            if not (r.data_type == rule.data_type and r.pattern == rule.pattern)
        ]
        self.rules.append(rule)
        self.touch()

    def remove_rule(self, data_type: DataType, pattern: str | None = None) -> bool:
        """Remove a retention rule."""
        original_len = len(self.rules)
        self.rules = [
            r for r in self.rules if not (r.data_type == data_type and r.pattern == pattern)
        ]
        if len(self.rules) < original_len:
            self.touch()
            return True
        return False

    def get_rule(self, data_type: DataType, pattern: str | None = None) -> RetentionRule | None:
        """Get a specific rule by data type and pattern."""
        for rule in self.rules:
            if rule.data_type == data_type and rule.pattern == pattern:
                return rule
        return None

    def get_rules_for_type(self, data_type: DataType) -> list[RetentionRule]:
        """Get all rules for a data type."""
        return [r for r in self.rules if r.data_type == data_type and r.enabled]

    def has_trigger(self, trigger: CleanupTrigger) -> bool:
        """Check if policy has a specific trigger."""
        return trigger in self.triggers

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "preset": self.preset.value,
            "rules": [r.to_dict() for r in self.rules],
            "triggers": [t.value for t in self.triggers],
            "schedule_hours": self.schedule_hours,
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RetentionPolicy:
        """Create from dictionary."""
        rules = [RetentionRule.from_dict(r) for r in data.get("rules", [])]
        triggers = [CleanupTrigger(t) for t in data.get("triggers", ["manual"])]
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            preset=PolicyPreset(data.get("preset", "custom")),
            rules=rules,
            triggers=triggers,
            schedule_hours=data.get("schedule_hours", 24),
            tenant_id=data.get("tenant_id"),
            workspace_id=data.get("workspace_id"),
            enabled=data.get("enabled", True),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


# =============================================================================
# Policy Presets
# =============================================================================


def create_minimal_policy(
    tenant_id: str | None = None,
    workspace_id: str | None = None,
) -> RetentionPolicy:
    """
    Create a minimal retention policy.

    Aggressive cleanup for minimal storage usage:
    - Backups: 3 days, max 3
    - State: 7 days, max 10
    - Cache: 1 day, max 100MB
    - Logs: 3 days, max 10MB
    """
    return RetentionPolicy(
        id="minimal",
        name="Minimal",
        description="Aggressive cleanup for minimal storage usage",
        preset=PolicyPreset.MINIMAL,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        triggers=[CleanupTrigger.STARTUP, CleanupTrigger.AFTER_SYNC],
        schedule_hours=12,
        rules=[
            RetentionRule(
                data_type=DataType.BACKUP,
                max_age=3,
                max_age_unit=RetentionUnit.DAYS,
                max_count=3,
                min_keep=1,
                description="Keep backups for 3 days, max 3",
            ),
            RetentionRule(
                data_type=DataType.STATE,
                max_age=7,
                max_age_unit=RetentionUnit.DAYS,
                max_count=10,
                min_keep=1,
                description="Keep state for 7 days, max 10 sessions",
            ),
            RetentionRule(
                data_type=DataType.CACHE,
                max_age=1,
                max_age_unit=RetentionUnit.DAYS,
                max_size_mb=100,
                min_keep=0,
                description="Keep cache for 1 day, max 100MB",
            ),
            RetentionRule(
                data_type=DataType.LOGS,
                max_age=3,
                max_age_unit=RetentionUnit.DAYS,
                max_size_mb=10,
                min_keep=1,
                description="Keep logs for 3 days, max 10MB",
            ),
        ],
    )


def create_standard_policy(
    tenant_id: str | None = None,
    workspace_id: str | None = None,
) -> RetentionPolicy:
    """
    Create a standard retention policy.

    Balanced defaults for most use cases:
    - Backups: 30 days, max 10
    - State: 30 days, max 50
    - Cache: 7 days, max 500MB
    - Logs: 14 days, max 50MB
    """
    return RetentionPolicy(
        id="standard",
        name="Standard",
        description="Balanced retention for most use cases",
        preset=PolicyPreset.STANDARD,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        triggers=[CleanupTrigger.STARTUP, CleanupTrigger.SCHEDULED],
        schedule_hours=24,
        rules=[
            RetentionRule(
                data_type=DataType.BACKUP,
                max_age=30,
                max_age_unit=RetentionUnit.DAYS,
                max_count=10,
                min_keep=1,
                description="Keep backups for 30 days, max 10",
            ),
            RetentionRule(
                data_type=DataType.STATE,
                max_age=30,
                max_age_unit=RetentionUnit.DAYS,
                max_count=50,
                min_keep=5,
                description="Keep state for 30 days, max 50 sessions",
            ),
            RetentionRule(
                data_type=DataType.CACHE,
                max_age=7,
                max_age_unit=RetentionUnit.DAYS,
                max_size_mb=500,
                min_keep=0,
                description="Keep cache for 7 days, max 500MB",
            ),
            RetentionRule(
                data_type=DataType.LOGS,
                max_age=14,
                max_age_unit=RetentionUnit.DAYS,
                max_size_mb=50,
                min_keep=1,
                description="Keep logs for 14 days, max 50MB",
            ),
        ],
    )


def create_extended_policy(
    tenant_id: str | None = None,
    workspace_id: str | None = None,
) -> RetentionPolicy:
    """
    Create an extended retention policy.

    Keep more history for compliance/audit:
    - Backups: 90 days, max 30
    - State: 90 days, max 100
    - Cache: 14 days, max 1GB
    - Logs: 30 days, max 200MB
    """
    return RetentionPolicy(
        id="extended",
        name="Extended",
        description="Extended retention for compliance and audit",
        preset=PolicyPreset.EXTENDED,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        triggers=[CleanupTrigger.SCHEDULED],
        schedule_hours=48,
        rules=[
            RetentionRule(
                data_type=DataType.BACKUP,
                max_age=90,
                max_age_unit=RetentionUnit.DAYS,
                max_count=30,
                min_keep=5,
                description="Keep backups for 90 days, max 30",
            ),
            RetentionRule(
                data_type=DataType.STATE,
                max_age=90,
                max_age_unit=RetentionUnit.DAYS,
                max_count=100,
                min_keep=10,
                description="Keep state for 90 days, max 100 sessions",
            ),
            RetentionRule(
                data_type=DataType.CACHE,
                max_age=14,
                max_age_unit=RetentionUnit.DAYS,
                max_size_mb=1024,
                min_keep=0,
                description="Keep cache for 14 days, max 1GB",
            ),
            RetentionRule(
                data_type=DataType.LOGS,
                max_age=30,
                max_age_unit=RetentionUnit.DAYS,
                max_size_mb=200,
                min_keep=1,
                description="Keep logs for 30 days, max 200MB",
            ),
        ],
    )


def create_archive_policy(
    tenant_id: str | None = None,
    workspace_id: str | None = None,
) -> RetentionPolicy:
    """
    Create an archive retention policy.

    Keep almost everything for long-term storage:
    - Backups: 365 days, max 100
    - State: 365 days, max 500
    - Cache: 30 days, max 2GB
    - Logs: 90 days, max 500MB
    """
    return RetentionPolicy(
        id="archive",
        name="Archive",
        description="Long-term retention for archival purposes",
        preset=PolicyPreset.ARCHIVE,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        triggers=[CleanupTrigger.SCHEDULED],
        schedule_hours=168,  # Weekly
        rules=[
            RetentionRule(
                data_type=DataType.BACKUP,
                max_age=365,
                max_age_unit=RetentionUnit.DAYS,
                max_count=100,
                min_keep=10,
                description="Keep backups for 1 year, max 100",
            ),
            RetentionRule(
                data_type=DataType.STATE,
                max_age=365,
                max_age_unit=RetentionUnit.DAYS,
                max_count=500,
                min_keep=20,
                description="Keep state for 1 year, max 500 sessions",
            ),
            RetentionRule(
                data_type=DataType.CACHE,
                max_age=30,
                max_age_unit=RetentionUnit.DAYS,
                max_size_mb=2048,
                min_keep=0,
                description="Keep cache for 30 days, max 2GB",
            ),
            RetentionRule(
                data_type=DataType.LOGS,
                max_age=90,
                max_age_unit=RetentionUnit.DAYS,
                max_size_mb=500,
                min_keep=1,
                description="Keep logs for 90 days, max 500MB",
            ),
        ],
    )


def get_preset_policy(
    preset: PolicyPreset,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
) -> RetentionPolicy:
    """Get a policy from a preset."""
    if preset == PolicyPreset.MINIMAL:
        return create_minimal_policy(tenant_id, workspace_id)
    if preset == PolicyPreset.STANDARD:
        return create_standard_policy(tenant_id, workspace_id)
    if preset == PolicyPreset.EXTENDED:
        return create_extended_policy(tenant_id, workspace_id)
    if preset == PolicyPreset.ARCHIVE:
        return create_archive_policy(tenant_id, workspace_id)
    return create_standard_policy(tenant_id, workspace_id)


# =============================================================================
# Cleanup Result
# =============================================================================


@dataclass
class CleanupItem:
    """A single item that was or would be cleaned up."""

    __slots__ = ("age_days", "data_type", "path", "reason", "size_bytes")

    path: Path
    data_type: DataType
    size_bytes: int
    age_days: float
    reason: str

    def __init__(
        self,
        path: Path,
        data_type: DataType,
        size_bytes: int = 0,
        age_days: float = 0,
        reason: str = "",
    ) -> None:
        """Initialize a cleanup item."""
        self.path = path
        self.data_type = data_type
        self.size_bytes = size_bytes
        self.age_days = age_days
        self.reason = reason

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "path": str(self.path),
            "data_type": self.data_type.value,
            "size_bytes": self.size_bytes,
            "age_days": round(self.age_days, 2),
            "reason": self.reason,
        }


@dataclass
class CleanupResult:
    """
    Result of a cleanup operation.

    Tracks all items cleaned up and statistics.
    """

    policy_id: str
    dry_run: bool = True
    success: bool = True
    items_cleaned: list[CleanupItem] = field(default_factory=list)
    items_kept: list[CleanupItem] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: str | None = None

    @property
    def total_cleaned(self) -> int:
        """Total items cleaned."""
        return len(self.items_cleaned)

    @property
    def total_kept(self) -> int:
        """Total items kept."""
        return len(self.items_kept)

    @property
    def bytes_freed(self) -> int:
        """Total bytes freed."""
        return sum(item.size_bytes for item in self.items_cleaned)

    @property
    def bytes_kept(self) -> int:
        """Total bytes kept."""
        return sum(item.size_bytes for item in self.items_kept)

    def by_data_type(self) -> dict[DataType, list[CleanupItem]]:
        """Group cleaned items by data type."""
        result: dict[DataType, list[CleanupItem]] = {}
        for item in self.items_cleaned:
            if item.data_type not in result:
                result[item.data_type] = []
            result[item.data_type].append(item)
        return result

    def add_cleaned(self, item: CleanupItem) -> None:
        """Add a cleaned item."""
        self.items_cleaned.append(item)

    def add_kept(self, item: CleanupItem) -> None:
        """Add a kept item."""
        self.items_kept.append(item)

    def add_error(self, error: str) -> None:
        """Add an error."""
        self.errors.append(error)
        self.success = False

    def complete(self) -> None:
        """Mark cleanup as complete."""
        self.completed_at = datetime.now().isoformat()

    def summary(self) -> str:
        """Generate human-readable summary."""
        lines = []

        if self.dry_run:
            lines.append("DRY RUN - No changes made")

        if self.success:
            lines.append("✓ Cleanup completed successfully")
        else:
            lines.append(f"✗ Cleanup completed with errors ({len(self.errors)} failures)")

        lines.append(f"  Policy: {self.policy_id}")
        lines.append(f"  Items cleaned: {self.total_cleaned}")
        lines.append(f"  Items kept: {self.total_kept}")
        lines.append(f"  Space freed: {self._format_bytes(self.bytes_freed)}")
        lines.append(f"  Space remaining: {self._format_bytes(self.bytes_kept)}")

        # By data type
        by_type = self.by_data_type()
        if by_type:
            lines.append("")
            lines.append("By data type:")
            for data_type, items in by_type.items():
                type_bytes = sum(i.size_bytes for i in items)
                lines.append(
                    f"  {data_type.value}: {len(items)} items ({self._format_bytes(type_bytes)})"
                )

        if self.errors:
            lines.append("")
            lines.append("Errors:")
            for error in self.errors[:5]:
                lines.append(f"  • {error}")
            if len(self.errors) > 5:
                lines.append(f"  ... and {len(self.errors) - 5} more")

        return "\n".join(lines)

    def _format_bytes(self, bytes_val: int | float) -> str:
        """Format bytes to human-readable string."""
        val = float(bytes_val)
        for unit in ["B", "KB", "MB", "GB"]:
            if val < 1024:
                return f"{val:.1f} {unit}"
            val /= 1024
        return f"{val:.1f} TB"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "policy_id": self.policy_id,
            "dry_run": self.dry_run,
            "success": self.success,
            "items_cleaned": [i.to_dict() for i in self.items_cleaned],
            "items_kept": [i.to_dict() for i in self.items_kept],
            "errors": self.errors,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "total_cleaned": self.total_cleaned,
            "total_kept": self.total_kept,
            "bytes_freed": self.bytes_freed,
            "bytes_kept": self.bytes_kept,
        }


# =============================================================================
# Policy Registry
# =============================================================================


class RetentionPolicyRegistry:
    """
    Registry for retention policies.

    Manages storage and retrieval of policies.
    Thread-safe for concurrent access.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        """
        Initialize the registry.

        Args:
            base_dir: Base directory for storing policy files.
        """
        self.base_dir = base_dir or DEFAULT_SPECTRA_DIR
        self._lock = threading.Lock()
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        """Ensure the base directory exists."""
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _registry_file(self) -> Path:
        """Get path to the registry file."""
        return self.base_dir / RETENTION_CONFIG_FILE

    def _load_policies(self) -> list[RetentionPolicy]:
        """Load policies from disk (internal, no lock)."""
        registry_file = self._registry_file()
        if not registry_file.exists():
            return []

        try:
            with open(registry_file) as f:
                data = json.load(f)
            return [RetentionPolicy.from_dict(p) for p in data.get("policies", [])]
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to load policy registry: {e}")
            return []

    def list_all(self) -> list[RetentionPolicy]:
        """List all policies."""
        with self._lock:
            return self._load_policies()

    def get(self, policy_id: str) -> RetentionPolicy | None:
        """Get a policy by ID."""
        with self._lock:
            policies = self._load_policies()
            for policy in policies:
                if policy.id == policy_id:
                    return policy
            return None

    def get_for_scope(
        self,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
    ) -> RetentionPolicy | None:
        """
        Get the most specific policy for a scope.

        Priority: workspace > tenant > global
        """
        with self._lock:
            policies = self._load_policies()
            best_match: RetentionPolicy | None = None

            for policy in policies:
                if not policy.enabled:
                    continue

                # Check scope match
                if workspace_id and policy.workspace_id == workspace_id:
                    return policy  # Most specific
                if tenant_id and policy.tenant_id == tenant_id and not policy.workspace_id:
                    best_match = policy
                elif not policy.tenant_id and not policy.workspace_id and best_match is None:
                    best_match = policy  # Global fallback

            return best_match

    def create(self, policy: RetentionPolicy) -> RetentionPolicy:
        """Create a new policy."""
        with self._lock:
            policies = self._load_policies()

            # Check for duplicate ID
            if any(p.id == policy.id for p in policies):
                raise ValueError(f"Policy with ID '{policy.id}' already exists")

            policies.append(policy)
            self._save(policies)
            logger.info(f"Created retention policy: {policy.id}")
            return policy

    def update(self, policy: RetentionPolicy) -> RetentionPolicy:
        """Update an existing policy."""
        with self._lock:
            policies = self._load_policies()
            found = False

            for i, p in enumerate(policies):
                if p.id == policy.id:
                    policy.touch()
                    policies[i] = policy
                    found = True
                    break

            if not found:
                raise ValueError(f"Policy not found: {policy.id}")

            self._save(policies)
            logger.info(f"Updated retention policy: {policy.id}")
            return policy

    def delete(self, policy_id: str) -> bool:
        """Delete a policy."""
        with self._lock:
            policies = self._load_policies()
            original_len = len(policies)
            policies = [p for p in policies if p.id != policy_id]

            if len(policies) < original_len:
                self._save(policies)
                logger.info(f"Deleted retention policy: {policy_id}")
                return True
            return False

    def _save(self, policies: list[RetentionPolicy]) -> None:
        """Save policies to disk."""
        registry_file = self._registry_file()
        data = {
            "version": "1.0",
            "updated_at": datetime.now().isoformat(),
            "policies": [p.to_dict() for p in policies],
        }
        with open(registry_file, "w") as f:
            json.dump(data, f, indent=2)


# =============================================================================
# Retention Manager
# =============================================================================


class RetentionManager:
    """
    High-level manager for data retention and cleanup.

    Provides:
    - Policy application and enforcement
    - Scheduled cleanup execution
    - Dry-run previews
    - Cleanup reporting
    """

    def __init__(
        self,
        base_dir: Path | None = None,
        registry: RetentionPolicyRegistry | None = None,
    ) -> None:
        """
        Initialize the retention manager.

        Args:
            base_dir: Base directory for Spectra data.
            registry: Policy registry (or create new one).
        """
        self.base_dir = base_dir or DEFAULT_SPECTRA_DIR
        self.registry = registry or RetentionPolicyRegistry(self.base_dir)
        self._lock = threading.Lock()
        self._last_cleanup: dict[str, datetime] = {}

    def get_effective_policy(
        self,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
    ) -> RetentionPolicy:
        """
        Get the effective policy for a scope.

        Falls back to standard policy if none configured.
        """
        policy = self.registry.get_for_scope(tenant_id, workspace_id)
        if policy is None:
            policy = create_standard_policy(tenant_id, workspace_id)
        return policy

    def run_cleanup(
        self,
        policy: RetentionPolicy | None = None,
        dry_run: bool = True,
        data_types: list[DataType] | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
    ) -> CleanupResult:
        """
        Run cleanup based on a policy.

        Args:
            policy: Policy to apply (or use effective policy).
            dry_run: If True, only simulate cleanup.
            data_types: Specific data types to clean (None = all).
            tenant_id: Tenant scope.
            workspace_id: Workspace scope.

        Returns:
            CleanupResult with details of what was cleaned.
        """
        if policy is None:
            policy = self.get_effective_policy(tenant_id, workspace_id)

        result = CleanupResult(policy_id=policy.id, dry_run=dry_run)

        logger.info(f"Running cleanup with policy {policy.id} (dry_run={dry_run})")

        # Get directories to clean
        dirs_to_clean = self._get_directories(tenant_id, workspace_id)

        # Process each data type
        types_to_process = data_types or [
            DataType.BACKUP,
            DataType.STATE,
            DataType.CACHE,
            DataType.LOGS,
        ]

        for data_type in types_to_process:
            rules = policy.get_rules_for_type(data_type)
            if not rules:
                continue

            # Get the directory for this data type
            target_dir = dirs_to_clean.get(data_type)
            if target_dir is None or not target_dir.exists():
                continue

            for rule in rules:
                self._apply_rule(rule, target_dir, result, dry_run)

        result.complete()
        self._last_cleanup[policy.id] = datetime.now()

        logger.info(
            f"Cleanup complete: {result.total_cleaned} items "
            f"({result._format_bytes(result.bytes_freed)}) freed"
        )

        return result

    def _get_directories(
        self,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
    ) -> dict[DataType, Path]:
        """Get directories for each data type."""
        # Determine base path
        if tenant_id:
            if tenant_id == "default":
                base = self.base_dir
            else:
                base = self.base_dir / "tenants" / tenant_id
        else:
            base = self.base_dir

        # Add workspace path if specified
        if workspace_id and workspace_id != "default":
            base = base / "workspaces" / workspace_id

        return {
            DataType.BACKUP: base / "backups",
            DataType.STATE: base / "state",
            DataType.CACHE: base / "cache",
            DataType.LOGS: base / "logs",
        }

    def _apply_rule(
        self,
        rule: RetentionRule,
        target_dir: Path,
        result: CleanupResult,
        dry_run: bool,
    ) -> None:
        """Apply a retention rule to a directory."""
        if not target_dir.exists():
            return

        # Collect all items
        items = self._collect_items(target_dir, rule)
        if not items:
            return

        # Sort by age (newest first for proper min_keep handling)
        items.sort(key=lambda x: x.age_days)

        # First pass: identify items that violate rules
        # We'll process newest to oldest, keeping track of what to keep
        items_to_keep: list[CleanupItem] = []
        items_to_clean: list[CleanupItem] = []
        total_size = 0

        for item in items:
            should_keep = True
            reason = ""

            # Check age
            if rule.max_age is not None:
                max_delta = rule.max_age_timedelta
                if max_delta and item.age_days > max_delta.days:
                    should_keep = False
                    reason = f"Age ({item.age_days:.1f} days) exceeds max ({max_delta.days} days)"

            # Check count (already kept enough)
            if rule.max_count is not None and len(items_to_keep) >= rule.max_count:
                should_keep = False
                reason = reason or f"Count ({len(items_to_keep)}) exceeds max ({rule.max_count})"

            # Check size
            if rule.max_size_mb is not None:
                if total_size > rule.max_size_mb * 1024 * 1024:
                    should_keep = False
                    reason = reason or f"Size exceeds max ({rule.max_size_mb} MB)"

            if should_keep:
                items_to_keep.append(item)
                total_size += item.size_bytes
            else:
                item.reason = reason
                items_to_clean.append(item)

        # Second pass: enforce min_keep by protecting the newest items
        # If we're going to clean too many, move some back to keep
        if rule.min_keep > 0 and len(items_to_keep) < rule.min_keep:
            # We need to keep more items - restore from items_to_clean (newest first)
            # items_to_clean is in order of processing (newest first for items that failed)
            items_to_clean_sorted = sorted(items_to_clean, key=lambda x: x.age_days)

            while len(items_to_keep) < rule.min_keep and items_to_clean_sorted:
                item = items_to_clean_sorted.pop(0)  # Take newest
                item.reason = ""
                items_to_keep.append(item)

            # Update items_to_clean with remaining items
            items_to_clean = items_to_clean_sorted

        # Execute cleanup
        for item in items_to_clean:
            try:
                if not dry_run:
                    if item.path.is_dir():
                        import shutil

                        shutil.rmtree(item.path)
                    else:
                        item.path.unlink()
                result.add_cleaned(item)
            except Exception as e:
                result.add_error(f"Failed to delete {item.path}: {e}")

        for item in items_to_keep:
            result.add_kept(item)

    def _collect_items(
        self,
        target_dir: Path,
        rule: RetentionRule,
    ) -> list[CleanupItem]:
        """Collect items from a directory matching the rule."""
        items: list[CleanupItem] = []
        now = datetime.now()

        # Use pattern if specified, otherwise get all items
        pattern = rule.pattern or "*"

        for path in target_dir.glob(pattern):
            if path.name.startswith("."):
                continue  # Skip hidden files

            try:
                stat = path.stat()
                mtime = datetime.fromtimestamp(stat.st_mtime)
                age = now - mtime

                # Calculate size (recursively for directories)
                if path.is_dir():
                    size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
                else:
                    size = stat.st_size

                items.append(
                    CleanupItem(
                        path=path,
                        data_type=rule.data_type,
                        size_bytes=size,
                        age_days=age.total_seconds() / 86400,
                    )
                )
            except OSError as e:
                logger.warning(f"Could not stat {path}: {e}")

        return items

    def should_run_cleanup(
        self,
        policy: RetentionPolicy,
        trigger: CleanupTrigger,
    ) -> bool:
        """Check if cleanup should run based on trigger and schedule."""
        if not policy.enabled:
            return False

        if not policy.has_trigger(trigger):
            return False

        # For scheduled triggers, check if enough time has passed
        if trigger == CleanupTrigger.SCHEDULED:
            last_run = self._last_cleanup.get(policy.id)
            if last_run:
                elapsed = datetime.now() - last_run
                if elapsed.total_seconds() < policy.schedule_hours * 3600:
                    return False

        return True

    def get_storage_summary(
        self,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Get a summary of storage usage.

        Returns:
            Dictionary with storage statistics.
        """
        dirs = self._get_directories(tenant_id, workspace_id)
        summary: dict[str, Any] = {
            "tenant_id": tenant_id,
            "workspace_id": workspace_id,
            "data_types": {},
            "total_size_bytes": 0,
            "total_items": 0,
        }

        for data_type, dir_path in dirs.items():
            if not dir_path.exists():
                continue

            items = list(dir_path.glob("*"))
            items = [i for i in items if not i.name.startswith(".")]
            total_size = 0

            for item in items:
                try:
                    if item.is_dir():
                        total_size += sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
                    else:
                        total_size += item.stat().st_size
                except OSError:
                    pass

            summary["data_types"][data_type.value] = {
                "path": str(dir_path),
                "items": len(items),
                "size_bytes": total_size,
                "size_human": self._format_bytes(total_size),
            }
            summary["total_size_bytes"] += total_size
            summary["total_items"] += len(items)

        summary["total_size_human"] = self._format_bytes(summary["total_size_bytes"])
        return summary

    def _format_bytes(self, bytes_val: int | float) -> str:
        """Format bytes to human-readable string."""
        val = float(bytes_val)
        for unit in ["B", "KB", "MB", "GB"]:
            if val < 1024:
                return f"{val:.1f} {unit}"
            val /= 1024
        return f"{val:.1f} TB"


# =============================================================================
# Cleanup Scheduler
# =============================================================================


class CleanupScheduler:
    """
    Scheduler for automatic cleanup operations.

    Runs cleanup based on policies and triggers.
    """

    def __init__(
        self,
        manager: RetentionManager,
        check_interval_seconds: int = 3600,
    ) -> None:
        """
        Initialize the scheduler.

        Args:
            manager: Retention manager to use.
            check_interval_seconds: How often to check for scheduled cleanups.
        """
        self.manager = manager
        self.check_interval = check_interval_seconds
        self._running = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._callbacks: list[Callable[[CleanupResult], None]] = []

    def start(self) -> None:
        """Start the scheduler in a background thread."""
        if self._running:
            return

        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("Cleanup scheduler started")

    def stop(self) -> None:
        """Stop the scheduler."""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Cleanup scheduler stopped")

    def register_callback(self, callback: Callable[[CleanupResult], None]) -> None:
        """Register a callback for cleanup results."""
        self._callbacks.append(callback)

    def _run_loop(self) -> None:
        """Main scheduler loop."""
        while not self._stop_event.is_set():
            try:
                self._check_and_run()
            except Exception as e:
                logger.error(f"Scheduler error: {e}")

            self._stop_event.wait(self.check_interval)

    def _check_and_run(self) -> None:
        """Check for and run scheduled cleanups."""
        policies = self.manager.registry.list_all()

        for policy in policies:
            if self.manager.should_run_cleanup(policy, CleanupTrigger.SCHEDULED):
                logger.info(f"Running scheduled cleanup for policy {policy.id}")
                result = self.manager.run_cleanup(policy=policy, dry_run=False)

                for callback in self._callbacks:
                    try:
                        callback(result)
                    except Exception as e:
                        logger.error(f"Callback error: {e}")

    def trigger(self, trigger: CleanupTrigger, dry_run: bool = False) -> list[CleanupResult]:
        """
        Manually trigger cleanup for policies with a specific trigger.

        Args:
            trigger: The trigger type.
            dry_run: If True, only simulate cleanup.

        Returns:
            List of cleanup results.
        """
        results: list[CleanupResult] = []
        policies = self.manager.registry.list_all()

        for policy in policies:
            if policy.has_trigger(trigger) and policy.enabled:
                result = self.manager.run_cleanup(policy=policy, dry_run=dry_run)
                results.append(result)

                # Call registered callbacks
                for callback in self._callbacks:
                    try:
                        callback(result)
                    except Exception as e:
                        logger.error(f"Callback error: {e}")

        return results


# =============================================================================
# Global Instance
# =============================================================================

_retention_manager: RetentionManager | None = None
_retention_lock = threading.Lock()


def get_retention_manager(base_dir: Path | None = None) -> RetentionManager:
    """Get or create the global retention manager."""
    global _retention_manager
    with _retention_lock:
        if _retention_manager is None:
            _retention_manager = RetentionManager(base_dir)
        return _retention_manager


def reset_retention_manager() -> None:
    """Reset the global retention manager (for testing)."""
    global _retention_manager
    with _retention_lock:
        _retention_manager = None


# =============================================================================
# Convenience Functions
# =============================================================================


def cleanup_now(
    dry_run: bool = True,
    data_types: list[DataType] | None = None,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
) -> CleanupResult:
    """
    Run cleanup immediately with effective policy.

    Args:
        dry_run: If True, only simulate cleanup.
        data_types: Specific data types to clean (None = all).
        tenant_id: Tenant scope.
        workspace_id: Workspace scope.

    Returns:
        CleanupResult with details.
    """
    manager = get_retention_manager()
    return manager.run_cleanup(
        dry_run=dry_run,
        data_types=data_types,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
    )


def apply_preset(
    preset: PolicyPreset,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
) -> RetentionPolicy:
    """
    Apply a preset policy to a scope.

    Args:
        preset: The preset to apply.
        tenant_id: Tenant scope.
        workspace_id: Workspace scope.

    Returns:
        The created policy.
    """
    manager = get_retention_manager()
    policy = get_preset_policy(preset, tenant_id, workspace_id)

    # Generate unique ID for scoped policies
    if tenant_id or workspace_id:
        parts = [preset.value]
        if tenant_id:
            parts.append(f"tenant-{tenant_id}")
        if workspace_id:
            parts.append(f"workspace-{workspace_id}")
        policy.id = "-".join(parts)

    try:
        return manager.registry.create(policy)
    except ValueError:
        # Policy already exists, update it
        return manager.registry.update(policy)


def get_storage_stats(
    tenant_id: str | None = None,
    workspace_id: str | None = None,
) -> dict[str, Any]:
    """
    Get storage statistics.

    Args:
        tenant_id: Tenant scope.
        workspace_id: Workspace scope.

    Returns:
        Storage summary dictionary.
    """
    manager = get_retention_manager()
    return manager.get_storage_summary(tenant_id, workspace_id)


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    # Classes
    "CleanupItem",
    "CleanupResult",
    "CleanupScheduler",
    # Enums
    "CleanupTrigger",
    "DataType",
    "PolicyPreset",
    "RetentionManager",
    "RetentionPolicy",
    "RetentionPolicyRegistry",
    "RetentionRule",
    "RetentionUnit",
    # Convenience functions
    "apply_preset",
    "cleanup_now",
    # Preset functions
    "create_archive_policy",
    "create_extended_policy",
    "create_minimal_policy",
    "create_standard_policy",
    "get_preset_policy",
    "get_retention_manager",
    "get_storage_stats",
    "reset_retention_manager",
]
