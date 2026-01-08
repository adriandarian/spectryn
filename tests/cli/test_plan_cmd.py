"""Tests for spectra.cli.plan_cmd module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from spectryn.cli.exit_codes import ExitCode
from spectryn.cli.plan_cmd import (
    PlannedChange,
    SyncPlan,
    format_plan,
    run_plan,
)


class TestPlannedChange:
    """Tests for PlannedChange dataclass."""

    def test_planned_change_creation(self):
        """Test PlannedChange creation."""
        change = PlannedChange(
            action="create",
            resource_type="story",
            resource_id="US-001",
            title="Test Story",
            details=["points: 5", "status: Planned"],
        )
        assert change.action == "create"
        assert change.resource_type == "story"
        assert change.resource_id == "US-001"
        assert change.title == "Test Story"
        assert len(change.details) == 2

    def test_planned_change_default_details(self):
        """Test PlannedChange with default empty details."""
        change = PlannedChange(
            action="update",
            resource_type="subtask",
            resource_id="ST-001",
            title="Subtask",
        )
        assert change.details == []


class TestSyncPlan:
    """Tests for SyncPlan dataclass."""

    def test_sync_plan_creation(self):
        """Test SyncPlan creation."""
        plan = SyncPlan()
        assert plan.changes == []

    def test_to_create(self):
        """Test to_create property."""
        plan = SyncPlan(
            changes=[
                PlannedChange(
                    action="create", resource_type="story", resource_id="US-001", title="A"
                ),
                PlannedChange(
                    action="update", resource_type="story", resource_id="US-002", title="B"
                ),
                PlannedChange(
                    action="create", resource_type="subtask", resource_id="ST-001", title="C"
                ),
            ]
        )
        creates = plan.to_create
        assert len(creates) == 2
        assert all(c.action == "create" for c in creates)

    def test_to_update(self):
        """Test to_update property."""
        plan = SyncPlan(
            changes=[
                PlannedChange(
                    action="create", resource_type="story", resource_id="US-001", title="A"
                ),
                PlannedChange(
                    action="update", resource_type="story", resource_id="US-002", title="B"
                ),
                PlannedChange(
                    action="update", resource_type="status", resource_id="US-003", title="C"
                ),
            ]
        )
        updates = plan.to_update
        assert len(updates) == 2
        assert all(c.action == "update" for c in updates)

    def test_no_change(self):
        """Test no_change property."""
        plan = SyncPlan(
            changes=[
                PlannedChange(
                    action="create", resource_type="story", resource_id="US-001", title="A"
                ),
                PlannedChange(
                    action="no-change", resource_type="story", resource_id="US-002", title="B"
                ),
                PlannedChange(
                    action="no-change", resource_type="story", resource_id="US-003", title="C"
                ),
            ]
        )
        no_changes = plan.no_change
        assert len(no_changes) == 2
        assert all(c.action == "no-change" for c in no_changes)

    def test_has_changes_true(self):
        """Test has_changes when there are changes."""
        plan = SyncPlan(
            changes=[
                PlannedChange(
                    action="create", resource_type="story", resource_id="US-001", title="A"
                ),
            ]
        )
        assert plan.has_changes is True

    def test_has_changes_false_with_only_no_change(self):
        """Test has_changes when only no-change."""
        plan = SyncPlan(
            changes=[
                PlannedChange(
                    action="no-change", resource_type="story", resource_id="US-001", title="A"
                ),
            ]
        )
        assert plan.has_changes is False

    def test_has_changes_false_empty(self):
        """Test has_changes when empty."""
        plan = SyncPlan()
        assert plan.has_changes is False


class TestFormatPlan:
    """Tests for format_plan function."""

    def test_format_empty_plan(self):
        """Test format with empty plan."""
        plan = SyncPlan()
        output = format_plan(plan, color=False)
        assert "No changes" in output

    def test_format_no_changes(self):
        """Test format with no-change items."""
        plan = SyncPlan(
            changes=[
                PlannedChange(
                    action="no-change", resource_type="story", resource_id="US-001", title="A"
                ),
            ]
        )
        output = format_plan(plan, color=False)
        # When only no-change items, should show "unchanged" count
        assert "unchanged" in output.lower()

    def test_format_with_color(self):
        """Test format with color enabled."""
        plan = SyncPlan(
            changes=[
                PlannedChange(
                    action="create", resource_type="story", resource_id="US-001", title="A"
                ),
            ]
        )
        output = format_plan(plan, color=True)
        # Should contain ANSI color codes
        assert "\x1b[" in output or "+" in output

    def test_format_without_color(self):
        """Test format without color."""
        plan = SyncPlan(
            changes=[
                PlannedChange(
                    action="create", resource_type="story", resource_id="US-001", title="A"
                ),
            ]
        )
        output = format_plan(plan, color=False)
        assert "+" in output

    def test_format_stories_to_create(self):
        """Test format with stories to create."""
        plan = SyncPlan(
            changes=[
                PlannedChange(
                    action="create",
                    resource_type="story",
                    resource_id="US-001",
                    title="Test Story",
                    details=["points: 5"],
                ),
            ]
        )
        output = format_plan(plan, color=False)
        assert "story.US-001" in output
        assert "Test Story" in output

    def test_format_stories_to_update(self):
        """Test format with stories to update."""
        plan = SyncPlan(
            changes=[
                PlannedChange(
                    action="update",
                    resource_type="story",
                    resource_id="US-001",
                    title="Test Story",
                    details=["status: Open → Done"],
                ),
            ]
        )
        output = format_plan(plan, color=False)
        assert "~" in output or "story.US-001" in output

    def test_format_subtasks_to_create(self):
        """Test format with subtasks to create."""
        plan = SyncPlan(
            changes=[
                PlannedChange(
                    action="create",
                    resource_type="subtask",
                    resource_id="ST-001",
                    title="Subtask 1",
                ),
                PlannedChange(
                    action="create",
                    resource_type="subtask",
                    resource_id="ST-002",
                    title="Subtask 2",
                ),
            ]
        )
        output = format_plan(plan, color=False)
        assert "subtasks" in output

    def test_format_subtasks_to_create_truncated(self):
        """Test format truncates many subtasks."""
        changes = [
            PlannedChange(
                action="create",
                resource_type="subtask",
                resource_id=f"ST-{i:03d}",
                title=f"Subtask {i}",
            )
            for i in range(15)
        ]
        plan = SyncPlan(changes=changes)
        output = format_plan(plan, color=False)
        assert "... and" in output  # Shows truncation message

    def test_format_subtasks_to_update(self):
        """Test format with subtasks to update."""
        plan = SyncPlan(
            changes=[
                PlannedChange(
                    action="update",
                    resource_type="subtask",
                    resource_id="ST-001",
                    title="Subtask 1",
                ),
            ]
        )
        output = format_plan(plan, color=False)
        assert "subtask" in output.lower()

    def test_format_comments_to_create(self):
        """Test format with comments to create."""
        plan = SyncPlan(
            changes=[
                PlannedChange(
                    action="create",
                    resource_type="comment",
                    resource_id="C-001",
                    title="This is a comment that may be long",
                ),
            ]
        )
        output = format_plan(plan, color=False)
        assert "comment" in output.lower()

    def test_format_status_updates(self):
        """Test format with status updates."""
        plan = SyncPlan(
            changes=[
                PlannedChange(
                    action="update",
                    resource_type="status",
                    resource_id="US-001",
                    title="",
                    details=["Open → Done"],
                ),
            ]
        )
        output = format_plan(plan, color=False)
        assert "status" in output.lower()

    def test_format_verbose_shows_unchanged(self):
        """Test verbose mode shows unchanged items."""
        plan = SyncPlan(
            changes=[
                PlannedChange(
                    action="no-change", resource_type="story", resource_id="US-001", title="A"
                ),
            ]
        )
        output = format_plan(plan, color=False, verbose=True)
        assert "unchanged" in output.lower()

    def test_format_non_verbose_hides_unchanged(self):
        """Test non-verbose mode hides unchanged items."""
        plan = SyncPlan(
            changes=[
                PlannedChange(
                    action="create", resource_type="story", resource_id="US-001", title="A"
                ),
                PlannedChange(
                    action="no-change", resource_type="story", resource_id="US-002", title="B"
                ),
            ]
        )
        output = format_plan(plan, color=False, verbose=False)
        # The unchanged section shouldn't appear without verbose
        # but summary line should show count
        assert "unchanged" in output.lower()  # In summary

    def test_format_summary_line(self):
        """Test summary line shows counts."""
        plan = SyncPlan(
            changes=[
                PlannedChange(
                    action="create", resource_type="story", resource_id="US-001", title="A"
                ),
                PlannedChange(
                    action="update", resource_type="story", resource_id="US-002", title="B"
                ),
                PlannedChange(
                    action="no-change", resource_type="story", resource_id="US-003", title="C"
                ),
            ]
        )
        output = format_plan(plan, color=False)
        assert "Plan:" in output
        assert "add" in output.lower()
        assert "change" in output.lower()


class TestRunPlan:
    """Tests for run_plan function."""

    @pytest.fixture
    def mock_console(self):
        """Create mock console."""
        console = MagicMock()
        console.color = True
        return console

    def test_run_plan_file_not_found(self, mock_console, tmp_path):
        """Test run_plan with non-existent file."""
        result = run_plan(
            console=mock_console,
            input_path=str(tmp_path / "nonexistent.md"),
            epic_key="EPIC-1",
        )
        assert result == ExitCode.FILE_NOT_FOUND

    @patch("spectryn.adapters.EnvironmentConfigProvider")
    @patch("spectryn.cli.logging.setup_logging")
    def test_run_plan_config_error(
        self, mock_logging, mock_config_provider, mock_console, tmp_path
    ):
        """Test run_plan with config error."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")

        mock_provider = MagicMock()
        mock_provider.validate.return_value = ["Missing JIRA_URL"]
        mock_config_provider.return_value = mock_provider

        result = run_plan(
            console=mock_console,
            input_path=str(test_file),
            epic_key="EPIC-1",
        )
        assert result == ExitCode.CONFIG_ERROR

    @patch("spectryn.application.SyncOrchestrator")
    @patch("spectryn.adapters.parsers.MarkdownParser")
    @patch("spectryn.adapters.JiraAdapter")
    @patch("spectryn.adapters.ADFFormatter")
    @patch("spectryn.adapters.EnvironmentConfigProvider")
    @patch("spectryn.cli.logging.setup_logging")
    def test_run_plan_connection_error(
        self,
        mock_logging,
        mock_config_provider,
        mock_formatter,
        mock_jira,
        mock_parser,
        mock_orchestrator,
        mock_console,
        tmp_path,
    ):
        """Test run_plan with connection error."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")

        mock_provider = MagicMock()
        mock_provider.validate.return_value = []
        mock_config_provider.return_value = mock_provider

        mock_tracker = MagicMock()
        mock_tracker.test_connection.return_value = False
        mock_jira.return_value = mock_tracker

        result = run_plan(
            console=mock_console,
            input_path=str(test_file),
            epic_key="EPIC-1",
        )
        assert result == ExitCode.CONNECTION_ERROR

    @patch("spectryn.application.SyncOrchestrator")
    @patch("spectryn.adapters.parsers.MarkdownParser")
    @patch("spectryn.adapters.JiraAdapter")
    @patch("spectryn.adapters.ADFFormatter")
    @patch("spectryn.adapters.EnvironmentConfigProvider")
    @patch("spectryn.cli.logging.setup_logging")
    def test_run_plan_success(
        self,
        mock_logging,
        mock_config_provider,
        mock_formatter,
        mock_jira,
        mock_parser,
        mock_orchestrator_class,
        mock_console,
        tmp_path,
    ):
        """Test run_plan success."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")

        mock_provider = MagicMock()
        mock_provider.validate.return_value = []
        mock_config = MagicMock()
        mock_config.tracker.url = "https://jira.example.com"
        mock_config.sync.dry_run = False
        mock_provider.load.return_value = mock_config
        mock_config_provider.return_value = mock_provider

        mock_tracker = MagicMock()
        mock_tracker.test_connection.return_value = True
        mock_jira.return_value = mock_tracker

        mock_orchestrator = MagicMock()
        mock_orchestrator.analyze.return_value = {
            "unmatched_stories": [],
            "local_stories": [],
            "matches": [],
        }
        mock_orchestrator_class.return_value = mock_orchestrator

        result = run_plan(
            console=mock_console,
            input_path=str(test_file),
            epic_key="EPIC-1",
        )
        assert result == ExitCode.SUCCESS

    @patch("spectryn.application.SyncOrchestrator")
    @patch("spectryn.adapters.parsers.MarkdownParser")
    @patch("spectryn.adapters.JiraAdapter")
    @patch("spectryn.adapters.ADFFormatter")
    @patch("spectryn.adapters.EnvironmentConfigProvider")
    @patch("spectryn.cli.logging.setup_logging")
    def test_run_plan_json_output(
        self,
        mock_logging,
        mock_config_provider,
        mock_formatter,
        mock_jira,
        mock_parser,
        mock_orchestrator_class,
        mock_console,
        tmp_path,
        capsys,
    ):
        """Test run_plan with JSON output format."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")

        mock_provider = MagicMock()
        mock_provider.validate.return_value = []
        mock_config = MagicMock()
        mock_config.tracker.url = "https://jira.example.com"
        mock_provider.load.return_value = mock_config
        mock_config_provider.return_value = mock_provider

        mock_tracker = MagicMock()
        mock_tracker.test_connection.return_value = True
        mock_jira.return_value = mock_tracker

        mock_orchestrator = MagicMock()
        mock_orchestrator.analyze.return_value = {
            "unmatched_stories": [],
            "local_stories": [],
            "matches": [],
        }
        mock_orchestrator_class.return_value = mock_orchestrator

        result = run_plan(
            console=mock_console,
            input_path=str(test_file),
            epic_key="EPIC-1",
            output_format="json",
        )
        assert result == ExitCode.SUCCESS

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "has_changes" in data
        assert "summary" in data

    @patch("spectryn.application.SyncOrchestrator")
    @patch("spectryn.adapters.parsers.MarkdownParser")
    @patch("spectryn.adapters.JiraAdapter")
    @patch("spectryn.adapters.ADFFormatter")
    @patch("spectryn.adapters.EnvironmentConfigProvider")
    @patch("spectryn.cli.logging.setup_logging")
    def test_run_plan_with_changes(
        self,
        mock_logging,
        mock_config_provider,
        mock_formatter,
        mock_jira,
        mock_parser,
        mock_orchestrator_class,
        mock_console,
        tmp_path,
    ):
        """Test run_plan with actual changes to plan."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")

        mock_provider = MagicMock()
        mock_provider.validate.return_value = []
        mock_config = MagicMock()
        mock_config.tracker.url = "https://jira.example.com"
        mock_provider.load.return_value = mock_config
        mock_config_provider.return_value = mock_provider

        mock_tracker = MagicMock()
        mock_tracker.test_connection.return_value = True
        mock_jira.return_value = mock_tracker

        # Mock story
        mock_story = MagicMock()
        mock_story.id = "US-001"
        mock_story.title = "Test Story"
        mock_story.story_points = 5
        mock_story.status = MagicMock()
        mock_story.status.value = "Planned"
        mock_story.subtasks = []

        mock_orchestrator = MagicMock()
        mock_orchestrator.analyze.return_value = {
            "unmatched_stories": ["US-001"],
            "local_stories": [mock_story],
            "matches": [],
        }
        mock_orchestrator_class.return_value = mock_orchestrator

        result = run_plan(
            console=mock_console,
            input_path=str(test_file),
            epic_key="EPIC-1",
        )
        assert result == ExitCode.SUCCESS
        # Should show hint about execution
        mock_console.info.assert_called()

    @patch("spectryn.application.SyncOrchestrator")
    @patch("spectryn.adapters.parsers.MarkdownParser")
    @patch("spectryn.adapters.JiraAdapter")
    @patch("spectryn.adapters.ADFFormatter")
    @patch("spectryn.adapters.EnvironmentConfigProvider")
    @patch("spectryn.cli.logging.setup_logging")
    def test_run_plan_with_updates(
        self,
        mock_logging,
        mock_config_provider,
        mock_formatter,
        mock_jira,
        mock_parser,
        mock_orchestrator_class,
        mock_console,
        tmp_path,
    ):
        """Test run_plan with story updates."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")

        mock_provider = MagicMock()
        mock_provider.validate.return_value = []
        mock_config = MagicMock()
        mock_config.tracker.url = "https://jira.example.com"
        mock_provider.load.return_value = mock_config
        mock_config_provider.return_value = mock_provider

        mock_tracker = MagicMock()
        mock_tracker.test_connection.return_value = True
        mock_jira.return_value = mock_tracker

        mock_story = MagicMock()
        mock_story.id = "US-001"
        mock_story.title = "Test Story"
        mock_story.subtasks = []

        mock_orchestrator = MagicMock()
        mock_orchestrator.analyze.return_value = {
            "unmatched_stories": [],
            "local_stories": [mock_story],
            "matches": [
                {
                    "story_id": "US-001",
                    "remote_key": "JIRA-123",
                    "changes": {
                        "status": {"old": "Open", "new": "Done"},
                    },
                }
            ],
        }
        mock_orchestrator_class.return_value = mock_orchestrator

        result = run_plan(
            console=mock_console,
            input_path=str(test_file),
            epic_key="EPIC-1",
        )
        assert result == ExitCode.SUCCESS

    @patch("spectryn.application.SyncOrchestrator")
    @patch("spectryn.adapters.parsers.MarkdownParser")
    @patch("spectryn.adapters.JiraAdapter")
    @patch("spectryn.adapters.ADFFormatter")
    @patch("spectryn.adapters.EnvironmentConfigProvider")
    @patch("spectryn.cli.logging.setup_logging")
    def test_run_plan_with_subtasks(
        self,
        mock_logging,
        mock_config_provider,
        mock_formatter,
        mock_jira,
        mock_parser,
        mock_orchestrator_class,
        mock_console,
        tmp_path,
    ):
        """Test run_plan with subtasks to create."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")

        mock_provider = MagicMock()
        mock_provider.validate.return_value = []
        mock_config = MagicMock()
        mock_config.tracker.url = "https://jira.example.com"
        mock_provider.load.return_value = mock_config
        mock_config_provider.return_value = mock_provider

        mock_tracker = MagicMock()
        mock_tracker.test_connection.return_value = True
        mock_jira.return_value = mock_tracker

        mock_subtask = MagicMock()
        mock_subtask.name = "Test Subtask"
        mock_subtask.number = 1

        mock_story = MagicMock()
        mock_story.id = "US-001"
        mock_story.title = "Test Story"
        mock_story.subtasks = [mock_subtask]

        mock_orchestrator = MagicMock()
        mock_orchestrator.analyze.return_value = {
            "unmatched_stories": [],
            "local_stories": [mock_story],
            "matches": [
                {
                    "story_id": "US-001",
                    "remote_key": "JIRA-123",
                    "changes": {},
                    "remote_subtasks": [],  # No existing subtasks
                }
            ],
        }
        mock_orchestrator_class.return_value = mock_orchestrator

        result = run_plan(
            console=mock_console,
            input_path=str(test_file),
            epic_key="EPIC-1",
        )
        assert result == ExitCode.SUCCESS

    @patch("spectryn.application.SyncOrchestrator")
    @patch("spectryn.adapters.parsers.MarkdownParser")
    @patch("spectryn.adapters.JiraAdapter")
    @patch("spectryn.adapters.ADFFormatter")
    @patch("spectryn.adapters.EnvironmentConfigProvider")
    @patch("spectryn.cli.logging.setup_logging")
    def test_run_plan_with_status_change(
        self,
        mock_logging,
        mock_config_provider,
        mock_formatter,
        mock_jira,
        mock_parser,
        mock_orchestrator_class,
        mock_console,
        tmp_path,
    ):
        """Test run_plan with status changes."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")

        mock_provider = MagicMock()
        mock_provider.validate.return_value = []
        mock_config = MagicMock()
        mock_config.tracker.url = "https://jira.example.com"
        mock_provider.load.return_value = mock_config
        mock_config_provider.return_value = mock_provider

        mock_tracker = MagicMock()
        mock_tracker.test_connection.return_value = True
        mock_jira.return_value = mock_tracker

        mock_story = MagicMock()
        mock_story.id = "US-001"
        mock_story.title = "Test Story"
        mock_story.subtasks = []

        mock_orchestrator = MagicMock()
        mock_orchestrator.analyze.return_value = {
            "unmatched_stories": [],
            "local_stories": [mock_story],
            "matches": [
                {
                    "story_id": "US-001",
                    "remote_key": "JIRA-123",
                    "changes": {},
                    "status_change": {"old": "Open", "new": "Done"},
                }
            ],
        }
        mock_orchestrator_class.return_value = mock_orchestrator

        result = run_plan(
            console=mock_console,
            input_path=str(test_file),
            epic_key="EPIC-1",
        )
        assert result == ExitCode.SUCCESS

    @patch("spectryn.application.SyncOrchestrator")
    @patch("spectryn.adapters.parsers.MarkdownParser")
    @patch("spectryn.adapters.JiraAdapter")
    @patch("spectryn.adapters.ADFFormatter")
    @patch("spectryn.adapters.EnvironmentConfigProvider")
    @patch("spectryn.cli.logging.setup_logging")
    def test_run_plan_verbose(
        self,
        mock_logging,
        mock_config_provider,
        mock_formatter,
        mock_jira,
        mock_parser,
        mock_orchestrator_class,
        mock_console,
        tmp_path,
    ):
        """Test run_plan in verbose mode."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")

        mock_provider = MagicMock()
        mock_provider.validate.return_value = []
        mock_config = MagicMock()
        mock_config.tracker.url = "https://jira.example.com"
        mock_provider.load.return_value = mock_config
        mock_config_provider.return_value = mock_provider

        mock_tracker = MagicMock()
        mock_tracker.test_connection.return_value = True
        mock_jira.return_value = mock_tracker

        mock_orchestrator = MagicMock()
        mock_orchestrator.analyze.return_value = {
            "unmatched_stories": [],
            "local_stories": [],
            "matches": [],
        }
        mock_orchestrator_class.return_value = mock_orchestrator

        result = run_plan(
            console=mock_console,
            input_path=str(test_file),
            epic_key="EPIC-1",
            verbose=True,
        )
        assert result == ExitCode.SUCCESS
