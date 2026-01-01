"""
Issue Commands - Commands for issue tracker operations.
"""

from dataclasses import dataclass
from typing import Any

from spectra.core.domain.events import (
    CommentAdded,
    EventBus,
    StatusTransitioned,
    StoryUpdated,
    SubtaskCreated,
)
from spectra.core.ports.issue_tracker import IssueTrackerError, IssueTrackerPort

from .base import Command, CommandResult


@dataclass
class UpdateDescriptionCommand(Command):
    """Update an issue's description.

    This command updates the description field of an issue in the tracker.
    It supports undo by storing the original description before modification.

    Attributes:
        issue_key: The unique identifier of the issue (e.g., "PROJ-123").
        description: The new description content (markdown string or ADF).

    Example:
        >>> cmd = UpdateDescriptionCommand(
        ...     tracker=tracker,
        ...     issue_key="PROJ-123",
        ...     description="# New Description\n\nUpdated content.",
        ... )
        >>> result = cmd.execute()
    """

    issue_key: str = ""
    description: Any = None  # Can be markdown string or ADF

    def __init__(
        self,
        tracker: IssueTrackerPort,
        issue_key: str,
        description: Any,
        event_bus: EventBus | None = None,
        dry_run: bool = True,
    ):
        super().__init__(tracker, event_bus, dry_run)
        self.issue_key = issue_key
        self.description = description

    @property
    def name(self) -> str:
        return f"UpdateDescription({self.issue_key})"

    @property
    def supports_undo(self) -> bool:
        return True

    def validate(self) -> str | None:
        if not self.issue_key:
            return "Issue key is required"
        if not self.description:
            return "Description is required"
        return None

    def execute(self) -> CommandResult[bool]:
        error = self.validate()
        if error:
            return CommandResult.fail(error)

        try:
            if self.dry_run:
                return CommandResult.ok(True, dry_run=True)

            # Store current description for undo
            current = self.tracker.get_issue(self.issue_key)
            self._undo_data = current.description

            # Update description
            success = self.tracker.update_issue_description(self.issue_key, self.description)

            if success:
                self._publish_event(
                    StoryUpdated(
                        issue_key=self.issue_key,
                        field_name="description",
                    )
                )

            return CommandResult.ok(success)

        except IssueTrackerError as e:
            return CommandResult.fail(str(e))

    def undo(self) -> CommandResult[bool] | None:
        if self._undo_data is None:
            return None

        try:
            success = self.tracker.update_issue_description(self.issue_key, self._undo_data)
            return CommandResult.ok(success)
        except IssueTrackerError as e:
            return CommandResult.fail(str(e))


