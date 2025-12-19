"""
Tests for the generate command.

Tests template generation from Jira epics.
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from spectra.cli.exit_codes import ExitCode
from spectra.cli.generate import (
    GenerateResult,
    TemplateGenerator,
    run_generate,
)
from spectra.cli.output import Console


# =============================================================================
# GenerateResult Tests
# =============================================================================


class TestGenerateResult:
    """Tests for GenerateResult dataclass."""

    def test_default_values(self):
        """Test GenerateResult has sensible defaults."""
        result = GenerateResult()

        assert result.success is True
        assert result.output_path == ""
        assert result.epic_key == ""
        assert result.epic_title == ""
        assert result.stories_count == 0
        assert result.subtasks_count == 0
        assert result.warnings == []
        assert result.errors == []

    def test_add_warning(self):
        """Test adding a warning."""
        result = GenerateResult()
        result.add_warning("Test warning")

        assert len(result.warnings) == 1
        assert "Test warning" in result.warnings
        assert result.success is True  # Warnings don't affect success

    def test_add_error(self):
        """Test adding an error sets success to False."""
        result = GenerateResult()
        result.add_error("Test error")

        assert len(result.errors) == 1
        assert "Test error" in result.errors
        assert result.success is False


# =============================================================================
# TemplateGenerator Tests
# =============================================================================


class TestTemplateGenerator:
    """Tests for TemplateGenerator class."""

    @pytest.fixture
    def mock_tracker(self):
        """Create a mock tracker."""
        tracker = Mock()
        tracker.config = Mock()
        tracker.config.url = "https://example.atlassian.net"
        return tracker

    @pytest.fixture
    def console(self):
        """Create a console instance."""
        return Console(color=False, json_mode=False)

    @pytest.fixture
    def generator(self, mock_tracker, console):
        """Create a generator instance."""
        return TemplateGenerator(
            tracker=mock_tracker,
            console=console,
        )

    def test_generator_initialization(self, generator):
        """Test generator initializes with default settings."""
        assert generator.include_subtasks is True
        assert generator.include_descriptions is True
        assert generator.include_acceptance_criteria is True
        assert generator.template_style == "full"

    def test_get_status_emoji_done(self, generator):
        """Test status emoji for done status."""
        assert generator._get_status_emoji("Done") == "✅"
        assert generator._get_status_emoji("Closed") == "✅"
        assert generator._get_status_emoji("Resolved") == "✅"

    def test_get_status_emoji_in_progress(self, generator):
        """Test status emoji for in progress status."""
        assert generator._get_status_emoji("In Progress") == "🔄"
        assert generator._get_status_emoji("In Review") == "🔄"

    def test_get_status_emoji_todo(self, generator):
        """Test status emoji for todo status."""
        assert generator._get_status_emoji("To Do") == "📋"
        assert generator._get_status_emoji("Backlog") == "📋"

    def test_get_status_name(self, generator):
        """Test extracting status name from Jira object."""
        assert generator._get_status_name({"name": "Done"}) == "Done"
        assert generator._get_status_name({}) == "To Do"
        assert generator._get_status_name(None) == "To Do"

    def test_get_priority_name(self, generator):
        """Test extracting priority name from Jira object."""
        assert generator._get_priority_name({"name": "High"}) == "High"
        assert generator._get_priority_name({}) == "Medium"
        assert generator._get_priority_name(None) == "Medium"

    def test_extract_description_string(self, generator):
        """Test extracting plain text description."""
        assert generator._extract_description("Plain text") == "Plain text"
        assert generator._extract_description("") == ""
        assert generator._extract_description(None) == ""

    def test_extract_description_adf(self, generator):
        """Test extracting description from ADF format."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Hello "},
                        {"type": "text", "text": "World"},
                    ],
                }
            ],
        }

        result = generator._extract_description(adf)
        assert "Hello World" in result

    def test_generate_placeholder_story(self, generator):
        """Test generating a placeholder story."""
        lines = generator._generate_placeholder_story()

        content = "\n".join(lines)
        assert "US-001" in content
        assert "Story Points" in content
        assert "Acceptance Criteria" in content
        assert "- [ ]" in content


# =============================================================================
# Generate with Mock Tracker Tests
# =============================================================================


