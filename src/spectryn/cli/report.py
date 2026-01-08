"""
Report Command - Generate weekly/monthly progress reports.

Features:
- Sprint summary reports
- Progress tracking
- Velocity metrics
- Burndown charts
- Export to various formats
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from .exit_codes import ExitCode
from .output import Colors, Console, Symbols


@dataclass
class ReportData:
    """Data for a progress report."""

    period: str  # weekly, monthly, sprint
    start_date: datetime
    end_date: datetime

    # Metrics
    stories_total: int = 0
    stories_completed: int = 0
    stories_in_progress: int = 0
    stories_blocked: int = 0

    points_total: int = 0
    points_completed: int = 0

    # Velocity
    velocity: float = 0.0
    velocity_trend: str = "stable"

    # Details
    completed_stories: list[dict] = field(default_factory=list)
    in_progress_stories: list[dict] = field(default_factory=list)
    blocked_stories: list[dict] = field(default_factory=list)

    @property
    def completion_rate(self) -> float:
        """Calculate completion rate."""
        if self.stories_total == 0:
            return 0.0
        return (self.stories_completed / self.stories_total) * 100


def collect_report_data(file_path: str, period: str = "weekly") -> ReportData:
    """
    Collect report data from a markdown file.

    Args:
        file_path: Path to markdown file.
        period: Report period (weekly, monthly, sprint).

    Returns:
        ReportData with collected metrics.
    """
    from spectryn.adapters.parsers import MarkdownParser

    parser = MarkdownParser()
    stories = parser.parse_stories(file_path)

    # Calculate date range
    now = datetime.now()
    if period == "weekly":
        start = now - timedelta(days=7)
    elif period == "monthly":
        start = now - timedelta(days=30)
    else:  # sprint
        start = now - timedelta(days=14)

    report = ReportData(
        period=period,
        start_date=start,
        end_date=now,
        stories_total=len(stories),
    )

    for story in stories:
        status = story.status.value.lower() if story.status else "planned"
        points = story.story_points or 0
        report.points_total += points

        story_data = {
            "id": str(story.id),
            "title": story.title,
            "points": points,
            "status": status,
            "priority": story.priority.value if story.priority else "Medium",
        }

        if status in ("done", "closed", "resolved"):
            report.stories_completed += 1
            report.points_completed += points
            report.completed_stories.append(story_data)
        elif status in ("in_progress", "in progress", "active"):
            report.stories_in_progress += 1
            report.in_progress_stories.append(story_data)
        elif status == "blocked":
            report.stories_blocked += 1
            report.blocked_stories.append(story_data)

    # Calculate velocity
    if period == "weekly":
        report.velocity = report.points_completed
    elif period == "monthly":
        report.velocity = report.points_completed / 4  # Weekly average
    else:
        report.velocity = report.points_completed

    return report


def format_text_report(report: ReportData, color: bool = True) -> str:
    """Format report as text."""
    lines = []

    # Header
    period_name = report.period.capitalize()
    if color:
        lines.append(f"{Colors.BOLD}📊 {period_name} Progress Report{Colors.RESET}")
    else:
        lines.append(f"📊 {period_name} Progress Report")

    lines.append("=" * 60)
    lines.append(
        f"Period: {report.start_date.strftime('%Y-%m-%d')} to {report.end_date.strftime('%Y-%m-%d')}"
    )
    lines.append("")

    # Summary
    if color:
        lines.append(f"{Colors.BOLD}Summary{Colors.RESET}")
    else:
        lines.append("Summary")
    lines.append("-" * 40)

    completion_bar = _progress_bar(report.completion_rate, color=color)
    lines.append(f"  Stories: {report.stories_completed}/{report.stories_total} completed")
    lines.append(f"  Points:  {report.points_completed}/{report.points_total}")
    lines.append(f"  Progress: {completion_bar}")
    lines.append("")

    # Status breakdown
    if color:
        lines.append(f"{Colors.BOLD}Status Breakdown{Colors.RESET}")
    else:
        lines.append("Status Breakdown")
    lines.append("-" * 40)

    if color:
        lines.append(f"  {Colors.GREEN}✅ Completed:{Colors.RESET} {report.stories_completed}")
        lines.append(f"  {Colors.YELLOW}🔄 In Progress:{Colors.RESET} {report.stories_in_progress}")
        lines.append(f"  {Colors.RED}⏸️  Blocked:{Colors.RESET} {report.stories_blocked}")
    else:
        lines.append(f"  ✅ Completed: {report.stories_completed}")
        lines.append(f"  🔄 In Progress: {report.stories_in_progress}")
        lines.append(f"  ⏸️  Blocked: {report.stories_blocked}")
    lines.append("")

    # Velocity
    if color:
        lines.append(f"{Colors.BOLD}Velocity{Colors.RESET}")
    else:
        lines.append("Velocity")
    lines.append("-" * 40)
    lines.append(f"  {report.period.capitalize()}: {report.velocity:.1f} points")
    lines.append("")

    # Completed stories
    if report.completed_stories:
        if color:
            lines.append(f"{Colors.GREEN}{Colors.BOLD}Completed Stories{Colors.RESET}")
        else:
            lines.append("Completed Stories")
        lines.append("-" * 40)

        for story in report.completed_stories[:10]:
            pts = f"({story['points']} pts)" if story["points"] else ""
            lines.append(f"  ✅ {story['id']}: {story['title'][:40]} {pts}")

        if len(report.completed_stories) > 10:
            lines.append(f"  ... and {len(report.completed_stories) - 10} more")
        lines.append("")

    # In progress
    if report.in_progress_stories:
        if color:
            lines.append(f"{Colors.YELLOW}{Colors.BOLD}In Progress{Colors.RESET}")
        else:
            lines.append("In Progress")
        lines.append("-" * 40)

        for story in report.in_progress_stories[:5]:
            pts = f"({story['points']} pts)" if story["points"] else ""
            lines.append(f"  🔄 {story['id']}: {story['title'][:40]} {pts}")
        lines.append("")

    # Blocked
    if report.blocked_stories:
        if color:
            lines.append(f"{Colors.RED}{Colors.BOLD}Blocked{Colors.RESET}")
        else:
            lines.append("Blocked")
        lines.append("-" * 40)

        for story in report.blocked_stories:
            lines.append(f"  ⏸️  {story['id']}: {story['title'][:40]}")
        lines.append("")

    # Footer
    lines.append("-" * 60)
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    return "\n".join(lines)


def format_html_report(report: ReportData) -> str:
    """Format report as HTML."""
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{report.period.capitalize()} Report</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 2rem;
            background: #f8fafc;
        }}
        h1 {{ color: #1e40af; }}
        .card {{
            background: white;
            border-radius: 8px;
            padding: 1.5rem;
            margin: 1rem 0;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .metric {{
            display: inline-block;
            text-align: center;
            padding: 1rem 2rem;
        }}
        .metric-value {{
            font-size: 2rem;
            font-weight: bold;
            color: #1e40af;
        }}
        .metric-label {{
            font-size: 0.9rem;
            color: #64748b;
        }}
        .progress-bar {{
            background: #e2e8f0;
            border-radius: 9999px;
            height: 8px;
            overflow: hidden;
        }}
        .progress-fill {{
            background: #22c55e;
            height: 100%;
            transition: width 0.3s;
        }}
        .story-list {{ list-style: none; padding: 0; }}
        .story-item {{
            padding: 0.5rem 0;
            border-bottom: 1px solid #e2e8f0;
        }}
        .completed {{ color: #16a34a; }}
        .in-progress {{ color: #d97706; }}
        .blocked {{ color: #dc2626; }}
    </style>
</head>
<body>
    <h1>📊 {report.period.capitalize()} Progress Report</h1>
    <p>{report.start_date.strftime("%Y-%m-%d")} to {report.end_date.strftime("%Y-%m-%d")}</p>

    <div class="card">
        <div class="metric">
            <div class="metric-value">{report.stories_completed}/{report.stories_total}</div>
            <div class="metric-label">Stories Completed</div>
        </div>
        <div class="metric">
            <div class="metric-value">{report.points_completed}</div>
            <div class="metric-label">Points Completed</div>
        </div>
        <div class="metric">
            <div class="metric-value">{report.completion_rate:.0f}%</div>
            <div class="metric-label">Completion Rate</div>
        </div>
    </div>

    <div class="card">
        <h3>Progress</h3>
        <div class="progress-bar">
            <div class="progress-fill" style="width: {report.completion_rate}%"></div>
        </div>
    </div>
"""

    if report.completed_stories:
        html += """
    <div class="card">
        <h3 class="completed">✅ Completed Stories</h3>
        <ul class="story-list">
"""
        for story in report.completed_stories[:10]:
            html += f"""            <li class="story-item">{story["id"]}: {story["title"]}</li>
"""
        html += """        </ul>
    </div>
"""

    if report.in_progress_stories:
        html += """
    <div class="card">
        <h3 class="in-progress">🔄 In Progress</h3>
        <ul class="story-list">
"""
        for story in report.in_progress_stories[:5]:
            html += f"""            <li class="story-item">{story["id"]}: {story["title"]}</li>
"""
        html += """        </ul>
    </div>
"""

    html += f"""
    <footer style="text-align: center; color: #64748b; margin-top: 2rem;">
        Generated by spectra on {datetime.now().strftime("%Y-%m-%d %H:%M")}
    </footer>
</body>
</html>
"""
    return html


