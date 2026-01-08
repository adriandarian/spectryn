"""Tests for CLI retention commands."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_policy():
    """Create a mock retention policy."""
    policy = MagicMock()
    policy.id = "test-policy"
    policy.name = "Test Policy"
    policy.description = "A test policy"
    policy.preset = MagicMock()
    policy.preset.value = "standard"
    policy.enabled = True
    policy.created_at = "2024-01-01T00:00:00"
    policy.updated_at = "2024-01-02T00:00:00"
    policy.triggers = []
    policy.schedule_hours = 24
    policy.workspace_id = None
    policy.tenant_id = None
    policy.rules = []
    policy.to_dict = MagicMock(
        return_value={
            "id": "test-policy",
            "name": "Test Policy",
            "preset": "standard",
        }
    )
    policy.add_rule = MagicMock()
    policy.remove_rule = MagicMock(return_value=True)
    return policy


@pytest.fixture
def mock_rule():
    """Create a mock retention rule."""
    rule = MagicMock()
    rule.data_type = MagicMock()
    rule.data_type.value = "backup"
    rule.max_age = 30
    rule.max_age_unit = MagicMock()
    rule.max_age_unit.value = "days"
    rule.max_count = 10
    rule.max_size_mb = None
    rule.min_keep = 1
    rule.pattern = None
    rule.enabled = True
    return rule


@pytest.fixture
def mock_manager(mock_policy):
    """Create a mock retention manager."""
    manager = MagicMock()
    manager.registry = MagicMock()
    manager.registry.list_all = MagicMock(return_value=[mock_policy])
    manager.registry.get = MagicMock(return_value=mock_policy)
    manager.registry.create = MagicMock(return_value=mock_policy)
    manager.registry.update = MagicMock(return_value=mock_policy)
    manager.registry.delete = MagicMock(return_value=True)
    return manager


@pytest.fixture
def mock_cleanup_result():
    """Create a mock cleanup result."""
    result = MagicMock()
    result.success = True
    result.items_cleaned = []
    result.summary = MagicMock(return_value="0 items cleaned")
    result.to_dict = MagicMock(return_value={"success": True, "items": 0})
    return result


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestFormatPolicyTable:
    """Tests for _format_policy_table helper."""

    def test_empty_policies(self):
        """Test formatting empty policy list."""
        from spectryn.cli.retention import _format_policy_table

        result = _format_policy_table([])
        assert result == "No policies configured."

    def test_with_policies(self, mock_policy):
        """Test formatting policy list."""
        from spectryn.cli.retention import _format_policy_table

        result = _format_policy_table([mock_policy])
        assert "test-policy" in result
        assert "Test Policy" in result


class TestFormatRulesTable:
    """Tests for _format_rules_table helper."""

    def test_empty_rules(self):
        """Test formatting empty rules list."""
        from spectryn.cli.retention import _format_rules_table

        result = _format_rules_table([])
        assert result == "No rules configured."

    def test_with_rules(self, mock_rule):
        """Test formatting rules list."""
        from spectryn.cli.retention import _format_rules_table

        result = _format_rules_table([mock_rule])
        assert "backup" in result


class TestFormatStorageTable:
    """Tests for _format_storage_table helper."""

    def test_empty_summary(self):
        """Test formatting empty storage summary."""
        from spectryn.cli.retention import _format_storage_table

        result = _format_storage_table({})
        assert result == "No data found."

    def test_with_data(self):
        """Test formatting storage summary with data."""
        from spectryn.cli.retention import _format_storage_table

        summary = {
            "data_types": {"backup": {"path": "/backups", "items": 5, "size_human": "1 MB"}},
            "total_items": 5,
            "total_size_human": "1 MB",
        }
        result = _format_storage_table(summary)
        assert "backup" in result
        assert "TOTAL" in result


class TestFormatCleanupTable:
    """Tests for _format_cleanup_table helper."""

    def test_empty_result(self, mock_cleanup_result):
        """Test formatting empty cleanup result."""
        from spectryn.cli.retention import _format_cleanup_table

        result = _format_cleanup_table(mock_cleanup_result)
        assert result == "No items to clean up."


class TestMakeTable:
    """Tests for _make_table helper."""

    def test_creates_table(self):
        """Test table creation."""
        from spectryn.cli.retention import _make_table

        headers = ["Name", "Value"]
        rows = [["foo", "bar"]]
        result = _make_table(headers, rows)
        assert "Name" in result
        assert "foo" in result


class TestFormatBytes:
    """Tests for _format_bytes helper."""

    def test_bytes(self):
        """Test formatting bytes."""
        from spectryn.cli.retention import _format_bytes

        assert _format_bytes(500) == "500.0 B"

    def test_kilobytes(self):
        """Test formatting kilobytes."""
        from spectryn.cli.retention import _format_bytes

        assert _format_bytes(1024) == "1.0 KB"

    def test_megabytes(self):
        """Test formatting megabytes."""
        from spectryn.cli.retention import _format_bytes

        assert _format_bytes(1024 * 1024) == "1.0 MB"


# =============================================================================
# cmd_retention_list Tests
# =============================================================================


class TestCmdRetentionList:
    """Tests for retention list command."""

    def test_list_empty(self):
        """Test listing when no policies exist."""
        from spectryn.cli.retention import cmd_retention_list

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_mgr = MagicMock()
            mock_mgr.registry.list_all.return_value = []
            mock_get.return_value = mock_mgr

            result = cmd_retention_list()

            assert result == 0

    def test_list_with_policies(self, mock_manager):
        """Test listing existing policies."""
        from spectryn.cli.retention import cmd_retention_list

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager

            result = cmd_retention_list()

            assert result == 0

    def test_list_json_output(self, mock_manager):
        """Test listing with JSON output."""
        from spectryn.cli.retention import cmd_retention_list

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager

            result = cmd_retention_list(output_format="json")

            assert result == 0


# =============================================================================
# cmd_retention_show Tests
# =============================================================================


class TestCmdRetentionShow:
    """Tests for retention show command."""

    def test_show_success(self, mock_manager):
        """Test showing a policy."""
        from spectryn.cli.retention import cmd_retention_show

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager

            result = cmd_retention_show("test-policy")

            assert result == 0

    def test_show_not_found(self, mock_manager):
        """Test showing non-existent policy."""
        from spectryn.cli.retention import cmd_retention_show

        mock_manager.registry.get.return_value = None

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager

            result = cmd_retention_show("missing")

            assert result == 1

    def test_show_json_output(self, mock_manager):
        """Test showing with JSON output."""
        from spectryn.cli.retention import cmd_retention_show

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager

            result = cmd_retention_show("test-policy", output_format="json")

            assert result == 0


# =============================================================================
# cmd_retention_apply Tests
# =============================================================================


class TestCmdRetentionApply:
    """Tests for retention apply command."""

    def test_apply_preset(self, mock_manager, mock_policy):
        """Test applying a preset."""
        from spectryn.cli.retention import cmd_retention_apply

        mock_preset_policy = mock_policy

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager
            with patch("spectryn.core.retention.get_preset_policy") as mock_preset:
                mock_preset.return_value = mock_preset_policy

                result = cmd_retention_apply("standard")

                assert result == 0

    def test_apply_invalid_preset(self):
        """Test applying invalid preset."""
        from spectryn.cli.retention import cmd_retention_apply

        result = cmd_retention_apply("invalid")

        assert result == 1

    def test_apply_with_tenant_scope(self, mock_manager, mock_policy):
        """Test applying preset with tenant scope."""
        from spectryn.cli.retention import cmd_retention_apply

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager
            with patch("spectryn.core.retention.get_preset_policy") as mock_preset:
                mock_preset.return_value = mock_policy

                result = cmd_retention_apply("standard", tenant_id="tenant-1")

                assert result == 0

    def test_apply_with_workspace_scope(self, mock_manager, mock_policy):
        """Test applying preset with workspace scope."""
        from spectryn.cli.retention import cmd_retention_apply

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager
            with patch("spectryn.core.retention.get_preset_policy") as mock_preset:
                mock_preset.return_value = mock_policy

                result = cmd_retention_apply("minimal", workspace_id="ws-1")

                assert result == 0

    def test_apply_updates_existing(self, mock_manager, mock_policy):
        """Test applying preset updates existing policy."""
        from spectryn.cli.retention import cmd_retention_apply

        mock_manager.registry.create.side_effect = ValueError("Already exists")

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager
            with patch("spectryn.core.retention.get_preset_policy") as mock_preset:
                mock_preset.return_value = mock_policy

                result = cmd_retention_apply("standard")

                assert result == 0


# =============================================================================
# cmd_retention_delete Tests
# =============================================================================


class TestCmdRetentionDelete:
    """Tests for retention delete command."""

    def test_delete_with_force(self, mock_manager):
        """Test force deleting a policy."""
        from spectryn.cli.retention import cmd_retention_delete

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager

            result = cmd_retention_delete("test-policy", force=True)

            assert result == 0

    def test_delete_not_found(self, mock_manager):
        """Test deleting non-existent policy."""
        from spectryn.cli.retention import cmd_retention_delete

        mock_manager.registry.get.return_value = None

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager

            result = cmd_retention_delete("missing", force=True)

            assert result == 1

    def test_delete_cancelled(self, mock_manager):
        """Test cancelling delete."""
        from spectryn.cli.retention import cmd_retention_delete

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager
            with patch("builtins.input", return_value="no"):
                result = cmd_retention_delete("test-policy", force=False)

            assert result == 1

    def test_delete_confirmed(self, mock_manager):
        """Test confirming delete."""
        from spectryn.cli.retention import cmd_retention_delete

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager
            with patch("builtins.input", return_value="yes"):
                result = cmd_retention_delete("test-policy", force=False)

            assert result == 0

    def test_delete_failed(self, mock_manager):
        """Test delete failure."""
        from spectryn.cli.retention import cmd_retention_delete

        mock_manager.registry.delete.return_value = False

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager

            result = cmd_retention_delete("test-policy", force=True)

            assert result == 1


# =============================================================================
# cmd_retention_enable Tests
# =============================================================================


class TestCmdRetentionEnable:
    """Tests for retention enable command."""

    def test_enable_success(self, mock_manager, mock_policy):
        """Test enabling a policy."""
        from spectryn.cli.retention import cmd_retention_enable

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager

            result = cmd_retention_enable("test-policy")

            assert result == 0
            assert mock_policy.enabled is True

    def test_enable_not_found(self, mock_manager):
        """Test enabling non-existent policy."""
        from spectryn.cli.retention import cmd_retention_enable

        mock_manager.registry.get.return_value = None

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager

            result = cmd_retention_enable("missing")

            assert result == 1


# =============================================================================
# cmd_retention_disable Tests
# =============================================================================


class TestCmdRetentionDisable:
    """Tests for retention disable command."""

    def test_disable_success(self, mock_manager, mock_policy):
        """Test disabling a policy."""
        from spectryn.cli.retention import cmd_retention_disable

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager

            result = cmd_retention_disable("test-policy")

            assert result == 0
            assert mock_policy.enabled is False

    def test_disable_not_found(self, mock_manager):
        """Test disabling non-existent policy."""
        from spectryn.cli.retention import cmd_retention_disable

        mock_manager.registry.get.return_value = None

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager

            result = cmd_retention_disable("missing")

            assert result == 1


# =============================================================================
# cmd_retention_cleanup Tests
# =============================================================================


class TestCmdRetentionCleanup:
    """Tests for retention cleanup command."""

    def test_cleanup_dry_run(self, mock_manager, mock_cleanup_result):
        """Test dry run cleanup."""
        from spectryn.cli.retention import cmd_retention_cleanup

        mock_manager.run_cleanup.return_value = mock_cleanup_result

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager

            result = cmd_retention_cleanup(dry_run=True)

            assert result == 0

    def test_cleanup_actual(self, mock_manager, mock_cleanup_result):
        """Test actual cleanup."""
        from spectryn.cli.retention import cmd_retention_cleanup

        mock_manager.run_cleanup.return_value = mock_cleanup_result

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager

            result = cmd_retention_cleanup(dry_run=False)

            assert result == 0

    def test_cleanup_with_policy(self, mock_manager, mock_cleanup_result):
        """Test cleanup with specific policy."""
        from spectryn.cli.retention import cmd_retention_cleanup

        mock_manager.run_cleanup.return_value = mock_cleanup_result

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager

            result = cmd_retention_cleanup(policy_id="test-policy")

            assert result == 0

    def test_cleanup_policy_not_found(self, mock_manager):
        """Test cleanup with non-existent policy."""
        from spectryn.cli.retention import cmd_retention_cleanup

        mock_manager.registry.get.return_value = None

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager

            result = cmd_retention_cleanup(policy_id="missing")

            assert result == 1

    def test_cleanup_with_data_types(self, mock_manager, mock_cleanup_result):
        """Test cleanup with specific data types."""
        from spectryn.cli.retention import cmd_retention_cleanup

        mock_manager.run_cleanup.return_value = mock_cleanup_result

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager

            result = cmd_retention_cleanup(data_types=["backup", "cache"])

            assert result == 0

    def test_cleanup_invalid_data_type(self, mock_manager):
        """Test cleanup with invalid data type."""
        from spectryn.cli.retention import cmd_retention_cleanup

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager

            result = cmd_retention_cleanup(data_types=["invalid"])

            assert result == 1

    def test_cleanup_json_output(self, mock_manager, mock_cleanup_result):
        """Test cleanup with JSON output."""
        from spectryn.cli.retention import cmd_retention_cleanup

        mock_manager.run_cleanup.return_value = mock_cleanup_result

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager

            result = cmd_retention_cleanup(output_format="json")

            assert result == 0

    def test_cleanup_failure(self, mock_manager, mock_cleanup_result):
        """Test cleanup failure."""
        from spectryn.cli.retention import cmd_retention_cleanup

        mock_cleanup_result.success = False
        mock_manager.run_cleanup.return_value = mock_cleanup_result

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager

            result = cmd_retention_cleanup()

            assert result == 1


# =============================================================================
# cmd_retention_stats Tests
# =============================================================================


class TestCmdRetentionStats:
    """Tests for retention stats command."""

    def test_stats_global(self):
        """Test global storage stats."""
        from spectryn.cli.retention import cmd_retention_stats

        with patch("spectryn.cli.retention.get_storage_stats") as mock_stats:
            mock_stats.return_value = {
                "data_types": {},
                "total_items": 0,
                "total_size_human": "0 B",
            }

            result = cmd_retention_stats()

            assert result == 0

    def test_stats_with_tenant(self):
        """Test stats with tenant scope."""
        from spectryn.cli.retention import cmd_retention_stats

        with patch("spectryn.cli.retention.get_storage_stats") as mock_stats:
            mock_stats.return_value = {"data_types": {}}

            result = cmd_retention_stats(tenant_id="tenant-1")

            assert result == 0

    def test_stats_with_workspace(self):
        """Test stats with workspace scope."""
        from spectryn.cli.retention import cmd_retention_stats

        with patch("spectryn.cli.retention.get_storage_stats") as mock_stats:
            mock_stats.return_value = {"data_types": {}}

            result = cmd_retention_stats(workspace_id="ws-1")

            assert result == 0

    def test_stats_json_output(self):
        """Test stats with JSON output."""
        from spectryn.cli.retention import cmd_retention_stats

        with patch("spectryn.cli.retention.get_storage_stats") as mock_stats:
            mock_stats.return_value = {"data_types": {}}

            result = cmd_retention_stats(output_format="json")

            assert result == 0


# =============================================================================
# cmd_retention_presets Tests
# =============================================================================


class TestCmdRetentionPresets:
    """Tests for retention presets command."""

    def test_presets(self):
        """Test showing presets."""
        from spectryn.cli.retention import cmd_retention_presets

        result = cmd_retention_presets()

        assert result == 0


# =============================================================================
# cmd_retention_create Tests
# =============================================================================


class TestCmdRetentionCreate:
    """Tests for retention create command."""

    def test_create_with_backup_rule(self, mock_manager):
        """Test creating policy with backup rule."""
        from spectryn.cli.retention import cmd_retention_create

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager

            result = cmd_retention_create(
                policy_id="new-policy",
                name="New Policy",
                backup_days=30,
                backup_count=10,
            )

            assert result == 0

    def test_create_with_all_rules(self, mock_manager):
        """Test creating policy with all rule types."""
        from spectryn.cli.retention import cmd_retention_create

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager

            result = cmd_retention_create(
                policy_id="new-policy",
                name="New Policy",
                backup_days=30,
                state_days=14,
                cache_days=7,
                logs_days=30,
            )

            assert result == 0

    def test_create_no_rules(self, mock_manager):
        """Test creating policy without rules fails."""
        from spectryn.cli.retention import cmd_retention_create

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager

            result = cmd_retention_create(
                policy_id="new-policy",
                name="New Policy",
            )

            assert result == 1

    def test_create_with_triggers(self, mock_manager):
        """Test creating policy with triggers."""
        from spectryn.cli.retention import cmd_retention_create

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager

            result = cmd_retention_create(
                policy_id="new-policy",
                name="New Policy",
                backup_days=30,
                triggers=["manual", "scheduled"],
            )

            assert result == 0

    def test_create_invalid_trigger(self, mock_manager):
        """Test creating policy with invalid trigger."""
        from spectryn.cli.retention import cmd_retention_create

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager

            result = cmd_retention_create(
                policy_id="new-policy",
                name="New Policy",
                backup_days=30,
                triggers=["invalid"],
            )

            assert result == 1

    def test_create_error(self, mock_manager):
        """Test create with error."""
        from spectryn.cli.retention import cmd_retention_create

        mock_manager.registry.create.side_effect = ValueError("Already exists")

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager

            result = cmd_retention_create(
                policy_id="existing",
                name="Existing",
                backup_days=30,
            )

            assert result == 1


# =============================================================================
# cmd_retention_add_rule Tests
# =============================================================================


class TestCmdRetentionAddRule:
    """Tests for retention add rule command."""

    def test_add_rule_success(self, mock_manager, mock_policy):
        """Test adding a rule."""
        from spectryn.cli.retention import cmd_retention_add_rule

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager

            result = cmd_retention_add_rule(
                policy_id="test-policy",
                data_type="backup",
                max_age=30,
            )

            assert result == 0

    def test_add_rule_not_found(self, mock_manager):
        """Test adding rule to non-existent policy."""
        from spectryn.cli.retention import cmd_retention_add_rule

        mock_manager.registry.get.return_value = None

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager

            result = cmd_retention_add_rule(
                policy_id="missing",
                data_type="backup",
                max_age=30,
            )

            assert result == 1

    def test_add_rule_invalid_type(self, mock_manager):
        """Test adding rule with invalid data type."""
        from spectryn.cli.retention import cmd_retention_add_rule

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager

            result = cmd_retention_add_rule(
                policy_id="test-policy",
                data_type="invalid",
                max_age=30,
            )

            assert result == 1

    def test_add_rule_invalid_unit(self, mock_manager):
        """Test adding rule with invalid unit."""
        from spectryn.cli.retention import cmd_retention_add_rule

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager

            result = cmd_retention_add_rule(
                policy_id="test-policy",
                data_type="backup",
                max_age=30,
                max_age_unit="invalid",
            )

            assert result == 1


# =============================================================================
# cmd_retention_remove_rule Tests
# =============================================================================


class TestCmdRetentionRemoveRule:
    """Tests for retention remove rule command."""

    def test_remove_rule_success(self, mock_manager):
        """Test removing a rule."""
        from spectryn.cli.retention import cmd_retention_remove_rule

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager

            result = cmd_retention_remove_rule(
                policy_id="test-policy",
                data_type="backup",
            )

            assert result == 0

    def test_remove_rule_not_found(self, mock_manager):
        """Test removing rule from non-existent policy."""
        from spectryn.cli.retention import cmd_retention_remove_rule

        mock_manager.registry.get.return_value = None

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager

            result = cmd_retention_remove_rule(
                policy_id="missing",
                data_type="backup",
            )

            assert result == 1

    def test_remove_rule_invalid_type(self, mock_manager):
        """Test removing rule with invalid data type."""
        from spectryn.cli.retention import cmd_retention_remove_rule

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager

            result = cmd_retention_remove_rule(
                policy_id="test-policy",
                data_type="invalid",
            )

            assert result == 1

    def test_remove_rule_not_exists(self, mock_manager, mock_policy):
        """Test removing non-existent rule."""
        from spectryn.cli.retention import cmd_retention_remove_rule

        mock_policy.remove_rule.return_value = False

        with patch("spectryn.cli.retention.get_retention_manager") as mock_get:
            mock_get.return_value = mock_manager

            result = cmd_retention_remove_rule(
                policy_id="test-policy",
                data_type="backup",
            )

            assert result == 1
