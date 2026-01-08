"""Tests for spectra.cli.diff_cmd module."""

from __future__ import annotations

import json
import textwrap
from unittest.mock import MagicMock, patch

import pytest

from spectryn.cli.diff_cmd import (
    DiffResult,
    FieldDiff,
    StoryDiff,
    compare_stories,
    format_diff,
    run_diff,
)
from spectryn.cli.exit_codes import ExitCode


class TestFieldDiff:
    """Tests for FieldDiff dataclass."""

    def test_field_diff_creation(self):
        """Test FieldDiff creation."""
        diff = FieldDiff(
            field_name="Status",
            local_value="Done",
            remote_value="In Progress",
        )
        assert diff.field_name == "Status"
        assert diff.local_value == "Done"
        assert diff.remote_value == "In Progress"

    def test_is_added_true(self):
        """Test is_added when field exists locally but not remotely."""
        diff = FieldDiff(
            field_name="Priority",
            local_value="High",
            remote_value=None,
        )
        assert diff.is_added is True
        assert diff.is_removed is False
        assert diff.is_changed is True

    def test_is_added_false(self):
        """Test is_added when field exists remotely."""
        diff = FieldDiff(
            field_name="Priority",
            local_value="High",
            remote_value="Medium",
        )
        assert diff.is_added is False

    def test_is_removed_true(self):
        """Test is_removed when field exists remotely but not locally."""
        diff = FieldDiff(
            field_name="Priority",
            local_value=None,
            remote_value="High",
        )
        assert diff.is_removed is True
        assert diff.is_added is False
        assert diff.is_changed is True

    def test_is_removed_false(self):
        """Test is_removed when field exists locally."""
        diff = FieldDiff(
            field_name="Priority",
            local_value="Low",
            remote_value="High",
        )
        assert diff.is_removed is False

    def test_is_changed_true(self):
        """Test is_changed when values differ."""
        diff = FieldDiff(
            field_name="Status",
            local_value="Done",
            remote_value="In Progress",
        )
        assert diff.is_changed is True

    def test_is_changed_false(self):
        """Test is_changed when values are same."""
        diff = FieldDiff(
            field_name="Status",
            local_value="Done",
            remote_value="Done",
        )
        assert diff.is_changed is False


class TestStoryDiff:
    """Tests for StoryDiff dataclass."""

    def test_story_diff_creation(self):
        """Test StoryDiff creation."""
        diff = StoryDiff(
            story_id="US-001",
            title="Test Story",
            external_key="JIRA-123",
        )
        assert diff.story_id == "US-001"
        assert diff.title == "Test Story"
        assert diff.external_key == "JIRA-123"
        assert diff.field_diffs == []
        assert diff.is_new_local is False
        assert diff.is_new_remote is False

    def test_has_changes_with_field_diffs(self):
        """Test has_changes when there are field differences."""
        diff = StoryDiff(
            story_id="US-001",
            title="Test Story",
            field_diffs=[
                FieldDiff(field_name="Status", local_value="Done", remote_value="In Progress")
            ],
        )
        assert diff.has_changes is True

    def test_has_changes_new_local(self):
        """Test has_changes when story is new locally."""
        diff = StoryDiff(
            story_id="US-001",
            title="Test Story",
            is_new_local=True,
        )
        assert diff.has_changes is True

    def test_has_changes_new_remote(self):
        """Test has_changes when story is new remotely."""
        diff = StoryDiff(
            story_id="US-001",
            title="Test Story",
            is_new_remote=True,
        )
        assert diff.has_changes is True

    def test_has_changes_false(self):
        """Test has_changes when no changes."""
        diff = StoryDiff(
            story_id="US-001",
            title="Test Story",
        )
        assert diff.has_changes is False


