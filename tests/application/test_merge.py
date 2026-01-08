"""Tests for 3-way merge module."""

import pytest

from spectryn.application.sync.conflict import Conflict, ConflictType
from spectryn.application.sync.merge import (
    MergeAttempt,
    MergeConfig,
    MergeResult,
    MergeStrategy,
    SmartMergeResolver,
    ThreeWayMerger,
    resolve_conflict_with_merge,
)


# =============================================================================
# ThreeWayMerger - Basic Tests
# =============================================================================


class TestThreeWayMergerBasic:
    """Basic tests for ThreeWayMerger."""

    @pytest.fixture
    def merger(self):
        """Create a default merger."""
        return ThreeWayMerger()

    def test_all_identical(self, merger):
        """Test when all three values are identical."""
        result = merger.merge("hello", "hello", "hello")
        assert result.result == MergeResult.UNCHANGED
        assert result.merged_value == "hello"

    def test_local_remote_identical(self, merger):
        """Test when local and remote are identical (different from base)."""
        result = merger.merge("old", "new", "new")
        assert result.result == MergeResult.UNCHANGED
        assert result.merged_value == "new"

    def test_only_local_changed(self, merger):
        """Test when only local changed."""
        result = merger.merge("base", "local_change", "base")
        assert result.result == MergeResult.SUCCESS
        assert result.merged_value == "local_change"
        assert result.changes_from_local == 1
        assert result.changes_from_remote == 0

    def test_only_remote_changed(self, merger):
        """Test when only remote changed."""
        result = merger.merge("base", "base", "remote_change")
        assert result.result == MergeResult.SUCCESS
        assert result.merged_value == "remote_change"
        assert result.changes_from_local == 0
        assert result.changes_from_remote == 1


# =============================================================================
# ThreeWayMerger - Text Merge Tests
# =============================================================================


class TestThreeWayMergerText:
    """Tests for text merging."""

    @pytest.fixture
    def merger(self):
        """Create a merger with line-level strategy."""
        return ThreeWayMerger(MergeConfig(text_strategy=MergeStrategy.LINE_LEVEL))

    def test_non_overlapping_changes(self, merger):
        """Test merge of non-overlapping changes."""
        base = "line1\nline2\nline3\n"
        local = "line1_modified\nline2\nline3\n"  # Changed line 1
        remote = "line1\nline2\nline3_modified\n"  # Changed line 3

        result = merger.merge(base, local, remote, field_type="text")

        assert result.result == MergeResult.SUCCESS
        assert "line1_modified" in result.merged_value
        assert "line3_modified" in result.merged_value

    def test_overlapping_identical_changes(self, merger):
        """Test when both sides make identical changes."""
        base = "original\n"
        local = "modified\n"
        remote = "modified\n"

        result = merger.merge(base, local, remote, field_type="text")

        assert result.result in (MergeResult.SUCCESS, MergeResult.UNCHANGED)
        assert result.merged_value == "modified\n"

    def test_overlapping_different_changes(self, merger):
        """Test when both sides make different changes to same location."""
        base = "original\n"
        local = "local_version\n"
        remote = "remote_version\n"

        result = merger.merge(base, local, remote, field_type="text")

        # Should be conflict or partial with markers
        assert result.result in (MergeResult.CONFLICT, MergeResult.PARTIAL)

    def test_conflict_markers(self):
        """Test that conflict markers are added when configured."""
        config = MergeConfig(
            text_strategy=MergeStrategy.LINE_LEVEL,
            conflict_markers=True,
        )
        merger = ThreeWayMerger(config)

        base = "original\n"
        local = "local_version\n"
        remote = "remote_version\n"

        result = merger.merge(base, local, remote, field_type="text")

        if result.result == MergeResult.PARTIAL:
            assert "<<<<<<< LOCAL" in result.merged_value
            assert "=======" in result.merged_value
            assert ">>>>>>> REMOTE" in result.merged_value

    def test_word_level_merge(self):
        """Test word-level merging."""
        config = MergeConfig(text_strategy=MergeStrategy.WORD_LEVEL)
        merger = ThreeWayMerger(config)

        base = "the quick brown fox"
        local = "the slow brown fox"  # Changed 'quick' to 'slow'
        remote = "the quick brown dog"  # Changed 'fox' to 'dog'

        result = merger.merge(base, local, remote, field_type="text")

        assert result.result == MergeResult.SUCCESS
        assert "slow" in result.merged_value
        assert "dog" in result.merged_value


