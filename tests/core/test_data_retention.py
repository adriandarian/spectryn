"""
Tests for Data Retention Policies.

Comprehensive test suite covering:
- RetentionRule entity
- RetentionPolicy entity
- Policy presets
- RetentionPolicyRegistry CRUD
- RetentionManager cleanup operations
- CleanupResult reporting
- CleanupScheduler
- Edge cases and error handling
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
from collections.abc import Generator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from spectryn.core.retention import (
    CleanupItem,
    CleanupResult,
    CleanupScheduler,
    CleanupTrigger,
    DataType,
    PolicyPreset,
    RetentionManager,
    RetentionPolicy,
    RetentionPolicyRegistry,
    RetentionRule,
    RetentionUnit,
    apply_preset,
    cleanup_now,
    create_archive_policy,
    create_extended_policy,
    create_minimal_policy,
    create_standard_policy,
    get_preset_policy,
    get_retention_manager,
    get_storage_stats,
    reset_retention_manager,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for tests."""
    dir_path = Path(tempfile.mkdtemp())
    yield dir_path
    shutil.rmtree(dir_path, ignore_errors=True)


@pytest.fixture
def registry(temp_dir: Path) -> RetentionPolicyRegistry:
    """Create a test registry."""
    return RetentionPolicyRegistry(base_dir=temp_dir)


@pytest.fixture
def manager(temp_dir: Path) -> RetentionManager:
    """Create a test retention manager."""
    return RetentionManager(base_dir=temp_dir)


@pytest.fixture
def sample_rule() -> RetentionRule:
    """Create a sample retention rule."""
    return RetentionRule(
        data_type=DataType.BACKUP,
        max_age=30,
        max_age_unit=RetentionUnit.DAYS,
        max_count=10,
        min_keep=1,
        description="Test backup rule",
    )


@pytest.fixture
def sample_policy(sample_rule: RetentionRule) -> RetentionPolicy:
    """Create a sample retention policy."""
    return RetentionPolicy(
        id="test-policy",
        name="Test Policy",
        description="A test retention policy",
        preset=PolicyPreset.CUSTOM,
        rules=[sample_rule],
        triggers=[CleanupTrigger.MANUAL, CleanupTrigger.STARTUP],
        schedule_hours=24,
    )


@pytest.fixture
def clean_global_manager() -> Generator[None, None, None]:
    """Reset global manager before and after test."""
    reset_retention_manager()
    yield
    reset_retention_manager()


# =============================================================================
# Test RetentionRule
# =============================================================================


class TestRetentionRule:
    """Tests for RetentionRule entity."""

    def test_create_rule(self) -> None:
        """Test creating a retention rule."""
        rule = RetentionRule(
            data_type=DataType.BACKUP,
            max_age=30,
            max_count=10,
        )
        assert rule.data_type == DataType.BACKUP
        assert rule.max_age == 30
        assert rule.max_count == 10
        assert rule.enabled is True

    def test_rule_defaults(self) -> None:
        """Test rule default values."""
        rule = RetentionRule(data_type=DataType.CACHE)
        assert rule.max_age is None
        assert rule.max_age_unit == RetentionUnit.DAYS
        assert rule.max_count is None
        assert rule.max_size_mb is None
        assert rule.min_keep == 1
        assert rule.pattern is None
        assert rule.enabled is True
        assert rule.description == ""

    def test_rule_max_age_timedelta_days(self) -> None:
        """Test max_age_timedelta with days."""
        rule = RetentionRule(
            data_type=DataType.BACKUP,
            max_age=7,
            max_age_unit=RetentionUnit.DAYS,
        )
        td = rule.max_age_timedelta
        assert td is not None
        assert td.days == 7

    def test_rule_max_age_timedelta_hours(self) -> None:
        """Test max_age_timedelta with hours."""
        rule = RetentionRule(
            data_type=DataType.CACHE,
            max_age=24,
            max_age_unit=RetentionUnit.HOURS,
        )
        td = rule.max_age_timedelta
        assert td is not None
        assert td.total_seconds() == 24 * 3600

    def test_rule_max_age_timedelta_weeks(self) -> None:
        """Test max_age_timedelta with weeks."""
        rule = RetentionRule(
            data_type=DataType.LOGS,
            max_age=2,
            max_age_unit=RetentionUnit.WEEKS,
        )
        td = rule.max_age_timedelta
        assert td is not None
        assert td.days == 14

    def test_rule_max_age_timedelta_months(self) -> None:
        """Test max_age_timedelta with months."""
        rule = RetentionRule(
            data_type=DataType.STATE,
            max_age=3,
            max_age_unit=RetentionUnit.MONTHS,
        )
        td = rule.max_age_timedelta
        assert td is not None
        assert td.days == 90  # Approximate

    def test_rule_max_age_timedelta_none(self) -> None:
        """Test max_age_timedelta when max_age is None."""
        rule = RetentionRule(data_type=DataType.BACKUP)
        assert rule.max_age_timedelta is None

    def test_rule_to_dict(self, sample_rule: RetentionRule) -> None:
        """Test rule serialization."""
        data = sample_rule.to_dict()
        assert data["data_type"] == "backup"
        assert data["max_age"] == 30
        assert data["max_age_unit"] == "days"
        assert data["max_count"] == 10
        assert data["min_keep"] == 1
        assert data["enabled"] is True

    def test_rule_from_dict(self) -> None:
        """Test rule deserialization."""
        data = {
            "data_type": "cache",
            "max_age": 7,
            "max_age_unit": "days",
            "max_size_mb": 500,
            "min_keep": 0,
            "enabled": True,
        }
        rule = RetentionRule.from_dict(data)
        assert rule.data_type == DataType.CACHE
        assert rule.max_age == 7
        assert rule.max_size_mb == 500
        assert rule.min_keep == 0

    def test_rule_equality(self) -> None:
        """Test rule equality by data type and pattern."""
        rule1 = RetentionRule(data_type=DataType.BACKUP, pattern="*.json")
        rule2 = RetentionRule(data_type=DataType.BACKUP, pattern="*.json")
        rule3 = RetentionRule(data_type=DataType.BACKUP, pattern="*.xml")
        assert rule1 == rule2
        assert rule1 != rule3

    def test_rule_hash(self) -> None:
        """Test rule hashing."""
        rule1 = RetentionRule(data_type=DataType.BACKUP, pattern="*.json")
        rule2 = RetentionRule(data_type=DataType.BACKUP, pattern="*.json")
        assert hash(rule1) == hash(rule2)


