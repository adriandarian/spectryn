"""
Multi-Tracker Sync - Sync the same markdown to multiple trackers simultaneously.

This enables keeping multiple issue trackers in sync from a single source of truth
(the markdown file). Use cases include:
- Mirror stories to Jira for enterprise and GitHub for OSS
- Sync to Linear for planning and Azure DevOps for deployment tracking
- Keep multiple teams' trackers in sync

Components:
- TrackerTarget: Configuration for a single tracker target
- MultiTrackerSyncResult: Combined results from all trackers
- MultiTrackerSyncOrchestrator: Orchestrates sync to multiple trackers
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from spectryn.core.domain.entities import UserStory
from spectryn.core.domain.events import EventBus
from spectryn.core.ports.config_provider import SyncConfig
from spectryn.core.ports.issue_tracker import IssueTrackerPort


if TYPE_CHECKING:
    from spectryn.core.ports.document_formatter import DocumentFormatterPort
    from spectryn.core.ports.document_parser import DocumentParserPort


logger = logging.getLogger(__name__)


class TrackerType(Enum):
    """Supported tracker types."""

    JIRA = "jira"
    GITHUB = "github"
    GITLAB = "gitlab"
    LINEAR = "linear"
    AZURE_DEVOPS = "azure_devops"
    ASANA = "asana"
    TRELLO = "trello"
    PIVOTAL = "pivotal"
    YOUTRACK = "youtrack"
    PLANE = "plane"
    CLICKUP = "clickup"
    MONDAY = "monday"
    SHORTCUT = "shortcut"
    NOTION = "notion"
    CONFLUENCE = "confluence"
    BITBUCKET = "bitbucket"


class SyncStrategy(Enum):
    """Strategy for syncing to multiple trackers."""

    PARALLEL = "parallel"  # Sync to all trackers in parallel
    SEQUENTIAL = "sequential"  # Sync to trackers one at a time
    PRIMARY_FIRST = "primary_first"  # Sync to primary, then mirror to others


@dataclass
class TrackerTarget:
    """
    Configuration for a single tracker target in multi-tracker sync.

    Attributes:
        tracker: The issue tracker adapter
        epic_key: Epic key in this tracker
        name: Human-readable name for this target
        is_primary: If True, this is the primary tracker (used for ID generation)
        enabled: If False, skip this tracker
        formatter: Optional custom formatter for this tracker
    """

    tracker: IssueTrackerPort
    epic_key: str
    name: str = ""
    is_primary: bool = False
    enabled: bool = True
    formatter: DocumentFormatterPort | None = None

    def __post_init__(self) -> None:
        if not self.name:
            self.name = self.tracker.name


@dataclass
class TrackerSyncStatus:
    """
    Status of sync to a single tracker.

    Tracks success/failure and details for one tracker in a multi-tracker sync.
    """

    tracker_name: str
    epic_key: str
    success: bool = True
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: str = ""

    # Counts
    stories_synced: int = 0
    stories_created: int = 0
    stories_updated: int = 0
    stories_skipped: int = 0
    subtasks_synced: int = 0

    # Errors and warnings
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # Key mappings (story_id -> tracker_issue_key)
    key_mappings: dict[str, str] = field(default_factory=dict)

    def add_error(self, error: str) -> None:
        """Add an error."""
        self.errors.append(error)
        self.success = False

    def add_warning(self, warning: str) -> None:
        """Add a warning."""
        self.warnings.append(warning)

    def complete(self) -> None:
        """Mark sync as complete."""
        self.completed_at = datetime.now().isoformat()

    @property
    def summary(self) -> str:
        """Get human-readable summary."""
        status = "✓" if self.success else "✗"
        return (
            f"{status} {self.tracker_name} ({self.epic_key}): "
            f"{self.stories_synced} synced, {self.stories_skipped} skipped"
        )


@dataclass
class MultiTrackerSyncResult:
    """
    Combined result of syncing to multiple trackers.

    Aggregates results from all target trackers.
    """

    dry_run: bool = True
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: str = ""

    # Per-tracker results
    tracker_statuses: list[TrackerSyncStatus] = field(default_factory=list)

    # Aggregated counts
    total_trackers: int = 0
    successful_trackers: int = 0
    failed_trackers: int = 0

    # Cross-tracker mappings (story_id -> {tracker_name -> issue_key})
    cross_tracker_mappings: dict[str, dict[str, str]] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        """Check if all trackers synced successfully."""
        return self.failed_trackers == 0

    @property
    def partial_success(self) -> bool:
        """Check if at least one tracker synced successfully."""
        return self.successful_trackers > 0

    def add_tracker_status(self, status: TrackerSyncStatus) -> None:
        """Add a tracker's sync status."""
        self.tracker_statuses.append(status)
        self.total_trackers += 1

        if status.success:
            self.successful_trackers += 1
        else:
            self.failed_trackers += 1

        # Update cross-tracker mappings
        for story_id, issue_key in status.key_mappings.items():
            if story_id not in self.cross_tracker_mappings:
                self.cross_tracker_mappings[story_id] = {}
            self.cross_tracker_mappings[story_id][status.tracker_name] = issue_key

    def complete(self) -> None:
        """Mark the sync as complete."""
        self.completed_at = datetime.now().isoformat()

    def summary(self) -> str:
        """Get human-readable summary."""
        lines = [
            "Multi-Tracker Sync Results",
            "=" * 50,
            f"Mode: {'Dry Run' if self.dry_run else 'Execute'}",
            f"Trackers: {self.successful_trackers}/{self.total_trackers} successful",
            "",
        ]

        for status in self.tracker_statuses:
            lines.append(status.summary)
            if status.errors:
                for error in status.errors[:3]:
                    lines.append(f"    Error: {error}")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "dry_run": self.dry_run,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "total_trackers": self.total_trackers,
            "successful_trackers": self.successful_trackers,
            "failed_trackers": self.failed_trackers,
            "cross_tracker_mappings": self.cross_tracker_mappings,
            "tracker_statuses": [
                {
                    "tracker_name": s.tracker_name,
                    "epic_key": s.epic_key,
                    "success": s.success,
                    "stories_synced": s.stories_synced,
                    "errors": s.errors,
                }
                for s in self.tracker_statuses
            ],
        }


