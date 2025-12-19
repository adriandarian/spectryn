"""
Tests for the TUI dashboard.

Tests dashboard display and data loading.
"""

from datetime import datetime

import pytest

from spectra.cli.dashboard import (
    Dashboard,
    DashboardData,
    StoryStatus,
    load_dashboard_data,
    run_dashboard,
)
from spectra.cli.exit_codes import ExitCode
from spectra.cli.output import Console


# =============================================================================
# StoryStatus Tests
# =============================================================================


class TestStoryStatus:
    """Tests for StoryStatus dataclass."""

    def test_default_values(self):
        """Test StoryStatus has sensible defaults."""
        status = StoryStatus(
            story_id="US-001",
            title="Test Story",
        )

        assert status.story_id == "US-001"
        assert status.title == "Test Story"
        assert status.jira_key is None
        assert status.status == "Unknown"
        assert status.points == 0
        assert status.subtask_count == 0
        assert status.last_synced is None
        assert status.has_changes is False
        assert status.sync_status == "pending"

    def test_full_story_status(self):
        """Test StoryStatus with all fields."""
        now = datetime.now()
        status = StoryStatus(
            story_id="US-001",
            title="Full Story",
            jira_key="PROJ-123",
            status="In Progress",
            points=5,
            subtask_count=3,
            last_synced=now,
            has_changes=True,
            sync_status="synced",
        )

        assert status.jira_key == "PROJ-123"
        assert status.status == "In Progress"
        assert status.points == 5
        assert status.subtask_count == 3
        assert status.last_synced == now
        assert status.has_changes is True
        assert status.sync_status == "synced"


# =============================================================================
# DashboardData Tests
# =============================================================================


class TestDashboardData:
    """Tests for DashboardData dataclass."""

    def test_default_values(self):
        """Test DashboardData has sensible defaults."""
        data = DashboardData()

        assert data.epic_key == ""
        assert data.epic_title == ""
        assert data.markdown_path == ""
        assert data.stories == []
        assert data.total_syncs == 0
        assert data.successful_syncs == 0
        assert data.failed_syncs == 0
        assert data.last_sync is None
        assert data.has_pending_session is False
        assert data.backup_count == 0

    def test_with_stories(self):
        """Test DashboardData with stories."""
        stories = [
            StoryStatus(story_id="US-001", title="Story 1", points=3),
            StoryStatus(story_id="US-002", title="Story 2", points=5),
        ]

        data = DashboardData(
            epic_key="PROJ-100",
            epic_title="Test Epic",
            stories=stories,
        )

        assert len(data.stories) == 2
        assert data.epic_key == "PROJ-100"


# =============================================================================
# Dashboard Tests
# =============================================================================


