"""
Sync Orchestrator - Coordinates the synchronization process.

This is the main entry point for sync operations.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ...core.ports.issue_tracker import IssueTrackerPort, IssueData
from ...core.ports.document_parser import DocumentParserPort
from ...core.ports.document_formatter import DocumentFormatterPort
from ...core.ports.config_provider import SyncConfig
from ...core.domain.entities import Epic, UserStory, Subtask
from ...core.domain.events import EventBus, SyncStarted, SyncCompleted
from ..commands import (
    CommandBatch,
    UpdateDescriptionCommand,
    CreateSubtaskCommand,
    UpdateSubtaskCommand,
    AddCommentCommand,
    TransitionStatusCommand,
)


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
    """
    
    success: bool = True
    dry_run: bool = True
    
    # Counts
    stories_matched: int = 0
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
            self.stories_updated > 0 or
            self.subtasks_created > 0 or
            self.subtasks_updated > 0 or
            self.comments_added > 0 or
            self.statuses_updated > 0
        )
        has_failures = len(self.failed_operations) > 0
        return has_successes and has_failures
    
    @property
    def total_operations(self) -> int:
        """Total number of operations attempted."""
        return (
            self.stories_updated +
            self.subtasks_created +
            self.subtasks_updated +
            self.comments_added +
            self.statuses_updated +
            len(self.failed_operations)
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
        event_bus: Optional[EventBus] = None,
    ):
        """
        Initialize the orchestrator.
        
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
        self.logger = logging.getLogger("SyncOrchestrator")
        
        self._md_stories: list[UserStory] = []
        self._jira_issues: list[IssueData] = []
        self._matches: dict[str, str] = {}  # story_id -> issue_key
    
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
        self.logger.info(f"Parsed {len(self._md_stories)} stories from markdown")
        
        # Fetch Jira issues
        self._jira_issues = self.tracker.get_epic_children(epic_key)
        self.logger.info(f"Found {len(self._jira_issues)} issues in Jira epic")
        
        # Match stories
        self._match_stories(result)
        
        return result
    
    def sync(
        self,
        markdown_path: str,
        epic_key: str,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
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
        self.event_bus.publish(SyncStarted(
            epic_key=epic_key,
            markdown_path=markdown_path,
            dry_run=self.config.dry_run,
        ))
        
        # Phase 1: Analyze
        self._report_progress(progress_callback, "Analyzing", 1, 5)
        self.analyze(markdown_path, epic_key)
        result.stories_matched = len(self._matches)
        result.matched_stories = list(self._matches.items())
        
        # Phase 2: Update descriptions
        if self.config.sync_descriptions:
            self._report_progress(progress_callback, "Updating descriptions", 2, 5)
            self._sync_descriptions(result)
        
        # Phase 3: Sync subtasks
        if self.config.sync_subtasks:
            self._report_progress(progress_callback, "Syncing subtasks", 3, 5)
            self._sync_subtasks(result)
        
        # Phase 4: Add commit comments
        if self.config.sync_comments:
            self._report_progress(progress_callback, "Adding comments", 4, 5)
            self._sync_comments(result)
        
        # Phase 5: Sync statuses
        if self.config.sync_statuses:
            self._report_progress(progress_callback, "Syncing statuses", 5, 5)
            self._sync_statuses(result)
        
        # Publish complete event
        self.event_bus.publish(SyncCompleted(
            epic_key=epic_key,
            stories_matched=result.stories_matched,
            stories_updated=result.stories_updated,
            subtasks_created=result.subtasks_created,
            comments_added=result.comments_added,
            errors=result.errors,
        ))
        
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
        from ...core.ports.issue_tracker import IssueTrackerError
        
        for md_story in self._md_stories:
            story_id = str(md_story.id)
            if story_id not in self._matches:
                continue
            
            issue_key = self._matches[story_id]
            project_key = issue_key.split("-")[0]
            
            # Get existing subtasks - wrap in try/except for graceful degradation
            try:
                jira_issue = self.tracker.get_issue(issue_key)
                existing_subtasks = {st.summary.lower(): st for st in jira_issue.subtasks}
            except IssueTrackerError as e:
                result.add_failed_operation(
                    operation="fetch_issue",
                    issue_key=issue_key,
                    error=str(e),
                    story_id=story_id,
                )
                self.logger.warning(f"Failed to fetch issue {issue_key}, skipping subtasks: {e}")
                continue  # Skip this story's subtasks but continue with others
            
            for md_subtask in md_story.subtasks:
                subtask_name_lower = md_subtask.name.lower()
                
                try:
                    if subtask_name_lower in existing_subtasks:
                        # Update existing subtask
                        existing = existing_subtasks[subtask_name_lower]
                        
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
                    else:
                        # Create new subtask
                        adf = self.formatter.format_text(md_subtask.description)
                        
                        create_cmd = CreateSubtaskCommand(
                            tracker=self.tracker,
                            parent_key=issue_key,
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
                                issue_key=issue_key,
                                error=create_result.error,
                                story_id=story_id,
                            )
                            
                except Exception as e:
                    # Catch any unexpected errors and continue
                    result.add_failed_operation(
                        operation="sync_subtask",
                        issue_key=issue_key,
                        error=f"Unexpected error: {e}",
                        story_id=story_id,
                    )
                    self.logger.exception(f"Unexpected error syncing subtask for {issue_key}")
    
    def _sync_comments(self, result: SyncResult) -> None:
        """
        Add commit table comments to stories that have related commits.
        
        Skips stories that already have a "Related Commits" comment.
        Uses graceful degradation - failures don't stop processing.
        
        Args:
            result: SyncResult to update with operation counts and errors.
        """
        from ...core.ports.issue_tracker import IssueTrackerError
        
        for md_story in self._md_stories:
            story_id = str(md_story.id)
            if story_id not in self._matches:
                continue
            
            if not md_story.commits:
                continue
            
            issue_key = self._matches[story_id]
            
            try:
                # Check if commits comment already exists
                existing_comments = self.tracker.get_issue_comments(issue_key)
                has_commits_comment = any(
                    "Related Commits" in str(c.get("body", ""))
                    for c in existing_comments
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
    
    def _sync_statuses(
        self,
        result: SyncResult,
        target_status: str = "Resolved"
    ) -> None:
        """
        Transition subtask statuses based on markdown story status.
        
        Only processes stories that are marked as complete in markdown.
        Skips subtasks that are already in a resolved/done state.
        Uses graceful degradation - failures don't stop processing.
        
        Args:
            result: SyncResult to update with operation counts and errors.
            target_status: The status to transition subtasks to.
        """
        from ...core.ports.issue_tracker import IssueTrackerError
        
        for md_story in self._md_stories:
            story_id = str(md_story.id)
            if story_id not in self._matches:
                continue
            
            # Only sync done stories
            if not md_story.status.is_complete():
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
    # Helpers
    # -------------------------------------------------------------------------
    
    def _report_progress(
        self,
        callback: Optional[Callable],
        phase: str,
        current: int,
        total: int
    ) -> None:
        """Report progress to callback if provided."""
        if callback:
            callback(phase, current, total)
        self.logger.info(f"Phase {current}/{total}: {phase}")

