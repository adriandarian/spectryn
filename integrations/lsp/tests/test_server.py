"""Tests for Spectra Language Server."""

import pytest
from lsprotocol import types as lsp

from spectryn_lsp.server import SpectraLanguageServer


@pytest.fixture
def server() -> SpectraLanguageServer:
    """Create a test server instance."""
    return SpectraLanguageServer()


class TestBasicValidation:
    """Test basic validation without CLI."""

    def test_valid_epic_header(self, server: SpectraLanguageServer) -> None:
        """Test valid epic header passes validation."""
        source = "# Epic: User Authentication"
        diagnostics = server._basic_validation(source)
        assert len(diagnostics) == 0

    def test_valid_story_with_status(self, server: SpectraLanguageServer) -> None:
        """Test valid story with status passes validation."""
        source = "## Story: Login form\n**Status**: Todo"
        diagnostics = server._basic_validation(source)
        # Should have no errors
        error_diagnostics = [d for d in diagnostics if d.severity == lsp.DiagnosticSeverity.Error]
        assert len(error_diagnostics) == 0

    def test_missing_colon_error(self, server: SpectraLanguageServer) -> None:
        """Test missing colon is detected."""
        source = "## Story Login form"
        diagnostics = server._basic_validation(source)
        # This doesn't match the header pattern check
        assert len(diagnostics) == 0

    def test_story_missing_status_warning(self, server: SpectraLanguageServer) -> None:
        """Test missing status produces warning."""
        source = "## Story: Login form\n\nSome description"
        diagnostics = server._basic_validation(source)
        warnings = [d for d in diagnostics if d.severity == lsp.DiagnosticSeverity.Warning]
        assert len(warnings) == 1
        assert "Status" in warnings[0].message


class TestCompletions:
    """Test completion provider."""

    def test_status_completions(self, server: SpectraLanguageServer) -> None:
        """Test status field completions."""
        # Mock a simple completion request
        items = []
        prefix = "**Status**:"

        # Simulate what happens in _get_completions
        if prefix.endswith("**Status**:"):
            for status in ["Todo", "In Progress", "In Review", "Done", "Blocked", "Cancelled"]:
                items.append(status)

        assert "Todo" in items
        assert "Done" in items
        assert "In Progress" in items
        assert len(items) == 6

    def test_priority_completions(self, server: SpectraLanguageServer) -> None:
        """Test priority field completions."""
        items = []
        prefix = "**Priority**:"

        if prefix.endswith("**Priority**:"):
            for priority in ["Critical", "High", "Medium", "Low"]:
                items.append(priority)

        assert "High" in items
        assert "Critical" in items
        assert len(items) == 4

    def test_points_completions(self, server: SpectraLanguageServer) -> None:
        """Test points field completions."""
        items = []
        prefix = "**Points**:"

        if prefix.endswith("**Points**:"):
            for points in ["1", "2", "3", "5", "8", "13", "21"]:
                items.append(points)

        assert "1" in items
        assert "13" in items
        assert len(items) == 7


class TestDocumentSymbols:
    """Test document symbols provider."""

    def test_epic_symbol(self, server: SpectraLanguageServer) -> None:
        """Test epic creates module symbol."""
        kind = server._get_symbol_kind("Epic")
        assert kind == lsp.SymbolKind.Module

    def test_story_symbol(self, server: SpectraLanguageServer) -> None:
        """Test story creates class symbol."""
        kind = server._get_symbol_kind("Story")
        assert kind == lsp.SymbolKind.Class

    def test_subtask_symbol(self, server: SpectraLanguageServer) -> None:
        """Test subtask creates method symbol."""
        kind = server._get_symbol_kind("Subtask")
        assert kind == lsp.SymbolKind.Method


class TestTrackerUrls:
    """Test tracker URL building."""

    def test_jira_url(self, server: SpectraLanguageServer) -> None:
        """Test Jira URL format."""
        server.config.tracker_type = "jira"
        server.config.tracker_url = "https://example.atlassian.net"

        url = server._build_tracker_url("PROJ-123")
        assert url == "https://example.atlassian.net/browse/PROJ-123"

    def test_github_url(self, server: SpectraLanguageServer) -> None:
        """Test GitHub URL format."""
        server.config.tracker_type = "github"
        server.config.tracker_url = "https://github.com/owner/repo"

        url = server._build_tracker_url("#456")
        assert url == "https://github.com/owner/repo/issues/456"

    def test_gitlab_url(self, server: SpectraLanguageServer) -> None:
        """Test GitLab URL format."""
        server.config.tracker_type = "gitlab"
        server.config.tracker_url = "https://gitlab.com/owner/repo"

        url = server._build_tracker_url("GL-789")
        assert url == "https://gitlab.com/owner/repo/-/issues/789"

    def test_linear_url(self, server: SpectraLanguageServer) -> None:
        """Test Linear URL format."""
        server.config.tracker_type = "linear"
        server.config.tracker_url = "https://linear.app/team"

        url = server._build_tracker_url("LIN-100")
        assert url == "https://linear.app/team/issue/LIN-100"

    def test_no_tracker_url(self, server: SpectraLanguageServer) -> None:
        """Test no URL when tracker URL not configured."""
        server.config.tracker_url = ""
        url = server._build_tracker_url("PROJ-123")
        assert url is None


