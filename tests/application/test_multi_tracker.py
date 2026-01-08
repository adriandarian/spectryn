"""Tests for multi-tracker sync module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from spectryn.application.sync.multi_tracker import (
    MultiTrackerSyncOrchestrator,
    MultiTrackerSyncResult,
    SyncStrategy,
    TrackerSyncStatus,
    TrackerTarget,
    TrackerType,
)
from spectryn.core.domain.entities import UserStory
from spectryn.core.domain.enums import Priority, Status
from spectryn.core.domain.value_objects import Description, IssueKey, StoryId
from spectryn.core.ports.config_provider import SyncConfig
from spectryn.core.ports.issue_tracker import IssueData


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_tracker():
    """Create a mock issue tracker."""
    tracker = MagicMock()
    tracker.name = "MockTracker"
    tracker.test_connection.return_value = True
    tracker.get_epic_children.return_value = []
    tracker.create_issue.return_value = "MOCK-123"
    return tracker


@pytest.fixture
def mock_parser():
    """Create a mock document parser."""
    parser = MagicMock()
    parser.parse_stories.return_value = [
        UserStory(
            id=StoryId("US-001"),
            title="Test Story",
            status=Status.PLANNED,
            story_points=5,
        ),
    ]
    return parser


@pytest.fixture
def sync_config():
    """Create a default sync config."""
    return SyncConfig(dry_run=True)


@pytest.fixture
def sample_markdown(tmp_path):
    """Create a sample markdown file."""
    content = """\
# 🚀 Test Epic

---

### 🔧 US-001: Test Story

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Status** | 📋 Planned |

#### Description

**As a** user
**I want** to test multi-tracker sync
**So that** I can verify it works

---
"""
    md_file = tmp_path / "EPIC.md"
    md_file.write_text(content, encoding="utf-8")
    return str(md_file)


# =============================================================================
# TrackerType Tests
# =============================================================================


class TestTrackerType:
    """Tests for TrackerType enum."""

    def test_jira_type(self):
        """Test JIRA tracker type."""
        assert TrackerType.JIRA.value == "jira"

    def test_github_type(self):
        """Test GitHub tracker type."""
        assert TrackerType.GITHUB.value == "github"

    def test_all_types_have_values(self):
        """Test all tracker types have string values."""
        for tracker_type in TrackerType:
            assert isinstance(tracker_type.value, str)
            assert len(tracker_type.value) > 0


# =============================================================================
# SyncStrategy Tests
# =============================================================================


class TestSyncStrategy:
    """Tests for SyncStrategy enum."""

    def test_parallel_strategy(self):
        """Test parallel sync strategy."""
        assert SyncStrategy.PARALLEL.value == "parallel"

    def test_sequential_strategy(self):
        """Test sequential sync strategy."""
        assert SyncStrategy.SEQUENTIAL.value == "sequential"

    def test_primary_first_strategy(self):
        """Test primary first sync strategy."""
        assert SyncStrategy.PRIMARY_FIRST.value == "primary_first"


# =============================================================================
# TrackerTarget Tests
# =============================================================================


class TestTrackerTarget:
    """Tests for TrackerTarget dataclass."""

    def test_default_name_from_tracker(self, mock_tracker):
        """Test that name defaults to tracker name."""
        target = TrackerTarget(tracker=mock_tracker, epic_key="PROJ-123")
        assert target.name == "MockTracker"

    def test_custom_name(self, mock_tracker):
        """Test custom name."""
        target = TrackerTarget(tracker=mock_tracker, epic_key="PROJ-123", name="My Tracker")
        assert target.name == "My Tracker"

    def test_is_primary_default(self, mock_tracker):
        """Test is_primary defaults to False."""
        target = TrackerTarget(tracker=mock_tracker, epic_key="PROJ-123")
        assert target.is_primary is False

    def test_enabled_default(self, mock_tracker):
        """Test enabled defaults to True."""
        target = TrackerTarget(tracker=mock_tracker, epic_key="PROJ-123")
        assert target.enabled is True


# =============================================================================
# TrackerSyncStatus Tests
# =============================================================================


class TestTrackerSyncStatus:
    """Tests for TrackerSyncStatus dataclass."""

    def test_default_values(self):
        """Test default values."""
        status = TrackerSyncStatus(tracker_name="Jira", epic_key="PROJ-123")

        assert status.success is True
        assert status.stories_synced == 0
        assert status.errors == []

    def test_add_error(self):
        """Test adding an error sets success to False."""
        status = TrackerSyncStatus(tracker_name="Jira", epic_key="PROJ-123")
        status.add_error("Something went wrong")

        assert status.success is False
        assert "Something went wrong" in status.errors

    def test_add_warning(self):
        """Test adding a warning doesn't affect success."""
        status = TrackerSyncStatus(tracker_name="Jira", epic_key="PROJ-123")
        status.add_warning("Minor issue")

        assert status.success is True
        assert "Minor issue" in status.warnings

    def test_complete(self):
        """Test marking status as complete."""
        status = TrackerSyncStatus(tracker_name="Jira", epic_key="PROJ-123")
        assert status.completed_at == ""

        status.complete()
        assert status.completed_at != ""

    def test_summary(self):
        """Test summary generation."""
        status = TrackerSyncStatus(
            tracker_name="Jira",
            epic_key="PROJ-123",
            stories_synced=5,
            stories_skipped=2,
        )

        summary = status.summary
        assert "✓" in summary  # Success indicator
        assert "Jira" in summary
        assert "5" in summary  # synced