class TestGenerateWithMockTracker:
    """Tests for generate operation with mocked Jira."""

    @pytest.fixture
    def mock_tracker(self):
        """Create a mock tracker with data."""
        tracker = Mock()
        tracker.config = Mock()
        tracker.config.url = "https://example.atlassian.net"

        # Mock epic data
        tracker.get_issue.return_value = {
            "key": "PROJ-100",
            "fields": {
                "summary": "Test Epic",
                "description": "Epic description",
            },
        }

        # Mock stories
        tracker.get_epic_children.return_value = [
            {
                "key": "PROJ-101",
                "fields": {
                    "summary": "First Story",
                    "description": "Story description",
                    "status": {"name": "To Do"},
                    "priority": {"name": "Medium"},
                    "customfield_10014": 3,
                    "subtasks": [
                        {
                            "key": "PROJ-102",
                            "fields": {
                                "summary": "Subtask 1",
                                "status": {"name": "To Do"},
                            },
                        }
                    ],
                },
            },
            {
                "key": "PROJ-103",
                "fields": {
                    "summary": "Second Story",
                    "description": None,
                    "status": {"name": "Done"},
                    "priority": {"name": "High"},
                    "customfield_10014": 5,
                    "subtasks": [],
                },
            },
        ]

        return tracker

    @pytest.fixture
    def console(self):
        """Create a console instance."""
        return Console(color=False, json_mode=False)

    def test_generate_dry_run(self, mock_tracker, console):
        """Test generate in dry run mode."""
        generator = TemplateGenerator(
            tracker=mock_tracker,
            console=console,
        )

        result = generator.generate(
            epic_key="PROJ-100",
            dry_run=True,
        )

        assert result.success is True
        assert result.epic_key == "PROJ-100"
        assert result.epic_title == "Test Epic"
        assert result.stories_count == 2
        assert result.subtasks_count == 1  # Only first story has subtasks

    def test_generate_with_output_path(self, mock_tracker, console):
        """Test generate with custom output path."""
        generator = TemplateGenerator(
            tracker=mock_tracker,
            console=console,
        )

        result = generator.generate(
            epic_key="PROJ-100",
            output_path="custom-output.md",
            dry_run=True,
        )

        assert result.output_path == "custom-output.md"

    def test_generate_execute(self, mock_tracker, console, tmp_path, monkeypatch):
        """Test generate with execute (writes file)."""
        monkeypatch.chdir(tmp_path)

        generator = TemplateGenerator(
            tracker=mock_tracker,
            console=console,
        )

        output_path = str(tmp_path / "PROJ-100.md")
        result = generator.generate(
            epic_key="PROJ-100",
            output_path=output_path,
            dry_run=False,
        )

        assert result.success is True
        assert Path(output_path).exists()

        content = Path(output_path).read_text()
        assert "PROJ-100" in content
        assert "Test Epic" in content
        assert "US-001" in content
        assert "First Story" in content
        assert "Second Story" in content

    def test_generate_no_stories(self, mock_tracker, console):
        """Test generate with no stories returns warning."""
        mock_tracker.get_epic_children.return_value = []

        generator = TemplateGenerator(
            tracker=mock_tracker,
            console=console,
        )

        result = generator.generate(
            epic_key="PROJ-100",
            dry_run=True,
        )

        assert result.success is True
        assert result.stories_count == 0
        assert len(result.warnings) == 1
        assert "No stories found" in result.warnings[0]

    def test_preview(self, mock_tracker, console):
        """Test preview returns markdown content."""
        generator = TemplateGenerator(
            tracker=mock_tracker,
            console=console,
        )

        content = generator.preview("PROJ-100")

        assert content is not None
        assert "PROJ-100" in content
        assert "Test Epic" in content
        assert "First Story" in content

    def test_generate_no_subtasks(self, mock_tracker, console):
        """Test generate without subtasks."""
        generator = TemplateGenerator(
            tracker=mock_tracker,
            console=console,
            include_subtasks=False,
        )

        result = generator.generate(
            epic_key="PROJ-100",
            dry_run=True,
        )

        assert result.success is True
        # Subtasks count should still be counted from Jira
        assert result.subtasks_count == 1

    def test_generate_tracker_error(self, mock_tracker, console):
        """Test generate handles tracker errors."""
        mock_tracker.get_issue.side_effect = Exception("Connection failed")

        generator = TemplateGenerator(
            tracker=mock_tracker,
            console=console,
        )

        result = generator.generate(
            epic_key="PROJ-100",
            dry_run=True,
        )

        assert result.success is False
        assert len(result.errors) >= 1


# =============================================================================
# Markdown Content Tests
# =============================================================================