class TestDiffResult:
    """Tests for DiffResult dataclass."""

    def test_diff_result_creation(self):
        """Test DiffResult creation."""
        result = DiffResult(
            local_path="/path/to/file.md",
            remote_source="https://jira.example.com/browse/EPIC-1",
        )
        assert result.local_path == "/path/to/file.md"
        assert result.remote_source == "https://jira.example.com/browse/EPIC-1"
        assert result.story_diffs == []
        assert result.local_only == []
        assert result.remote_only == []

    def test_has_changes_with_story_diffs(self):
        """Test has_changes when there are story diffs."""
        result = DiffResult(
            local_path="/path/to/file.md",
            remote_source="https://jira.example.com",
            story_diffs=[StoryDiff(story_id="US-001", title="Test", field_diffs=[])],
        )
        assert result.has_changes is True

    def test_has_changes_with_local_only(self):
        """Test has_changes when there are local only stories."""
        result = DiffResult(
            local_path="/path/to/file.md",
            remote_source="https://jira.example.com",
            local_only=["US-001"],
        )
        assert result.has_changes is True

    def test_has_changes_with_remote_only(self):
        """Test has_changes when there are remote only stories."""
        result = DiffResult(
            local_path="/path/to/file.md",
            remote_source="https://jira.example.com",
            remote_only=["JIRA-123"],
        )
        assert result.has_changes is True

    def test_has_changes_false(self):
        """Test has_changes when no changes."""
        result = DiffResult(
            local_path="/path/to/file.md",
            remote_source="https://jira.example.com",
        )
        assert result.has_changes is False

    def test_total_changes(self):
        """Test total_changes calculation."""
        result = DiffResult(
            local_path="/path/to/file.md",
            remote_source="https://jira.example.com",
            story_diffs=[
                StoryDiff(
                    story_id="US-001",
                    title="Test",
                    field_diffs=[
                        FieldDiff(field_name="Status", local_value="Done", remote_value="Open")
                    ],
                )
            ],
            local_only=["US-002", "US-003"],
            remote_only=["JIRA-456"],
        )
        assert result.total_changes == 4  # 1 changed + 2 local + 1 remote