# =============================================================================
# MultiTrackerSyncResult Tests
# =============================================================================


class TestMultiTrackerSyncResult:
    """Tests for MultiTrackerSyncResult dataclass."""

    def test_default_values(self):
        """Test default values."""
        result = MultiTrackerSyncResult()

        assert result.dry_run is True
        assert result.total_trackers == 0
        assert result.successful_trackers == 0
        assert result.failed_trackers == 0

    def test_success_when_no_failures(self):
        """Test success when all trackers succeed."""
        result = MultiTrackerSyncResult()
        result.add_tracker_status(TrackerSyncStatus(tracker_name="Jira", epic_key="PROJ-123"))

        assert result.success is True

    def test_failure_when_tracker_fails(self):
        """Test failure when any tracker fails."""
        result = MultiTrackerSyncResult()

        failed_status = TrackerSyncStatus(tracker_name="Jira", epic_key="PROJ-123")
        failed_status.add_error("Failed")

        result.add_tracker_status(failed_status)

        assert result.success is False

    def test_partial_success(self):
        """Test partial success."""
        result = MultiTrackerSyncResult()

        # One success
        result.add_tracker_status(TrackerSyncStatus(tracker_name="Jira", epic_key="PROJ-123"))

        # One failure
        failed_status = TrackerSyncStatus(tracker_name="GitHub", epic_key="1")
        failed_status.add_error("Failed")
        result.add_tracker_status(failed_status)

        assert result.success is False
        assert result.partial_success is True
        assert result.successful_trackers == 1
        assert result.failed_trackers == 1

    def test_cross_tracker_mappings(self):
        """Test cross-tracker key mappings."""
        result = MultiTrackerSyncResult()

        status1 = TrackerSyncStatus(tracker_name="Jira", epic_key="PROJ-123")
        status1.key_mappings = {"US-001": "PROJ-101"}
        result.add_tracker_status(status1)

        status2 = TrackerSyncStatus(tracker_name="GitHub", epic_key="1")
        status2.key_mappings = {"US-001": "#42"}
        result.add_tracker_status(status2)

        assert "US-001" in result.cross_tracker_mappings
        assert result.cross_tracker_mappings["US-001"]["Jira"] == "PROJ-101"
        assert result.cross_tracker_mappings["US-001"]["GitHub"] == "#42"

    def test_summary_generation(self):
        """Test summary generation."""
        result = MultiTrackerSyncResult()
        result.add_tracker_status(TrackerSyncStatus(tracker_name="Jira", epic_key="PROJ-123"))

        summary = result.summary()
        assert "Multi-Tracker Sync Results" in summary
        assert "Jira" in summary

    def test_to_dict(self):
        """Test conversion to dictionary."""
        result = MultiTrackerSyncResult()
        result.add_tracker_status(TrackerSyncStatus(tracker_name="Jira", epic_key="PROJ-123"))

        d = result.to_dict()
        assert "total_trackers" in d
        assert "tracker_statuses" in d
        assert d["total_trackers"] == 1


