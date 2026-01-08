"""
Shortcut Adapter - Implements IssueTrackerPort for Shortcut (formerly Clubhouse).

This is the main entry point for Shortcut integration.
Maps the generic IssueTrackerPort interface to Shortcut's issue model.

Key mappings:
- Epic → Epic
- Story → Story
- Subtask → Task (within story)
- Status → Workflow State
- Priority → Story priority
- Story Points → Story estimate
"""

import logging
from typing import Any

from spectryn.core.ports.issue_tracker import (
    IssueData,
    IssueLink,
    IssueTrackerError,
    IssueTrackerPort,
    LinkType,
    NotFoundError,
    TransitionError,
)

from .client import ShortcutApiClient


class ShortcutAdapter(IssueTrackerPort):
    """
    Shortcut implementation of the IssueTrackerPort.

    Translates between domain entities and Shortcut's REST API.

    Shortcut concepts:
    - Epic: Collection of stories (like an epic)
    - Story: Work item (like a story)
    - Task: Subtask within a story (like a subtask)
    - Workflow State: Status (To Do, In Progress, Done, etc.)
    - Estimate: Story points
    - Priority: Story priority (low, medium, high)
    """

    def __init__(
        self,
        api_token: str,
        workspace_id: str,
        dry_run: bool = True,
        api_url: str = "https://api.app.shortcut.com/api/v3",
    ):
        """
        Initialize the Shortcut adapter.

        Args:
            api_token: Shortcut API token
            workspace_id: Shortcut workspace ID
            dry_run: If True, don't make changes
            api_url: Shortcut API URL
        """
        self._dry_run = dry_run
        self.workspace_id = workspace_id
        self.logger = logging.getLogger("ShortcutAdapter")

        # API client
        self._client = ShortcutApiClient(
            api_token=api_token,
            workspace_id=workspace_id,
            api_url=api_url,
            dry_run=dry_run,
        )

        # Cache for workflow states
        self._workflow_states: dict[str, dict] = {}  # name -> state

    def _get_workflow_states(self) -> dict[str, dict]:
        """Get workflow states for the workspace, caching the result."""
        if not self._workflow_states:
            states = self._client.get_workflow_states()
            self._workflow_states = {state["name"].lower(): state for state in states}
        return self._workflow_states

    def _find_workflow_state(self, name: str) -> dict | None:
        """Find a workflow state by name (case-insensitive)."""
        states = self._get_workflow_states()
        name_lower = name.lower()

        # Try exact match first
        if name_lower in states:
            return states[name_lower]

        # Try partial match
        for state_name, state in states.items():
            if name_lower in state_name or state_name in name_lower:
                return state

        # Try matching by type
        type_mapping = {
            "open": "to do",
            "todo": "to do",
            "in progress": "in progress",
            "done": "done",
            "closed": "done",
            "cancelled": "done",
        }

        target_type = type_mapping.get(name_lower)
        if target_type:
            for state in states.values():
                if state.get("name", "").lower() == target_type:
                    return state

        return None

    def _parse_story_id(self, issue_key: str) -> int:
        """Parse story ID from issue key (e.g., 'SC-123' -> 123)."""
        # Shortcut uses numeric IDs, but we might have keys like "SC-123"
        if "-" in issue_key:
            try:
                return int(issue_key.split("-")[-1])
            except ValueError:
                pass
        try:
            return int(issue_key)
        except ValueError:
            raise NotFoundError(f"Invalid story ID format: {issue_key}")

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Properties
    # -------------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "Shortcut"

    @property
    def is_connected(self) -> bool:
        return self._client.is_connected

    def test_connection(self) -> bool:
        return self._client.test_connection()

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Read Operations
    # -------------------------------------------------------------------------

    def get_current_user(self) -> dict[str, Any]:
        return self._client.get_current_member()

    def get_issue(self, issue_key: str) -> IssueData:
        """
        Fetch a single issue by key.

        Args:
            issue_key: Issue identifier (e.g., 'SC-123' or '123')
        """
        story_id = self._parse_story_id(issue_key)
        try:
            data = self._client.get_story(story_id)
            return self._parse_story(data)
        except NotFoundError:
            # Try as epic
            try:
                epic_data = self._client.get_epic(story_id)
                return self._parse_epic(epic_data)
            except NotFoundError:
                raise NotFoundError(f"Issue not found: {issue_key}")

    def get_epic_children(self, epic_key: str) -> list[IssueData]:
        """
        Fetch all children of an epic.

        In Shortcut, epics contain stories.
        """
        epic_id = self._parse_story_id(epic_key)
        try:
            stories = self._client.get_epic_stories(epic_id)
            return [self._parse_story(story) for story in stories]
        except NotFoundError:
            return []

    def get_issue_comments(self, issue_key: str) -> list[dict]:
        """Get all comments on an issue."""
        story_id = self._parse_story_id(issue_key)
        comments = self._client.get_story_comments(story_id)
        return [
            {
                "id": comment.get("id"),
                "body": comment.get("text", ""),
                "author": comment.get("author", {}).get("profile", {}).get("name"),
                "created": comment.get("created_at"),
            }
            for comment in comments
        ]

    def get_issue_status(self, issue_key: str) -> str:
        """Get the current status (workflow state) of an issue."""
        story_id = self._parse_story_id(issue_key)
        story = self._client.get_story(story_id)
        workflow_state = story.get("workflow_state", {})
        status = workflow_state.get("name", "Unknown")
        return str(status) if status else "Unknown"

    def search_issues(self, query: str, max_results: int = 50) -> list[IssueData]:
        """
        Search for issues.

        Args:
            query: Search query string
            max_results: Maximum results to return
        """
        stories = self._client.search_stories(query=query, limit=max_results)
        return [self._parse_story(story) for story in stories]

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Write Operations
    # -------------------------------------------------------------------------

    def update_issue_description(self, issue_key: str, description: Any) -> bool:
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would update description for {issue_key}")
            return True

        story_id = self._parse_story_id(issue_key)
        desc_str = description if isinstance(description, str) else str(description)
        self._client.update_story(story_id, description=desc_str)
        self.logger.info(f"Updated description for {issue_key}")
        return True

    def update_issue_story_points(self, issue_key: str, story_points: float) -> bool:
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would update story points for {issue_key} to {story_points}"
            )
            return True

        story_id = self._parse_story_id(issue_key)
        self._client.update_story(story_id, estimate=int(story_points))
        self.logger.info(f"Updated story points for {issue_key} to {story_points}")
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
        Create a subtask (task in Shortcut).

        In Shortcut, subtasks are tasks within a story.
        """
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would create subtask '{summary[:50]}...' under {parent_key}"
            )
            return None

        story_id = self._parse_story_id(parent_key)
        desc_str = description if isinstance(description, str) else str(description)
        task_description = f"{summary}\n\n{desc_str}" if desc_str else summary

        owner_ids = [assignee] if assignee else None
        result = self._client.create_task(
            story_id=story_id,
            description=task_description,
            owner_ids=owner_ids,
        )

        task_id = result.get("id")
        if task_id:
            task_key = f"{parent_key}-T{task_id}"
            self.logger.info(f"Created subtask {task_key} under {parent_key}")
            return task_key
        return None

    def update_subtask(
        self,
        issue_key: str,
        description: Any | None = None,
        story_points: int | None = None,
        assignee: str | None = None,
        priority_id: str | None = None,
    ) -> bool:
        """Update a subtask's fields."""
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would update subtask {issue_key}")
            return True

        # Parse task ID from key (format: "SC-123-T456")
        parts = issue_key.split("-T")
        if len(parts) != 2:
            raise NotFoundError(f"Invalid subtask key format: {issue_key}")

        story_id = self._parse_story_id(parts[0])
        try:
            task_id = int(parts[1])
        except ValueError:
            raise NotFoundError(f"Invalid task ID: {parts[1]}")

        updates: dict[str, Any] = {}

        if description is not None:
            updates["description"] = (
                description if isinstance(description, str) else str(description)
            )

        if assignee is not None:
            updates["owner_ids"] = [assignee]

        if updates:
            self._client.update_task(story_id, task_id, **updates)
            self.logger.info(f"Updated subtask {issue_key}")

        return True

    def add_comment(self, issue_key: str, body: Any) -> bool:
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would add comment to {issue_key}")
            return True

        story_id = self._parse_story_id(issue_key)
        comment_body = body if isinstance(body, str) else str(body)
        self._client.create_comment(story_id, comment_body)
        self.logger.info(f"Added comment to {issue_key}")
        return True

    def transition_issue(self, issue_key: str, target_status: str) -> bool:
        """
        Transition an issue to a new workflow state.

        Args:
            issue_key: Issue to transition
            target_status: Target status name
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would transition {issue_key} to {target_status}")
            return True

        target_state = self._find_workflow_state(target_status)
        if not target_state:
            available = list(self._get_workflow_states().keys())
            raise TransitionError(
                f"Workflow state not found: {target_status}. Available states: {available}",
                issue_key=issue_key,
            )

        try:
            story_id = self._parse_story_id(issue_key)
            self._client.update_story(story_id, workflow_state_id=target_state["id"])
            self.logger.info(f"Transitioned {issue_key} to {target_state['name']}")
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
        Get available transitions (workflow states) for an issue.

        In Shortcut, any issue can transition to any workflow state,
        so we return all states.
        """
        states = self._get_workflow_states()
        return [
            {
                "id": state["id"],
                "name": state["name"],
                "type": state.get("type", ""),
            }
            for state in states.values()
        ]

    def format_description(self, markdown: str) -> Any:
        """
        Convert markdown to Shortcut-compatible format.

        Shortcut uses Markdown natively, so we just return the input.
        """
        return markdown

    # -------------------------------------------------------------------------
    # Webhook Methods
    # -------------------------------------------------------------------------

    def create_webhook(
        self,
        url: str,
        events: list[str] | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a webhook subscription for the workspace.

        Shortcut webhooks notify when changes occur in the workspace.
        Supported events include:
        - story.create, story.update, story.delete
        - epic.create, epic.update, epic.delete
        - task.create, task.update, task.delete
        - comment.create, comment.update

        Args:
            url: Webhook URL to receive events
            events: Optional list of event types to subscribe to (defaults to all)
            description: Optional description for the webhook

        Returns:
            Webhook subscription data
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would create webhook for URL {url}")
            return {"id": "webhook:dry-run", "url": url, "events": events or []}

        return self._client.create_webhook(url=url, events=events, description=description)

    def list_webhooks(self) -> list[dict[str, Any]]:
        """
        List webhook subscriptions for the workspace.

        Returns:
            List of webhook subscriptions
        """
        return self._client.list_webhooks()

    def get_webhook(self, webhook_id: str) -> dict[str, Any]:
        """
        Get a webhook by ID.

        Args:
            webhook_id: Webhook ID to retrieve

        Returns:
            Webhook data
        """
        return self._client.get_webhook(webhook_id)

    def update_webhook(
        self,
        webhook_id: str,
        url: str | None = None,
        events: list[str] | None = None,
        description: str | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any]:
        """
        Update a webhook subscription.

        Args:
            webhook_id: Webhook ID to update
            url: New webhook URL (optional)
            events: New event types (optional)
            description: New description (optional)
            enabled: New enabled status (optional)

        Returns:
            Updated webhook data
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would update webhook {webhook_id}")
            return {"id": webhook_id}

        return self._client.update_webhook(
            webhook_id=webhook_id,
            url=url,
            events=events,
            description=description,
            enabled=enabled,
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
    # Iteration (Sprint) Methods
    # -------------------------------------------------------------------------

    def list_iterations(self) -> list[dict[str, Any]]:
        """
        List all iterations (sprints) for the workspace.

        Returns:
            List of iteration dictionaries
        """
        return self._client.list_iterations()

    def get_iteration(self, iteration_id: int) -> dict[str, Any]:
        """
        Get an iteration by ID.

        Args:
            iteration_id: Iteration ID

        Returns:
            Iteration data
        """
        return self._client.get_iteration(iteration_id)

    def create_iteration(
        self,
        name: str,
        start_date: str,
        end_date: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a new iteration (sprint).

        Args:
            name: Iteration name (e.g., "Sprint 2025-W03")
            start_date: Start date in ISO 8601 format (YYYY-MM-DD)
            end_date: End date in ISO 8601 format (YYYY-MM-DD)
            description: Optional description

        Returns:
            Created iteration data
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would create iteration '{name}'")
            return {
                "id": 0,
                "name": name,
                "start_date": start_date,
                "end_date": end_date,
            }

        return self._client.create_iteration(
            name=name,
            start_date=start_date,
            end_date=end_date,
            description=description,
        )

    def update_iteration(
        self,
        iteration_id: int,
        name: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """
        Update an iteration.

        Args:
            iteration_id: Iteration ID to update
            name: New name (optional)
            start_date: New start date (optional)
            end_date: New end date (optional)
            description: New description (optional)

        Returns:
            Updated iteration data
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would update iteration {iteration_id}")
            return {"id": iteration_id}

        return self._client.update_iteration(
            iteration_id=iteration_id,
            name=name,
            start_date=start_date,
            end_date=end_date,
            description=description,
        )

    def delete_iteration(self, iteration_id: int) -> bool:
        """
        Delete an iteration.

        Args:
            iteration_id: Iteration ID to delete

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would delete iteration {iteration_id}")
            return True

        return self._client.delete_iteration(iteration_id)

    def get_iteration_stories(self, iteration_id: int) -> list[dict[str, Any]]:
        """
        Get all stories assigned to an iteration.

        Args:
            iteration_id: Iteration ID

        Returns:
            List of story dictionaries
        """
        return self._client.get_iteration_stories(iteration_id)

    def assign_story_to_iteration(self, story_id: int, iteration_id: int) -> bool:
        """
        Assign a story to an iteration.

        Args:
            story_id: Story ID
            iteration_id: Iteration ID to assign to

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would assign story {story_id} to iteration {iteration_id}")
            return True

        try:
            self._client.assign_story_to_iteration(story_id, iteration_id)
            self.logger.info(f"Assigned story {story_id} to iteration {iteration_id}")
            return True
        except (NotFoundError, IssueTrackerError) as e:
            self.logger.error(f"Failed to assign story to iteration: {e}")
            return False

    def remove_story_from_iteration(self, story_id: int) -> bool:
        """
        Remove a story from its iteration.

        Args:
            story_id: Story ID

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would remove story {story_id} from iteration")
            return True

        try:
            self._client.remove_story_from_iteration(story_id)
            self.logger.info(f"Removed story {story_id} from iteration")
            return True
        except (NotFoundError, IssueTrackerError) as e:
            self.logger.error(f"Failed to remove story from iteration: {e}")
            return False

    # -------------------------------------------------------------------------
    # Link Operations (Dependencies)
    # -------------------------------------------------------------------------

    def get_issue_links(self, issue_key: str) -> list[IssueLink]:
        """
        Get all links (dependencies) for an issue.

        In Shortcut, links are represented as story dependencies.
        A story can depend on other stories.

        Args:
            issue_key: Issue to get links for

        Returns:
            List of IssueLinks
        """
        try:
            story_id = self._parse_story_id(issue_key)
            dep_ids = self._client.get_story_dependencies(story_id)

            links = []
            for dep_id in dep_ids:
                links.append(
                    IssueLink(
                        link_type=LinkType.DEPENDS_ON,
                        target_key=str(dep_id),
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
        Create a link (dependency) between two issues.

        In Shortcut, we support dependency links:
        - DEPENDS_ON: source depends on target
        - IS_DEPENDENCY_OF: target depends on source (reverse)

        Args:
            source_key: Source issue key
            target_key: Target issue key
            link_type: Type of link to create

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would create link: {source_key} {link_type.value} {target_key}"
            )
            return True

        try:
            source_id = self._parse_story_id(source_key)
            target_id = self._parse_story_id(target_key)

            # Handle link direction
            if link_type == LinkType.DEPENDS_ON:
                # source depends on target
                self._client.add_story_dependency(source_id, target_id)
            elif link_type == LinkType.IS_DEPENDENCY_OF:
                # target depends on source (reverse)
                self._client.add_story_dependency(target_id, source_id)
            elif link_type == LinkType.BLOCKS:
                # source blocks target -> target depends on source
                self._client.add_story_dependency(target_id, source_id)
            elif link_type == LinkType.IS_BLOCKED_BY:
                # source is blocked by target -> source depends on target
                self._client.add_story_dependency(source_id, target_id)
            else:
                # For other link types, use DEPENDS_ON as default
                self.logger.warning(
                    f"Link type {link_type.value} mapped to DEPENDS_ON for Shortcut"
                )
                self._client.add_story_dependency(source_id, target_id)

            self.logger.info(f"Created link: {source_key} {link_type.value} {target_key}")
            return True
        except (NotFoundError, IssueTrackerError) as e:
            self.logger.error(f"Failed to create link: {e}")
            return False

    def delete_link(
        self,
        source_key: str,
        target_key: str,
        link_type: LinkType | None = None,
    ) -> bool:
        """
        Delete a link (dependency) between issues.

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
            source_id = self._parse_story_id(source_key)
            target_id = self._parse_story_id(target_key)

            # Remove dependency - try both directions if type is None
            # (Shortcut dependencies are directional)
            if link_type is None:
                # Try both directions to be safe
                self._client.remove_story_dependency(source_id, target_id)
                self._client.remove_story_dependency(target_id, source_id)
            elif link_type in (
                LinkType.DEPENDS_ON,
                LinkType.IS_BLOCKED_BY,
            ):
                self._client.remove_story_dependency(source_id, target_id)
            elif link_type in (LinkType.IS_DEPENDENCY_OF, LinkType.BLOCKS):
                self._client.remove_story_dependency(target_id, source_id)
            else:
                # For other types, try both directions
                self._client.remove_story_dependency(source_id, target_id)
                self._client.remove_story_dependency(target_id, source_id)

            self.logger.info(f"Deleted link: {source_key} -> {target_key}")
            return True
        except (NotFoundError, IssueTrackerError) as e:
            self.logger.error(f"Failed to delete link: {e}")
            return False

    # -------------------------------------------------------------------------
    # File Attachment Operations
    # -------------------------------------------------------------------------

    def get_issue_attachments(self, issue_key: str) -> list[dict[str, Any]]:
        """
        Get all file attachments for an issue.

        Args:
            issue_key: Issue key (story ID)

        Returns:
            List of attachment dictionaries with id, name, url, etc.
        """
        story_id = self._parse_story_id(issue_key)
        files = self._client.get_story_files(story_id)
        return [
            {
                "id": str(f.get("id", "")),
                "name": f.get("name", ""),
                "url": f.get("url", ""),
                "content_type": f.get("content_type", ""),
                "size": f.get("size", 0),
                "created": f.get("created_at"),
            }
            for f in files
        ]

    def upload_attachment(
        self,
        issue_key: str,
        file_path: str,
        name: str | None = None,
    ) -> dict[str, Any]:
        """
        Upload a file attachment to an issue.

        Args:
            issue_key: Issue key (story ID)
            file_path: Path to file to upload
            name: Optional attachment name

        Returns:
            Attachment information dictionary
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would upload attachment {file_path} to {issue_key}")
            return {"id": "attachment:dry-run", "name": name or file_path}

        story_id = self._parse_story_id(issue_key)

        # First upload the file
        file_data = self._client.upload_file(file_path, name)
        file_id = file_data.get("id")

        if file_id:
            # Link the file to the story
            self._client.link_file_to_story(story_id, file_id)
            self.logger.info(
                f"Uploaded and linked attachment to {issue_key}: {file_data.get('name')}"
            )

        return file_data

    def delete_attachment(
        self,
        issue_key: str,
        attachment_id: str,
    ) -> bool:
        """
        Delete a file attachment from an issue.

        Args:
            issue_key: Issue key (story ID)
            attachment_id: Attachment ID to delete

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would delete attachment {attachment_id} from {issue_key}")
            return True

        try:
            story_id = self._parse_story_id(issue_key)
            file_id = int(attachment_id)

            # First unlink from story
            self._client.unlink_file_from_story(story_id, file_id)

            # Then delete the file
            self._client.delete_file(file_id)

            self.logger.info(f"Deleted attachment {attachment_id} from {issue_key}")
            return True
        except (ValueError, NotFoundError, IssueTrackerError) as e:
            self.logger.error(f"Failed to delete attachment: {e}")
            return False

    # -------------------------------------------------------------------------
    # Private Methods
    # -------------------------------------------------------------------------

    def _parse_story(self, data: dict) -> IssueData:
        """Parse Shortcut story API response into IssueData."""
        # Determine issue type
        story_type = data.get("story_type", "feature")
        issue_type = "Story" if story_type == "feature" else story_type.capitalize()

        # Get status from workflow state
        workflow_state = data.get("workflow_state", {})
        status = workflow_state.get("name", "Unknown")

        # Get assignee
        assignee = None
        owners = data.get("owners", [])
        if owners:
            assignee = owners[0].get("profile", {}).get("name")

        # Get estimate (story points)
        estimate = data.get("estimate")

        # Parse tasks (subtasks)
        subtasks = []
        tasks = data.get("tasks", [])
        for task in tasks:
            subtasks.append(
                IssueData(
                    key=f"{data.get('id')}-T{task.get('id')}",
                    summary=task.get("description", ""),
                    status="Done" if task.get("complete") else "To Do",
                    issue_type="Sub-task",
                )
            )

        # Parse comments
        comments = []
        story_comments = data.get("comments", [])
        for comment in story_comments:
            comments.append(
                {
                    "id": comment.get("id"),
                    "body": comment.get("text", ""),
                    "author": comment.get("author", {}).get("profile", {}).get("name"),
                    "created": comment.get("created_at"),
                }
            )

        # Parse dependencies (links)
        links = []
        depends_on = data.get("depends_on", [])
        story_id = data.get("id")
        if story_id:
            for dep in depends_on:
                dep_id = dep.get("id") if isinstance(dep, dict) else dep
                if dep_id:
                    links.append(
                        IssueLink(
                            link_type=LinkType.DEPENDS_ON,
                            target_key=str(dep_id),
                            source_key=str(story_id),
                        )
                    )

        return IssueData(
            key=str(data.get("id", "")),
            summary=data.get("name", ""),
            description=data.get("description"),
            status=status,
            issue_type=issue_type,
            assignee=assignee,
            story_points=float(estimate) if estimate else None,
            subtasks=subtasks,
            comments=comments,
            links=links,
        )

    def _parse_epic(self, data: dict) -> IssueData:
        """Parse Shortcut epic API response into IssueData."""
        # Get status from state
        state = data.get("state", "to do")
        status = state.capitalize()

        return IssueData(
            key=str(data.get("id", "")),
            summary=data.get("name", ""),
            description=data.get("description"),
            status=status,
            issue_type="Epic",
        )
