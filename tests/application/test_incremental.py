"""
Tests for incremental sync functionality.

Tests change detection, fingerprinting, and incremental sync operations.
"""

import tempfile
from pathlib import Path

import pytest

from spectryn.application.sync.incremental import (
    ChangeDetectionResult,
    ChangeTracker,
    IncrementalSyncStats,
    StoryFingerprint,
    compute_story_hash,
    stories_differ,
)
from spectryn.core.domain.entities import Subtask, UserStory
from spectryn.core.domain.enums import Priority, Status
from spectryn.core.domain.value_objects import Description, StoryId


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_story():
    """Create a sample story for testing."""
    desc_text = """**As a** user
**I want** to test features
**So that** I can verify functionality"""
    return UserStory(
        id=StoryId("US-001"),
        title="Test Story",
        description=Description.from_markdown(desc_text),
        status=Status.PLANNED,
        priority=Priority.MEDIUM,
        story_points=5,
        subtasks=[
            Subtask(name="Subtask 1", description="First subtask", story_points=2),
            Subtask(name="Subtask 2", description="Second subtask", story_points=3),
        ],
    )


@pytest.fixture
def modified_story():
    """Create a modified version of the sample story."""
    desc_text = """**As a** user
**I want** to test UPDATED features
**So that** I can verify new functionality"""
    return UserStory(
        id=StoryId("US-001"),
        title="Test Story",
        description=Description.from_markdown(desc_text),  # Changed
        status=Status.PLANNED,
        priority=Priority.MEDIUM,
        story_points=5,
        subtasks=[
            Subtask(name="Subtask 1", description="First subtask", story_points=2),
            Subtask(name="Subtask 2", description="Second subtask", story_points=3),
        ],
    )


@pytest.fixture
def story_with_new_subtask():
    """Story with an added subtask."""
    desc_text = """**As a** user
**I want** to test features
**So that** I can verify functionality"""
    return UserStory(
        id=StoryId("US-001"),
        title="Test Story",
        description=Description.from_markdown(desc_text),
        status=Status.PLANNED,
        priority=Priority.MEDIUM,
        story_points=5,
        subtasks=[
            Subtask(name="Subtask 1", description="First subtask", story_points=2),
            Subtask(name="Subtask 2", description="Second subtask", story_points=3),
            Subtask(name="Subtask 3", description="New subtask", story_points=1),  # Added
        ],
    )


@pytest.fixture
def temp_storage_dir():
    """Create a temporary directory for change tracker storage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


# =============================================================================
# StoryFingerprint Tests
# =============================================================================


class TestStoryFingerprint:
    """Tests for StoryFingerprint class."""

    def test_create_from_story(self, sample_story):
        """Test creating fingerprint from story."""
        fp = StoryFingerprint.from_story(sample_story)

        assert fp.story_id == "US-001"
        assert fp.content_hash  # Non-empty hash
        assert fp.metadata_hash  # Non-empty hash
        assert len(fp.subtask_hashes) == 2
        assert fp.created_at  # Timestamp set

    def test_same_story_same_fingerprint(self, sample_story):
        """Same story should produce same fingerprint."""
        fp1 = StoryFingerprint.from_story(sample_story)
        fp2 = StoryFingerprint.from_story(sample_story)

        assert fp1.content_hash == fp2.content_hash
        assert fp1.metadata_hash == fp2.metadata_hash
        assert fp1.subtask_hashes == fp2.subtask_hashes

    def test_modified_description_different_hash(self, sample_story, modified_story):
        """Modified description should produce different content hash."""
        fp1 = StoryFingerprint.from_story(sample_story)
        fp2 = StoryFingerprint.from_story(modified_story)

        assert fp1.content_hash != fp2.content_hash
        assert fp1.content_changed(fp2) is True

    def test_content_changed_detection(self, sample_story, modified_story):
        """Test content change detection."""
        fp1 = StoryFingerprint.from_story(sample_story)
        fp2 = StoryFingerprint.from_story(modified_story)

        assert fp1.content_changed(fp2)
        assert fp1.has_any_changes(fp2)

    def test_subtask_change_detection(self, sample_story, story_with_new_subtask):
        """Test subtask change detection."""
        fp1 = StoryFingerprint.from_story(sample_story)
        fp2 = StoryFingerprint.from_story(story_with_new_subtask)

        # fp2 has a new subtask compared to fp1
        # get_changed_subtasks(other) compares self to other
        # added = in self but not in other
        # removed = in other but not in self
        added, removed, modified = fp2.get_changed_subtasks(fp1)

        assert len(added) == 1  # fp2 has Subtask 3 which fp1 doesn't
        assert len(removed) == 0  # fp1's subtasks are all in fp2
        assert len(modified) == 0  # Common subtasks are unchanged

    def test_no_changes_same_story(self, sample_story):
        """Identical stories should show no changes."""
        fp1 = StoryFingerprint.from_story(sample_story)
        fp2 = StoryFingerprint.from_story(sample_story)

        assert not fp1.has_any_changes(fp2)
        assert not fp1.content_changed(fp2)
        assert not fp1.metadata_changed(fp2)

    def test_serialization(self, sample_story):
        """Test fingerprint serialization/deserialization."""
        fp = StoryFingerprint.from_story(sample_story)

        data = fp.to_dict()
        fp2 = StoryFingerprint.from_dict(data)

        assert fp.story_id == fp2.story_id
        assert fp.content_hash == fp2.content_hash
        assert fp.metadata_hash == fp2.metadata_hash
        assert fp.subtask_hashes == fp2.subtask_hashes

    def test_status_change_affects_metadata(self, sample_story):
        """Changing status should affect metadata hash."""
        desc_text = """**As a** user