# =============================================================================
# MultiTrackerSyncOrchestrator Tests
# =============================================================================


class TestMultiTrackerSyncOrchestrator:
    """Tests for MultiTrackerSyncOrchestrator."""

    def test_init(self, mock_parser, sync_config):
        """Test orchestrator initialization."""
        orchestrator = MultiTrackerSyncOrchestrator(
            parser=mock_parser,
            config=sync_config,
        )

        assert orchestrator.parser == mock_parser
        assert orchestrator.config == sync_config
        assert len(orchestrator.targets) == 0

    def test_add_target(self, mock_parser, sync_config, mock_tracker):
        """Test adding a target."""
        orchestrator = MultiTrackerSyncOrchestrator(
            parser=mock_parser,
            config=sync_config,
        )

        target = TrackerTarget(tracker=mock_tracker, epic_key="PROJ-123")
        orchestrator.add_target(target)

        assert len(orchestrator.targets) == 1
        assert orchestrator.targets[0] == target

    def test_remove_target(self, mock_parser, sync_config, mock_tracker):
        """Test removing a target."""
        orchestrator = MultiTrackerSyncOrchestrator(
            parser=mock_parser,
            config=sync_config,
        )

        target = TrackerTarget(tracker=mock_tracker, epic_key="PROJ-123", name="Test")
        orchestrator.add_target(target)

        result = orchestrator.remove_target("Test")
        assert result is True
        assert len(orchestrator.targets) == 0

        result = orchestrator.remove_target("NonExistent")
        assert result is False

    def test_primary_target(self, mock_parser, sync_config, mock_tracker):
        """Test getting primary target."""
        orchestrator = MultiTrackerSyncOrchestrator(
            parser=mock_parser,
            config=sync_config,
        )

        # No targets
        assert orchestrator.primary_target is None

        # Add non-primary
        target1 = TrackerTarget(tracker=mock_tracker, epic_key="PROJ-123", name="Secondary")
        orchestrator.add_target(target1)

        # First target becomes primary by default
        assert orchestrator.primary_target == target1

        # Add primary
        target2 = TrackerTarget(
            tracker=mock_tracker, epic_key="PROJ-456", name="Primary", is_primary=True
        )
        orchestrator.add_target(target2)

        assert orchestrator.primary_target == target2

    def test_sync_no_targets(self, mock_parser, sync_config, sample_markdown):
        """Test sync with no targets."""
        orchestrator = MultiTrackerSyncOrchestrator(
            parser=mock_parser,
            config=sync_config,
        )

        result = orchestrator.sync(sample_markdown)

        assert result.total_trackers == 0

    def test_sync_with_tracker(self, mock_parser, sync_config, mock_tracker, sample_markdown):
        """Test sync with a tracker."""
        orchestrator = MultiTrackerSyncOrchestrator(
            parser=mock_parser,
            config=sync_config,
        )

        target = TrackerTarget(tracker=mock_tracker, epic_key="PROJ-123")
        orchestrator.add_target(target)

        result = orchestrator.sync(sample_markdown)

        assert result.total_trackers == 1
        mock_tracker.test_connection.assert_called()

    def test_sync_file_not_found(self, mock_parser, sync_config, mock_tracker):
        """Test sync with non-existent file."""
        orchestrator = MultiTrackerSyncOrchestrator(
            parser=mock_parser,
            config=sync_config,
        )

        target = TrackerTarget(tracker=mock_tracker, epic_key="PROJ-123")
        orchestrator.add_target(target)

        # Mock parser to raise error
        mock_parser.parse_stories.side_effect = FileNotFoundError("Not found")

        result = orchestrator.sync("/nonexistent/file.md")

        assert result.total_trackers == 1
        assert result.failed_trackers == 1

    def test_sync_connection_failure(self, mock_parser, sync_config, mock_tracker, sample_markdown):
        """Test sync when connection fails."""
        mock_tracker.test_connection.return_value = False

        orchestrator = MultiTrackerSyncOrchestrator(
            parser=mock_parser,
            config=sync_config,
        )

        target = TrackerTarget(tracker=mock_tracker, epic_key="PROJ-123")
        orchestrator.add_target(target)

        result = orchestrator.sync(sample_markdown)

        assert result.failed_trackers == 1
        assert any("connect" in e.lower() for s in result.tracker_statuses for e in s.errors)

    def test_preview_mode(self, mock_parser, sync_config, mock_tracker, sample_markdown):
        """Test preview mode forces dry run."""
        sync_config.dry_run = False

        orchestrator = MultiTrackerSyncOrchestrator(
            parser=mock_parser,
            config=sync_config,
        )

        target = TrackerTarget(tracker=mock_tracker, epic_key="PROJ-123")
        orchestrator.add_target(target)

        result = orchestrator.preview(sample_markdown)

        assert result.dry_run is True
        # Config should be restored
        assert sync_config.dry_run is False

    def test_disabled_target_skipped(self, mock_parser, sync_config, mock_tracker, sample_markdown):
        """Test that disabled targets are skipped."""
        orchestrator = MultiTrackerSyncOrchestrator(
            parser=mock_parser,
            config=sync_config,
        )

        target = TrackerTarget(tracker=mock_tracker, epic_key="PROJ-123", enabled=False)
        orchestrator.add_target(target)

        result = orchestrator.sync(sample_markdown)

        assert result.total_trackers == 0
        mock_tracker.test_connection.assert_not_called()