class MultiTrackerSyncOrchestrator:
    """
    Orchestrates synchronization to multiple issue trackers.

    Syncs the same markdown source to multiple trackers simultaneously,
    keeping all trackers in sync with the markdown source of truth.

    Features:
    - Sync to multiple trackers in parallel or sequentially
    - Primary tracker for ID generation
    - Cross-tracker key mappings
    - Independent error handling per tracker

    Example:
        >>> from spectryn.adapters.jira import JiraAdapter
        >>> from spectryn.adapters.github import GitHubAdapter
        >>>
        >>> orchestrator = MultiTrackerSyncOrchestrator(
        ...     parser=markdown_parser,
        ...     config=sync_config,
        ... )
        >>>
        >>> orchestrator.add_target(TrackerTarget(
        ...     tracker=jira_adapter,
        ...     epic_key="PROJ-123",
        ...     name="Jira",
        ...     is_primary=True,
        ... ))
        >>> orchestrator.add_target(TrackerTarget(
        ...     tracker=github_adapter,
        ...     epic_key="1",  # Milestone number
        ...     name="GitHub",
        ... ))
        >>>
        >>> result = orchestrator.sync("path/to/EPIC.md")
    """

    def __init__(
        self,
        parser: DocumentParserPort,
        config: SyncConfig,
        formatter: DocumentFormatterPort | None = None,
        event_bus: EventBus | None = None,
        strategy: SyncStrategy = SyncStrategy.SEQUENTIAL,
    ):
        """
        Initialize the multi-tracker sync orchestrator.

        Args:
            parser: Document parser for markdown.
            config: Sync configuration.
            formatter: Default document formatter.
            event_bus: Optional event bus.
            strategy: Sync strategy (parallel, sequential, primary_first).
        """
        self.parser = parser
        self.config = config
        self.formatter = formatter
        self.event_bus = event_bus or EventBus()
        self.strategy = strategy
        self.logger = logging.getLogger("MultiTrackerSyncOrchestrator")

        self._targets: list[TrackerTarget] = []
        self._stories: list[UserStory] = []

    def add_target(self, target: TrackerTarget) -> None:
        """
        Add a tracker target.

        Args:
            target: TrackerTarget configuration.
        """
        self._targets.append(target)
        self.logger.info(f"Added target: {target.name} ({target.epic_key})")

    def remove_target(self, name: str) -> bool:
        """
        Remove a tracker target by name.

        Args:
            name: Target name to remove.

        Returns:
            True if removed, False if not found.
        """
        for i, target in enumerate(self._targets):
            if target.name == name:
                self._targets.pop(i)
                return True
        return False

    @property
    def targets(self) -> list[TrackerTarget]:
        """Get all configured targets."""
        return self._targets

    @property
    def primary_target(self) -> TrackerTarget | None:
        """Get the primary tracker target."""
        for target in self._targets:
            if target.is_primary:
                return target
        return self._targets[0] if self._targets else None

    def sync(
        self,
        markdown_path: str,
        progress_callback: Callable[[str, str, int, int], None] | None = None,
    ) -> MultiTrackerSyncResult:
        """
        Sync markdown to all configured trackers.

        Args:
            markdown_path: Path to markdown file.
            progress_callback: Optional callback(tracker_name, phase, current, total).

        Returns:
            MultiTrackerSyncResult with results from all trackers.
        """
        result = MultiTrackerSyncResult(dry_run=self.config.dry_run)

        if not self._targets:
            self.logger.warning("No tracker targets configured")
            return result

        # Parse markdown once
        try:
            from pathlib import Path

            content = Path(markdown_path).read_text(encoding="utf-8")
            self._stories = self.parser.parse_stories(content)
            self.logger.info(f"Parsed {len(self._stories)} stories from {markdown_path}")
        except Exception as e:
            self.logger.error(f"Failed to parse markdown: {e}")
            # Add error to all trackers
            for target in self._targets:
                status = TrackerSyncStatus(
                    tracker_name=target.name,
                    epic_key=target.epic_key,
                    success=False,
                )
                status.add_error(f"Failed to parse markdown: {e}")
                status.complete()
                result.add_tracker_status(status)
            result.complete()
            return result

        # Sync to each tracker
        enabled_targets = [t for t in self._targets if t.enabled]

        if self.strategy == SyncStrategy.PRIMARY_FIRST:
            # Sync primary first, then others
            primary = self.primary_target
            if primary and primary.enabled:
                status = self._sync_to_tracker(primary, progress_callback)
                result.add_tracker_status(status)

            for target in enabled_targets:
                if target != primary:
                    status = self._sync_to_tracker(target, progress_callback)
                    result.add_tracker_status(status)
        else:
            # Sequential or parallel (sequential for now)
            for target in enabled_targets:
                status = self._sync_to_tracker(target, progress_callback)
                result.add_tracker_status(status)

        result.complete()
        return result

    def _sync_to_tracker(
        self,
        target: TrackerTarget,
        progress_callback: Callable[[str, str, int, int], None] | None = None,
    ) -> TrackerSyncStatus:
        """
        Sync stories to a single tracker.

        Args:
            target: Tracker target configuration.
            progress_callback: Optional progress callback.

        Returns:
            TrackerSyncStatus with sync results.
        """
        status = TrackerSyncStatus(
            tracker_name=target.name,
            epic_key=target.epic_key,
        )

        self.logger.info(f"Syncing to {target.name} (epic: {target.epic_key})")

        try:
            # Test connection
            if not target.tracker.test_connection():
                status.add_error(f"Failed to connect to {target.name}")
                status.complete()
                return status

            # Report progress
            if progress_callback:
                progress_callback(target.name, "Connecting", 0, len(self._stories))

            # Fetch existing issues
            try:
                existing_issues = target.tracker.get_epic_children(target.epic_key)
                existing_by_summary = {issue.summary.lower(): issue for issue in existing_issues}
            except Exception as e:
                self.logger.warning(f"Failed to fetch existing issues: {e}")
                existing_by_summary = {}

            # Sync each story
            for i, story in enumerate(self._stories):
                if progress_callback:
                    progress_callback(target.name, f"Syncing {story.id}", i + 1, len(self._stories))

                try:
                    result = self._sync_story_to_tracker(story, target, existing_by_summary, status)
                    if result:
                        status.stories_synced += 1
                except Exception as e:
                    status.add_warning(f"Failed to sync {story.id}: {e}")

        except Exception as e:
            status.add_error(str(e))
            self.logger.error(f"Sync to {target.name} failed: {e}")

        status.complete()
        return status

    def _sync_story_to_tracker(
        self,
        story: UserStory,
        target: TrackerTarget,
        existing_issues: dict[str, Any],
        status: TrackerSyncStatus,
    ) -> bool:
        """
        Sync a single story to a tracker.

        Args:
            story: Story to sync.
            target: Tracker target.
            existing_issues: Existing issues keyed by lowercase summary.
            status: Status to update.

        Returns:
            True if synced successfully.
        """
        story_key = story.title.lower()

        # Check if story already exists
        if story_key in existing_issues:
            existing = existing_issues[story_key]
            status.key_mappings[str(story.id)] = existing.key

            if not self.config.dry_run:
                # Update existing issue
                self._update_story_in_tracker(story, existing.key, target)
                status.stories_updated += 1
            else:
                status.stories_skipped += 1

            return True

        # Create new story
        if not self.config.dry_run:
            issue_key = self._create_story_in_tracker(story, target)
            if issue_key:
                status.key_mappings[str(story.id)] = issue_key
                status.stories_created += 1
                return True
            return False
        status.stories_skipped += 1
        return True

    def _update_story_in_tracker(
        self,
        story: UserStory,
        issue_key: str,
        target: TrackerTarget,
    ) -> None:
        """Update an existing story in a tracker."""
        # Get formatter
        formatter = target.formatter or self.formatter
        if not formatter:
            self.logger.warning(f"No formatter for {target.name}, skipping update")
            return

        # Format and update description
        if story.description and self.config.sync_descriptions:
            description = formatter.format_story_description(story)
            target.tracker.update_description(issue_key, description)

    def _create_story_in_tracker(
        self,
        story: UserStory,
        target: TrackerTarget,
    ) -> str | None:
        """
        Create a new story in a tracker.

        Returns:
            Issue key if created, None otherwise.
        """
        # Get formatter
        formatter = target.formatter or self.formatter
        if not formatter:
            self.logger.warning(f"No formatter for {target.name}, skipping create")
            return None

        # Format description
        description = None
        if story.description:
            description = formatter.format_story_description(story)

        # Create issue
        try:
            result = target.tracker.create_issue(
                project_key=target.epic_key.split("-")[0] if "-" in target.epic_key else "",
                summary=f"{story.id}: {story.title}",
                description=description,
                issue_type="Story",
                parent_key=target.epic_key,
            )
            return str(result) if result else None
        except Exception as e:
            self.logger.error(f"Failed to create story {story.id} in {target.name}: {e}")
            return None

    def preview(self, markdown_path: str) -> MultiTrackerSyncResult:
        """
        Preview what would be synced without making changes.

        Args:
            markdown_path: Path to markdown file.

        Returns:
            MultiTrackerSyncResult showing what would happen.
        """
        # Force dry run for preview
        original_dry_run = self.config.dry_run
        self.config.dry_run = True

        try:
            return self.sync(markdown_path)
        finally:
            self.config.dry_run = original_dry_run


