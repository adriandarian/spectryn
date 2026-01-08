"""
Tests for TUI data models and utilities.
"""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from spectryn.cli.tui.data import (
    ConflictType,
    StoryConflict,
    SyncProgress,
    SyncState,
    TUIState,
    create_demo_state,
)
from spectryn.core.domain.entities import UserStory
from spectryn.core.domain.enums import Priority, Status
from spectryn.core.domain.value_objects import IssueKey, StoryId


class TestSyncProgress:
    """Tests for SyncProgress dataclass."""

    def test_default_values(self) -> None:
        """Test default values are set correctly."""
        progress = SyncProgress()

        assert progress.total_operations == 0
        assert progress.completed_operations == 0
        assert progress.current_operation == ""
        assert progress.phase == "idle"
        assert progress.errors == []
        assert progress.warnings == []

    def test_progress_percent_zero_total(self) -> None:
        """Test progress percentage when total is zero."""
        progress = SyncProgress(total_operations=0, completed_operations=0)

        assert progress.progress_percent == 0.0

    def test_progress_percent_partial(self) -> None:
        """Test progress percentage calculation."""
        progress = SyncProgress(total_operations=10, completed_operations=5)

        assert progress.progress_percent == 50.0

    def test_progress_percent_complete(self) -> None:
        """Test progress percentage when complete."""
        progress = SyncProgress(total_operations=10, completed_operations=10)

        assert progress.progress_percent == 100.0

    def test_elapsed_time_not_started(self) -> None:
        """Test elapsed time when not started."""
        progress = SyncProgress()

        assert progress.elapsed_time == 0.0

    def test_elapsed_time_in_progress(self) -> None:
        """Test elapsed time during operation."""
        start = datetime.now() - timedelta(seconds=5)
        progress = SyncProgress(start_time=start)

        # Should be approximately 5 seconds (allow some tolerance)
        assert 4.0 <= progress.elapsed_time <= 6.0

    def test_elapsed_time_completed(self) -> None:
        """Test elapsed time when completed."""
        start = datetime.now() - timedelta(seconds=10)
        end = datetime.now() - timedelta(seconds=5)
        progress = SyncProgress(start_time=start, end_time=end)

        # Should be exactly 5 seconds
        assert 4.9 <= progress.elapsed_time <= 5.1

    def test_is_complete_false(self) -> None:
        """Test is_complete when not complete."""
        progress = SyncProgress(phase="syncing")

        assert not progress.is_complete

    def test_is_complete_true(self) -> None:
        """Test is_complete when phase is complete."""
        progress = SyncProgress(phase="complete")

        assert progress.is_complete

    def test_has_errors_false(self) -> None:
        """Test has_errors when no errors."""
        progress = SyncProgress()

        assert not progress.has_errors

    def test_has_errors_true(self) -> None:
        """Test has_errors when errors exist."""
        progress = SyncProgress(errors=["Error 1", "Error 2"])

        assert progress.has_errors


class TestStoryConflict:
    """Tests for StoryConflict dataclass."""

    def test_creation(self) -> None:
        """Test conflict creation."""
        conflict = StoryConflict(
            story_id="US-001",
            story_title="Test Story",
            conflict_type=ConflictType.BOTH_MODIFIED,
            local_value="Local description",
            remote_value="Remote description",
        )

        assert conflict.story_id == "US-001"
        assert conflict.conflict_type == ConflictType.BOTH_MODIFIED
        assert not conflict.resolved
        assert conflict.resolution is None

    def test_resolve_with_local(self) -> None:
        """Test resolving conflict with local value."""
        conflict = StoryConflict(
            story_id="US-001",
            story_title="Test",
            conflict_type=ConflictType.BOTH_MODIFIED,
            local_value="Local",
            remote_value="Remote",
        )

        conflict.resolve_with_local()

        assert conflict.resolved
        assert conflict.resolution == "local"

    def test_resolve_with_remote(self) -> None:
        """Test resolving conflict with remote value."""
        conflict = StoryConflict(
            story_id="US-001",
            story_title="Test",
            conflict_type=ConflictType.BOTH_MODIFIED,
            local_value="Local",
            remote_value="Remote",
        )

        conflict.resolve_with_remote()

        assert conflict.resolved
        assert conflict.resolution == "remote"


