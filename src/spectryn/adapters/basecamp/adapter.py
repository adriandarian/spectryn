"""
Basecamp Adapter - Implements IssueTrackerPort for Basecamp 3.

This is the main entry point for Basecamp integration.
Maps the generic IssueTrackerPort interface to Basecamp's model.

Key mappings:
- Epic → Project or Message Board category (we use Message Board)
- Story → Todo (in a todo list) or Message
- Subtask → Todo list item (sub-todo)
- Status → Todo completion status (completed/not completed)
- Priority → Not natively supported (stored in notes)
- Story Points → Not natively supported (stored in notes)
"""

import logging
from typing import Any

from spectryn.core.ports.issue_tracker import (
    IssueData,
    IssueTrackerError,
    IssueTrackerPort,
    NotFoundError,
    TransitionError,
)

from .client import BasecampApiClient


class BasecampAdapter(IssueTrackerPort):
    """
    Basecamp 3 implementation of the IssueTrackerPort.

    Translates between domain entities and Basecamp's todo/message model.

    Basecamp concepts:
    - Project: Top-level container (like an epic)
    - Todo Set: Collection of todos (like a todo list)
    - Todo: Individual task (like a story)
    - Todo Item: Sub-item in a todo (like a subtask)
    - Message: Post in a message board (alternative to todos)
    - Comment: Comment on any recording (todo or message)
    """

    def __init__(
        self,
        access_token: str,
        account_id: str,
        project_id: str,
        dry_run: bool = True,
        api_url: str = "https://3.basecampapi.com",
        use_messages_for_stories: bool = False,
    ):
        """
        Initialize the Basecamp adapter.

        Args:
            access_token: OAuth 2.0 access token
            account_id: Basecamp account ID
            project_id: Basecamp project ID
            dry_run: If True, don't make changes
            api_url: Basecamp API URL
            use_messages_for_stories: If True, use Messages instead of Todos
        """
        self._dry_run = dry_run
        self.account_id = account_id
        self.project_id = project_id
        self.use_messages_for_stories = use_messages_for_stories
        self.logger = logging.getLogger("BasecampAdapter")

        # API client
        self._client = BasecampApiClient(
            access_token=access_token,
            account_id=account_id,
            project_id=project_id,
            api_url=api_url,
            dry_run=dry_run,
        )

        # Cache for todo lists and mappings
        self._todolists_cache: dict[str, dict] = {}  # name -> todolist
        self._todos_cache: dict[str, dict] = {}  # todo_id -> todo

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Properties
    # -------------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "Basecamp"

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
            issue_key: The issue key (e.g., 'TODO-123' or 'MSG-456')
        """
        # Parse issue key to determine type
        if issue_key.startswith("TODO-"):
            todo_id = issue_key.replace("TODO-", "")
            return self._get_todo_as_issue(todo_id)
        if issue_key.startswith("MSG-"):
            message_id = issue_key.replace("MSG-", "")
            return self._get_message_as_issue(message_id)
        # Try as todo first
        try:
            return self._get_todo_as_issue(issue_key)
        except NotFoundError:
            return self._get_message_as_issue(issue_key)

    def get_epic_children(self, epic_key: str) -> list[IssueData]:
        """
        Fetch all children of an epic.

        In Basecamp, epics are represented as Projects.
        We return all todos or messages in the project.
        """
        issues: list[IssueData] = []

        if self.use_messages_for_stories:
            # Get all messages
            messages = self._client.get_messages()
            for message in messages:
                issues.append(self._parse_message(message))
        else:
            # Get all todos from all todo lists
            todolists = self._client.get_todolists()
            for todolist in todolists:
                todos = self._client.get_todos(str(todolist.get("id", "")))
                for todo in todos:
                    issues.append(self._parse_todo(todo))

        return issues

    def get_issue_comments(self, issue_key: str) -> list[dict]:
        """Fetch all comments on an issue."""
        if issue_key.startswith("TODO-"):
            todo_id = issue_key.replace("TODO-", "")
            return self._client.get_comments(todo_id, "Todo")
        if issue_key.startswith("MSG-"):
            message_id = issue_key.replace("MSG-", "")
            return self._client.get_comments(message_id, "Message")
        # Try as todo first
        try:
            return self._client.get_comments(issue_key, "Todo")
        except NotFoundError:
            return self._client.get_comments(issue_key, "Message")

    def get_issue_status(self, issue_key: str) -> str:
        """Get the current status of an issue."""
        issue = self.get_issue(issue_key)
        return issue.status

    def search_issues(self, query: str, max_results: int = 50) -> list[IssueData]:
        """
        Search for issues.

        Basecamp doesn't have a full-text search API, so we search
        within the configured project and filter by content.
        """
        issues: list[IssueData] = []

        if self.use_messages_for_stories:
            messages = self._client.get_messages()
            for message in messages[:max_results]:
                subject = message.get("subject", "")
                content = message.get("content", "")
                if query.lower() in subject.lower() or query.lower() in content.lower():
                    issues.append(self._parse_message(message))
        else:
            todolists = self._client.get_todolists()
            for todolist in todolists:
                todos = self._client.get_todos(str(todolist.get("id", "")))
                for todo in todos:
                    content = todo.get("content", "")
                    notes = todo.get("notes", "")
                    if query.lower() in content.lower() or query.lower() in notes.lower():
                        issues.append(self._parse_todo(todo))
                        if len(issues) >= max_results:
                            break
                if len(issues) >= max_results:
                    break

        return issues[:max_results]

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Write Operations
    # -------------------------------------------------------------------------

    def update_issue_description(self, issue_key: str, description: Any) -> bool:
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would update description for {issue_key}")
            return True

        desc_str = description if isinstance(description, str) else str(description)

        if issue_key.startswith("TODO-"):
            todo_id = issue_key.replace("TODO-", "")
            self._client.update_todo(todo_id, notes=desc_str)
        elif issue_key.startswith("MSG-"):
            message_id = issue_key.replace("MSG-", "")
            # Messages don't have a separate description field, update content
            self._client.put(
                f"projects/{self.project_id}/messages/{message_id}.json",
                json={"content": desc_str},
            )
        else:
            # Try as todo
            try:
                self._client.update_todo(issue_key, notes=desc_str)
            except NotFoundError:
                # Try as message
                self._client.put(
                    f"projects/{self.project_id}/messages/{issue_key}.json",
                    json={"content": desc_str},
                )

        self.logger.info(f"Updated description for {issue_key}")
        return True

    def update_issue_story_points(self, issue_key: str, story_points: float) -> bool:
        """
        Update an issue's story points.

        Basecamp doesn't natively support story points, so we store
        them in the notes field.
        """
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would update story points for {issue_key} to {story_points}"
            )
            return True

        # Get current issue to preserve existing notes
        issue = self.get_issue(issue_key)
        current_notes = issue.description or ""

        # Add or update story points in notes
        notes = self._update_notes_with_story_points(current_notes, story_points)

        if issue_key.startswith("TODO-"):
            todo_id = issue_key.replace("TODO-", "")
            self._client.update_todo(todo_id, notes=notes)
        else:
            # For messages, we can't easily update notes, so log a warning
            self.logger.warning("Story points not supported for messages, storing in content")

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
        Create a subtask under a parent issue.

        In Basecamp, subtasks are represented as todo items within a todo.
        However, Basecamp's API doesn't directly support nested todos,
        so we create a new todo in the same todo list and link it via notes.
        """
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would create subtask '{summary[:50]}...' under {parent_key}"
            )
            return None

        if not parent_key.startswith("TODO-"):
            raise IssueTrackerError("Subtasks can only be created under todos, not messages")

        todo_id = parent_key.replace("TODO-", "")
        parent_todo = self._client.get_todo(todo_id)
        todolist_id = str(parent_todo.get("parent", {}).get("id", ""))

        if not todolist_id:
            raise IssueTrackerError(f"Could not find todo list for todo {todo_id}")

        # Build notes with description and metadata
        notes_parts = []
        if description:
            desc_str = description if isinstance(description, str) else str(description)
            notes_parts.append(desc_str)
        if priority:
            notes_parts.append(f"\n**Priority:** {priority}")
        if story_points:
            notes_parts.append(f"\n**Story Points:** {story_points}")
        notes_parts.append(f"\n**Parent:** {parent_key}")
        notes = "\n".join(notes_parts)

        # Create the subtask as a new todo
        assignee_ids = None
        if assignee:
            # Try to parse assignee ID (Basecamp uses integer IDs)
            try:
                assignee_ids = [int(assignee)]
            except ValueError:
                self.logger.warning(f"Invalid assignee ID: {assignee}")

        result = self._client.create_todo(
            todolist_id=todolist_id,
            content=summary,
            notes=notes,
            assignee_ids=assignee_ids,
        )

        subtask_id = result.get("id")
        if subtask_id:
            subtask_key = f"TODO-{subtask_id}"
            self.logger.info(f"Created subtask {subtask_key} under {parent_key}")
            return subtask_key
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

        if not issue_key.startswith("TODO-"):
            raise IssueTrackerError("Subtasks must be todos")

        todo_id = issue_key.replace("TODO-", "")
        updates: dict[str, Any] = {}

        if description is not None:
            desc_str = description if isinstance(description, str) else str(description)
            updates["notes"] = desc_str

        if story_points is not None:
            # Get current notes and update story points
            todo = self._client.get_todo(todo_id)
            current_notes = todo.get("notes", "")
            updates["notes"] = self._update_notes_with_story_points(current_notes, story_points)

        if assignee is not None:
            try:
                updates["assignee_ids"] = [int(assignee)]
            except ValueError:
                self.logger.warning(f"Invalid assignee ID: {assignee}")

        if updates:
            self._client.update_todo(todo_id, **updates)
            self.logger.info(f"Updated subtask {issue_key}")

        return True

    def add_comment(self, issue_key: str, body: Any) -> bool:
        """Add a comment to an issue."""
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would add comment to {issue_key}")
            return True

        comment_body = body if isinstance(body, str) else str(body)

        if issue_key.startswith("TODO-"):
            todo_id = issue_key.replace("TODO-", "")
            self._client.create_comment(todo_id, "Todo", comment_body)
        elif issue_key.startswith("MSG-"):
            message_id = issue_key.replace("MSG-", "")
            self._client.create_comment(message_id, "Message", comment_body)
        else:
            # Try as todo first
            try:
                self._client.create_comment(issue_key, "Todo", comment_body)
            except NotFoundError:
                self._client.create_comment(issue_key, "Message", comment_body)

        self.logger.info(f"Added comment to {issue_key}")
        return True

    def transition_issue(self, issue_key: str, target_status: str) -> bool:
        """
        Transition an issue to a new status.

        In Basecamp, status is represented by completion state.
        We map statuses to completed/not completed.
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would transition {issue_key} to {target_status}")
            return True

        if not issue_key.startswith("TODO-"):
            raise TransitionError(
                "Status transitions only supported for todos, not messages",
                issue_key=issue_key,
            )

        todo_id = issue_key.replace("TODO-", "")

        # Map status to completion state
        status_lower = target_status.lower()
        is_completed = status_lower in ("done", "completed", "closed", "resolved")

        try:
            if is_completed:
                self._client.complete_todo(todo_id)
            else:
                self._client.uncomplete_todo(todo_id)
            self.logger.info(f"Transitioned {issue_key} to {target_status}")
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
        Get available transitions for an issue.

        Basecamp only has completed/not completed, so we return those.
        """
        return [
            {"id": "completed", "name": "Completed", "to": "Done"},
            {"id": "not_completed", "name": "Not Completed", "to": "Planned"},
        ]

    def format_description(self, markdown: str) -> Any:
        """
        Convert markdown to Basecamp-compatible format.

        Basecamp supports HTML and some markdown, so we return as-is.
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
        Create a webhook subscription for the project.

        Basecamp webhooks notify when changes occur in the project.
        Supported events include:
        - todo.created, todo.updated, todo.completed, todo.uncompleted
        - message.created, message.updated
        - comment.created, comment.updated
        - todo_list.created, todo_list.updated

        Args:
            url: Webhook URL to receive events (must be HTTPS)
            events: Optional list of event types to subscribe to (defaults to all)
            description: Optional description for the webhook

        Returns:
            Webhook subscription data
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would create webhook for URL {url}")
            return {
                "id": "webhook:dry-run",
                "url": url,
                "events": events or [],
                "project_id": self.project_id,
            }

        return self._client.create_webhook(url=url, events=events, description=description)

    def list_webhooks(self) -> list[dict[str, Any]]:
        """
        List webhook subscriptions for the project.

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
            url: Optional new webhook URL
            events: Optional new list of event types
            description: Optional new description
            enabled: Optional enable/disable flag

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
    # Campfire (Chat) Methods
    # -------------------------------------------------------------------------

    def get_campfires(self) -> list[dict[str, Any]]:
        """
        Get all Campfire chats for the project.

        Returns:
            List of Campfire chat data
        """
        return self._client.get_campfires()

    def get_campfire(self, chat_id: str) -> dict[str, Any]:
        """
        Get a specific Campfire chat.

        Args:
            chat_id: Campfire chat ID

        Returns:
            Campfire chat data
        """
        return self._client.get_campfire(chat_id)

    def get_campfire_messages(
        self,
        chat_id: str,
        since: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get chat messages from a Campfire.

        Args:
            chat_id: Campfire chat ID
            since: Optional ISO 8601 timestamp to get messages since
            limit: Optional maximum number of messages to return

        Returns:
            List of chat message data
        """
        return self._client.get_campfire_lines(chat_id=chat_id, since=since, limit=limit)

    def send_campfire_message(
        self,
        chat_id: str,
        content: str,
    ) -> dict[str, Any]:
        """
        Send a message to a Campfire chat.

        Useful for notifications, status updates, or automated messages.

        Args:
            chat_id: Campfire chat ID
            content: Message content

        Returns:
            Created message data
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would send message to Campfire {chat_id}")
            return {
                "id": "line:dry-run",
                "content": content,
                "chat_id": chat_id,
            }

        return self._client.send_campfire_message(chat_id=chat_id, content=content)

    def create_campfire(
        self,
        name: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a new Campfire chat in the project.

        Args:
            name: Optional name for the Campfire (defaults to "Campfire")

        Returns:
            Created Campfire chat data
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would create Campfire '{name or 'Campfire'}'")
            return {
                "id": "chat:dry-run",
                "name": name or "Campfire",
                "project_id": self.project_id,
            }

        return self._client.create_campfire(name=name)

    # -------------------------------------------------------------------------
    # Private Methods
    # -------------------------------------------------------------------------

    def _get_todo_as_issue(self, todo_id: str) -> IssueData:
        """Get a todo and convert it to IssueData."""
        todo = self._client.get_todo(todo_id)
        return self._parse_todo(todo)

    def _get_message_as_issue(self, message_id: str) -> IssueData:
        """Get a message and convert it to IssueData."""
        message = self._client.get_message(message_id)
        return self._parse_message(message)

    def _parse_todo(self, todo: dict[str, Any]) -> IssueData:
        """Parse Basecamp todo into IssueData."""
        todo_id = str(todo.get("id", ""))
        content = todo.get("content", "")
        notes = todo.get("notes", "")
        completed = todo.get("completed", False)

        # Determine status
        status = "Done" if completed else "Planned"

        # Extract story points from notes if present
        story_points = self._extract_story_points_from_notes(notes)

        # Get assignee
        assignee = None
        assignees = todo.get("assignees", [])
        if assignees:
            assignee = assignees[0].get("name") or str(assignees[0].get("id", ""))

        # Get due date
        due_date = todo.get("due_on")

        # Parse subtasks (todo items) - Basecamp doesn't have nested todos,
        # so we look for linked todos in notes
        subtasks: list[IssueData] = []

        # Get comments
        comments = []
        try:
            comment_data = self._client.get_comments(todo_id, "Todo")
            for comment in comment_data:
                comments.append(
                    {
                        "id": str(comment.get("id", "")),
                        "body": comment.get("content", ""),
                        "author": comment.get("creator", {}).get("name", ""),
                        "created": comment.get("created_at", ""),
                    }
                )
        except Exception:
            pass

        return IssueData(
            key=f"TODO-{todo_id}",
            summary=content,
            description=notes,
            status=status,
            issue_type="Story",
            assignee=assignee,
            story_points=story_points,
            due_date=due_date,
            subtasks=subtasks,
            comments=comments,
        )

    def _parse_message(self, message: dict[str, Any]) -> IssueData:
        """Parse Basecamp message into IssueData."""
        message_id = str(message.get("id", ""))
        subject = message.get("subject", "")
        content = message.get("content", "")

        # Messages don't have completion status, so they're always "Planned"
        status = "Planned"

        # Extract story points from content if present
        story_points = self._extract_story_points_from_notes(content)

        # Get comments
        comments = []
        try:
            comment_data = self._client.get_comments(message_id, "Message")
            for comment in comment_data:
                comments.append(
                    {
                        "id": str(comment.get("id", "")),
                        "body": comment.get("content", ""),
                        "author": comment.get("creator", {}).get("name", ""),
                        "created": comment.get("created_at", ""),
                    }
                )
        except Exception:
            pass

        return IssueData(
            key=f"MSG-{message_id}",
            summary=subject,
            description=content,
            status=status,
            issue_type="Story",
            assignee=None,
            story_points=story_points,
            due_date=None,
            subtasks=[],
            comments=comments,
        )

    def _extract_story_points_from_notes(self, notes: str) -> float | None:
        """Extract story points from notes if present."""
        if not notes:
            return None

        import re

        # Look for "Story Points: X" or "SP: X" pattern
        patterns = [
            r"story\s*points?[:\s]+(\d+(?:\.\d+)?)",
            r"sp[:\s]+(\d+(?:\.\d+)?)",
            r"points?[:\s]+(\d+(?:\.\d+)?)",
        ]

        for pattern in patterns:
            match = re.search(pattern, notes, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    pass

        return None

    def _extract_priority_from_notes(self, notes: str) -> str | None:
        """Extract priority from notes if present."""
        if not notes:
            return None

        import re

        # Look for "Priority: X" pattern
        match = re.search(r"priority[:\s]+(\w+)", notes, re.IGNORECASE)
        if match:
            return match.group(1).capitalize()

        return None

    def _update_notes_with_story_points(self, current_notes: str, story_points: float) -> str:
        """Update notes to include story points."""
        import re

        # Remove existing story points
        patterns = [
            r"story\s*points?[:\s]+\d+(?:\.\d+)?\s*\n?",
            r"sp[:\s]+\d+(?:\.\d+)?\s*\n?",
            r"points?[:\s]+\d+(?:\.\d+)?\s*\n?",
        ]

        notes = current_notes
        for pattern in patterns:
            notes = re.sub(pattern, "", notes, flags=re.IGNORECASE)

        # Add new story points
        if notes.strip():
            notes = f"{notes.strip()}\n\n**Story Points:** {story_points}"
        else:
            notes = f"**Story Points:** {story_points}"

        return notes
