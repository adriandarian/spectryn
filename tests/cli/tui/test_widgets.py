"""
Tests for TUI widgets helper functions.

Note: Full widget testing requires Textual's async test harness.
These tests focus on the utility functions that can be tested synchronously.
"""

import pytest

from spectryn.core.domain.enums import Priority, Status


class TestStatusFormatting:
    """Tests for status formatting utilities."""

    def test_get_status_icon_done(self) -> None:
        """Test status icon for done."""
        from spectryn.cli.tui.widgets import get_status_icon

        assert get_status_icon(Status.DONE) == "✅"

    def test_get_status_icon_in_progress(self) -> None:
        """Test status icon for in progress."""
        from spectryn.cli.tui.widgets import get_status_icon

        assert get_status_icon(Status.IN_PROGRESS) == "🔄"

    def test_get_status_icon_planned(self) -> None:
        """Test status icon for planned."""
        from spectryn.cli.tui.widgets import get_status_icon

        assert get_status_icon(Status.PLANNED) == "📋"

    def test_get_status_icon_open(self) -> None:
        """Test status icon for open."""
        from spectryn.cli.tui.widgets import get_status_icon

        assert get_status_icon(Status.OPEN) == "📝"

    def test_get_status_color_done(self) -> None:
        """Test status color for done."""
        from spectryn.cli.tui.widgets import get_status_color

        assert get_status_color(Status.DONE) == "success"

    def test_get_status_color_in_progress(self) -> None:
        """Test status color for in progress."""
        from spectryn.cli.tui.widgets import get_status_color

        assert get_status_color(Status.IN_PROGRESS) == "warning"

    def test_get_status_color_planned(self) -> None:
        """Test status color for planned."""
        from spectryn.cli.tui.widgets import get_status_color

        assert get_status_color(Status.PLANNED) == "primary"

    def test_get_status_color_open(self) -> None:
        """Test status color for open."""
        from spectryn.cli.tui.widgets import get_status_color

        assert get_status_color(Status.OPEN) == "primary"


class TestPriorityFormatting:
    """Tests for priority formatting utilities."""

    def test_get_priority_icon_critical(self) -> None:
        """Test priority icon for critical."""
        from spectryn.cli.tui.widgets import get_priority_icon

        assert get_priority_icon(Priority.CRITICAL) == "🔴"

    def test_get_priority_icon_high(self) -> None:
        """Test priority icon for high."""
        from spectryn.cli.tui.widgets import get_priority_icon

        assert get_priority_icon(Priority.HIGH) == "🟡"

    def test_get_priority_icon_medium(self) -> None:
        """Test priority icon for medium."""
        from spectryn.cli.tui.widgets import get_priority_icon

        assert get_priority_icon(Priority.MEDIUM) == "🟢"

    def test_get_priority_icon_low(self) -> None:
        """Test priority icon for low."""
        from spectryn.cli.tui.widgets import get_priority_icon

        assert get_priority_icon(Priority.LOW) == "🔵"


class TestTextualAvailability:
    """Tests for Textual availability detection."""

    def test_textual_import_check(self) -> None:
        """Test that TEXTUAL_AVAILABLE is set correctly."""
        from spectryn.cli.tui.widgets import TEXTUAL_AVAILABLE

        # This should be True or False depending on whether textual is installed
        assert isinstance(TEXTUAL_AVAILABLE, bool)


class TestAppTextualAvailability:
    """Tests for app-level Textual availability."""

    def test_check_textual_available_function(self) -> None:
        """Test the check_textual_available function."""
        from spectryn.cli.tui.app import check_textual_available

        result = check_textual_available()
        assert isinstance(result, bool)
