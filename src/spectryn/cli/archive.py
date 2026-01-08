"""Archive/unarchive command for spectra.

Provides functionality to archive and unarchive stories in trackers.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .exit_codes import ExitCode
from .output import Colors, Console


@dataclass
class ArchiveResult:
    """Result of an archive operation."""

    total_processed: int = 0
    total_archived: int = 0
    total_unarchived: int = 0
    total_skipped: int = 0
    total_failed: int = 0
    archived_keys: list[str] = field(default_factory=list)
    unarchived_keys: list[str] = field(default_factory=list)
    skipped_keys: list[str] = field(default_factory=list)
    failed_keys: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class ArchiveCandidate:
    """A story that could be archived."""

    key: str
    title: str
    status: str
    last_updated: datetime | None = None
    days_since_update: int = 0
    reason: str = ""


def find_archive_candidates(
    stories: list,
    days_threshold: int = 90,
    status_filter: list[str] | None = None,
) -> list[ArchiveCandidate]:
    """Find stories that are candidates for archiving.

    Criteria:
    - Status is "done", "closed", or "resolved"
    - Not updated in X days (default 90)

    Args:
        stories: List of stories to check
        days_threshold: Days since last update to consider for archiving
        status_filter: Optional list of statuses to include

    Returns:
        List of archive candidates
    """
    candidates: list[ArchiveCandidate] = []
    now = datetime.now()

    done_statuses = status_filter or ["done", "closed", "resolved", "complete", "completed"]

    for story in stories:
        # Extract fields
        if hasattr(story, "id"):
            key = str(story.id)
            title = story.title or ""
            status = story.status.name.lower() if story.status else ""
            # Note: UserStory doesn't have last_updated, so we estimate
            last_updated = None
        else:
            key = str(story.get("key", story.get("id", "")))
            title = story.get("title", story.get("summary", ""))
            status = str(story.get("status", "")).lower()
            last_updated = story.get("updated")

        # Check if eligible for archiving
        if status not in done_statuses:
            continue

        # Calculate days since update
        days = 0
        if last_updated:
            if isinstance(last_updated, str):
                try:
                    last_updated = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
                except ValueError:
                    last_updated = None

            if last_updated:
                days = (now - last_updated.replace(tzinfo=None)).days

        # For local stories without dates, assume they're candidates if done
        if not last_updated:
            days = days_threshold  # Assume eligible

        if days >= days_threshold:
            candidates.append(
                ArchiveCandidate(
                    key=key,
                    title=title[:50],
                    status=status,
                    last_updated=last_updated,
                    days_since_update=days,
                    reason=f"Status: {status}, inactive for {days} days",
                )
            )

    return candidates


def format_archive_result(
    result: ArchiveResult,
    action: str,
    color: bool = True,
) -> list[str]:
    """Format archive result for display.

    Args:
        result: Result to format
        action: Action performed (archive/unarchive)
        color: Whether to use colors

    Returns:
        Formatted lines
    """
    lines: list[str] = []

    # Header
    if color:
        lines.append(f"{Colors.BOLD}Archive Operation Results{Colors.RESET}")
    else:
        lines.append("Archive Operation Results")
    lines.append("")

    # Summary
    lines.append(f"  Processed: {result.total_processed}")

    if action == "archive":
        if color:
            lines.append(f"  Archived:  {Colors.GREEN}{result.total_archived}{Colors.RESET}")
        else:
            lines.append(f"  Archived:  {result.total_archived}")
    elif color:
        lines.append(f"  Unarchived: {Colors.GREEN}{result.total_unarchived}{Colors.RESET}")
    else:
        lines.append(f"  Unarchived: {result.total_unarchived}")

    if result.total_skipped > 0:
        if color:
            lines.append(f"  Skipped:  {Colors.YELLOW}{result.total_skipped}{Colors.RESET}")
        else:
            lines.append(f"  Skipped:  {result.total_skipped}")

    if result.total_failed > 0:
        if color:
            lines.append(f"  Failed:   {Colors.RED}{result.total_failed}{Colors.RESET}")
        else:
            lines.append(f"  Failed:   {result.total_failed}")
    lines.append("")

    # Archived/unarchived keys
    if result.archived_keys:
        if color:
            lines.append(f"{Colors.GREEN}Archived:{Colors.RESET}")
        else:
            lines.append("Archived:")
        for key in result.archived_keys[:15]:
            lines.append(f"  ✓ {key}")
        if len(result.archived_keys) > 15:
            lines.append(f"  ... and {len(result.archived_keys) - 15} more")
        lines.append("")

    if result.unarchived_keys:
        if color:
            lines.append(f"{Colors.GREEN}Unarchived:{Colors.RESET}")
        else:
            lines.append("Unarchived:")
        for key in result.unarchived_keys[:15]:
            lines.append(f"  ✓ {key}")
        if len(result.unarchived_keys) > 15:
            lines.append(f"  ... and {len(result.unarchived_keys) - 15} more")
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


def run_archive(
    console: Console | None = None,
    input_path: Path | None = None,
    action: str = "list",  # list, archive, unarchive
    story_keys: list[str] | None = None,
    days_threshold: int = 90,
    dry_run: bool = False,
    color: bool = True,
) -> ExitCode:
    """Run archive command.

    Args:
        console: Console for output
        input_path: Path to markdown file
        action: Action to perform (list, archive, unarchive)
        story_keys: Specific story keys to archive/unarchive
        days_threshold: Days threshold for auto-detection
        dry_run: If True, only show what would be done
        color: Whether to use colors

    Returns:
        Exit code
    """
    console = console or Console(color=color)

    console.header("Story Archive Management")

    # List action - show candidates
    if action == "list":
        if not input_path:
            console.error("Input file required: --markdown EPIC.md")
            return ExitCode.ERROR

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

        candidates = find_archive_candidates(stories, days_threshold)

        if not candidates:
            console.info("No archive candidates found")
            console.print("")
            console.print(f"  Criteria: Done/Closed stories inactive for {days_threshold}+ days")
            return ExitCode.SUCCESS

        console.info(f"Found {len(candidates)} archive candidates")
        console.print("")

        if color:
            console.print(f"  {Colors.BOLD}Archive Candidates:{Colors.RESET}")
        else:
            console.print("  Archive Candidates:")
        console.print("")

        for candidate in candidates:
            if color:
                console.print(f"    {Colors.DIM}{candidate.key}{Colors.RESET}: {candidate.title}")
            else:
                console.print(f"    {candidate.key}: {candidate.title}")
            console.print(f"      {candidate.reason}")
            console.print("")

        console.print("")
        console.info("To archive these stories:")
        console.print("  spectra --archive archive --markdown EPIC.md")
        console.print("")
        console.info("To archive specific stories:")
        console.print("  spectra --archive archive --story-keys US-001,US-002")

        return ExitCode.SUCCESS

    # Archive action
    if action == "archive":
        result = ArchiveResult()

        if story_keys:
            # Archive specific stories
            result.total_processed = len(story_keys)

            if dry_run:
                console.info("Dry run - showing what would be archived:")
                for key in story_keys:
                    console.print(f"  Would archive: {key}")
                return ExitCode.SUCCESS

            console.warning("Archive to tracker not yet implemented")
            console.info("This will archive stories in your configured tracker")
            console.print("")

            # Simulate archiving
            for key in story_keys:
                result.archived_keys.append(key)
                result.total_archived += 1

        else:
            # Auto-detect candidates
            if not input_path:
                console.error("Provide --markdown or --story-keys")
                return ExitCode.ERROR

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

            candidates = find_archive_candidates(stories, days_threshold)
            result.total_processed = len(candidates)

            if not candidates:
                console.info("No archive candidates found")
                return ExitCode.SUCCESS

            if dry_run:
                console.info("Dry run - showing what would be archived:")
                for candidate in candidates:
                    console.print(f"  Would archive: {candidate.key} - {candidate.title}")
                return ExitCode.SUCCESS

            console.warning("Archive to tracker not yet implemented")

            for candidate in candidates:
                result.archived_keys.append(candidate.key)
                result.total_archived += 1

        # Show results
        lines = format_archive_result(result, "archive", color)
        for line in lines:
            console.print(line)

        return ExitCode.SUCCESS

    # Unarchive action
    if action == "unarchive":
        if not story_keys:
            console.error("--story-keys required for unarchive")
            console.print("  Example: spectra --archive unarchive --story-keys US-001,US-002")
            return ExitCode.ERROR

        result = ArchiveResult()
        result.total_processed = len(story_keys)

        if dry_run:
            console.info("Dry run - showing what would be unarchived:")
            for key in story_keys:
                console.print(f"  Would unarchive: {key}")
            return ExitCode.SUCCESS

        console.warning("Unarchive from tracker not yet implemented")
        console.info("This will unarchive stories in your configured tracker")
        console.print("")

        # Simulate unarchiving
        for key in story_keys:
            result.unarchived_keys.append(key)
            result.total_unarchived += 1

        # Show results
        lines = format_archive_result(result, "unarchive", color)
        for line in lines:
            console.print(line)

        return ExitCode.SUCCESS

    console.error(f"Unknown action: {action}")
    console.print("  Valid actions: list, archive, unarchive")
    return ExitCode.ERROR
