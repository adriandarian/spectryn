"""
Source File Updater - Update markdown files with tracker information.

Updates the source markdown file after successful sync operations
to record the tracker type, issue key, URL, and sync metadata for stories and subtasks.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from spectra.core.domain.entities import Subtask, UserStory
from spectra.core.ports.config_provider import TrackerType


if TYPE_CHECKING:
    pass


class SyncStatus:
    """Sync status constants."""

    SYNCED = "synced"
    PENDING = "pending"
    MODIFIED = "modified"
    CONFLICT = "conflict"

    @staticmethod
    def emoji(status: str) -> str:
        """Get emoji for sync status."""
        return {
            SyncStatus.SYNCED: "✅",
            SyncStatus.PENDING: "⏳",
            SyncStatus.MODIFIED: "📝",
            SyncStatus.CONFLICT: "⚠️",
        }.get(status, "❓")


@dataclass
class TrackerInfo:
    """Information about a synced issue in the tracker."""

    tracker_type: TrackerType
    issue_key: str
    issue_url: str
    last_synced: datetime | None = None
    sync_status: str = SyncStatus.SYNCED
    content_hash: str | None = None


@dataclass
class EpicTrackerInfo:
    """Information about a synced epic in the tracker."""

    tracker_type: TrackerType
    epic_key: str
    epic_url: str
    last_synced: datetime | None = None
    total_stories: int = 0
    synced_stories: int = 0


@dataclass
class SubtaskTrackerInfo:
    """Information about a synced subtask in the tracker."""

    issue_key: str
    issue_url: str


@dataclass
class SourceUpdateResult:
    """Result of a source file update operation."""

    success: bool = True
    stories_updated: int = 0
    stories_skipped: int = 0
    subtasks_updated: int = 0
    epic_updated: bool = False
    file_path: str = ""
    errors: list[str] = field(default_factory=list)

    def add_error(self, error: str) -> None:
        """Add an error and mark as failed."""
        self.errors.append(error)
        self.success = False

    @property
    def summary(self) -> str:
        """Get a human-readable summary."""
        if self.success:
            parts = []
            if self.stories_updated > 0:
                parts.append(f"{self.stories_updated} stories")
            if self.subtasks_updated > 0:
                parts.append(f"{self.subtasks_updated} subtasks")
            if self.epic_updated:
                parts.append("epic header")
            if parts:
                return f"Updated {', '.join(parts)} in {self.file_path}"
            return f"No updates needed in {self.file_path}"
        return f"Failed to update {self.file_path}: {'; '.join(self.errors)}"


def compute_content_hash(content: str) -> str:
    """
    Compute a short hash of content for change detection.

    Args:
        content: The content to hash.

    Returns:
        8-character hex hash string.
    """
    # Normalize whitespace for consistent hashing
    normalized = " ".join(content.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:8]


def compute_story_content_hash(story: UserStory) -> str:
    """
    Compute a hash of story content for change detection.

    Includes title, description, acceptance criteria, and subtask names.

    Args:
        story: The story to hash.

    Returns:
        8-character hex hash string.
    """
    parts = [
        str(story.id),
        story.title,
        story.description.to_markdown() if story.description else "",
        story.acceptance_criteria.to_markdown() if story.acceptance_criteria else "",
        story.technical_notes,
        str(story.story_points),
        story.priority.name,
        ",".join(st.name for st in story.subtasks),
    ]
    content = "|".join(parts)
    return compute_content_hash(content)


class SourceFileUpdater:
    """
    Updates markdown source files with tracker information.

    After a successful sync, this service writes back:
    - Tracker type (jira, github, linear, azure_devops)
    - Issue key (PROJ-123, #456, etc.)
    - Issue URL (clickable link to view)
    - Last sync timestamp
    - Sync status indicator
    - Content hash for conflict detection
    - Subtask tracker info
    - Epic-level tracker info

    This enables:
    - Direct navigation from markdown to tracker
    - Reliable re-sync without re-matching
    - Audit trail of what's synced where
    - Conflict detection between local and remote changes

    Example usage:
        >>> updater = SourceFileUpdater(
        ...     tracker_type=TrackerType.JIRA,
        ...     base_url="https://company.atlassian.net"
        ... )
        >>> result = updater.update_file(
        ...     Path("EPIC.md"),
        ...     synced_stories,
        ...     epic_key="PROJ-100"
        ... )
        >>> print(result.summary)
        Updated 5 stories, 12 subtasks, epic header in EPIC.md
    """

    # Pattern to find story headers (any PREFIX-NUMBER format)
    STORY_HEADER_PATTERN = r"(#{1,3}\s+[^\n]*\s+)({story_id})(:.*?\n)"

    # Tracker info blockquote patterns for detection (extended)
    # Note: colon is INSIDE the bold markers (**Tracker:**) in markdown
    # \s* at start allows for optional leading whitespace/newlines
    TRACKER_INFO_PATTERNS = [
        # Full tracker block with optional extra fields
        r"\s*(?:>\s*\*\*(?:Tracker|Issue|Last Synced|Sync Status|Content Hash):\*\*\s*[^\n]+\n)+",
        # Legacy shorthand format
        r"\s*>\s*\*\*(?:Jira|GitHub|Linear|Azure(?:\s*DevOps)?):\*\*\s*\[[^\]]+\]\([^)]+\)\n?",
    ]

    # Epic header patterns
    EPIC_TRACKER_PATTERN = (
        r"\s*(?:>\s*\*\*(?:Epic Tracker|Epic Issue|Epic Synced|Stories Synced):\*\*\s*[^\n]+\n)+"
    )

    def __init__(
        self,
        tracker_type: TrackerType,
        base_url: str,
    ):
        """
        Initialize the updater.

        Args:
            tracker_type: The type of tracker being used.
            base_url: Base URL for constructing issue links.
        """
        self.tracker_type = tracker_type
        self.base_url = base_url.rstrip("/")
        self.logger = logging.getLogger("SourceFileUpdater")

    def update_file(
        self,
        file_path: Path,
        stories: list[UserStory],
        epic_key: str | None = None,
        dry_run: bool = False,
    ) -> SourceUpdateResult:
        """
        Update a markdown file with tracker info for synced stories.

        Args:
            file_path: Path to the markdown file.
            stories: Stories that have been synced (with external_key set).
            epic_key: Optional epic key to add to document header.
            dry_run: If True, don't write changes to disk.

        Returns:
            SourceUpdateResult with details of changes made.
        """
        result = SourceUpdateResult(file_path=str(file_path))

        if not file_path.exists():
            result.add_error(f"File not found: {file_path}")
            return result

        try:
            content = file_path.read_text(encoding="utf-8")
            original = content

            # Update epic header if epic_key provided
            if epic_key:
                content = self._update_epic_header(content, epic_key, stories)
                result.epic_updated = True

            # Update each story
            for story in stories:
                if not story.external_key:
                    result.stories_skipped += 1
                    continue

                issue_key = str(story.external_key)
                issue_url = story.external_url or self._build_url(issue_key)

                tracker_info = TrackerInfo(
                    tracker_type=self.tracker_type,
                    issue_key=issue_key,
                    issue_url=issue_url,
                    last_synced=datetime.now(timezone.utc),
                    sync_status=SyncStatus.SYNCED,
                    content_hash=compute_story_content_hash(story),
                )

                new_content = self._update_story_tracker_info(
                    content=content,
                    story_id=str(story.id),
                    tracker_info=tracker_info,
                )

                if new_content != content:
                    content = new_content
                    result.stories_updated += 1
                    self.logger.debug(f"Updated tracker info for {story.id}")

                # Update subtasks
                if story.subtasks:
                    subtask_count = self._update_subtasks_tracker_info(
                        content, str(story.id), story.subtasks
                    )
                    if subtask_count > 0:
                        # Re-read content after subtask updates
                        # (subtask updates modify content in place)
                        new_content = self._update_subtasks_in_content(
                            content, str(story.id), story.subtasks
                        )
                        if new_content != content:
                            content = new_content
                            result.subtasks_updated += subtask_count

            if content != original and not dry_run:
                file_path.write_text(content, encoding="utf-8")
                self.logger.info(f"Updated {file_path}: {result.summary}")
            elif content != original:
                self.logger.info(f"[DRY RUN] Would update: {result.summary}")

        except PermissionError:
            result.add_error(f"Permission denied writing to {file_path}")
        except Exception as e:
            result.add_error(f"Unexpected error: {e}")
            self.logger.exception(f"Failed to update {file_path}")

        return result

    def update_directory(
        self,
        directory: Path,
        stories: list[UserStory],
        epic_key: str | None = None,
        dry_run: bool = False,
    ) -> list[SourceUpdateResult]:
        """
        Update all markdown files in a directory with tracker info.

        For directory-based projects where stories are split across files.

        Args:
            directory: Directory containing markdown files.
            stories: Stories that have been synced.
            epic_key: Optional epic key to add to EPIC.md header.
            dry_run: If True, don't write changes to disk.

        Returns:
            List of SourceUpdateResult for each file updated.
        """
        results = []

        # Build a map of story_id -> story for efficient lookup
        story_map = {str(s.id): s for s in stories if s.external_key}

        # Update EPIC.md first if it exists and we have an epic_key
        epic_file = directory / "EPIC.md"
        if epic_file.exists() and epic_key:
            # Find stories mentioned in EPIC.md
            content = epic_file.read_text(encoding="utf-8")
            stories_in_epic = []
            for story_id, story in story_map.items():
                if re.search(rf"#{{1,3}}\s+[^\n]*{re.escape(story_id)}:", content):
                    stories_in_epic.append(story)

            result = self.update_file(epic_file, stories_in_epic, epic_key, dry_run)
            results.append(result)

        # Process other markdown files
        for md_file in directory.glob("*.md"):
            if md_file.name.lower() == "epic.md":
                continue  # Already processed

            content = md_file.read_text(encoding="utf-8")

            # Find which stories are in this file
            stories_in_file = []
            for story_id, story in story_map.items():
                if re.search(rf"#{{1,3}}\s+[^\n]*{re.escape(story_id)}:", content):
                    stories_in_file.append(story)

            if stories_in_file:
                result = self.update_file(md_file, stories_in_file, None, dry_run)
                results.append(result)

        return results

    def _update_epic_header(
        self,
        content: str,
        epic_key: str,
        stories: list[UserStory],
    ) -> str:
        """
        Update or insert epic tracker info at document header.

        Args:
            content: Full markdown content.
            epic_key: The epic key (e.g., "PROJ-100").
            stories: List of stories for counting.

        Returns:
            Updated content.
        """
        epic_url = self._build_url(epic_key)
        synced_count = sum(1 for s in stories if s.external_key)
        total_count = len(stories)

        epic_info = EpicTrackerInfo(
            tracker_type=self.tracker_type,
            epic_key=epic_key,
            epic_url=epic_url,
            last_synced=datetime.now(timezone.utc),
            total_stories=total_count,
            synced_stories=synced_count,
        )

        epic_block = self._format_epic_tracker_block(epic_info)

        # Find the first h1 header
        h1_match = re.search(r"^(#\s+[^\n]+\n)", content, re.MULTILINE)

        if not h1_match:
            # No h1 header, insert at beginning
            return epic_block + "\n\n" + content

        h1_end = h1_match.end()
        after_h1 = content[h1_end:]

        # Check if epic tracker info already exists
        existing_match = re.match(self.EPIC_TRACKER_PATTERN, after_h1, re.IGNORECASE)

        if existing_match:
            # Replace existing epic info
            block_end = h1_end + existing_match.end()
            content = content[:h1_end] + "\n" + epic_block + "\n" + content[block_end:].lstrip()
        else:
            # Insert new epic info after h1
            content = content[:h1_end] + "\n" + epic_block + "\n" + content[h1_end:]

        return content

    def _update_story_tracker_info(
        self,
        content: str,
        story_id: str,
        tracker_info: TrackerInfo,
    ) -> str:
        """
        Update or insert tracker info for a single story.

        Args:
            content: Full markdown content.
            story_id: Story ID to update (e.g., "US-001").
            tracker_info: Tracker information to write.

        Returns:
            Updated content.
        """
        # Find the story header with flexible pattern
        # Matches: ### ✅ US-001: Title  or  # US-001: Title  etc.
        # Note: doubled braces {{1,3}} to escape them in the f-string
        header_pattern = rf"(#{{1,3}}\s+[^\n]*?{re.escape(story_id)}:\s*[^\n]+\n)"
        header_match = re.search(header_pattern, content)

        if not header_match:
            self.logger.warning(f"Story {story_id} not found in content")
            return content

        header_end = header_match.end()
        after_header = content[header_end:]

        # Check if tracker info already exists
        existing_tracker_match = None
        for pattern in self.TRACKER_INFO_PATTERNS:
            match = re.match(pattern, after_header, re.IGNORECASE)
            if match:
                existing_tracker_match = match
                break

        tracker_block = self._format_tracker_block(tracker_info)

        if existing_tracker_match:
            # Replace existing tracker info
            block_end = header_end + existing_tracker_match.end()
            # Preserve one newline after the block
            while block_end < len(content) and content[block_end] == "\n":
                block_end += 1
                break  # Only consume one newline

            content = content[:header_end] + tracker_block + "\n\n" + content[block_end:].lstrip()
        else:
            # Insert new tracker info after header
            content = content[:header_end] + "\n" + tracker_block + "\n" + content[header_end:]

        return content

    def _update_subtasks_tracker_info(
        self,
        content: str,
        story_id: str,
        subtasks: list[Subtask],
    ) -> int:
        """
        Count how many subtasks have tracker info to update.

        Args:
            content: Full markdown content.
            story_id: Story ID the subtasks belong to.
            subtasks: List of subtasks.

        Returns:
            Count of subtasks with external keys.
        """
        return sum(1 for st in subtasks if st.external_key)

    def _update_subtasks_in_content(
        self,
        content: str,
        story_id: str,
        subtasks: list[Subtask],
    ) -> str:
        """
        Update subtask table with tracker links.

        Transforms:
        | # | Subtask | Status |
        |---|---------|--------|
        | 1 | Task A  | Done   |

        To:
        | # | Subtask | Status | Tracker |
        |---|---------|--------|---------|
        | 1 | Task A  | Done   | [PROJ-124](url) |

        Args:
            content: Full markdown content.
            story_id: Story ID the subtasks belong to.
            subtasks: List of subtasks with external_key.

        Returns:
            Updated content with subtask tracker links.
        """
        # Find the subtasks section for this story
        # First, find the story section
        story_pattern = rf"(#{{1,3}}\s+[^\n]*?{re.escape(story_id)}:\s*[^\n]+\n)"
        story_match = re.search(story_pattern, content)

        if not story_match:
            return content

        story_start = story_match.start()

        # Find the next story or end of content
        next_story = re.search(r"\n#{{1,3}}\s+[^\n]*[A-Z]+-\d+:", content[story_match.end() :])
        story_end = story_match.end() + next_story.start() if next_story else len(content)

        story_section = content[story_start:story_end]

        # Find subtasks table in this section
        subtasks_section = re.search(
            r"(#{2,4}\s*Subtasks\s*\n)([\s\S]*?)(?=\n#{2,4}\s|\Z)",
            story_section,
            re.IGNORECASE,
        )

        if not subtasks_section:
            return content

        table_content = subtasks_section.group(2)

        # Check if table already has Tracker column
        has_tracker_column = bool(re.search(r"\|\s*Tracker\s*\|", table_content, re.IGNORECASE))

        if not has_tracker_column:
            # Add Tracker column to header
            table_content = re.sub(
                r"(\|[^\n]+)\|(\s*\n)",
                r"\1| Tracker |\2",
                table_content,
                count=1,
            )
            # Add separator for new column
            table_content = re.sub(
                r"(\|[-|]+)\|(\s*\n)",
                r"\1|---------|\\2",
                table_content,
                count=1,
            )

        # Update each subtask row with tracker link
        for subtask in subtasks:
            if not subtask.external_key:
                continue

            issue_key = str(subtask.external_key)
            issue_url = self._build_url(issue_key)
            tracker_link = f"[{issue_key}]({issue_url})"

            # Find the row for this subtask (match by subtask number or name)
            # Pattern for row: | number | name | ... |
            subtask_name_escaped = re.escape(subtask.name[:30])  # First 30 chars
            row_pattern = (
                rf"(\|\s*{subtask.number}\s*\|[^\n]*{subtask_name_escaped}[^\n]*)\|(\s*\n)"
            )

            if has_tracker_column:
                # Replace existing tracker cell
                table_content = re.sub(
                    row_pattern,
                    rf"\1| {tracker_link} |\2",
                    table_content,
                )
            else:
                # Add tracker cell to row
                table_content = re.sub(
                    row_pattern,
                    rf"\1| {tracker_link} |\2",
                    table_content,
                )

        # Reconstruct the section
        new_section = subtasks_section.group(1) + table_content
        new_story_section = (
            story_section[: subtasks_section.start()]
            + new_section
            + story_section[subtasks_section.end() :]
        )

        return content[:story_start] + new_story_section + content[story_end:]

    def _format_epic_tracker_block(self, info: EpicTrackerInfo) -> str:
        """Format epic tracker info as markdown blockquote."""
        tracker_name = self._get_tracker_display_name(info.tracker_type)
        timestamp = info.last_synced.strftime("%Y-%m-%d %H:%M UTC") if info.last_synced else "Never"

        return (
            f"> **Epic Tracker:** {tracker_name}\n"
            f"> **Epic Issue:** [{info.epic_key}]({info.epic_url})\n"
            f"> **Epic Synced:** {timestamp}\n"
            f"> **Stories Synced:** {info.synced_stories}/{info.total_stories}"
        )

    def _format_tracker_block(self, info: TrackerInfo) -> str:
        """Format tracker info as markdown blockquote with full metadata."""
        tracker_name = self._get_tracker_display_name(info.tracker_type)
        timestamp = info.last_synced.strftime("%Y-%m-%d %H:%M UTC") if info.last_synced else "Never"
        status_emoji = SyncStatus.emoji(info.sync_status)

        lines = [
            f"> **Tracker:** {tracker_name}",
            f"> **Issue:** [{info.issue_key}]({info.issue_url})",
            f"> **Last Synced:** {timestamp}",
            f"> **Sync Status:** {status_emoji} {info.sync_status.title()}",
        ]

        if info.content_hash:
            lines.append(f"> **Content Hash:** `{info.content_hash}`")

        return "\n".join(lines)

    def _get_tracker_display_name(self, tracker_type: TrackerType) -> str:
        """Get human-readable tracker name."""
        names = {
            TrackerType.JIRA: "Jira",
            TrackerType.GITHUB: "GitHub",
            TrackerType.LINEAR: "Linear",
            TrackerType.AZURE_DEVOPS: "Azure DevOps",
        }
        return names.get(tracker_type, tracker_type.value.title())

    def _build_url(self, issue_key: str) -> str:
        """
        Build issue URL from key based on tracker type.

        Args:
            issue_key: The issue key (e.g., PROJ-123, #456, 789).

        Returns:
            Full URL to view the issue.
        """
        if self.tracker_type == TrackerType.JIRA:
            return f"{self.base_url}/browse/{issue_key}"

        if self.tracker_type == TrackerType.GITHUB:
            # GitHub URLs: https://github.com/owner/repo/issues/123
            # Extract number from key like "#123" or "123"
            issue_num = issue_key.lstrip("#")
            return f"{self.base_url}/issues/{issue_num}"

        if self.tracker_type == TrackerType.LINEAR:
            # Linear URLs: https://linear.app/team/issue/TEAM-123
            return f"{self.base_url}/issue/{issue_key}"

        if self.tracker_type == TrackerType.AZURE_DEVOPS:
            # Azure DevOps URLs: https://dev.azure.com/org/project/_workitems/edit/123
            return f"{self.base_url}/_workitems/edit/{issue_key}"

        # Fallback for unknown trackers
        return f"{self.base_url}/{issue_key}"


def detect_sync_conflicts(
    file_path: Path,
    stories: list[UserStory],
) -> list[tuple[str, str, str]]:
    """
    Detect conflicts between local content and previously synced state.

    Compares current content hash with stored hash to detect local modifications
    since the last sync.

    Args:
        file_path: Path to the markdown file.
        stories: Current stories to check.

    Returns:
        List of (story_id, stored_hash, current_hash) tuples for conflicts.
    """
    conflicts: list[tuple[str, str, str]] = []

    if not file_path.exists():
        return conflicts

    content = file_path.read_text(encoding="utf-8")

    for story in stories:
        story_id = str(story.id)

        # Find stored hash in content
        hash_pattern = r">\s*\*\*Content Hash:\*\*\s*`([a-f0-9]+)`"
        story_section = _extract_story_section(content, story_id)

        if not story_section:
            continue

        hash_match = re.search(hash_pattern, story_section)
        if not hash_match:
            continue

        stored_hash = hash_match.group(1)
        current_hash = compute_story_content_hash(story)

        if stored_hash != current_hash:
            conflicts.append((story_id, stored_hash, current_hash))

    return conflicts


def _extract_story_section(content: str, story_id: str) -> str | None:
    """Extract the content section for a specific story."""
    pattern = rf"(#{{1,3}}\s+[^\n]*?{re.escape(story_id)}:\s*[^\n]+\n[\s\S]*?)(?=#{{1,3}}\s+[^\n]*[A-Z]+-\d+:|\Z)"
    match = re.search(pattern, content)
    return match.group(1) if match else None
