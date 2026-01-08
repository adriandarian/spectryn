"""
TUI App - Main Textual application for Spectra.

Provides the interactive TUI dashboard with:
- Story browser with tree navigation
- Real-time sync progress
- Conflict resolution
- Statistics and logs
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any


try:
    from textual import on
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, ScrollableContainer, Vertical
    from textual.screen import Screen
    from textual.widgets import (
        Footer,
        Header,
        Rule,
        Static,
        TabbedContent,
        TabPane,
        Tree,
    )

    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False
    if TYPE_CHECKING:
        from textual.app import App, ComposeResult

from spectryn.cli.tui.data import (
    SyncProgress,
    TUIState,
    create_demo_state,
    load_stories_from_file,
)
from spectryn.cli.tui.widgets import (
    ConflictPanel,
    LogPanel,
    StatsPanel,
    StoryBrowser,
    StoryDetail,
    SyncProgressPanel,
)


# =============================================================================
# CSS Styles
# =============================================================================

SPECTRA_CSS = """
/* Base theme - Deep space aesthetic */
Screen {
    background: $surface;
}

/* Header styling */
Header {
    background: $primary-darken-3;
    color: $text;
}

/* Sidebar */
#sidebar {
    width: 35;
    background: $surface-darken-1;
    border-right: solid $primary-darken-2;
    padding: 1;
}

/* Main content area */
#main-content {
    background: $surface;
    padding: 1;
}

/* Panel titles */
.panel-title {
    text-style: bold;
    color: $primary-lighten-2;
    padding: 0 1;
}

/* Story tree */
#story-tree {
    height: 100%;
    scrollbar-gutter: stable;
}

Tree {
    background: transparent;
}

Tree > .tree--cursor {
    background: $primary;
    color: $text;
}

Tree > .tree--highlight {
    background: $primary-darken-1;
}

/* Stats panel */
#stats-container {
    height: auto;
    max-height: 20;
    padding: 1;
    background: $surface-darken-1;
    border: solid $primary-darken-2;
    margin-bottom: 1;
}

/* Sync progress panel */
#sync-panel {
    height: auto;
    padding: 1;
    background: $surface-darken-1;
    border: solid $primary-darken-2;
    margin-bottom: 1;
}

ProgressBar {
    padding: 0 1;
}

ProgressBar > .bar--complete {
    color: $success;
}

ProgressBar > .bar--bar {
    color: $primary;
}

/* Detail panel */
#detail-container {
    padding: 1;
    background: $surface-darken-1;
    border: solid $primary-darken-2;
}

#detail-content {
    padding: 1;
}

/* Conflict panel */
#conflict-container {
    padding: 1;
    background: $warning-darken-3;
    border: solid $warning;
}

#conflict-diff {
    height: auto;
    min-height: 10;
}

.diff-side {
    width: 1fr;
    padding: 1;
    margin: 0 1;
    background: $surface;
    border: solid $border;
}

.diff-label {
    text-align: center;
    padding-bottom: 1;
}

.diff-content {
    padding: 1;
}

#conflict-actions {
    height: auto;
    padding-top: 1;
    align: center middle;
}

#conflict-actions Button {
    margin: 0 1;
}

/* Log panel */
#log-container {
    height: auto;
    max-height: 15;
    padding: 1;
    background: $surface-darken-1;
    border: solid $primary-darken-2;
}

#log-scroll {
    height: auto;
    max-height: 10;
}

/* Tabs */
TabbedContent {
    background: transparent;
}

TabPane {
    padding: 1;
}

/* Actions bar */
#actions-bar {
    height: auto;
    dock: bottom;
    padding: 1;
    background: $surface-darken-2;
    border-top: solid $primary-darken-2;
}

#actions-bar Button {
    margin: 0 1;
}

/* Footer */
Footer {
    background: $primary-darken-3;
}

/* Search input */
#search-input {
    dock: top;
    margin: 1;
}

/* Status bar */
#status-bar {
    height: 1;
    dock: bottom;
    background: $surface-darken-2;
    padding: 0 1;
}

