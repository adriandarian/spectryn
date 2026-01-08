"""
TUI Widgets - Custom Textual widgets for the Spectra TUI.

Provides reusable widget components for:
- Story browser tree
- Progress panel
- Story detail view
- Conflict resolution
- Stats dashboard
"""

from __future__ import annotations

from typing import TYPE_CHECKING


try:
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, ScrollableContainer, Vertical
    from textual.message import Message
    from textual.reactive import reactive
    from textual.widget import Widget
    from textual.widgets import (
        Button,
        ProgressBar,
        Rule,
        Static,
        Tree,
    )

    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False
    # Provide stubs for type checking
    if TYPE_CHECKING:
        from textual.app import ComposeResult
        from textual.widget import Widget

from spectryn.core.domain.entities import UserStory
from spectryn.core.domain.enums import Priority, Status


if TYPE_CHECKING:
    from spectryn.cli.tui.data import StoryConflict, SyncProgress


# =============================================================================
# Status and Priority Formatting
# =============================================================================


def get_status_icon(status: Status) -> str:
    """Get emoji icon for a status."""
    icons = {
        Status.DONE: "✅",
        Status.IN_PROGRESS: "🔄",
        Status.PLANNED: "📋",
        Status.OPEN: "📝",
        Status.IN_REVIEW: "👀",
        Status.CANCELLED: "❌",
    }
    return icons.get(status, "❓")


def get_priority_icon(priority: Priority) -> str:
    """Get emoji icon for a priority."""
    icons = {
        Priority.CRITICAL: "🔴",
        Priority.HIGH: "🟡",
        Priority.MEDIUM: "🟢",
        Priority.LOW: "🔵",
    }
    return icons.get(priority, "⚪")


def get_status_color(status: Status) -> str:
    """Get CSS color class for a status."""
    colors = {
        Status.DONE: "success",
        Status.IN_PROGRESS: "warning",
        Status.PLANNED: "primary",
        Status.OPEN: "primary",
        Status.IN_REVIEW: "warning",
        Status.CANCELLED: "error",
    }
    return colors.get(status, "")


# =============================================================================
# Story Browser Widget
# =============================================================================


