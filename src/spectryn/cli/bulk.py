"""Bulk operations commands for spectra.

Provides bulk-update and bulk-assign functionality for stories.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .exit_codes import ExitCode
from .output import Colors, Console


@dataclass
class StoryFilter:
    """Filter criteria for selecting stories."""

    status: str | None = None
    priority: str | None = None
    assignee: str | None = None
    labels: list[str] = field(default_factory=list)
    points_min: int | None = None
    points_max: int | None = None
    title_pattern: str | None = None
    epic_key: str | None = None


@dataclass
class BulkUpdateSpec:
    """Specification for bulk update operation."""

    filter: StoryFilter
    updates: dict[str, Any]


@dataclass
class BulkResult:
    """Result of a bulk operation."""

    total_matched: int = 0
    total_updated: int = 0
    total_failed: int = 0
    updated_keys: list[str] = field(default_factory=list)
    failed_keys: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def parse_filter(filter_str: str) -> StoryFilter:
    """Parse a filter string into a StoryFilter.

    Filter format: field=value,field=value,...
    Examples:
        status=planned
        priority=high,status=in_progress
        points>=5,labels=backend

    Args:
        filter_str: Filter string to parse

    Returns:
        Parsed StoryFilter
    """
    story_filter = StoryFilter()

    if not filter_str:
        return story_filter

    parts = filter_str.split(",")

    for part in parts:
        part = part.strip()

        # Handle operators: =, >=, <=, !=
        if ">=" in part:
            key, value = part.split(">=", 1)
            key = key.strip().lower()
            value = value.strip()

            if key == "points":
                story_filter.points_min = int(value)
        elif "<=" in part:
            key, value = part.split("<=", 1)
            key = key.strip().lower()
            value = value.strip()

            if key == "points":
                story_filter.points_max = int(value)
        elif "=" in part:
            key, value = part.split("=", 1)
            key = key.strip().lower()
            value = value.strip()

            if key == "status":
                story_filter.status = value
            elif key == "priority":
                story_filter.priority = value
            elif key == "assignee":
                story_filter.assignee = value
            elif key == "labels":
                story_filter.labels = [v.strip() for v in value.split("|")]
            elif key == "epic":
                story_filter.epic_key = value
            elif key == "title":
                story_filter.title_pattern = value

    return story_filter


def parse_updates(update_str: str) -> dict[str, Any]:
    """Parse an update string into field updates.

    Format: field=value,field=value,...
    Examples:
        status=in_progress
        priority=high,labels=urgent

    Args:
        update_str: Update string to parse

    Returns:
        Dictionary of field updates
    """
    updates: dict[str, Any] = {}

    if not update_str:
        return updates

    parts = update_str.split(",")

    for part in parts:
        part = part.strip()

        if "=" in part:
            key, value = part.split("=", 1)
            key = key.strip().lower()
            value = value.strip()

            if key == "status":
                updates["status"] = value
            elif key == "priority":
                updates["priority"] = value
            elif key == "labels":
                updates["labels"] = [v.strip() for v in value.split("|")]
            elif key == "assignee":
                updates["assignee"] = value
            elif key == "points":
                updates["story_points"] = int(value)

    return updates


def matches_filter(story: Any, story_filter: StoryFilter) -> bool:
    """Check if a story matches the filter criteria.

    Args:
        story: Story to check (can be dict or UserStory)
        story_filter: Filter criteria

    Returns:
        True if story matches all filter criteria
    """
    # Handle both dict and UserStory objects
    if hasattr(story, "status"):
        status = story.status.name.lower() if story.status else ""
        priority = story.priority.name.lower() if story.priority else ""
        points = story.story_points or 0
        title = story.title or ""
        assignee = getattr(story, "assignee", "") or ""
        labels = getattr(story, "labels", []) or []
    else:
        status = str(story.get("status", "")).lower()
        priority = str(story.get("priority", "")).lower()
        points = story.get("story_points", 0) or 0
        title = story.get("title", "") or ""
        assignee = story.get("assignee", "") or ""
        labels = story.get("labels", []) or []

    # Check status
    if story_filter.status:
        if story_filter.status.lower() not in status:
            return False

    # Check priority
    if story_filter.priority:
        if story_filter.priority.lower() not in priority:
            return False

    # Check assignee
    if story_filter.assignee:
        if story_filter.assignee.lower() not in assignee.lower():
            return False

    # Check labels
    if story_filter.labels:
        if not any(lbl in labels for lbl in story_filter.labels):
            return False

    # Check points range
    if story_filter.points_min is not None:
        if points < story_filter.points_min:
            return False

    if story_filter.points_max is not None:
        if points > story_filter.points_max:
            return False

    # Check title pattern
    if story_filter.title_pattern:
        if not re.search(story_filter.title_pattern, title, re.IGNORECASE):
            return False

    return True


def format_bulk_result(
    result: BulkResult,
    operation: str,
    color: bool = True,
) -> list[str]:
    """Format bulk operation result for display.

    Args:
        result: Result to format
        operation: Operation name (update, assign)
        color: Whether to use colors

    Returns:
        Formatted lines
    """
    lines: list[str] = []

    # Header
    if color:
        lines.append(f"{Colors.BOLD}Bulk {operation.title()} Results{Colors.RESET}")
    else:
        lines.append(f"Bulk {operation.title()} Results")
    lines.append("")

    # Summary
    lines.append(f"  Matched:  {result.total_matched}")
    if color:
        lines.append(f"  Updated:  {Colors.GREEN}{result.total_updated}{Colors.RESET}")
        if result.total_failed > 0:
            lines.append(f"  Failed:   {Colors.RED}{result.total_failed}{Colors.RESET}")
    else:
        lines.append(f"  Updated:  {result.total_updated}")
        if result.total_failed > 0:
            lines.append(f"  Failed:   {result.total_failed}")
    lines.append("")

    # Updated keys
    if result.updated_keys:
        if color:
            lines.append(f"{Colors.GREEN}Updated:{Colors.RESET}")
        else:
            lines.append("Updated:")
        for key in result.updated_keys[:20]:
            lines.append(f"  ✓ {key}")
        if len(result.updated_keys) > 20:
            lines.append(f"  ... and {len(result.updated_keys) - 20} more")
        lines.append("")

    # Failed keys
    if result.failed_keys:
        if color:
            lines.append(f"{Colors.RED}Failed:{Colors.RESET}")
        else:
            lines.append("Failed:")
        for key in result.failed_keys[:10]:
            lines.append(f"  ✗ {key}")
        lines.append("")

    # Errors
    if result.errors:
        if color:
            lines.append(f"{Colors.RED}Errors:{Colors.RESET}")
        else:
            lines.append("Errors:")
        for error in result.errors[:5]:
            lines.append(f"  • {error}")
        lines.append("")

    return lines


def run_bulk_update(
    console: Console | None = None,
    input_path: Path | None = None,
    filter_str: str = "",
    update_str: str = "",
    dry_run: bool = False,
    color: bool = True,
) -> ExitCode:
    """Run bulk update command.

    Args:
        console: Console for output
        input_path: Path to markdown file or epic
        filter_str: Filter string (e.g., "status=planned,priority=high")
        update_str: Update string (e.g., "status=in_progress")
        dry_run: If True, only show what would be updated
        color: Whether to use colors

    Returns:
        Exit code
    """
    console = console or Console(color=color)

    if not input_path:
        console.error("Input file required: --markdown EPIC.md")
        return ExitCode.ERROR

    if not update_str:
        console.error("Update specification required: --set status=in_progress")
        return ExitCode.ERROR

    console.header("Bulk Update")

    # Parse filter and updates
    story_filter = parse_filter(filter_str)
    updates = parse_updates(update_str)

    if not updates:
        console.error("No valid updates specified")
        return ExitCode.ERROR

    console.info(f"Filter: {filter_str or '(all stories)'}")
    console.info(f"Updates: {update_str}")
    console.info(f"Mode: {'dry-run' if dry_run else 'live'}")
    console.print("")

    # Parse stories from file
    if not input_path.exists():
        console.error(f"File not found: {input_path}")
        return ExitCode.ERROR

    try:
        from spectryn.adapters.parsers.markdown import MarkdownParser

        parser = MarkdownParser()
        stories = parser.parse_stories(input_path)
    except Exception as e:
        console.error(f"Failed to parse file: {e}")
        return ExitCode.ERROR

    # Filter stories
    matched_stories = [s for s in stories if matches_filter(s, story_filter)]

    result = BulkResult(total_matched=len(matched_stories))

    if not matched_stories:
        console.warning("No stories matched the filter")
        return ExitCode.SUCCESS

    console.info(f"Matched {len(matched_stories)} stories")

    # Preview matches
    console.print("")
    if color:
        console.print(f"{Colors.BOLD}Matching Stories:{Colors.RESET}")
    else:
        console.print("Matching Stories:")

    for story in matched_stories[:10]:
        story_id = str(story.id)
        status = story.status.name if story.status else "?"
        priority = story.priority.name if story.priority else "?"
        console.print(f"  • {story_id}: {story.title[:40]} [{status}/{priority}]")

    if len(matched_stories) > 10:
        console.print(f"  ... and {len(matched_stories) - 10} more")

    console.print("")

    if dry_run:
        console.info("Dry run - no changes made")
        console.print("")
        console.print("Changes that would be applied:")
        for key, value in updates.items():
            console.print(f"  {key} → {value}")
        return ExitCode.SUCCESS

    # Apply updates (in a real implementation, this would update the tracker)
    console.warning("Bulk update to tracker not yet implemented")
    console.info("This will update stories in your configured tracker")

    # For now, show what would happen
    for story in matched_stories:
        story_id = str(story.id)
        result.updated_keys.append(story_id)
        result.total_updated += 1

    # Show results
    lines = format_bulk_result(result, "update", color)
    for line in lines:
        console.print(line)

    return ExitCode.SUCCESS


def run_bulk_assign(
    console: Console | None = None,
    input_path: Path | None = None,
    filter_str: str = "",
    assignee: str = "",
    dry_run: bool = False,
    color: bool = True,
) -> ExitCode:
    """Run bulk assign command.

    Args:
        console: Console for output
        input_path: Path to markdown file or epic
        filter_str: Filter string (e.g., "status=planned,priority=high")
        assignee: User to assign stories to
        dry_run: If True, only show what would be assigned
        color: Whether to use colors

    Returns:
        Exit code
    """
    console = console or Console(color=color)

    if not input_path:
        console.error("Input file required: --markdown EPIC.md")
        return ExitCode.ERROR

    if not assignee:
        console.error("Assignee required: --assignee username")
        return ExitCode.ERROR

    console.header("Bulk Assign")

    # Parse filter
    story_filter = parse_filter(filter_str)

    console.info(f"Filter: {filter_str or '(all stories)'}")
    console.info(f"Assignee: {assignee}")
    console.info(f"Mode: {'dry-run' if dry_run else 'live'}")
    console.print("")

    # Parse stories from file
    if not input_path.exists():
        console.error(f"File not found: {input_path}")
        return ExitCode.ERROR

    try:
        from spectryn.adapters.parsers.markdown import MarkdownParser

        parser = MarkdownParser()
        stories = parser.parse_stories(input_path)
    except Exception as e:
        console.error(f"Failed to parse file: {e}")
        return ExitCode.ERROR

    # Filter stories
    matched_stories = [s for s in stories if matches_filter(s, story_filter)]

    result = BulkResult(total_matched=len(matched_stories))

    if not matched_stories:
        console.warning("No stories matched the filter")
        return ExitCode.SUCCESS

    console.info(f"Matched {len(matched_stories)} stories")

    # Preview matches
    console.print("")
    if color:
        console.print(f"{Colors.BOLD}Stories to assign to {assignee}:{Colors.RESET}")
    else:
        console.print(f"Stories to assign to {assignee}:")

    for story in matched_stories[:10]:
        story_id = str(story.id)
        current_assignee = getattr(story, "assignee", None) or "unassigned"
        console.print(f"  • {story_id}: {story.title[:40]} (current: {current_assignee})")

    if len(matched_stories) > 10:
        console.print(f"  ... and {len(matched_stories) - 10} more")

    console.print("")

    if dry_run:
        console.info("Dry run - no changes made")
        return ExitCode.SUCCESS

    # Apply assignments (in a real implementation, this would update the tracker)
    console.warning("Bulk assign to tracker not yet implemented")
    console.info("This will assign stories in your configured tracker")

    # For now, show what would happen
    for story in matched_stories:
        story_id = str(story.id)
        result.updated_keys.append(story_id)
        result.total_updated += 1

    # Show results
    lines = format_bulk_result(result, "assign", color)
    for line in lines:
        console.print(line)

    return ExitCode.SUCCESS