# =============================================================================
# Test RetentionPolicy
# =============================================================================


class TestRetentionPolicy:
    """Tests for RetentionPolicy entity."""

    def test_create_policy(self) -> None:
        """Test creating a retention policy."""
        policy = RetentionPolicy(
            id="my-policy",
            name="My Policy",
            description="Test policy",
        )
        assert policy.id == "my-policy"
        assert policy.name == "My Policy"
        assert policy.preset == PolicyPreset.CUSTOM
        assert policy.enabled is True

    def test_policy_defaults(self) -> None:
        """Test policy default values."""
        policy = RetentionPolicy(id="test", name="Test")
        assert policy.description == ""
        assert policy.rules == []
        assert policy.triggers == [CleanupTrigger.MANUAL]
        assert policy.schedule_hours == 24
        assert policy.tenant_id is None
        assert policy.workspace_id is None

    def test_policy_touch(self, sample_policy: RetentionPolicy) -> None:
        """Test policy touch updates timestamp."""
        original = sample_policy.updated_at
        time.sleep(0.01)
        sample_policy.touch()
        assert sample_policy.updated_at != original

    def test_policy_add_rule(self, sample_policy: RetentionPolicy) -> None:
        """Test adding a rule to policy."""
        new_rule = RetentionRule(data_type=DataType.CACHE, max_age=7)
        sample_policy.add_rule(new_rule)
        assert len(sample_policy.rules) == 2
        assert sample_policy.get_rule(DataType.CACHE) == new_rule

    def test_policy_add_rule_replaces_existing(self, sample_policy: RetentionPolicy) -> None:
        """Test adding a rule replaces existing for same type."""
        original_count = len(sample_policy.rules)
        new_rule = RetentionRule(data_type=DataType.BACKUP, max_age=60)
        sample_policy.add_rule(new_rule)
        assert len(sample_policy.rules) == original_count
        assert sample_policy.get_rule(DataType.BACKUP) == new_rule

    def test_policy_remove_rule(self, sample_policy: RetentionPolicy) -> None:
        """Test removing a rule from policy."""
        assert sample_policy.remove_rule(DataType.BACKUP)
        assert sample_policy.get_rule(DataType.BACKUP) is None

    def test_policy_remove_nonexistent_rule(self, sample_policy: RetentionPolicy) -> None:
        """Test removing nonexistent rule returns False."""
        assert not sample_policy.remove_rule(DataType.CACHE)

    def test_policy_get_rules_for_type(self, sample_policy: RetentionPolicy) -> None:
        """Test getting rules by data type."""
        rules = sample_policy.get_rules_for_type(DataType.BACKUP)
        assert len(rules) == 1
        assert rules[0].data_type == DataType.BACKUP

    def test_policy_has_trigger(self, sample_policy: RetentionPolicy) -> None:
        """Test checking policy triggers."""
        assert sample_policy.has_trigger(CleanupTrigger.MANUAL)
        assert sample_policy.has_trigger(CleanupTrigger.STARTUP)
        assert not sample_policy.has_trigger(CleanupTrigger.SCHEDULED)

    def test_policy_to_dict(self, sample_policy: RetentionPolicy) -> None:
        """Test policy serialization."""
        data = sample_policy.to_dict()
        assert data["id"] == "test-policy"
        assert data["name"] == "Test Policy"
        assert data["preset"] == "custom"
        assert len(data["rules"]) == 1
        assert "manual" in data["triggers"]

    def test_policy_from_dict(self) -> None:
        """Test policy deserialization."""
        data = {
            "id": "loaded",
            "name": "Loaded Policy",
            "preset": "standard",
            "rules": [{"data_type": "backup", "max_age": 30, "max_count": 5}],
            "triggers": ["startup", "scheduled"],
            "schedule_hours": 12,
            "tenant_id": "tenant-1",
        }
        policy = RetentionPolicy.from_dict(data)
        assert policy.id == "loaded"
        assert policy.preset == PolicyPreset.STANDARD
        assert len(policy.rules) == 1
        assert policy.tenant_id == "tenant-1"
        assert policy.schedule_hours == 12

    def test_policy_equality(self) -> None:
        """Test policy equality by ID."""
        p1 = RetentionPolicy(id="same", name="Policy 1")
        p2 = RetentionPolicy(id="same", name="Policy 2")
        p3 = RetentionPolicy(id="different", name="Policy 3")
        assert p1 == p2
        assert p1 != p3