def create_multi_tracker_orchestrator(
    parser: DocumentParserPort,
    config: SyncConfig,
    targets: list[dict[str, Any]],
) -> MultiTrackerSyncOrchestrator:
    """
    Factory function to create a multi-tracker orchestrator from config.

    Args:
        parser: Document parser.
        config: Sync configuration.
        targets: List of target configurations.

    Returns:
        Configured MultiTrackerSyncOrchestrator.

    Example targets config:
        [
            {
                "type": "jira",
                "epic_key": "PROJ-123",
                "name": "Enterprise Jira",
                "is_primary": True,
                "url": "https://company.atlassian.net",
                "email": "user@company.com",
                "api_token": "xxx",
            },
            {
                "type": "github",
                "epic_key": "1",
                "name": "GitHub Mirror",
                "owner": "company",
                "repo": "project",
                "token": "xxx",
            },
        ]
    """
    orchestrator = MultiTrackerSyncOrchestrator(parser=parser, config=config)

    for target_config in targets:
        tracker_type = target_config.get("type", "").lower()
        epic_key = target_config.get("epic_key", "")
        name = target_config.get("name", tracker_type)
        is_primary = target_config.get("is_primary", False)

        # Create tracker based on type
        tracker = _create_tracker_from_config(tracker_type, target_config, config.dry_run)
        if tracker:
            orchestrator.add_target(
                TrackerTarget(
                    tracker=tracker,
                    epic_key=epic_key,
                    name=name,
                    is_primary=is_primary,
                )
            )
        else:
            logger.warning(f"Unknown tracker type: {tracker_type}")

    return orchestrator


