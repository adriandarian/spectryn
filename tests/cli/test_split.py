"""Tests for spectra.cli.split module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from spectryn.cli.exit_codes import ExitCode
from spectryn.cli.split import (
    SplitSuggestion,
    StorySplitAnalysis,
    analyze_story_complexity,
    format_analysis,
    generate_split_suggestions,
    run_split,
)


class TestSplitSuggestion:
    """Tests for SplitSuggestion dataclass."""

    def test_suggestion_creation(self):
        """Test SplitSuggestion creation."""
        suggestion = SplitSuggestion(
            title="Test Story - Part 1",
            description="First part",
            story_points=5,
            acceptance_criteria=["AC1", "AC2"],
            rationale="Split for smaller scope",
        )
        assert suggestion.title == "Test Story - Part 1"
        assert suggestion.description == "First part"
        assert suggestion.story_points == 5
        assert len(suggestion.acceptance_criteria) == 2
        assert suggestion.rationale == "Split for smaller scope"

    def test_suggestion_defaults(self):
        """Test SplitSuggestion default values."""
        suggestion = SplitSuggestion(
            title="Test",
            description="Desc",
        )
        assert suggestion.story_points is None
        assert suggestion.acceptance_criteria == []
        assert suggestion.rationale == ""


class TestStorySplitAnalysis:
    """Tests for StorySplitAnalysis dataclass."""

    def test_analysis_creation(self):
        """Test StorySplitAnalysis creation."""
        analysis = StorySplitAnalysis(
            original_id="US-001",
            original_title="Test Story",
            original_points=13,
            complexity_score=7,
            split_recommended=True,
            reasons=["Too large"],
            suggestions=[
                SplitSuggestion(title="Part 1", description="First"),
            ],
        )
        assert analysis.original_id == "US-001"
        assert analysis.original_title == "Test Story"
        assert analysis.original_points == 13
        assert analysis.complexity_score == 7
        assert analysis.split_recommended is True
        assert len(analysis.reasons) == 1
        assert len(analysis.suggestions) == 1

    def test_analysis_defaults(self):
        """Test StorySplitAnalysis default values."""
        analysis = StorySplitAnalysis(
            original_id="US-001",
            original_title="Test",
            original_points=None,
            complexity_score=1,
            split_recommended=False,
        )
        assert analysis.reasons == []
        assert analysis.suggestions == []


class TestAnalyzeStoryComplexity:
    """Tests for analyze_story_complexity function."""

    def test_analyze_simple_story(self):
        """Test analysis of simple story."""
        story = {
            "id": "US-001",
            "title": "Simple story",
            "story_points": 3,
            "acceptance_criteria": ["AC1"],
            "description": "",
        }
        analysis = analyze_story_complexity(story)

        assert analysis.original_id == "US-001"
        assert analysis.complexity_score < 4
        assert analysis.split_recommended is False

    def test_analyze_high_points_story(self):
        """Test analysis of high-points story."""
        story = {
            "id": "US-001",
            "title": "Large story",
            "story_points": 13,
            "acceptance_criteria": [],
            "description": "",
        }
        analysis = analyze_story_complexity(story)

        assert analysis.complexity_score >= 4
        assert analysis.split_recommended is True
        assert any("story points" in r.lower() for r in analysis.reasons)

    def test_analyze_moderate_points(self):
        """Test analysis with 8 points."""
        story = {
            "id": "US-001",
            "title": "Medium story",
            "story_points": 8,
            "acceptance_criteria": [],
            "description": "",
        }
        analysis = analyze_story_complexity(story)

        assert any("story points" in r.lower() for r in analysis.reasons)

    def test_analyze_many_acceptance_criteria(self):
        """Test analysis with many acceptance criteria."""
        story = {
            "id": "US-001",
            "title": "Story",
            "story_points": 3,
            "acceptance_criteria": [f"AC{i}" for i in range(10)],
            "description": "",
        }
        analysis = analyze_story_complexity(story)

        assert analysis.complexity_score >= 3
        assert any("acceptance criteria" in r.lower() for r in analysis.reasons)

    def test_analyze_title_with_and(self):
        """Test analysis of title with 'and'."""
        story = {
            "id": "US-001",
            "title": "Create login and registration",
            "story_points": 3,
            "acceptance_criteria": [],
            "description": "",
        }
        analysis = analyze_story_complexity(story)

        assert any("and" in r.lower() for r in analysis.reasons)

    def test_analyze_title_with_ampersand(self):
        """Test analysis of title with '&'."""
        story = {
            "id": "US-001",
            "title": "Create login & registration",
            "story_points": 3,
            "acceptance_criteria": [],
            "description": "",
        }
        analysis = analyze_story_complexity(story)

        assert any("and" in r.lower() for r in analysis.reasons)

    def test_analyze_multiple_user_types(self):
        """Test analysis with multiple user types."""
        story = {
            "id": "US-001",
            "title": "Create permission system",
            "story_points": 3,
            "acceptance_criteria": [],
            "description": "As a user and admin, I want to manage permissions",
        }
        analysis = analyze_story_complexity(story)

        assert any("user types" in r.lower() for r in analysis.reasons)

    def test_analyze_technical_breadth(self):
        """Test analysis with technical breadth."""
        story = {
            "id": "US-001",
            "title": "Build frontend and backend with database integration",
            "story_points": 3,
            "acceptance_criteria": [],
            "description": "",
        }
        analysis = analyze_story_complexity(story)

        assert any("technical" in r.lower() for r in analysis.reasons)

    def test_analyze_story_object(self):
        """Test analysis with story object (not dict)."""
        mock_story = MagicMock()
        mock_story.id = "US-001"
        mock_story.title = "Test Story"
        mock_story.story_points = 3
        mock_story.acceptance_criteria = []
        mock_story.description = None

        analysis = analyze_story_complexity(mock_story)

        assert analysis.original_id == "US-001"

    def test_analyze_story_with_description_object(self):
        """Test analysis with description having as_a attribute."""
        mock_story = MagicMock()
        mock_story.id = "US-001"
        mock_story.title = "Test Story"
        mock_story.story_points = 3
        mock_story.acceptance_criteria = []
        mock_story.description = MagicMock()
        mock_story.description.as_a = "As a user"
        mock_story.description.i_want = "I want to login"
        mock_story.description.so_that = "so that I can access the system"

        analysis = analyze_story_complexity(mock_story)

        assert analysis.original_id == "US-001"

    def test_analyze_complexity_capped_at_10(self):
        """Test that complexity score is capped at 10."""
        story = {
            "id": "US-001",
            "title": "Full frontend and backend with database integration and migration",
            "story_points": 21,
            "acceptance_criteria": [f"AC{i}" for i in range(15)],
            "description": "As a user and admin and manager, I want everything",
        }
        analysis = analyze_story_complexity(story)

        assert analysis.complexity_score <= 10

    def test_analyze_generates_suggestions_when_recommended(self):
        """Test that suggestions are generated when split is recommended."""
        story = {
            "id": "US-001",
            "title": "Large story",
            "story_points": 13,
            "acceptance_criteria": ["AC1", "AC2", "AC3", "AC4", "AC5", "AC6"],
            "description": "",
        }
        analysis = analyze_story_complexity(story)

        assert analysis.split_recommended is True
        assert len(analysis.suggestions) > 0


class TestGenerateSplitSuggestions:
    """Tests for generate_split_suggestions function."""

    def test_generate_by_acceptance_criteria(self):
        """Test splitting by acceptance criteria."""
        suggestions = generate_split_suggestions(
            title="Test Story",
            description="",
            acceptance_criteria=["AC1", "AC2", "AC3", "AC4"],
            original_points=8,
        )

        # Should suggest splitting AC
        assert len(suggestions) >= 2
        assert any("Part 1" in s.title for s in suggestions)
        assert any("Part 2" in s.title for s in suggestions)

    def test_generate_by_technical_layer(self):
        """Test splitting by technical layer."""
        suggestions = generate_split_suggestions(
            title="Full stack feature implementation",
            description="",
            acceptance_criteria=[],
            original_points=9,
        )

        # Should suggest vertical slices
        assert any("Backend" in s.title or "Frontend" in s.title for s in suggestions)

    def test_generate_by_and_in_title(self):
        """Test splitting by 'and' in title."""
        suggestions = generate_split_suggestions(
            title="Create login and registration",
            description="",
            acceptance_criteria=[],
            original_points=8,
        )

        # Should have suggestions for each concern
        assert len(suggestions) >= 2

    def test_generate_generic_mvp_split(self):
        """Test generic MVP/Enhancement split."""
        suggestions = generate_split_suggestions(
            title="Regular feature",
            description="",
            acceptance_criteria=["AC1"],  # Not enough for AC-based split
            original_points=10,
        )

        # Should have generic MVP split
        assert any("MVP" in s.title or "Core" in s.title for s in suggestions)
        assert any("Enhancement" in s.title for s in suggestions)

    def test_points_distributed_correctly(self):
        """Test that points are distributed."""
        suggestions = generate_split_suggestions(
            title="Test Story",
            description="",
            acceptance_criteria=["AC1", "AC2", "AC3", "AC4"],
            original_points=8,
        )

        total_points = sum(s.story_points or 0 for s in suggestions[:2])
        assert total_points == 8

    def test_no_points(self):
        """Test with no original points."""
        suggestions = generate_split_suggestions(
            title="Test Story",
            description="",
            acceptance_criteria=["AC1", "AC2", "AC3", "AC4"],
            original_points=None,
        )

        assert all(s.story_points is None for s in suggestions)


class TestFormatAnalysis:
    """Tests for format_analysis function."""

    def test_format_basic_analysis(self):
        """Test basic analysis formatting."""
        analysis = StorySplitAnalysis(
            original_id="US-001",
            original_title="Test Story",
            original_points=5,
            complexity_score=3,
            split_recommended=False,
        )
        lines = format_analysis(analysis, color=False)
        output = "\n".join(lines)

        assert "US-001" in output
        assert "Test Story" in output
        assert "3/10" in output

    def test_format_split_recommended(self):
        """Test formatting when split is recommended."""
        analysis = StorySplitAnalysis(
            original_id="US-001",
            original_title="Test Story",
            original_points=13,
            complexity_score=7,
            split_recommended=True,
            reasons=["Too large"],
        )
        lines = format_analysis(analysis, color=False)
        output = "\n".join(lines)

        assert "Split Recommended" in output

    def test_format_size_looks_good(self):
        """Test formatting when size looks good."""
        analysis = StorySplitAnalysis(
            original_id="US-001",
            original_title="Test",
            original_points=3,
            complexity_score=2,
            split_recommended=False,
        )
        lines = format_analysis(analysis, color=False)
        output = "\n".join(lines)

        assert "Size looks good" in output or "✓" in output

    def test_format_with_reasons(self):
        """Test formatting with reasons."""
        analysis = StorySplitAnalysis(
            original_id="US-001",
            original_title="Test",
            original_points=8,
            complexity_score=5,
            split_recommended=True,
            reasons=["Too many AC", "Multiple concerns"],
        )
        lines = format_analysis(analysis, color=False)
        output = "\n".join(lines)

        assert "Analysis:" in output
        assert "Too many AC" in output

    def test_format_with_suggestions(self):
        """Test formatting with suggestions."""
        analysis = StorySplitAnalysis(
            original_id="US-001",
            original_title="Test",
            original_points=10,
            complexity_score=6,
            split_recommended=True,
            suggestions=[
                SplitSuggestion(
                    title="Part 1",
                    description="First",
                    story_points=5,
                    rationale="Split for scope",
                    acceptance_criteria=["AC1", "AC2"],
                ),
            ],
        )
        lines = format_analysis(analysis, color=False)
        output = "\n".join(lines)

        assert "Suggested Split" in output
        assert "Part 1" in output
        assert "5" in output
        assert "Split for scope" in output

    def test_format_with_color(self):
        """Test formatting with color enabled."""
        analysis = StorySplitAnalysis(
            original_id="US-001",
            original_title="Test",
            original_points=13,
            complexity_score=8,
            split_recommended=True,
        )
        lines = format_analysis(analysis, color=True)
        output = "\n".join(lines)

        # Should contain ANSI color codes
        assert "\x1b[" in output

    def test_format_complexity_colors(self):
        """Test complexity bar color based on score."""
        # Low complexity - green
        analysis_low = StorySplitAnalysis(
            original_id="US-001",
            original_title="Test",
            original_points=3,
            complexity_score=2,
            split_recommended=False,
        )
        lines_low = format_analysis(analysis_low, color=True)
        output_low = "\n".join(lines_low)

        # High complexity - red
        analysis_high = StorySplitAnalysis(
            original_id="US-002",
            original_title="Test",
            original_points=21,
            complexity_score=9,
            split_recommended=True,
        )
        lines_high = format_analysis(analysis_high, color=True)
        output_high = "\n".join(lines_high)

        # Both should have ANSI codes
        assert "\x1b[" in output_low
        assert "\x1b[" in output_high

    def test_format_no_points(self):
        """Test formatting with no story points."""
        analysis = StorySplitAnalysis(
            original_id="US-001",
            original_title="Test",
            original_points=None,
            complexity_score=3,
            split_recommended=False,
        )
        lines = format_analysis(analysis, color=False)
        output = "\n".join(lines)

        # Should not crash, "Story Points" line should not appear
        assert "US-001" in output

    def test_format_many_acceptance_criteria(self):
        """Test truncation of many acceptance criteria."""
        analysis = StorySplitAnalysis(
            original_id="US-001",
            original_title="Test",
            original_points=10,
            complexity_score=6,
            split_recommended=True,
            suggestions=[
                SplitSuggestion(
                    title="Part 1",
                    description="First",
                    acceptance_criteria=[f"AC{i}" for i in range(10)],
                ),
            ],
        )
        lines = format_analysis(analysis, color=False)
        output = "\n".join(lines)

        # Should show truncation message
        assert "... and" in output


class TestRunSplit:
    """Tests for run_split function."""

    @pytest.fixture
    def mock_console(self):
        """Create mock console."""
        console = MagicMock()
        console.color = True
        return console

    def test_run_split_no_input(self, mock_console):
        """Test run_split with no input path."""
        result = run_split(
            console=mock_console,
            input_path=None,
        )
        assert result == ExitCode.ERROR
        mock_console.error.assert_called()

    def test_run_split_file_not_found(self, mock_console, tmp_path):
        """Test run_split with non-existent file."""
        result = run_split(
            console=mock_console,
            input_path=tmp_path / "nonexistent.md",
        )
        assert result == ExitCode.ERROR

    @patch("spectryn.adapters.parsers.markdown.MarkdownParser")
    def test_run_split_parse_error(self, mock_parser_class, mock_console, tmp_path):
        """Test run_split with parse error."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")

        mock_parser = MagicMock()
        mock_parser.parse_stories.side_effect = Exception("Parse error")
        mock_parser_class.return_value = mock_parser

        result = run_split(
            console=mock_console,
            input_path=test_file,
        )
        assert result == ExitCode.ERROR

    @patch("spectryn.adapters.parsers.markdown.MarkdownParser")
    def test_run_split_no_stories(self, mock_parser_class, mock_console, tmp_path):
        """Test run_split with no stories found."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")

        mock_parser = MagicMock()
        mock_parser.parse_stories.return_value = []
        mock_parser_class.return_value = mock_parser

        result = run_split(
            console=mock_console,
            input_path=test_file,
        )
        assert result == ExitCode.SUCCESS
        mock_console.warning.assert_called()

    @patch("spectryn.adapters.parsers.markdown.MarkdownParser")
    def test_run_split_success(self, mock_parser_class, mock_console, tmp_path):
        """Test run_split success."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")

        mock_story = MagicMock()
        mock_story.id = "US-001"
        mock_story.title = "Test Story"
        mock_story.story_points = 5
        mock_story.acceptance_criteria = []
        mock_story.description = None

        mock_parser = MagicMock()
        mock_parser.parse_stories.return_value = [mock_story]
        mock_parser_class.return_value = mock_parser

        result = run_split(
            console=mock_console,
            input_path=test_file,
        )
        assert result == ExitCode.SUCCESS

    @patch("spectryn.adapters.parsers.markdown.MarkdownParser")
    def test_run_split_specific_story(self, mock_parser_class, mock_console, tmp_path):
        """Test run_split with specific story ID."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")

        mock_story1 = MagicMock()
        mock_story1.id = "US-001"
        mock_story1.title = "Story 1"
        mock_story1.story_points = 3
        mock_story1.acceptance_criteria = []
        mock_story1.description = None

        mock_story2 = MagicMock()
        mock_story2.id = "US-002"
        mock_story2.title = "Story 2"
        mock_story2.story_points = 5
        mock_story2.acceptance_criteria = []
        mock_story2.description = None

        mock_parser = MagicMock()
        mock_parser.parse_stories.return_value = [mock_story1, mock_story2]
        mock_parser_class.return_value = mock_parser

        result = run_split(
            console=mock_console,
            input_path=test_file,
            story_id="US-001",
        )
        assert result == ExitCode.SUCCESS

    @patch("spectryn.adapters.parsers.markdown.MarkdownParser")
    def test_run_split_story_not_found(self, mock_parser_class, mock_console, tmp_path):
        """Test run_split when story ID not found."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")

        mock_story = MagicMock()
        mock_story.id = "US-001"
        mock_story.title = "Story"
        mock_story.story_points = 3
        mock_story.acceptance_criteria = []
        mock_story.description = None

        mock_parser = MagicMock()
        mock_parser.parse_stories.return_value = [mock_story]
        mock_parser_class.return_value = mock_parser

        result = run_split(
            console=mock_console,
            input_path=test_file,
            story_id="US-999",
        )
        assert result == ExitCode.ERROR

    @patch("spectryn.adapters.parsers.markdown.MarkdownParser")
    def test_run_split_json_output(self, mock_parser_class, mock_console, tmp_path, capsys):
        """Test run_split with JSON output."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")

        mock_story = MagicMock()
        mock_story.id = "US-001"
        mock_story.title = "Test Story"
        mock_story.story_points = 13
        mock_story.acceptance_criteria = ["AC1", "AC2", "AC3", "AC4", "AC5", "AC6"]
        mock_story.description = None

        mock_parser = MagicMock()
        mock_parser.parse_stories.return_value = [mock_story]
        mock_parser_class.return_value = mock_parser

        result = run_split(
            console=mock_console,
            input_path=test_file,
            output_format="json",
        )
        assert result == ExitCode.SUCCESS

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "total_stories" in data
        assert "split_recommended" in data
        assert "analyses" in data

    @patch("spectryn.adapters.parsers.markdown.MarkdownParser")
    def test_run_split_markdown_output(self, mock_parser_class, mock_console, tmp_path, capsys):
        """Test run_split with markdown output."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")

        mock_story = MagicMock()
        mock_story.id = "US-001"
        mock_story.title = "Test Story"
        mock_story.story_points = 13
        mock_story.acceptance_criteria = []
        mock_story.description = None

        mock_parser = MagicMock()
        mock_parser.parse_stories.return_value = [mock_story]
        mock_parser_class.return_value = mock_parser

        result = run_split(
            console=mock_console,
            input_path=test_file,
            output_format="markdown",
        )
        assert result == ExitCode.SUCCESS

        captured = capsys.readouterr()
        assert "# Story Split Analysis" in captured.out
        assert "US-001" in captured.out

    @patch("spectryn.adapters.parsers.markdown.MarkdownParser")
    def test_run_split_with_recommendations(self, mock_parser_class, mock_console, tmp_path):
        """Test run_split with stories needing splits."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")

        mock_story = MagicMock()
        mock_story.id = "US-001"
        mock_story.title = "Large feature and another feature"
        mock_story.story_points = 13
        mock_story.acceptance_criteria = ["AC1", "AC2", "AC3", "AC4", "AC5"]
        mock_story.description = None

        mock_parser = MagicMock()
        mock_parser.parse_stories.return_value = [mock_story]
        mock_parser_class.return_value = mock_parser

        result = run_split(
            console=mock_console,
            input_path=test_file,
        )
        assert result == ExitCode.SUCCESS

    @patch("spectryn.adapters.parsers.markdown.MarkdownParser")
    def test_run_split_no_color(self, mock_parser_class, mock_console, tmp_path):
        """Test run_split without color."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")

        mock_story = MagicMock()
        mock_story.id = "US-001"
        mock_story.title = "Test"
        mock_story.story_points = 3
        mock_story.acceptance_criteria = []
        mock_story.description = None

        mock_parser = MagicMock()
        mock_parser.parse_stories.return_value = [mock_story]
        mock_parser_class.return_value = mock_parser

        # Set color to False
        mock_console.color = False

        result = run_split(
            console=mock_console,
            input_path=test_file,
            color=False,
        )
        assert result == ExitCode.SUCCESS

    def test_run_split_creates_console_if_none(self, tmp_path):
        """Test that run_split creates console if None provided."""
        test_file = tmp_path / "nonexistent.md"

        # Should not crash even without console
        result = run_split(
            console=None,
            input_path=test_file,
        )
        assert result == ExitCode.ERROR  # File not found