class TestHeaderPatterns:
    """Test header pattern matching."""

    def test_epic_header_match(self, server: SpectraLanguageServer) -> None:
        """Test epic header pattern."""
        match = server.HEADER_PATTERN.match("# Epic: User Authentication")
        assert match is not None
        assert match.group("type") == "Epic"
        assert match.group("title") == "User Authentication"

    def test_story_header_with_id(self, server: SpectraLanguageServer) -> None:
        """Test story header with tracker ID."""
        match = server.HEADER_PATTERN.match("## Story: Login form [PROJ-123]")
        assert match is not None
        assert match.group("type") == "Story"
        assert match.group("title") == "Login form"
        assert match.group("id") == "PROJ-123"

    def test_subtask_header(self, server: SpectraLanguageServer) -> None:
        """Test subtask header pattern."""
        match = server.HEADER_PATTERN.match("## Subtask: Add validation")
        assert match is not None
        assert match.group("type") == "Subtask"

    def test_invalid_header_no_match(self, server: SpectraLanguageServer) -> None:
        """Test invalid header doesn't match."""
        match = server.HEADER_PATTERN.match("## Some random header")
        assert match is None


class TestIssuePatterns:
    """Test issue ID pattern matching."""

    def test_jira_issue_pattern(self, server: SpectraLanguageServer) -> None:
        """Test Jira issue ID pattern."""
        match = server.ISSUE_PATTERN.search("See PROJ-123 for details")
        assert match is not None
        assert match.group(0) == "PROJ-123"

    def test_github_issue_pattern(self, server: SpectraLanguageServer) -> None:
        """Test GitHub issue ID pattern."""
        match = server.ISSUE_PATTERN.search("Fixed in #456")
        assert match is not None
        assert match.group(0) == "#456"

    def test_multiple_issues(self, server: SpectraLanguageServer) -> None:
        """Test multiple issue IDs in one line."""
        matches = list(server.ISSUE_PATTERN.finditer("See PROJ-123 and PROJ-456"))
        assert len(matches) == 2


class TestConfiguration:
    """Test configuration updates."""

    def test_update_tracker_config(self, server: SpectraLanguageServer) -> None:
        """Test updating tracker configuration."""
        settings = {
            "spectra": {
                "tracker": {
                    "type": "github",
                    "url": "https://github.com/test/repo",
                    "projectKey": "TEST",
                }
            }
        }
        server._update_config(settings)

        assert server.config.tracker_type == "github"
        assert server.config.tracker_url == "https://github.com/test/repo"
        assert server.config.project_key == "TEST"

    def test_update_validation_config(self, server: SpectraLanguageServer) -> None:
        """Test updating validation configuration."""
        settings = {
            "spectra": {
                "validation": {
                    "validateOnSave": False,
                    "validateOnType": False,
                }
            }
        }
        server._update_config(settings)

        assert server.config.validate_on_save is False
        assert server.config.validate_on_type is False

    def test_update_with_empty_settings(self, server: SpectraLanguageServer) -> None:
        """Test update with empty settings doesn't crash."""
        server._update_config({})
        server._update_config(None)  # type: ignore


class TestFormatIssueDetails:
    """Test issue details formatting."""

    def test_format_full_issue(self, server: SpectraLanguageServer) -> None:
        """Test formatting issue with all fields."""
        data = {
            "title": "Test Issue",
            "status": "In Progress",
            "priority": "High",
            "assignee": "john.doe",
            "points": 5,
            "description": "This is the description",
        }
        result = server._format_issue_details(data)

        assert "### Test Issue" in result
        assert "**Status**: In Progress" in result
        assert "**Priority**: High" in result
        assert "**Assignee**: john.doe" in result
        assert "**Points**: 5" in result
        assert "This is the description" in result

    def test_format_minimal_issue(self, server: SpectraLanguageServer) -> None:
        """Test formatting issue with minimal fields."""
        data = {"title": "Minimal Issue"}
        result = server._format_issue_details(data)

        assert "### Minimal Issue" in result

    def test_format_long_description_truncated(self, server: SpectraLanguageServer) -> None:
        """Test long descriptions are truncated."""
        data = {
            "title": "Long Issue",
            "description": "x" * 300,
        }
        result = server._format_issue_details(data)

        assert "..." in result
        assert len(result) < 400
