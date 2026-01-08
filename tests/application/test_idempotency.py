"""Tests for idempotency module."""

from unittest.mock import MagicMock

import pytest

from spectryn.application.sync.idempotency import (
    ContentHasher,
    IdempotencyCheck,
    IdempotencyGuard,
    IdempotencyLog,
    IdempotencyResult,
    IdempotencyStatus,
    check_idempotency,
    is_content_unchanged,
)
from spectryn.core.domain.entities import UserStory
from spectryn.core.domain.enums import Status
from spectryn.core.domain.value_objects import Description, StoryId


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_story():
    """Create a sample story."""
    return UserStory(
        id=StoryId("US-001"),
        title="Test Story",
        description=Description.from_markdown("This is a test description"),
        status=Status.PLANNED,
        story_points=5,
    )


@pytest.fixture
def mock_issue():
    """Create a mock issue."""
    issue = MagicMock()
    issue.key = "PROJ-123"
    issue.summary = "Test Story"
    issue.description = "This is a test description"
    issue.status = "planned"
    issue.story_points = 5
    return issue


# =============================================================================
# ContentHasher Tests
# =============================================================================


class TestContentHasher:
    """Tests for ContentHasher class."""

    def test_hash_text_identical(self):
        """Test that identical text produces same hash."""
        hasher = ContentHasher()
        hash1 = hasher.hash_text("hello world")
        hash2 = hasher.hash_text("hello world")
        assert hash1 == hash2

    def test_hash_text_different(self):
        """Test that different text produces different hash."""
        hasher = ContentHasher()
        hash1 = hasher.hash_text("hello world")
        hash2 = hasher.hash_text("goodbye world")
        assert hash1 != hash2

    def test_hash_text_normalizes_whitespace(self):
        """Test that whitespace is normalized."""
        hasher = ContentHasher()
        hash1 = hasher.hash_text("  hello world  ")
        hash2 = hasher.hash_text("hello world")
        assert hash1 == hash2

    def test_hash_text_normalizes_line_endings(self):
        """Test that line endings are normalized."""
        hasher = ContentHasher()
        hash1 = hasher.hash_text("hello\r\nworld")
        hash2 = hasher.hash_text("hello\nworld")
        assert hash1 == hash2

    def test_hash_text_none(self):
        """Test hashing None value."""
        hasher = ContentHasher()
        assert hasher.hash_text(None) == "null"

    def test_hash_text_strict_preserves_whitespace(self):
        """Test strict hashing preserves whitespace."""
        hasher = ContentHasher()
        hash1 = hasher.hash_text_strict("  hello  ")
        hash2 = hasher.hash_text_strict("hello")
        assert hash1 != hash2

    def test_hash_numeric(self):
        """Test hashing numeric values."""
        hasher = ContentHasher()
        assert hasher.hash_numeric(5) == hasher.hash_numeric(5)
        assert hasher.hash_numeric(5) != hasher.hash_numeric(8)
        assert hasher.hash_numeric(None) == "null"

    def test_hash_status(self):
        """Test hashing status values."""
        hasher = ContentHasher()
        assert hasher.hash_status("In Progress") == hasher.hash_status("in progress")
        assert hasher.hash_status("done") != hasher.hash_status("planned")

    def test_hash_list(self):
        """Test hashing lists."""
        hasher = ContentHasher()
        # Order shouldn't matter for lists
        hash1 = hasher.hash_list(["a", "b", "c"])
        hash2 = hasher.hash_list(["c", "b", "a"])
        assert hash1 == hash2

        # Different content should differ
        hash3 = hasher.hash_list(["a", "b", "d"])
        assert hash1 != hash3

    def test_hash_value_dict(self):
        """Test hashing dictionaries."""
        hasher = ContentHasher()
        hash1 = hasher.hash_value({"a": 1, "b": 2})
        hash2 = hasher.hash_value({"b": 2, "a": 1})  # Same content, different order
        assert hash1 == hash2


# =============================================================================
# IdempotencyStatus Tests
# =============================================================================


class TestIdempotencyStatus:
    """Tests for IdempotencyStatus enum."""

    def test_all_statuses_exist(self):
        """Test all expected statuses exist."""
        assert IdempotencyStatus.UNCHANGED.value == "unchanged"
        assert IdempotencyStatus.CHANGED.value == "changed"
        assert IdempotencyStatus.NEW.value == "new"
        assert IdempotencyStatus.DELETED.value == "deleted"
        assert IdempotencyStatus.CONFLICT.value == "conflict"


# =============================================================================
# IdempotencyCheck Tests
# =============================================================================


