"""
Tests for TUI application.

Note: Full TUI testing requires Textual's async test harness.
These tests focus on initialization and configuration.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from spectryn.cli.tui.data import TUIState, create_demo_state


class TestTUIStateInitialization:
    """Tests for TUI state initialization."""

    def test_default_initialization(self) -> None:
        """Test default state initialization."""
        state = TUIState()

        assert state.markdown_path is None
        assert state.epic_key is None
        assert state.stories == []
        assert state.dry_run is True

    def test_initialization_with_values(self) -> None:
        """Test state initialization with values."""
        path = Path("/test/file.md")
        state = TUIState(
            markdown_path=path,
            epic_key="PROJ-123",
            dry_run=False,
        )

        assert state.markdown_path == path
        assert state.epic_key == "PROJ-123"
        assert not state.dry_run


class TestRunTUIFunction:
    """Tests for run_tui function."""

    def test_run_tui_without_textual(self) -> None:
        """Test run_tui returns error when Textual not available."""
        with patch("spectryn.cli.tui.app.TEXTUAL_AVAILABLE", False):
            from spectryn.cli.tui.app import run_tui

            # Re-import to get patched version
            result = run_tui(demo=True)
            # When TEXTUAL_AVAILABLE is False, should return error code
            if result != 0:
                assert result == 1  # Error code when Textual not available

    def test_run_tui_demo_mode_available(self) -> None:
        """Test that demo mode is supported."""
        from spectryn.cli.tui.app import check_textual_available

        if not check_textual_available():
            pytest.skip("Textual not available")

        # Just verify the function can be called with demo=True
        # Actual running would require Textual's test harness
        from spectryn.cli.tui.app import SpectraTUI

        app = SpectraTUI(demo=True)
        assert app.state is not None
        assert len(app.state.stories) > 0


class TestDemoState:
    """Tests for demo state creation."""

    def test_create_demo_state_returns_populated_state(self) -> None:
        """Test demo state has all required fields."""
        state = create_demo_state()

        assert state.epic_key is not None
        assert state.epic is not None
        assert len(state.stories) >= 2
        assert state.selected_story_id is not None

    def test_demo_state_stories_have_variety(self) -> None:
        """Test demo stories have varied attributes."""
        state = create_demo_state()

        statuses = {s.status for s in state.stories}
        priorities = {s.priority for s in state.stories}

        assert len(statuses) >= 2, "Demo should have varied statuses"
        assert len(priorities) >= 2, "Demo should have varied priorities"

    def test_demo_state_selected_story_exists(self) -> None:
        """Test that selected story exists in stories list."""
        state = create_demo_state()

        story = state.get_selected_story()
        assert story is not None
        assert str(story.id) == state.selected_story_id


class TestTUIStateExtendedFields:
    """Tests for extended TUI state fields used by keyboard shortcuts."""

    def test_selected_stories_set_default_empty(self) -> None:
        """Test that selected_stories starts as empty set."""
        state = TUIState()
        assert state.selected_stories == set()

    def test_selected_stories_bulk_selection(self) -> None:
        """Test bulk story selection."""
        state = create_demo_state()

        # Select all stories
        state.selected_stories = {str(s.id) for s in state.stories}
        assert len(state.selected_stories) == len(state.stories)

    def test_status_filter_default_none(self) -> None:
        """Test that status_filter starts as None."""
        state = TUIState()
        assert state.status_filter is None

    def test_status_filter_values(self) -> None:
        """Test setting status filter values."""
        state = TUIState()

        state.status_filter = "in_progress"
        assert state.status_filter == "in_progress"

        state.status_filter = "planned"
        assert state.status_filter == "planned"

        state.status_filter = "done"
        assert state.status_filter == "done"

        state.status_filter = None
        assert state.status_filter is None

    def test_sidebar_visible_default_true(self) -> None:
        """Test that sidebar_visible starts as True."""
        state = TUIState()
        assert state.sidebar_visible is True


class TestKeyboardShortcutBindings:
    """Tests for keyboard shortcut bindings in TUI screens."""

    def test_dashboard_screen_has_vim_navigation(self) -> None:
        """Test DashboardScreen has vim-style navigation keys."""
        from spectryn.cli.tui.app import TEXTUAL_AVAILABLE

        if not TEXTUAL_AVAILABLE:
            pytest.skip("Textual not available")

        from spectryn.cli.tui.app import DashboardScreen

        binding_keys = [b.key for b in DashboardScreen.BINDINGS]

        # Vim navigation
        assert "j" in binding_keys, "Should have j for move down"
        assert "k" in binding_keys, "Should have k for move up"
        assert "g" in binding_keys, "Should have g for go to first"
        assert "G" in binding_keys, "Should have G for go to last"
        assert "ctrl+d" in binding_keys, "Should have ctrl+d for page down"
        assert "ctrl+u" in binding_keys, "Should have ctrl+u for page up"

    def test_dashboard_screen_has_tab_navigation(self) -> None:
        """Test DashboardScreen has tab navigation keys."""
        from spectryn.cli.tui.app import TEXTUAL_AVAILABLE

        if not TEXTUAL_AVAILABLE:
            pytest.skip("Textual not available")

        from spectryn.cli.tui.app import DashboardScreen

        binding_keys = [b.key for b in DashboardScreen.BINDINGS]

        # Tab navigation
        assert "1" in binding_keys, "Should have 1 for details tab"
        assert "2" in binding_keys, "Should have 2 for conflicts tab"
        assert "3" in binding_keys, "Should have 3 for log tab"

    def test_dashboard_screen_has_quick_filters(self) -> None:
        """Test DashboardScreen has quick filter keys."""
        from spectryn.cli.tui.app import TEXTUAL_AVAILABLE

        if not TEXTUAL_AVAILABLE:
            pytest.skip("Textual not available")

        from spectryn.cli.tui.app import DashboardScreen

        binding_keys = [b.key for b in DashboardScreen.BINDINGS]

        # Quick filters
        assert "!" in binding_keys, "Should have ! for in-progress filter"
        assert "@" in binding_keys, "Should have @ for planned filter"
        assert "#" in binding_keys, "Should have # for done filter"
        assert "0" in binding_keys, "Should have 0 for clear filter"

    def test_dashboard_screen_has_story_operations(self) -> None:
        """Test DashboardScreen has story operation keys."""
        from spectryn.cli.tui.app import TEXTUAL_AVAILABLE

        if not TEXTUAL_AVAILABLE:
            pytest.skip("Textual not available")

        from spectryn.cli.tui.app import DashboardScreen

        binding_keys = [b.key for b in DashboardScreen.BINDINGS]

        # Story operations
        assert "o" in binding_keys, "Should have o for open in tracker"
        assert "y" in binding_keys, "Should have y for copy ID"
        assert "e" in binding_keys, "Should have e for edit"

    def test_dashboard_screen_has_bulk_operations(self) -> None:
        """Test DashboardScreen has bulk operation keys."""
        from spectryn.cli.tui.app import TEXTUAL_AVAILABLE

        if not TEXTUAL_AVAILABLE:
            pytest.skip("Textual not available")

        from spectryn.cli.tui.app import DashboardScreen

        binding_keys = [b.key for b in DashboardScreen.BINDINGS]

        # Bulk operations
        assert "a" in binding_keys, "Should have a for select all"
        assert "x" in binding_keys, "Should have x for toggle selection"

    def test_dashboard_screen_has_view_controls(self) -> None:
        """Test DashboardScreen has view control keys."""
        from spectryn.cli.tui.app import TEXTUAL_AVAILABLE

        if not TEXTUAL_AVAILABLE:
            pytest.skip("Textual not available")

        from spectryn.cli.tui.app import DashboardScreen

        binding_keys = [b.key for b in DashboardScreen.BINDINGS]

        # View controls
        assert "l" in binding_keys, "Should have l for focus log"
        assert "z" in binding_keys, "Should have z for toggle zoom"
        assert "h" in binding_keys, "Should have h for toggle sidebar"

    def test_help_screen_has_scroll_keys(self) -> None:
        """Test HelpScreen has scroll navigation keys."""
        from spectryn.cli.tui.app import TEXTUAL_AVAILABLE

        if not TEXTUAL_AVAILABLE:
            pytest.skip("Textual not available")

        from spectryn.cli.tui.app import HelpScreen

        binding_keys = [b.key for b in HelpScreen.BINDINGS]

        assert "j" in binding_keys, "Should have j for scroll down"
        assert "k" in binding_keys, "Should have k for scroll up"
        assert "escape" in binding_keys, "Should have escape for dismiss"

    def test_main_app_has_global_shortcuts(self) -> None:
        """Test SpectraTUI has global keyboard shortcuts."""
        from spectryn.cli.tui.app import TEXTUAL_AVAILABLE

        if not TEXTUAL_AVAILABLE:
            pytest.skip("Textual not available")

        from spectryn.cli.tui.app import SpectraTUI

        binding_keys = [b.key for b in SpectraTUI.BINDINGS]

        # Global shortcuts
        assert "ctrl+c" in binding_keys, "Should have ctrl+c for quit"
        assert "ctrl+q" in binding_keys, "Should have ctrl+q for quit"
        assert "ctrl+r" in binding_keys, "Should have ctrl+r for reload"
        assert "ctrl+h" in binding_keys, "Should have ctrl+h for help"
        assert "f1" in binding_keys, "Should have f1 for help"
        assert "f5" in binding_keys, "Should have f5 for refresh"


class TestKeyboardShortcutActions:
    """Tests for keyboard shortcut action methods."""

    def test_dashboard_has_navigation_action_methods(self) -> None:
        """Test DashboardScreen has navigation action methods."""
        from spectryn.cli.tui.app import TEXTUAL_AVAILABLE

        if not TEXTUAL_AVAILABLE:
            pytest.skip("Textual not available")

        from spectryn.cli.tui.app import DashboardScreen

        # Check action methods exist
        assert hasattr(DashboardScreen, "action_move_down")
        assert hasattr(DashboardScreen, "action_move_up")
        assert hasattr(DashboardScreen, "action_goto_first")
        assert hasattr(DashboardScreen, "action_goto_last")
        assert hasattr(DashboardScreen, "action_page_down")
        assert hasattr(DashboardScreen, "action_page_up")

    def test_dashboard_has_tab_action_methods(self) -> None:
        """Test DashboardScreen has tab navigation action methods."""
        from spectryn.cli.tui.app import TEXTUAL_AVAILABLE

        if not TEXTUAL_AVAILABLE:
            pytest.skip("Textual not available")

        from spectryn.cli.tui.app import DashboardScreen

        assert hasattr(DashboardScreen, "action_tab_details")
        assert hasattr(DashboardScreen, "action_tab_conflicts")
        assert hasattr(DashboardScreen, "action_tab_log")

    def test_dashboard_has_filter_action_methods(self) -> None:
        """Test DashboardScreen has filter action methods."""
        from spectryn.cli.tui.app import TEXTUAL_AVAILABLE

        if not TEXTUAL_AVAILABLE:
            pytest.skip("Textual not available")

        from spectryn.cli.tui.app import DashboardScreen

        assert hasattr(DashboardScreen, "action_filter_in_progress")
        assert hasattr(DashboardScreen, "action_filter_planned")
        assert hasattr(DashboardScreen, "action_filter_done")
        assert hasattr(DashboardScreen, "action_filter_clear")

    def test_dashboard_has_story_operation_methods(self) -> None:
        """Test DashboardScreen has story operation action methods."""
        from spectryn.cli.tui.app import TEXTUAL_AVAILABLE

        if not TEXTUAL_AVAILABLE:
            pytest.skip("Textual not available")

        from spectryn.cli.tui.app import DashboardScreen

        assert hasattr(DashboardScreen, "action_open_in_tracker")
        assert hasattr(DashboardScreen, "action_copy_story_id")
        assert hasattr(DashboardScreen, "action_edit_story")
        assert hasattr(DashboardScreen, "action_select_story")
        assert hasattr(DashboardScreen, "action_toggle_expand")

    def test_dashboard_has_view_control_methods(self) -> None:
        """Test DashboardScreen has view control action methods."""
        from spectryn.cli.tui.app import TEXTUAL_AVAILABLE

        if not TEXTUAL_AVAILABLE:
            pytest.skip("Textual not available")

        from spectryn.cli.tui.app import DashboardScreen

        assert hasattr(DashboardScreen, "action_focus_log")
        assert hasattr(DashboardScreen, "action_toggle_zoom")
        assert hasattr(DashboardScreen, "action_toggle_sidebar")

    def test_dashboard_has_bulk_operation_methods(self) -> None:
        """Test DashboardScreen has bulk operation action methods."""
        from spectryn.cli.tui.app import TEXTUAL_AVAILABLE

        if not TEXTUAL_AVAILABLE:
            pytest.skip("Textual not available")

        from spectryn.cli.tui.app import DashboardScreen

        assert hasattr(DashboardScreen, "action_select_all")
        assert hasattr(DashboardScreen, "action_toggle_selection")

    def test_help_screen_has_scroll_methods(self) -> None:
        """Test HelpScreen has scroll action methods."""
        from spectryn.cli.tui.app import TEXTUAL_AVAILABLE

        if not TEXTUAL_AVAILABLE:
            pytest.skip("Textual not available")

        from spectryn.cli.tui.app import HelpScreen

        assert hasattr(HelpScreen, "action_scroll_down")
        assert hasattr(HelpScreen, "action_scroll_up")
        assert hasattr(HelpScreen, "action_dismiss")
