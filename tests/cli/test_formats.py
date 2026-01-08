"""Tests for output format module."""

import json

import pytest

from spectryn.cli.formats import (
    OutputData,
    OutputFormat,
    OutputFormatter,
    format_diff_result_output,
    format_stats_output,
    format_sync_result_output,
    format_validation_result_output,
)


class TestOutputFormat:
    """Tests for OutputFormat enum."""

    def test_from_string_valid(self) -> None:
        """Should parse valid format strings."""
        assert OutputFormat.from_string("json") == OutputFormat.JSON
        assert OutputFormat.from_string("yaml") == OutputFormat.YAML
        assert OutputFormat.from_string("markdown") == OutputFormat.MARKDOWN
        assert OutputFormat.from_string("text") == OutputFormat.TEXT

    def test_from_string_case_insensitive(self) -> None:
        """Should handle case variations."""
        assert OutputFormat.from_string("JSON") == OutputFormat.JSON
        assert OutputFormat.from_string("Yaml") == OutputFormat.YAML
        assert OutputFormat.from_string("MARKDOWN") == OutputFormat.MARKDOWN

    def test_from_string_invalid(self) -> None:
        """Should default to TEXT for invalid formats."""
        assert OutputFormat.from_string("invalid") == OutputFormat.TEXT
        assert OutputFormat.from_string("") == OutputFormat.TEXT


class TestOutputData:
    """Tests for OutputData dataclass."""

    def test_to_dict_basic(self) -> None:
        """Should convert basic data to dict."""
        data = OutputData(title="Test", success=True, data={"key": "value"})
        result = data.to_dict()

        assert result["success"] is True
        assert result["key"] == "value"

    def test_to_dict_with_errors(self) -> None:
        """Should include errors in dict."""
        data = OutputData(
            title="Test",
            success=False,
            errors=["Error 1", "Error 2"],
        )
        result = data.to_dict()

        assert result["success"] is False
        assert result["errors"] == ["Error 1", "Error 2"]

    def test_to_dict_with_warnings(self) -> None:
        """Should include warnings in dict."""
        data = OutputData(
            title="Test",
            success=True,
            warnings=["Warning 1"],
        )
        result = data.to_dict()

        assert result["warnings"] == ["Warning 1"]

    def test_to_dict_with_metadata(self) -> None:
        """Should include metadata in dict."""
        data = OutputData(
            title="Test",
            success=True,
            metadata={"version": "1.0"},
        )
        result = data.to_dict()

        assert result["metadata"]["version"] == "1.0"


class TestOutputFormatter:
    """Tests for OutputFormatter class."""

    @pytest.fixture
    def sample_data(self) -> OutputData:
        """Create sample output data."""
        return OutputData(
            title="Test Output",
            success=True,
            data={
                "count": 5,
                "items": ["item1", "item2"],
            },
            errors=[],
            warnings=["A warning"],
            metadata={"timestamp": "2024-01-15T10:00:00"},
        )

    def test_to_json(self, sample_data: OutputData) -> None:
        """Should format as valid JSON."""
        formatter = OutputFormatter(format=OutputFormat.JSON)
        result = formatter.to_json(sample_data)

        # Should be valid JSON
        parsed = json.loads(result)
        assert parsed["success"] is True
        assert parsed["count"] == 5

    def test_to_yaml(self, sample_data: OutputData) -> None:
        """Should format as YAML-like output."""
        formatter = OutputFormatter(format=OutputFormat.YAML)
        result = formatter.to_yaml(sample_data)

        # Should contain YAML-like structure
        assert "success:" in result or "success: true" in result
        assert "count:" in result

    def test_to_markdown(self, sample_data: OutputData) -> None:
        """Should format as Markdown."""
        formatter = OutputFormatter(format=OutputFormat.MARKDOWN)
        result = formatter.to_markdown(sample_data)

        # Should contain markdown elements
        assert "# Test Output" in result
        assert "**Status**:" in result
        assert "✅ Success" in result

    def test_to_markdown_with_errors(self) -> None:
        """Should format errors in markdown."""
        data = OutputData(
            title="Failed Task",
            success=False,
            errors=["Something went wrong"],
        )
        formatter = OutputFormatter(format=OutputFormat.MARKDOWN)
        result = formatter.to_markdown(data)

        assert "## Errors" in result
        assert "❌" in result
        assert "Something went wrong" in result

    def test_to_markdown_with_warnings(self) -> None:
        """Should format warnings in markdown."""
        data = OutputData(
            title="Task",
            success=True,
            warnings=["Be careful"],
        )
        formatter = OutputFormatter(format=OutputFormat.MARKDOWN)
        result = formatter.to_markdown(data)

        assert "## Warnings" in result
        assert "⚠️" in result
        assert "Be careful" in result

    def test_format_output_dispatches(self, sample_data: OutputData) -> None:
        """Should dispatch to correct format method."""
        # JSON
        json_formatter = OutputFormatter(format=OutputFormat.JSON)
        assert json_formatter.format_output(sample_data).startswith("{")

        # Markdown
        md_formatter = OutputFormatter(format=OutputFormat.MARKDOWN)
        assert md_formatter.format_output(sample_data).startswith("#")


class TestFormatSyncResultOutput:
    """Tests for format_sync_result_output function."""

    def test_formats_sync_result(self) -> None:
        """Should format sync result to JSON."""

        # Create a mock sync result
        class MockSyncResult:
            success = True
            dry_run = False
            stories_matched = 5
            stories_updated = 3
            subtasks_created = 10
            subtasks_updated = 2
            comments_added = 1
            statuses_updated = 0
            matched_stories = [("US-001", "PROJ-100")]
            unmatched_stories = []
            errors = []
            warnings = []
            failed_operations = []

        result = format_sync_result_output(
            MockSyncResult(),
            format=OutputFormat.JSON,
            epic_key="PROJ-1",
        )

        parsed = json.loads(result)
        assert parsed["success"] is True
        assert parsed["stats"]["stories_matched"] == 5


class TestFormatStatsOutput:
    """Tests for format_stats_output function."""

    def test_formats_stats(self) -> None:
        """Should format stats to JSON."""
        stats = {
            "total_stories": 10,
            "completed": 5,
            "in_progress": 3,
        }

        result = format_stats_output(stats, format=OutputFormat.JSON)

        parsed = json.loads(result)
        assert parsed["total_stories"] == 10
        assert parsed["completed"] == 5


class TestFormatDiffResultOutput:
    """Tests for format_diff_result_output function."""

    def test_formats_diff_result(self) -> None:
        """Should format diff result to JSON."""

        class MockDiffResult:
            has_changes = True
            total_changes = 3
            local_path = "/path/to/file.md"
            remote_source = "Jira"
            local_only = ["US-003"]
            remote_only = []
            story_diffs = []

        result = format_diff_result_output(
            MockDiffResult(),
            format=OutputFormat.JSON,
        )

        parsed = json.loads(result)
        assert parsed["has_changes"] is True
        assert parsed["total_changes"] == 3
        assert parsed["local_only"] == ["US-003"]