# =============================================================================
# Test Policy Presets
# =============================================================================


class TestPolicyPresets:
    """Tests for policy preset functions."""

    def test_create_minimal_policy(self) -> None:
        """Test minimal preset."""
        policy = create_minimal_policy()
        assert policy.id == "minimal"
        assert policy.preset == PolicyPreset.MINIMAL
        assert len(policy.rules) == 4
        # Check backup rule
        backup_rule = policy.get_rule(DataType.BACKUP)
        assert backup_rule is not None
        assert backup_rule.max_age == 3
        assert backup_rule.max_count == 3

    def test_create_standard_policy(self) -> None:
        """Test standard preset."""
        policy = create_standard_policy()
        assert policy.id == "standard"
        assert policy.preset == PolicyPreset.STANDARD
        backup_rule = policy.get_rule(DataType.BACKUP)
        assert backup_rule is not None
        assert backup_rule.max_age == 30
        assert backup_rule.max_count == 10

    def test_create_extended_policy(self) -> None:
        """Test extended preset."""
        policy = create_extended_policy()
        assert policy.id == "extended"
        assert policy.preset == PolicyPreset.EXTENDED
        backup_rule = policy.get_rule(DataType.BACKUP)
        assert backup_rule is not None
        assert backup_rule.max_age == 90
        assert backup_rule.max_count == 30

    def test_create_archive_policy(self) -> None:
        """Test archive preset."""
        policy = create_archive_policy()
        assert policy.id == "archive"
        assert policy.preset == PolicyPreset.ARCHIVE
        backup_rule = policy.get_rule(DataType.BACKUP)
        assert backup_rule is not None
        assert backup_rule.max_age == 365
        assert backup_rule.max_count == 100

    def test_preset_with_tenant_scope(self) -> None:
        """Test preset with tenant scope."""
        policy = create_standard_policy(tenant_id="acme")
        assert policy.tenant_id == "acme"
        assert policy.workspace_id is None

    def test_preset_with_workspace_scope(self) -> None:
        """Test preset with workspace scope."""
        policy = create_minimal_policy(tenant_id="acme", workspace_id="proj-1")
        assert policy.tenant_id == "acme"
        assert policy.workspace_id == "proj-1"

    def test_get_preset_policy(self) -> None:
        """Test getting preset by enum."""
        policy = get_preset_policy(PolicyPreset.EXTENDED)
        assert policy.preset == PolicyPreset.EXTENDED

    def test_get_preset_custom_fallback(self) -> None:
        """Test custom preset falls back to standard."""
        policy = get_preset_policy(PolicyPreset.CUSTOM)
        # Should return standard as fallback
        assert policy.preset == PolicyPreset.STANDARD


# =============================================================================
# Test CleanupResult
# =============================================================================