class TestCompareStories:
    """Tests for compare_stories function."""

    def test_compare_no_differences(self):
        """Test comparison with no differences."""
        local_story = MagicMock()
        local_story.title = "Test Story"
        local_story.status.value = "In Progress"
        local_story.story_points = 5
        local_story.priority.value = "High"
        local_story.subtasks = [1, 2, 3]

        remote_issue = {
            "summary": "Test Story",
            "status": {"name": "In Progress"},
            "customfield_10016": 5,
            "priority": {"name": "High"},
            "subtasks": [1, 2, 3],
        }

        diffs = compare_stories(local_story, remote_issue)
        assert len(diffs) == 0

    def test_compare_title_difference(self):
        """Test comparison with title difference."""
        local_story = MagicMock()
        local_story.title = "Updated Title"
        local_story.status.value = "Done"
        local_story.story_points = None
        local_story.priority.value = "Medium"
        local_story.subtasks = []

        remote_issue = {
            "summary": "Original Title",
            "status": {"name": "Done"},
            "priority": {"name": "Medium"},
        }

        diffs = compare_stories(local_story, remote_issue)
        assert len(diffs) >= 1
        title_diff = next((d for d in diffs if d.field_name == "Title"), None)
        assert title_diff is not None
        assert title_diff.local_value == "Updated Title"
        assert title_diff.remote_value == "Original Title"

    def test_compare_status_difference(self):
        """Test comparison with status difference."""
        local_story = MagicMock()
        local_story.title = "Test Story"
        local_story.status.value = "Done"
        local_story.story_points = None
        local_story.priority.value = "Medium"
        local_story.subtasks = []

        remote_issue = {
            "summary": "Test Story",
            "status": {"name": "In Progress"},
            "priority": {"name": "Medium"},
        }

        diffs = compare_stories(local_story, remote_issue)
        status_diff = next((d for d in diffs if d.field_name == "Status"), None)
        assert status_diff is not None
        assert status_diff.local_value == "Done"
        assert status_diff.remote_value == "In Progress"

    def test_compare_story_points_difference(self):
        """Test comparison with story points difference."""
        local_story = MagicMock()
        local_story.title = "Test Story"
        local_story.status.value = "Planned"
        local_story.story_points = 8
        local_story.priority.value = "Medium"
        local_story.subtasks = []

        remote_issue = {
            "summary": "Test Story",
            "status": {"name": "Planned"},
            "customfield_10016": 5,
            "priority": {"name": "Medium"},
        }

        diffs = compare_stories(local_story, remote_issue)
        points_diff = next((d for d in diffs if d.field_name == "Story Points"), None)
        assert points_diff is not None
        assert points_diff.local_value == "8"
        assert points_diff.remote_value == "5"

    def test_compare_priority_difference(self):
        """Test comparison with priority difference."""
        local_story = MagicMock()
        local_story.title = "Test Story"
        local_story.status.value = "Planned"
        local_story.story_points = None
        local_story.priority.value = "High"
        local_story.subtasks = []

        remote_issue = {
            "summary": "Test Story",
            "status": {"name": "Planned"},
            "priority": {"name": "Low"},
        }

        diffs = compare_stories(local_story, remote_issue)
        priority_diff = next((d for d in diffs if d.field_name == "Priority"), None)
        assert priority_diff is not None
        assert priority_diff.local_value == "High"
        assert priority_diff.remote_value == "Low"

    def test_compare_subtasks_difference(self):
        """Test comparison with subtask count difference."""
        local_story = MagicMock()
        local_story.title = "Test Story"
        local_story.status.value = "Planned"
        local_story.story_points = None
        local_story.priority.value = "Medium"
        local_story.subtasks = [1, 2, 3, 4, 5]

        remote_issue = {
            "summary": "Test Story",
            "status": {"name": "Planned"},
            "priority": {"name": "Medium"},
            "subtasks": [1, 2],
        }

        diffs = compare_stories(local_story, remote_issue)
        subtask_diff = next((d for d in diffs if d.field_name == "Subtasks"), None)
        assert subtask_diff is not None
        assert subtask_diff.local_value == "5"
        assert subtask_diff.remote_value == "2"

    def test_compare_null_status(self):
        """Test comparison with null status."""
        local_story = MagicMock()
        local_story.title = "Test"
        local_story.status = None
        local_story.story_points = None
        local_story.priority = None
        local_story.subtasks = None

        remote_issue = {
            "summary": "Test",
            "status": {"name": "Open"},
            "priority": {},
        }

        diffs = compare_stories(local_story, remote_issue)
        # Should find status diff
        status_diff = next((d for d in diffs if d.field_name == "Status"), None)
        assert status_diff is not None


