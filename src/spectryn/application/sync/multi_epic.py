"""
Multi-Epic Sync Orchestrator - Sync multiple epics from one file.

Handles markdown files containing multiple epics, syncing each
to their respective Jira epics.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from spectryn.core.domain.entities import Epic
from spectryn.core.domain.events import EventBus
from spectryn.core.ports.document_formatter import DocumentFormatterPort
from spectryn.core.ports.document_parser import DocumentParserPort
from spectryn.core.ports.issue_tracker import IssueTrackerPort


if TYPE_CHECKING:
    from spectryn.core.domain.config import SyncConfig


@dataclass
class EpicSyncResult:
    """Result of syncing a single epic."""

    epic_key: str
    epic_title: str
    success: bool = True
    dry_run: bool = False

    # Story counts
    stories_total: int = 0
    stories_matched: int = 0
    stories_created: int = 0
    stories_updated: int = 0

    # Subtask counts
    subtasks_created: int = 0
    subtasks_updated: int = 0

    # Issues
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # Duration
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @property
    def duration_seconds(self) -> float:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return 0.0

    def add_error(self, error: str) -> None:
        self.errors.append(error)
        self.success = False

    def add_warning(self, warning: str) -> None:
        self.warnings.append(warning)


@dataclass
class MultiEpicSyncResult:
    """Result of syncing multiple epics."""

    dry_run: bool = False
    success: bool = True

    # Epic results
    epic_results: list[EpicSyncResult] = field(default_factory=list)

    # Aggregate counts
    epics_total: int = 0
    epics_synced: int = 0
    epics_failed: int = 0

    # Totals
    total_stories: int = 0
    total_stories_matched: int = 0
    total_stories_created: int = 0
    total_stories_updated: int = 0
    total_subtasks_created: int = 0

    # Issues
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

    def add_epic_result(self, result: EpicSyncResult) -> None:
        """Add result for a single epic."""
        self.epic_results.append(result)

        if result.success:
            self.epics_synced += 1
        else:
            self.epics_failed += 1
            self.success = False

        self.total_stories += result.stories_total
        self.total_stories_matched += result.stories_matched
        self.total_stories_created += result.stories_created
        self.total_stories_updated += result.stories_updated
        self.total_subtasks_created += result.subtasks_created

        self.errors.extend(result.errors)
        self.warnings.extend(result.warnings)

    def summary(self) -> str:
        """Generate a summary of the sync."""
        lines = [
            f"Multi-Epic Sync {'(dry run)' if self.dry_run else ''}",
            f"{'=' * 40}",
            f"Epics: {self.epics_synced}/{self.epics_total} synced",
        ]

        if self.epics_failed:
            lines.append(f"  Failed: {self.epics_failed}")

        lines.extend(
            [
                "",
                f"Stories: {self.total_stories_matched} matched, "
                f"{self.total_stories_created} created, "
                f"{self.total_stories_updated} updated",
                f"Subtasks: {self.total_subtasks_created} created",
            ]
        )

        if self.errors:
            lines.append(f"\nErrors ({len(self.errors)}):")
            for error in self.errors[:5]:
                lines.append(f"  - {error}")
            if len(self.errors) > 5:
                lines.append(f"  ... and {len(self.errors) - 5} more")

        return "\n".join(lines)


class MultiEpicSyncOrchestrator:
    """
    Orchestrates synchronization of multiple epics from a single file.

    Parses a multi-epic markdown file and syncs each epic to its
    corresponding Jira epic.
    """

    def __init__(
        self,
        tracker: IssueTrackerPort,
        parser: DocumentParserPort,
        formatter: DocumentFormatterPort,
        config: "SyncConfig",
        event_bus: EventBus | None = None,
    ):
        """
        Initialize the multi-epic orchestrator.

        Args:
            tracker: Issue tracker port
            parser: Document parser port
            formatter: Document formatter port
            config: Sync configuration
            event_bus: Optional event bus
        """
        self.tracker = tracker
        self.parser = parser
        self.formatter = formatter
        self.config = config
        self.event_bus = event_bus or EventBus()
        self.logger = logging.getLogger("MultiEpicSyncOrchestrator")

    def analyze(
        self,
        markdown_path: str,
        epic_filter: list[str] | None = None,
    ) -> MultiEpicSyncResult:
        """
        Analyze a multi-epic file without syncing.

        Args:
            markdown_path: Path to markdown file
            epic_filter: Optional list of epic keys to include

        Returns:
            MultiEpicSyncResult with analysis
        """
        result = MultiEpicSyncResult(dry_run=True)

        # Parse epics from file
        epics = self.parser.parse_epics(markdown_path)

        # Filter if specified
        if epic_filter:
            epics = [e for e in epics if str(e.key) in epic_filter]

        result.epics_total = len(epics)

        for epic in epics:
            epic_result = EpicSyncResult(
                epic_key=str(epic.key),
                epic_title=epic.title,
                stories_total=len(epic.stories),
                dry_run=True,
            )
            result.add_epic_result(epic_result)

        return result

    def sync(
        self,
        markdown_path: str,
        epic_filter: list[str] | None = None,
        progress_callback: Callable[[str, str, int, int], None] | None = None,
        stop_on_error: bool = False,
    ) -> MultiEpicSyncResult:
        """
        Sync multiple epics from a markdown file.

        Args:
            markdown_path: Path to markdown file
            epic_filter: Optional list of epic keys to include
            progress_callback: Callback for progress (epic_key, phase, current, total)
            stop_on_error: Whether to stop on first error

        Returns:
            MultiEpicSyncResult with sync details
        """

        result = MultiEpicSyncResult(dry_run=self.config.dry_run)

        # Parse epics from file
        self.logger.info(f"Parsing epics from {markdown_path}")
        epics = self.parser.parse_epics(markdown_path)

        if not epics:
            result.add_epic_result(
                EpicSyncResult(
                    epic_key="N/A",
                    epic_title="N/A",
                    success=False,
                    errors=["No epics found in file"],
                )
            )
            return result

        # Filter if specified
        if epic_filter:
            original_count = len(epics)
            epics = [e for e in epics if str(e.key) in epic_filter]
            self.logger.info(f"Filtered to {len(epics)}/{original_count} epics")

        result.epics_total = len(epics)
        self.logger.info(f"Syncing {len(epics)} epics")

        # Sync each epic
        for i, epic in enumerate(epics):
            epic_key = str(epic.key)

            self.logger.info(f"[{i + 1}/{len(epics)}] Syncing epic {epic_key}: {epic.title}")

            if progress_callback:
                progress_callback(epic_key, "Starting", i + 1, len(epics))

            epic_result = self._sync_single_epic(
                epic=epic,
                markdown_path=markdown_path,
                progress_callback=lambda phase, curr, total: (
                    progress_callback(epic_key, phase, curr, total) if progress_callback else None
                ),
            )

            result.add_epic_result(epic_result)

            if not epic_result.success and stop_on_error:
                self.logger.error(f"Stopping due to error in {epic_key}")
                break

        result.completed_at = datetime.now()
        return result

    def _sync_single_epic(
        self,
        epic: Epic,
        markdown_path: str,
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> EpicSyncResult:
        """
        Sync a single epic.

        Creates a temporary single-epic content and uses the
        standard SyncOrchestrator to sync it.
        """
        from .orchestrator import SyncOrchestrator

        epic_key = str(epic.key)
        result = EpicSyncResult(
            epic_key=epic_key,
            epic_title=epic.title,
            dry_run=self.config.dry_run,
            started_at=datetime.now(),
        )

        result.stories_total = len(epic.stories)

        if not epic.stories:
            result.add_warning(f"No stories found for epic {epic_key}")
            result.completed_at = datetime.now()
            return result

        try:
            # Create a single-epic orchestrator
            orchestrator = SyncOrchestrator(
                tracker=self.tracker,
                parser=self.parser,
                formatter=self.formatter,
                config=self.config,
                event_bus=self.event_bus,
            )

            # Inject the pre-parsed stories
            orchestrator._md_stories = epic.stories

            # Fetch and match with Jira
            orchestrator._fetch_jira_state(epic_key)
            orchestrator._match_stories()

            result.stories_matched = len(orchestrator._matches)

            # Create a minimal sync result to track changes
            from .orchestrator import SyncResult

            sync_result = SyncResult(dry_run=self.config.dry_run)
            sync_result.stories_matched = result.stories_matched

            # Sync descriptions
            if self.config.sync_descriptions:
                orchestrator._sync_descriptions(sync_result)

            # Sync subtasks
            if self.config.sync_subtasks:
                orchestrator._sync_subtasks(sync_result)

            # Transfer results
            result.stories_updated = sync_result.stories_updated
            result.subtasks_created = sync_result.subtasks_created
            result.subtasks_updated = sync_result.subtasks_updated
            result.errors.extend(sync_result.errors)
            result.warnings.extend(sync_result.warnings)
            result.success = sync_result.success

        except Exception as e:
            result.add_error(f"Sync failed for {epic_key}: {e!s}")
            self.logger.error(f"Error syncing {epic_key}: {e}")

        result.completed_at = datetime.now()
        return result

    def get_epic_summary(self, markdown_path: str) -> dict[str, Any]:
        """
        Get a summary of epics in a file without syncing.

        Args:
            markdown_path: Path to markdown file

        Returns:
            Summary dict with epic info
        """
        epics = self.parser.parse_epics(markdown_path)

        return {
            "total_epics": len(epics),
            "total_stories": sum(len(e.stories) for e in epics),
            "epics": [
                {
                    "key": str(e.key),
                    "title": e.title,
                    "stories": len(e.stories),
                }
                for e in epics
            ],
        }
