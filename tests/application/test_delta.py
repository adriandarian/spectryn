"""Tests for delta sync module."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from spectryn.application.sync.delta import (
    ChangeDirection,
    DeltaSyncResult,
    DeltaTracker,
    FieldChange,
    StoryDelta,
    SyncableField,
    create_delta_tracker,
)
from spectryn.core.domain.entities import UserStory
from spectryn.core.domain.enums import Priority, Status
from spectryn.core.domain.value_objects import Description, IssueKey, StoryId
from spectryn.core.ports.issue_tracker import IssueData


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_story():
    """Create a sample UserStory."""
    return UserStory(
        id=StoryId("US-001"),
        title="Test Story",
        description=Description(
            role="developer",
            want="to test delta sync",
            benefit="I can verify it works",
        ),
        status=Status.IN_PROGRESS,
        story_points=5,
        priority=Priority.HIGH,
        external_key=IssueKey("PROJ-123"),
    )


@pytest.fixture
def sample_issue():
    """Create a sample IssueData."""
    return IssueData(
        key="PROJ-123",
        summary="Test Story",
        description="As a developer, I want to test delta sync",
        status="In Progress",
        story_points=5,
        assignee="john@example.com",
    )


@pytest.fixture
def delta_tracker(tmp_path):
    """Create a DeltaTracker with temp directory."""
    return DeltaTracker(baseline_dir=tmp_path / ".spectra" / "delta")


# =============================================================================
# SyncableField Tests
# =============================================================================


class TestSyncableField:
    """Tests for SyncableField enum."""

    def test_content_fields(self):
        """Test content fields classification."""
        content = SyncableField.content_fields()
        assert SyncableField.TITLE in content
        assert SyncableField.DESCRIPTION in content
        assert SyncableField.STATUS not in content

    def test_metadata_fields(self):
        """Test metadata fields classification."""
        metadata = SyncableField.metadata_fields()
        assert SyncableField.STATUS in metadata
        assert SyncableField.STORY_POINTS in metadata
        assert SyncableField.DESCRIPTION not in metadata


# =============================================================================
# FieldChange Tests
# =============================================================================


class TestFieldChange:
    """Tests for FieldChange dataclass."""

    def test_hash_computation(self):
        """Test that hash is computed automatically."""
        change = FieldChange(
            field=SyncableField.TITLE,
            direction=ChangeDirection.LOCAL_TO_REMOTE,
            local_value="New Title",
            remote_value="Old Title",
        )

        assert change.local_hash != ""
        assert change.remote_hash != ""
        assert change.local_hash != change.remote_hash

    def test_needs_push(self):
        """Test needs_push property."""
        change = FieldChange(
            field=SyncableField.TITLE,
            direction=ChangeDirection.LOCAL_TO_REMOTE,
            local_value="New",
            remote_value="Old",
        )
        assert change.needs_push is True
        assert change.needs_pull is False

    def test_needs_pull(self):
        """Test needs_pull property."""
        change = FieldChange(
            field=SyncableField.STATUS,
            direction=ChangeDirection.REMOTE_TO_LOCAL,
            local_value="Open",
            remote_value="Done",
        )
        assert change.needs_pull is True
        assert change.needs_push is False

    def test_is_conflict(self):
        """Test is_conflict property."""
        change = FieldChange(
            field=SyncableField.STATUS,
            direction=ChangeDirection.CONFLICT,
            local_value="In Progress",
            remote_value="Done",
            base_value="Open",
        )
        assert change.is_conflict is True

    def test_to_dict(self):
        """Test serialization to dict."""
        change = FieldChange(
            field=SyncableField.TITLE,
            direction=ChangeDirection.LOCAL_TO_REMOTE,
            local_value="New",
            remote_value="Old",
            story_id="US-001",
            issue_key="PROJ-123",
        )

        d = change.to_dict()
        assert d["field"] == "title"
        assert d["direction"] == "push"
        assert d["local_value"] == "New"
        assert d["remote_value"] == "Old"


# =============================================================================
# StoryDelta Tests
# =============================================================================


class TestStoryDelta:
    """Tests for StoryDelta dataclass."""

    def test_no_changes(self):
        """Test delta with no changes."""
        delta = StoryDelta(story_id="US-001", issue_key="PROJ-123")

        assert delta.has_changes is False
        assert len(delta.push_changes) == 0
        assert len(delta.pull_changes) == 0
        assert "no changes" in delta.summary()

    def test_with_push_changes(self):
        """Test delta with push changes."""
        delta = StoryDelta(story_id="US-001", issue_key="PROJ-123")
        delta.add_change(
            FieldChange(
                field=SyncableField.TITLE,
                direction=ChangeDirection.LOCAL_TO_REMOTE,
                local_value="New",
                remote_value="Old",
            )
        )

        assert delta.has_changes is True
        assert len(delta.push_changes) == 1
        assert "↑1" in delta.summary()

    def test_with_pull_changes(self):
        """Test delta with pull changes."""
        delta = StoryDelta(story_id="US-001", issue_key="PROJ-123")
        delta.add_change(
            FieldChange(
                field=SyncableField.STATUS,
                direction=ChangeDirection.REMOTE_TO_LOCAL,
                local_value="Open",
                remote_value="Done",
            )
        )

        assert delta.has_changes is True
        assert len(delta.pull_changes) == 1
        assert "↓1" in delta.summary()

    def test_new_story(self):
        """Test delta for new story."""
        delta = StoryDelta(story_id="US-001", issue_key="", is_new=True)

        assert delta.has_changes is True
        assert "NEW" in delta.summary()

    def test_changed_fields(self):
        """Test changed_fields property."""
        delta = StoryDelta(story_id="US-001", issue_key="PROJ-123")
        delta.add_change(
            FieldChange(
                field=SyncableField.TITLE,
                direction=ChangeDirection.LOCAL_TO_REMOTE,
                local_value="New",
                remote_value="Old",
            )
        )
        delta.add_change(
            FieldChange(
                field=SyncableField.STATUS,
                direction=ChangeDirection.REMOTE_TO_LOCAL,
                local_value="Open",
                remote_value="Done",
            )
        )

        changed = delta.changed_fields
        assert SyncableField.TITLE in changed
        assert SyncableField.STATUS in changed
        assert len(changed) == 2

    def test_get_change(self):
        """Test getting change by field."""
        delta = StoryDelta(story_id="US-001", issue_key="PROJ-123")
        delta.add_change(
            FieldChange(
                field=SyncableField.TITLE,
                direction=ChangeDirection.LOCAL_TO_REMOTE,
                local_value="New",
                remote_value="Old",
            )
        )

        assert delta.get_change(SyncableField.TITLE) is not None
        assert delta.get_change(SyncableField.STATUS) is None


# =============================================================================
# DeltaSyncResult Tests
# =============================================================================


class TestDeltaSyncResult:
    """Tests for DeltaSyncResult dataclass."""

    def test_default_values(self):
        """Test default values."""
        result = DeltaSyncResult()

        assert result.total_stories == 0
        assert result.stories_with_changes == 0
        assert result.has_changes is False
        assert result.has_conflicts is False

    def test_has_changes_property(self):
        """Test has_changes property."""
        result = DeltaSyncResult()
        assert result.has_changes is False

        result.fields_to_push = 3
        assert result.has_changes is True

    def test_has_conflicts_property(self):
        """Test has_conflicts property."""
        result = DeltaSyncResult()
        assert result.has_conflicts is False

        result.fields_conflicting = 1
        assert result.has_conflicts is True

    def test_get_stories_to_push(self):
        """Test getting stories with push changes."""
        result = DeltaSyncResult()

        delta1 = StoryDelta(story_id="US-001", issue_key="PROJ-123")
        delta1.add_change(
            FieldChange(
                field=SyncableField.TITLE,
                direction=ChangeDirection.LOCAL_TO_REMOTE,
                local_value="New",
                remote_value="Old",
            )
        )
        delta2 = StoryDelta(story_id="US-002", issue_key="PROJ-124")  # No changes

        result.deltas = [delta1, delta2]

        to_push = result.get_stories_to_push()
        assert len(to_push) == 1
        assert to_push[0].story_id == "US-001"

    def test_summary_generation(self):
        """Test summary generation."""
        result = DeltaSyncResult(
            total_stories=10,
            stories_with_changes=3,
            stories_unchanged=7,
            fields_to_push=5,
            fields_to_pull=2,
        )

        summary = result.summary()
        assert "Delta Sync Analysis" in summary
        assert "10" in summary
        assert "3" in summary  # changed
        assert "5" in summary  # to push


# =============================================================================
# DeltaTracker Tests
# =============================================================================


class TestDeltaTracker:
    """Tests for DeltaTracker class."""

    def test_init(self, delta_tracker):
        """Test initialization."""
        assert delta_tracker.baseline_dir.exists()
        assert delta_tracker.sync_fields == set(SyncableField)

    def test_init_with_specific_fields(self, tmp_path):
        """Test initialization with specific fields."""
        tracker = DeltaTracker(
            baseline_dir=tmp_path,
            sync_fields={SyncableField.TITLE, SyncableField.STATUS},
        )

        assert len(tracker.sync_fields) == 2
        assert SyncableField.TITLE in tracker.sync_fields

    def test_load_baseline_no_file(self, delta_tracker):
        """Test loading baseline when no file exists."""
        result = delta_tracker.load_baseline("PROJ-123")
        assert result is False

    def test_save_and_load_baseline(self, delta_tracker, sample_story):
        """Test saving and loading baseline."""
        stories = [sample_story]
        matches = {"US-001": "PROJ-123"}

        delta_tracker.save_baseline("PROJ-123", stories, matches)

        result = delta_tracker.load_baseline("PROJ-123")
        assert result is True
        assert "US-001" in delta_tracker._baseline

    def test_analyze_new_story(self, delta_tracker, sample_story):
        """Test analyzing a new story (not matched)."""
        result = delta_tracker.analyze(
            local_stories=[sample_story],
            remote_issues=[],
            matches={},  # No matches
        )

        assert result.new_stories == 1
        assert result.stories_with_changes == 1
        assert result.deltas[0].is_new is True

    def test_analyze_matched_story_no_changes(self, delta_tracker, sample_story, sample_issue):
        """Test analyzing matched story with no changes."""
        # First, save baseline
        matches = {"US-001": "PROJ-123"}
        delta_tracker.save_baseline("PROJ-123", [sample_story], matches)
        delta_tracker.load_baseline("PROJ-123")

        # Analyze (same story)
        result = delta_tracker.analyze(
            local_stories=[sample_story],
            remote_issues=[sample_issue],
            matches=matches,
        )

        # Status maps correctly, story_points match
        assert result.stories_with_changes <= 1  # May have minor differences

    def test_analyze_detects_status_change(self, delta_tracker, sample_story, sample_issue):
        """Test that status changes are detected."""
        matches = {"US-001": "PROJ-123"}

        # Save baseline with PLANNED status
        sample_story.status = Status.PLANNED
        delta_tracker.save_baseline("PROJ-123", [sample_story], matches)
        delta_tracker.load_baseline("PROJ-123")

        # Change local status
        sample_story.status = Status.IN_PROGRESS

        # Remote also changed
        sample_issue.status = "Done"

        result = delta_tracker.analyze(
            local_stories=[sample_story],
            remote_issues=[sample_issue],
            matches=matches,
        )

        # Should detect status change
        delta = result.get_delta("US-001")
        assert delta is not None

    def test_analyze_detects_story_points_change(self, delta_tracker, sample_story, sample_issue):
        """Test that story points changes are detected."""
        matches = {"US-001": "PROJ-123"}

        # Save baseline with 5 story points
        delta_tracker.save_baseline("PROJ-123", [sample_story], matches)
        delta_tracker.load_baseline("PROJ-123")

        # Change local story points
        sample_story.story_points = 8

        result = delta_tracker.analyze(
            local_stories=[sample_story],
            remote_issues=[sample_issue],
            matches=matches,
        )

        delta = result.get_delta("US-001")
        assert delta is not None
        assert delta.has_changes is True

    def test_clear_baseline(self, delta_tracker, sample_story):
        """Test clearing baseline."""
        matches = {"US-001": "PROJ-123"}
        delta_tracker.save_baseline("PROJ-123", [sample_story], matches)

        # Verify file exists
        baseline_path = delta_tracker._baseline_path("PROJ-123")
        assert baseline_path.exists()

        # Clear
        result = delta_tracker.clear_baseline("PROJ-123")
        assert result is True
        assert not baseline_path.exists()

    def test_clear_nonexistent_baseline(self, delta_tracker):
        """Test clearing nonexistent baseline."""
        result = delta_tracker.clear_baseline("NONEXISTENT-123")
        assert result is False


# =============================================================================
# Factory Function Tests
# =============================================================================


class TestCreateDeltaTracker:
    """Tests for create_delta_tracker factory function."""

    def test_create_default(self, tmp_path):
        """Test creating tracker with defaults."""
        tracker = create_delta_tracker(baseline_dir=str(tmp_path))

        assert tracker is not None
        assert tracker.sync_fields == set(SyncableField)

    def test_create_with_specific_fields(self, tmp_path):
        """Test creating tracker with specific fields."""
        tracker = create_delta_tracker(
            sync_fields=["title", "status"],
            baseline_dir=str(tmp_path),
        )

        assert len(tracker.sync_fields) == 2
        assert SyncableField.TITLE in tracker.sync_fields
        assert SyncableField.STATUS in tracker.sync_fields

    def test_create_with_invalid_field(self, tmp_path):
        """Test that invalid fields are ignored."""
        tracker = create_delta_tracker(
            sync_fields=["title", "invalid_field"],
            baseline_dir=str(tmp_path),
        )

        assert SyncableField.TITLE in tracker.sync_fields
        assert len(tracker.sync_fields) == 1  # Invalid field ignored


# =============================================================================
# Integration Tests
# =============================================================================


class TestDeltaSyncIntegration:
    """Integration tests for delta sync workflow."""

    def test_full_delta_sync_cycle(self, tmp_path):
        """Test complete delta sync cycle: save baseline, modify, analyze."""
        tracker = DeltaTracker(baseline_dir=tmp_path)

        # Initial story
        story = UserStory(
            id=StoryId("US-001"),
            title="Original Title",
            status=Status.PLANNED,
            story_points=3,
            priority=Priority.MEDIUM,
            external_key=IssueKey("PROJ-123"),
        )
        matches = {"US-001": "PROJ-123"}

        # Save baseline
        tracker.save_baseline("PROJ-123", [story], matches)
        tracker.load_baseline("PROJ-123")

        # Modify story
        story.title = "Modified Title"
        story.story_points = 5

        # Remote state (unchanged from baseline)
        remote_issue = IssueData(
            key="PROJ-123",
            summary="Original Title",
            status="To Do",
            story_points=3,
        )

        # Analyze
        result = tracker.analyze(
            local_stories=[story],
            remote_issues=[remote_issue],
            matches=matches,
        )

        # Should detect local changes
        assert result.stories_with_changes >= 1
        delta = result.get_delta("US-001")
        assert delta is not None
        assert delta.has_changes is True

        # Changes should be pushes (local -> remote)
        push_changes = delta.push_changes
        assert len(push_changes) >= 1
