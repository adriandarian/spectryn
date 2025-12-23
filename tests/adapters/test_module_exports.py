"""
Tests for adapter module exports.
These are simple tests to verify __all__ exports are correctly set up.
"""


class TestInfrastructureExports:
    """Tests for infrastructure module exports."""

    def test_infrastructure_all_exports(self):
        """Test that infrastructure __all__ exports are defined."""
        from spectra.adapters import infrastructure

        assert hasattr(infrastructure, "__all__")
        assert "async_base" in infrastructure.__all__
        assert "cache" in infrastructure.__all__
        assert "config" in infrastructure.__all__


class TestInputExports:
    """Tests for input module exports."""

    def test_input_parsers_exported(self):
        """Test that input parsers are exported."""
        from spectra.adapters.input import MarkdownParser, NotionParser, YamlParser

        assert MarkdownParser is not None
        assert NotionParser is not None
        assert YamlParser is not None

    def test_input_all_exports(self):
        """Test that input __all__ is defined."""
        from spectra.adapters import input

        assert hasattr(input, "__all__")
        assert "MarkdownParser" in input.__all__
        assert "NotionParser" in input.__all__
        assert "YamlParser" in input.__all__


class TestOutputExports:
    """Tests for output module exports."""

    def test_output_formatters_exported(self):
        """Test that output formatters are exported."""
        from spectra.adapters.output import ADFFormatter, MarkdownWriter

        assert ADFFormatter is not None
        assert MarkdownWriter is not None

    def test_output_all_exports(self):
        """Test that output __all__ is defined."""
        from spectra.adapters import output

        assert hasattr(output, "__all__")
        assert "ADFFormatter" in output.__all__
        assert "MarkdownWriter" in output.__all__


class TestTrackersExports:
    """Tests for trackers module exports."""

    def test_trackers_adapters_exported(self):
        """Test that tracker adapters are exported."""
        from spectra.adapters.trackers import (
            AsanaAdapter,
            AzureDevOpsAdapter,
            ConfluenceAdapter,
            GitHubAdapter,
            JiraAdapter,
            LinearAdapter,
        )

        assert AsanaAdapter is not None
        assert AzureDevOpsAdapter is not None
        assert ConfluenceAdapter is not None
        assert GitHubAdapter is not None
        assert JiraAdapter is not None
        assert LinearAdapter is not None

    def test_trackers_all_exports(self):
        """Test that trackers __all__ is defined."""
        from spectra.adapters import trackers

        assert hasattr(trackers, "__all__")
        assert "AsanaAdapter" in trackers.__all__
        assert "AzureDevOpsAdapter" in trackers.__all__
        assert "ConfluenceAdapter" in trackers.__all__
        assert "GitHubAdapter" in trackers.__all__
        assert "JiraAdapter" in trackers.__all__
        assert "LinearAdapter" in trackers.__all__

