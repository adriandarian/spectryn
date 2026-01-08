"""Tests for CLI import command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from spectryn.cli.exit_codes import ExitCode
from spectryn.cli.import_cmd import (
    ImportOptions,
    ImportResult,
    _extract_text_from_adf,
    generate_markdown_content,
    run_import,
)


# =============================================================================
# ImportOptions Tests
# =============================================================================


class TestImportOptions:
    """Tests for ImportOptions dataclass."""

    def test_default_values(self):
        """Test default values."""
        options = ImportOptions()

        assert options.include_subtasks is True
        assert options.include_comments is False
        assert options.include_attachments is False
        assert options.include_links is True
        assert options.template is None
        assert options.output_dir == "."
        assert options.single_file is True

    def test_custom_values(self):
        """Test custom values."""
        options = ImportOptions(
            include_subtasks=False,
            include_comments=True,
            include_attachments=True,
            include_links=False,
            template="custom.md",
            output_dir="/path/to/output",
            single_file=False,
        )

        assert options.include_subtasks is False
        assert options.include_comments is True
        assert options.include_attachments is True
        assert options.include_links is False
        assert options.template == "custom.md"
        assert options.output_dir == "/path/to/output"
        assert options.single_file is False


# =============================================================================
# ImportResult Tests
# =============================================================================


class TestImportResult:
    """Tests for ImportResult dataclass."""

    def test_default_values(self):
        """Test default values."""
        result = ImportResult()

        assert result.success is True
        assert result.epics_imported == 0
        assert result.stories_imported == 0
        assert result.subtasks_imported == 0
        assert result.files_created == []
        assert result.errors == []
        assert result.warnings == []

    def test_custom_values(self):
        """Test custom values."""
        result = ImportResult(
            success=False,
            epics_imported=5,
            stories_imported=20,
            subtasks_imported=50,
            files_created=["file1.md", "file2.md"],
            errors=["error1", "error2"],
            warnings=["warn1"],
        )

        assert result.success is False
        assert result.epics_imported == 5
        assert result.stories_imported == 20
        assert result.subtasks_imported == 50
        assert result.files_created == ["file1.md", "file2.md"]
        assert result.errors == ["error1", "error2"]
        assert result.warnings == ["warn1"]


# =============================================================================
# _extract_text_from_adf Tests
# =============================================================================


class TestExtractTextFromAdf:
    """Tests for _extract_text_from_adf function."""

    def test_extract_simple_text(self):
        """Test extracting simple text."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Hello"},
                        {"type": "text", "text": " "},
                        {"type": "text", "text": "World"},
                    ],
                }
            ],
        }

        result = _extract_text_from_adf(adf)
        assert "Hello" in result
        assert "World" in result

    def test_extract_from_non_dict(self):
        """Test with non-dict input."""
        result = _extract_text_from_adf("plain string")
        assert result == "plain string"

    def test_extract_from_empty_adf(self):
        """Test with empty ADF."""
        result = _extract_text_from_adf({})
        assert result == ""

    def test_extract_nested_content(self):
        """Test with nested content."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "panel",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": "Nested text"},
                            ],
                        }
                    ],
                }
            ],
        }

        result = _extract_text_from_adf(adf)
        assert "Nested text" in result


# =============================================================================
# generate_markdown_content Tests
# =============================================================================


class TestGenerateMarkdownContent:
    """Tests for generate_markdown_content function."""

    @pytest.fixture
    def sample_epic(self):
        """Create sample epic data."""
        return {
            "key": "EPIC-123",
            "summary": "Test Epic",
            "status": {"name": "In Progress"},
            "priority": {"name": "High"},
            "assignee": {"displayName": "John Doe"},
            "description": "Epic description text",
        }

    @pytest.fixture
    def sample_stories(self):
        """Create sample stories data."""
        return [
            {
                "key": "STORY-1",
                "summary": "First Story",
                "description": "Story description",
                "status": {"name": "To Do"},
                "priority": {"name": "Medium"},
                "assignee": {"displayName": "Jane Doe"},
                "storyPoints": 5,
                "subtasks": [],
                "issuelinks": [],
            },
            {
                "key": "STORY-2",
                "summary": "Second Story",
                "description": "Another description",
                "status": {"name": "Done"},
                "priority": {"name": "Low"},
                "storyPoints": 3,
                "subtasks": [
                    {"summary": "Subtask 1", "status": {"name": "Done"}},
                    {"summary": "Subtask 2", "status": {"name": "To Do"}},
                ],
                "issuelinks": [],
            },
        ]

    def test_generate_basic_content(self, sample_epic, sample_stories):
        """Test basic content generation."""
        options = ImportOptions()
        content = generate_markdown_content(sample_epic, sample_stories, options)

        assert "EPIC-123" in content
        assert "Test Epic" in content
        assert "STORY-1" in content
        assert "First Story" in content
        assert "STORY-2" in content
        assert "Second Story" in content

    def test_generate_with_subtasks(self, sample_epic, sample_stories):
        """Test content generation with subtasks."""
        options = ImportOptions(include_subtasks=True)
        content = generate_markdown_content(sample_epic, sample_stories, options)

        assert "Subtask 1" in content
        assert "Subtask 2" in content
        assert "[x]" in content  # Done subtask
        assert "[ ]" in content  # To Do subtask

    def test_generate_without_subtasks(self, sample_epic, sample_stories):
        """Test content generation without subtasks."""
        options = ImportOptions(include_subtasks=False)
        content = generate_markdown_content(sample_epic, sample_stories, options)

        # Should not have subtasks section
        assert "#### Subtasks" not in content

    def test_generate_with_story_points(self, sample_epic, sample_stories):
        """Test story points are included."""
        options = ImportOptions()
        content = generate_markdown_content(sample_epic, sample_stories, options)

        assert "**Total Points:** 8" in content

    def test_generate_with_adf_description(self, sample_epic, sample_stories):
        """Test ADF description is extracted."""
        sample_epic["description"] = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "ADF description content"}],
                }
            ],
        }

        options = ImportOptions()
        content = generate_markdown_content(sample_epic, sample_stories, options)

        assert "ADF description content" in content

    def test_generate_with_links(self, sample_epic, sample_stories):
        """Test content with issue links."""
        sample_stories[0]["issuelinks"] = [
            {
                "type": {"name": "blocks"},
                "outwardIssue": {"key": "BLOCKED-1"},
            }
        ]

        options = ImportOptions(include_links=True)
        content = generate_markdown_content(sample_epic, sample_stories, options)

        assert "BLOCKED-1" in content
        assert "Related Issues" in content

    def test_generate_with_acceptance_criteria(self, sample_epic, sample_stories):
        """Test acceptance criteria handling."""
        sample_stories[0]["customfield_10017"] = ["AC 1", "AC 2", "AC 3"]

        options = ImportOptions()
        content = generate_markdown_content(sample_epic, sample_stories, options)

        assert "Acceptance Criteria" in content
        assert "AC 1" in content
        assert "AC 2" in content

    def test_generate_with_string_acceptance_criteria(self, sample_epic, sample_stories):
        """Test string acceptance criteria."""
        sample_stories[0]["customfield_10017"] = "AC 1\nAC 2\nAC 3"

        options = ImportOptions()
        content = generate_markdown_content(sample_epic, sample_stories, options)

        assert "Acceptance Criteria" in content


# =============================================================================
# run_import Tests
# =============================================================================


class TestRunImport:
    """Tests for run_import function."""

    @pytest.fixture
    def mock_console(self):
        """Create mock console."""
        return MagicMock()

    def test_import_requires_epic_or_project(self, mock_console):
        """Test that either epic or project must be specified."""
        with patch("spectryn.cli.logging.setup_logging"):
            result = run_import(mock_console)

        assert result == ExitCode.CONFIG_ERROR
        mock_console.error.assert_called()

    def test_import_config_error(self, mock_console):
        """Test import with config validation error."""
        mock_provider = MagicMock()
        mock_provider.validate.return_value = ["Missing JIRA_URL"]

        with patch("spectryn.adapters.EnvironmentConfigProvider", return_value=mock_provider):
            with patch("spectryn.adapters.JiraAdapter"):
                with patch("spectryn.adapters.ADFFormatter"):
                    with patch("spectryn.cli.logging.setup_logging"):
                        result = run_import(mock_console, epic_key="EPIC-123")

        assert result == ExitCode.CONFIG_ERROR

    def test_import_connection_error(self, mock_console):
        """Test import with connection error."""
        mock_provider = MagicMock()
        mock_provider.validate.return_value = []
        mock_provider.load.return_value = MagicMock()

        mock_adapter = MagicMock()
        mock_adapter.test_connection.return_value = False

        with patch("spectryn.adapters.EnvironmentConfigProvider", return_value=mock_provider):
            with patch("spectryn.adapters.JiraAdapter", return_value=mock_adapter):
                with patch("spectryn.adapters.ADFFormatter"):
                    with patch("spectryn.cli.logging.setup_logging"):
                        result = run_import(mock_console, epic_key="EPIC-123")

        assert result == ExitCode.CONNECTION_ERROR

    def test_import_epic_not_found(self, mock_console):
        """Test import with epic not found."""
        mock_provider = MagicMock()
        mock_provider.validate.return_value = []
        mock_provider.load.return_value = MagicMock()

        mock_adapter = MagicMock()
        mock_adapter.test_connection.return_value = True
        mock_adapter.get_current_user.return_value = {"displayName": "Test"}
        mock_adapter.get_issue.return_value = None

        with patch("spectryn.adapters.EnvironmentConfigProvider", return_value=mock_provider):
            with patch("spectryn.adapters.JiraAdapter", return_value=mock_adapter):
                with patch("spectryn.adapters.ADFFormatter"):
                    with patch("spectryn.cli.logging.setup_logging"):
                        result = run_import(mock_console, epic_key="EPIC-123")

        assert result == ExitCode.FILE_NOT_FOUND

    def test_import_epic_success(self, mock_console, tmp_path):
        """Test successful epic import."""
        mock_provider = MagicMock()
        mock_provider.validate.return_value = []
        mock_provider.load.return_value = MagicMock()

        mock_adapter = MagicMock()
        mock_adapter.test_connection.return_value = True
        mock_adapter.get_current_user.return_value = {"displayName": "Test"}
        mock_adapter.get_issue.return_value = {
            "key": "EPIC-123",
            "fields": {
                "summary": "Test Epic",
                "description": "Epic description",
                "status": {"name": "In Progress"},
                "priority": {"name": "High"},
            },
        }
        mock_adapter.get_epic_issues.return_value = [
            {
                "key": "STORY-1",
                "fields": {
                    "summary": "Test Story",
                    "description": "Story description",
                    "status": {"name": "To Do"},
                    "priority": {"name": "Medium"},
                    "issuetype": {"subtask": False},
                },
            }
        ]

        output_path = tmp_path / "output.md"

        with patch("spectryn.adapters.EnvironmentConfigProvider", return_value=mock_provider):
            with patch("spectryn.adapters.JiraAdapter", return_value=mock_adapter):
                with patch("spectryn.adapters.ADFFormatter"):
                    with patch("spectryn.cli.logging.setup_logging"):
                        result = run_import(
                            mock_console, epic_key="EPIC-123", output_path=str(output_path)
                        )

        assert result == ExitCode.SUCCESS
        assert output_path.exists()
        content = output_path.read_text()
        assert "EPIC-123" in content
        assert "Test Epic" in content

    def test_import_epic_dry_run(self, mock_console):
        """Test dry run import."""
        mock_provider = MagicMock()
        mock_provider.validate.return_value = []
        mock_provider.load.return_value = MagicMock()

        mock_adapter = MagicMock()
        mock_adapter.test_connection.return_value = True
        mock_adapter.get_current_user.return_value = {"displayName": "Test"}
        mock_adapter.get_issue.return_value = {
            "key": "EPIC-123",
            "fields": {
                "summary": "Test Epic",
                "status": {"name": "In Progress"},
            },
        }
        mock_adapter.get_epic_issues.return_value = []

        with patch("spectryn.adapters.EnvironmentConfigProvider", return_value=mock_provider):
            with patch("spectryn.adapters.JiraAdapter", return_value=mock_adapter):
                with patch("spectryn.adapters.ADFFormatter"):
                    with patch("spectryn.cli.logging.setup_logging"):
                        result = run_import(mock_console, epic_key="EPIC-123", dry_run=True)

        assert result == ExitCode.SUCCESS
        # File should not be created in dry run
        mock_console.info.assert_called()

    def test_import_project_not_implemented(self, mock_console):
        """Test project import shows not implemented."""
        mock_provider = MagicMock()
        mock_provider.validate.return_value = []
        mock_provider.load.return_value = MagicMock()

        mock_adapter = MagicMock()
        mock_adapter.test_connection.return_value = True
        mock_adapter.get_current_user.return_value = {"displayName": "Test"}

        with patch("spectryn.adapters.EnvironmentConfigProvider", return_value=mock_provider):
            with patch("spectryn.adapters.JiraAdapter", return_value=mock_adapter):
                with patch("spectryn.adapters.ADFFormatter"):
                    with patch("spectryn.cli.logging.setup_logging"):
                        result = run_import(mock_console, project_key="PROJ")

        assert result == ExitCode.CONFIG_ERROR
        mock_console.warning.assert_called()

    def test_import_exception_handling(self, mock_console):
        """Test exception handling during import."""
        mock_provider = MagicMock()
        mock_provider.validate.return_value = []
        mock_provider.load.return_value = MagicMock()

        mock_adapter = MagicMock()
        mock_adapter.test_connection.return_value = True
        mock_adapter.get_current_user.return_value = {"displayName": "Test"}
        mock_adapter.get_issue.side_effect = Exception("API Error")

        with patch("spectryn.adapters.EnvironmentConfigProvider", return_value=mock_provider):
            with patch("spectryn.adapters.JiraAdapter", return_value=mock_adapter):
                with patch("spectryn.adapters.ADFFormatter"):
                    with patch("spectryn.cli.logging.setup_logging"):
                        result = run_import(mock_console, epic_key="EPIC-123")

        assert result == ExitCode.ERROR

    def test_import_with_subtasks(self, mock_console, tmp_path):
        """Test import includes subtasks."""
        mock_provider = MagicMock()
        mock_provider.validate.return_value = []
        mock_provider.load.return_value = MagicMock()

        mock_adapter = MagicMock()
        mock_adapter.test_connection.return_value = True
        mock_adapter.get_current_user.return_value = {"displayName": "Test"}
        mock_adapter.get_issue.return_value = {
            "key": "EPIC-123",
            "fields": {
                "summary": "Test Epic",
                "status": {"name": "In Progress"},
            },
        }
        mock_adapter.get_epic_issues.return_value = [
            {
                "key": "STORY-1",
                "fields": {
                    "summary": "Test Story",
                    "status": {"name": "To Do"},
                    "priority": {"name": "Medium"},
                    "issuetype": {"subtask": False},
                    "subtasks": [
                        {"summary": "Subtask 1", "status": {"name": "Done"}},
                    ],
                },
            }
        ]

        output_path = tmp_path / "output.md"

        with patch("spectryn.adapters.EnvironmentConfigProvider", return_value=mock_provider):
            with patch("spectryn.adapters.JiraAdapter", return_value=mock_adapter):
                with patch("spectryn.adapters.ADFFormatter"):
                    with patch("spectryn.cli.logging.setup_logging"):
                        result = run_import(
                            mock_console,
                            epic_key="EPIC-123",
                            output_path=str(output_path),
                            include_subtasks=True,
                        )

        assert result == ExitCode.SUCCESS
        content = output_path.read_text()
        assert "Subtask 1" in content

    def test_import_skips_subtask_issues(self, mock_console, tmp_path):
        """Test that subtask issues are skipped in main list."""
        mock_provider = MagicMock()
        mock_provider.validate.return_value = []
        mock_provider.load.return_value = MagicMock()

        mock_adapter = MagicMock()
        mock_adapter.test_connection.return_value = True
        mock_adapter.get_current_user.return_value = {"displayName": "Test"}
        mock_adapter.get_issue.return_value = {
            "key": "EPIC-123",
            "fields": {
                "summary": "Test Epic",
                "status": {"name": "In Progress"},
            },
        }
        mock_adapter.get_epic_issues.return_value = [
            {
                "key": "STORY-1",
                "fields": {
                    "summary": "Test Story",
                    "status": {"name": "To Do"},
                    "priority": {"name": "Medium"},
                    "issuetype": {"subtask": False},
                },
            },
            {
                "key": "SUB-1",
                "fields": {
                    "summary": "Should be skipped",
                    "status": {"name": "To Do"},
                    "priority": {"name": "Medium"},
                    "issuetype": {"subtask": True},
                },
            },
        ]

        output_path = tmp_path / "output.md"

        with patch("spectryn.adapters.EnvironmentConfigProvider", return_value=mock_provider):
            with patch("spectryn.adapters.JiraAdapter", return_value=mock_adapter):
                with patch("spectryn.adapters.ADFFormatter"):
                    with patch("spectryn.cli.logging.setup_logging"):
                        result = run_import(
                            mock_console, epic_key="EPIC-123", output_path=str(output_path)
                        )

        assert result == ExitCode.SUCCESS
        content = output_path.read_text()
        assert "Test Story" in content
        assert "Should be skipped" not in content