# =============================================================================
# Integration Tests
# =============================================================================


class TestMultiTrackerIntegration:
    """Integration tests for multi-tracker sync."""

    def test_sync_to_multiple_trackers(self, mock_parser, sync_config, sample_markdown):
        """Test syncing to multiple trackers."""
        # Create two mock trackers
        tracker1 = MagicMock()
        tracker1.name = "Jira"
        tracker1.test_connection.return_value = True
        tracker1.get_epic_children.return_value = []

        tracker2 = MagicMock()
        tracker2.name = "GitHub"
        tracker2.test_connection.return_value = True
        tracker2.get_epic_children.return_value = []

        orchestrator = MultiTrackerSyncOrchestrator(
            parser=mock_parser,
            config=sync_config,
        )

        orchestrator.add_target(
            TrackerTarget(tracker=tracker1, epic_key="PROJ-123", is_primary=True)
        )
        orchestrator.add_target(TrackerTarget(tracker=tracker2, epic_key="1"))

        result = orchestrator.sync(sample_markdown)

        assert result.total_trackers == 2
        assert result.successful_trackers == 2
        tracker1.test_connection.assert_called()
        tracker2.test_connection.assert_called()

    def test_primary_first_strategy(self, mock_parser, sample_markdown):
        """Test primary-first sync strategy."""
        config = SyncConfig(dry_run=True)

        tracker1 = MagicMock()
        tracker1.name = "Primary"
        tracker1.test_connection.return_value = True
        tracker1.get_epic_children.return_value = []

        tracker2 = MagicMock()
        tracker2.name = "Secondary"
        tracker2.test_connection.return_value = True
        tracker2.get_epic_children.return_value = []

        orchestrator = MultiTrackerSyncOrchestrator(
            parser=mock_parser,
            config=config,
            strategy=SyncStrategy.PRIMARY_FIRST,
        )

        orchestrator.add_target(TrackerTarget(tracker=tracker2, epic_key="2", name="Secondary"))
        orchestrator.add_target(
            TrackerTarget(tracker=tracker1, epic_key="1", name="Primary", is_primary=True)
        )

        result = orchestrator.sync(sample_markdown)

        assert result.total_trackers == 2
        # Primary should be first in results
        assert result.tracker_statuses[0].tracker_name == "Primary"
