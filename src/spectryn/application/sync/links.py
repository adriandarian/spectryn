"""
Link Sync Orchestrator - Sync issue links across projects.

Handles cross-project linking between Jira issues based on
link definitions in markdown files.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from spectryn.core.domain.entities import UserStory
from spectryn.core.ports.issue_tracker import IssueTrackerPort, LinkType


if TYPE_CHECKING:
    pass


@dataclass
class LinkChange:
    """A single link change."""

    source_key: str
    target_key: str
    link_type: str
    action: str  # "create" or "delete"
    success: bool = True
    error: str | None = None


@dataclass
class LinkSyncResult:
    """Result of link synchronization."""

    success: bool = True
    dry_run: bool = False

    # Counts
    stories_processed: int = 0
    links_created: int = 0
    links_deleted: int = 0
    links_unchanged: int = 0
    links_failed: int = 0

    # Details
    changes: list[LinkChange] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # Timing
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None

    @property
    def duration_seconds(self) -> float:
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return 0.0

    def add_change(self, change: LinkChange) -> None:
        """Add a link change."""
        self.changes.append(change)
        if change.action == "create":
            if change.success:
                self.links_created += 1
            else:
                self.links_failed += 1
                self.success = False
        elif change.action == "delete":
            if change.success:
                self.links_deleted += 1
            else:
                self.links_failed += 1

    def add_error(self, error: str) -> None:
        self.errors.append(error)
        self.success = False

    def summary(self) -> str:
        """Generate summary."""
        lines = [
            f"Link Sync {'(dry run)' if self.dry_run else ''}",
            f"{'=' * 40}",
            f"Stories processed: {self.stories_processed}",
            f"Links created: {self.links_created}",
            f"Links deleted: {self.links_deleted}",
            f"Links unchanged: {self.links_unchanged}",
        ]

        if self.links_failed:
            lines.append(f"Links failed: {self.links_failed}")

        if self.errors:
            lines.append(f"\nErrors ({len(self.errors)}):")
            for error in self.errors[:5]:
                lines.append(f"  - {error}")

        return "\n".join(lines)


class LinkSyncOrchestrator:
    """
    Orchestrates synchronization of issue links.

    Reads link definitions from markdown and syncs them to the
    issue tracker, supporting cross-project links.
    """

    def __init__(
        self,
        tracker: IssueTrackerPort,
        dry_run: bool = True,
    ):
        """
        Initialize the link sync orchestrator.

        Args:
            tracker: Issue tracker adapter
            dry_run: If True, don't make changes
        """
        self.tracker = tracker
        self.dry_run = dry_run
        self.logger = logging.getLogger("LinkSyncOrchestrator")

    def sync_story_links(
        self,
        story: UserStory,
        progress_callback: Callable[[str], None] | None = None,
    ) -> LinkSyncResult:
        """
        Sync links for a single story.

        Args:
            story: Story with links to sync
            progress_callback: Optional progress callback

        Returns:
            LinkSyncResult
        """
        result = LinkSyncResult(dry_run=self.dry_run)

        if not story.external_key:
            result.add_error(f"Story {story.id} has no external key")
            return result

        issue_key = str(story.external_key)

        if progress_callback:
            progress_callback(f"Syncing links for {issue_key}")

        # Get desired links from story
        desired_links = story.links

        if not desired_links:
            self.logger.debug(f"No links defined for {issue_key}")
            result.stories_processed = 1
            return result

        # Get existing links
        existing = self.tracker.get_issue_links(issue_key)
        existing_set = {(link.link_type.value, link.target_key) for link in existing}

        # Convert desired to set
        desired_set = set(desired_links)

        result.stories_processed = 1

        # Links to create
        to_create = desired_set - existing_set
        for link_type_str, target_key in to_create:
            change = self._create_link(issue_key, target_key, link_type_str)
            result.add_change(change)

        # Links to delete (if we're doing bidirectional sync)
        # For now, we only add links, not delete them
        # to_delete = existing_set - desired_set

        # Unchanged
        result.links_unchanged = len(existing_set & desired_set)

        result.completed_at = datetime.now()
        return result

    def sync_all_links(
        self,
        stories: list[UserStory],
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> LinkSyncResult:
        """
        Sync links for all stories.

        Args:
            stories: Stories with links to sync
            progress_callback: Callback (message, current, total)

        Returns:
            LinkSyncResult
        """
        result = LinkSyncResult(dry_run=self.dry_run)

        # Filter to stories with links and external keys
        stories_with_links = [s for s in stories if s.links and s.external_key]

        total = len(stories_with_links)
        self.logger.info(f"Syncing links for {total} stories")

        for i, story in enumerate(stories_with_links):
            if progress_callback:
                progress_callback(f"Processing {story.external_key}", i + 1, total)

            story_result = self.sync_story_links(story)

            # Aggregate results
            result.stories_processed += story_result.stories_processed
            result.links_created += story_result.links_created
            result.links_deleted += story_result.links_deleted
            result.links_unchanged += story_result.links_unchanged
            result.links_failed += story_result.links_failed
            result.changes.extend(story_result.changes)
            result.errors.extend(story_result.errors)

            if not story_result.success:
                result.success = False

        result.completed_at = datetime.now()
        return result

    def _create_link(
        self,
        source_key: str,
        target_key: str,
        link_type_str: str,
    ) -> LinkChange:
        """Create a single link."""
        link_type = LinkType.from_string(link_type_str)

        change = LinkChange(
            source_key=source_key,
            target_key=target_key,
            link_type=link_type_str,
            action="create",
        )

        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would link {source_key} --{link_type_str}--> {target_key}")
            return change

        try:
            success = self.tracker.create_link(source_key, target_key, link_type)
            change.success = success
            if not success:
                change.error = "Link creation failed"
        except Exception as e:
            change.success = False
            change.error = str(e)
            self.logger.error(f"Failed to create link: {e}")

        return change

    def analyze_links(
        self,
        stories: list[UserStory],
    ) -> dict[str, Any]:
        """
        Analyze links without syncing.

        Args:
            stories: Stories to analyze

        Returns:
            Analysis dict
        """
        total_links = 0
        cross_project_links = 0
        link_types: dict[str, int] = {}
        target_projects: dict[str, int] = {}

        for story in stories:
            if not story.external_key:
                continue

            source_project = str(story.external_key).split("-")[0]

            for link_type, target_key in story.links:
                total_links += 1

                # Count by link type
                link_types[link_type] = link_types.get(link_type, 0) + 1

                # Check if cross-project
                if "-" in target_key:
                    target_project = target_key.split("-")[0]
                    target_projects[target_project] = target_projects.get(target_project, 0) + 1

                    if target_project != source_project:
                        cross_project_links += 1

        return {
            "total_links": total_links,
            "cross_project_links": cross_project_links,
            "same_project_links": total_links - cross_project_links,
            "link_types": link_types,
            "target_projects": target_projects,
            "stories_with_links": sum(1 for s in stories if s.links),
        }
