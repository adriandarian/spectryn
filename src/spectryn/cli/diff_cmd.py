"""
Diff Command - Compare local file vs tracker state.

Shows differences between:
- Local markdown file state
- Current state in issue tracker (Jira, GitHub, etc.)

Helps identify:
- Stories that have been updated in tracker
- Stories that have been updated locally
- Conflicts between local and remote
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

from .exit_codes import ExitCode
from .output import Colors, Console, Symbols


@dataclass
class FieldDiff:
    """Difference in a single field."""

    field_name: str
    local_value: str | None
    remote_value: str | None

    @property
    def is_added(self) -> bool:
        """Field exists locally but not remotely."""
        return self.remote_value is None and self.local_value is not None

    @property
    def is_removed(self) -> bool:
        """Field exists remotely but not locally."""
        return self.local_value is None and self.remote_value is not None

    @property
    def is_changed(self) -> bool:
        """Field has different values."""
        return self.local_value != self.remote_value


@dataclass
class StoryDiff:
    """Difference for a single story."""

    story_id: str
    title: str
    external_key: str | None = None
    field_diffs: list[FieldDiff] = field(default_factory=list)
    is_new_local: bool = False
    is_new_remote: bool = False

    @property
    def has_changes(self) -> bool:
        """Check if there are any differences."""
        return bool(self.field_diffs) or self.is_new_local or self.is_new_remote


@dataclass
class DiffResult:
    """Complete diff result."""

    local_path: str
    remote_source: str
    story_diffs: list[StoryDiff] = field(default_factory=list)
    local_only: list[str] = field(default_factory=list)  # Story IDs only in local
    remote_only: list[str] = field(default_factory=list)  # Story IDs only in remote

    @property
    def has_changes(self) -> bool:
        """Check if there are any differences."""
        return bool(self.story_diffs) or bool(self.local_only) or bool(self.remote_only)

    @property
    def total_changes(self) -> int:
        """Total number of changed stories."""
        return (
            sum(1 for s in self.story_diffs if s.has_changes)
            + len(self.local_only)
            + len(self.remote_only)
        )


def compare_stories(local_story, remote_issue: dict) -> list[FieldDiff]:
    """
    Compare a local story with remote issue data.

    Args:
        local_story: Local UserStory object.
        remote_issue: Remote issue data from tracker.

    Returns:
        List of field differences.
    """
    diffs = []

    # Compare title/summary
    remote_title = remote_issue.get("summary", "")
    if local_story.title != remote_title:
        diffs.append(
            FieldDiff(
                field_name="Title",
                local_value=local_story.title,
                remote_value=remote_title,
            )
        )

    # Compare status
    remote_status = remote_issue.get("status", {}).get("name", "")
    local_status = local_story.status.value if local_story.status else ""
    if local_status.lower() != remote_status.lower():
        diffs.append(
            FieldDiff(
                field_name="Status",
                local_value=local_status,
                remote_value=remote_status,
            )
        )

    # Compare story points
    remote_points = remote_issue.get("customfield_10016")  # Story points field
    local_points = local_story.story_points
    if local_points != remote_points:
        diffs.append(
            FieldDiff(
                field_name="Story Points",
                local_value=str(local_points) if local_points else None,
                remote_value=str(remote_points) if remote_points else None,
            )
        )

    # Compare priority
    remote_priority = remote_issue.get("priority", {}).get("name", "")
    local_priority = local_story.priority.value if local_story.priority else ""
    if local_priority.lower() != remote_priority.lower():
        diffs.append(
            FieldDiff(
                field_name="Priority",
                local_value=local_priority,
                remote_value=remote_priority,
            )
        )

    # Compare subtask count
    remote_subtasks = len(remote_issue.get("subtasks", []))
    local_subtasks = len(local_story.subtasks) if local_story.subtasks else 0
    if local_subtasks != remote_subtasks:
        diffs.append(
            FieldDiff(
                field_name="Subtasks",
                local_value=str(local_subtasks),
                remote_value=str(remote_subtasks),
            )
        )

    return diffs


def format_diff(diff_result: DiffResult, color: bool = True) -> str:
    """
    Format diff result for display with enhanced colors.

    Args:
        diff_result: DiffResult to format.
        color: Whether to use colors.

    Returns:
        Formatted string.
    """
    lines = []

    # Header with enhanced styling
    if color:
        lines.append(f"{Colors.BOLD}{Colors.CYAN}Diff: Local vs Tracker{Colors.RESET}")
        lines.append(f"{Colors.DIM}{'=' * 60}{Colors.RESET}")
    else:
        lines.append("Diff: Local vs Tracker")
        lines.append("=" * 60)

    lines.append(f"  {Colors.DIM}Local:{Colors.RESET}  {diff_result.local_path}")
    lines.append(f"  {Colors.DIM}Remote:{Colors.RESET} {diff_result.remote_source}")
    lines.append("")

    if not diff_result.has_changes:
        if color:
            lines.append(
                f"{Colors.GREEN}{Colors.BOLD}{Symbols.CHECK} No differences found{Colors.RESET}"
            )
        else:
            lines.append("✓ No differences found")
        return "\n".join(lines)

    # Summary with color
    if color:
        lines.append(
            f"  {Colors.BOLD}Changes:{Colors.RESET} "
            f"{Colors.YELLOW}{diff_result.total_changes}{Colors.RESET} story/stories"
        )
    else:
        lines.append(f"  Changes: {diff_result.total_changes} story/stories")
    lines.append("")

    # New local stories - enhanced formatting
    if diff_result.local_only:
        if color:
            lines.append(f"{Colors.GREEN}{Colors.BOLD}Local Only (to be created):{Colors.RESET}")
        else:
            lines.append("Local Only (to be created):")

        for story_id in diff_result.local_only:
            if color:
                lines.append(
                    f"  {Colors.GREEN}{Colors.BOLD}+{Colors.RESET} "
                    f"{Colors.GREEN}{story_id}{Colors.RESET}"
                )
            else:
                lines.append(f"  + {story_id}")
        lines.append("")

    # Remote only stories - enhanced formatting
    if diff_result.remote_only:
        if color:
            lines.append(f"{Colors.RED}{Colors.BOLD}Remote Only (not in local):{Colors.RESET}")
        else:
            lines.append("Remote Only (not in local):")

        for story_id in diff_result.remote_only:
            if color:
                lines.append(
                    f"  {Colors.RED}{Colors.BOLD}-{Colors.RESET} "
                    f"{Colors.RED}{story_id}{Colors.RESET}"
                )
            else:
                lines.append(f"  - {story_id}")
        lines.append("")

    # Changed stories - enhanced formatting with better field visualization
    changed = [s for s in diff_result.story_diffs if s.has_changes]
    if changed:
        if color:
            lines.append(f"{Colors.YELLOW}{Colors.BOLD}Modified Stories:{Colors.RESET}")
        else:
            lines.append("Modified Stories:")

        for story in changed:
            title_display = story.title[:40] + "..." if len(story.title) > 40 else story.title

            # Story header with key if available
            if story.external_key:
                story_header = f"{story.story_id} ({story.external_key})"
            else:
                story_header = story.story_id

            if color:
                lines.append(
                    f"  {Colors.YELLOW}{Colors.BOLD}~{Colors.RESET} "
                    f"{Colors.BOLD}{story_header}{Colors.RESET}: {title_display}"
                )
            else:
                lines.append(f"  ~ {story_header}: {title_display}")

            # Field diffs with enhanced formatting
            for field_diff in story.field_diffs:
                local_val = (
                    field_diff.local_value or f"{Colors.DIM}(none){Colors.RESET}"
                    if color
                    else "(none)"
                )
                remote_val = (
                    field_diff.remote_value or f"{Colors.DIM}(none){Colors.RESET}"
                    if color
                    else "(none)"
                )

                # Truncate long values for better display
                max_val_length = 50
                if isinstance(local_val, str) and len(local_val) > max_val_length:
                    local_val = local_val[: max_val_length - 3] + "..."
                if isinstance(remote_val, str) and len(remote_val) > max_val_length:
                    remote_val = remote_val[: max_val_length - 3] + "..."

                if color:
                    # Special formatting for status/priority
                    if field_diff.field_name.lower() in ("status", "priority"):
                        lines.append(
                            f"      {Colors.BOLD}{field_diff.field_name}:{Colors.RESET} "
                            f"{Colors.RED}{Colors.BOLD}{remote_val}{Colors.RESET} "
                            f"{Colors.DIM}→{Colors.RESET} "
                            f"{Colors.GREEN}{Colors.BOLD}{local_val}{Colors.RESET}"
                        )
                    else:
                        lines.append(
                            f"      {Colors.BOLD}{field_diff.field_name}:{Colors.RESET} "
                            f"{Colors.RED}{remote_val}{Colors.RESET} "
                            f"{Colors.DIM}→{Colors.RESET} "
                            f"{Colors.GREEN}{local_val}{Colors.RESET}"
                        )
                else:
                    lines.append(f"      {field_diff.field_name}: {remote_val} → {local_val}")

        lines.append("")

    return "\n".join(lines)


def run_diff(
    console: Console,
    input_path: str,
    epic_key: str,
    output_format: str = "text",
) -> int:
    """
    Run the diff command.

    Args:
        console: Console for output.
        input_path: Path to markdown file.
        epic_key: Epic key in tracker.
        output_format: Output format (text, json).

    Returns:
        Exit code.
    """
    from spectryn.adapters import ADFFormatter, EnvironmentConfigProvider, JiraAdapter
    from spectryn.adapters.parsers import MarkdownParser

    from .logging import setup_logging

    setup_logging(level=logging.INFO)

    console.header(f"spectra Diff {Symbols.DIFF}")
    console.print()

    # Check file exists
    if not Path(input_path).exists():
        console.error(f"File not found: {input_path}")
        return ExitCode.FILE_NOT_FOUND

    console.info(f"Local:  {input_path}")
    console.info(f"Remote: {epic_key}")
    console.print()

    # Load configuration
    config_provider = EnvironmentConfigProvider()
    errors = config_provider.validate()

    if errors:
        console.config_errors(errors)
        return ExitCode.CONFIG_ERROR

    config = config_provider.load()

    # Initialize components
    formatter = ADFFormatter()
    tracker = JiraAdapter(
        config=config.tracker,
        dry_run=True,
        formatter=formatter,
    )
    parser = MarkdownParser()

    # Test connection
    console.info("Connecting to tracker...")
    if not tracker.test_connection():
        console.connection_error(config.tracker.url)
        return ExitCode.CONNECTION_ERROR

    console.success("Connected")
    console.print()

    # Parse local stories
    console.info("Parsing local file...")
    local_stories = parser.parse_stories(input_path)
    console.info(f"Found {len(local_stories)} local stories")

    # Fetch remote issues
    console.info("Fetching remote issues...")
    try:
        remote_issues = tracker.get_epic_issues(epic_key)
        console.info(f"Found {len(remote_issues)} remote issues")
    except Exception as e:
        console.error(f"Failed to fetch remote issues: {e}")
        return ExitCode.CONNECTION_ERROR

    console.print()

    # Build diff
    diff_result = DiffResult(
        local_path=input_path,
        remote_source=f"{config.tracker.url}/browse/{epic_key}",
    )

    # Create lookup maps
    remote_by_key = {issue.get("key"): issue for issue in remote_issues}

    # Also try to match by title for unmapped stories
    remote_by_title = {
        issue.get("fields", {}).get("summary", "").lower(): issue for issue in remote_issues
    }

    # Find stories with external keys (already mapped)
    for story in local_stories:
        if story.external_key and story.external_key in remote_by_key:
            remote_issue = remote_by_key[story.external_key]
            fields = remote_issue.get("fields", {})
            field_diffs = compare_stories(story, fields)

            if field_diffs:
                diff_result.story_diffs.append(
                    StoryDiff(
                        story_id=str(story.id),
                        title=story.title,
                        external_key=story.external_key,
                        field_diffs=field_diffs,
                    )
                )

            # Mark as processed
            del remote_by_key[story.external_key]
        else:
            # Try to match by title
            title_lower = story.title.lower()
            if title_lower in remote_by_title:
                remote_issue = remote_by_title[title_lower]
                remote_key = remote_issue.get("key")
                fields = remote_issue.get("fields", {})
                field_diffs = compare_stories(story, fields)

                if field_diffs:
                    diff_result.story_diffs.append(
                        StoryDiff(
                            story_id=str(story.id),
                            title=story.title,
                            external_key=remote_key,
                            field_diffs=field_diffs,
                        )
                    )

                remote_by_key.pop(remote_key, None)
            else:
                # Story only exists locally
                diff_result.local_only.append(str(story.id))

    # Remaining remote issues are remote-only
    for key, issue in remote_by_key.items():
        # Skip subtasks
        if issue.get("fields", {}).get("issuetype", {}).get("subtask"):
            continue
        diff_result.remote_only.append(key)

    # Output
    if output_format == "json":
        import json

        data = {
            "local_path": diff_result.local_path,
            "remote_source": diff_result.remote_source,
            "has_changes": diff_result.has_changes,
            "total_changes": diff_result.total_changes,
            "local_only": diff_result.local_only,
            "remote_only": diff_result.remote_only,
            "modified": [
                {
                    "story_id": s.story_id,
                    "title": s.title,
                    "external_key": s.external_key,
                    "field_changes": [
                        {
                            "field": f.field_name,
                            "local": f.local_value,
                            "remote": f.remote_value,
                        }
                        for f in s.field_diffs
                    ],
                }
                for s in diff_result.story_diffs
            ],
        }
        print(json.dumps(data, indent=2))
    else:
        formatted = format_diff(diff_result, color=console.color)
        print(formatted)

    # Exit code based on changes
    if diff_result.has_changes:
        return ExitCode.SUCCESS  # Changes found but not an error
    return ExitCode.SUCCESS
