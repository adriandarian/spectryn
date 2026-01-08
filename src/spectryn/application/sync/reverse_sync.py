"""
Reverse Sync Orchestrator - Pull changes from Jira back to markdown.

This orchestrates the bidirectional sync in the reverse direction:
Jira -> Markdown (as opposed to the main sync which is Markdown -> Jira).
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from spectryn.adapters.formatters.markdown_writer import MarkdownUpdater, MarkdownWriter
from spectryn.core.domain.entities import Epic, Subtask, UserStory
from spectryn.core.domain.enums import Status
from spectryn.core.domain.events import EventBus
from spectryn.core.domain.value_objects import Description, IssueKey, StoryId
from spectryn.core.ports.config_provider import SyncConfig
from spectryn.core.ports.issue_tracker import IssueData, IssueTrackerPort


@dataclass
class PullResult:
    """
    Result of a pull (reverse sync) operation.

    Contains counts and details of what was pulled from Jira to markdown.
    """

    success: bool = True
    dry_run: bool = True

    # Counts
    stories_pulled: int = 0
    stories_created: int = 0
    stories_updated: int = 0
    subtasks_pulled: int = 0

    # Details
    pulled_stories: list[tuple[str, str]] = field(default_factory=list)  # (jira_key, story_id)
    new_stories: list[str] = field(default_factory=list)  # jira keys
    updated_stories: list[str] = field(default_factory=list)  # jira keys

    # Output
    output_path: str | None = None

    # Errors and warnings
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, error: str) -> None:
        """Add an error message."""
        self.errors.append(error)
        self.success = False

    def add_warning(self, warning: str) -> None:
        """Add a warning message."""
        self.warnings.append(warning)

    @property
    def has_changes(self) -> bool:
        """Check if any changes were made/detected."""
        return self.stories_created > 0 or self.stories_updated > 0

    @property
    def summary(self) -> str:
        """Get a human-readable summary."""
        lines = []

        mode = "Preview" if self.dry_run else "Result"
        lines.append(f"Pull {mode}")
        lines.append("-" * 40)

        lines.append(f"Stories pulled: {self.stories_pulled}")
        lines.append(f"  - New: {self.stories_created}")
        lines.append(f"  - Updated: {self.stories_updated}")
        lines.append(f"Subtasks: {self.subtasks_pulled}")

        if self.output_path:
            lines.append(f"Output: {self.output_path}")

        if self.errors:
            lines.append("")
            lines.append("Errors:")
            for error in self.errors[:5]:
                lines.append(f"  - {error}")

        return "\n".join(lines)


@dataclass
class ChangeDetail:
    """Details of a single change detected during pull."""

    story_id: str
    jira_key: str
    field: str
    old_value: Any
    new_value: Any

    def __str__(self) -> str:
        return f"{self.story_id} ({self.jira_key}): {self.field} changed"


@dataclass
class PullChanges:
    """
    Collection of changes detected between Jira and markdown.

    Used for preview mode and conflict detection.
    """

    new_stories: list[UserStory] = field(default_factory=list)
    updated_stories: list[tuple[UserStory, list[ChangeDetail]]] = field(default_factory=list)
    deleted_stories: list[str] = field(default_factory=list)  # story IDs

    @property
    def has_changes(self) -> bool:
        """Check if there are any changes."""
        return bool(self.new_stories or self.updated_stories or self.deleted_stories)

    @property
    def total_changes(self) -> int:
        """Count total number of changes."""
        return len(self.new_stories) + len(self.updated_stories) + len(self.deleted_stories)


class ReverseSyncOrchestrator:
    """
    Orchestrates pulling changes from Jira to markdown.

    Phases:
    1. Fetch current state from Jira (epic + children)
    2. Parse existing markdown file (if exists)
    3. Match Jira issues to markdown stories
    4. Detect changes
    5. Update or create markdown file
    """

    def __init__(
        self,
        tracker: IssueTrackerPort,
        config: SyncConfig,
        event_bus: EventBus | None = None,
        writer: MarkdownWriter | None = None,
    ):
        """
        Initialize the reverse sync orchestrator.

        Args:
            tracker: Issue tracker port (Jira adapter).
            config: Sync configuration.
            event_bus: Optional event bus for publishing events.
            writer: Optional custom markdown writer.
        """
        self.tracker = tracker
        self.config = config
        self.event_bus = event_bus or EventBus()
        self.writer = writer or MarkdownWriter()
        self.updater = MarkdownUpdater()
        self.logger = logging.getLogger("ReverseSyncOrchestrator")

        # State
        self._jira_issues: list[IssueData] = []
        self._md_stories: list[UserStory] = []
        self._matches: dict[str, str] = {}  # jira_key -> story_id

    def pull(
        self,
        epic_key: str,
        output_path: str,
        existing_markdown: str | None = None,
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> PullResult:
        """
        Pull changes from Jira to markdown.

        Args:
            epic_key: Jira epic key to pull from.
            output_path: Path to write/update markdown file.
            existing_markdown: Optional path to existing markdown file for updating.
            progress_callback: Optional callback for progress updates.

        Returns:
            PullResult with details of what was pulled.
        """
        result = PullResult(dry_run=self.config.dry_run)
        result.output_path = output_path

        total_phases = 5

        try:
            # Phase 1: Fetch from Jira
            self._report_progress(progress_callback, "Fetching from Jira", 1, total_phases)
            epic_data, stories = self._fetch_from_jira(epic_key, result)

            if not stories:
                result.add_warning(f"No stories found under epic {epic_key}")
                return result

            result.stories_pulled = len(stories)

            # Phase 2: Parse existing markdown (if any)
            self._report_progress(progress_callback, "Parsing existing markdown", 2, total_phases)
            existing_content = None
            if existing_markdown and Path(existing_markdown).exists():
                existing_content = Path(existing_markdown).read_text(encoding="utf-8")
                self._parse_existing_markdown(existing_content)

            # Phase 3: Match Jira issues to markdown stories
            self._report_progress(progress_callback, "Matching stories", 3, total_phases)
            self._match_issues_to_stories(stories)

            # Phase 4: Detect changes
            self._report_progress(progress_callback, "Detecting changes", 4, total_phases)
            changes = self._detect_changes(stories, epic_data)

            result.stories_created = len(changes.new_stories)
            result.stories_updated = len(changes.updated_stories)

            for story in changes.new_stories:
                if story.external_key:
                    result.new_stories.append(str(story.external_key))

            for story, _ in changes.updated_stories:
                if story.external_key:
                    result.updated_stories.append(str(story.external_key))

            # Phase 5: Write/update markdown
            self._report_progress(progress_callback, "Writing markdown", 5, total_phases)

            if not self.config.dry_run:
                self._write_markdown(
                    epic_data,
                    stories,
                    output_path,
                    existing_content,
                    result,
                )

        except Exception as e:
            self.logger.error(f"Pull failed: {e}")
            result.add_error(str(e))

        return result

    def preview(
        self,
        epic_key: str,
        existing_markdown: str | None = None,
    ) -> PullChanges:
        """
        Preview what would be pulled from Jira without making changes.

        Args:
            epic_key: Jira epic key.
            existing_markdown: Optional path to existing markdown.

        Returns:
            PullChanges describing what would change.
        """
        result = PullResult(dry_run=True)

        # Fetch from Jira
        epic_data, stories = self._fetch_from_jira(epic_key, result)

        # Parse existing markdown
        if existing_markdown and Path(existing_markdown).exists():
            content = Path(existing_markdown).read_text(encoding="utf-8")
            self._parse_existing_markdown(content)

        # Match and detect changes
        self._match_issues_to_stories(stories)
        return self._detect_changes(stories, epic_data)

    def _fetch_from_jira(
        self,
        epic_key: str,
        result: PullResult,
    ) -> tuple[IssueData, list[UserStory]]:
        """Fetch epic and child issues from Jira."""
        # Get epic details
        epic_data = self.tracker.get_issue(epic_key)
        self.logger.info(f"Fetched epic: {epic_key} - {epic_data.summary}")

        # Get child issues (stories)
        jira_issues = self.tracker.get_epic_children(epic_key)
        self.logger.info(f"Fetched {len(jira_issues)} child issues")

        # Convert to domain entities
        stories = []
        for i, issue in enumerate(jira_issues):
            story = self._issue_to_story(issue, i + 1)
            stories.append(story)
            result.subtasks_pulled += len(story.subtasks)
            result.pulled_stories.append((issue.key, str(story.id)))

        self._jira_issues = jira_issues
        return epic_data, stories

    def _issue_to_story(self, issue: IssueData, index: int) -> UserStory:
        """Convert Jira IssueData to UserStory entity."""
        # Generate story ID from index or extract from summary
        story_id = self._extract_story_id(issue.summary) or f"US-{index:03d}"

        # Parse description if present
        description = None
        if issue.description:
            description = self._parse_jira_description(issue.description)

        # Convert subtasks
        subtasks = []
        for j, st in enumerate(issue.subtasks):
            subtasks.append(
                Subtask(
                    number=j + 1,
                    name=st.summary,
                    description="",
                    story_points=1,
                    status=Status.from_string(st.status),
                    external_key=IssueKey(st.key),
                )
            )

        return UserStory(
            id=StoryId(story_id),
            title=self._clean_title(issue.summary, story_id),
            description=description,
            status=Status.from_string(issue.status),
            story_points=int(issue.story_points) if issue.story_points else 0,
            assignee=issue.assignee,
            subtasks=subtasks,
            external_key=IssueKey(issue.key),
        )

    def _extract_story_id(self, summary: str) -> str | None:
        """Extract story ID from summary if present (e.g., 'STORY-001: Title')."""
        import re

        match = re.match(r"^(US-\d+)[:\s]", summary)
        return match.group(1) if match else None

    def _clean_title(self, summary: str, story_id: str) -> str:
        """Remove story ID prefix from summary to get clean title."""
        import re

        # Remove "PREFIX-XXX: " or "PREFIX-XXX - " prefix (e.g., STORY-001: Title)
        cleaned = re.sub(rf"^{re.escape(story_id)}[:\s-]+\s*", "", summary)
        return cleaned.strip() or summary

    def _parse_jira_description(self, description: Any) -> Description | None:
        """Parse Jira description (ADF or text) to Description value object."""
        text = self._adf_to_text(description) if isinstance(description, dict) else str(description)

        if not text:
            return None

        # Try to parse As a/I want/So that format
        import re

        pattern = (
            r"[Aa]s\s+a\s+(.+?)[,.]?\s+[Ii]\s+want\s+(.+?)[,.]?\s+[Ss]o\s+that\s+(.+?)(?:\.|$)"
        )
        match = re.search(pattern, text, re.DOTALL)

        if match:
            return Description(
                role=match.group(1).strip(),
                want=match.group(2).strip(),
                benefit=match.group(3).strip(),
            )

        # Fallback: use entire text as "want"
        return Description(
            role="user",
            want=text[:500] if len(text) > 500 else text,
            benefit="the feature works as expected",
        )

    def _adf_to_text(self, adf: dict) -> str:
        """Convert Atlassian Document Format to plain text."""
        if not isinstance(adf, dict):
            return str(adf) if adf else ""

        content = adf.get("content", [])
        return self._extract_adf_text(content)

    def _extract_adf_text(self, nodes: list) -> str:
        """Recursively extract text from ADF nodes."""
        texts = []

        for node in nodes:
            if isinstance(node, dict):
                node_type = node.get("type", "")

                if node_type == "text":
                    texts.append(node.get("text", ""))
                elif node_type == "hardBreak":
                    texts.append("\n")
                elif "content" in node:
                    texts.append(self._extract_adf_text(node["content"]))

                # Add newline after paragraphs
                if node_type in ("paragraph", "heading"):
                    texts.append("\n")

        return "".join(texts).strip()

    def _parse_existing_markdown(self, content: str) -> None:
        """Parse existing markdown file to get current stories."""
        from spectryn.adapters.parsers.markdown import MarkdownParser

        parser = MarkdownParser()
        self._md_stories = parser.parse_stories(content)
        self.logger.info(f"Parsed {len(self._md_stories)} stories from existing markdown")

    def _match_issues_to_stories(self, jira_stories: list[UserStory]) -> None:
        """Match Jira issues to existing markdown stories."""
        self._matches = {}

        for jira_story in jira_stories:
            jira_key = str(jira_story.external_key) if jira_story.external_key else ""

            # Try to find matching markdown story
            for md_story in self._md_stories:
                # Match by external key if set
                if md_story.external_key and str(md_story.external_key) == jira_key:
                    self._matches[jira_key] = str(md_story.id)
                    break

                # Match by story ID
                if str(md_story.id) == str(jira_story.id):
                    self._matches[jira_key] = str(md_story.id)
                    break

                # Match by title similarity
                if md_story.matches_title(jira_story.title):
                    self._matches[jira_key] = str(md_story.id)
                    break

        self.logger.info(f"Matched {len(self._matches)} Jira issues to markdown stories")

    def _detect_changes(
        self,
        jira_stories: list[UserStory],
        epic_data: IssueData,
    ) -> PullChanges:
        """Detect what has changed between Jira and markdown."""
        changes = PullChanges()

        {str(s.id) for s in self._md_stories}

        for jira_story in jira_stories:
            jira_key = str(jira_story.external_key) if jira_story.external_key else ""
            matched_id = self._matches.get(jira_key)

            if not matched_id:
                # New story in Jira
                changes.new_stories.append(jira_story)
            else:
                # Check for updates
                md_story = next((s for s in self._md_stories if str(s.id) == matched_id), None)

                if md_story:
                    story_changes = self._compare_stories(md_story, jira_story)
                    if story_changes:
                        changes.updated_stories.append((jira_story, story_changes))

        return changes

    def _compare_stories(
        self,
        md_story: UserStory,
        jira_story: UserStory,
    ) -> list[ChangeDetail]:
        """Compare markdown story with Jira story and return differences."""
        changes = []
        jira_key = str(jira_story.external_key) if jira_story.external_key else ""
        story_id = str(md_story.id)

        # Compare status
        if md_story.status != jira_story.status:
            changes.append(
                ChangeDetail(
                    story_id=story_id,
                    jira_key=jira_key,
                    field="status",
                    old_value=md_story.status.display_name,
                    new_value=jira_story.status.display_name,
                )
            )

        # Compare story points
        if md_story.story_points != jira_story.story_points:
            changes.append(
                ChangeDetail(
                    story_id=story_id,
                    jira_key=jira_key,
                    field="story_points",
                    old_value=md_story.story_points,
                    new_value=jira_story.story_points,
                )
            )

        # Compare subtask count
        if len(md_story.subtasks) != len(jira_story.subtasks):
            changes.append(
                ChangeDetail(
                    story_id=story_id,
                    jira_key=jira_key,
                    field="subtasks",
                    old_value=len(md_story.subtasks),
                    new_value=len(jira_story.subtasks),
                )
            )

        return changes

    def _write_markdown(
        self,
        epic_data: IssueData,
        stories: list[UserStory],
        output_path: str,
        existing_content: str | None,
        result: PullResult,
    ) -> None:
        """Write or update the markdown file."""
        output = Path(output_path)

        # Create epic entity
        epic = Epic(
            key=IssueKey(epic_data.key),
            title=epic_data.summary,
            summary="",
            description=self._adf_to_text(epic_data.description) if epic_data.description else "",
            status=Status.from_string(epic_data.status),
            stories=stories,
        )

        # Generate markdown
        content = self.writer.write_epic(epic)

        # Write file
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")

        self.logger.info(f"Wrote markdown to {output_path}")

    def _report_progress(
        self,
        callback: Callable[[str, int, int], None] | None,
        phase: str,
        current: int,
        total: int,
    ) -> None:
        """Report progress via callback if provided."""
        if callback:
            callback(phase, current, total)