def _progress_bar(percentage: float, width: int = 30, color: bool = True) -> str:
    """Create a text progress bar."""
    filled = int(width * percentage / 100)
    empty = width - filled

    if color:
        bar = f"{Colors.GREEN}{'█' * filled}{Colors.DIM}{'░' * empty}{Colors.RESET}"
    else:
        bar = "█" * filled + "░" * empty

    return f"[{bar}] {percentage:.1f}%"


def run_report(
    console: Console,
    input_path: str,
    period: str = "weekly",
    output_path: str | None = None,
    output_format: str = "text",
) -> int:
    """
    Run the report command.

    Args:
        console: Console for output.
        input_path: Path to markdown file.
        period: Report period (weekly, monthly, sprint).
        output_path: Optional output file path.
        output_format: Output format (text, html, json).

    Returns:
        Exit code.
    """
    console.header(f"spectra Report {Symbols.CHART}")
    console.print()

    # Check file exists
    if not Path(input_path).exists():
        console.error(f"File not found: {input_path}")
        return ExitCode.FILE_NOT_FOUND

    console.info(f"Source: {input_path}")
    console.info(f"Period: {period}")
    console.print()

    # Collect data
    console.info("Collecting report data...")
    report = collect_report_data(input_path, period)
    console.print()

    # Format output
    if output_format == "html":
        content = format_html_report(report)
        if output_path:
            Path(output_path).write_text(content, encoding="utf-8")
            console.success(f"Report saved to: {output_path}")
        else:
            print(content)

    elif output_format == "json":
        import json

        data = {
            "period": report.period,
            "start_date": report.start_date.isoformat(),
            "end_date": report.end_date.isoformat(),
            "summary": {
                "stories_total": report.stories_total,
                "stories_completed": report.stories_completed,
                "stories_in_progress": report.stories_in_progress,
                "stories_blocked": report.stories_blocked,
                "points_total": report.points_total,
                "points_completed": report.points_completed,
                "completion_rate": round(report.completion_rate, 1),
                "velocity": round(report.velocity, 1),
            },
            "completed_stories": report.completed_stories,
            "in_progress_stories": report.in_progress_stories,
            "blocked_stories": report.blocked_stories,
        }
        output = json.dumps(data, indent=2)

        if output_path:
            Path(output_path).write_text(output, encoding="utf-8")
            console.success(f"Report saved to: {output_path}")
        else:
            print(output)

    else:  # text
        content = format_text_report(report, color=console.color)

        if output_path:
            # Strip ANSI codes for file output
            import re

            clean = re.sub(r"\x1b\[[0-9;]*m", "", content)
            Path(output_path).write_text(clean, encoding="utf-8")
            console.success(f"Report saved to: {output_path}")
        else:
            print(content)

    return ExitCode.SUCCESS