class TestIdempotencyCheck:
    """Tests for IdempotencyCheck dataclass."""

    def test_needs_sync_when_changed(self):
        """Test needs_sync is True when changed."""
        check = IdempotencyCheck(
            story_id="US-001",
            field="description",
            status=IdempotencyStatus.CHANGED,
        )
        assert check.needs_sync is True

    def test_needs_sync_when_new(self):
        """Test needs_sync is True when new."""
        check = IdempotencyCheck(
            story_id="US-001",
            field="description",
            status=IdempotencyStatus.NEW,
        )
        assert check.needs_sync is True

    def test_needs_sync_false_when_unchanged(self):
        """Test needs_sync is False when unchanged."""
        check = IdempotencyCheck(
            story_id="US-001",
            field="description",
            status=IdempotencyStatus.UNCHANGED,
        )
        assert check.needs_sync is False

    def test_is_unchanged(self):
        """Test is_unchanged property."""
        unchanged = IdempotencyCheck(
            story_id="US-001",
            field="description",
            status=IdempotencyStatus.UNCHANGED,
        )
        assert unchanged.is_unchanged is True

        changed = IdempotencyCheck(
            story_id="US-001",
            field="description",
            status=IdempotencyStatus.CHANGED,
        )
        assert changed.is_unchanged is False


# =============================================================================
# IdempotencyResult Tests
# =============================================================================


class TestIdempotencyResult:
    """Tests for IdempotencyResult dataclass."""

    def test_is_fully_idempotent_when_no_changes(self):
        """Test is_fully_idempotent when no changes needed."""
        result = IdempotencyResult(
            total_fields_checked=5,
            fields_unchanged=5,
            fields_need_sync=0,
            fields_new=0,
        )
        assert result.is_fully_idempotent is True

    def test_not_idempotent_when_changes_needed(self):
        """Test is_fully_idempotent is False when changes needed."""
        result = IdempotencyResult(
            total_fields_checked=5,
            fields_unchanged=3,
            fields_need_sync=2,
        )
        assert result.is_fully_idempotent is False

    def test_skip_percentage(self):
        """Test skip percentage calculation."""
        result = IdempotencyResult(
            total_fields_checked=10,
            fields_unchanged=8,
            fields_need_sync=2,
        )
        assert result.skip_percentage == 80.0

    def test_skip_percentage_all_skipped(self):
        """Test skip percentage when all are skipped."""
        result = IdempotencyResult(
            total_fields_checked=5,
            fields_unchanged=5,
        )
        assert result.skip_percentage == 100.0

    def test_skip_percentage_zero_fields(self):
        """Test skip percentage with zero fields."""
        result = IdempotencyResult()
        assert result.skip_percentage == 100.0

    def test_summary_when_idempotent(self):
        """Test summary when fully idempotent."""
        result = IdempotencyResult(
            total_fields_checked=5,
            fields_unchanged=5,
        )
        assert "no changes needed" in result.summary

    def test_summary_when_changes_needed(self):
        """Test summary when changes are needed."""
        result = IdempotencyResult(
            total_fields_checked=10,
            fields_unchanged=6,
            fields_need_sync=3,
            fields_new=1,
        )
        assert "60%" in result.summary
        assert "3 need sync" in result.summary


# =============================================================================
# IdempotencyGuard Tests
# =============================================================================


class TestIdempotencyGuard:
    """Tests for IdempotencyGuard class."""

    def test_check_field_unchanged(self, sample_story, mock_issue):
        """Test checking unchanged field."""
        guard = IdempotencyGuard()
        check = guard.check_field(sample_story, mock_issue, "story_points")

        assert check.status == IdempotencyStatus.UNCHANGED
        assert check.is_unchanged is True

    def test_check_field_changed(self, sample_story, mock_issue):
        """Test checking changed field."""
        mock_issue.story_points = 8  # Different from story's 5
        guard = IdempotencyGuard()
        check = guard.check_field(sample_story, mock_issue, "story_points")

        assert check.status == IdempotencyStatus.CHANGED
        assert check.needs_sync is True

    def test_check_story_new(self, sample_story):
        """Test checking a new story (no matching issue)."""
        guard = IdempotencyGuard()
        checks = guard.check_story(sample_story, None)

        assert len(checks) == 4  # description, story_points, status, title
        assert all(c.status == IdempotencyStatus.NEW for c in checks)

    def test_check_story_all_unchanged(self, sample_story, mock_issue):
        """Test checking story with all fields unchanged."""
        guard = IdempotencyGuard()
        checks = guard.check_story(sample_story, mock_issue)

        unchanged_count = sum(1 for c in checks if c.is_unchanged)
        assert unchanged_count >= 2  # At least story_points and status

    def test_analyze_sync(self, sample_story, mock_issue):
        """Test full sync analysis."""
        guard = IdempotencyGuard()

        result = guard.analyze_sync(
            stories=[sample_story],
            issues=[mock_issue],
            matches={"US-001": "PROJ-123"},
        )

        assert result.total_fields_checked == 4
        assert result.stories_unchanged + result.stories_need_sync == 1

    def test_get_unchanged_story_ids(self, sample_story, mock_issue):
        """Test getting unchanged story IDs."""
        guard = IdempotencyGuard()
        guard.check_story(sample_story, mock_issue)

        unchanged = guard.get_unchanged_story_ids()
        # If all fields match, story should be unchanged
        # This depends on exact field matching
        assert isinstance(unchanged, set)

    def test_get_fields_needing_sync(self, sample_story, mock_issue):
        """Test getting fields that need sync."""
        mock_issue.story_points = 99  # Different

        guard = IdempotencyGuard()
        guard.check_story(sample_story, mock_issue)

        fields = guard.get_fields_needing_sync("US-001")
        assert "story_points" in fields


