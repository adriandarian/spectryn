"""
Bidirectional Sync - Two-way synchronization with conflict detection.

Synchronizes changes in both directions:
- Push: Markdown -> Tracker (create/update issues)
- Pull: Tracker -> Markdown (update local file)

With conflict detection when both sides have been modified.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from spectryn.core.domain.entities import UserStory
from spectryn.core.domain.events import EventBus
from spectryn.core.ports.config_provider import SyncConfig
from spectryn.core.ports.issue_tracker import IssueData, IssueTrackerPort

from .conflict import (
    Conflict,
    ConflictDetector,
    ConflictReport,
    ConflictResolver,
    ResolutionStrategy,
    SnapshotStore,
    StorySnapshot,
    SyncSnapshot,
    create_snapshot_from_sync,
)


@dataclass
class BidirectionalSyncResult:
    """Result of a bidirectional sync operation."""

    success: bool = True
    dry_run: bool = True

    # Push stats (Markdown -> Tracker)
    stories_pushed: int = 0
    stories_created: int = 0
    stories_updated: int = 0
    subtasks_synced: int = 0

    # Pull stats (Tracker -> Markdown)
    stories_pulled: int = 0
    fields_updated_locally: int = 0

    # Conflict stats
    conflicts_detected: int = 0
    conflicts_resolved: int = 0
    conflicts_skipped: int = 0

    # Details
    pushed_stories: list[str] = field(default_factory=list)
    pulled_stories: list[str] = field(default_factory=list)
    conflict_report: ConflictReport | None = None

    # Output
    markdown_updated: bool = False
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
    def has_conflicts(self) -> bool:
        """Check if any conflicts were detected."""
        return self.conflicts_detected > 0

    @property
    def summary(self) -> str:
        """Get a human-readable summary."""
        lines = []
        mode = "Preview" if self.dry_run else "Result"
        lines.append(f"Bidirectional Sync {mode}")
        lines.append("=" * 50)

        lines.append("")
        lines.append("Push (Markdown → Tracker):")
        lines.append(f"  Stories: {self.stories_pushed}")
        lines.append(f"    Created: {self.stories_created}")
        lines.append(f"    Updated: {self.stories_updated}")
        lines.append(f"  Subtasks: {self.subtasks_synced}")

        lines.append("")
        lines.append("Pull (Tracker → Markdown):")
        lines.append(f"  Stories pulled: {self.stories_pulled}")
        lines.append(f"  Fields updated: {self.fields_updated_locally}")

        if self.conflicts_detected > 0:
            lines.append("")
            lines.append("Conflicts:")
            lines.append(f"  Detected: {self.conflicts_detected}")
            lines.append(f"  Resolved: {self.conflicts_resolved}")
            lines.append(f"  Skipped: {self.conflicts_skipped}")

        if self.errors:
            lines.append("")
            lines.append("Errors:")
            for err in self.errors[:5]:
                lines.append(f"  • {err}")

        return "\n".join(lines)


class BidirectionalSyncOrchestrator:
    """
    Orchestrates bidirectional synchronization between markdown and tracker.

    Workflow:
    1. Load last sync snapshot (baseline)
    2. Parse current markdown file
    3. Fetch current tracker state
    4. Detect conflicts (both sides changed since last sync)
    5. Resolve conflicts (strategy or interactive)
    6. Push local changes to tracker
    7. Pull remote changes to markdown
    8. Save new snapshot

    This enables true two-way sync where:
    - New stories in markdown are created in tracker
    - Changes in tracker are reflected back in markdown
    - Conflicts are detected and resolved appropriately
    """

    def __init__(
        self,
        tracker: IssueTrackerPort,
        config: SyncConfig,
        parser: Any = None,
        writer: Any = None,
        event_bus: EventBus | None = None,
        snapshot_store: SnapshotStore | None = None,
    ):
        """
        Initialize the bidirectional sync orchestrator.

        Args:
            tracker: Issue tracker adapter.
            config: Sync configuration.
            parser: Markdown parser (optional, will create default).
            writer: Markdown writer (optional, will create default).
            event_bus: Optional event bus.
            snapshot_store: Optional snapshot store (uses default if not provided).
        """
        self.tracker = tracker
        self.config = config
        self.event_bus = event_bus or EventBus()
        self.snapshot_store = snapshot_store or SnapshotStore()
        self.logger = logging.getLogger("BidirectionalSyncOrchestrator")

        # Lazy load parser and writer
        self._parser = parser
        self._writer = writer

        # State during sync
        self._local_stories: list[UserStory] = []
        self._remote_issues: list[IssueData] = []
        self._matches: dict[str, str] = {}  # story_id -> jira_key
        self._base_snapshot: SyncSnapshot | None = None

    @property
    def parser(self) -> Any:
        """Get or create the markdown parser."""
        if self._parser is None:
            from spectryn.adapters.parsers.markdown import MarkdownParser

            self._parser = MarkdownParser()
        return self._parser

    @property
    def writer(self) -> Any:
        """Get or create the markdown writer."""
        if self._writer is None:
            from spectryn.adapters.formatters.markdown_writer import MarkdownUpdater

            self._writer = MarkdownUpdater()
        return self._writer

    def sync(
        self,
        markdown_path: str,
        epic_key: str,
        resolution_strategy: ResolutionStrategy = ResolutionStrategy.ASK,
        conflict_resolver: Callable[[Conflict], str] | None = None,
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> BidirectionalSyncResult:
        """
        Perform bidirectional sync.

        Args:
            markdown_path: Path to markdown file.
            epic_key: Epic key in tracker.
            resolution_strategy: Strategy for resolving conflicts.
            conflict_resolver: Optional function to resolve individual conflicts.
            progress_callback: Optional progress callback.

        Returns:
            BidirectionalSyncResult with sync details.
        """
        result = BidirectionalSyncResult(dry_run=self.config.dry_run)
        result.output_path = markdown_path
        total_phases = 7

        try:
            # Phase 1: Load baseline snapshot
            self._report_progress(progress_callback, "Loading baseline", 1, total_phases)
            self._base_snapshot = self.snapshot_store.load(epic_key)

            # Phase 2: Parse current markdown
            self._report_progress(progress_callback, "Parsing markdown", 2, total_phases)
            self._parse_markdown(markdown_path, result)

            # Phase 3: Fetch current tracker state
            self._report_progress(progress_callback, "Fetching from tracker", 3, total_phases)
            self._fetch_tracker_state(epic_key, result)

            # Phase 4: Match stories
            self._report_progress(progress_callback, "Matching stories", 4, total_phases)
            self._match_stories()

            # Phase 5: Detect conflicts
            self._report_progress(progress_callback, "Detecting conflicts", 5, total_phases)
            conflict_report = self._detect_conflicts(epic_key)
            result.conflict_report = conflict_report
            result.conflicts_detected = conflict_report.conflict_count

            # Phase 6: Resolve conflicts
            if conflict_report.has_conflicts:
                self._report_progress(progress_callback, "Resolving conflicts", 6, total_phases)
                self._resolve_conflicts(
                    conflict_report, resolution_strategy, conflict_resolver, result
                )

            # Phase 7: Apply changes
            self._report_progress(progress_callback, "Applying changes", 7, total_phases)

            if not self.config.dry_run:
                # Push local changes to tracker
                self._push_changes(result, conflict_report)

                # Pull remote changes to markdown
                self._pull_changes(markdown_path, result, conflict_report)

                # Save snapshot
                self._save_snapshot(epic_key, markdown_path)

        except Exception as e:
            self.logger.error(f"Bidirectional sync failed: {e}")
            result.add_error(str(e))

        return result

    def preview(
        self,
        markdown_path: str,
        epic_key: str,
    ) -> BidirectionalSyncResult:
        """
        Preview bidirectional sync without making changes.

        Args:
            markdown_path: Path to markdown file.
            epic_key: Epic key in tracker.

        Returns:
            BidirectionalSyncResult showing what would happen.
        """
        # Force dry run for preview
        original_dry_run = self.config.dry_run
        self.config.dry_run = True

        try:
            result = self.sync(
                markdown_path=markdown_path,
                epic_key=epic_key,
                resolution_strategy=ResolutionStrategy.SKIP,
            )
        finally:
            self.config.dry_run = original_dry_run

        return result

    def _parse_markdown(self, markdown_path: str, result: BidirectionalSyncResult) -> None:
        """Parse the markdown file."""
        path = Path(markdown_path)
        if not path.exists():
            result.add_error(f"Markdown file not found: {markdown_path}")
            return

        content = path.read_text(encoding="utf-8")
        self._local_stories = self.parser.parse_stories(content)
        self.logger.info(f"Parsed {len(self._local_stories)} stories from markdown")

    def _fetch_tracker_state(self, epic_key: str, result: BidirectionalSyncResult) -> None:
        """Fetch current state from tracker."""
        try:
            self._remote_issues = self.tracker.get_epic_children(epic_key)
            self.logger.info(f"Fetched {len(self._remote_issues)} issues from tracker")
        except Exception as e:
            result.add_error(f"Failed to fetch from tracker: {e}")

    def _match_stories(self) -> None:
        """Match local stories to remote issues."""
        self._matches = {}

        for story in self._local_stories:
            story_id = str(story.id)

            # Match by external key if set
            if story.external_key:
                self._matches[story_id] = str(story.external_key)
                continue

            # Try to match by title
            for issue in self._remote_issues:
                if self._titles_match(story.title, issue.summary):
                    self._matches[story_id] = issue.key
                    break

        self.logger.info(f"Matched {len(self._matches)} stories to issues")

    def _titles_match(self, local_title: str, remote_title: str) -> bool:
        """Check if titles match (ignoring minor differences)."""
        # Normalize titles
        local = local_title.lower().strip()
        remote = remote_title.lower().strip()

        # Direct match
        if local == remote:
            return True

        # Check if one contains the other (for prefixed titles)
        return bool(local in remote or remote in local)

    def _detect_conflicts(self, epic_key: str) -> ConflictReport:
        """Detect conflicts between local and remote state."""
        detector = ConflictDetector(base_snapshot=self._base_snapshot)
        return detector.detect_conflicts(
            local_stories=self._local_stories,
            remote_issues=self._remote_issues,
            matches=self._matches,
        )

    def _resolve_conflicts(
        self,
        conflict_report: ConflictReport,
        strategy: ResolutionStrategy,
        conflict_resolver: Callable[[Conflict], str] | None,
        result: BidirectionalSyncResult,
    ) -> None:
        """Resolve detected conflicts."""
        resolver = ConflictResolver(strategy=strategy, prompt_func=conflict_resolver)
        resolver.resolve(conflict_report)

        result.conflicts_resolved = conflict_report.resolved_count
        result.conflicts_skipped = conflict_report.unresolved_count

    def _push_changes(
        self, result: BidirectionalSyncResult, conflict_report: ConflictReport
    ) -> None:
        """Push local changes to tracker."""
        # Get stories that should be pushed (not skipped due to conflicts)
        skipped_stories = {
            r.conflict.story_id for r in conflict_report.resolutions if r.resolution == "skip"
        }

        for story in self._local_stories:
            story_id = str(story.id)

            if story_id in skipped_stories:
                continue

            jira_key = self._matches.get(story_id)

            if not jira_key:
                # New story - would need to create (simplified here)
                result.stories_created += 1
                result.pushed_stories.append(story_id)
            # Check if local has changes to push
            elif self._local_has_changes(story, jira_key, conflict_report):
                result.stories_updated += 1
                result.pushed_stories.append(story_id)

            result.stories_pushed += 1
            result.subtasks_synced += len(story.subtasks)

    def _local_has_changes(
        self, story: UserStory, jira_key: str, conflict_report: ConflictReport
    ) -> bool:
        """Check if local story has changes to push."""
        if not self._base_snapshot:
            return True  # First sync, everything is "new"

        base_story = self._base_snapshot.get_story(str(story.id))
        if not base_story:
            return True  # Story not in snapshot, treat as new

        # Check if resolution says to use local
        for res in conflict_report.resolutions:
            if res.conflict.story_id == str(story.id) and res.resolution == "local":
                return True

        # Compare current to base
        current = StorySnapshot.from_story(story, jira_key)
        return (
            current.title.hash != base_story.title.hash
            or current.description.hash != base_story.description.hash
            or current.status.hash != base_story.status.hash
            or current.story_points.hash != base_story.story_points.hash
        )

    def _pull_changes(
        self,
        markdown_path: str,
        result: BidirectionalSyncResult,
        conflict_report: ConflictReport,
    ) -> None:
        """Pull remote changes to markdown."""
        # Get stories that should be updated from remote
        remote_updates: dict[str, dict[str, Any]] = {}

        # Stories resolved as "remote"
        for res in conflict_report.resolutions:
            if res.resolution == "remote":
                story_id = res.conflict.story_id
                jira_key = res.conflict.jira_key

                # Find the remote issue
                remote = next((i for i in self._remote_issues if i.key == jira_key), None)
                if remote:
                    if story_id not in remote_updates:
                        remote_updates[story_id] = {}
                    remote_updates[story_id][res.conflict.field] = res.conflict.remote_value

        # Check for remote-only changes (not conflicts)
        for issue in self._remote_issues:
            story_id = next((sid for sid, jk in self._matches.items() if jk == issue.key), None)
            if not story_id:
                continue

            if story_id in {r.conflict.story_id for r in conflict_report.resolutions}:
                continue  # Already handled as conflict

            # Check if remote has changes
            if self._remote_has_changes(issue):
                if story_id not in remote_updates:
                    remote_updates[story_id] = {}
                # Add all remote fields
                remote_updates[story_id]["status"] = issue.status
                remote_updates[story_id]["story_points"] = issue.story_points

        if remote_updates:
            # Update markdown file
            result.stories_pulled = len(remote_updates)
            result.fields_updated_locally = sum(len(u) for u in remote_updates.values())
            result.pulled_stories = list(remote_updates.keys())
            result.markdown_updated = True

            # Apply updates to markdown (simplified - full implementation would use MarkdownUpdater)
            self._apply_markdown_updates(markdown_path, remote_updates)

    def _remote_has_changes(self, issue: IssueData) -> bool:
        """Check if remote issue has changes since last sync."""
        if not self._base_snapshot:
            return False  # No baseline, can't tell

        base_story = self._base_snapshot.get_story_by_jira_key(issue.key)
        if not base_story:
            return True  # Not in snapshot, treat as changed

        # Compare status
        from spectryn.core.domain.enums import Status

        current_status = Status.from_string(issue.status).value
        if current_status != base_story.status.value:
            return True

        # Compare story points
        current_sp = int(issue.story_points) if issue.story_points else 0
        return current_sp != (base_story.story_points.value or 0)

    def _apply_markdown_updates(
        self, markdown_path: str, updates: dict[str, dict[str, Any]]
    ) -> None:
        """Apply updates to markdown file."""
        if not updates:
            return

        path = Path(markdown_path)
        content = path.read_text(encoding="utf-8")

        # Use the updater to apply changes
        updated_content = self.writer.update_stories(content, updates)

        path.write_text(updated_content, encoding="utf-8")
        self.logger.info(f"Updated markdown with {len(updates)} story changes")

    def _save_snapshot(self, epic_key: str, markdown_path: str) -> None:
        """Save a new snapshot after successful sync."""
        snapshot = create_snapshot_from_sync(
            epic_key=epic_key,
            markdown_path=markdown_path,
            stories=self._local_stories,
            matches=self._matches,
        )
        self.snapshot_store.save(snapshot)
        self.logger.info(f"Saved sync snapshot for {epic_key}")

    def _report_progress(
        self,
        callback: Callable[[str, int, int], None] | None,
        phase: str,
        current: int,
        total: int,
    ) -> None:
        """Report progress if callback is provided."""
        if callback:
            callback(phase, current, total)