class TestCleanupResult:
    """Tests for CleanupResult."""

    def test_create_result(self) -> None:
        """Test creating a cleanup result."""
        result = CleanupResult(policy_id="test", dry_run=True)
        assert result.policy_id == "test"
        assert result.dry_run is True
        assert result.success is True
        assert result.total_cleaned == 0

    def test_result_add_cleaned(self) -> None:
        """Test adding cleaned items."""
        result = CleanupResult(policy_id="test")
        item = CleanupItem(
            path=Path("/test/file.json"),
            data_type=DataType.BACKUP,
            size_bytes=1024,
            age_days=10,
            reason="Over age limit",
        )
        result.add_cleaned(item)
        assert result.total_cleaned == 1
        assert result.bytes_freed == 1024

    def test_result_add_kept(self) -> None:
        """Test adding kept items."""
        result = CleanupResult(policy_id="test")
        item = CleanupItem(
            path=Path("/test/file.json"),
            data_type=DataType.BACKUP,
            size_bytes=2048,
        )
        result.add_kept(item)
        assert result.total_kept == 1
        assert result.bytes_kept == 2048

    def test_result_add_error(self) -> None:
        """Test adding errors marks failure."""
        result = CleanupResult(policy_id="test")
        assert result.success is True
        result.add_error("Something went wrong")
        assert result.success is False
        assert len(result.errors) == 1

    def test_result_by_data_type(self) -> None:
        """Test grouping by data type."""
        result = CleanupResult(policy_id="test")
        result.add_cleaned(CleanupItem(Path("/a"), DataType.BACKUP, 100))
        result.add_cleaned(CleanupItem(Path("/b"), DataType.BACKUP, 200))
        result.add_cleaned(CleanupItem(Path("/c"), DataType.CACHE, 300))

        by_type = result.by_data_type()
        assert len(by_type[DataType.BACKUP]) == 2
        assert len(by_type[DataType.CACHE]) == 1

    def test_result_complete(self) -> None:
        """Test completing a result."""
        result = CleanupResult(policy_id="test")
        assert result.completed_at is None
        result.complete()
        assert result.completed_at is not None

    def test_result_summary(self) -> None:
        """Test result summary generation."""
        result = CleanupResult(policy_id="test-policy", dry_run=True)
        result.add_cleaned(CleanupItem(Path("/a"), DataType.BACKUP, 1024))
        result.complete()

        summary = result.summary()
        assert "DRY RUN" in summary
        assert "test-policy" in summary
        assert "1 items" in summary.lower() or "cleaned: 1" in summary.lower()

    def test_result_to_dict(self) -> None:
        """Test result serialization."""
        result = CleanupResult(policy_id="test", dry_run=False)
        result.add_cleaned(CleanupItem(Path("/a"), DataType.BACKUP, 1024))
        result.complete()

        data = result.to_dict()
        assert data["policy_id"] == "test"
        assert data["dry_run"] is False
        assert data["total_cleaned"] == 1
        assert data["bytes_freed"] == 1024


# =============================================================================
# Test RetentionPolicyRegistry
# =============================================================================