# =============================================================================
# IdempotencyLog Tests
# =============================================================================


class TestIdempotencyLog:
    """Tests for IdempotencyLog class."""

    def test_record_operation(self, tmp_path):
        """Test recording an operation."""
        log = IdempotencyLog(log_dir=tmp_path)

        log.record_operation(
            issue_key="PROJ-123",
            operation_type="update_description",
            field="description",
            content_hash="abc123",
            epic_key="EPIC-1",
        )

        assert log.was_executed(
            issue_key="PROJ-123",
            operation_type="update_description",
            field="description",
            content_hash="abc123",
            epic_key="EPIC-1",
        )

    def test_was_executed_false_for_new(self, tmp_path):
        """Test was_executed returns False for new operations."""
        log = IdempotencyLog(log_dir=tmp_path)

        assert not log.was_executed(
            issue_key="PROJ-123",
            operation_type="update_description",
            field="description",
            content_hash="new_hash",
            epic_key="EPIC-1",
        )

    def test_save_and_load(self, tmp_path):
        """Test saving and loading operations."""
        log = IdempotencyLog(log_dir=tmp_path)

        log.record_operation(
            issue_key="PROJ-123",
            operation_type="update_description",
            field="description",
            content_hash="abc123",
            epic_key="EPIC-1",
        )
        log.save("EPIC-1")

        # Load in new instance
        log2 = IdempotencyLog(log_dir=tmp_path)
        log2.load("EPIC-1")

        assert log2.was_executed(
            issue_key="PROJ-123",
            operation_type="update_description",
            field="description",
            content_hash="abc123",
            epic_key="EPIC-1",
        )

    def test_clear(self, tmp_path):
        """Test clearing operation log."""
        log = IdempotencyLog(log_dir=tmp_path)

        log.record_operation(
            issue_key="PROJ-123",
            operation_type="update",
            field="desc",
            content_hash="abc",
            epic_key="EPIC-1",
        )
        log.save("EPIC-1")

        assert log.clear("EPIC-1") is True
        assert log.clear("EPIC-1") is False  # Already cleared


# =============================================================================
# Convenience Function Tests
# =============================================================================


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_is_content_unchanged_true(self):
        """Test is_content_unchanged returns True for same content."""
        assert is_content_unchanged("hello", "hello") is True
        assert is_content_unchanged("  hello  ", "hello") is True

    def test_is_content_unchanged_false(self):
        """Test is_content_unchanged returns False for different content."""
        assert is_content_unchanged("hello", "world") is False

    def test_is_content_unchanged_none(self):
        """Test is_content_unchanged with None values."""
        assert is_content_unchanged(None, None) is True
        assert is_content_unchanged(None, "hello") is False

    def test_check_idempotency(self, sample_story, mock_issue):
        """Test check_idempotency convenience function."""
        result = check_idempotency(
            stories=[sample_story],
            issues=[mock_issue],
            matches={"US-001": "PROJ-123"},
        )

        assert isinstance(result, IdempotencyResult)
        assert result.total_fields_checked > 0


# =============================================================================
# Integration Tests
# =============================================================================


class TestIdempotencyIntegration:
    """Integration tests for idempotency."""

    def test_repeated_check_produces_same_result(self, sample_story, mock_issue):
        """Test that repeated checks produce consistent results."""
        guard = IdempotencyGuard()

        result1 = guard.analyze_sync(
            stories=[sample_story],
            issues=[mock_issue],
            matches={"US-001": "PROJ-123"},
        )

        guard.clear()

        result2 = guard.analyze_sync(
            stories=[sample_story],
            issues=[mock_issue],
            matches={"US-001": "PROJ-123"},
        )

        assert result1.fields_unchanged == result2.fields_unchanged
        assert result1.fields_need_sync == result2.fields_need_sync

    def test_mixed_stories(self, mock_issue):
        """Test analysis with mix of unchanged and changed stories."""
        story1 = UserStory(
            id=StoryId("US-001"),
            title="Test Story",
            status=Status.PLANNED,
            story_points=5,
        )
        story2 = UserStory(
            id=StoryId("US-002"),
            title="Different Story",
            status=Status.IN_PROGRESS,
            story_points=8,
        )

        mock_issue2 = MagicMock()
        mock_issue2.key = "PROJ-124"
        mock_issue2.summary = "Different Story"
        mock_issue2.description = None
        mock_issue2.status = "open"  # Different from IN_PROGRESS
        mock_issue2.story_points = 3  # Different from 8

        guard = IdempotencyGuard()
        result = guard.analyze_sync(
            stories=[story1, story2],
            issues=[mock_issue, mock_issue2],
            matches={"US-001": "PROJ-123", "US-002": "PROJ-124"},
        )

        assert result.stories_need_sync >= 1  # At least story2 needs sync