class StoryBrowser(Widget):
    """
    A tree-based story browser widget.

    Displays stories grouped by status with expandable details.
    """

    BINDINGS = [
        Binding("enter", "select", "Select"),
        Binding("space", "toggle", "Expand/Collapse"),
        Binding("f", "filter", "Filter"),
        Binding("/", "search", "Search"),
    ]

    selected_story_id: reactive[str | None] = reactive(None)

    class StorySelected(Message):
        """Message emitted when a story is selected."""

        def __init__(self, story_id: str) -> None:
            self.story_id = story_id
            super().__init__()

    def __init__(
        self,
        stories: list[UserStory] | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(id=id, classes=classes)
        self._stories = stories or []

    def compose(self) -> ComposeResult:
        """Compose the widget."""
        yield Tree("📁 Stories", id="story-tree")

    def on_mount(self) -> None:
        """Handle mount event."""
        self._refresh_tree()

    def update_stories(self, stories: list[UserStory]) -> None:
        """Update the stories displayed."""
        self._stories = stories
        self._refresh_tree()

    def _refresh_tree(self) -> None:
        """Rebuild the tree with current stories."""
        tree = self.query_one("#story-tree", Tree)
        tree.clear()

        # Group stories by status
        by_status: dict[Status, list[UserStory]] = {}
        for story in self._stories:
            status = story.status
            if status not in by_status:
                by_status[status] = []
            by_status[status].append(story)

        # Add status groups
        for status in [Status.IN_PROGRESS, Status.PLANNED, Status.OPEN, Status.DONE]:
            if status not in by_status:
                continue

            stories = by_status[status]
            icon = get_status_icon(status)
            status_node = tree.root.add(
                f"{icon} {status.display_name} ({len(stories)})",
                expand=status == Status.IN_PROGRESS,
            )

            for story in stories:
                priority_icon = get_priority_icon(story.priority)
                points = f"[{story.story_points}SP]" if story.story_points else ""
                external = f" → {story.external_key}" if story.external_key else ""
                label = f"{priority_icon} {story.id}: {story.title} {points}{external}"
                status_node.add_leaf(label, data=str(story.id))

        tree.root.expand()

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """Handle tree node selection."""
        if event.node.data:
            self.selected_story_id = event.node.data
            self.post_message(self.StorySelected(event.node.data))


# =============================================================================
# Story Detail Widget
# =============================================================================


class StoryDetail(Widget):
    """
    Displays detailed information about a selected story.

    Shows metadata, description, acceptance criteria, and subtasks.
    """

    def __init__(
        self,
        story: UserStory | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(id=id, classes=classes)
        self._story = story

    def compose(self) -> ComposeResult:
        """Compose the widget."""
        with ScrollableContainer():
            yield Static("Select a story to view details", id="detail-content")

    def update_story(self, story: UserStory | None) -> None:
        """Update the displayed story."""
        self._story = story
        self._refresh_content()

    def _refresh_content(self) -> None:
        """Refresh the content display."""
        content = self.query_one("#detail-content", Static)

        if self._story is None:
            content.update("Select a story to view details")
            return

        story = self._story
        status_icon = get_status_icon(story.status)
        priority_icon = get_priority_icon(story.priority)

        lines = [
            f"[bold]{story.id}: {story.title}[/bold]",
            "",
            f"Status: {status_icon} {story.status.display_name}",
            f"Priority: {priority_icon} {story.priority.display_name}",
            f"Story Points: {story.story_points or 'Not estimated'}",
        ]

        if story.external_key:
            lines.append(f"External: {story.external_key}")

        if story.assignee:
            lines.append(f"Assignee: {story.assignee}")

        if story.labels:
            lines.append(f"Labels: {', '.join(story.labels)}")

        # Description
        if story.description:
            lines.extend(["", "─" * 40, "[bold]Description[/bold]", ""])
            desc = (
                story.description.to_markdown()
                if hasattr(story.description, "to_markdown")
                else str(story.description)
            )
            lines.append(desc[:500] + "..." if len(desc) > 500 else desc)

        # Acceptance Criteria
        if story.acceptance_criteria and story.acceptance_criteria.items:
            lines.extend(["", "─" * 40, "[bold]Acceptance Criteria[/bold]", ""])
            for i, ac in enumerate(story.acceptance_criteria.items[:5], 1):
                lines.append(f"  {i}. {ac}")
            if len(story.acceptance_criteria.items) > 5:
                lines.append(f"  ... and {len(story.acceptance_criteria.items) - 5} more")

        # Subtasks
        if story.subtasks:
            lines.extend(["", "─" * 40, f"[bold]Subtasks ({len(story.subtasks)})[/bold]", ""])
            for subtask in story.subtasks[:10]:
                st_icon = get_status_icon(subtask.status)
                lines.append(f"  {st_icon} {subtask.name}")
            if len(story.subtasks) > 10:
                lines.append(f"  ... and {len(story.subtasks) - 10} more")

        content.update("\n".join(lines))


# =============================================================================
# Sync Progress Widget
# =============================================================================


class SyncProgressPanel(Widget):
    """
    Displays real-time sync progress.

    Shows current operation, progress bar, and status messages.
    """

    def __init__(
        self,
        progress: SyncProgress | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(id=id, classes=classes)
        self._progress: SyncProgress | None = progress

    def compose(self) -> ComposeResult:
        """Compose the widget."""
        with Vertical(id="sync-panel"):
            yield Static("⚙️ Sync Status", classes="panel-title")
            yield Rule()
            yield Static("Idle", id="sync-phase")
            yield ProgressBar(id="sync-progress", total=100, show_eta=False)
            yield Static("", id="sync-operation")
            yield Static("", id="sync-stats")

    def update_progress(self, progress: SyncProgress) -> None:
        """Update the progress display."""
        self._progress = progress
        self._refresh_display()

    def _refresh_display(self) -> None:
        """Refresh the display with current progress."""
        if self._progress is None:
            return

        progress = self._progress

        # Update phase
        phase_display = self.query_one("#sync-phase", Static)
        phase_icons = {
            "idle": "⏸️ Idle",
            "analyzing": "🔍 Analyzing...",
            "syncing": "🔄 Syncing...",
            "complete": "✅ Complete",
        }
        phase_display.update(phase_icons.get(progress.phase, progress.phase))

        # Update progress bar
        progress_bar = self.query_one("#sync-progress", ProgressBar)
        progress_bar.update(progress=progress.progress_percent)

        # Update current operation
        operation_display = self.query_one("#sync-operation", Static)
        if progress.current_operation:
            story_info = f" ({progress.current_story})" if progress.current_story else ""
            operation_display.update(f"📝 {progress.current_operation}{story_info}")
        else:
            operation_display.update("")

        # Update stats
        stats_display = self.query_one("#sync-stats", Static)
        elapsed = f"{progress.elapsed_time:.1f}s" if progress.elapsed_time > 0 else ""
        stats_parts = []

        if progress.completed_operations > 0 or progress.total_operations > 0:
            stats_parts.append(
                f"Progress: {progress.completed_operations}/{progress.total_operations}"
            )

        if elapsed:
            stats_parts.append(f"Time: {elapsed}")

        if progress.errors:
            stats_parts.append(f"[red]Errors: {len(progress.errors)}[/red]")

        if progress.warnings:
            stats_parts.append(f"[yellow]Warnings: {len(progress.warnings)}[/yellow]")

        stats_display.update(" | ".join(stats_parts))


# =============================================================================
# Stats Panel Widget
# =============================================================================


class StatsPanel(Widget):
    """
    Displays summary statistics for stories.

    Shows counts by status, total points, completion percentage.
    """

    def __init__(
        self,
        stories: list[UserStory] | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(id=id, classes=classes)
        self._stories = stories or []

    def compose(self) -> ComposeResult:
        """Compose the widget."""
        with Vertical(id="stats-container"):
            yield Static("📊 Statistics", classes="panel-title")
            yield Rule()
            yield Static("", id="stats-content")

    def on_mount(self) -> None:
        """Handle mount event."""
        self._refresh_stats()

    def update_stories(self, stories: list[UserStory]) -> None:
        """Update the stories for stats calculation."""
        self._stories = stories
        self._refresh_stats()

    def _refresh_stats(self) -> None:
        """Refresh the stats display."""
        content = self.query_one("#stats-content", Static)

        if not self._stories:
            content.update("No stories loaded")
            return

        total = len(self._stories)
        done = len([s for s in self._stories if s.status == Status.DONE])
        in_progress = len([s for s in self._stories if s.status == Status.IN_PROGRESS])
        planned = len([s for s in self._stories if s.status == Status.PLANNED])
        in_review = len([s for s in self._stories if s.status == Status.IN_REVIEW])

        total_points = sum((s.story_points or 0) for s in self._stories)
        done_points = sum((s.story_points or 0) for s in self._stories if s.status == Status.DONE)

        completion = (done / total * 100) if total > 0 else 0
        points_completion = (done_points / total_points * 100) if total_points > 0 else 0

        synced = len([s for s in self._stories if s.external_key is not None])

        lines = [
            f"Total Stories: [bold]{total}[/bold]",
            f"  ✅ Done: {done}",
            f"  🔄 In Progress: {in_progress}",
            f"  📋 Planned: {planned}",
            f"  👀 In Review: {in_review}",
            "",
            f"Story Points: [bold]{total_points}[/bold]",
            f"  Completed: {done_points} ({points_completion:.0f}%)",
            "",
            f"Completion: [bold]{completion:.0f}%[/bold]",
            "",
            f"Synced: {synced}/{total}",
        ]

        content.update("\n".join(lines))


# =============================================================================
# Conflict Resolution Widget
# =============================================================================


class ConflictPanel(Widget):
    """
    Displays and handles conflict resolution.

    Shows side-by-side diff with resolution options.
    """

    class ConflictResolved(Message):
        """Message emitted when a conflict is resolved."""

        def __init__(self, conflict_index: int, resolution: str) -> None:
            self.conflict_index = conflict_index
            self.resolution = resolution
            super().__init__()

    def __init__(
        self,
        conflicts: list[StoryConflict] | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(id=id, classes=classes)
        self._conflicts = conflicts or []
        self._current_index = 0

    def compose(self) -> ComposeResult:
        """Compose the widget."""
        with Vertical(id="conflict-container"):
            yield Static("⚠️ Conflicts", classes="panel-title")
            yield Rule()
            yield Static("", id="conflict-header")
            with Horizontal(id="conflict-diff"):
                with Vertical(classes="diff-side"):
                    yield Static("[bold]Local[/bold]", classes="diff-label")
                    yield Static("", id="diff-local", classes="diff-content")
                with Vertical(classes="diff-side"):
                    yield Static("[bold]Remote[/bold]", classes="diff-label")
                    yield Static("", id="diff-remote", classes="diff-content")
            with Horizontal(id="conflict-actions"):
                yield Button("← Use Local", id="btn-local", variant="primary")
                yield Button("Use Remote →", id="btn-remote", variant="warning")
                yield Button("Skip", id="btn-skip", variant="default")

    def on_mount(self) -> None:
        """Handle mount event."""
        self._refresh_display()

    def update_conflicts(self, conflicts: list[StoryConflict]) -> None:
        """Update the conflicts list."""
        self._conflicts = conflicts
        self._current_index = 0
        self._refresh_display()

    def _refresh_display(self) -> None:
        """Refresh the display with current conflict."""
        header = self.query_one("#conflict-header", Static)
        local = self.query_one("#diff-local", Static)
        remote = self.query_one("#diff-remote", Static)

        unresolved = [c for c in self._conflicts if not c.resolved]

        if not unresolved:
            header.update("✅ No conflicts to resolve")
            local.update("")
            remote.update("")
            return

        if self._current_index >= len(unresolved):
            self._current_index = 0

        conflict = unresolved[self._current_index]
        remaining = len(unresolved)

        header.update(
            f"Conflict {self._current_index + 1}/{remaining}: "
            f"[bold]{conflict.story_id}[/bold] - {conflict.story_title}\n"
            f"Field: {conflict.field_name} | Type: {conflict.conflict_type.value}"
        )

        local.update(
            conflict.local_value[:300] + "..."
            if len(conflict.local_value) > 300
            else conflict.local_value
        )
        remote.update(
            conflict.remote_value[:300] + "..."
            if len(conflict.remote_value) > 300
            else conflict.remote_value
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        unresolved = [c for c in self._conflicts if not c.resolved]
        if not unresolved:
            return

        conflict = unresolved[self._current_index]

        if event.button.id == "btn-local":
            conflict.resolve_with_local()
            self.post_message(self.ConflictResolved(self._current_index, "local"))
        elif event.button.id == "btn-remote":
            conflict.resolve_with_remote()
            self.post_message(self.ConflictResolved(self._current_index, "remote"))
        elif event.button.id == "btn-skip":
            self._current_index += 1

        self._refresh_display()


# =============================================================================
# Log Panel Widget
# =============================================================================


class LogPanel(Widget):
    """
    Displays log messages from sync operations.

    Shows a scrollable list of recent log entries.
    """

    def __init__(
        self,
        *,
        max_entries: int = 100,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(id=id, classes=classes)
        self._max_entries = max_entries
        self._entries: list[tuple[str, str]] = []  # (level, message)

    def compose(self) -> ComposeResult:
        """Compose the widget."""
        with Vertical(id="log-container"):
            yield Static("📜 Activity Log", classes="panel-title")
            yield Rule()
            with ScrollableContainer(id="log-scroll"):
                yield Static("", id="log-content")

    def add_entry(self, message: str, level: str = "info") -> None:
        """Add a log entry."""
        self._entries.append((level, message))
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries :]
        self._refresh_display()

    def clear(self) -> None:
        """Clear all log entries."""
        self._entries = []
        self._refresh_display()

    def _refresh_display(self) -> None:
        """Refresh the log display."""
        content = self.query_one("#log-content", Static)

        if not self._entries:
            content.update("[dim]No activity yet[/dim]")
            return

        lines = []
        for level, message in self._entries[-20:]:  # Show last 20
            prefix = {
                "info": "ℹ️",
                "success": "✅",
                "warning": "⚠️",
                "error": "❌",
            }.get(level, "•")
            lines.append(f"{prefix} {message}")

        content.update("\n".join(lines))


# =============================================================================
# Command Palette Results Widget
# =============================================================================


class CommandItem(Static):
    """A single command item in the command palette."""

    def __init__(
        self,
        command: str,
        description: str,
        shortcut: str | None = None,
        *,
        id: str | None = None,
    ) -> None:
        self.command = command
        self.shortcut = shortcut
        label = f"[bold]{command}[/bold] - {description}"
        if shortcut:
            label += f" [dim]({shortcut})[/dim]"
        super().__init__(label, id=id)