# =============================================================================
# ThreeWayMerger - Status Merge Tests
# =============================================================================


class TestThreeWayMergerStatus:
    """Tests for status field merging."""

    @pytest.fixture
    def merger(self):
        """Create a merger with default config."""
        return ThreeWayMerger()

    def test_higher_priority_wins(self, merger):
        """Test that higher priority status wins."""
        # Default priority: done > in_progress > blocked > planned > open
        result = merger.merge("planned", "in_progress", "planned", field_type="status")
        assert result.merged_value == "in_progress"

        result = merger.merge("planned", "planned", "done", field_type="status")
        assert result.merged_value == "done"

    def test_done_beats_in_progress(self, merger):
        """Test that done status wins over in_progress."""
        result = merger.merge("in_progress", "done", "in_progress", field_type="status")
        assert result.merged_value == "done"

    def test_same_priority_is_conflict(self, merger):
        """Test that same priority different values is conflict."""
        # If both changed to different but equal priority status
        # Create a priority list where "blocked" and "wip" have equal (non-listed) priority
        config = MergeConfig(status_priority=["done", "planned"])
        merger = ThreeWayMerger(config)

        result = merger.merge("planned", "blocked", "wip", field_type="status")
        # blocked and wip have same priority (both unlisted), should conflict
        assert result.result == MergeResult.CONFLICT


# =============================================================================
# ThreeWayMerger - Numeric Merge Tests
# =============================================================================


class TestThreeWayMergerNumeric:
    """Tests for numeric field merging."""

    def test_take_higher(self):
        """Test take_higher strategy."""
        config = MergeConfig(numeric_strategy=MergeStrategy.TAKE_HIGHER)
        merger = ThreeWayMerger(config)

        result = merger.merge(3, 5, 8, field_type="numeric")
        assert result.merged_value == 8

    def test_take_lower(self):
        """Test take_lower strategy."""
        config = MergeConfig(numeric_strategy=MergeStrategy.TAKE_LOWER)
        merger = ThreeWayMerger(config)

        result = merger.merge(3, 5, 8, field_type="numeric")
        assert result.merged_value == 5

    def test_sum_changes(self):
        """Test sum_changes strategy."""
        config = MergeConfig(numeric_strategy=MergeStrategy.SUM_CHANGES)
        merger = ThreeWayMerger(config)

        # base=3, local=5 (+2), remote=7 (+4)
        # merged = 3 + 2 + 4 = 9
        result = merger.merge(3, 5, 7, field_type="numeric")
        assert result.merged_value == 9

    def test_integer_preservation(self):
        """Test that integer values stay as integers."""
        merger = ThreeWayMerger()

        result = merger.merge(3, 5, 5, field_type="numeric")
        assert result.merged_value == 5
        assert isinstance(result.merged_value, int)


# =============================================================================
# ThreeWayMerger - List Merge Tests
# =============================================================================


