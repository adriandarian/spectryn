"""Tests for the progress reporting module."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from spectryn.application.sync.progress import (
    ProgressReporter,
    ProgressState,
    SyncPhase,
    create_progress_reporter,
)


class TestSyncPhase:
    """Tests for SyncPhase enum."""

    def test_display_name_for_all_phases(self) -> None:
        """All phases should have display names."""
        for phase in SyncPhase:
            assert phase.display_name
            assert isinstance(phase.display_name, str)

    def test_display_name_mapping(self) -> None:
        """Display names should be human-readable."""
        assert SyncPhase.BACKUP.display_name == "Creating backup"
        assert SyncPhase.ANALYZING.display_name == "Analyzing"
        assert SyncPhase.DESCRIPTIONS.display_name == "Updating descriptions"
        assert SyncPhase.SUBTASKS.display_name == "Syncing subtasks"
        assert SyncPhase.COMPLETE.display_name == "Complete"


class TestProgressState:
    """Tests for ProgressState dataclass."""

    def test_default_state(self) -> None:
        """Default state should have sensible defaults."""
        state = ProgressState()
        assert state.phase == SyncPhase.ANALYZING
        assert state.phase_index == 0
        assert state.total_phases == 5
        assert state.current_item == 0
        assert state.total_items == 0
        assert state.item_name == ""

    def test_phase_progress(self) -> None:
        """Phase progress should be calculated correctly."""
        state = ProgressState(phase_index=2, total_phases=4)
        assert state.phase_progress == 50.0

    def test_phase_progress_zero_phases(self) -> None:
        """Phase progress should be 0 when no phases."""
        state = ProgressState(total_phases=0)
        assert state.phase_progress == 0.0

    def test_item_progress(self) -> None:
        """Item progress should be calculated correctly."""
        state = ProgressState(current_item=5, total_items=10)
        assert state.item_progress == 50.0

    def test_item_progress_zero_items(self) -> None:
        """Item progress should be 0 when no items."""
        state = ProgressState(total_items=0)
        assert state.item_progress == 0.0

    def test_overall_progress(self) -> None:
        """Overall progress should combine phase and item progress."""
        state = ProgressState(
            phase_index=1,
            total_phases=4,
            current_item=2,
            total_items=4,
        )
        # Phase 1/4 complete = 25%, then 2/4 of current phase = 12.5%
        # Total = 25% + 12.5% = 37.5%
        assert state.overall_progress == pytest.approx(37.5)

    def test_overall_progress_complete(self) -> None:
        """Overall progress should be 100 when complete."""
        state = ProgressState(
            phase_index=4,
            total_phases=4,
            current_item=10,
            total_items=10,
        )
        assert state.overall_progress == 100.0

    def test_elapsed_seconds(self) -> None:
        """Elapsed seconds should be positive after creation."""
        state = ProgressState()
        # Allow some time to pass
        assert state.elapsed_seconds >= 0


class TestProgressReporter:
    """Tests for ProgressReporter class."""

    def test_init_with_callback(self) -> None:
        """Reporter should initialize with callback."""
        callback = MagicMock()
        reporter = ProgressReporter(callback=callback, total_phases=5)
        assert reporter.state.total_phases == 5

    def test_start_phase(self) -> None:
        """Starting a phase should update state."""
        reporter = ProgressReporter(total_phases=5)
        reporter.start_phase(SyncPhase.DESCRIPTIONS, total_items=10)

        assert reporter.state.phase == SyncPhase.DESCRIPTIONS
        assert reporter.state.total_items == 10
        assert reporter.state.current_item == 0

    def test_update_item(self) -> None:
        """Updating item should increment counter."""
        reporter = ProgressReporter(total_phases=5)
        reporter.start_phase(SyncPhase.SUBTASKS, total_items=5)

        reporter.update_item("Subtask 1")
        assert reporter.state.current_item == 1
        assert reporter.state.item_name == "Subtask 1"

        reporter.update_item("Subtask 2")
        assert reporter.state.current_item == 2
        assert reporter.state.item_name == "Subtask 2"

    def test_update_item_no_increment(self) -> None:
        """Update item without incrementing should only change name."""
        reporter = ProgressReporter(total_phases=5)
        reporter.start_phase(SyncPhase.SUBTASKS, total_items=5)
        reporter.update_item("Item 1")

        reporter.update_item("Item 1 (detail)", increment=False)
        assert reporter.state.current_item == 1
        assert reporter.state.item_name == "Item 1 (detail)"

    def test_complete(self) -> None:
        """Completing should set phase to COMPLETE."""
        reporter = ProgressReporter(total_phases=5)
        reporter.complete()

        assert reporter.state.phase == SyncPhase.COMPLETE
        assert reporter.state.phase_index == 5

    def test_callback_called_on_start_phase(self) -> None:
        """Callback should be called when starting phase."""
        callback = MagicMock()
        reporter = ProgressReporter(callback=callback, total_phases=5)

        reporter.start_phase(SyncPhase.ANALYZING, total_items=10)

        callback.assert_called()
        args = callback.call_args[0]
        assert args[0] == "Analyzing"  # phase name
        assert args[1] == ""  # item name (empty at phase start)
        assert args[4] == 10  # total items

    def test_callback_called_on_update_item(self) -> None:
        """Callback should be called when updating item."""
        callback = MagicMock()
        reporter = ProgressReporter(callback=callback, total_phases=5)
        reporter.start_phase(SyncPhase.SUBTASKS, total_items=5)
        callback.reset_mock()

        reporter.update_item("PROJ-123")

        callback.assert_called()
        args = callback.call_args[0]
        assert args[1] == "PROJ-123"  # item name

    def test_legacy_callback(self) -> None:
        """Legacy callback should be called with phase info."""
        legacy_callback = MagicMock()
        reporter = ProgressReporter(legacy_callback=legacy_callback, total_phases=5)

        reporter.start_phase(SyncPhase.DESCRIPTIONS)

        legacy_callback.assert_called()
        args = legacy_callback.call_args[0]
        assert args[0] == "Updating descriptions"  # phase name
        assert isinstance(args[1], int)  # phase index
        assert args[2] == 5  # total phases


class TestCreateProgressReporter:
    """Tests for create_progress_reporter factory function."""

    def test_none_callback_returns_none(self) -> None:
        """None callback should return None."""
        reporter = create_progress_reporter(None)
        assert reporter is None

    def test_legacy_callback_detected(self) -> None:
        """Legacy 3-parameter callback should be detected."""

        def legacy_callback(phase: str, current: int, total: int) -> None:
            pass

        reporter = create_progress_reporter(legacy_callback, total_phases=5)
        assert reporter is not None
        assert reporter._legacy_callback is not None
        assert reporter._callback is None

    def test_new_callback_detected(self) -> None:
        """New 5-parameter callback should be detected."""

        def new_callback(phase: str, item: str, progress: float, current: int, total: int) -> None:
            pass

        reporter = create_progress_reporter(new_callback, total_phases=5)
        assert reporter is not None
        assert reporter._callback is not None
        assert reporter._legacy_callback is None