class TestDashboard:
    """Tests for Dashboard class."""

    @pytest.fixture
    def console(self):
        """Create a console instance."""
        return Console(color=False, json_mode=False)

    @pytest.fixture
    def dashboard(self, console):
        """Create a dashboard instance."""
        return Dashboard(console)

    @pytest.fixture
    def sample_data(self):
        """Create sample dashboard data."""
        return DashboardData(
            epic_key="PROJ-100",
            epic_title="Sample Epic",
            markdown_path="epic.md",
            stories=[
                StoryStatus(
                    story_id="US-001",
                    title="First Story",
                    jira_key="PROJ-101",
                    status="Done",
                    points=3,
                    subtask_count=2,
                    sync_status="synced",
                ),
                StoryStatus(
                    story_id="US-002",
                    title="Second Story",
                    jira_key="PROJ-102",
                    status="In Progress",
                    points=5,
                    subtask_count=4,
                    sync_status="synced",
                ),
                StoryStatus(
                    story_id="US-003",
                    title="Third Story",
                    status="To Do",
                    points=2,
                    sync_status="pending",
                    has_changes=True,
                ),
            ],
            total_syncs=10,
            successful_syncs=8,
            failed_syncs=2,
            last_sync=datetime.now(),
            last_sync_result="success",
            backup_count=5,
        )

    def test_render_static(self, dashboard, sample_data):
        """Test static render produces output."""
        output = dashboard.render_static(sample_data)

        assert "spectra Dashboard" in output
        assert "PROJ-100" in output
        assert "Sample Epic" in output
        assert "Stories" in output

    def test_render_static_empty_data(self, dashboard):
        """Test static render with empty data."""
        data = DashboardData()
        output = dashboard.render_static(data)

        assert "spectra Dashboard" in output
        assert "No stories loaded" in output

    def test_build_header(self, dashboard, sample_data):
        """Test header building."""
        lines = dashboard._build_header(sample_data)

        assert any("spectra Dashboard" in line for line in lines)
        assert any("PROJ-100" in line for line in lines)
        assert any("epic.md" in line for line in lines)

    def test_build_overview(self, dashboard, sample_data):
        """Test overview building."""
        lines = dashboard._build_overview(sample_data)

        assert any("Overview" in line for line in lines)

    def test_build_stories_summary(self, dashboard, sample_data):
        """Test stories summary building."""
        lines = dashboard._build_stories_summary(sample_data)

        assert any("Stories" in line for line in lines)
        assert any("synced" in line for line in lines)
        assert any("US-001" in line for line in lines)

    def test_build_sync_status(self, dashboard, sample_data):
        """Test sync status building."""
        lines = dashboard._build_sync_status(sample_data)

        assert any("Last Sync" in line for line in lines)
        assert any("Success" in line for line in lines)
        assert any("80%" in line for line in lines)  # 8/10 = 80%

    def test_get_story_status_icon_synced(self, dashboard):
        """Test synced story icon."""
        story = StoryStatus(
            story_id="US-001",
            title="Test",
            sync_status="synced",
        )

        icon = dashboard._get_story_status_icon(story)
        assert "✓" in icon

    def test_get_story_status_icon_error(self, dashboard):
        """Test error story icon."""
        story = StoryStatus(
            story_id="US-001",
            title="Test",
            sync_status="error",
        )

        icon = dashboard._get_story_status_icon(story)
        assert "✗" in icon

    def test_get_story_status_icon_changed(self, dashboard):
        """Test changed story icon."""
        story = StoryStatus(
            story_id="US-001",
            title="Test",
            sync_status="pending",
            has_changes=True,
        )

        icon = dashboard._get_story_status_icon(story)
        assert "↻" in icon

    def test_progress_bar(self, dashboard):
        """Test progress bar generation."""
        bar = dashboard._progress_bar(0.5, 10)

        # Should have some filled and some empty
        assert "#" in bar or "█" in bar
        assert "-" in bar or "░" in bar


# =============================================================================
# Data Loading Tests
# =============================================================================


class TestLoadDashboardData:
    """Tests for load_dashboard_data function."""

    def test_load_empty(self):
        """Test loading with no arguments."""
        data = load_dashboard_data()

        assert data.epic_key == ""
        assert data.markdown_path == ""
        assert data.stories == []

    def test_load_with_keys(self):
        """Test loading with epic key."""
        data = load_dashboard_data(epic_key="PROJ-100")

        assert data.epic_key == "PROJ-100"

    def test_load_with_markdown(self, tmp_path):
        """Test loading with markdown file."""
        md_file = tmp_path / "test.md"
        md_file.write_text(
            """### 📋 US-001: Test Story

| Field | Value |
|-------|-------|
| **Story Points** | 3 |
| **Status** | To Do |

**As a** user
**I want** to test
**So that** it works
""",
            encoding="utf-8",
        )

        data = load_dashboard_data(markdown_path=str(md_file))

        assert data.markdown_path == str(md_file)
        assert len(data.stories) == 1
        assert data.stories[0].story_id == "US-001"
        assert data.stories[0].title == "Test Story"

    def test_load_nonexistent_file(self):
        """Test loading with non-existent file."""
        data = load_dashboard_data(markdown_path="/nonexistent/file.md")

        # Should not crash, just have empty stories
        assert data.stories == []