class TestRetentionPolicyRegistry:
    """Tests for RetentionPolicyRegistry."""

    def test_create_policy(
        self, registry: RetentionPolicyRegistry, sample_policy: RetentionPolicy
    ) -> None:
        """Test creating a policy in registry."""
        created = registry.create(sample_policy)
        assert created.id == sample_policy.id

    def test_create_duplicate_fails(
        self, registry: RetentionPolicyRegistry, sample_policy: RetentionPolicy
    ) -> None:
        """Test creating duplicate policy fails."""
        registry.create(sample_policy)
        with pytest.raises(ValueError, match="already exists"):
            registry.create(sample_policy)

    def test_get_policy(
        self, registry: RetentionPolicyRegistry, sample_policy: RetentionPolicy
    ) -> None:
        """Test getting a policy by ID."""
        registry.create(sample_policy)
        retrieved = registry.get(sample_policy.id)
        assert retrieved is not None
        assert retrieved.id == sample_policy.id

    def test_get_nonexistent(self, registry: RetentionPolicyRegistry) -> None:
        """Test getting nonexistent policy returns None."""
        assert registry.get("nonexistent") is None

    def test_list_all(self, registry: RetentionPolicyRegistry) -> None:
        """Test listing all policies."""
        p1 = RetentionPolicy(id="p1", name="Policy 1")
        p2 = RetentionPolicy(id="p2", name="Policy 2")
        registry.create(p1)
        registry.create(p2)

        policies = registry.list_all()
        assert len(policies) == 2
        ids = [p.id for p in policies]
        assert "p1" in ids
        assert "p2" in ids

    def test_update_policy(
        self, registry: RetentionPolicyRegistry, sample_policy: RetentionPolicy
    ) -> None:
        """Test updating a policy."""
        registry.create(sample_policy)
        sample_policy.name = "Updated Name"
        updated = registry.update(sample_policy)
        assert updated.name == "Updated Name"

        # Verify persisted
        retrieved = registry.get(sample_policy.id)
        assert retrieved is not None
        assert retrieved.name == "Updated Name"

    def test_update_nonexistent_fails(
        self, registry: RetentionPolicyRegistry, sample_policy: RetentionPolicy
    ) -> None:
        """Test updating nonexistent policy fails."""
        with pytest.raises(ValueError, match="not found"):
            registry.update(sample_policy)

    def test_delete_policy(
        self, registry: RetentionPolicyRegistry, sample_policy: RetentionPolicy
    ) -> None:
        """Test deleting a policy."""
        registry.create(sample_policy)
        assert registry.delete(sample_policy.id) is True
        assert registry.get(sample_policy.id) is None

    def test_delete_nonexistent(self, registry: RetentionPolicyRegistry) -> None:
        """Test deleting nonexistent returns False."""
        assert registry.delete("nonexistent") is False

    def test_get_for_scope_global(self, registry: RetentionPolicyRegistry) -> None:
        """Test getting policy for global scope."""
        global_policy = RetentionPolicy(id="global", name="Global")
        registry.create(global_policy)

        found = registry.get_for_scope()
        assert found is not None
        assert found.id == "global"

    def test_get_for_scope_tenant(self, registry: RetentionPolicyRegistry) -> None:
        """Test getting policy for tenant scope."""
        global_policy = RetentionPolicy(id="global", name="Global")
        tenant_policy = RetentionPolicy(id="tenant", name="Tenant", tenant_id="acme")
        registry.create(global_policy)
        registry.create(tenant_policy)

        found = registry.get_for_scope(tenant_id="acme")
        assert found is not None
        assert found.id == "tenant"

    def test_get_for_scope_workspace(self, registry: RetentionPolicyRegistry) -> None:
        """Test getting policy for workspace scope (most specific)."""
        global_policy = RetentionPolicy(id="global", name="Global")
        tenant_policy = RetentionPolicy(id="tenant", name="Tenant", tenant_id="acme")
        ws_policy = RetentionPolicy(
            id="ws", name="Workspace", tenant_id="acme", workspace_id="proj"
        )
        registry.create(global_policy)
        registry.create(tenant_policy)
        registry.create(ws_policy)

        found = registry.get_for_scope(tenant_id="acme", workspace_id="proj")
        assert found is not None
        assert found.id == "ws"

    def test_persistence(self, temp_dir: Path) -> None:
        """Test policies persist across registry instances."""
        reg1 = RetentionPolicyRegistry(base_dir=temp_dir)
        policy = RetentionPolicy(id="persistent", name="Persistent")
        reg1.create(policy)

        reg2 = RetentionPolicyRegistry(base_dir=temp_dir)
        found = reg2.get("persistent")
        assert found is not None
        assert found.name == "Persistent"


# =============================================================================
# Test RetentionManager
# =============================================================================