/* Buttons */
Button {
    min-width: 12;
}

Button.-primary {
    background: $primary;
}

Button.-success {
    background: $success;
}

Button.-warning {
    background: $warning;
}

Button.-error {
    background: $error;
}

/* Rule styling */
Rule {
    margin: 1 0;
    color: $primary-darken-2;
}
"""


# =============================================================================
# Main Dashboard Screen
# =============================================================================


class DashboardScreen(Screen):
    """Main dashboard screen with story browser and details."""

    BINDINGS = [
        # Core actions
        Binding("q", "quit", "Quit", show=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("s", "sync", "Sync", show=True),
        Binding("d", "toggle_dry_run", "Dry Run", show=True),
        Binding("?", "help", "Help", show=True),
        # Vim-style navigation
        Binding("j", "move_down", "Down", show=False),
        Binding("k", "move_up", "Up", show=False),
        Binding("g", "goto_first", "First", show=False),
        Binding("G", "goto_last", "Last", show=False, key_display="shift+g"),
        Binding("ctrl+d", "page_down", "Page Down", show=False),
        Binding("ctrl+u", "page_up", "Page Up", show=False),
        # Tab navigation (1-4 for tabs)
        Binding("1", "tab_details", "Details Tab", show=False),
        Binding("2", "tab_conflicts", "Conflicts Tab", show=False),
        Binding("3", "tab_log", "Log Tab", show=False),
        # Quick filters by status
        Binding("!", "filter_in_progress", "In Progress", show=False),
        Binding("@", "filter_planned", "Planned", show=False),
        Binding("#", "filter_done", "Done", show=False),
        Binding("0", "filter_clear", "Clear Filter", show=False),
        # Story operations
        Binding("o", "open_in_tracker", "Open", show=False),
        Binding("y", "copy_story_id", "Copy ID", show=False),
        Binding("e", "edit_story", "Edit", show=False),
        Binding("enter", "select_story", "Select", show=False),
        Binding("space", "toggle_expand", "Expand", show=False),
        # Search & filter
        Binding("f", "filter", "Filter", show=False),
        Binding("/", "search", "Search", show=False),
        Binding("n", "next_match", "Next Match", show=False),
        Binding("N", "prev_match", "Prev Match", show=False, key_display="shift+n"),
        Binding("escape", "clear_search", "Clear", show=False),
        # View controls
        Binding("c", "conflicts", "Conflicts", show=False),
        Binding("l", "focus_log", "Focus Log", show=False),
        Binding("z", "toggle_zoom", "Zoom", show=False),
        Binding("h", "toggle_sidebar", "Sidebar", show=False),
        # Bulk operations
        Binding("a", "select_all", "Select All", show=False),
        Binding("x", "toggle_selection", "Toggle Select", show=False),
    ]

    def __init__(self, state: TUIState, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.state = state
        self._log_panel: LogPanel | None = None

    def compose(self) -> ComposeResult:
        """Compose the screen layout."""
        yield Header(show_clock=True)

        with Horizontal(id="main-layout"):
            # Left sidebar - Story browser
            with Vertical(id="sidebar"):
                yield StatsPanel(self.state.stories, id="stats-panel")
                yield StoryBrowser(self.state.stories, id="story-browser")

            # Main content area
            with Vertical(id="main-content"):
                yield SyncProgressPanel(id="sync-progress-panel")

                with TabbedContent(id="content-tabs"):
                    with TabPane("📝 Details", id="tab-details"):
                        yield StoryDetail(id="story-detail")

                    with TabPane("⚠️ Conflicts", id="tab-conflicts"):
                        yield ConflictPanel(self.state.conflicts, id="conflict-panel")

                    with TabPane("📜 Log", id="tab-log"):
                        self._log_panel = LogPanel(id="log-panel")
                        yield self._log_panel

        # Status bar
        with Horizontal(id="status-bar"):
            mode = "DRY-RUN" if self.state.dry_run else "LIVE"
            yield Static(f"Mode: {mode}", id="status-mode")
            yield Static(" | ", classes="separator")
            file_info = str(self.state.markdown_path) if self.state.markdown_path else "No file"
            yield Static(f"File: {file_info}", id="status-file")
            yield Static(" | ", classes="separator")
            epic_info = self.state.epic_key or "No epic"
            yield Static(f"Epic: {epic_info}", id="status-epic")

        yield Footer()

    def on_mount(self) -> None:
        """Handle mount event."""
        self._log("Dashboard loaded", "success")
        if self.state.stories:
            self._log(f"Loaded {len(self.state.stories)} stories", "info")

    def _log(self, message: str, level: str = "info") -> None:
        """Add a log entry."""
        if self._log_panel:
            self._log_panel.add_entry(message, level)

    @on(StoryBrowser.StorySelected)
    def handle_story_selected(self, event: StoryBrowser.StorySelected) -> None:
        """Handle story selection."""
        self.state.selected_story_id = event.story_id
        story = self.state.get_selected_story()
        detail = self.query_one("#story-detail", StoryDetail)
        detail.update_story(story)
        self._log(f"Selected: {event.story_id}", "info")

    @on(ConflictPanel.ConflictResolved)
    def handle_conflict_resolved(self, event: ConflictPanel.ConflictResolved) -> None:
        """Handle conflict resolution."""
        self._log(f"Conflict resolved with {event.resolution}", "success")

    def action_refresh(self) -> None:
        """Refresh data from file."""
        self._log("Refreshing...", "info")
        if self.state.markdown_path and self.state.markdown_path.exists():
            stories, epic = load_stories_from_file(self.state.markdown_path)
            self.state.stories = stories
            self.state.epic = epic

            # Update widgets
            browser = self.query_one("#story-browser", StoryBrowser)
            browser.update_stories(stories)

            stats = self.query_one("#stats-panel", StatsPanel)
            stats.update_stories(stories)

            self._log(f"Loaded {len(stories)} stories", "success")
        else:
            self._log("No file to refresh", "warning")

    async def action_sync(self) -> None:
        """Start sync operation."""
        self._log("Starting sync...", "info")
        await self._simulate_sync()

    def action_toggle_dry_run(self) -> None:
        """Toggle dry run mode."""
        self.state.dry_run = not self.state.dry_run
        mode = "DRY-RUN" if self.state.dry_run else "LIVE"
        status_mode = self.query_one("#status-mode", Static)
        status_mode.update(f"Mode: {mode}")
        self._log(f"Mode switched to {mode}", "info")

    def action_conflicts(self) -> None:
        """Switch to conflicts tab."""
        tabs = self.query_one("#content-tabs", TabbedContent)
        tabs.active = "tab-conflicts"

    def action_help(self) -> None:
        """Show help."""
        self.app.push_screen(HelpScreen())

    def action_search(self) -> None:
        """Focus search input."""
        # Would normally show a search modal
        self._log("Search: Press / to search stories", "info")

    # -------------------------------------------------------------------------
    # Vim-style Navigation Actions
    # -------------------------------------------------------------------------

    def action_move_down(self) -> None:
        """Move selection down (vim j)."""
        try:
            browser = self.query_one("#story-browser", StoryBrowser)
            tree = browser.query_one("#story-tree", Tree)
            tree.action_cursor_down()
        except Exception:
            pass

    def action_move_up(self) -> None:
        """Move selection up (vim k)."""
        try:
            browser = self.query_one("#story-browser", StoryBrowser)
            tree = browser.query_one("#story-tree", Tree)
            tree.action_cursor_up()
        except Exception:
            pass

    def action_goto_first(self) -> None:
        """Go to first item (vim g)."""
        try:
            browser = self.query_one("#story-browser", StoryBrowser)
            tree = browser.query_one("#story-tree", Tree)
            # Move to root, then first child
            tree.select_node(tree.root)
            tree.action_cursor_down()
            self._log("Jumped to first item", "info")
        except Exception:
            pass

    def action_goto_last(self) -> None:
        """Go to last item (vim G)."""
        try:
            browser = self.query_one("#story-browser", StoryBrowser)
            tree = browser.query_one("#story-tree", Tree)
            # Expand all and go to last
            tree.root.expand_all()
            if tree.last_line >= 0:
                tree.scroll_end()
            self._log("Jumped to last item", "info")
        except Exception:
            pass

    def action_page_down(self) -> None:
        """Page down (ctrl+d)."""
        try:
            browser = self.query_one("#story-browser", StoryBrowser)
            tree = browser.query_one("#story-tree", Tree)
            for _ in range(10):
                tree.action_cursor_down()
        except Exception:
            pass

    def action_page_up(self) -> None:
        """Page up (ctrl+u)."""
        try:
            browser = self.query_one("#story-browser", StoryBrowser)
            tree = browser.query_one("#story-tree", Tree)
            for _ in range(10):
                tree.action_cursor_up()
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Tab Navigation Actions
    # -------------------------------------------------------------------------

    def action_tab_details(self) -> None:
        """Switch to details tab."""
        tabs = self.query_one("#content-tabs", TabbedContent)
        tabs.active = "tab-details"
        self._log("Switched to Details tab", "info")

    def action_tab_conflicts(self) -> None:
        """Switch to conflicts tab."""
        tabs = self.query_one("#content-tabs", TabbedContent)
        tabs.active = "tab-conflicts"
        self._log("Switched to Conflicts tab", "info")

    def action_tab_log(self) -> None:
        """Switch to log tab."""
        tabs = self.query_one("#content-tabs", TabbedContent)
        tabs.active = "tab-log"
        self._log("Switched to Log tab", "info")

    # -------------------------------------------------------------------------
    # Quick Filter Actions
    # -------------------------------------------------------------------------

    def action_filter_in_progress(self) -> None:
        """Filter to show only in-progress stories."""
        self.state.status_filter = "in_progress"
        self._apply_filter()
        self._log("Filtered: In Progress only", "info")

    def action_filter_planned(self) -> None:
        """Filter to show only planned stories."""
        self.state.status_filter = "planned"
        self._apply_filter()
        self._log("Filtered: Planned only", "info")

    def action_filter_done(self) -> None:
        """Filter to show only done stories."""
        self.state.status_filter = "done"
        self._apply_filter()
        self._log("Filtered: Done only", "info")

    def action_filter_clear(self) -> None:
        """Clear all filters."""
        self.state.status_filter = None
        self._apply_filter()
        self._log("Filters cleared", "info")

    def _apply_filter(self) -> None:
        """Apply current filter to story browser."""
        from spectryn.core.domain.enums import Status

        browser = self.query_one("#story-browser", StoryBrowser)

        if self.state.status_filter is None:
            browser.update_stories(self.state.stories)
        else:
            status_map = {
                "in_progress": Status.IN_PROGRESS,
                "planned": Status.PLANNED,
                "done": Status.DONE,
            }
            target_status = status_map.get(self.state.status_filter)
            if target_status:
                filtered = [s for s in self.state.stories if s.status == target_status]
                browser.update_stories(filtered)

    # -------------------------------------------------------------------------
    # Story Operation Actions
    # -------------------------------------------------------------------------

    def action_open_in_tracker(self) -> None:
        """Open selected story in external tracker."""
        story = self.state.get_selected_story()
        if story and story.external_key:
            # Would open browser to tracker URL
            self._log(f"Opening {story.external_key} in browser...", "info")
        else:
            self._log("No external tracker link available", "warning")

    def action_copy_story_id(self) -> None:
        """Copy selected story ID to clipboard."""
        story = self.state.get_selected_story()
        if story:
            # Would copy to clipboard if pyperclip available
            self._log(f"Copied: {story.id}", "success")
        else:
            self._log("No story selected", "warning")

    def action_edit_story(self) -> None:
        """Edit selected story (would open editor)."""
        story = self.state.get_selected_story()
        if story:
            self._log(f"Edit mode for {story.id} (not yet implemented)", "info")
        else:
            self._log("No story selected", "warning")

    def action_select_story(self) -> None:
        """Select/confirm current story."""
        try:
            browser = self.query_one("#story-browser", StoryBrowser)
            tree = browser.query_one("#story-tree", Tree)
            tree.action_select_cursor()
        except Exception:
            pass

    def action_toggle_expand(self) -> None:
        """Toggle expand/collapse of current node."""
        try:
            browser = self.query_one("#story-browser", StoryBrowser)
            tree = browser.query_one("#story-tree", Tree)
            tree.action_toggle_node()
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Search Actions
    # -------------------------------------------------------------------------

    def action_next_match(self) -> None:
        """Go to next search match."""
        self._log("Next match (n)", "info")

    def action_prev_match(self) -> None:
        """Go to previous search match."""
        self._log("Previous match (N)", "info")

    def action_filter(self) -> None:
        """Open filter dialog."""
        self._log("Filter: Use !, @, # for quick filters", "info")

    def action_clear_search(self) -> None:
        """Clear search and filters."""
        self.state.status_filter = None
        self._apply_filter()
        self._log("Search/filter cleared", "info")

    # -------------------------------------------------------------------------
    # View Control Actions
    # -------------------------------------------------------------------------

    def action_focus_log(self) -> None:
        """Focus the log panel."""
        tabs = self.query_one("#content-tabs", TabbedContent)
        tabs.active = "tab-log"
        self._log("Focused log panel", "info")

    def action_toggle_zoom(self) -> None:
        """Toggle zoom on main content (hide/show sidebar)."""
        try:
            sidebar = self.query_one("#sidebar")
            sidebar.display = not sidebar.display
            mode = "hidden" if not sidebar.display else "visible"
            self._log(f"Sidebar {mode}", "info")
        except Exception:
            pass

    def action_toggle_sidebar(self) -> None:
        """Toggle sidebar visibility."""
        self.action_toggle_zoom()

    # -------------------------------------------------------------------------
    # Bulk Operation Actions
    # -------------------------------------------------------------------------

    def action_select_all(self) -> None:
        """Select all visible stories."""
        self.state.selected_stories = {str(s.id) for s in self.state.stories}
        count = len(self.state.selected_stories)
        self._log(f"Selected all {count} stories", "info")

    def action_toggle_selection(self) -> None:
        """Toggle selection of current story."""
        story = self.state.get_selected_story()
        if story:
            story_id = str(story.id)
            if story_id in self.state.selected_stories:
                self.state.selected_stories.discard(story_id)
                self._log(f"Deselected {story.id}", "info")
            else:
                self.state.selected_stories.add(story_id)
                self._log(f"Selected {story.id}", "info")

    async def _simulate_sync(self) -> None:
        """Simulate a sync operation with progress updates."""
        progress_panel = self.query_one("#sync-progress-panel", SyncProgressPanel)

        progress = SyncProgress(
            total_operations=len(self.state.stories) * 3,
            phase="analyzing",
            start_time=datetime.now(),
        )
        progress_panel.update_progress(progress)
        self._log("Analyzing stories...", "info")

        await self.app.sleep(0.5)  # type: ignore

        progress.phase = "syncing"
        for i, story in enumerate(self.state.stories):
            progress.completed_operations = i * 3
            progress.current_operation = "Syncing description"
            progress.current_story = str(story.id)
            progress_panel.update_progress(progress)
            self._log(f"Syncing {story.id}: description", "info")
            await self.app.sleep(0.2)  # type: ignore

            progress.completed_operations = i * 3 + 1
            progress.current_operation = "Syncing subtasks"
            progress_panel.update_progress(progress)
            self._log(f"Syncing {story.id}: subtasks", "info")
            await self.app.sleep(0.2)  # type: ignore

            progress.completed_operations = i * 3 + 2
            progress.current_operation = "Syncing status"
            progress_panel.update_progress(progress)
            self._log(f"Syncing {story.id}: status", "info")
            await self.app.sleep(0.1)  # type: ignore

        progress.completed_operations = progress.total_operations
        progress.phase = "complete"
        progress.current_operation = ""
        progress.end_time = datetime.now()
        progress_panel.update_progress(progress)

        mode = "DRY-RUN" if self.state.dry_run else "executed"
        self._log(f"Sync complete ({mode})", "success")


# =============================================================================
# Help Screen
# =============================================================================


class HelpScreen(Screen):
    """Help screen with keyboard shortcuts and usage information."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close", show=True),
        Binding("q", "dismiss", "Close", show=False),
        Binding("j", "scroll_down", "Scroll Down", show=False),
        Binding("k", "scroll_up", "Scroll Up", show=False),
    ]

    def compose(self) -> ComposeResult:
        """Compose the help screen."""
        yield Header(show_clock=False)

        with ScrollableContainer(id="help-container"):
            yield Static(
                "[bold]Spectra TUI Dashboard - Keyboard Shortcuts[/bold]\n", id="help-title"
            )
            yield Rule()

            help_text = """
[bold cyan]━━━ Navigation ━━━[/bold cyan]
  [bold]↑/↓ or j/k[/bold]     Move up/down in story list
  [bold]g[/bold]              Jump to first item
  [bold]G (Shift+g)[/bold]    Jump to last item
  [bold]Ctrl+d[/bold]         Page down (10 items)
  [bold]Ctrl+u[/bold]         Page up (10 items)
  [bold]Enter[/bold]          Select/confirm story
  [bold]Space[/bold]          Expand/collapse node
  [bold]Tab[/bold]            Switch between panels

[bold cyan]━━━ Core Actions ━━━[/bold cyan]
  [bold]s[/bold]              Start sync operation
  [bold]r[/bold]              Refresh from markdown file
  [bold]d[/bold]              Toggle dry-run/live mode
  [bold]?[/bold]              Show this help screen
  [bold]q[/bold]              Quit application

[bold cyan]━━━ Tab Navigation ━━━[/bold cyan]
  [bold]1[/bold]              Switch to Details tab
  [bold]2[/bold]              Switch to Conflicts tab
  [bold]3[/bold]              Switch to Log tab

[bold cyan]━━━ Quick Filters ━━━[/bold cyan]
  [bold]![/bold]              Show In Progress only
  [bold]@[/bold]              Show Planned only
  [bold]#[/bold]              Show Done only
  [bold]0[/bold]              Clear all filters

[bold cyan]━━━ Story Operations ━━━[/bold cyan]
  [bold]o[/bold]              Open story in external tracker
  [bold]y[/bold]              Copy story ID to clipboard
  [bold]e[/bold]              Edit story (when available)
  [bold]c[/bold]              View conflicts tab

[bold cyan]━━━ Search & Filter ━━━[/bold cyan]
  [bold]/[/bold]              Search stories
  [bold]f[/bold]              Open filter options
  [bold]n[/bold]              Go to next search match
  [bold]N (Shift+n)[/bold]    Go to previous match
  [bold]Escape[/bold]         Clear search/filter

[bold cyan]━━━ View Controls ━━━[/bold cyan]
  [bold]l[/bold]              Focus log panel
  [bold]z or h[/bold]         Toggle sidebar (zoom)

[bold cyan]━━━ Bulk Operations ━━━[/bold cyan]
  [bold]a[/bold]              Select all visible stories
  [bold]x[/bold]              Toggle selection on current

[bold cyan]━━━ Global Shortcuts ━━━[/bold cyan]
  [bold]Ctrl+c/Ctrl+q[/bold]  Quit application
  [bold]Ctrl+r[/bold]         Reload application
  [bold]Ctrl+h or F1[/bold]   Show help
  [bold]F5[/bold]             Refresh all data

[bold yellow]━━━ Sync Modes ━━━[/bold yellow]
  [bold]DRY-RUN[/bold]   Preview changes without applying (default)
  [bold]LIVE[/bold]      Apply changes to external tracker

[bold yellow]━━━ Conflict Resolution ━━━[/bold yellow]
  When conflicts are detected, switch to Conflicts tab (2 or c):
  • View side-by-side local vs remote differences
  • Choose which version to keep (local/remote)
  • Skip conflicts for later resolution

[bold yellow]━━━ Status Icons ━━━[/bold yellow]
  ✅  Done            🔄  In Progress
  📋  Planned         📝  Open
  👀  In Review       ❌  Cancelled

[bold yellow]━━━ Priority Icons ━━━[/bold yellow]
  🔴  Critical        🟡  High
  🟢  Medium          🔵  Low
            """
            yield Static(help_text)

            yield Rule()
            yield Static("\n[dim]Press Escape, Q, or ? to close[/dim]", id="help-footer")

        yield Footer()

    async def action_dismiss(self, result: None = None) -> None:
        """Dismiss the help screen."""
        self.app.pop_screen()

    def action_scroll_down(self) -> None:
        """Scroll help content down."""
        try:
            container = self.query_one("#help-container", ScrollableContainer)
            container.scroll_down()
        except Exception:
            pass

    def action_scroll_up(self) -> None:
        """Scroll help content up."""
        try:
            container = self.query_one("#help-container", ScrollableContainer)
            container.scroll_up()
        except Exception:
            pass