# =============================================================================
# run_dashboard Tests
# =============================================================================


class TestRunDashboard:
    """Tests for run_dashboard function."""

    def test_run_dashboard_empty(self, capsys):
        """Test running dashboard with no data."""
        console = Console(color=False)

        result = run_dashboard(console)

        assert result == ExitCode.SUCCESS

        captured = capsys.readouterr()
        assert "spectra Dashboard" in captured.out

    def test_run_dashboard_with_markdown(self, tmp_path, capsys):
        """Test running dashboard with markdown file."""
        md_file = tmp_path / "test.md"
        md_file.write_text(
            """### 📋 US-001: Test Story

| **Story Points** | 5 |

Description.
""",
            encoding="utf-8",
        )

        console = Console(color=False)
        result = run_dashboard(console, markdown_path=str(md_file))

        assert result == ExitCode.SUCCESS

        captured = capsys.readouterr()
        assert "US-001" in captured.out


# =============================================================================
# CLI Integration Tests
# =============================================================================


class TestCLIIntegration:
    """Tests for CLI integration."""

    def test_dashboard_flag_in_parser(self, cli_parser):
        """Test --dashboard flag is recognized."""
        args = cli_parser.parse_args(["--dashboard"])

        assert args.dashboard is True

    def test_dashboard_with_markdown(self, cli_parser):
        """Test --dashboard with markdown."""
        args = cli_parser.parse_args(
            [
                "--dashboard",
                "--input",
                "epic.md",
            ]
        )

        assert args.dashboard is True
        assert args.markdown == "epic.md"

    def test_dashboard_with_epic(self, cli_parser):
        """Test --dashboard with epic."""
        args = cli_parser.parse_args(
            [
                "--dashboard",
                "--epic",
                "PROJ-123",
            ]
        )

        assert args.dashboard is True
        assert args.epic == "PROJ-123"

    def test_dashboard_standalone(self, cli_parser):
        """Test --dashboard can be used without other arguments."""
        # Should not raise
        args = cli_parser.parse_args(["--dashboard"])

        assert args.dashboard is True
        assert args.markdown is None
        assert args.epic is None


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    @pytest.fixture
    def console(self):
        return Console(color=False)

    @pytest.fixture
    def dashboard(self, console):
        return Dashboard(console)

    def test_long_story_title_truncation(self, dashboard):
        """Test long story titles are truncated."""
        data = DashboardData(
            stories=[
                StoryStatus(
                    story_id="US-001",
                    title="This is a very long story title that should be truncated in the display",
                    sync_status="synced",
                ),
            ]
        )

        lines = dashboard._build_stories_summary(data)
        output = "\n".join(lines)

        # Should contain truncated title with ...
        assert "..." in output

    def test_no_sync_history(self, dashboard):
        """Test dashboard with no sync history."""
        data = DashboardData(
            total_syncs=0,
            last_sync=None,
        )

        lines = dashboard._build_sync_status(data)
        output = "\n".join(lines)

        assert "No sync history" in output

    def test_all_error_status(self, dashboard):
        """Test dashboard with all error stories."""
        data = DashboardData(
            stories=[
                StoryStatus(story_id="US-001", title="Error 1", sync_status="error"),
                StoryStatus(story_id="US-002", title="Error 2", sync_status="error"),
            ]
        )

        lines = dashboard._build_stories_summary(data)
        output = "\n".join(lines)

        assert "error" in output.lower()

    def test_mixed_status(self, dashboard):
        """Test dashboard with mixed status stories."""
        data = DashboardData(
            stories=[
                StoryStatus(story_id="US-001", title="Synced", sync_status="synced"),
                StoryStatus(story_id="US-002", title="Pending", sync_status="pending"),
                StoryStatus(story_id="US-003", title="Error", sync_status="error"),
            ]
        )

        lines = dashboard._build_stories_summary(data)
        output = "\n".join(lines)

        assert "synced" in output.lower()
        assert "pending" in output.lower()
        assert "error" in output.lower()