class TestThreeWayMergerList:
    """Tests for list field merging."""

    def test_union_merge(self):
        """Test union merge strategy."""
        config = MergeConfig(list_strategy=MergeStrategy.UNION)
        merger = ThreeWayMerger(config)

        base = ["a", "b"]
        local = ["a", "b", "c"]  # Added c
        remote = ["a", "b", "d"]  # Added d

        result = merger.merge(base, local, remote, field_type="list")
        assert result.result == MergeResult.SUCCESS
        assert set(result.merged_value) == {"a", "b", "c", "d"}

    def test_intersection_merge(self):
        """Test intersection merge strategy."""
        config = MergeConfig(list_strategy=MergeStrategy.INTERSECTION)
        merger = ThreeWayMerger(config)

        base = ["a", "b", "c"]
        local = ["a", "b", "d"]
        remote = ["a", "b", "e"]

        result = merger.merge(base, local, remote, field_type="list")
        assert result.result == MergeResult.SUCCESS
        assert set(result.merged_value) == {"a", "b"}

    def test_local_priority_merge(self):
        """Test local priority merge strategy."""
        config = MergeConfig(list_strategy=MergeStrategy.LOCAL_PRIORITY)
        merger = ThreeWayMerger(config)

        base = ["a", "b"]
        local = ["a", "b", "c"]
        remote = ["a", "b", "d"]

        result = merger.merge(base, local, remote, field_type="list")
        assert result.result == MergeResult.SUCCESS
        # Should have local items plus remote additions
        assert "c" in result.merged_value
        assert "d" in result.merged_value


# =============================================================================
# MergeAttempt Tests
# =============================================================================


class TestMergeAttempt:
    """Tests for MergeAttempt dataclass."""

    def test_success_property(self):
        """Test success property."""
        success = MergeAttempt(result=MergeResult.SUCCESS)
        assert success.success is True

        unchanged = MergeAttempt(result=MergeResult.UNCHANGED)
        assert unchanged.success is True

        conflict = MergeAttempt(result=MergeResult.CONFLICT)
        assert conflict.success is False

        partial = MergeAttempt(result=MergeResult.PARTIAL)
        assert partial.success is False


# =============================================================================
# MergeConfig Tests
# =============================================================================