class TestRetentionManager:
    """Tests for RetentionManager."""

    def test_get_effective_policy_default(self, manager: RetentionManager) -> None:
        """Test effective policy defaults to standard."""
        policy = manager.get_effective_policy()
        assert policy.preset == PolicyPreset.STANDARD

    def test_get_effective_policy_configured(self, manager: RetentionManager) -> None:
        """Test effective policy uses configured policy."""
        custom = RetentionPolicy(id="custom", name="Custom")
        manager.registry.create(custom)

        policy = manager.get_effective_policy()
        assert policy.id == "custom"

    def test_run_cleanup_dry_run(self, manager: RetentionManager, temp_dir: Path) -> None:
        """Test cleanup in dry run mode."""
        # Create test backup files
        backup_dir = temp_dir / "backups"
        backup_dir.mkdir()
        (backup_dir / "old_backup.json").write_text("{}")

        result = manager.run_cleanup(dry_run=True)
        assert result.dry_run is True
        # Files should not be deleted in dry run
        assert (backup_dir / "old_backup.json").exists()

    def test_run_cleanup_actual(self, manager: RetentionManager, temp_dir: Path) -> None:
        """Test actual cleanup deletes files."""
        # Create test backup files with old timestamps
        backup_dir = temp_dir / "backups"
        backup_dir.mkdir()
        old_file = backup_dir / "old_backup.json"
        old_file.write_text("{}")

        # Set file to be old (60 days ago)
        old_time = (datetime.now() - timedelta(days=60)).timestamp()
        os.utime(old_file, (old_time, old_time))

        # Create policy with 30 day retention
        policy = RetentionPolicy(
            id="test",
            name="Test",
            rules=[
                RetentionRule(
                    data_type=DataType.BACKUP,
                    max_age=30,
                    max_age_unit=RetentionUnit.DAYS,
                    min_keep=0,
                )
            ],
        )

        result = manager.run_cleanup(policy=policy, dry_run=False)
        assert result.success is True
        # Old file should be deleted
        assert not old_file.exists()

    def test_run_cleanup_respects_min_keep(self, manager: RetentionManager, temp_dir: Path) -> None:
        """Test cleanup respects min_keep."""
        backup_dir = temp_dir / "backups"
        backup_dir.mkdir()

        # Create old files
        for i in range(3):
            f = backup_dir / f"backup_{i}.json"
            f.write_text("{}")
            old_time = (datetime.now() - timedelta(days=60)).timestamp()
            os.utime(f, (old_time, old_time))

        policy = RetentionPolicy(
            id="test",
            name="Test",
            rules=[
                RetentionRule(
                    data_type=DataType.BACKUP,
                    max_age=30,
                    min_keep=2,  # Keep at least 2
                )
            ],
        )

        manager.run_cleanup(policy=policy, dry_run=False)
        # Should keep at least 2 files
        remaining = list(backup_dir.glob("*.json"))
        assert len(remaining) >= 2

    def test_run_cleanup_by_count(self, manager: RetentionManager, temp_dir: Path) -> None:
        """Test cleanup by count limit."""
        backup_dir = temp_dir / "backups"
        backup_dir.mkdir()

        # Create files with different ages
        for i in range(5):
            f = backup_dir / f"backup_{i}.json"
            f.write_text("{}")
            age_days = i * 2  # 0, 2, 4, 6, 8 days old
            old_time = (datetime.now() - timedelta(days=age_days)).timestamp()
            os.utime(f, (old_time, old_time))

        policy = RetentionPolicy(
            id="test",
            name="Test",
            rules=[
                RetentionRule(
                    data_type=DataType.BACKUP,
                    max_count=3,
                    min_keep=0,
                )
            ],
        )

        manager.run_cleanup(policy=policy, dry_run=False)
        remaining = list(backup_dir.glob("*.json"))
        assert len(remaining) == 3

    def test_run_cleanup_specific_data_types(
        self, manager: RetentionManager, temp_dir: Path
    ) -> None:
        """Test cleanup with specific data types."""
        # Create directories
        backup_dir = temp_dir / "backups"
        cache_dir = temp_dir / "cache"
        backup_dir.mkdir()
        cache_dir.mkdir()

        # Create old files - need 2 backups so one can be cleaned while min_keep=1 keeps one
        backup_file_old = backup_dir / "backup_old.json"
        backup_file_new = backup_dir / "backup_new.json"
        cache_file = cache_dir / "cache.json"
        backup_file_old.write_text("{}")
        backup_file_new.write_text("{}")
        cache_file.write_text("{}")

        # Make one backup old (60 days) and one recent (1 day)
        old_time = (datetime.now() - timedelta(days=60)).timestamp()
        new_time = (datetime.now() - timedelta(days=1)).timestamp()
        os.utime(backup_file_old, (old_time, old_time))
        os.utime(backup_file_new, (new_time, new_time))
        os.utime(cache_file, (old_time, old_time))

        policy = create_minimal_policy()
        manager.run_cleanup(
            policy=policy,
            dry_run=False,
            data_types=[DataType.BACKUP],  # Only backup
        )

        # Old backup should be cleaned (exceeds max_age of 3 days)
        assert not backup_file_old.exists()
        # New backup should remain (min_keep=1 and within age limit)
        assert backup_file_new.exists()
        # Cache should remain (not in data_types)
        assert cache_file.exists()

    def test_get_storage_summary(self, manager: RetentionManager, temp_dir: Path) -> None:
        """Test getting storage summary."""
        # Create some files
        backup_dir = temp_dir / "backups"
        backup_dir.mkdir()
        (backup_dir / "file1.json").write_text("x" * 1000)
        (backup_dir / "file2.json").write_text("x" * 2000)

        summary = manager.get_storage_summary()
        assert "backup" in summary["data_types"]
        assert summary["data_types"]["backup"]["items"] == 2
        assert summary["data_types"]["backup"]["size_bytes"] == 3000

    def test_should_run_cleanup_disabled_policy(self, manager: RetentionManager) -> None:
        """Test should_run_cleanup returns False for disabled policy."""
        policy = RetentionPolicy(id="test", name="Test", enabled=False)
        assert manager.should_run_cleanup(policy, CleanupTrigger.STARTUP) is False

    def test_should_run_cleanup_wrong_trigger(self, manager: RetentionManager) -> None:
        """Test should_run_cleanup returns False for wrong trigger."""
        policy = RetentionPolicy(
            id="test",
            name="Test",
            triggers=[CleanupTrigger.MANUAL],
        )
        assert manager.should_run_cleanup(policy, CleanupTrigger.STARTUP) is False


# =============================================================================
# Test CleanupScheduler
# =============================================================================