@dataclass
class CreateSubtaskCommand(Command):
    """Create a subtask under a parent issue.

    Creates a new subtask (child issue) linked to a parent story or issue.
    The subtask inherits the project context from the parent.

    Attributes:
        parent_key: The issue key of the parent (e.g., "PROJ-123").
        project_key: The project key for the new subtask.
        summary: The title/summary of the subtask.
        description: Optional description content.
        story_points: Optional story point estimate.
        assignee: Optional username to assign the subtask to.
        priority: Optional priority level.

    Example:
        >>> cmd = CreateSubtaskCommand(
        ...     tracker=tracker,
        ...     parent_key="PROJ-123",
        ...     project_key="PROJ",
        ...     summary="Implement login form",
        ...     story_points=2,
        ... )
        >>> result = cmd.execute()
        >>> if result.success:
        ...     new_key = result.data  # e.g., "PROJ-456"
    """

    parent_key: str = ""
    project_key: str = ""
    summary: str = ""
    description: Any = None
    story_points: int | None = None
    assignee: str | None = None
    priority: str | None = None

    def __init__(
        self,
        tracker: IssueTrackerPort,
        parent_key: str,
        project_key: str,
        summary: str,
        description: Any = None,
        story_points: int | None = None,
        assignee: str | None = None,
        priority: str | None = None,
        event_bus: EventBus | None = None,
        dry_run: bool = True,
    ):
        super().__init__(tracker, event_bus, dry_run)
        self.parent_key = parent_key
        self.project_key = project_key
        self.summary = summary
        self.description = description
        self.story_points = story_points
        self.assignee = assignee
        self.priority = priority

    @property
    def name(self) -> str:
        return f"CreateSubtask({self.parent_key}, '{self.summary[:30]}...')"

    def validate(self) -> str | None:
        if not self.parent_key:
            return "Parent issue key is required"
        if not self.project_key:
            return "Project key is required"
        if not self.summary:
            return "Summary is required"
        return None

    def execute(self) -> CommandResult[str]:
        error = self.validate()
        if error:
            return CommandResult.fail(error)

        try:
            if self.dry_run:
                return CommandResult.ok("[DRY-RUN] Would create subtask", dry_run=True)

            new_key = self.tracker.create_subtask(
                parent_key=self.parent_key,
                summary=self.summary,
                description=self.description or "",
                project_key=self.project_key,
                story_points=self.story_points,
                assignee=self.assignee,
                priority=self.priority,
            )

            if new_key:
                self._undo_data = new_key
                self._publish_event(
                    SubtaskCreated(
                        parent_key=self.parent_key,
                        subtask_key=new_key,
                        subtask_name=self.summary,
                        story_points=self.story_points or 0,
                    )
                )
                return CommandResult.ok(new_key)

            return CommandResult.fail("Failed to create subtask")

        except IssueTrackerError as e:
            return CommandResult.fail(str(e))


@dataclass
class UpdateSubtaskCommand(Command):
    """Update an existing subtask.

    Updates one or more fields on an existing subtask. At least one field
    must be provided for the update.

    Attributes:
        issue_key: The subtask's issue key (e.g., "PROJ-456").
        description: Optional new description content.
        story_points: Optional new story point estimate.
        assignee: Optional new assignee username.
        priority_id: Optional new priority ID.

    Example:
        >>> cmd = UpdateSubtaskCommand(
        ...     tracker=tracker,
        ...     issue_key="PROJ-456",
        ...     story_points=3,
        ...     assignee="jdoe",
        ... )
        >>> result = cmd.execute()
    """

    issue_key: str = ""
    description: Any | None = None
    story_points: int | None = None
    assignee: str | None = None
    priority_id: str | None = None

    def __init__(
        self,
        tracker: IssueTrackerPort,
        issue_key: str,
        description: Any | None = None,
        story_points: int | None = None,
        assignee: str | None = None,
        priority_id: str | None = None,
        event_bus: EventBus | None = None,
        dry_run: bool = True,
    ):
        super().__init__(tracker, event_bus, dry_run)
        self.issue_key = issue_key
        self.description = description
        self.story_points = story_points
        self.assignee = assignee
        self.priority_id = priority_id

    @property
    def name(self) -> str:
        return f"UpdateSubtask({self.issue_key})"

    def validate(self) -> str | None:
        if not self.issue_key:
            return "Issue key is required"
        if not any([self.description, self.story_points, self.assignee, self.priority_id]):
            return "At least one field to update is required"
        return None

    def execute(self) -> CommandResult[bool]:
        error = self.validate()
        if error:
            return CommandResult.fail(error)

        try:
            # Always call tracker - it handles dry-run with proper value comparison
            success = self.tracker.update_subtask(
                issue_key=self.issue_key,
                description=self.description,
                story_points=self.story_points,
                assignee=self.assignee,
                priority_id=self.priority_id,
            )

            return CommandResult.ok(success, dry_run=self.dry_run)

        except IssueTrackerError as e:
            return CommandResult.fail(str(e))


