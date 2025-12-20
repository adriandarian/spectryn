"""
Dashboard - TUI dashboard showing sync status.

Provides a terminal-based dashboard with:
- Epic and story overview
- Sync history and statistics
- Real-time progress during sync operations
- Session status display
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

from spectra.core.ports.document_parser import DocumentParserPort
from spectra.core.ports.issue_tracker import IssueTrackerPort

from .exit_codes import ExitCode
from .output import Colors, Console, Symbols


class DashboardMode(Enum):
    """Dashboard display modes."""

    OVERVIEW = "overview"
    STORIES = "stories"
    SESSIONS = "sessions"
    BACKUPS = "backups"


@dataclass
class StoryStatus:
    """Status information for a single story."""

    story_id: str
    title: str
    jira_key: str | None = None
    status: str = "Unknown"
    points: int = 0
    subtask_count: int = 0
    last_synced: datetime | None = None
    has_changes: bool = False
    sync_status: str = "pending"  # pending, synced, error


@dataclass
class DashboardData:
    """Data for dashboard display."""

    # Epic info
    epic_key: str = ""
    epic_title: str = ""
    markdown_path: str = ""

    # Stories
    stories: list[StoryStatus] = field(default_factory=list)

    # Sync stats
    total_syncs: int = 0
    successful_syncs: int = 0
    failed_syncs: int = 0
    last_sync: datetime | None = None
    last_sync_result: str | None = None

    # Session info
    has_pending_session: bool = False
    pending_operations: int = 0
    completed_operations: int = 0

    # Backup info
    backup_count: int = 0
    latest_backup: str | None = None


class Dashboard:
    """
    TUI Dashboard for spectra sync status.

    Displays a comprehensive overview of sync status, stories,
    and operations in a terminal-friendly format.
    """

    def __init__(self, console: Console):
        """
        Initialize the dashboard.

        Args:
            console: Console instance for output.
        """
        self.console = console
        self.color = console.color

    def render(self, data: DashboardData, mode: DashboardMode = DashboardMode.OVERVIEW) -> None:
        """
        Render the dashboard.

        Args:
            data: Dashboard data to display.
            mode: Display mode.
        """
        # Clear screen and move cursor to top
        if self.color:
            print("\033[2J\033[H", end="")

        self._render_header(data)

        if mode == DashboardMode.OVERVIEW:
            self._render_overview(data)
        elif mode == DashboardMode.STORIES:
            self._render_stories(data)
        elif mode == DashboardMode.SESSIONS:
            self._render_sessions(data)
        elif mode == DashboardMode.BACKUPS:
            self._render_backups(data)

        self._render_footer()

    def render_static(self, data: DashboardData) -> str:
        """
        Render dashboard to a string (non-interactive).

        Args:
            data: Dashboard data to display.

        Returns:
            Rendered dashboard as string.
        """
        lines: list[str] = []

        # Header
        lines.extend(self._build_header(data))
        lines.append("")

        # Overview section (includes stats, sync status, and stories summary)
        lines.extend(self._build_overview(data))

        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # Header
    # -------------------------------------------------------------------------

    def _render_header(self, data: DashboardData) -> None:
        """Render the dashboard header."""
        for line in self._build_header(data):
            print(line)
        print()

    def _build_header(self, data: DashboardData) -> list[str]:
        """Build header lines."""
        lines: list[str] = []

        # Title bar
        title = f" spectra Dashboard {Symbols.ROCKET} "
        if self.color:
            width = 70
            padding = (width - len(title)) // 2
            title_line = (
                f"{Colors.BG_BLUE}{Colors.WHITE}{Colors.BOLD}"
                f"{' ' * padding}{title}{' ' * (width - padding - len(title))}"
                f"{Colors.RESET}"
            )
        else:
            title_line = f"{'=' * 20} {title} {'=' * 20}"

        lines.append(title_line)
        lines.append("")

        # Epic info
        if data.epic_key:
            if self.color:
                lines.append(
                    f"  {Colors.BOLD}Epic:{Colors.RESET} "
                    f"{Colors.CYAN}{data.epic_key}{Colors.RESET}"
                    f" - {data.epic_title}"
                )
            else:
                lines.append(f"  Epic: {data.epic_key} - {data.epic_title}")

        if data.markdown_path:
            if self.color:
                lines.append(
                    f"  {Colors.BOLD}File:{Colors.RESET} "
                    f"{Colors.DIM}{data.markdown_path}{Colors.RESET}"
                )
            else:
                lines.append(f"  File: {data.markdown_path}")

        return lines

    # -------------------------------------------------------------------------
    # Overview
    # -------------------------------------------------------------------------

    def _render_overview(self, data: DashboardData) -> None:
        """Render the overview section."""
        for line in self._build_overview(data):
            print(line)

    def _build_overview(self, data: DashboardData) -> list[str]:
        """Build overview section lines."""
        lines: list[str] = []

        # Section header
        if self.color:
            lines.append(f"{Colors.BOLD}{Colors.BLUE}{Symbols.ARROW} Overview{Colors.RESET}")
        else:
            lines.append("→ Overview")
        lines.append("")

        # Stats boxes
        lines.extend(self._build_stats_row(data))
        lines.append("")

        # Sync status
        lines.extend(self._build_sync_status(data))
        lines.append("")

        # Stories summary
        lines.extend(self._build_stories_summary(data))

        return lines

    def _build_stats_row(self, data: DashboardData) -> list[str]:
        """Build the stats boxes row."""
        lines: list[str] = []

        # Calculate stats
        total_stories = len(data.stories)
        sum(1 for s in data.stories if s.sync_status == "synced")
        sum(1 for s in data.stories if s.sync_status == "pending")
        sum(1 for s in data.stories if s.sync_status == "error")
        total_points = sum(s.points for s in data.stories)
        total_subtasks = sum(s.subtask_count for s in data.stories)

        if self.color:
            # Colorful stat boxes
            box_width = 15

            # Stories box
            stories_box = self._stat_box("Stories", str(total_stories), Colors.CYAN, box_width)
            points_box = self._stat_box("Points", str(total_points), Colors.MAGENTA, box_width)
            subtasks_box = self._stat_box("Subtasks", str(total_subtasks), Colors.BLUE, box_width)
            syncs_box = self._stat_box("Syncs", str(data.total_syncs), Colors.GREEN, box_width)

            # Combine boxes side by side
            for i in range(3):  # 3 lines per box
                line = "  "
                line += stories_box[i] + "  "
                line += points_box[i] + "  "
                line += subtasks_box[i] + "  "
                line += syncs_box[i]
                lines.append(line)
        else:
            lines.append(
                f"  Stories: {total_stories}  |  Points: {total_points}  |  Subtasks: {total_subtasks}  |  Syncs: {data.total_syncs}"
            )

        return lines

    def _stat_box(self, label: str, value: str, color: str, width: int) -> list[str]:
        """Build a single stat box (3 lines)."""
        top = f"{color}╭{'─' * (width - 2)}╮{Colors.RESET}"
        middle = f"{color}│{Colors.RESET}{Colors.BOLD}{value.center(width - 2)}{Colors.RESET}{color}│{Colors.RESET}"
        bottom = f"{color}╰{label.center(width - 2, '─')}╯{Colors.RESET}"
        return [top, middle, bottom]

    def _build_sync_status(self, data: DashboardData) -> list[str]:
        """Build sync status section."""
        lines: list[str] = []

        if self.color:
            lines.append(
                f"  {Colors.BOLD}Last Sync:{Colors.RESET}",
            )
        else:
            lines.append("  Last Sync:")

        if data.last_sync:
            time_str = data.last_sync.strftime("%Y-%m-%d %H:%M:%S")
            result = data.last_sync_result or "Unknown"

            if result == "success":
                if self.color:
                    status = f"{Colors.GREEN}{Symbols.CHECK} Success{Colors.RESET}"
                else:
                    status = "✓ Success"
            elif result == "partial":
                if self.color:
                    status = f"{Colors.YELLOW}{Symbols.WARN} Partial{Colors.RESET}"
                else:
                    status = "⚠ Partial"
            elif self.color:
                status = f"{Colors.RED}{Symbols.CROSS} Failed{Colors.RESET}"
            else:
                status = "✗ Failed"

            lines.append(f"    {time_str} - {status}")
        elif self.color:
            lines.append(f"    {Colors.DIM}No sync history{Colors.RESET}")
        else:
            lines.append("    No sync history")

        # Success rate
        if data.total_syncs > 0:
            rate = (data.successful_syncs / data.total_syncs) * 100
            if self.color:
                rate_color = (
                    Colors.GREEN if rate >= 80 else (Colors.YELLOW if rate >= 50 else Colors.RED)
                )
                lines.append(
                    f"    Success rate: {rate_color}{rate:.0f}%{Colors.RESET} ({data.successful_syncs}/{data.total_syncs})"
                )
            else:
                lines.append(
                    f"    Success rate: {rate:.0f}% ({data.successful_syncs}/{data.total_syncs})"
                )

        return lines

    def _build_stories_summary(self, data: DashboardData) -> list[str]:
        """Build stories summary section."""
        lines: list[str] = []

        if self.color:
            lines.append(f"  {Colors.BOLD}Stories:{Colors.RESET}")
        else:
            lines.append("  Stories:")

        if not data.stories:
            if self.color:
                lines.append(f"    {Colors.DIM}No stories loaded{Colors.RESET}")
            else:
                lines.append("    No stories loaded")
            return lines

        # Status breakdown
        synced = sum(1 for s in data.stories if s.sync_status == "synced")
        pending = sum(1 for s in data.stories if s.sync_status == "pending")
        errors = sum(1 for s in data.stories if s.sync_status == "error")
        changed = sum(1 for s in data.stories if s.has_changes)

        if self.color:
            parts = []
            if synced > 0:
                parts.append(f"{Colors.GREEN}{Symbols.CHECK} {synced} synced{Colors.RESET}")
            if pending > 0:
                parts.append(f"{Colors.CYAN}◯ {pending} pending{Colors.RESET}")
            if errors > 0:
                parts.append(f"{Colors.RED}{Symbols.CROSS} {errors} errors{Colors.RESET}")
            if changed > 0:
                parts.append(f"{Colors.YELLOW}↻ {changed} changed{Colors.RESET}")

            lines.append(f"    {' | '.join(parts)}")
        else:
            lines.append(
                f"    ✓ {synced} synced | ◯ {pending} pending | ✗ {errors} errors | ↻ {changed} changed"
            )

        # Show first few stories
        lines.append("")
        max_show = 8
        for _i, story in enumerate(data.stories[:max_show]):
            status_icon = self._get_story_status_icon(story)
            jira_info = f" [{story.jira_key}]" if story.jira_key else ""

            if self.color:
                title_display = story.title[:40] + "..." if len(story.title) > 40 else story.title
                lines.append(
                    f"    {status_icon} {story.story_id}: {title_display}{Colors.DIM}{jira_info}{Colors.RESET}"
                )
            else:
                title_display = story.title[:40] + "..." if len(story.title) > 40 else story.title
                lines.append(f"    {status_icon} {story.story_id}: {title_display}{jira_info}")

        if len(data.stories) > max_show:
            remaining = len(data.stories) - max_show
            if self.color:
                lines.append(f"    {Colors.DIM}... and {remaining} more stories{Colors.RESET}")
            else:
                lines.append(f"    ... and {remaining} more stories")

        return lines

    def _get_story_status_icon(self, story: StoryStatus) -> str:
        """Get status icon for a story."""
        if story.sync_status == "synced":
            return f"{Colors.GREEN}{Symbols.CHECK}{Colors.RESET}" if self.color else "✓"
        if story.sync_status == "error":
            return f"{Colors.RED}{Symbols.CROSS}{Colors.RESET}" if self.color else "✗"
        if story.has_changes:
            return f"{Colors.YELLOW}↻{Colors.RESET}" if self.color else "↻"
        return f"{Colors.DIM}◯{Colors.RESET}" if self.color else "◯"

    # -------------------------------------------------------------------------
    # Stories View
    # -------------------------------------------------------------------------

    def _render_stories(self, data: DashboardData) -> None:
        """Render detailed stories view."""
        if self.color:
            print(f"{Colors.BOLD}{Colors.BLUE}{Symbols.ARROW} Stories{Colors.RESET}")
        else:
            print("→ Stories")
        print()

        if not data.stories:
            print("  No stories to display")
            return

        # Table header
        if self.color:
            header = (
                f"  {Colors.BOLD}"
                f"{'ID':<10} {'Title':<35} {'Status':<12} {'Pts':>4} {'Jira':<12}"
                f"{Colors.RESET}"
            )
        else:
            header = f"  {'ID':<10} {'Title':<35} {'Status':<12} {'Pts':>4} {'Jira':<12}"

        print(header)
        print("  " + "-" * 75)

        for story in data.stories:
            self._render_story_row(story)

    def _render_story_row(self, story: StoryStatus) -> None:
        """Render a single story row."""
        title = story.title[:33] + ".." if len(story.title) > 35 else story.title
        jira = story.jira_key or "-"

        status_icon = self._get_story_status_icon(story)

        if self.color:
            status_color = {
                "synced": Colors.GREEN,
                "error": Colors.RED,
                "pending": Colors.DIM,
            }.get(story.sync_status, Colors.DIM)

            row = (
                f"  {status_icon} "
                f"{story.story_id:<8} "
                f"{title:<35} "
                f"{status_color}{story.status:<10}{Colors.RESET} "
                f"{story.points:>4} "
                f"{Colors.CYAN}{jira:<12}{Colors.RESET}"
            )
        else:
            row = f"  {status_icon} {story.story_id:<8} {title:<35} {story.status:<10} {story.points:>4} {jira:<12}"

        print(row)

    # -------------------------------------------------------------------------
    # Sessions View
    # -------------------------------------------------------------------------

    def _render_sessions(self, data: DashboardData) -> None:
        """Render sessions view."""
        if self.color:
            print(f"{Colors.BOLD}{Colors.BLUE}{Symbols.ARROW} Sync Sessions{Colors.RESET}")
        else:
            print("→ Sync Sessions")
        print()

        if data.has_pending_session:
            progress = data.completed_operations / max(
                data.pending_operations + data.completed_operations, 1
            )
            pct = int(progress * 100)

            if self.color:
                print(f"  {Colors.YELLOW}⚡ Active Session{Colors.RESET}")
                bar = self._progress_bar(progress, 30)
                print(f"  {bar} {pct}%")
                print(
                    f"  {Colors.DIM}Completed: {data.completed_operations} | Pending: {data.pending_operations}{Colors.RESET}"
                )
            else:
                print("  ⚡ Active Session")
                print(f"  Progress: {pct}%")
                print(
                    f"  Completed: {data.completed_operations} | Pending: {data.pending_operations}"
                )
        elif self.color:
            print(f"  {Colors.DIM}No active sessions{Colors.RESET}")
        else:
            print("  No active sessions")

    def _progress_bar(self, progress: float, width: int) -> str:
        """Build a progress bar."""
        filled = int(width * progress)
        empty = width - filled

        if self.color:
            return f"{Colors.GREEN}{'█' * filled}{Colors.DIM}{'░' * empty}{Colors.RESET}"
        return f"[{'#' * filled}{'-' * empty}]"

    # -------------------------------------------------------------------------
    # Backups View
    # -------------------------------------------------------------------------

    def _render_backups(self, data: DashboardData) -> None:
        """Render backups view."""
        if self.color:
            print(f"{Colors.BOLD}{Colors.BLUE}{Symbols.ARROW} Backups{Colors.RESET}")
        else:
            print("→ Backups")
        print()

        if data.backup_count > 0:
            if self.color:
                print(f"  Total backups: {Colors.CYAN}{data.backup_count}{Colors.RESET}")
                if data.latest_backup:
                    print(f"  Latest: {Colors.DIM}{data.latest_backup}{Colors.RESET}")
            else:
                print(f"  Total backups: {data.backup_count}")
                if data.latest_backup:
                    print(f"  Latest: {data.latest_backup}")
        elif self.color:
            print(f"  {Colors.DIM}No backups found{Colors.RESET}")
        else:
            print("  No backups found")

    # -------------------------------------------------------------------------
    # Footer
    # -------------------------------------------------------------------------

    def _render_footer(self) -> None:
        """Render the dashboard footer."""
        print()
        if self.color:
            print(f"{Colors.DIM}{'─' * 70}{Colors.RESET}")
            print(
                f"{Colors.DIM}  Last updated: {datetime.now().strftime('%H:%M:%S')}  |  spectra dashboard{Colors.RESET}"
            )
        else:
            print("-" * 70)
            print(f"  Last updated: {datetime.now().strftime('%H:%M:%S')}  |  spectra dashboard")


def load_dashboard_data(
    markdown_path: str | None = None,
    epic_key: str | None = None,
    tracker: IssueTrackerPort | None = None,
    parser: DocumentParserPort | None = None,
) -> DashboardData:
    """
    Load data for the dashboard.

    Args:
        markdown_path: Path to markdown file.
        epic_key: Jira epic key.
        tracker: Jira tracker adapter (optional).
        parser: Markdown parser (optional).

    Returns:
        DashboardData populated with available information.
    """
    data = DashboardData()
    data.epic_key = epic_key or ""
    data.markdown_path = markdown_path or ""

    # Parse markdown to get stories
    if markdown_path and Path(markdown_path).exists():
        try:
            from spectra.adapters import MarkdownParser

            if parser is None:
                parser = MarkdownParser()

            stories = parser.parse_stories(markdown_path)

            for story in stories:
                story_status = StoryStatus(
                    story_id=str(story.id),
                    title=story.title,
                    jira_key=str(story.external_key) if story.external_key else None,
                    status=story.status.display_name if story.status else "Unknown",
                    points=story.story_points or 0,
                    subtask_count=len(story.subtasks) if story.subtasks else 0,
                    sync_status="synced" if story.external_key else "pending",
                )
                data.stories.append(story_status)
        except Exception:
            pass

    # Load session data
    try:
        from spectra.application.sync import StateStore

        store = StateStore()
        sessions = store.list_sessions()

        if sessions and epic_key:
            # Find session for this epic
            for session in sessions:
                if session.get("epic_key") == epic_key:
                    state = store.load(session["session_id"])
                    if state:
                        data.has_pending_session = state.pending_count > 0
                        data.pending_operations = state.pending_count
                        data.completed_operations = state.completed_count
                    break
    except Exception:
        pass

    # Load backup data
    try:
        from spectra.application.sync import BackupManager

        manager = BackupManager()
        backups = manager.list_backups(epic_key) if epic_key else []
        data.backup_count = len(backups)

        if backups:
            data.latest_backup = backups[0].get("backup_id", "")
    except Exception:
        pass

    return data


def run_dashboard(
    console: Console,
    markdown_path: str | None = None,
    epic_key: str | None = None,
) -> int:
    """
    Run the dashboard display.

    Args:
        console: Console for output.
        markdown_path: Optional markdown file path.
        epic_key: Optional epic key.

    Returns:
        Exit code.
    """
    # Load data
    data = load_dashboard_data(
        markdown_path=markdown_path,
        epic_key=epic_key,
    )

    # Create and render dashboard
    dashboard = Dashboard(console)

    # Static render (non-interactive)
    output = dashboard.render_static(data)
    print(output)

    return ExitCode.SUCCESS