class TestCleanupScheduler:
    """Tests for CleanupScheduler."""

    def test_scheduler_start_stop(self, manager: RetentionManager) -> None:
        """Test starting and stopping scheduler."""
        scheduler = CleanupScheduler(manager, check_interval_seconds=1)
        scheduler.start()
        assert scheduler._running is True
        scheduler.stop()
        assert scheduler._running is False

    def test_scheduler_double_start(self, manager: RetentionManager) -> None:
        """Test starting twice is safe."""
        scheduler = CleanupScheduler(manager)
        scheduler.start()
        scheduler.start()  # Should not error
        scheduler.stop()

    def test_scheduler_trigger(self, manager: RetentionManager, temp_dir: Path) -> None:
        """Test manual trigger."""
        # Create a policy with startup trigger
        policy = RetentionPolicy(
            id="test",
            name="Test",
            triggers=[CleanupTrigger.STARTUP],
            rules=[
                RetentionRule(
                    data_type=DataType.BACKUP,
                    max_age=1,
                    min_keep=0,
                )
            ],
        )
        manager.registry.create(policy)

        scheduler = CleanupScheduler(manager)
        results = scheduler.trigger(CleanupTrigger.STARTUP, dry_run=True)
        assert len(results) == 1
        assert results[0].policy_id == "test"

    def test_scheduler_callback(self, manager: RetentionManager) -> None:
        """Test scheduler callbacks."""
        scheduler = CleanupScheduler(manager)
        results_received: list[CleanupResult] = []

        def callback(result: CleanupResult) -> None:
            results_received.append(result)

        scheduler.register_callback(callback)

        policy = RetentionPolicy(
            id="test",
            name="Test",
            triggers=[CleanupTrigger.MANUAL],
        )
        manager.registry.create(policy)

        scheduler.trigger(CleanupTrigger.MANUAL)
        assert len(results_received) == 1


# =============================================================================
# Test Convenience Functions
# =============================================================================


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_cleanup_now(self, temp_dir: Path) -> None:
        """Test cleanup_now function."""
        reset_retention_manager()
        # Use temp dir by setting up manager first
        RetentionManager(base_dir=temp_dir)

        result = cleanup_now(dry_run=True)
        assert result.dry_run is True

    def test_get_storage_stats(self, temp_dir: Path) -> None:
        """Test get_storage_stats function."""
        reset_retention_manager()
        RetentionManager(base_dir=temp_dir)

        stats = get_storage_stats()
        assert "total_size_bytes" in stats
        assert "total_items" in stats