class TestTUIState:
    """Tests for TUIState dataclass."""

    def test_default_state(self) -> None:
        """Test default state initialization."""
        state = TUIState()

        assert state.markdown_path is None
        assert state.epic_key is None
        assert state.stories == []
        assert state.sync_state == SyncState.IDLE
        assert state.dry_run is True
        assert not state.has_conflicts

    def test_has_conflicts_none(self) -> None:
        """Test has_conflicts when no conflicts."""
        state = TUIState()

        assert not state.has_conflicts
        assert state.unresolved_conflicts_count == 0

    def test_has_conflicts_unresolved(self) -> None:
        """Test has_conflicts with unresolved conflicts."""
        conflict = StoryConflict(
            story_id="US-001",
            story_title="Test",
            conflict_type=ConflictType.BOTH_MODIFIED,
            local_value="Local",
            remote_value="Remote",
        )
        state = TUIState(conflicts=[conflict])

        assert state.has_conflicts
        assert state.unresolved_conflicts_count == 1

    def test_has_conflicts_all_resolved(self) -> None:
        """Test has_conflicts when all resolved."""
        conflict = StoryConflict(
            story_id="US-001",
            story_title="Test",
            conflict_type=ConflictType.BOTH_MODIFIED,
            local_value="Local",
            remote_value="Remote",
            resolved=True,
            resolution="local",
        )
        state = TUIState(conflicts=[conflict])

        assert not state.has_conflicts
        assert state.unresolved_conflicts_count == 0

    def test_get_selected_story_none(self) -> None:
        """Test get_selected_story when none selected."""
        state = TUIState()

        assert state.get_selected_story() is None

    def test_get_selected_story_not_found(self) -> None:
        """Test get_selected_story when ID not in list."""
        story = UserStory(id=StoryId("US-001"), title="Test")
        state = TUIState(stories=[story], selected_story_id="US-999")

        assert state.get_selected_story() is None

    def test_get_selected_story_found(self) -> None:
        """Test get_selected_story when found."""
        story = UserStory(id=StoryId("US-001"), title="Test")
        state = TUIState(stories=[story], selected_story_id="US-001")

        result = state.get_selected_story()
        assert result is not None
        assert str(result.id) == "US-001"

    def test_get_filtered_stories_no_filter(self) -> None:
        """Test get_filtered_stories with no filters."""
        stories = [
            UserStory(id=StoryId("US-001"), title="Story 1"),
            UserStory(id=StoryId("US-002"), title="Story 2"),
        ]
        state = TUIState(stories=stories)

        result = state.get_filtered_stories()
        assert len(result) == 2

    def test_get_filtered_stories_by_status(self) -> None:
        """Test get_filtered_stories by status."""
        stories = [
            UserStory(id=StoryId("US-001"), title="Story 1", status=Status.DONE),
            UserStory(id=StoryId("US-002"), title="Story 2", status=Status.IN_PROGRESS),
            UserStory(id=StoryId("US-003"), title="Story 3", status=Status.DONE),
        ]
        state = TUIState(stories=stories, filter_status=Status.DONE)

        result = state.get_filtered_stories()
        assert len(result) == 2
        assert all(s.status == Status.DONE for s in result)

    def test_get_filtered_stories_by_priority(self) -> None:
        """Test get_filtered_stories by priority."""
        stories = [
            UserStory(id=StoryId("US-001"), title="Story 1", priority=Priority.HIGH),
            UserStory(id=StoryId("US-002"), title="Story 2", priority=Priority.LOW),
        ]
        state = TUIState(stories=stories, filter_priority=Priority.HIGH)

        result = state.get_filtered_stories()
        assert len(result) == 1
        assert result[0].priority == Priority.HIGH

    def test_get_filtered_stories_by_search(self) -> None:
        """Test get_filtered_stories by search query."""
        stories = [
            UserStory(id=StoryId("US-001"), title="Authentication Feature"),
            UserStory(id=StoryId("US-002"), title="Dashboard Layout"),
            UserStory(
                id=StoryId("US-003"), title="Auth Settings", external_key=IssueKey("PROJ-123")
            ),
        ]
        state = TUIState(stories=stories, search_query="auth")

        result = state.get_filtered_stories()
        assert len(result) == 2
        assert all("auth" in s.title.lower() for s in result)

    def test_get_filtered_stories_combined_filters(self) -> None:
        """Test get_filtered_stories with multiple filters."""
        stories = [
            UserStory(
                id=StoryId("US-001"),
                title="Auth Feature",
                status=Status.DONE,
                priority=Priority.HIGH,
            ),
            UserStory(
                id=StoryId("US-002"),
                title="Auth Config",
                status=Status.PLANNED,
                priority=Priority.HIGH,
            ),
            UserStory(
                id=StoryId("US-003"), title="Dashboard", status=Status.DONE, priority=Priority.LOW
            ),
        ]
        state = TUIState(
            stories=stories,
            filter_status=Status.DONE,
            filter_priority=Priority.HIGH,
            search_query="auth",
        )

        result = state.get_filtered_stories()
        assert len(result) == 1
        assert result[0].title == "Auth Feature"


class TestCreateDemoState:
    """Tests for create_demo_state function."""

    def test_creates_valid_state(self) -> None:
        """Test that demo state is created with valid data."""
        state = create_demo_state()

        assert state.epic_key is not None
        assert state.epic is not None
        assert len(state.stories) > 0
        assert state.selected_story_id is not None

    def test_demo_stories_have_varied_status(self) -> None:
        """Test that demo stories have varied statuses."""
        state = create_demo_state()

        statuses = {s.status for s in state.stories}
        # Should have at least 2 different statuses
        assert len(statuses) >= 2

    def test_demo_stories_have_external_keys(self) -> None:
        """Test that some demo stories have external keys."""
        state = create_demo_state()

        with_keys = [s for s in state.stories if s.external_key]
        assert len(with_keys) >= 1


class TestSyncState:
    """Tests for SyncState enum."""

    def test_all_states_defined(self) -> None:
        """Test all expected states are defined."""
        assert SyncState.IDLE.value == "idle"
        assert SyncState.LOADING.value == "loading"
        assert SyncState.SYNCING.value == "syncing"
        assert SyncState.SUCCESS.value == "success"
        assert SyncState.ERROR.value == "error"


class TestConflictType:
    """Tests for ConflictType enum."""

    def test_all_types_defined(self) -> None:
        """Test all expected conflict types are defined."""
        assert ConflictType.LOCAL_MODIFIED.value == "local_modified"
        assert ConflictType.REMOTE_MODIFIED.value == "remote_modified"
        assert ConflictType.BOTH_MODIFIED.value == "both_modified"
        assert ConflictType.DELETED_REMOTE.value == "deleted_remote"
        assert ConflictType.DELETED_LOCAL.value == "deleted_local"