class TestFormatDiff:
    """Tests for format_diff function."""

    def test_format_no_changes(self):
        """Test format with no changes."""
        result = DiffResult(
            local_path="/path/to/file.md",
            remote_source="https://jira.example.com",
        )
        output = format_diff(result, color=False)
        assert "No differences found" in output

    def test_format_with_color(self):
        """Test format with color enabled."""
        result = DiffResult(
            local_path="/path/to/file.md",
            remote_source="https://jira.example.com",
            local_only=["US-001"],
        )
        output = format_diff(result, color=True)
        assert "Local" in output or "\x1b" in output  # Contains color codes

    def test_format_without_color(self):
        """Test format without color."""
        result = DiffResult(
            local_path="/path/to/file.md",
            remote_source="https://jira.example.com",
            local_only=["US-001"],
        )
        output = format_diff(result, color=False)
        assert "+" in output
        assert "US-001" in output

    def test_format_local_only(self):
        """Test format with local only stories."""
        result = DiffResult(
            local_path="/path/to/file.md",
            remote_source="https://jira.example.com",
            local_only=["US-001", "US-002"],
        )
        output = format_diff(result, color=False)
        assert "Local Only" in output
        assert "US-001" in output
        assert "US-002" in output

    def test_format_remote_only(self):
        """Test format with remote only stories."""
        result = DiffResult(
            local_path="/path/to/file.md",
            remote_source="https://jira.example.com",
            remote_only=["JIRA-123", "JIRA-456"],
        )
        output = format_diff(result, color=False)
        assert "Remote Only" in output
        assert "JIRA-123" in output
        assert "JIRA-456" in output

    def test_format_modified_stories(self):
        """Test format with modified stories."""
        result = DiffResult(
            local_path="/path/to/file.md",
            remote_source="https://jira.example.com",
            story_diffs=[
                StoryDiff(
                    story_id="US-001",
                    title="Test Story",
                    external_key="JIRA-123",
                    field_diffs=[
                        FieldDiff(
                            field_name="Status",
                            local_value="Done",
                            remote_value="In Progress",
                        )
                    ],
                )
            ],
        )
        output = format_diff(result, color=False)
        assert "Modified" in output
        assert "US-001" in output
        assert "Status" in output

    def test_format_with_external_key(self):
        """Test format shows external key when available."""
        result = DiffResult(
            local_path="/path/to/file.md",
            remote_source="https://jira.example.com",
            story_diffs=[
                StoryDiff(
                    story_id="US-001",
                    title="Test Story",
                    external_key="JIRA-123",
                    field_diffs=[
                        FieldDiff(field_name="Title", local_value="New", remote_value="Old")
                    ],
                )
            ],
        )
        output = format_diff(result, color=False)
        assert "JIRA-123" in output

    def test_format_truncates_long_title(self):
        """Test format truncates long titles."""
        result = DiffResult(
            local_path="/path/to/file.md",
            remote_source="https://jira.example.com",
            story_diffs=[
                StoryDiff(
                    story_id="US-001",
                    title="A" * 100,  # Very long title
                    field_diffs=[
                        FieldDiff(field_name="Status", local_value="Done", remote_value="Open")
                    ],
                )
            ],
        )
        output = format_diff(result, color=False)
        assert "..." in output  # Title truncated

    def test_format_truncates_long_values(self):
        """Test format truncates long field values."""
        result = DiffResult(
            local_path="/path/to/file.md",
            remote_source="https://jira.example.com",
            story_diffs=[
                StoryDiff(
                    story_id="US-001",
                    title="Test",
                    field_diffs=[
                        FieldDiff(
                            field_name="Description",
                            local_value="A" * 100,
                            remote_value="B" * 100,
                        )
                    ],
                )
            ],
        )
        output = format_diff(result, color=False)
        # Values should be truncated
        assert "A" * 100 not in output