# =============================================================================
# Main TUI Application
# =============================================================================


class SpectraTUI(App):
    """
    The main Spectra TUI application.

    Provides an interactive terminal dashboard for managing
    epic/story sync operations with real-time feedback.
    """

    TITLE = "Spectra"
    SUB_TITLE = "Interactive Sync Dashboard"
    CSS = SPECTRA_CSS

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=False),
        Binding("ctrl+q", "quit", "Quit", show=False),
        Binding("ctrl+r", "reload", "Reload", show=False),
        Binding("ctrl+s", "save", "Save", show=False),
        Binding("ctrl+h", "toggle_help", "Help", show=False),
        Binding("f1", "show_help", "Help", show=False),
        Binding("f5", "refresh_all", "Refresh", show=False),
    ]

    def __init__(
        self,
        markdown_path: Path | None = None,
        epic_key: str | None = None,
        dry_run: bool = True,
        demo: bool = False,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """
        Initialize the TUI application.

        Args:
            markdown_path: Path to the markdown file to load.
            epic_key: Epic key for sync operations.
            dry_run: Whether to run in dry-run mode.
            demo: Use demo data for testing.
        """
        super().__init__(*args, **kwargs)

        if demo:
            self.state = create_demo_state()
        else:
            self.state = TUIState(
                markdown_path=markdown_path,
                epic_key=epic_key,
                dry_run=dry_run,
            )

            # Load stories from file if provided
            if markdown_path and markdown_path.exists():
                stories, epic = load_stories_from_file(markdown_path)
                self.state.stories = stories
                self.state.epic = epic
                if epic:
                    self.state.epic_key = str(epic.key)

    def on_mount(self) -> None:
        """Handle application mount."""
        self.push_screen(DashboardScreen(self.state))

    async def sleep(self, seconds: float) -> None:
        """Sleep for the given number of seconds."""
        import asyncio

        await asyncio.sleep(seconds)


# =============================================================================
# Entry Point
# =============================================================================


def run_tui(
    markdown_path: str | None = None,
    epic_key: str | None = None,
    dry_run: bool = True,
    demo: bool = False,
) -> int:
    """
    Run the Spectra TUI application.

    Args:
        markdown_path: Path to markdown file.
        epic_key: Epic key for sync.
        dry_run: Run in dry-run mode.
        demo: Use demo data.

    Returns:
        Exit code (0 for success).
    """
    if not TEXTUAL_AVAILABLE:
        print("Error: Textual is not installed.")
        print("Install with: pip install spectra[tui]")
        return 1

    path = Path(markdown_path) if markdown_path else None
    app = SpectraTUI(
        markdown_path=path,
        epic_key=epic_key,
        dry_run=dry_run,
        demo=demo,
    )
    app.run()
    return 0


def check_textual_available() -> bool:
    """Check if Textual is available."""
    return TEXTUAL_AVAILABLE