**I want** to test features
**So that** I can verify functionality"""
        modified = UserStory(
            id=StoryId("US-001"),
            title="Test Story",
            description=Description.from_markdown(desc_text),
            status=Status.DONE,  # Changed
            priority=Priority.MEDIUM,
            story_points=5,
        )

        fp1 = StoryFingerprint.from_story(sample_story)
        fp2 = StoryFingerprint.from_story(modified)

        assert fp1.metadata_changed(fp2)


# =============================================================================
# ChangeTracker Tests
# =============================================================================


class TestChangeTracker:
    """Tests for ChangeTracker class."""

    def test_init_creates_directory(self, temp_storage_dir):
        """Tracker should create storage directory if needed."""
        subdir = Path(temp_storage_dir) / "nested" / "dir"
        ChangeTracker(storage_dir=str(subdir))

        assert subdir.exists()

    def test_load_no_previous_state(self, temp_storage_dir):
        """Load should return False when no previous state exists."""
        tracker = ChangeTracker(storage_dir=temp_storage_dir)

        result = tracker.load("EPIC-123", "/path/to/doc.md")

        assert result is False
        assert not tracker.has_previous_state

    def test_save_and_load(self, temp_storage_dir, sample_story):
        """Test saving and loading state."""
        tracker = ChangeTracker(storage_dir=temp_storage_dir)

        # Detect changes (populates current fingerprints)
        tracker.detect_changes([sample_story])

        # Save state
        tracker.save("EPIC-123", "/path/to/doc.md")

        # Create new tracker and load
        tracker2 = ChangeTracker(storage_dir=temp_storage_dir)
        result = tracker2.load("EPIC-123", "/path/to/doc.md")

        assert result is True
        assert tracker2.has_previous_state
        assert tracker2.previous_story_count == 1

    def test_detect_new_stories(self, temp_storage_dir, sample_story):
        """New stories should be detected as changed."""
        tracker = ChangeTracker(storage_dir=temp_storage_dir)
        tracker.load("EPIC-123", "/path/to/doc.md")  # No previous state

        changes = tracker.detect_changes([sample_story])

        assert "US-001" in changes
        assert changes["US-001"].is_new
        assert changes["US-001"].has_changes

    def test_detect_unchanged_stories(self, temp_storage_dir, sample_story):
        """Unchanged stories should not be marked as changed."""
        tracker = ChangeTracker(storage_dir=temp_storage_dir)

        # First sync
        tracker.detect_changes([sample_story])
        tracker.save("EPIC-123", "/path/to/doc.md")

        # Second sync with same story
        tracker2 = ChangeTracker(storage_dir=temp_storage_dir)
        tracker2.load("EPIC-123", "/path/to/doc.md")

        changes = tracker2.detect_changes([sample_story])

        assert "US-001" in changes
        assert not changes["US-001"].has_changes
        assert not changes["US-001"].is_new

    def test_detect_modified_stories(self, temp_storage_dir, sample_story, modified_story):
        """Modified stories should be detected as changed."""
        tracker = ChangeTracker(storage_dir=temp_storage_dir)

        # First sync with original
        tracker.detect_changes([sample_story])
        tracker.save("EPIC-123", "/path/to/doc.md")

        # Second sync with modified story
        tracker2 = ChangeTracker(storage_dir=temp_storage_dir)
        tracker2.load("EPIC-123", "/path/to/doc.md")

        changes = tracker2.detect_changes([modified_story])

        assert "US-001" in changes
        assert changes["US-001"].has_changes
        assert changes["US-001"].description_changed

    def test_detect_subtask_changes(self, temp_storage_dir, sample_story, story_with_new_subtask):
        """Subtask changes should be detected."""
        tracker = ChangeTracker(storage_dir=temp_storage_dir)

        # First sync
        tracker.detect_changes([sample_story])
        tracker.save("EPIC-123", "/path/to/doc.md")

        # Second sync with new subtask
        tracker2 = ChangeTracker(storage_dir=temp_storage_dir)
        tracker2.load("EPIC-123", "/path/to/doc.md")

        changes = tracker2.detect_changes([story_with_new_subtask])

        assert "US-001" in changes
        assert changes["US-001"].has_changes
        assert changes["US-001"].subtasks_changed

    def test_get_changed_story_ids(self, temp_storage_dir, sample_story, modified_story):
        """Test convenience method for getting changed story IDs."""
        tracker = ChangeTracker(storage_dir=temp_storage_dir)

        # First sync
        tracker.detect_changes([sample_story])
        tracker.save("EPIC-123", "/path/to/doc.md")

        # Second sync - story 1 modified, story 2 new
        story2 = UserStory(id=StoryId("US-002"), title="New Story")

        tracker2 = ChangeTracker(storage_dir=temp_storage_dir)
        tracker2.load("EPIC-123", "/path/to/doc.md")

        changed_ids = tracker2.get_changed_story_ids([modified_story, story2])

        assert "US-001" in changed_ids  # Modified
        assert "US-002" in changed_ids  # New

    def test_clear_state(self, temp_storage_dir, sample_story):
        """Test clearing saved state."""
        tracker = ChangeTracker(storage_dir=temp_storage_dir)

        # Save state
        tracker.detect_changes([sample_story])
        tracker.save("EPIC-123", "/path/to/doc.md")

        # Clear
        result = tracker.clear("EPIC-123", "/path/to/doc.md")
        assert result is True

        # Should not load anymore
        tracker2 = ChangeTracker(storage_dir=temp_storage_dir)
        assert tracker2.load("EPIC-123", "/path/to/doc.md") is False

    def test_different_epics_separate_state(self, temp_storage_dir, sample_story):
        """Different epics should have separate state files."""
        tracker = ChangeTracker(storage_dir=temp_storage_dir)

        # Save for EPIC-123
        tracker.detect_changes([sample_story])
        tracker.save("EPIC-123", "/path/to/doc.md")

        # Load for EPIC-456 should not find state
        tracker2 = ChangeTracker(storage_dir=temp_storage_dir)
        assert tracker2.load("EPIC-456", "/path/to/doc.md") is False


# =============================================================================
# ChangeDetectionResult Tests
# =============================================================================


class TestChangeDetectionResult:
    """Tests for ChangeDetectionResult class."""

    def test_no_changes(self):
        """Test result with no changes."""
        result = ChangeDetectionResult(story_id="US-001")

        assert not result.has_changes
        assert not result.subtasks_changed
        assert "no changes" in str(result)

    def test_new_story(self):
        """Test result for new story."""
        result = ChangeDetectionResult(
            story_id="US-001",
            is_new=True,
            has_changes=True,
        )

        assert result.has_changes
        assert result.is_new
        assert "new" in str(result)

    def test_description_changed(self):
        """Test result with description changed."""
        result = ChangeDetectionResult(
            story_id="US-001",
            description_changed=True,
            has_changes=True,
        )

        assert result.has_changes
        assert "description" in str(result)

    def test_subtasks_changed(self):
        """Test result with subtask changes."""
        result = ChangeDetectionResult(
            story_id="US-001",
            subtasks_added={"Subtask 3"},
            subtasks_modified={"Subtask 1"},
            has_changes=True,
        )

        assert result.has_changes
        assert result.subtasks_changed
        assert "+1 subtasks" in str(result)
        assert "~1 subtasks" in str(result)


# =============================================================================
# IncrementalSyncStats Tests
# =============================================================================


class TestIncrementalSyncStats:
    """Tests for IncrementalSyncStats class."""

    def test_skip_rate(self):
        """Test skip rate calculation."""
        stats = IncrementalSyncStats(
            total_stories=10,
            changed_stories=3,
            skipped_stories=7,
        )

        assert stats.skip_rate == 0.7

    def test_skip_rate_zero_stories(self):
        """Test skip rate with zero stories."""
        stats = IncrementalSyncStats(total_stories=0)

        assert stats.skip_rate == 0.0

    def test_to_dict(self):
        """Test serialization to dict."""
        stats = IncrementalSyncStats(
            total_stories=10,
            changed_stories=3,
            skipped_stories=7,
            new_stories=1,
        )

        data = stats.to_dict()

        assert data["total_stories"] == 10
        assert data["changed_stories"] == 3
        assert data["skipped_stories"] == 7
        assert data["skip_rate"] == 0.7

    def test_summary(self):
        """Test summary string."""
        stats = IncrementalSyncStats(
            total_stories=10,
            changed_stories=3,
            skipped_stories=7,
            new_stories=1,
        )

        summary = stats.summary()

        assert "3/10" in summary
        assert "7 skipped" in summary
        assert "1 new" in summary


# =============================================================================
# Utility Functions Tests
# =============================================================================


class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_compute_story_hash(self, sample_story):
        """Test computing story hash."""
        hash1 = compute_story_hash(sample_story)
        hash2 = compute_story_hash(sample_story)

        assert hash1 == hash2
        assert ":" in hash1  # Format is content_hash:metadata_hash

    def test_compute_story_hash_changes(self, sample_story, modified_story):
        """Modified stories should have different hashes."""
        hash1 = compute_story_hash(sample_story)
        hash2 = compute_story_hash(modified_story)

        assert hash1 != hash2

    def test_stories_differ_same(self, sample_story):
        """Same stories should not differ."""
        assert stories_differ(sample_story, sample_story) is False

    def test_stories_differ_modified(self, sample_story, modified_story):
        """Different stories should differ."""
        assert stories_differ(sample_story, modified_story) is True


# =============================================================================
# Integration Tests
# =============================================================================


class TestIncrementalSyncIntegration:
    """Integration tests for incremental sync workflow."""

    def test_full_sync_workflow(self, temp_storage_dir):
        """Test complete incremental sync workflow."""
        desc1 = """**As a** user
