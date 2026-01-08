"""
Velocity Command - Track story points completed over time.

Features:
- Sprint velocity calculation
- Trend analysis
- Burndown/burnup charts (ASCII)
- Capacity planning
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from .exit_codes import ExitCode
from .output import Colors, Console, Symbols


@dataclass
class SprintData:
    """Data for a single sprint."""

    name: str
    start_date: datetime
    end_date: datetime
    committed_points: int = 0
    completed_points: int = 0
    stories_completed: int = 0
    stories_total: int = 0

    @property
    def completion_rate(self) -> float:
        """Calculate completion rate."""
        if self.committed_points == 0:
            return 0.0
        return (self.completed_points / self.committed_points) * 100


@dataclass
class VelocityData:
    """Velocity tracking data."""

    sprints: list[SprintData] = field(default_factory=list)
    data_file: str = ".spectra/velocity.json"

    @property
    def average_velocity(self) -> float:
        """Calculate average velocity."""
        if not self.sprints:
            return 0.0
        return sum(s.completed_points for s in self.sprints) / len(self.sprints)

    @property
    def last_velocity(self) -> int:
        """Get last sprint velocity."""
        if not self.sprints:
            return 0
        return self.sprints[-1].completed_points

    @property
    def trend(self) -> str:
        """Determine velocity trend."""
        if len(self.sprints) < 2:
            return "stable"

        recent = self.sprints[-3:] if len(self.sprints) >= 3 else self.sprints
        velocities = [s.completed_points for s in recent]

        if all(velocities[i] <= velocities[i + 1] for i in range(len(velocities) - 1)):
            return "up"
        if all(velocities[i] >= velocities[i + 1] for i in range(len(velocities) - 1)):
            return "down"
        return "stable"


def load_velocity_data(data_file: str = ".spectra/velocity.json") -> VelocityData:
    """Load velocity data from file."""
    data = VelocityData(data_file=data_file)

    if Path(data_file).exists():
        try:
            with open(data_file) as f:
                raw = json.load(f)

            for sprint_data in raw.get("sprints", []):
                data.sprints.append(
                    SprintData(
                        name=sprint_data.get("name", ""),
                        start_date=datetime.fromisoformat(sprint_data.get("start_date", "")),
                        end_date=datetime.fromisoformat(sprint_data.get("end_date", "")),
                        committed_points=sprint_data.get("committed_points", 0),
                        completed_points=sprint_data.get("completed_points", 0),
                        stories_completed=sprint_data.get("stories_completed", 0),
                        stories_total=sprint_data.get("stories_total", 0),
                    )
                )
        except (json.JSONDecodeError, KeyError):
            pass

    return data


def save_velocity_data(data: VelocityData) -> None:
    """Save velocity data to file."""
    # Ensure directory exists
    Path(data.data_file).parent.mkdir(parents=True, exist_ok=True)

    raw = {
        "sprints": [
            {
                "name": s.name,
                "start_date": s.start_date.isoformat(),
                "end_date": s.end_date.isoformat(),
                "committed_points": s.committed_points,
                "completed_points": s.completed_points,
                "stories_completed": s.stories_completed,
                "stories_total": s.stories_total,
            }
            for s in data.sprints
        ],
    }

    with open(data.data_file, "w") as f:
        json.dump(raw, f, indent=2)


def generate_velocity_chart(sprints: list[SprintData], width: int = 50, color: bool = True) -> str:
    """
    Generate ASCII velocity chart.

    Args:
        sprints: List of sprint data.
        width: Chart width in characters.
        color: Whether to use colors.

    Returns:
        ASCII chart string.
    """
    if not sprints:
        return "No velocity data available."

    lines = []

    # Find max for scaling
    max_points = max(s.completed_points for s in sprints) or 1

    # Header
    if color:
        lines.append(f"{Colors.BOLD}Velocity Chart{Colors.RESET}")
    else:
        lines.append("Velocity Chart")
    lines.append("")

    # Bars
    bar_width = width - 20  # Leave room for labels
    for sprint in sprints[-10:]:  # Show last 10 sprints
        bar_length = int((sprint.completed_points / max_points) * bar_width)

        label = sprint.name[:10].ljust(10)
        points = str(sprint.completed_points).rjust(4)

        bar = f"{Colors.GREEN}{'█' * bar_length}{Colors.RESET}" if color else "█" * bar_length

        lines.append(f"  {label} │{bar} {points} pts")

    # Average line
    avg = sum(s.completed_points for s in sprints) / len(sprints)
    avg_pos = int((avg / max_points) * bar_width)

    lines.append("")
    lines.append(f"  {'Average':10} │{'-' * avg_pos}┼ {avg:.1f} pts")

    return "\n".join(lines)


def generate_burndown(
    total_points: int,
    completed_points: int,
    days_elapsed: int,
    days_total: int,
    width: int = 50,
    color: bool = True,
) -> str:
    """
    Generate ASCII burndown chart.

    Args:
        total_points: Total committed points.
        completed_points: Points completed so far.
        days_elapsed: Days into sprint.
        days_total: Total sprint days.
        width: Chart width.
        color: Whether to use colors.

    Returns:
        ASCII burndown chart.
    """
    lines = []

    if color:
        lines.append(f"{Colors.BOLD}Sprint Burndown{Colors.RESET}")
    else:
        lines.append("Sprint Burndown")
    lines.append("")

    height = 10
    remaining = total_points - completed_points

    for row in range(height):
        points_at_row = total_points * (height - row) / height

        # Ideal line position
        ideal_col = int((1 - points_at_row / total_points) * width) if total_points > 0 else 0

        # Actual position
        actual_col = (
            int((1 - remaining / total_points) * days_elapsed / days_total * width)
            if total_points > 0
            else 0
        )

        line = [" "] * (width + 1)

        # Draw ideal line
        if ideal_col < len(line):
            line[ideal_col] = "·"

        # Draw actual progress
        if row == height - int(remaining / total_points * height) - 1:
            for c in range(min(actual_col + 1, len(line))):
                if line[c] == " ":
                    if color:
                        line[c] = "─"
                    else:
                        line[c] = "─"

        # Y-axis label
        label = f"{int(points_at_row):3} │"
        lines.append(label + "".join(line))

    # X-axis
    lines.append(f"    └{'─' * width}┘")
    lines.append(f"      Day 1{' ' * (width - 10)}Day {days_total}")

    # Legend
    lines.append("")
    lines.append("  ─ Actual  · Ideal")

    return "\n".join(lines)


def run_velocity(
    console: Console,
    input_path: str | None = None,
    action: str = "show",
    sprint_name: str | None = None,
    sprint_start: str | None = None,
    sprint_end: str | None = None,
    output_format: str = "text",
) -> int:
    """
    Run the velocity command.

    Args:
        console: Console for output.
        input_path: Path to markdown file (for calculating current sprint).
        action: Action to perform (show, add, burndown).
        sprint_name: Sprint name for add action.
        sprint_start: Sprint start date.
        sprint_end: Sprint end date.
        output_format: Output format (text, json).

    Returns:
        Exit code.
    """
    console.header(f"spectra Velocity {Symbols.CHART}")
    console.print()

    # Load existing data
    data = load_velocity_data()

    if action == "add":
        # Add a sprint
        if not sprint_name:
            console.error("Sprint name required (--sprint)")
            return ExitCode.CONFIG_ERROR

        # Calculate from file if provided
        completed = 0
        committed = 0
        stories_done = 0
        stories_total = 0

        if input_path and Path(input_path).exists():
            from spectryn.adapters.parsers import MarkdownParser

            parser = MarkdownParser()
            stories = parser.parse_stories(input_path)

            for story in stories:
                stories_total += 1
                points = story.story_points or 0
                committed += points

                status = story.status.value.lower() if story.status else ""
                if status in ("done", "closed", "resolved"):
                    completed += points
                    stories_done += 1

        # Dates
        start = (
            datetime.fromisoformat(sprint_start)
            if sprint_start
            else datetime.now() - timedelta(days=14)
        )
        end = datetime.fromisoformat(sprint_end) if sprint_end else datetime.now()

        sprint = SprintData(
            name=sprint_name,
            start_date=start,
            end_date=end,
            committed_points=committed,
            completed_points=completed,
            stories_completed=stories_done,
            stories_total=stories_total,
        )

        data.sprints.append(sprint)
        save_velocity_data(data)

        console.success(f"Added sprint: {sprint_name}")
        console.info(f"  Committed: {committed} points")
        console.info(f"  Completed: {completed} points")
        console.info(f"  Stories: {stories_done}/{stories_total}")

        return ExitCode.SUCCESS

    if action == "burndown":
        if not input_path:
            console.error("Input file required for burndown")
            return ExitCode.CONFIG_ERROR

        # Calculate current burndown
        from spectryn.adapters.parsers import MarkdownParser

        parser = MarkdownParser()
        stories = parser.parse_stories(input_path)

        total = sum(s.story_points or 0 for s in stories)
        done_stories = [
            s
            for s in stories
            if s.status and s.status.name.lower() in ("done", "closed", "resolved")
        ]
        done = sum(s.story_points or 0 for s in done_stories)

        # Assume 2-week sprint, calculate days
        days_total = 14
        days_elapsed = 7  # Assume mid-sprint

        chart = generate_burndown(
            total_points=total,
            completed_points=done,
            days_elapsed=days_elapsed,
            days_total=days_total,
            color=console.color,
        )
        print(chart)

        return ExitCode.SUCCESS

    # show
    if not data.sprints:
        console.warning("No velocity data found")
        console.print()
        console.info("Add sprint data with:")
        console.detail("  spectra velocity --add --sprint 'Sprint 1' --input EPIC.md")
        return ExitCode.SUCCESS

    if output_format == "json":
        output = {
            "sprints": [
                {
                    "name": s.name,
                    "start": s.start_date.isoformat(),
                    "end": s.end_date.isoformat(),
                    "committed": s.committed_points,
                    "completed": s.completed_points,
                    "completion_rate": round(s.completion_rate, 1),
                }
                for s in data.sprints
            ],
            "average_velocity": round(data.average_velocity, 1),
            "last_velocity": data.last_velocity,
            "trend": data.trend,
        }
        print(json.dumps(output, indent=2))
    else:
        # Summary
        console.info(f"Sprints tracked: {len(data.sprints)}")
        console.info(f"Average velocity: {data.average_velocity:.1f} points")
        console.info(f"Last sprint: {data.last_velocity} points")

        trend_symbol = "📈" if data.trend == "up" else ("📉" if data.trend == "down" else "➡️")
        console.info(f"Trend: {trend_symbol} {data.trend}")

        console.print()

        # Chart
        chart = generate_velocity_chart(data.sprints, color=console.color)
        print(chart)

    return ExitCode.SUCCESS
