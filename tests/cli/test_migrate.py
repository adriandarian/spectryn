"""Tests for CLI migrate command."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from spectryn.cli.exit_codes import ExitCode
from spectryn.cli.migrate import (
    DEFAULT_STATUS_MAPS,
    MigrationMapping,
    MigrationResult,
    create_default_mapping,
    format_migration_plan,
    run_migrate,
)


# =============================================================================
# MigrationMapping Tests
# =============================================================================


class TestMigrationMapping:
    """Tests for MigrationMapping dataclass."""

    def test_default_values(self):
        """Test default values."""
        mapping = MigrationMapping()

        assert mapping.status_map == {}
        assert mapping.priority_map == {}
        assert mapping.user_map == {}
        assert mapping.type_map == {}

    def test_custom_values(self):
        """Test custom values."""
        mapping = MigrationMapping(
            status_map={"To Do": "open"},
            priority_map={"High": "Critical"},
            user_map={"user@source.com": "user@target.com"},
            type_map={"Story": "issue"},
        )

        assert mapping.status_map == {"To Do": "open"}
        assert mapping.priority_map == {"High": "Critical"}
        assert mapping.user_map == {"user@source.com": "user@target.com"}
        assert mapping.type_map == {"Story": "issue"}


# =============================================================================
# MigrationResult Tests
# =============================================================================


class TestMigrationResult:
    """Tests for MigrationResult dataclass."""

    def test_default_values(self):
        """Test default values."""
        result = MigrationResult()

        assert result.success is True
        assert result.issues_migrated == 0
        assert result.issues_failed == 0
        assert result.comments_migrated == 0
        assert result.attachments_migrated == 0
        assert result.errors == []
        assert result.warnings == []
        assert result.issue_mapping == {}

    def test_custom_values(self):
        """Test custom values."""
        result = MigrationResult(
            success=False,
            issues_migrated=10,
            issues_failed=2,
            comments_migrated=50,
            attachments_migrated=5,
            errors=["Error 1"],
            warnings=["Warning 1"],
            issue_mapping={"OLD-1": "NEW-1"},
        )

        assert result.success is False
        assert result.issues_migrated == 10
        assert result.issues_failed == 2
        assert result.issue_mapping == {"OLD-1": "NEW-1"}


# =============================================================================
# DEFAULT_STATUS_MAPS Tests
# =============================================================================


class TestDefaultStatusMaps:
    """Tests for DEFAULT_STATUS_MAPS constant."""

    def test_jira_to_github_mapping_exists(self):
        """Test Jira to GitHub mapping exists."""
        assert ("jira", "github") in DEFAULT_STATUS_MAPS

    def test_jira_to_linear_mapping_exists(self):
        """Test Jira to Linear mapping exists."""
        assert ("jira", "linear") in DEFAULT_STATUS_MAPS

    def test_github_to_jira_mapping_exists(self):
        """Test GitHub to Jira mapping exists."""
        assert ("github", "jira") in DEFAULT_STATUS_MAPS

    def test_linear_to_jira_mapping_exists(self):
        """Test Linear to Jira mapping exists."""
        assert ("linear", "jira") in DEFAULT_STATUS_MAPS

    def test_jira_to_github_status_values(self):
        """Test Jira to GitHub status values."""
        mapping = DEFAULT_STATUS_MAPS[("jira", "github")]

        assert mapping["Done"] == "closed"
        assert mapping["To Do"] == "open"


# =============================================================================
# create_default_mapping Tests
# =============================================================================


class TestCreateDefaultMapping:
    """Tests for create_default_mapping function."""

    def test_create_jira_to_github_mapping(self):
        """Test creating Jira to GitHub mapping."""
        mapping = create_default_mapping("jira", "github")

        assert "Done" in mapping.status_map
        assert "High" in mapping.priority_map

    def test_create_unknown_mapping(self):
        """Test creating mapping for unknown pair."""
        mapping = create_default_mapping("unknown1", "unknown2")

        assert mapping.status_map == {}
        assert "High" in mapping.priority_map  # Priority always included

    def test_case_insensitive(self):
        """Test case insensitivity."""
        mapping1 = create_default_mapping("JIRA", "GITHUB")
        mapping2 = create_default_mapping("jira", "github")

        assert mapping1.status_map == mapping2.status_map

    def test_priority_mapping_always_included(self):
        """Test priority mapping is always included."""
        mapping = create_default_mapping("jira", "linear")

        assert "Critical" in mapping.priority_map
        assert "High" in mapping.priority_map
        assert "Medium" in mapping.priority_map
        assert "Low" in mapping.priority_map


# =============================================================================
# format_migration_plan Tests
# =============================================================================


class TestFormatMigrationPlan:
    """Tests for format_migration_plan function."""

    def test_format_basic_plan(self):
        """Test basic plan formatting."""
        mapping = MigrationMapping(status_map={"To Do": "open"})

        result = format_migration_plan(
            source="jira", target="github", issues_count=10, mapping=mapping, color=False
        )

        assert "Migration Plan" in result
        assert "Source: jira" in result
        assert "Target: github" in result
        assert "Issues: 10" in result

    def test_format_with_status_mappings(self):
        """Test plan with status mappings."""
        mapping = MigrationMapping(status_map={"To Do": "open", "Done": "closed"})

        result = format_migration_plan(
            source="jira", target="github", issues_count=5, mapping=mapping, color=False
        )

        assert "Status Mappings:" in result
        assert "To Do → open" in result or "Done → closed" in result

    def test_format_with_priority_mappings(self):
        """Test plan with priority mappings."""
        mapping = MigrationMapping(priority_map={"High": "Critical", "Low": "Minor"})

        result = format_migration_plan(
            source="jira", target="github", issues_count=5, mapping=mapping, color=False
        )

        assert "Priority Mappings:" in result

    def test_format_with_colors(self):
        """Test plan with colors enabled."""
        mapping = MigrationMapping(status_map={"To Do": "open"})

        result = format_migration_plan(
            source="jira", target="github", issues_count=5, mapping=mapping, color=True
        )

        # Should have color codes
        assert "\033[" in result

    def test_format_truncates_many_mappings(self):
        """Test truncation with many mappings."""
        mapping = MigrationMapping(status_map={f"Status{i}": f"target{i}" for i in range(10)})

        result = format_migration_plan(
            source="jira", target="github", issues_count=5, mapping=mapping, color=False
        )

        assert "... and 5 more" in result


# =============================================================================
# run_migrate Tests
# =============================================================================


class TestRunMigrate:
    """Tests for run_migrate function."""

    @pytest.fixture
    def mock_console(self):
        """Create mock console."""
        console = MagicMock()
        console.color = True
        return console

    def test_unsupported_source_tracker(self, mock_console):
        """Test with unsupported source tracker."""
        with patch("spectryn.cli.logging.setup_logging"):
            result = run_migrate(mock_console, source_type="unsupported", target_type="github")

        assert result == ExitCode.CONFIG_ERROR
        mock_console.error.assert_called()

    def test_unsupported_target_tracker(self, mock_console):
        """Test with unsupported target tracker."""
        with patch("spectryn.cli.logging.setup_logging"):
            result = run_migrate(mock_console, source_type="jira", target_type="unsupported")

        assert result == ExitCode.CONFIG_ERROR
        mock_console.error.assert_called()

    def test_same_source_and_target(self, mock_console):
        """Test source and target cannot be the same."""
        with patch("spectryn.cli.logging.setup_logging"):
            result = run_migrate(mock_console, source_type="jira", target_type="jira")

        assert result == ExitCode.CONFIG_ERROR
        mock_console.error.assert_called()

    def test_migrate_to_markdown(self, mock_console):
        """Test migration to markdown."""
        with patch("spectryn.cli.logging.setup_logging"):
            result = run_migrate(mock_console, source_type="jira", target_type="markdown")

        assert result == ExitCode.SUCCESS

    def test_basic_migration_dry_run(self, mock_console):
        """Test basic migration in dry run."""
        with patch("spectryn.cli.logging.setup_logging"):
            result = run_migrate(
                mock_console,
                source_type="jira",
                target_type="github",
                dry_run=True,
            )

        assert result == ExitCode.SUCCESS
        mock_console.warning.assert_called()  # DRY RUN warning

    def test_migration_with_project(self, mock_console):
        """Test migration with project specified."""
        with patch("spectryn.cli.logging.setup_logging"):
            result = run_migrate(
                mock_console,
                source_type="jira",
                target_type="github",
                source_project="PROJ",
                target_project="org/repo",
            )

        assert result == ExitCode.SUCCESS
        mock_console.info.assert_called()

    def test_migration_with_epic(self, mock_console):
        """Test migration with epic specified."""
        with patch("spectryn.cli.logging.setup_logging"):
            result = run_migrate(
                mock_console,
                source_type="jira",
                target_type="github",
                epic_key="EPIC-123",
            )

        assert result == ExitCode.SUCCESS

    def test_migration_with_mapping_file(self, mock_console, tmp_path):
        """Test migration with mapping file."""
        mapping_file = tmp_path / "mapping.yaml"
        mapping_file.write_text("status_map:\n  To Do: open")

        with patch("spectryn.cli.logging.setup_logging"):
            result = run_migrate(
                mock_console,
                source_type="jira",
                target_type="github",
                mapping_file=str(mapping_file),
            )

        assert result == ExitCode.SUCCESS

    def test_migration_nonexistent_mapping_file(self, mock_console, tmp_path):
        """Test migration with nonexistent mapping file uses defaults."""
        with patch("spectryn.cli.logging.setup_logging"):
            result = run_migrate(
                mock_console,
                source_type="jira",
                target_type="github",
                mapping_file=str(tmp_path / "nonexistent.yaml"),
            )

        assert result == ExitCode.SUCCESS

    def test_all_supported_trackers(self, mock_console):
        """Test all supported trackers are valid."""
        supported = ["jira", "github", "linear", "azure", "gitlab", "markdown"]

        for source in supported[:2]:  # Just test a couple as source
            for target in supported[2:4]:  # And a couple as target
                if source != target:
                    with patch("spectryn.cli.logging.setup_logging"):
                        result = run_migrate(mock_console, source_type=source, target_type=target)
                    assert result == ExitCode.SUCCESS

    def test_migration_github_to_jira(self, mock_console):
        """Test GitHub to Jira migration."""
        with patch("spectryn.cli.logging.setup_logging"):
            result = run_migrate(mock_console, source_type="github", target_type="jira")

        assert result == ExitCode.SUCCESS

    def test_migration_linear_to_jira(self, mock_console):
        """Test Linear to Jira migration."""
        with patch("spectryn.cli.logging.setup_logging"):
            result = run_migrate(mock_console, source_type="linear", target_type="jira")

        assert result == ExitCode.SUCCESS

    def test_migration_jira_to_linear(self, mock_console):
        """Test Jira to Linear migration."""
        with patch("spectryn.cli.logging.setup_logging"):
            result = run_migrate(mock_console, source_type="jira", target_type="linear")

        assert result == ExitCode.SUCCESS

    def test_migration_with_comments_flag(self, mock_console):
        """Test migration with comments flag."""
        with patch("spectryn.cli.logging.setup_logging"):
            result = run_migrate(
                mock_console,
                source_type="jira",
                target_type="github",
                include_comments=True,
            )

        assert result == ExitCode.SUCCESS

    def test_migration_with_attachments_flag(self, mock_console):
        """Test migration with attachments flag."""
        with patch("spectryn.cli.logging.setup_logging"):
            result = run_migrate(
                mock_console,
                source_type="jira",
                target_type="github",
                include_attachments=True,
            )

        assert result == ExitCode.SUCCESS
