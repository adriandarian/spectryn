"""
Sync Orchestrator - Coordinates the synchronization process.

This is the main entry point for sync operations.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from spectra.core.ports.issue_tracker import IssueData, IssueTrackerPort


if TYPE_CHECKING:
    from .backup import Backup, BackupManager
    from .incremental import ChangeTracker
    from .state import StateStore, SyncState
from spectra.application.commands import (
    AddCommentCommand,
    CommandBatch,
    CreateSubtaskCommand,
    TransitionStatusCommand,
    UpdateDescriptionCommand,
    UpdateSubtaskCommand,
)
from spectra.core.domain.entities import UserStory
from spectra.core.domain.events import EventBus, SyncCompleted, SyncStarted
from spectra.core.ports.config_provider import SyncConfig
from spectra.core.ports.document_formatter import DocumentFormatterPort
from spectra.core.ports.document_parser import DocumentParserPort


@dataclass
class FailedOperation:
    """
    Details of a failed operation during sync.

    Provides context about what failed, where, and why for
    better error reporting and debugging.
    """

    operation: str  # e.g., "update_description", "create_subtask"
    issue_key: str  # The issue that was being operated on
    error: str  # The error message
    story_id: str = ""  # The markdown story ID (if applicable)
    recoverable: bool = True  # Whether other operations can continue

    def __str__(self) -> str:
        """Format as human-readable error message."""
        if self.story_id:
            return f"[{self.operation}] {self.issue_key} (story {self.story_id}): {self.error}"
        return f"[{self.operation}] {self.issue_key}: {self.error}"


@dataclass
class SyncResult:
    """
    Result of a sync operation with graceful degradation support.

    Contains counts, details, and status of a completed sync operation.
    Supports partial success - some operations can fail while others succeed.

    Attributes:
        success: Whether the sync completed without any errors.
        dry_run: Whether this was a dry-run (no changes made).
        stories_matched: Number of markdown stories matched to tracker issues.
        stories_updated: Number of story descriptions updated.
        subtasks_created: Number of new subtasks created.
        subtasks_updated: Number of existing subtasks updated.
        comments_added: Number of comments added to issues.
        statuses_updated: Number of status transitions performed.
        matched_stories: List of (markdown_id, tracker_key) tuples.
        unmatched_stories: List of markdown story IDs that couldn't be matched.
        failed_operations: List of FailedOperation with detailed error info.
        errors: List of error messages (for backward compatibility).
        warnings: List of warning messages.
        incremental: Whether incremental sync was used.
        stories_skipped: Number of unchanged stories skipped (incremental).
        changed_story_ids: IDs of stories that were changed (incremental).
    """

    success: bool = True
    dry_run: bool = True

    # Counts
    epic_updated: bool = False
    stories_matched: int = 0
    stories_created: int = 0
    stories_updated: int = 0
    subtasks_created: int = 0
    subtasks_updated: int = 0
    comments_added: int = 0
    statuses_updated: int = 0

    # Details
    matched_stories: list[tuple[str, str]] = field(default_factory=list)  # (md_id, jira_key)
    unmatched_stories: list[str] = field(default_factory=list)
    failed_operations: list[FailedOperation] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # Incremental sync stats
    incremental: bool = False
    stories_skipped: int = 0
    changed_story_ids: set[str] = field(default_factory=set)

    def add_error(self, error: str) -> None:
        """
        Add an error message and mark sync as failed.

        Args:
            error: Error message to add.
        """
        self.errors.append(error)
        self.success = False

    def add_failed_operation(
        self,
        operation: str,
        issue_key: str,
        error: str,
        story_id: str = "",
        recoverable: bool = True,
    ) -> None:
        """
        Add a failed operation with detailed context.

        Args:
            operation: The operation that failed.
            issue_key: The issue being operated on.
            error: The error message.
            story_id: The markdown story ID if applicable.
            recoverable: Whether sync can continue after this failure.
        """
        failed = FailedOperation(
            operation=operation,
            issue_key=issue_key,
            error=error,
            story_id=story_id,
            recoverable=recoverable,
        )
        self.failed_operations.append(failed)
        self.errors.append(str(failed))
        self.success = False

    def add_warning(self, warning: str) -> None:
        """
        Add a warning message (does not affect success status).

        Args:
            warning: Warning message to add.
        """
        self.warnings.append(warning)

    @property
    def partial_success(self) -> bool:
        """
        Check if sync had partial success (some ops succeeded, some failed).

        Returns:
            True if there are both successes and failures.
        """
        has_successes = (
            self.stories_updated > 0
            or self.subtasks_created > 0
            or self.subtasks_updated > 0
            or self.comments_added > 0
            or self.statuses_updated > 0
        )
        has_failures = len(self.failed_operations) > 0
        return has_successes and has_failures

    @property
    def total_operations(self) -> int:
        """Total number of operations attempted."""
        return (
            self.stories_updated
            + self.subtasks_created
            + self.subtasks_updated
            + self.comments_added
            + self.statuses_updated
            + len(self.failed_operations)
        )

    @property
    def success_rate(self) -> float:
        """
        Calculate the success rate of operations.

        Returns:
            Percentage of successful operations (0.0 to 1.0).
        """
        total = self.total_operations
        if total == 0:
            return 1.0
        successful = total - len(self.failed_operations)
        return successful / total

    def summary(self) -> str:
        """
        Generate a human-readable summary of the sync result.

        Returns:
            Multi-line summary string.
        """
        lines = []

        if self.dry_run:
            lines.append("DRY RUN - No changes made")

        if self.success:
            lines.append("✓ Sync completed successfully")
        elif self.partial_success:
            lines.append(f"⚠ Sync completed with errors ({len(self.failed_operations)} failures)")
        else:
            lines.append(f"✗ Sync failed ({len(self.errors)} errors)")

        lines.append(f"  Stories matched: {self.stories_matched}")
        lines.append(f"  Descriptions updated: {self.stories_updated}")
        lines.append(f"  Subtasks created: {self.subtasks_created}")
        lines.append(f"  Subtasks updated: {self.subtasks_updated}")
        lines.append(f"  Comments added: {self.comments_added}")
        lines.append(f"  Statuses updated: {self.statuses_updated}")

        if self.incremental:
            lines.append(f"  Stories skipped (unchanged): {self.stories_skipped}")

        if self.failed_operations:
            lines.append("")
            lines.append("Failed operations:")
            for failed in self.failed_operations[:10]:  # Limit to first 10
                lines.append(f"  • {failed}")
            if len(self.failed_operations) > 10:
                lines.append(f"  ... and {len(self.failed_operations) - 10} more")

        if self.warnings:
            lines.append("")
            lines.append("Warnings:")
            for warning in self.warnings[:5]:  # Limit to first 5
                lines.append(f"  • {warning}")
            if len(self.warnings) > 5:
                lines.append(f"  ... and {len(self.warnings) - 5} more")

        return "\n".join(lines)


class SyncOrchestrator:
    """
    Orchestrates the synchronization between markdown and issue tracker.

    Phases:
    0. Create backup of current Jira state (if enabled)
    1. Parse markdown into domain entities
    2. Fetch current state from issue tracker
    3. Match markdown stories to tracker issues
    4. Generate commands for required changes
    5. Execute commands (or preview in dry-run)
    """

    def __init__(
        self,
        tracker: IssueTrackerPort,
        parser: DocumentParserPort,
        formatter: DocumentFormatterPort,
        config: SyncConfig,
        event_bus: EventBus | None = None,
        state_store: StateStore | None = None,
        backup_manager: BackupManager | None = None,
    ):
        """
        Initialize the orchestrator.

        Args:
            tracker: Issue tracker port
            parser: Document parser port
            formatter: Document formatter port
            config: Sync configuration
            event_bus: Optional event bus
            state_store: Optional state store for persistence
            backup_manager: Optional backup manager for pre-sync backups
        """
        self.tracker = tracker
        self.parser = parser
        self.formatter = formatter
        self.config = config
        self.event_bus = event_bus or EventBus()
        self.state_store = state_store
        self.backup_manager = backup_manager
        self.logger = logging.getLogger("SyncOrchestrator")

        self._md_stories: list[UserStory] = []
        self._jira_issues: list[IssueData] = []
        self._matches: dict[str, str] = {}  # story_id -> issue_key
        self._state: SyncState | None = None
        self._last_backup: Backup | None = None

        # Incremental sync support
        self._change_tracker: ChangeTracker | None = None
        self._changed_story_ids: set[str] = set()
        if self.config.incremental:
            from .incremental import ChangeTracker

            state_dir = self.config.incremental_state_dir or "~/.spectra/sync"
            self._change_tracker = ChangeTracker(storage_dir=state_dir)

    # -------------------------------------------------------------------------
    # Main Entry Points
    # -------------------------------------------------------------------------

    def analyze(
        self,
        markdown_path: str,
        epic_key: str,
    ) -> SyncResult:
        """
        Analyze markdown and issue tracker without making changes.

        Args:
            markdown_path: Path to markdown file
            epic_key: Jira epic key

        Returns:
            SyncResult with analysis details
        """
        result = SyncResult(dry_run=True)

        # Parse markdown
        self._md_stories = self.parser.parse_stories(markdown_path)
        self.logger.debug(f"Parsed {len(self._md_stories)} stories from markdown")

        # Fetch Jira issues
        self._jira_issues = self.tracker.get_epic_children(epic_key)
        self.logger.debug(f"Found {len(self._jira_issues)} issues in Jira epic")

        # Match stories
        self._match_stories(result)

        return result

    def sync(
        self,
        markdown_path: str,
        epic_key: str,
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> SyncResult:
        """
        Full sync from markdown to issue tracker.

        Args:
            markdown_path: Path to markdown file
            epic_key: Jira epic key
            progress_callback: Optional callback for progress updates

        Returns:
            SyncResult with sync details
        """
        result = SyncResult(dry_run=self.config.dry_run)

        # Publish start event
        self.event_bus.publish(
            SyncStarted(
                epic_key=epic_key,
                markdown_path=markdown_path,
                dry_run=self.config.dry_run,
            )
        )

        # Phase 0: Create backup (only for non-dry-run)
        if not self.config.dry_run and self.config.backup_enabled:
            self._report_progress(progress_callback, "Creating backup", 0, 6)
            try:
                self._create_backup(markdown_path, epic_key)
            except Exception as e:
                self.logger.error(f"Backup failed: {e}")
                result.add_warning(f"Backup failed: {e}")

        # Phase 1: Analyze
        total_phases = 8 if self.config.backup_enabled else 7
        self._report_progress(progress_callback, "Analyzing", 1, total_phases)
        analyze_result = self.analyze(markdown_path, epic_key)
        result.stories_matched = len(self._matches)
        result.matched_stories = list(self._matches.items())
        result.unmatched_stories = analyze_result.unmatched_stories

        # Phase 1a: Update epic issue itself
        if self.config.sync_epic:
            self._report_progress(progress_callback, "Updating epic", 2, total_phases)
            self._sync_epic(markdown_path, epic_key, result)

        # Phase 1b: Create unmatched stories
        if self.config.create_stories and result.unmatched_stories:
            self._report_progress(progress_callback, "Creating stories", 2, total_phases)
            self._create_unmatched_stories(epic_key, result, progress_callback)
            # Update matched count after creation
            result.stories_matched = len(self._matches)
            result.matched_stories = list(self._matches.items())

        # Phase 1c: Detect changes (incremental sync)
        if self.config.incremental and self._change_tracker and not self.config.force_full_sync:
            self._change_tracker.load(epic_key, markdown_path)
            changes = self._change_tracker.detect_changes(self._md_stories)
            self._changed_story_ids = {
                story_id for story_id, change in changes.items() if change.has_changes
            }
            result.incremental = True
            result.changed_story_ids = self._changed_story_ids
            result.stories_skipped = len(self._md_stories) - len(self._changed_story_ids)

            if result.stories_skipped > 0:
                self.logger.info(
                    f"Incremental sync: {len(self._changed_story_ids)} changed, "
                    f"{result.stories_skipped} skipped"
                )
        else:
            # Full sync - all stories are "changed"
            self._changed_story_ids = {str(s.id) for s in self._md_stories}

        # Phase 2: Update descriptions
        if self.config.sync_descriptions:
            self._report_progress(progress_callback, "Updating descriptions", 2, total_phases)
            self._sync_descriptions(result)

        # Phase 3: Sync subtasks
        if self.config.sync_subtasks:
            self._report_progress(progress_callback, "Syncing subtasks", 3, total_phases)
            self._sync_subtasks(result)

        # Phase 4: Add commit comments
        if self.config.sync_comments:
            self._report_progress(progress_callback, "Adding comments", 4, total_phases)
            self._sync_comments(result)

        # Phase 5: Sync statuses
        if self.config.sync_statuses:
            self._report_progress(progress_callback, "Syncing statuses", 5, total_phases)
            self._sync_statuses(result)

        # Save incremental sync state (on successful non-dry-run)
        if (
            self.config.incremental
            and self._change_tracker
            and not self.config.dry_run
            and result.success
        ):
            self._change_tracker.save(epic_key, markdown_path)

        # Publish complete event
        self.event_bus.publish(
            SyncCompleted(
                epic_key=epic_key,
                stories_matched=result.stories_matched,
                stories_updated=result.stories_updated,
                subtasks_created=result.subtasks_created,
                comments_added=result.comments_added,
                errors=result.errors,
            )
        )

        return result

    def sync_descriptions_only(
        self,
        markdown_path: str,
        epic_key: str,
    ) -> SyncResult:
        """
        Sync only story descriptions (skip subtasks, comments, statuses).

        Args:
            markdown_path: Path to markdown file.
            epic_key: Jira epic key.

        Returns:
            SyncResult with sync details.
        """
        result = SyncResult(dry_run=self.config.dry_run)
        self.analyze(markdown_path, epic_key)
        self._sync_descriptions(result)
        return result

    def sync_subtasks_only(
        self,
        markdown_path: str,
        epic_key: str,
    ) -> SyncResult:
        """
        Sync only subtasks (skip descriptions, comments, statuses).

        Args:
            markdown_path: Path to markdown file.
            epic_key: Jira epic key.

        Returns:
            SyncResult with sync details.
        """
        result = SyncResult(dry_run=self.config.dry_run)
        self.analyze(markdown_path, epic_key)
        self._sync_subtasks(result)
        return result

    def sync_statuses_only(
        self,
        markdown_path: str,
        epic_key: str,
        target_status: str = "Resolved",
    ) -> SyncResult:
        """
        Sync subtask statuses to a target status.

        Only updates subtasks belonging to completed stories.

        Args:
            markdown_path: Path to markdown file.
            epic_key: Jira epic key.
            target_status: Status to transition subtasks to.

        Returns:
            SyncResult with sync details.
        """
        result = SyncResult(dry_run=self.config.dry_run)
        self.analyze(markdown_path, epic_key)
        self._sync_statuses(result, target_status)
        return result

    # -------------------------------------------------------------------------
    # Matching Logic
    # -------------------------------------------------------------------------

    def _match_stories(self, result: SyncResult) -> None:
        """
        Match markdown stories to Jira issues by title.

        Populates self._matches with story_id -> issue_key mappings.
        Updates result with matched and unmatched story information.

        Args:
            result: SyncResult to update with matching results.
        """
        self._matches = {}

        for md_story in self._md_stories:
            matched_issue = None

            # Try to match by title
            for jira_issue in self._jira_issues:
                if md_story.matches_title(jira_issue.summary):
                    matched_issue = jira_issue
                    break

            if matched_issue:
                self._matches[str(md_story.id)] = matched_issue.key
                result.matched_stories.append((str(md_story.id), matched_issue.key))
                self.logger.debug(f"Matched {md_story.id} -> {matched_issue.key}")
            else:
                result.unmatched_stories.append(str(md_story.id))
                result.add_warning(f"Could not match story: {md_story.id} - {md_story.title}")

        result.stories_matched = len(self._matches)

    def _create_unmatched_stories(
        self,
        epic_key: str,
        result: SyncResult,
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> None:
        """
        Create stories in Jira for unmatched markdown stories.

        Args:
            epic_key: The epic key to link new stories to.
            result: SyncResult to update with creation results.
            progress_callback: Optional callback for progress updates.
        """
        if not hasattr(self.tracker, "create_story"):
            self.logger.warning("Tracker does not support story creation")
            return

        # Get project key from epic key
        project_key = epic_key.split("-")[0] if "-" in epic_key else epic_key

        # Get list of stories to create
        stories_to_create = [
            s for s in self._md_stories if str(s.id) in list(result.unmatched_stories)
        ]
        total_stories = len(stories_to_create)

        created_count = 0
        for i, md_story in enumerate(stories_to_create):
            story_id = str(md_story.id)

            # Report sub-progress
            if progress_callback:
                progress_callback(f"Creating {i + 1}/{total_stories}", i, total_stories)

            # Format description
            description = ""
            if md_story.description:
                description = md_story.description.to_markdown()

            # Add acceptance criteria
            if md_story.acceptance_criteria:
                description += "\n\n## Acceptance Criteria\n"
                description += md_story.acceptance_criteria.to_markdown()

            # Create the story - try "User Story" first, fall back to "Story"
            # Some Jira projects use "User Story" as the issue type name
            new_key = None
            for issue_type in ["User Story", "Story"]:
                try:
                    new_key = self.tracker.create_story(
                        summary=md_story.title,
                        description=description,
                        project_key=project_key,
                        epic_key=epic_key,
                        story_points=md_story.story_points,
                        priority=None,  # Skip priority - custom schemes vary by project
                        assignee=None,  # Will auto-assign to current user in adapter
                        issue_type=issue_type,
                    )
                    if new_key or self.config.dry_run:
                        break  # Success or dry-run
                except Exception as e:
                    if "User Story" in str(e) or "issue type" in str(e).lower():
                        continue  # Try next issue type
                    raise  # Re-raise other errors

            # Count as created (even in dry-run where new_key is None)
            created_count += 1

            if new_key:
                # Add to matches so subsequent phases can sync to it
                self._matches[story_id] = new_key
                result.matched_stories.append((story_id, new_key))
                self.logger.debug(f"Created story {new_key} for {story_id}: {md_story.title}")

                # Also add to jira_issues for subtask/description sync
                # Create a minimal issue representation
                class CreatedIssue:
                    def __init__(self, key: str, summary: str) -> None:
                        self.key = key
                        self.summary = summary

                self._jira_issues.append(CreatedIssue(new_key, md_story.title))

        # Remove created stories from unmatched list (only if actually created)
        if not self.config.dry_run:
            result.unmatched_stories = [
                s for s in result.unmatched_stories if s not in self._matches
            ]

        # Always set count (for dry-run display)
        result.stories_created = created_count
        if created_count > 0:
            self.logger.debug(f"{'Would create' if self.config.dry_run else 'Created'} {created_count} stories")

    def _sync_epic(self, markdown_path: str, epic_key: str, result: SyncResult) -> None:
        """
        Update the epic issue itself with details from markdown.

        Parses the EPIC.md (or main file) to extract title and description,
        then updates the epic issue in Jira.

        Args:
            markdown_path: Path to markdown file or directory.
            epic_key: The epic key to update.
            result: SyncResult to update.
        """
        from pathlib import Path

        path = Path(markdown_path)

        # Parse epic details
        epic = None
        if path.is_dir():
            # Use directory parser which extracts description from EPIC.md
            if hasattr(self.parser, "parse_epic_directory"):
                epic = self.parser.parse_epic_directory(path)
            else:
                epic_file = path / "EPIC.md"
                if epic_file.exists():
                    epic = self.parser.parse_epic(epic_file.read_text(encoding="utf-8"))
        else:
            epic = self.parser.parse_epic(path.read_text(encoding="utf-8"))

        if not epic:
            self.logger.debug("Could not parse epic details from markdown")
            return

        # Build description from epic content
        description = ""
        if epic.description:
            description = epic.description
        if epic.summary:
            description = f"**{epic.summary}**\n\n{description}" if description else epic.summary

        self.logger.debug(f"Epic description length: {len(description)} chars")

        # Format as ADF if needed
        adf_description = self.formatter.format_text(description) if description else None

        # Update the epic issue
        if self.config.dry_run:
            self.logger.debug(f"[DRY-RUN] Would update epic {epic_key}: {epic.title}")
            result.epic_updated = True  # Mark as would-be-updated for dry-run display
            return

        try:
            # Update description
            if adf_description:
                self.tracker.update_issue_description(epic_key, adf_description)
                result.epic_updated = True
                self.logger.info(f"Updated epic {epic_key} description")
        except Exception as e:
            result.add_warning(f"Failed to update epic {epic_key}: {e}")
            self.logger.error(f"Failed to update epic: {e}")

    # -------------------------------------------------------------------------
    # Sync Phases
    # -------------------------------------------------------------------------

    def _sync_descriptions(self, result: SyncResult) -> None:
        """
        Sync story descriptions from markdown to issue tracker.

        Creates UpdateDescriptionCommand for each matched story with a description,
        and executes them as a batch with graceful degradation (stop_on_error=False).

        Args:
            result: SyncResult to update with operation counts and errors.
        """
        batch = CommandBatch(stop_on_error=False)
        command_to_story: dict[int, tuple[str, str]] = {}  # cmd index -> (story_id, issue_key)

        for md_story in self._md_stories:
            story_id = str(md_story.id)
            if story_id not in self._matches:
                continue

            # Skip unchanged stories in incremental mode
            if self.config.incremental and story_id not in self._changed_story_ids:
                continue

            issue_key = self._matches[story_id]

            # Only update if story has description
            if md_story.description:
                adf = self.formatter.format_story_description(md_story)

                cmd = UpdateDescriptionCommand(
                    tracker=self.tracker,
                    issue_key=issue_key,
                    description=adf,
                    event_bus=self.event_bus,
                    dry_run=self.config.dry_run,
                )
                command_to_story[len(batch.commands)] = (story_id, issue_key)
                batch.add(cmd)

        # Execute batch
        batch.execute_all()
        result.stories_updated = batch.executed_count

        # Record failures with detailed context
        for idx, cmd_result in enumerate(batch.results):
            if not cmd_result.success and cmd_result.error:
                story_id, issue_key = command_to_story.get(idx, ("", "unknown"))
                result.add_failed_operation(
                    operation="update_description",
                    issue_key=issue_key,
                    error=cmd_result.error,
                    story_id=story_id,
                )

    def _sync_subtasks(self, result: SyncResult) -> None:
        """
        Sync subtasks from markdown to issue tracker.

        For each matched story, creates new subtasks or updates existing ones
        based on name matching. Uses graceful degradation - failures don't
        stop processing of remaining subtasks.

        Args:
            result: SyncResult to update with operation counts and errors.
        """
        for md_story in self._md_stories:
            story_id = str(md_story.id)

            # Skip unmatched or unchanged stories
            if not self._should_sync_story_subtasks(story_id):
                continue

            issue_key = self._matches[story_id]
            existing_subtasks = self._fetch_existing_subtasks(issue_key, story_id, result)

            if existing_subtasks is None:
                continue  # Failed to fetch, already logged

            # Sync each subtask
            project_key = issue_key.split("-")[0]
            for md_subtask in md_story.subtasks:
                self._sync_single_subtask(
                    md_subtask, existing_subtasks, issue_key, project_key, story_id, result
                )

    def _should_sync_story_subtasks(self, story_id: str) -> bool:
        """Check if a story's subtasks should be synced."""
        if story_id not in self._matches:
            return False
        return not (self.config.incremental and story_id not in self._changed_story_ids)

    def _fetch_existing_subtasks(
        self, issue_key: str, story_id: str, result: SyncResult
    ) -> dict | None:
        """Fetch existing subtasks for an issue. Returns None on failure."""
        from spectra.core.ports.issue_tracker import IssueTrackerError

        try:
            jira_issue = self.tracker.get_issue(issue_key)
            return {st.summary.lower(): st for st in jira_issue.subtasks}
        except IssueTrackerError as e:
            result.add_failed_operation(
                operation="fetch_issue",
                issue_key=issue_key,
                error=str(e),
                story_id=story_id,
            )
            self.logger.warning(f"Failed to fetch issue {issue_key}, skipping subtasks: {e}")
            return None

    def _sync_single_subtask(
        self,
        md_subtask: Subtask,
        existing_subtasks: dict,
        parent_key: str,
        project_key: str,
        story_id: str,
        result: SyncResult,
    ) -> None:
        """Sync a single subtask - update if exists, create if new."""

        subtask_name_lower = md_subtask.name.lower()

        try:
            if subtask_name_lower in existing_subtasks:
                self._update_existing_subtask(
                    md_subtask, existing_subtasks[subtask_name_lower], story_id, result
                )
            else:
                self._create_new_subtask(md_subtask, parent_key, project_key, story_id, result)
        except Exception as e:
            result.add_failed_operation(
                operation="sync_subtask",
                issue_key=parent_key,
                error=f"Unexpected error: {e}",
                story_id=story_id,
            )
            self.logger.exception(f"Unexpected error syncing subtask for {parent_key}")

    def _update_existing_subtask(
        self,
        md_subtask: Subtask,
        existing: IssueData,
        story_id: str,
        result: SyncResult,
    ) -> None:
        """Update an existing subtask."""
        update_cmd = UpdateSubtaskCommand(
            tracker=self.tracker,
            issue_key=existing.key,
            description=md_subtask.description,
            story_points=md_subtask.story_points,
            event_bus=self.event_bus,
            dry_run=self.config.dry_run,
        )
        update_result = update_cmd.execute()

        if update_result.success and not update_result.dry_run:
            result.subtasks_updated += 1
        elif not update_result.success and update_result.error:
            result.add_failed_operation(
                operation="update_subtask",
                issue_key=existing.key,
                error=update_result.error,
                story_id=story_id,
            )

    def _create_new_subtask(
        self,
        md_subtask: Subtask,
        parent_key: str,
        project_key: str,
        story_id: str,
        result: SyncResult,
    ) -> None:
        """Create a new subtask."""
        adf = self.formatter.format_text(md_subtask.description)

        create_cmd = CreateSubtaskCommand(
            tracker=self.tracker,
            parent_key=parent_key,
            project_key=project_key,
            summary=md_subtask.name,
            description=adf,
            story_points=md_subtask.story_points,
            event_bus=self.event_bus,
            dry_run=self.config.dry_run,
        )
        create_result = create_cmd.execute()

        if create_result.success:
            result.subtasks_created += 1
        elif create_result.error:
            result.add_failed_operation(
                operation="create_subtask",
                issue_key=parent_key,
                error=create_result.error,
                story_id=story_id,
            )

    def _sync_comments(self, result: SyncResult) -> None:
        """
        Add commit table comments to stories that have related commits.

        Skips stories that already have a "Related Commits" comment.
        Uses graceful degradation - failures don't stop processing.

        Args:
            result: SyncResult to update with operation counts and errors.
        """
        from spectra.core.ports.issue_tracker import IssueTrackerError

        for md_story in self._md_stories:
            story_id = str(md_story.id)
            if story_id not in self._matches:
                continue

            if not md_story.commits:
                continue

            # Skip unchanged stories in incremental mode
            if self.config.incremental and story_id not in self._changed_story_ids:
                continue

            issue_key = self._matches[story_id]

            try:
                # Check if commits comment already exists
                existing_comments = self.tracker.get_issue_comments(issue_key)
                has_commits_comment = any(
                    "Related Commits" in str(c.get("body", "")) for c in existing_comments
                )

                if has_commits_comment:
                    continue

                # Format commits as table
                adf = self.formatter.format_commits_table(md_story.commits)

                cmd = AddCommentCommand(
                    tracker=self.tracker,
                    issue_key=issue_key,
                    body=adf,
                    event_bus=self.event_bus,
                    dry_run=self.config.dry_run,
                )
                cmd_result = cmd.execute()

                if cmd_result.success:
                    result.comments_added += 1
                elif cmd_result.error:
                    result.add_failed_operation(
                        operation="add_comment",
                        issue_key=issue_key,
                        error=cmd_result.error,
                        story_id=story_id,
                    )

            except IssueTrackerError as e:
                result.add_failed_operation(
                    operation="add_comment",
                    issue_key=issue_key,
                    error=str(e),
                    story_id=story_id,
                )
                self.logger.warning(f"Failed to add comment to {issue_key}: {e}")
            except Exception as e:
                result.add_failed_operation(
                    operation="add_comment",
                    issue_key=issue_key,
                    error=f"Unexpected error: {e}",
                    story_id=story_id,
                )
                self.logger.exception(f"Unexpected error adding comment to {issue_key}")

    def _sync_statuses(self, result: SyncResult, target_status: str = "Resolved") -> None:
        """
        Transition subtask statuses based on markdown story status.

        Only processes stories that are marked as complete in markdown.
        Skips subtasks that are already in a resolved/done state.
        Uses graceful degradation - failures don't stop processing.

        Args:
            result: SyncResult to update with operation counts and errors.
            target_status: The status to transition subtasks to.
        """
        from spectra.core.ports.issue_tracker import IssueTrackerError

        for md_story in self._md_stories:
            story_id = str(md_story.id)
            if story_id not in self._matches:
                continue

            # Only sync done stories
            if not md_story.status.is_complete():
                continue

            # Skip unchanged stories in incremental mode
            if self.config.incremental and story_id not in self._changed_story_ids:
                continue

            issue_key = self._matches[story_id]

            try:
                jira_issue = self.tracker.get_issue(issue_key)
            except IssueTrackerError as e:
                result.add_failed_operation(
                    operation="fetch_issue",
                    issue_key=issue_key,
                    error=str(e),
                    story_id=story_id,
                )
                self.logger.warning(f"Failed to fetch issue {issue_key} for status sync: {e}")
                continue  # Skip this story but continue with others

            for jira_subtask in jira_issue.subtasks:
                if jira_subtask.status.lower() in ("resolved", "done", "closed"):
                    continue

                try:
                    cmd = TransitionStatusCommand(
                        tracker=self.tracker,
                        issue_key=jira_subtask.key,
                        target_status=target_status,
                        event_bus=self.event_bus,
                        dry_run=self.config.dry_run,
                    )
                    cmd_result = cmd.execute()

                    if cmd_result.success:
                        result.statuses_updated += 1
                    elif cmd_result.error:
                        result.add_failed_operation(
                            operation="transition_status",
                            issue_key=jira_subtask.key,
                            error=cmd_result.error,
                            story_id=story_id,
                        )

                except IssueTrackerError as e:
                    result.add_failed_operation(
                        operation="transition_status",
                        issue_key=jira_subtask.key,
                        error=str(e),
                        story_id=story_id,
                    )
                    self.logger.warning(f"Failed to transition {jira_subtask.key}: {e}")
                except Exception as e:
                    result.add_failed_operation(
                        operation="transition_status",
                        issue_key=jira_subtask.key,
                        error=f"Unexpected error: {e}",
                        story_id=story_id,
                    )
                    self.logger.exception(f"Unexpected error transitioning {jira_subtask.key}")

    # -------------------------------------------------------------------------
    # Resumable Sync
    # -------------------------------------------------------------------------

    def sync_resumable(
        self,
        markdown_path: str,
        epic_key: str,
        progress_callback: Callable[[str, int, int], None] | None = None,
        resume_state: SyncState | None = None,
    ) -> SyncResult:
        """
        Run a resumable sync with state persistence.

        Args:
            markdown_path: Path to markdown file.
            epic_key: Jira epic key.
            progress_callback: Optional progress callback.
            resume_state: Optional state to resume from.

        Returns:
            SyncResult with sync details.
        """
        from .state import SyncPhase, SyncState

        # Initialize or resume state
        if resume_state:
            self._state = resume_state
            self._matches = dict(self._state.matched_stories)
            self.logger.info(f"Resuming session {self._state.session_id}")
        else:
            session_id = SyncState.generate_session_id(markdown_path, epic_key)
            self._state = SyncState(
                session_id=session_id,
                markdown_path=markdown_path,
                epic_key=epic_key,
                dry_run=self.config.dry_run,
            )
            self.logger.debug(f"Starting session {session_id}")

        self._state.set_phase(SyncPhase.ANALYZING)
        self._save_state()

        # Run the normal sync
        result = self.sync(markdown_path, epic_key, progress_callback)

        # Update state with results
        self._state.matched_stories = result.matched_stories
        self._state.set_phase(SyncPhase.COMPLETED if result.success else SyncPhase.FAILED)
        self._save_state()

        return result

    def _save_state(self) -> None:
        """Save current state to the state store."""
        if self._state and self.state_store:
            self.state_store.save(self._state)

    @property
    def current_state(self) -> SyncState | None:
        """Get the current sync state."""
        return self._state

    @property
    def last_backup(self) -> Backup | None:
        """Get the last backup created during this sync."""
        return self._last_backup

    # -------------------------------------------------------------------------
    # Backup
    # -------------------------------------------------------------------------

    def _create_backup(self, markdown_path: str, epic_key: str) -> Backup | None:
        """
        Create a backup of the current Jira state before modifications.

        Args:
            markdown_path: Path to the markdown file.
            epic_key: Jira epic key.

        Returns:
            The created Backup, or None if backup is disabled or failed.
        """
        from .backup import BackupManager

        if not self.config.backup_enabled:
            return None

        # Use provided backup manager or create one
        if self.backup_manager:
            manager = self.backup_manager
        else:
            backup_dir = Path(self.config.backup_dir) if self.config.backup_dir else None
            manager = BackupManager(
                backup_dir=backup_dir,
                max_backups=self.config.backup_max_count,
                retention_days=self.config.backup_retention_days,
            )

        self.logger.info(f"Creating pre-sync backup for {epic_key}")

        backup = manager.create_backup(
            tracker=self.tracker,
            epic_key=epic_key,
            markdown_path=markdown_path,
            metadata={
                "trigger": "pre_sync",
                "dry_run": self.config.dry_run,
            },
        )

        self._last_backup = backup
        self.logger.info(f"Backup created: {backup.backup_id} ({backup.issue_count} issues)")

        return backup

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _report_progress(
        self, callback: Callable | None, phase: str, current: int, total: int
    ) -> None:
        """Report progress to callback if provided."""
        if callback:
            callback(phase, current, total)
        self.logger.debug(f"Phase {current}/{total}: {phase}")