@dataclass
class AddCommentCommand(Command):
    """Add a comment to an issue.

    Adds a new comment to an existing issue. The comment body can be
    plain text, markdown, or ADF (Atlassian Document Format) depending
    on the tracker's requirements.

    Attributes:
        issue_key: The issue key to comment on (e.g., "PROJ-123").
        body: The comment content (text, markdown, or ADF).

    Example:
        >>> cmd = AddCommentCommand(
        ...     tracker=tracker,
        ...     issue_key="PROJ-123",
        ...     body="This has been reviewed and approved.",
        ... )
        >>> result = cmd.execute()
    """

    issue_key: str = ""
    body: Any = None

    def __init__(
        self,
        tracker: IssueTrackerPort,
        issue_key: str,
        body: Any,
        event_bus: EventBus | None = None,
        dry_run: bool = True,
    ):
        super().__init__(tracker, event_bus, dry_run)
        self.issue_key = issue_key
        self.body = body

    @property
    def name(self) -> str:
        return f"AddComment({self.issue_key})"

    def validate(self) -> str | None:
        if not self.issue_key:
            return "Issue key is required"
        if not self.body:
            return "Comment body is required"
        return None

    def execute(self) -> CommandResult[bool]:
        error = self.validate()
        if error:
            return CommandResult.fail(error)

        try:
            if self.dry_run:
                return CommandResult.ok(True, dry_run=True)

            success = self.tracker.add_comment(self.issue_key, self.body)

            if success:
                self._publish_event(
                    CommentAdded(
                        issue_key=self.issue_key,
                        comment_type="text",
                    )
                )

            return CommandResult.ok(success)

        except IssueTrackerError as e:
            return CommandResult.fail(str(e))


@dataclass
class TransitionStatusCommand(Command):
    """Transition an issue to a new status.

    Executes a workflow transition to move an issue to a new status.
    The available transitions depend on the issue's current status and
    the tracker's workflow configuration.

    Supports undo by storing the original status and reversing the
    transition (if the workflow allows).

    Attributes:
        issue_key: The issue key to transition (e.g., "PROJ-123").
        target_status: The desired status name (e.g., "In Progress", "Done").

    Example:
        >>> cmd = TransitionStatusCommand(
        ...     tracker=tracker,
        ...     issue_key="PROJ-123",
        ...     target_status="In Progress",
        ... )
        >>> result = cmd.execute()
        >>> # Later, undo the transition:
        >>> cmd.undo()  # Returns to original status
    """

    issue_key: str = ""
    target_status: str = ""

    def __init__(
        self,
        tracker: IssueTrackerPort,
        issue_key: str,
        target_status: str,
        event_bus: EventBus | None = None,
        dry_run: bool = True,
    ):
        super().__init__(tracker, event_bus, dry_run)
        self.issue_key = issue_key
        self.target_status = target_status

    @property
    def name(self) -> str:
        return f"TransitionStatus({self.issue_key} -> {self.target_status})"

    @property
    def supports_undo(self) -> bool:
        return True

    def validate(self) -> str | None:
        if not self.issue_key:
            return "Issue key is required"
        if not self.target_status:
            return "Target status is required"
        return None

    def execute(self) -> CommandResult[bool]:
        error = self.validate()
        if error:
            return CommandResult.fail(error)

        try:
            # Get current status for undo
            self._undo_data = self.tracker.get_issue_status(self.issue_key)

            if self.dry_run:
                return CommandResult.ok(True, dry_run=True)

            success = self.tracker.transition_issue(self.issue_key, self.target_status)

            if success:
                self._publish_event(
                    StatusTransitioned(
                        issue_key=self.issue_key,
                        from_status=self._undo_data,
                        to_status=self.target_status,
                    )
                )

            return CommandResult.ok(success)

        except IssueTrackerError as e:
            return CommandResult.fail(str(e))

    def undo(self) -> CommandResult[bool] | None:
        if self._undo_data is None:
            return None

        try:
            success = self.tracker.transition_issue(self.issue_key, self._undo_data)
            return CommandResult.ok(success)
        except IssueTrackerError as e:
            return CommandResult.fail(str(e))
