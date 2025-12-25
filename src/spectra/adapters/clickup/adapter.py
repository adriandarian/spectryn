"""
ClickUp Adapter - Implements IssueTrackerPort for ClickUp.

This is the main entry point for ClickUp integration.
Maps the generic IssueTrackerPort interface to ClickUp's task model.

Key mappings:
- Epic -> Goal or Folder
- Story -> Task
- Subtask -> Subtask or Checklist item
- Status -> Status (custom statuses)
- Priority -> Priority
- Story Points -> Story points field
"""

import logging
from typing import Any

from spectra.core.domain.enums import Priority
from spectra.core.ports.issue_tracker import (
    IssueData,
    IssueLink,
    IssueTrackerError,
    IssueTrackerPort,
    LinkType,
    NotFoundError,
    TransitionError,
)

from .client import ClickUpApiClient


class ClickUpAdapter(IssueTrackerPort):
    """
    ClickUp implementation of the IssueTrackerPort.

    Translates between domain entities and ClickUp's REST API v2.

    ClickUp concepts:
    - Space: Top-level container (like a workspace)
    - Folder: Collection of lists (can represent an epic)
    - List: Collection of tasks (like a project board)
    - Task: Work item (like a story)
    - Subtask: Child task (like a subtask)
    - Checklist: List of items within a task (alternative to subtasks)
    - Goal: High-level objective (can represent an epic)
    - Status: Custom statuses per list
    - Priority: Urgent, High, Normal, Low
    """

    def __init__(
        self,
        api_token: str,
        space_id: str | None = None,
        folder_id: str | None = None,
        list_id: str | None = None,
        dry_run: bool = True,
        api_url: str = "https://api.clickup.com/api/v2",
    ):
        """
        Initialize the ClickUp adapter.

        Args:
            api_token: ClickUp API token
            space_id: Optional space ID to scope operations
            folder_id: Optional folder ID to scope operations
            list_id: Optional list ID to scope operations
            dry_run: If True, don't make changes
            api_url: ClickUp API URL
        """
        self._dry_run = dry_run
        self.space_id = space_id
        self.folder_id = folder_id
        self.list_id = list_id
        self.logger = logging.getLogger("ClickUpAdapter")

        # API client
        self._client = ClickUpApiClient(
            api_token=api_token,
            api_url=api_url,
            dry_run=dry_run,
        )

        # Cache for statuses and priorities
        self._statuses_cache: dict[str, list[dict]] = {}  # list_id -> statuses
        self._priority_map: dict[str, int] = {
            "urgent": 1,
            "high": 2,
            "normal": 3,
            "low": 4,
        }

    def _get_list_id(self) -> str:
        """Get the list ID, raising error if not configured."""
        if self.list_id:
            return self.list_id
        raise IssueTrackerError(
            "List ID not configured. Set CLICKUP_LIST_ID or provide list_id parameter."
        )

    def _get_statuses(self, list_id: str | None = None) -> list[dict[str, Any]]:
        """Get statuses for a list, caching the result."""
        target_list_id = list_id or self._get_list_id()
        if target_list_id not in self._statuses_cache:
            statuses = self._client.get_list_statuses(target_list_id)
            self._statuses_cache[target_list_id] = statuses
        return self._statuses_cache[target_list_id]

    def _find_status(self, status_name: str, list_id: str | None = None) -> dict | None:
        """Find a status by name (case-insensitive)."""
        statuses = self._get_statuses(list_id)
        status_name_lower = status_name.lower()

        # Try exact match first
        for status in statuses:
            if status.get("status", "").lower() == status_name_lower:
                return status

        # Try partial match
        for status in statuses:
            status_text = status.get("status", "").lower()
            if status_name_lower in status_text or status_text in status_name_lower:
                return status

        # Try mapping common status names
        status_mapping = {
            "done": ["complete", "closed", "resolved"],
            "in progress": ["in progress", "working", "active"],
            "open": ["open", "to do", "todo", "backlog"],
            "planned": ["planned", "backlog"],
        }

        for target, aliases in status_mapping.items():
            if status_name_lower in aliases or any(alias in status_name_lower for alias in aliases):
                for status in statuses:
                    if target in status.get("status", "").lower():
                        return status

        return None

    def _map_priority_to_clickup(self, priority: str | None) -> int | None:
        """Map priority string to ClickUp priority value."""
        if not priority:
            return None

        priority_enum = Priority.from_string(priority)

        if priority_enum == Priority.CRITICAL:
            return 1  # Urgent
        if priority_enum == Priority.HIGH:
            return 2  # High
        if priority_enum == Priority.LOW:
            return 4  # Low
        return 3  # Normal (default)

    def _map_clickup_priority(self, priority: int | None) -> str:
        """Map ClickUp priority value to priority string."""
        if priority is None:
            return "Medium"

        priority_map = {
            1: "Critical",  # Urgent
            2: "High",
            3: "Medium",  # Normal
            4: "Low",
        }
        return priority_map.get(priority, "Medium")

    def _extract_story_points(self, task: dict[str, Any]) -> float | None:
        """Extract story points from task custom fields."""
        custom_fields = task.get("custom_fields", [])
        for field in custom_fields:
            field_name = field.get("name", "").lower()
            if "story point" in field_name or "point" in field_name:
                value = field.get("value")
                if value is not None:
                    try:
                        return float(value)
                    except (ValueError, TypeError):
                        pass
        return None

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Properties
    # -------------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "ClickUp"

    @property
    def is_connected(self) -> bool:
        return self._client.is_connected

    def test_connection(self) -> bool:
        if not self._client.test_connection():
            return False
        # Also verify list access if configured
        if self.list_id:
            try:
                self._client.get_list(self.list_id)
                return True
            except IssueTrackerError:
                return False
        return True

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Read Operations
    # -------------------------------------------------------------------------

    def get_current_user(self) -> dict[str, Any]:
        return self._client.get_user()

    def get_issue(self, issue_key: str) -> IssueData:
        """
        Fetch a single issue by key.

        Args:
            issue_key: Task ID (e.g., 'abc123' or full task ID)
        """
        try:
            task = self._client.get_task(issue_key)
            return self._parse_task(task)
        except NotFoundError:
            # Try as goal (epic)
            try:
                goal = self._client.get_goal(issue_key)
                return self._parse_goal(goal)
            except NotFoundError:
                raise NotFoundError(f"Issue not found: {issue_key}")

    def get_epic_children(self, epic_key: str) -> list[IssueData]:
        """
        Fetch all children of an epic.

        In ClickUp, epics can be represented as Goals or Folders.
        We try both approaches.
        """
        children: list[IssueData] = []

        # Try as goal first
        try:
            self._client.get_goal(epic_key)
            # Goals don't directly have tasks, but we can search for tasks
            # with the goal reference. For now, return empty list.
            # In a real implementation, you'd query tasks linked to the goal.
            return []
        except NotFoundError:
            pass

        # Try as folder
        try:
            self._client.get_folder(epic_key)
            lists = self._client.get_lists(folder_id=epic_key)
            for list_data in lists:
                tasks = self._client.get_tasks(list_id=list_data["id"])
                children.extend([self._parse_task(task) for task in tasks])
            return children
        except NotFoundError:
            pass

        # Try as parent task
        try:
            self._client.get_task(epic_key)
            subtasks = self._client.get_subtasks(epic_key)
            return [self._parse_task(subtask) for subtask in subtasks]
        except NotFoundError:
            return []

    def get_issue_comments(self, issue_key: str) -> list[dict]:
        """Get all comments on an issue."""
        comments = self._client.get_comments(issue_key)
        return [
            {
                "id": comment.get("id"),
                "body": comment.get("comment", [{}])[0].get("text", ""),
                "author": comment.get("user", {}).get("username"),
                "created": comment.get("date"),
            }
            for comment in comments
        ]

    def get_issue_status(self, issue_key: str) -> str:
        """Get the current status of an issue."""
        task = self._client.get_task(issue_key)
        status_obj = task.get("status", {})
        return status_obj.get("status", "Unknown")  # type: ignore[no-any-return]

    def search_issues(self, query: str, max_results: int = 50) -> list[IssueData]:
        """
        Search for issues.

        ClickUp doesn't have a unified search API, so we search within
        the configured list/folder/space.
        """
        tasks: list[dict[str, Any]] = []

        if self.list_id:
            tasks = self._client.get_tasks(list_id=self.list_id)
        elif self.folder_id:
            tasks = self._client.get_tasks(folder_id=self.folder_id)
        elif self.space_id:
            tasks = self._client.get_tasks(space_id=self.space_id)
        else:
            self.logger.warning("No scope configured for search")
            return []

        # Simple text filtering (ClickUp API doesn't support full-text search)
        filtered_tasks = [
            task
            for task in tasks[:max_results]
            if query.lower() in task.get("name", "").lower()
            or query.lower() in task.get("description", "").lower()
        ]

        return [self._parse_task(task) for task in filtered_tasks]

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Write Operations
    # -------------------------------------------------------------------------

    def update_issue_description(self, issue_key: str, description: Any) -> bool:
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would update description for {issue_key}")
            return True

        desc_str = description if isinstance(description, str) else str(description)
        self._client.update_task(issue_key, description=desc_str)
        self.logger.info(f"Updated description for {issue_key}")
        return True

    def update_issue_story_points(self, issue_key: str, story_points: float) -> bool:
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would update story points for {issue_key} to {story_points}"
            )
            return True

        # ClickUp uses custom fields for story points
        # We need to find the story points field and update it
        task = self._client.get_task(issue_key)
        custom_fields = task.get("custom_fields", [])

        # Find story points field
        story_points_field = None
        for field in custom_fields:
            field_name = field.get("name", "").lower()
            if "story point" in field_name or "point" in field_name:
                story_points_field = field
                break

        if story_points_field:
            field_id = story_points_field.get("id")
            updated_fields = [
                {
                    "id": field_id,
                    "value": int(story_points),
                }
            ]
            self._client.update_task(issue_key, custom_fields=updated_fields)
            self.logger.info(f"Updated story points for {issue_key} to {story_points}")
        else:
            self.logger.warning(f"Story points field not found for {issue_key}, skipping update")

        return True

    def create_subtask(
        self,
        parent_key: str,
        summary: str,
        description: Any,
        project_key: str,
        story_points: int | None = None,
        assignee: str | None = None,
        priority: str | None = None,
    ) -> str | None:
        """
        Create a subtask under a parent issue.

        In ClickUp, subtasks are regular tasks with a parent reference.
        """
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would create subtask '{summary[:50]}...' under {parent_key}"
            )
            return None

        # Get parent task to find its list_id
        parent_task = self._client.get_task(parent_key)
        list_id = parent_task.get("list", {}).get("id")
        if not list_id:
            raise IssueTrackerError(f"Parent task {parent_key} has no list ID")

        desc_str = description if isinstance(description, str) else str(description)
        priority_value = self._map_priority_to_clickup(priority)

        result = self._client.create_subtask(
            list_id=list_id,
            parent_task_id=parent_key,
            name=summary[:255],
            description=desc_str,
            status=None,  # Use default status
        )

        task_id: str | None = result.get("id")
        if task_id:
            # Update story points if provided
            if story_points is not None:
                self.update_issue_story_points(task_id, float(story_points))

            # Update priority if provided
            if priority_value is not None:
                self._client.update_task(task_id, priority=priority_value)

            # Update assignee if provided
            if assignee:
                self._client.update_task(task_id, assignees={"add": [assignee], "rem": []})

            self.logger.info(f"Created subtask {task_id} under {parent_key}")
            return task_id  # type: ignore[return-value]

        return None

    def update_subtask(
        self,
        issue_key: str,
        description: Any | None = None,
        story_points: int | None = None,
        assignee: str | None = None,
        priority_id: str | None = None,
    ) -> bool:
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would update subtask {issue_key}")
            return True

        updates: dict[str, Any] = {}

        if description is not None:
            updates["description"] = (
                description if isinstance(description, str) else str(description)
            )

        if story_points is not None:
            # Update story points via custom field
            self.update_issue_story_points(issue_key, float(story_points))

        if assignee is not None:
            updates["assignees"] = {"add": [assignee], "rem": []}

        if priority_id is not None:
            # priority_id is a string, but ClickUp expects int
            from contextlib import suppress

            with suppress(ValueError):
                updates["priority"] = int(priority_id)

        if updates:
            self._client.update_task(issue_key, **updates)
            self.logger.info(f"Updated subtask {issue_key}")

        return True

    def add_comment(self, issue_key: str, body: Any) -> bool:
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would add comment to {issue_key}")
            return True

        comment_body = body if isinstance(body, str) else str(body)
        self._client.add_comment(issue_key, comment_body)
        self.logger.info(f"Added comment to {issue_key}")
        return True

    def transition_issue(self, issue_key: str, target_status: str) -> bool:
        """
        Transition an issue to a new status.

        ClickUp uses custom statuses per list, so we need to find
        the matching status in the task's list.
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would transition {issue_key} to {target_status}")
            return True

        # Get task to find its list_id
        task = self._client.get_task(issue_key)
        list_id = task.get("list", {}).get("id")
        if not list_id:
            raise TransitionError(f"Task {issue_key} has no list ID", issue_key=issue_key)

        target_status_obj = self._find_status(target_status, list_id=list_id)
        if not target_status_obj:
            available_statuses = [s.get("status") for s in self._get_statuses(list_id)]
            raise TransitionError(
                f"Status not found: {target_status}. Available statuses: {available_statuses}",
                issue_key=issue_key,
            )

        try:
            status_value = target_status_obj.get("status")
            self._client.update_task(issue_key, status=status_value)
            self.logger.info(f"Transitioned {issue_key} to {status_value}")
            return True
        except IssueTrackerError as e:
            raise TransitionError(
                f"Failed to transition {issue_key} to {target_status}: {e}",
                issue_key=issue_key,
                cause=e,
            )

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Utility
    # -------------------------------------------------------------------------

    def get_available_transitions(self, issue_key: str) -> list[dict]:
        """
        Get available transitions (statuses) for an issue.

        In ClickUp, any task can transition to any status in its list.
        """
        task = self._client.get_task(issue_key)
        list_id = task.get("list", {}).get("id")
        if not list_id:
            return []

        statuses = self._get_statuses(list_id=list_id)
        return [
            {
                "id": status.get("status"),
                "name": status.get("status"),
                "type": status.get("type", ""),
            }
            for status in statuses
        ]

    def format_description(self, markdown: str) -> Any:
        """
        Convert markdown to ClickUp-compatible format.

        ClickUp uses Markdown natively, so we just return the input.
        """
        return markdown

    # -------------------------------------------------------------------------
    # Private Methods
    # -------------------------------------------------------------------------

    def _parse_task(self, data: dict) -> IssueData:
        """Parse ClickUp task API response into IssueData."""
        task_id = data.get("id", "")
        name = data.get("name", "")
        description = data.get("description", "")

        # Get status
        status_obj = data.get("status", {})
        status = status_obj.get("status", "Unknown")

        # Get assignee
        assignee = None
        assignees = data.get("assignees", [])
        if assignees:
            assignee = assignees[0].get("username") or assignees[0].get("email")

        # Get story points
        story_points = self._extract_story_points(data)

        # Parse subtasks
        subtasks = []
        for subtask in data.get("subtasks", []):
            subtasks.append(
                IssueData(
                    key=subtask.get("id", ""),
                    summary=subtask.get("name", ""),
                    status=subtask.get("status", {}).get("status", ""),
                    issue_type="Sub-task",
                )
            )

        # Parse comments
        comments = []
        for comment in data.get("comments", []):
            comments.append(
                {
                    "id": comment.get("id"),
                    "body": comment.get("comment", [{}])[0].get("text", ""),
                    "author": comment.get("user", {}).get("username"),
                    "created": comment.get("date"),
                }
            )

        # Determine issue type
        has_parent = data.get("parent") is not None
        issue_type = "Sub-task" if has_parent else "Story"

        return IssueData(
            key=task_id,
            summary=name,
            description=description,
            status=status,
            issue_type=issue_type,
            assignee=assignee,
            story_points=story_points,
            subtasks=subtasks,
            comments=comments,
        )

    def _parse_goal(self, data: dict) -> IssueData:
        """Parse ClickUp goal API response into IssueData."""
        goal_id = data.get("id", "")
        name = data.get("name", "")
        description = data.get("description", "")

        return IssueData(
            key=goal_id,
            summary=name,
            description=description,
            status="Active",  # Goals don't have statuses like tasks
            issue_type="Epic",
        )

    # -------------------------------------------------------------------------
    # Webhook Methods
    # -------------------------------------------------------------------------

    def create_webhook(
        self,
        endpoint: str,
        team_id: str | None = None,
        client_id: str | None = None,
        events: list[str] | None = None,
        task_id: str | None = None,
        list_id: str | None = None,
        folder_id: str | None = None,
        space_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a webhook subscription.

        ClickUp webhooks notify when changes occur to tasks, lists, folders, or spaces.
        You can subscribe to specific events or all events.

        Supported events include:
        - taskCreated, taskUpdated, taskDeleted
        - taskStatusUpdated, taskPriorityUpdated, taskAssigneeUpdated
        - taskCommentPosted, taskCommentUpdated, taskCommentDeleted
        - taskTimeTracked, taskTimeDeleted
        - listCreated, listUpdated, listDeleted
        - folderCreated, folderUpdated, folderDeleted
        - spaceCreated, spaceUpdated, spaceDeleted

        Args:
            endpoint: Webhook URL to receive events
            team_id: Team ID (required if not using space/folder/list scope)
            client_id: Optional client ID for webhook authentication
            events: Optional list of event types (defaults to all events)
            task_id: Optional task ID to watch (for task-specific webhooks)
            list_id: Optional list ID to watch (defaults to configured list_id)
            folder_id: Optional folder ID to watch (defaults to configured folder_id)
            space_id: Optional space ID to watch (defaults to configured space_id)

        Returns:
            Webhook subscription data

        Raises:
            IssueTrackerError: If team_id is required but not provided
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would create webhook for endpoint {endpoint}")
            return {
                "id": "webhook:dry-run",
                "endpoint": endpoint,
            }

        # Use configured IDs as defaults
        target_list_id = list_id or self.list_id
        target_folder_id = folder_id or self.folder_id
        target_space_id = space_id or self.space_id

        # If we have a space_id, we can get the team_id from the space
        if not team_id and target_space_id:
            try:
                space = self._client.get_space(target_space_id)
                team_id = space.get("team", {}).get("id")
            except NotFoundError:
                pass

        if not team_id:
            raise IssueTrackerError(
                "team_id is required for webhook creation. "
                "Provide team_id parameter or configure space_id to auto-detect."
            )

        return self._client.create_webhook(
            team_id=team_id,
            endpoint=endpoint,
            client_id=client_id,
            events=events,
            task_id=task_id,
            list_id=target_list_id,
            folder_id=target_folder_id,
            space_id=target_space_id,
        )

    def get_webhook(self, webhook_id: str) -> dict[str, Any]:
        """
        Get a webhook by ID.

        Args:
            webhook_id: Webhook ID to retrieve

        Returns:
            Webhook data
        """
        return self._client.get_webhook(webhook_id)

    def list_webhooks(self, team_id: str | None = None) -> list[dict[str, Any]]:
        """
        List webhook subscriptions.

        Args:
            team_id: Optional team ID (will try to detect from space_id if not provided)

        Returns:
            List of webhook subscriptions

        Raises:
            IssueTrackerError: If team_id is required but not provided
        """
        # Try to get team_id from space if not provided
        if not team_id and self.space_id:
            try:
                space = self._client.get_space(self.space_id)
                team_id = space.get("team", {}).get("id")
            except NotFoundError:
                pass

        if not team_id:
            raise IssueTrackerError(
                "team_id is required for listing webhooks. "
                "Provide team_id parameter or configure space_id to auto-detect."
            )

        return self._client.list_webhooks(team_id)

    def update_webhook(
        self,
        webhook_id: str,
        endpoint: str | None = None,
        events: list[str] | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """
        Update a webhook subscription.

        Args:
            webhook_id: Webhook ID to update
            endpoint: Optional new webhook URL
            events: Optional new list of event types
            status: Optional status ('active' or 'inactive')

        Returns:
            Updated webhook data
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would update webhook {webhook_id}")
            return {"id": webhook_id}

        return self._client.update_webhook(
            webhook_id=webhook_id,
            endpoint=endpoint,
            events=events,
            status=status,
        )

    def delete_webhook(self, webhook_id: str) -> bool:
        """
        Delete a webhook subscription.

        Args:
            webhook_id: Webhook ID to delete

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would delete webhook {webhook_id}")
            return True

        return self._client.delete_webhook(webhook_id)

    # -------------------------------------------------------------------------
    # Time Tracking Methods
    # -------------------------------------------------------------------------

    def get_task_time_stats(self, task_id: str) -> dict[str, Any]:
        """
        Get time tracking statistics for a task.

        Args:
            task_id: Task ID

        Returns:
            Dict with time_spent, time_estimate, time_entries_count
        """
        return self._client.get_task_time_stats(task_id)

    def add_spent_time(
        self,
        task_id: str,
        duration: int,
        start: int,
        billable: bool = False,
        description: str | None = None,
    ) -> bool:
        """
        Add spent time to a task.

        Args:
            task_id: Task ID
            duration: Duration in milliseconds
            start: Start time timestamp (milliseconds)
            billable: Whether the time entry is billable
            description: Optional description

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would add {duration}ms spent time to task {task_id}")
            return True

        self._client.create_time_entry(
            task_id=task_id,
            duration=duration,
            start=start,
            billable=billable,
            description=description,
        )
        return True

    def get_time_entries(
        self,
        team_id: str | None = None,
        task_id: str | None = None,
        start_date: int | None = None,
        end_date: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get time entries.

        Args:
            team_id: Optional team ID (will try to detect from space_id)
            task_id: Optional task ID to filter by
            start_date: Optional start date timestamp (milliseconds)
            end_date: Optional end date timestamp (milliseconds)

        Returns:
            List of time entries
        """
        # Try to get team_id from space if not provided
        if not team_id and self.space_id:
            try:
                space = self._client.get_space(self.space_id)
                team_id = space.get("team", {}).get("id")
            except NotFoundError:
                pass

        if not team_id:
            raise IssueTrackerError(
                "team_id is required. Provide team_id parameter or configure space_id to auto-detect."
            )

        if task_id:
            return self._client.get_task_time_entries(task_id)

        return self._client.get_time_entries(
            team_id=team_id,
            start_date=start_date,
            end_date=end_date,
            space_id=self.space_id,
            folder_id=self.folder_id,
            list_id=self.list_id,
            task_id=task_id,
        )

    # -------------------------------------------------------------------------
    # Dependencies & Relationships Methods
    # -------------------------------------------------------------------------

    def get_issue_links(self, issue_key: str) -> list[IssueLink]:
        """
        Get all links (dependencies) for an issue.

        In ClickUp, links are represented as task dependencies.

        Args:
            issue_key: Issue to get links for

        Returns:
            List of IssueLinks
        """
        try:
            dependencies = self._client.get_task_dependencies(issue_key)

            links = []
            for dep in dependencies:
                dep_task_id = dep.get("task_id") or dep.get("depends_on")
                dep_type = dep.get("type", "waiting_on")

                # Map ClickUp dependency types to LinkType
                if dep_type == "blocked_by":
                    link_type = LinkType.IS_BLOCKED_BY
                elif dep_type == "waiting_on":
                    link_type = LinkType.DEPENDS_ON
                else:
                    link_type = LinkType.RELATES_TO

                links.append(
                    IssueLink(
                        link_type=link_type,
                        target_key=dep_task_id,
                        source_key=issue_key,
                    )
                )
            return links
        except (NotFoundError, IssueTrackerError) as e:
            self.logger.error(f"Failed to get links for {issue_key}: {e}")
            return []

    def create_link(
        self,
        source_key: str,
        target_key: str,
        link_type: LinkType,
    ) -> bool:
        """
        Create a link between two issues.

        Args:
            source_key: Source issue key
            target_key: Target issue key
            link_type: Type of link to create

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would create {link_type.value} link: {source_key} -> {target_key}"
            )
            return True

        # Map LinkType to ClickUp dependency type
        if link_type in (LinkType.DEPENDS_ON, LinkType.IS_DEPENDENCY_OF):
            dep_type = "waiting_on"
        elif link_type in (LinkType.BLOCKS, LinkType.IS_BLOCKED_BY):
            dep_type = "blocked_by"
        else:
            # For other link types, use relates_to as waiting_on
            dep_type = "waiting_on"

        try:
            self._client.create_task_dependency(
                task_id=source_key,
                depends_on_task_id=target_key,
                dependency_type=dep_type,
            )
            return True
        except IssueTrackerError as e:
            self.logger.error(f"Failed to create link: {e}")
            return False

    def delete_link(
        self,
        source_key: str,
        target_key: str,
        link_type: LinkType | None = None,
    ) -> bool:
        """
        Delete a link between issues.

        Args:
            source_key: Source issue key
            target_key: Target issue key
            link_type: Optional specific link type to delete

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would delete link: {source_key} -> {target_key}")
            return True

        try:
            self._client.delete_task_dependency(source_key, target_key)
            return True
        except IssueTrackerError as e:
            self.logger.error(f"Failed to delete link: {e}")
            return False

    def get_link_types(self) -> list[dict[str, Any]]:
        """
        Get available link types from ClickUp.

        ClickUp supports 'waiting_on' and 'blocked_by' dependency types.
        """
        return [
            {
                "name": "Waiting On",
                "type": "waiting_on",
                "maps_to": "depends_on",
            },
            {
                "name": "Blocked By",
                "type": "blocked_by",
                "maps_to": "is_blocked_by",
            },
        ]

    # -------------------------------------------------------------------------
    # Views Methods
    # -------------------------------------------------------------------------

    def get_views(
        self,
        team_id: str | None = None,
        view_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get views (Board, List, Calendar, etc.) for a team.

        Args:
            team_id: Optional team ID (will try to detect from space_id)
            view_type: Optional view type filter ('board', 'list', 'calendar', 'table', 'timeline', 'gantt')

        Returns:
            List of views
        """
        # Try to get team_id from space if not provided
        if not team_id and self.space_id:
            try:
                space = self._client.get_space(self.space_id)
                team_id = space.get("team", {}).get("id")
            except NotFoundError:
                pass

        if not team_id:
            raise IssueTrackerError(
                "team_id is required. Provide team_id parameter or configure space_id to auto-detect."
            )

        return self._client.get_views(team_id=team_id, view_type=view_type)

    def get_view(self, view_id: str) -> dict[str, Any]:
        """
        Get a specific view by ID.

        Args:
            view_id: View ID

        Returns:
            View data
        """
        return self._client.get_view(view_id)

    def get_view_tasks(
        self,
        view_id: str,
        page: int = 0,
        include_closed: bool = False,
    ) -> list[IssueData]:
        """
        Get tasks from a view.

        Args:
            view_id: View ID
            page: Page number (default: 0)
            include_closed: Include closed tasks

        Returns:
            List of tasks in the view as IssueData
        """
        tasks = self._client.get_view_tasks(
            view_id=view_id,
            page=page,
            include_closed=include_closed,
        )
        return [self._parse_task(task) for task in tasks]
