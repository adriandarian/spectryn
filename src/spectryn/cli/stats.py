"""
Stats Command - Show statistics about stories, points, and velocity.

Provides insights into:
- Story counts by status
- Story point distribution
- Sprint velocity metrics
- Progress tracking
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .exit_codes import ExitCode
from .output import Colors, Console, Symbols


@dataclass
class StoryStats:
    """Statistics about stories."""

    total_stories: int = 0
    total_subtasks: int = 0
    total_points: int = 0

    # By status
    done: int = 0
    in_progress: int = 0
    planned: int = 0
    blocked: int = 0

    # Points by status
    points_done: int = 0
    points_in_progress: int = 0
    points_planned: int = 0

    # Priority breakdown
    by_priority: dict[str, int] = field(default_factory=dict)

    # Acceptance criteria
    ac_total: int = 0
    ac_completed: int = 0

    @property
    def completion_percentage(self) -> float:
        """Get completion percentage by story count."""
        if self.total_stories == 0:
            return 0.0
        return (self.done / self.total_stories) * 100

    @property
    def points_completion_percentage(self) -> float:
        """Get completion percentage by points."""
        if self.total_points == 0:
            return 0.0
        return (self.points_done / self.total_points) * 100


@dataclass
class VelocityStats:
    """Velocity statistics."""

    sprints: list[dict] = field(default_factory=list)
    average_velocity: float = 0.0
    trend: str = "stable"  # up, down, stable


def collect_stats_from_file(file_path: str) -> StoryStats:
    """
    Collect statistics from a markdown file.

    Args:
        file_path: Path to the markdown file.

    Returns:
        StoryStats with collected data.
    """
    from spectryn.adapters.parsers import MarkdownParser

    stats = StoryStats()
    parser = MarkdownParser()

    try:
        stories = parser.parse_stories(file_path)
    except Exception:
        return stats

    stats.total_stories = len(stories)

    for story in stories:
        # Count by status
        status = story.status.name.lower() if story.status else "planned"
        if status in ("done", "closed", "resolved", "complete"):
            stats.done += 1
            stats.points_done += story.story_points or 0
        elif status in ("in_progress", "in progress", "active"):
            stats.in_progress += 1
            stats.points_in_progress += story.story_points or 0
        elif status in ("blocked", "on_hold"):
            stats.blocked += 1
        else:
            stats.planned += 1
            stats.points_planned += story.story_points or 0

        # Total points
        stats.total_points += story.story_points or 0

        # Subtasks
        stats.total_subtasks += len(story.subtasks) if story.subtasks else 0

        # Priority
        priority = story.priority.name.lower() if story.priority else "medium"
        stats.by_priority[priority] = stats.by_priority.get(priority, 0) + 1

        # Acceptance criteria
        if story.acceptance_criteria:
            for ac in story.acceptance_criteria.items:
                stats.ac_total += 1
                # Simple heuristic: if starts with [x] or contains ✓, it's complete
                if "[x]" in ac.lower() or "✓" in ac or "✅" in ac:
                    stats.ac_completed += 1

    return stats


def collect_stats_from_directory(dir_path: str) -> StoryStats:
    """
    Collect statistics from a directory of markdown files.

    Args:
        dir_path: Path to the directory.

    Returns:
        Combined StoryStats.
    """
    combined = StoryStats()
    path = Path(dir_path)

    for md_file in path.glob("*.md"):
        stats = collect_stats_from_file(str(md_file))
        combined.total_stories += stats.total_stories
        combined.total_subtasks += stats.total_subtasks
        combined.total_points += stats.total_points
        combined.done += stats.done
        combined.in_progress += stats.in_progress
        combined.planned += stats.planned
        combined.blocked += stats.blocked
        combined.points_done += stats.points_done
        combined.points_in_progress += stats.points_in_progress
        combined.points_planned += stats.points_planned
        combined.ac_total += stats.ac_total
        combined.ac_completed += stats.ac_completed

        for priority, count in stats.by_priority.items():
            combined.by_priority[priority] = combined.by_priority.get(priority, 0) + count

    return combined


def format_progress_bar(percentage: float, width: int = 30, color: bool = True) -> str:
    """
    Create a text-based progress bar.

    Args:
        percentage: Completion percentage (0-100).
        width: Width of the bar in characters.
        color: Whether to use colors.

    Returns:
        Formatted progress bar string.
    """
    filled = int(width * percentage / 100)
    empty = width - filled

    if color:
        if percentage >= 80:
            bar_color = Colors.GREEN
        elif percentage >= 50:
            bar_color = Colors.YELLOW
        else:
            bar_color = Colors.RED

        bar = f"{bar_color}{'█' * filled}{Colors.DIM}{'░' * empty}{Colors.RESET}"
    else:
        bar = "█" * filled + "░" * empty

    return f"[{bar}] {percentage:.1f}%"


def format_stats(stats: StoryStats, color: bool = True) -> str:
    """
    Format statistics for display.

    Args:
        stats: StoryStats to format.
        color: Whether to use colors.

    Returns:
        Formatted string.
    """
    lines = []

    # Header
    if color:
        lines.append(f"{Colors.BOLD}Story Statistics{Colors.RESET}")
    else:
        lines.append("Story Statistics")
    lines.append("=" * 50)

    # Overview
    lines.append("")
    lines.append(f"  Total Stories:    {stats.total_stories}")
    lines.append(f"  Total Subtasks:   {stats.total_subtasks}")
    lines.append(f"  Total Points:     {stats.total_points}")

    # Status breakdown
    lines.append("")
    if color:
        lines.append(f"{Colors.BOLD}Status Breakdown{Colors.RESET}")
    else:
        lines.append("Status Breakdown")
    lines.append("-" * 50)

    # Create status table
    status_data = [
        ("✅ Done", stats.done, stats.points_done, Colors.GREEN if color else ""),
        (
            "🔄 In Progress",
            stats.in_progress,
            stats.points_in_progress,
            Colors.YELLOW if color else "",
        ),
        ("📋 Planned", stats.planned, stats.points_planned, Colors.CYAN if color else ""),
        ("⏸️  Blocked", stats.blocked, 0, Colors.RED if color else ""),
    ]

    reset = Colors.RESET if color else ""
    for label, count, points, clr in status_data:
        pct = (count / stats.total_stories * 100) if stats.total_stories > 0 else 0
        lines.append(
            f"  {clr}{label:<15}{reset} {count:>3} stories ({pct:>5.1f}%)  {points:>3} pts"
        )

    # Progress bars
    lines.append("")
    if color:
        lines.append(f"{Colors.BOLD}Progress{Colors.RESET}")
    else:
        lines.append("Progress")
    lines.append("-" * 50)

    lines.append(f"  By Stories: {format_progress_bar(stats.completion_percentage, color=color)}")
    lines.append(
        f"  By Points:  {format_progress_bar(stats.points_completion_percentage, color=color)}"
    )

    # Acceptance criteria
    if stats.ac_total > 0:
        ac_pct = stats.ac_completed / stats.ac_total * 100
        lines.append(
            f"  AC Items:   {format_progress_bar(ac_pct, color=color)} ({stats.ac_completed}/{stats.ac_total})"
        )

    # Priority breakdown
    if stats.by_priority:
        lines.append("")
        if color:
            lines.append(f"{Colors.BOLD}Priority Distribution{Colors.RESET}")
        else:
            lines.append("Priority Distribution")
        lines.append("-" * 50)

        priority_colors = {
            "critical": Colors.RED,
            "high": Colors.YELLOW,
            "medium": Colors.GREEN,
            "low": Colors.CYAN,
        }

        for priority in ["critical", "high", "medium", "low"]:
            if priority in stats.by_priority:
                count = stats.by_priority[priority]
                pct = (count / stats.total_stories * 100) if stats.total_stories > 0 else 0
                clr = priority_colors.get(priority, "") if color else ""
                lines.append(
                    f"  {clr}{priority.capitalize():<10}{reset} {count:>3} stories ({pct:>5.1f}%)"
                )

    lines.append("")
    return "\n".join(lines)


def run_stats(
    console: Console,
    input_path: str | None = None,
    input_dir: str | None = None,
    output_format: str = "text",
) -> int:
    """
    Run the stats command.

    Args:
        console: Console for output.
        input_path: Path to markdown file.
        input_dir: Path to directory.
        output_format: Output format (text, json).

    Returns:
        Exit code.
    """
    console.header(f"spectra Stats {Symbols.CHART}")
    console.print()

    # Determine source
    if input_dir:
        path = Path(input_dir)
        if not path.is_dir():
            console.error(f"Directory not found: {input_dir}")
            return ExitCode.FILE_NOT_FOUND
        console.info(f"Directory: {input_dir}")
        stats = collect_stats_from_directory(input_dir)
    elif input_path:
        path = Path(input_path)
        if not path.exists():
            console.error(f"File not found: {input_path}")
            return ExitCode.FILE_NOT_FOUND
        console.info(f"File: {input_path}")
        stats = collect_stats_from_file(input_path)
    else:
        # Try current directory
        cwd = Path.cwd()
        md_files = list(cwd.glob("*.md"))
        if not md_files:
            console.error("No markdown files found in current directory")
            console.info("Specify a file with --input or directory with --input-dir")
            return ExitCode.FILE_NOT_FOUND
        console.info(f"Current directory: {cwd}")
        stats = collect_stats_from_directory(str(cwd))

    console.print()

    # Output based on format
    if output_format == "json":
        import json

        data = {
            "total_stories": stats.total_stories,
            "total_subtasks": stats.total_subtasks,
            "total_points": stats.total_points,
            "status": {
                "done": stats.done,
                "in_progress": stats.in_progress,
                "planned": stats.planned,
                "blocked": stats.blocked,
            },
            "points": {
                "done": stats.points_done,
                "in_progress": stats.points_in_progress,
                "planned": stats.points_planned,
            },
            "completion": {
                "by_stories": round(stats.completion_percentage, 2),
                "by_points": round(stats.points_completion_percentage, 2),
            },
            "acceptance_criteria": {
                "total": stats.ac_total,
                "completed": stats.ac_completed,
            },
            "priority": stats.by_priority,
            "timestamp": datetime.now().isoformat(),
        }
        print(json.dumps(data, indent=2))
    else:
        formatted = format_stats(stats, color=console.color)
        print(formatted)

    return ExitCode.SUCCESS