class TestMergeConfig:
    """Tests for MergeConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = MergeConfig()

        assert config.text_strategy == MergeStrategy.LINE_LEVEL
        assert config.numeric_strategy == MergeStrategy.TAKE_HIGHER
        assert config.list_strategy == MergeStrategy.UNION
        assert config.conflict_markers is True

    def test_custom_status_priority(self):
        """Test custom status priority."""
        config = MergeConfig(status_priority=["done", "wip", "todo"])
        assert config.status_priority == ["done", "wip", "todo"]


# =============================================================================
# resolve_conflict_with_merge Tests
# =============================================================================


class TestResolveConflictWithMerge:
    """Tests for resolve_conflict_with_merge function."""

    def test_text_conflict_resolution(self):
        """Test resolving a text conflict."""
        conflict = Conflict(
            story_id="US-001",
            jira_key="PROJ-123",
            field="description",
            conflict_type=ConflictType.BOTH_MODIFIED,
            local_value="local text",
            remote_value="local text",  # Same as local
            base_value="base text",
        )

        resolution = resolve_conflict_with_merge(conflict)
        assert resolution.resolution == "merge"
        assert resolution.merged_value == "local text"

    def test_status_conflict_resolution(self):
        """Test resolving a status conflict."""
        conflict = Conflict(
            story_id="US-001",
            jira_key="PROJ-123",
            field="status",
            conflict_type=ConflictType.BOTH_MODIFIED,
            local_value="done",
            remote_value="in_progress",
            base_value="planned",
        )

        resolution = resolve_conflict_with_merge(conflict)
        assert resolution.resolution == "merge"
        # done wins over in_progress
        assert resolution.merged_value == "done"

    def test_numeric_conflict_resolution(self):
        """Test resolving a numeric conflict."""
        conflict = Conflict(
            story_id="US-001",
            jira_key="PROJ-123",
            field="story_points",
            conflict_type=ConflictType.BOTH_MODIFIED,
            local_value=5,
            remote_value=8,
            base_value=3,
        )

        resolution = resolve_conflict_with_merge(conflict)
        assert resolution.resolution == "merge"
        # take_higher: 8 wins
        assert resolution.merged_value == 8


# =============================================================================
# SmartMergeResolver Tests
# =============================================================================


class TestSmartMergeResolver:
    """Tests for SmartMergeResolver class."""

    def test_successful_merge(self):
        """Test that successful merge doesn't call fallback."""
        resolver = SmartMergeResolver(fallback_strategy="local")

        conflict = Conflict(
            story_id="US-001",
            jira_key="PROJ-123",
            field="story_points",
            conflict_type=ConflictType.BOTH_MODIFIED,
            local_value=5,
            remote_value=8,
            base_value=3,
        )

        resolution = resolver.resolve(conflict)
        assert resolution.resolution == "merge"
        assert resolution.merged_value == 8

    def test_fallback_to_local(self):
        """Test fallback to local on merge failure."""
        resolver = SmartMergeResolver(fallback_strategy="local")

        # Create a conflict that will fail to merge
        conflict = Conflict(
            story_id="US-001",
            jira_key="PROJ-123",
            field="description",
            conflict_type=ConflictType.BOTH_MODIFIED,
            local_value="local only change",
            remote_value="remote only change",
            base_value="original",
        )

        resolution = resolver.resolve(conflict)
        # If merge fails, should fallback to local
        if resolution.resolution != "merge":
            assert resolution.resolution == "local"

    def test_fallback_to_skip(self):
        """Test fallback to skip."""
        resolver = SmartMergeResolver(fallback_strategy="skip")

        conflict = Conflict(
            story_id="US-001",
            jira_key="PROJ-123",
            field="description",
            conflict_type=ConflictType.BOTH_MODIFIED,
            local_value="local",
            remote_value="remote",
            base_value="base",
        )

        resolution = resolver.resolve(conflict)
        if resolution.resolution != "merge":
            assert resolution.resolution == "skip"

    def test_custom_prompt_function(self):
        """Test with custom prompt function."""

        def my_prompt(conflict):
            return "remote"  # Always choose remote

        resolver = SmartMergeResolver(
            fallback_strategy="ask",
            prompt_func=my_prompt,
        )

        conflict = Conflict(
            story_id="US-001",
            jira_key="PROJ-123",
            field="description",
            conflict_type=ConflictType.BOTH_MODIFIED,
            local_value="local",
            remote_value="remote",
            base_value="base",
        )

        resolution = resolver.resolve(conflict)
        if resolution.resolution != "merge":
            assert resolution.resolution == "remote"


# =============================================================================
# Integration Tests
# =============================================================================


class TestMergeIntegration:
    """Integration tests for merge functionality."""

    def test_complex_text_merge(self):
        """Test merging complex multi-line text."""
        merger = ThreeWayMerger()

        base = """
# Title

First paragraph.

Second paragraph.

Third paragraph.
"""
        local = """
# Modified Title

First paragraph.

Second paragraph with local edit.

Third paragraph.
"""
        remote = """
# Title

First paragraph.

Second paragraph.

Third paragraph with remote edit.

Fourth paragraph added by remote.
"""

        result = merger.merge(base, local, remote, field_type="text")

        # Should be able to merge since changes don't overlap
        assert result.result == MergeResult.SUCCESS
        assert "Modified Title" in result.merged_value
        assert "Fourth paragraph added by remote" in result.merged_value

    def test_subtask_list_merge(self):
        """Test merging subtask lists."""
        config = MergeConfig(list_strategy=MergeStrategy.UNION)
        merger = ThreeWayMerger(config)

        base = ["Setup database", "Create API"]
        local = ["Setup database", "Create API", "Add tests"]
        remote = ["Setup database", "Create API", "Write docs"]

        result = merger.merge(base, local, remote, field_type="list")

        assert result.result == MergeResult.SUCCESS
        assert len(result.merged_value) == 4
        assert "Add tests" in result.merged_value
        assert "Write docs" in result.merged_value