# =============================================================================
# Test Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_cleanup_empty_directory(self, manager: RetentionManager, temp_dir: Path) -> None:
        """Test cleanup on empty directory."""
        backup_dir = temp_dir / "backups"
        backup_dir.mkdir()

        result = manager.run_cleanup(dry_run=False)
        assert result.success is True
        assert result.total_cleaned == 0

    def test_cleanup_nonexistent_directory(self, manager: RetentionManager) -> None:
        """Test cleanup when directories don't exist."""
        result = manager.run_cleanup(dry_run=False)
        assert result.success is True

    def test_cleanup_permission_error(self, manager: RetentionManager, temp_dir: Path) -> None:
        """Test cleanup handles permission errors gracefully."""
        backup_dir = temp_dir / "backups"
        backup_dir.mkdir()
        test_file = backup_dir / "test.json"
        test_file.write_text("{}")

        # Make old
        old_time = (datetime.now() - timedelta(days=60)).timestamp()
        os.utime(test_file, (old_time, old_time))

        # Note: Can't easily test permission errors in a cross-platform way
        # This test ensures the basic flow works
        policy = create_minimal_policy()
        result = manager.run_cleanup(policy=policy, dry_run=False)
        # Should complete without raising
        assert result.completed_at is not None

    def test_cleanup_hidden_files_skipped(self, manager: RetentionManager, temp_dir: Path) -> None:
        """Test hidden files are skipped."""
        backup_dir = temp_dir / "backups"
        backup_dir.mkdir()
        hidden = backup_dir / ".hidden"
        hidden.write_text("{}")

        old_time = (datetime.now() - timedelta(days=60)).timestamp()
        os.utime(hidden, (old_time, old_time))

        policy = create_minimal_policy()
        manager.run_cleanup(policy=policy, dry_run=False)

        # Hidden file should still exist
        assert hidden.exists()

    def test_cleanup_directory_recursive(self, manager: RetentionManager, temp_dir: Path) -> None:
        """Test cleanup handles directories with contents."""
        backup_dir = temp_dir / "backups"
        backup_dir.mkdir()

        # Create an old directory that should be cleaned
        old_dir = backup_dir / "backup_old"
        old_dir.mkdir()
        (old_dir / "data.json").write_text("{}")

        # Create a new directory that should be kept (for min_keep=1)
        new_dir = backup_dir / "backup_new"
        new_dir.mkdir()
        (new_dir / "data.json").write_text("{}")

        # Make old directory old
        old_time = (datetime.now() - timedelta(days=60)).timestamp()
        os.utime(old_dir, (old_time, old_time))

        # Make new directory recent
        new_time = (datetime.now() - timedelta(days=1)).timestamp()
        os.utime(new_dir, (new_time, new_time))

        policy = create_minimal_policy()
        manager.run_cleanup(policy=policy, dry_run=False)

        # Old directory should be cleaned
        assert not old_dir.exists()
        # New directory should remain (min_keep=1)
        assert new_dir.exists()

    def test_concurrent_registry_access(self, registry: RetentionPolicyRegistry) -> None:
        """Test thread-safe registry access."""
        import contextlib

        errors: list[str] = []

        def create_policies(start: int) -> None:
            try:
                for i in range(5):
                    policy = RetentionPolicy(id=f"thread-{start}-{i}", name=f"Policy {start}-{i}")
                    with contextlib.suppress(ValueError):
                        registry.create(policy)  # Duplicate is ok
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=create_policies, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # Should have created some policies
        policies = registry.list_all()
        assert len(policies) > 0

    def test_rule_with_pattern(self, manager: RetentionManager, temp_dir: Path) -> None:
        """Test rule with glob pattern."""
        backup_dir = temp_dir / "backups"
        backup_dir.mkdir()
        (backup_dir / "important.json").write_text("{}")
        (backup_dir / "temp.tmp").write_text("{}")

        # Make both old
        for f in backup_dir.iterdir():
            old_time = (datetime.now() - timedelta(days=60)).timestamp()
            os.utime(f, (old_time, old_time))

        policy = RetentionPolicy(
            id="test",
            name="Test",
            rules=[
                RetentionRule(
                    data_type=DataType.BACKUP,
                    max_age=30,
                    min_keep=0,
                    pattern="*.tmp",  # Only match .tmp files
                )
            ],
        )

        manager.run_cleanup(policy=policy, dry_run=False)

        # .json should remain, .tmp should be deleted
        assert (backup_dir / "important.json").exists()
        assert not (backup_dir / "temp.tmp").exists()


# =============================================================================
# Test Data Types
# =============================================================================


class TestDataTypes:
    """Tests for DataType enum and related functionality."""

    def test_all_data_types(self) -> None:
        """Test all data types are valid."""
        assert DataType.BACKUP.value == "backup"
        assert DataType.STATE.value == "state"
        assert DataType.CACHE.value == "cache"
        assert DataType.LOGS.value == "logs"
        assert DataType.TEMP.value == "temp"
        assert DataType.ALL.value == "all"

    def test_retention_unit_values(self) -> None:
        """Test retention unit values."""
        assert RetentionUnit.HOURS.value == "hours"
        assert RetentionUnit.DAYS.value == "days"
        assert RetentionUnit.WEEKS.value == "weeks"
        assert RetentionUnit.MONTHS.value == "months"

    def test_cleanup_trigger_values(self) -> None:
        """Test cleanup trigger values."""
        assert CleanupTrigger.MANUAL.value == "manual"
        assert CleanupTrigger.STARTUP.value == "startup"
        assert CleanupTrigger.AFTER_SYNC.value == "after_sync"
        assert CleanupTrigger.SCHEDULED.value == "scheduled"
        assert CleanupTrigger.THRESHOLD.value == "threshold"


# =============================================================================
# Test CleanupItem
# =============================================================================


class TestCleanupItem:
    """Tests for CleanupItem."""

    def test_create_item(self) -> None:
        """Test creating a cleanup item."""
        item = CleanupItem(
            path=Path("/test/file.json"),
            data_type=DataType.BACKUP,
            size_bytes=1024,
            age_days=5.5,
            reason="Over age limit",
        )
        assert item.path == Path("/test/file.json")
        assert item.data_type == DataType.BACKUP
        assert item.size_bytes == 1024
        assert item.age_days == 5.5
        assert item.reason == "Over age limit"

    def test_item_to_dict(self) -> None:
        """Test item serialization."""
        item = CleanupItem(
            path=Path("/test/file.json"),
            data_type=DataType.CACHE,
            size_bytes=2048,
            age_days=3.14159,
            reason="Size limit",
        )
        data = item.to_dict()
        assert data["path"] == str(Path("/test/file.json"))
        assert data["data_type"] == "cache"
        assert data["size_bytes"] == 2048
        assert data["age_days"] == 3.14  # Rounded
        assert data["reason"] == "Size limit"