**I want** to test story 1
**So that** I can verify functionality"""
        desc2 = """**As a** user
**I want** to test story 2
**So that** I can verify other functionality"""
        desc1_updated = """**As a** user
**I want** to test story 1 UPDATED
**So that** I can verify new functionality"""

        # Create initial stories
        stories = [
            UserStory(
                id=StoryId("US-001"),
                title="Story 1",
                description=Description.from_markdown(desc1),
            ),
            UserStory(
                id=StoryId("US-002"),
                title="Story 2",
                description=Description.from_markdown(desc2),
            ),
        ]

        # First sync - all stories are new
        tracker = ChangeTracker(storage_dir=temp_storage_dir)
        tracker.load("EPIC-123", "/doc.md")

        changes = tracker.detect_changes(stories)
        assert all(r.is_new for r in changes.values())

        tracker.save("EPIC-123", "/doc.md")

        # Second sync - no changes
        tracker2 = ChangeTracker(storage_dir=temp_storage_dir)
        tracker2.load("EPIC-123", "/doc.md")

        changes2 = tracker2.detect_changes(stories)
        assert not any(r.has_changes for r in changes2.values())

        # Third sync - one story modified
        stories[0] = UserStory(
            id=StoryId("US-001"),
            title="Story 1",
            description=Description.from_markdown(desc1_updated),
        )

        tracker3 = ChangeTracker(storage_dir=temp_storage_dir)
        tracker3.load("EPIC-123", "/doc.md")

        changes3 = tracker3.detect_changes(stories)

        assert changes3["US-001"].has_changes
        assert changes3["US-001"].description_changed
        assert not changes3["US-002"].has_changes

    def test_multiple_epics_workflow(self, temp_storage_dir):
        """Test tracking changes for multiple epics."""
        story1 = UserStory(id=StoryId("US-001"), title="Story 1")
        story2 = UserStory(id=StoryId("US-002"), title="Story 2")

        # Sync epic 1
        tracker1 = ChangeTracker(storage_dir=temp_storage_dir)
        tracker1.load("EPIC-100", "/doc.md")
        tracker1.detect_changes([story1])
        tracker1.save("EPIC-100", "/doc.md")

        # Sync epic 2
        tracker2 = ChangeTracker(storage_dir=temp_storage_dir)
        tracker2.load("EPIC-200", "/doc.md")
        tracker2.detect_changes([story2])
        tracker2.save("EPIC-200", "/doc.md")

        # Both should have their own state
        tracker3 = ChangeTracker(storage_dir=temp_storage_dir)
        assert tracker3.load("EPIC-100", "/doc.md")
        assert tracker3.previous_story_count == 1

        tracker4 = ChangeTracker(storage_dir=temp_storage_dir)
        assert tracker4.load("EPIC-200", "/doc.md")
        assert tracker4.previous_story_count == 1