class TestMarkdownContent:
    """Tests for generated markdown content."""

    @pytest.fixture
    def mock_tracker(self):
        """Create a mock tracker."""
        tracker = Mock()
        tracker.config = Mock()
        tracker.config.url = "https://example.atlassian.net"

        tracker.get_issue.return_value = {
            "key": "TEST-1",
            "fields": {
                "summary": "Epic Title",
                "description": "Epic description text",
            },
        }

        tracker.get_epic_children.return_value = [
            {
                "key": "TEST-2",
                "fields": {
                    "summary": "Story Title",
                    "description": None,
                    "status": {"name": "To Do"},
                    "priority": {"name": "Medium"},
                    "customfield_10014": 5,
                    "subtasks": [
                        {
                            "key": "TEST-3",
                            "fields": {
                                "summary": "Task One",
                                "status": {"name": "Done"},
                            },
                        },
                        {
                            "key": "TEST-4",
                            "fields": {
                                "summary": "Task Two",
                                "status": {"name": "To Do"},
                            },
                        },
                    ],
                },
            },
        ]

        return tracker

    @pytest.fixture
    def console(self):
        """Create a console instance."""
        return Console(color=False, json_mode=False)

    def test_markdown_has_epic_header(self, mock_tracker, console):
        """Test markdown includes epic header."""
        generator = TemplateGenerator(tracker=mock_tracker, console=console)
        content = generator.preview("TEST-1")

        assert "# 🚀 TEST-1: Epic Title" in content

    def test_markdown_has_stories_section(self, mock_tracker, console):
        """Test markdown includes stories section."""
        generator = TemplateGenerator(tracker=mock_tracker, console=console)
        content = generator.preview("TEST-1")

        assert "## Stories" in content

    def test_markdown_has_story_format(self, mock_tracker, console):
        """Test markdown has proper story format."""
        generator = TemplateGenerator(tracker=mock_tracker, console=console)
        content = generator.preview("TEST-1")

        assert "### " in content
        assert "US-001" in content
        assert "Story Title" in content

    def test_markdown_has_metadata_table(self, mock_tracker, console):
        """Test markdown has metadata table."""
        generator = TemplateGenerator(tracker=mock_tracker, console=console)
        content = generator.preview("TEST-1")

        assert "| Field | Value |" in content
        assert "Story Points" in content
        assert "Priority" in content
        assert "Status" in content

    def test_markdown_has_subtasks(self, mock_tracker, console):
        """Test markdown includes subtasks."""
        generator = TemplateGenerator(tracker=mock_tracker, console=console)
        content = generator.preview("TEST-1")

        assert "#### Subtasks" in content
        assert "Task One" in content
        assert "Task Two" in content
        assert "[x]" in content  # Done task
        assert "[ ]" in content  # Todo task

    def test_markdown_has_jira_link(self, mock_tracker, console):
        """Test markdown includes Jira link."""
        generator = TemplateGenerator(tracker=mock_tracker, console=console)
        content = generator.preview("TEST-1")

        assert "[TEST-2]" in content
        assert "https://example.atlassian.net/browse/TEST-2" in content

    def test_markdown_has_footer(self, mock_tracker, console):
        """Test markdown includes footer with instructions."""
        generator = TemplateGenerator(tracker=mock_tracker, console=console)
        content = generator.preview("TEST-1")

        assert "Generated from Jira epic" in content
        assert "spectra --input" in content


# =============================================================================
# CLI Integration Tests
# =============================================================================


class TestCLIIntegration:
    """Tests for CLI integration."""

    def test_generate_flag_in_parser(self, cli_parser):
        """Test --generate flag is recognized by parser."""
        args = cli_parser.parse_args(["--generate", "--epic", "PROJ-123"])

        assert args.generate is True
        assert args.epic == "PROJ-123"

    def test_generate_with_output(self, cli_parser):
        """Test --generate with output path."""
        args = cli_parser.parse_args(
            [
                "--generate",
                "--epic",
                "PROJ-123",
                "--generate-output",
                "custom.md",
            ]
        )

        assert args.generate is True
        assert args.generate_output == "custom.md"

    def test_generate_with_options(self, cli_parser):
        """Test --generate with various options."""
        args = cli_parser.parse_args(
            [
                "--generate",
                "--epic",
                "PROJ-123",
                "--no-subtasks",
                "--no-descriptions",
                "--force",
                "--execute",
            ]
        )

        assert args.generate is True
        assert args.no_subtasks is True
        assert args.no_descriptions is True
        assert args.force is True
        assert args.execute is True

    def test_generate_with_preview(self, cli_parser):
        """Test --generate with preview."""
        args = cli_parser.parse_args(
            [
                "--generate",
                "--epic",
                "PROJ-123",
                "--preview",
            ]
        )

        assert args.generate is True
        assert args.preview is True


# =============================================================================
# run_generate Function Tests
# =============================================================================


class TestRunGenerate:
    """Tests for run_generate function."""

    @patch("spectra.adapters.config.environment.EnvironmentConfigProvider.validate")
    def test_run_generate_config_error(self, mock_validate):
        """Test run_generate with config error."""
        mock_validate.return_value = ["Missing JIRA_URL"]

        console = Console(color=False, json_mode=False)
        args = Mock()
        args.epic = "PROJ-123"
        args.config = None
        args.verbose = False
        args.log_format = "text"
        args.execute = False
        args.preview = False
        args.generate_output = None
        args.output_file = None
        args.force = False
        args.no_color = False
        args.quiet = False

        result = run_generate(args, console)

        assert result == ExitCode.CONFIG_ERROR