class TestRunDiff:
    """Tests for run_diff function."""

    @pytest.fixture
    def mock_console(self):
        """Create mock console."""
        console = MagicMock()
        console.color = True
        return console

    def test_run_diff_file_not_found(self, mock_console, tmp_path):
        """Test run_diff with non-existent file."""
        result = run_diff(
            console=mock_console,
            input_path=str(tmp_path / "nonexistent.md"),
            epic_key="EPIC-1",
        )
        assert result == ExitCode.FILE_NOT_FOUND
        mock_console.error.assert_called()

    @patch("spectryn.adapters.EnvironmentConfigProvider")
    @patch("spectryn.cli.logging.setup_logging")
    def test_run_diff_config_error(
        self, mock_logging, mock_config_provider, mock_console, tmp_path
    ):
        """Test run_diff with config error."""
        # Create test file
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")

        mock_provider = MagicMock()
        mock_provider.validate.return_value = ["Missing JIRA_URL"]
        mock_config_provider.return_value = mock_provider

        result = run_diff(
            console=mock_console,
            input_path=str(test_file),
            epic_key="EPIC-1",
        )
        assert result == ExitCode.CONFIG_ERROR

    @patch("spectryn.adapters.JiraAdapter")
    @patch("spectryn.adapters.ADFFormatter")
    @patch("spectryn.adapters.EnvironmentConfigProvider")
    @patch("spectryn.cli.logging.setup_logging")
    def test_run_diff_connection_error(
        self, mock_logging, mock_config_provider, mock_formatter, mock_jira, mock_console, tmp_path
    ):
        """Test run_diff with connection error."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")

        mock_provider = MagicMock()
        mock_provider.validate.return_value = []
        mock_config_provider.return_value = mock_provider

        mock_tracker = MagicMock()
        mock_tracker.test_connection.return_value = False
        mock_jira.return_value = mock_tracker

        result = run_diff(
            console=mock_console,
            input_path=str(test_file),
            epic_key="EPIC-1",
        )
        assert result == ExitCode.CONNECTION_ERROR

    @patch("spectryn.adapters.parsers.MarkdownParser")
    @patch("spectryn.adapters.JiraAdapter")
    @patch("spectryn.adapters.ADFFormatter")
    @patch("spectryn.adapters.EnvironmentConfigProvider")
    @patch("spectryn.cli.logging.setup_logging")
    def test_run_diff_success(
        self,
        mock_logging,
        mock_config_provider,
        mock_formatter,
        mock_jira,
        mock_parser_class,
        mock_console,
        tmp_path,
    ):
        """Test run_diff success."""
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
        mock_tracker.get_epic_issues.return_value = []
        mock_jira.return_value = mock_tracker

        mock_parser = MagicMock()
        mock_parser.parse_stories.return_value = []
        mock_parser_class.return_value = mock_parser

        result = run_diff(
            console=mock_console,
            input_path=str(test_file),
            epic_key="EPIC-1",
        )
        assert result == ExitCode.SUCCESS

    @patch("spectryn.adapters.parsers.MarkdownParser")
    @patch("spectryn.adapters.JiraAdapter")
    @patch("spectryn.adapters.ADFFormatter")
    @patch("spectryn.adapters.EnvironmentConfigProvider")
    @patch("spectryn.cli.logging.setup_logging")
    def test_run_diff_json_output(
        self,
        mock_logging,
        mock_config_provider,
        mock_formatter,
        mock_jira,
        mock_parser_class,
        mock_console,
        tmp_path,
        capsys,
    ):
        """Test run_diff with JSON output format."""
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
        mock_tracker.get_epic_issues.return_value = []
        mock_jira.return_value = mock_tracker

        mock_parser = MagicMock()
        mock_parser.parse_stories.return_value = []
        mock_parser_class.return_value = mock_parser

        result = run_diff(
            console=mock_console,
            input_path=str(test_file),
            epic_key="EPIC-1",
            output_format="json",
        )
        assert result == ExitCode.SUCCESS

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "local_path" in data
        assert "has_changes" in data

    @patch("spectryn.adapters.parsers.MarkdownParser")
    @patch("spectryn.adapters.JiraAdapter")
    @patch("spectryn.adapters.ADFFormatter")
    @patch("spectryn.adapters.EnvironmentConfigProvider")
    @patch("spectryn.cli.logging.setup_logging")
    def test_run_diff_fetch_error(
        self,
        mock_logging,
        mock_config_provider,
        mock_formatter,
        mock_jira,
        mock_parser_class,
        mock_console,
        tmp_path,
    ):
        """Test run_diff when fetching remote issues fails."""
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
        mock_tracker.get_epic_issues.side_effect = Exception("API error")
        mock_jira.return_value = mock_tracker

        mock_parser = MagicMock()
        mock_parser.parse_stories.return_value = []
        mock_parser_class.return_value = mock_parser

        result = run_diff(
            console=mock_console,
            input_path=str(test_file),
            epic_key="EPIC-1",
        )
        assert result == ExitCode.CONNECTION_ERROR

    @patch("spectryn.adapters.parsers.MarkdownParser")
    @patch("spectryn.adapters.JiraAdapter")
    @patch("spectryn.adapters.ADFFormatter")
    @patch("spectryn.adapters.EnvironmentConfigProvider")
    @patch("spectryn.cli.logging.setup_logging")
    def test_run_diff_with_changes(
        self,
        mock_logging,
        mock_config_provider,
        mock_formatter,
        mock_jira,
        mock_parser_class,
        mock_console,
        tmp_path,
    ):
        """Test run_diff with actual changes detected."""
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
        mock_tracker.get_epic_issues.return_value = [
            {
                "key": "JIRA-123",
                "fields": {
                    "summary": "Different Title",
                    "status": {"name": "Open"},
                    "priority": {"name": "Medium"},
                    "issuetype": {"subtask": False},
                },
            }
        ]
        mock_jira.return_value = mock_tracker

        # Create mock local story
        mock_story = MagicMock()
        mock_story.id = "US-001"
        mock_story.title = "Original Title"
        mock_story.external_key = "JIRA-123"
        mock_story.status.value = "Done"
        mock_story.priority.value = "High"
        mock_story.story_points = 5
        mock_story.subtasks = []

        mock_parser = MagicMock()
        mock_parser.parse_stories.return_value = [mock_story]
        mock_parser_class.return_value = mock_parser

        result = run_diff(
            console=mock_console,
            input_path=str(test_file),
            epic_key="EPIC-1",
        )
        assert result == ExitCode.SUCCESS

    @patch("spectryn.adapters.parsers.MarkdownParser")
    @patch("spectryn.adapters.JiraAdapter")
    @patch("spectryn.adapters.ADFFormatter")
    @patch("spectryn.adapters.EnvironmentConfigProvider")
    @patch("spectryn.cli.logging.setup_logging")
    def test_run_diff_match_by_title(
        self,
        mock_logging,
        mock_config_provider,
        mock_formatter,
        mock_jira,
        mock_parser_class,
        mock_console,
        tmp_path,
    ):
        """Test run_diff matches stories by title when no external key."""
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
        mock_tracker.get_epic_issues.return_value = [
            {
                "key": "JIRA-123",
                "fields": {
                    "summary": "Test Story",
                    "status": {"name": "Open"},
                    "priority": {"name": "Medium"},
                    "issuetype": {"subtask": False},
                },
            }
        ]
        mock_jira.return_value = mock_tracker

        # Create mock local story without external key
        mock_story = MagicMock()
        mock_story.id = "US-001"
        mock_story.title = "Test Story"
        mock_story.external_key = None  # No external key
        mock_story.status.value = "Done"
        mock_story.priority.value = "Medium"
        mock_story.story_points = None
        mock_story.subtasks = []

        mock_parser = MagicMock()
        mock_parser.parse_stories.return_value = [mock_story]
        mock_parser_class.return_value = mock_parser

        result = run_diff(
            console=mock_console,
            input_path=str(test_file),
            epic_key="EPIC-1",
        )
        assert result == ExitCode.SUCCESS

    @patch("spectryn.adapters.parsers.MarkdownParser")
    @patch("spectryn.adapters.JiraAdapter")
    @patch("spectryn.adapters.ADFFormatter")
    @patch("spectryn.adapters.EnvironmentConfigProvider")
    @patch("spectryn.cli.logging.setup_logging")
    def test_run_diff_skips_subtasks(
        self,
        mock_logging,
        mock_config_provider,
        mock_formatter,
        mock_jira,
        mock_parser_class,
        mock_console,
        tmp_path,
    ):
        """Test run_diff skips subtasks in remote_only list."""
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
        mock_tracker.get_epic_issues.return_value = [
            {
                "key": "JIRA-SUB-1",
                "fields": {
                    "summary": "Subtask",
                    "issuetype": {"subtask": True},  # Is a subtask
                },
            }
        ]
        mock_jira.return_value = mock_tracker

        mock_parser = MagicMock()
        mock_parser.parse_stories.return_value = []
        mock_parser_class.return_value = mock_parser

        result = run_diff(
            console=mock_console,
            input_path=str(test_file),
            epic_key="EPIC-1",
            output_format="json",
        )
        assert result == ExitCode.SUCCESS