def _create_tracker_from_config(
    tracker_type: str,
    config: dict[str, Any],
    dry_run: bool,
) -> IssueTrackerPort | None:
    """
    Create a tracker adapter from configuration.

    Args:
        tracker_type: Type of tracker (jira, github, etc.)
        config: Tracker configuration.
        dry_run: Whether to run in dry-run mode.

    Returns:
        Configured tracker adapter, or None if unknown type.
    """
    try:
        if tracker_type == "jira":
            from spectryn.adapters.jira import JiraAdapter
            from spectryn.core.ports.config_provider import TrackerConfig

            tracker_config = TrackerConfig(
                url=config.get("url", ""),
                email=config.get("email", ""),
                api_token=config.get("api_token", ""),
                project_key=config.get("project_key", ""),
            )
            return JiraAdapter(config=tracker_config, dry_run=dry_run)

        if tracker_type == "github":
            from spectryn.adapters.github import GitHubAdapter

            return GitHubAdapter(
                token=config.get("token", ""),
                owner=config.get("owner", ""),
                repo=config.get("repo", ""),
                dry_run=dry_run,
            )

        if tracker_type == "gitlab":
            from spectryn.adapters.gitlab import GitLabAdapter

            return GitLabAdapter(
                url=config.get("url", "https://gitlab.com"),
                token=config.get("token", ""),
                project_id=config.get("project_id", ""),
                dry_run=dry_run,
            )

        if tracker_type == "linear":
            from spectryn.adapters.linear import LinearAdapter

            return LinearAdapter(
                api_key=config.get("api_key", ""),
                team_id=config.get("team_id", ""),
                dry_run=dry_run,
            )

        if tracker_type == "azure_devops":
            from spectryn.adapters.azure_devops import AzureDevOpsAdapter

            return AzureDevOpsAdapter(
                organization=config.get("organization", ""),
                project=config.get("project", ""),
                token=config.get("token", ""),
                dry_run=dry_run,
            )

    except ImportError as e:
        logger.warning(f"Failed to import adapter for {tracker_type}: {e}")
    except Exception as e:
        logger.error(f"Failed to create {tracker_type} adapter: {e}")

    return None
