"""
Pivotal Tracker Adapter - Implements IssueTrackerPort for Pivotal Tracker.

This is the main entry point for Pivotal Tracker integration.
Maps the generic IssueTrackerPort interface to Pivotal Tracker's issue model.

Key mappings:
- Epic → Epic
- Story → Story
- Subtask → Task (within story)
- Status → Current State
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

from .client import PivotalApiClient


# Pivotal Tracker story states
PIVOTAL_STATES = [
    "unscheduled",
    "unstarted",
    "started",
    "finished",
    "delivered",
    "rejected",
    "accepted",
]


class PivotalAdapter(IssueTrackerPort):
    """
    Pivotal Tracker implementation of the IssueTrackerPort.

    Translates between domain entities and Pivotal Tracker's REST API.

    Pivotal Tracker concepts:
    - Epic: Container for stories with shared theme
    - Story: Work item (feature, bug, chore, release)
    - Task: Subtask within a story
    - Current State: Status (unstarted, started, finished, etc.)
    - Estimate: Story points (for features)
    - Priority: Not directly supported, using labels
    """

    def __init__(
        self,
        api_token: str,
        project_id: str,
        dry_run: bool = True,
        api_url: str = "https://www.pivotaltracker.com/services/v5",
    ):
        """
        Initialize the Pivotal Tracker adapter.

        Args:
            api_token: Pivotal Tracker API token
            project_id: Pivotal Tracker project ID
            dry_run: If True, don't make changes
            api_url: Pivotal Tracker API URL
        """
        self._dry_run = dry_run
        self.project_id = project_id
        self.logger = logging.getLogger("PivotalAdapter")

        # API client
        self._client = PivotalApiClient(
            api_token=api_token,
            project_id=project_id,
            api_url=api_url,
            dry_run=dry_run,
        )

    def _parse_story_id(self, issue_key: str) -> int:
        """Parse story ID from issue key (e.g., 'PT-123' or '123')."""
        # Pivotal uses numeric IDs, but we might have keys like "PT-123"
        if "-" in issue_key:
            try:
                return int(issue_key.split("-")[-1])
            except ValueError:
                pass
        try:
            return int(issue_key)
        except ValueError:
            raise NotFoundError(f"Invalid story ID format: {issue_key}")

    def _map_state_to_status(self, state: str) -> str:
        """Map Pivotal Tracker state to display status."""
        state_mapping = {
            "unscheduled": "Planned",
            "unstarted": "Open",
            "started": "In Progress",
            "finished": "In Review",
            "delivered": "In Review",
            "rejected": "Open",
            "accepted": "Done",
        }
        return state_mapping.get(state.lower(), state.capitalize())

    def _map_status_to_state(self, status: str) -> str:
        """Map display status to Pivotal Tracker state."""
        status_lower = status.lower()

        # Done/closed states
        if any(x in status_lower for x in ["done", "closed", "complete", "accepted"]):
            return "accepted"

        # In review states
        if any(x in status_lower for x in ["review", "delivered", "finished"]):
            return "finished"

        # In progress states
        if any(x in status_lower for x in ["progress", "started", "active"]):
            return "started"

        # Open/todo states
        if any(x in status_lower for x in ["open", "todo", "unstarted"]):
            return "unstarted"

        # Planned/backlog states
        if any(x in status_lower for x in ["planned", "backlog", "unscheduled"]):
            return "unscheduled"

        return "unstarted"

    def _map_story_type(self, story_type: str) -> str:
        """Map Pivotal story type to display issue type."""
        type_mapping = {
            "feature": "Story",
            "bug": "Bug",
            "chore": "Task",
            "release": "Release",
        }
        return type_mapping.get(story_type.lower(), "Story")

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Properties
    # -------------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "Pivotal Tracker"

    @property
    def is_connected(self) -> bool:
        return self._client.is_connected

    def test_connection(self) -> bool:
        return self._client.test_connection()

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Read Operations
    # -------------------------------------------------------------------------

    def get_current_user(self) -> dict[str, Any]:
        return self._client.get_current_user()

    def get_issue(self, issue_key: str) -> IssueData:
        """
        Fetch a single issue by key.

        Args:
            issue_key: Issue identifier (e.g., 'PT-123' or '123')
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

        In Pivotal Tracker, epics are linked to stories via labels.
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
                "author": comment.get("person", {}).get("name"),
                "created": comment.get("created_at"),
            }
            for comment in comments
        ]

    def get_issue_status(self, issue_key: str) -> str:
        """Get the current status (state) of an issue."""
        story_id = self._parse_story_id(issue_key)
        story = self._client.get_story(story_id)
        state = story.get("current_state", "unstarted")
        return self._map_state_to_status(state)

    def search_issues(self, query: str, max_results: int = 50) -> list[IssueData]:
        """
        Search for issues.

        Args:
            query: Search query string (Pivotal filter syntax)
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
        Create a subtask (task in Pivotal Tracker).

        In Pivotal Tracker, subtasks are tasks within a story.
        Note: Tasks don't support story points or assignees directly.
        """
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would create subtask '{summary[:50]}...' under {parent_key}"
            )
            return None

        story_id = self._parse_story_id(parent_key)
        desc_str = description if isinstance(description, str) else str(description)
        task_description = f"{summary}\n\n{desc_str}" if desc_str else summary

        result = self._client.create_task(
            story_id=story_id,
            description=task_description,
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

        # Parse task ID from key (format: "123-T456" or "PT-123-T456")
        if "-T" not in issue_key:
            raise NotFoundError(f"Invalid subtask key format: {issue_key}")

        parts = issue_key.rsplit("-T", 1)
        if len(parts) != 2:
            raise NotFoundError(f"Invalid subtask key format: {issue_key}")

        story_id = self._parse_story_id(parts[0])
        try:
            task_id = int(parts[1])
        except ValueError:
            raise NotFoundError(f"Invalid task ID: {parts[1]}")

        if description is not None:
            desc_str = description if isinstance(description, str) else str(description)
            self._client.update_task(story_id, task_id, description=desc_str)
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
        Transition an issue to a new state.

        Args:
            issue_key: Issue to transition
            target_status: Target status name
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would transition {issue_key} to {target_status}")
            return True

        target_state = self._map_status_to_state(target_status)

        if target_state not in PIVOTAL_STATES:
            raise TransitionError(
                f"Invalid state: {target_status}. Available states: {PIVOTAL_STATES}",
                issue_key=issue_key,
            )

        try:
            story_id = self._parse_story_id(issue_key)
            self._client.update_story(story_id, current_state=target_state)
            self.logger.info(f"Transitioned {issue_key} to {target_state}")
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
        Get available transitions (states) for an issue.

        In Pivotal Tracker, transitions depend on current state.
        """
        return [{"id": state, "name": self._map_state_to_status(state)} for state in PIVOTAL_STATES]

    def format_description(self, markdown: str) -> Any:
        """
        Convert markdown to Pivotal Tracker-compatible format.

        Pivotal Tracker uses Markdown natively.
        """
        return markdown

    # -------------------------------------------------------------------------
    # Label Operations
    # -------------------------------------------------------------------------

    def list_labels(self) -> list[dict[str, Any]]:
        """List all labels in the project."""
        return self._client.list_labels()

    def add_label_to_story(self, issue_key: str, label_name: str) -> bool:
        """Add a label to a story."""
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would add label '{label_name}' to {issue_key}")
            return True

        story_id = self._parse_story_id(issue_key)
        label = self._client.get_or_create_label(label_name)

        if not label.get("id"):
            return False

        story = self._client.get_story(story_id)
        current_labels = [lbl["id"] for lbl in story.get("labels", [])]

        if label["id"] not in current_labels:
            current_labels.append(label["id"])
            self._client.update_story(story_id, label_ids=current_labels)
            self.logger.info(f"Added label '{label_name}' to {issue_key}")

        return True

    # -------------------------------------------------------------------------
    # Iteration (Sprint) Methods
    # -------------------------------------------------------------------------

    def list_iterations(self, scope: str = "current_backlog") -> list[dict[str, Any]]:
        """
        List iterations (sprints) for the project.

        Args:
            scope: One of: done, current, backlog, current_backlog
        """
        return self._client.list_iterations(scope=scope)

    def get_iteration(self, iteration_number: int) -> dict[str, Any]:
        """Get an iteration by number."""
        return self._client.get_iteration(iteration_number)

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
        Create a webhook subscription for the project.

        Args:
            url: Webhook URL to receive events
            events: Ignored (Pivotal sends all events)
            description: Ignored

        Returns:
            Webhook subscription data
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would create webhook for URL {url}")
            return {"id": "webhook:dry-run", "url": url}

        return self._client.create_webhook(url=url)

    def list_webhooks(self) -> list[dict[str, Any]]:
        """List webhook subscriptions for the project."""
        return self._client.list_webhooks()

    def delete_webhook(self, webhook_id: str) -> bool:
        """Delete a webhook subscription."""
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would delete webhook {webhook_id}")
            return True

        return self._client.delete_webhook(int(webhook_id))

    # -------------------------------------------------------------------------
    # Link Operations
    # -------------------------------------------------------------------------

    def get_issue_links(self, issue_key: str) -> list[IssueLink]:
        """
        Get all links for an issue.

        Pivotal Tracker doesn't have native issue linking.
        We can parse blockers from labels or comments if needed.
        """
        return []

    def create_link(
        self,
        source_key: str,
        target_key: str,
        link_type: LinkType,
    ) -> bool:
        """
        Create a link between two issues.

        Pivotal Tracker doesn't have native issue linking.
        We can implement via labels (e.g., "blocks:123").
        """
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would create link: {source_key} {link_type.value} {target_key}"
            )
            return True

        # Implement via label (e.g., "blocks:123")
        label_name = f"{link_type.value}:{target_key}"
        return self.add_label_to_story(source_key, label_name)

    def delete_link(
        self,
        source_key: str,
        target_key: str,
        link_type: LinkType | None = None,
    ) -> bool:
        """
        Delete a link between issues.

        Pivotal Tracker doesn't have native issue linking.
        """
        self.logger.warning("Link deletion not fully supported in Pivotal Tracker")
        return False

    # -------------------------------------------------------------------------
    # File Attachment Operations
    # -------------------------------------------------------------------------

    def get_issue_attachments(self, issue_key: str) -> list[dict[str, Any]]:
        """Get all file attachments for an issue."""
        story_id = self._parse_story_id(issue_key)
        attachments = self._client.get_story_attachments(story_id)
        return [
            {
                "id": str(f.get("id", "")),
                "name": f.get("filename", ""),
                "url": f.get("download_url", ""),
                "content_type": f.get("content_type", ""),
                "size": f.get("size", 0),
                "created": f.get("created_at"),
            }
            for f in attachments
        ]

    def upload_attachment(
        self,
        issue_key: str,
        file_path: str,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Upload a file attachment to an issue."""
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would upload attachment {file_path} to {issue_key}")
            return {"id": "attachment:dry-run", "name": name or file_path}

        story_id = self._parse_story_id(issue_key)

        # Upload the file
        file_data = self._client.upload_file(file_path)
        file_id = file_data.get("id")

        if file_id and file_id != "file:dry-run":
            # Attach to story via comment
            self._client.add_attachment_to_comment(
                story_id,
                file_attachment_ids=[int(file_id)],
                text=f"Attached: {name or file_path}",
            )
            self.logger.info(f"Uploaded attachment to {issue_key}: {file_data.get('filename')}")

        return file_data

    # -------------------------------------------------------------------------
    # Activity Feed
    # -------------------------------------------------------------------------

    def get_activity(self, limit: int = 25) -> list[dict[str, Any]]:
        """Get project activity feed."""
        return self._client.get_project_activity(limit=limit)

    # -------------------------------------------------------------------------
    # Private Methods
    # -------------------------------------------------------------------------

    def _parse_story(self, data: dict) -> IssueData:
        """Parse Pivotal Tracker story API response into IssueData."""
        # Determine issue type from story_type
        story_type = data.get("story_type", "feature")
        issue_type = self._map_story_type(story_type)

        # Get status from current_state
        current_state = data.get("current_state", "unstarted")
        status = self._map_state_to_status(current_state)

        # Get assignee (first owner)
        assignee = None
        owners = data.get("owner_ids", [])
        if owners:
            # We'd need to fetch person details to get name
            # For now, just use the ID
            assignee = str(owners[0])

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
                    "author": comment.get("person", {}).get("name"),
                    "created": comment.get("created_at"),
                }
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
            links=[],  # Pivotal doesn't have native linking
        )

    def _parse_epic(self, data: dict) -> IssueData:
        """Parse Pivotal Tracker epic API response into IssueData."""
        return IssueData(
            key=str(data.get("id", "")),
            summary=data.get("name", ""),
            description=data.get("description"),
            status="Open",  # Epics don't have states in Pivotal
            issue_type="Epic",
        )
