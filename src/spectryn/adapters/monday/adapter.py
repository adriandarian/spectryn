"""
Monday.com Adapter - Implements IssueTrackerPort for Monday.com.

This is the main entry point for Monday.com integration.
Maps the generic IssueTrackerPort interface to Monday.com's board model.

Key mappings:
- Epic → Group (board group)
- Story → Item (board item)
- Subtask → Subitem (linked item)
- Status → Status column
- Priority → Priority column
- Story Points → Numbers column
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

from .client import MondayApiClient


class MondayAdapter(IssueTrackerPort):
    """
    Monday.com implementation of the IssueTrackerPort.

    Translates between domain entities and Monday.com's GraphQL API.

    Monday.com concepts:
    - Board: Collection of items (like a project)
    - Group: Column/group within a board (like an epic)
    - Item: Work item (like a story)
    - Subitem: Child of another item (like a subtask)
    - Column: Custom field (Status, Priority, Numbers, etc.)
    - Update: Comment/update on an item
    """

    def __init__(
        self,
        api_token: str,
        board_id: str,
        workspace_id: str | None = None,
        dry_run: bool = True,
        api_url: str = "https://api.monday.com/v2",
        status_column_id: str | None = None,
        priority_column_id: str | None = None,
        story_points_column_id: str | None = None,
    ):
        """
        Initialize the Monday.com adapter.

        Args:
            api_token: Monday.com API token (v2)
            board_id: Board ID to work with
            workspace_id: Optional workspace ID
            dry_run: If True, don't make changes
            api_url: Monday.com GraphQL API URL
            status_column_id: Optional status column ID (auto-detected if None)
            priority_column_id: Optional priority column ID (auto-detected if None)
            story_points_column_id: Optional story points column ID (auto-detected if None)
        """
        self._dry_run = dry_run
        self.board_id = board_id
        self.workspace_id = workspace_id
        self.logger = logging.getLogger("MondayAdapter")

        # API client
        self._client = MondayApiClient(
            api_token=api_token,
            api_url=api_url,
            dry_run=dry_run,
        )

        # Column mapping cache
        self._board: dict[str, Any] | None = None
        self._status_column_id: str | None = status_column_id
        self._priority_column_id: str | None = priority_column_id
        self._story_points_column_id: str | None = story_points_column_id

    def _get_board(self) -> dict[str, Any]:
        """Get the configured board, caching the result."""
        if self._board is None:
            self._board = self._client.get_board(self.board_id)
        return self._board

    def _get_column_id(self, column_type: str, title_hint: str | None = None) -> str | None:
        """
        Get column ID by type or title.

        Args:
            column_type: Column type (e.g., 'status', 'priority', 'numbers')
            title_hint: Optional title hint to match

        Returns:
            Column ID or None if not found
        """
        board = self._get_board()
        columns = board.get("columns", [])

        # Try exact type match first
        for col in columns:
            if col.get("type", "").lower() == column_type.lower():
                if title_hint:
                    # Prefer column matching title hint
                    if title_hint.lower() in col.get("title", "").lower():
                        return col["id"]
                else:
                    return col["id"]

        # Try title match if hint provided
        if title_hint:
            for col in columns:
                if title_hint.lower() in col.get("title", "").lower():
                    return col["id"]

        return None

    def _get_status_column_id(self) -> str | None:
        """Get status column ID, auto-detecting if not set."""
        if self._status_column_id:
            return self._status_column_id
        return self._get_column_id("status", "Status")

    def _get_priority_column_id(self) -> str | None:
        """Get priority column ID, auto-detecting if not set."""
        if self._priority_column_id:
            return self._priority_column_id
        return self._get_column_id("priority", "Priority")

    def _get_story_points_column_id(self) -> str | None:
        """Get story points column ID, auto-detecting if not set."""
        if self._story_points_column_id:
            return self._story_points_column_id
        return self._get_column_id("numbers", "Story Points")

    def _get_group_id(self, group_name: str) -> str | None:
        """Get group ID by name."""
        board = self._get_board()
        groups = board.get("groups", [])
        for group in groups:
            if group.get("title", "").lower() == group_name.lower():
                return group["id"]
        return None

    def _parse_column_value(self, column_value: dict[str, Any]) -> Any:
        """Parse column value based on type."""
        col_type = column_value.get("type", "")
        value = column_value.get("value")

        if col_type == "status":
            # Status values are JSON strings
            import json

            try:
                status_data = json.loads(value) if value else {}
                return status_data.get("index", 0)
            except (json.JSONDecodeError, TypeError):
                return column_value.get("text", "")

        if col_type == "priority":
            # Priority values are JSON strings
            import json

            try:
                priority_data = json.loads(value) if value else {}
                return priority_data.get("index", 0)
            except (json.JSONDecodeError, TypeError):
                return column_value.get("text", "")

        if col_type == "numbers":
            # Numbers are stored as text
            try:
                return float(column_value.get("text", "0") or "0")
            except (ValueError, TypeError):
                return None

        # Default: return text
        return column_value.get("text", "")

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Properties
    # -------------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "Monday.com"

    @property
    def is_connected(self) -> bool:
        return self._client.is_connected

    def test_connection(self) -> bool:
        if not self._client.test_connection():
            return False
        # Also verify board access
        try:
            self._get_board()
            return True
        except IssueTrackerError:
            return False

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Read Operations
    # -------------------------------------------------------------------------

    def get_current_user(self) -> dict[str, Any]:
        return self._client.get_viewer()

    def get_issue(self, issue_key: str) -> IssueData:
        """
        Fetch a single item by ID.

        Args:
            issue_key: Item ID
        """
        data = self._client.get_item(issue_key)
        return self._parse_item(data)

    def get_epic_children(self, epic_key: str) -> list[IssueData]:
        """
        Fetch all children of an epic (group).

        In Monday.com, epics are represented as Groups.
        """
        # Try to find group by name or ID
        group_id: str | None = epic_key if epic_key.isdigit() else None
        if not group_id:
            # Assume it's a group name
            group_id = self._get_group_id(epic_key)
            if not group_id:
                raise NotFoundError(f"Group not found: {epic_key}")

        items = self._client.get_board_items(
            board_id=self.board_id,
            group_id=group_id,
        )
        return [self._parse_item(item) for item in items]

    def get_issue_comments(self, issue_key: str) -> list[dict]:
        """Get all updates (comments) on an item."""
        item = self._client.get_item(issue_key)
        updates = item.get("updates", [])
        return [
            {
                "id": update.get("id"),
                "body": update.get("body"),
                "author": update.get("creator", {}).get("name"),
                "created": update.get("created_at"),
            }
            for update in updates
        ]

    def get_issue_status(self, issue_key: str) -> str:
        """Get the current status of an item."""
        item = self._client.get_item(issue_key)
        status_col_id = self._get_status_column_id()
        if not status_col_id:
            return "Unknown"

        for col_val in item.get("column_values", []):
            if col_val.get("id") == status_col_id:
                return col_val.get("text", "Unknown")
        return "Unknown"

    def search_issues(self, query: str, max_results: int = 50) -> list[IssueData]:
        """
        Search for items.

        Monday.com doesn't have a full-text search API like Jira's JQL,
        so we search within the configured board.
        """
        items = self._client.get_board_items(
            board_id=self.board_id,
            limit=max_results,
        )
        # Simple name-based filtering
        if query:
            query_lower = query.lower()
            items = [item for item in items if query_lower in item.get("name", "").lower()]

        return [self._parse_item(item) for item in items[:max_results]]

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Write Operations
    # -------------------------------------------------------------------------

    def update_issue_description(self, issue_key: str, description: Any) -> bool:
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would update description for {issue_key}")
            return True

        # Monday.com doesn't have a dedicated description field
        # We could use a text column or add as an update
        # For now, we'll add it as an update
        desc_str = description if isinstance(description, str) else str(description)
        self._client.add_update(issue_key, desc_str)
        self.logger.info(f"Updated description for {issue_key}")
        return True

    def update_issue_story_points(self, issue_key: str, story_points: float) -> bool:
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would update story points for {issue_key} to {story_points}"
            )
            return True

        col_id = self._get_story_points_column_id()
        if not col_id:
            self.logger.warning("Story points column not found, skipping update")
            return False

        column_values = {col_id: str(story_points)}
        self._client.update_item(issue_key, column_values=column_values)
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
        Create a subitem (subtask in Monday.com).

        In Monday.com, subitems are linked items under a parent.
        """
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would create subitem '{summary[:50]}...' under {parent_key}"
            )
            return None

        desc_str = description if isinstance(description, str) else str(description)

        column_values: dict[str, Any] = {}
        if story_points:
            col_id = self._get_story_points_column_id()
            if col_id:
                column_values[col_id] = str(story_points)

        result = self._client.create_subitem(
            parent_item_id=parent_key,
            subitem_name=summary[:255],
            column_values=column_values if column_values else None,
        )

        item_id = result.get("id")
        if item_id:
            self.logger.info(f"Created subitem {item_id} under {parent_key}")
            # Add description as update
            if desc_str:
                self._client.add_update(item_id, desc_str)
        return item_id

    def update_subtask(
        self,
        issue_key: str,
        description: Any | None = None,
        story_points: int | None = None,
        assignee: str | None = None,
        priority_id: str | None = None,
    ) -> bool:
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would update subitem {issue_key}")
            return True

        column_values: dict[str, Any] = {}

        if description is not None:
            desc_str = description if isinstance(description, str) else str(description)
            self._client.add_update(issue_key, desc_str)

        if story_points is not None:
            col_id = self._get_story_points_column_id()
            if col_id:
                column_values[col_id] = str(story_points)

        if column_values:
            self._client.update_item(issue_key, column_values=column_values)
            self.logger.info(f"Updated subitem {issue_key}")

        return True

    def add_comment(self, issue_key: str, body: Any) -> bool:
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would add comment to {issue_key}")
            return True

        comment_body = body if isinstance(body, str) else str(body)
        self._client.add_update(issue_key, comment_body)
        self.logger.info(f"Added comment to {issue_key}")
        return True

    def transition_issue(self, issue_key: str, target_status: str) -> bool:
        """
        Transition an item to a new status.

        Monday.com uses status columns with predefined values.
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would transition {issue_key} to {target_status}")
            return True

        col_id = self._get_status_column_id()
        if not col_id:
            raise TransitionError(
                f"Status column not found. Cannot transition {issue_key}.",
                issue_key=issue_key,
            )

        # Get current status column to find available values
        item = self._client.get_item(issue_key)
        status_col = None
        for col_val in item.get("column_values", []):
            if col_val.get("id") == col_id:
                status_col = col_val
                break

        if not status_col:
            raise TransitionError(
                f"Status column not found on item {issue_key}.",
                issue_key=issue_key,
            )

        # Monday.com status values are JSON with index
        # We need to find the index for the target status
        import json

        try:
            settings_str = status_col.get("settings_str", "{}")
            settings = json.loads(settings_str) if settings_str else {}
            labels = settings.get("labels", {})

            # Find status index by matching label text
            status_index = None
            for idx_str, label_data in labels.items():
                if label_data.get("label", "").lower() == target_status.lower():
                    status_index = int(idx_str)
                    break

            if status_index is None:
                # Try to use first available status as fallback
                if labels:
                    status_index = int(next(iter(labels.keys())))
                else:
                    raise TransitionError(
                        f"Status '{target_status}' not found. Available: {list(labels.values())}",
                        issue_key=issue_key,
                    )

            status_value = json.dumps({"index": status_index})
            column_values = {col_id: status_value}
            self._client.update_item(issue_key, column_values=column_values)
            self.logger.info(f"Transitioned {issue_key} to {target_status}")
            return True

        except (json.JSONDecodeError, ValueError, KeyError) as e:
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
        Get available status transitions for an item.

        In Monday.com, we return all available status values.
        """
        col_id = self._get_status_column_id()
        if not col_id:
            return []

        # Get status column settings
        board = self._get_board()
        status_col = None
        for col in board.get("columns", []):
            if col.get("id") == col_id:
                status_col = col
                break

        if not status_col:
            return []

        import json

        try:
            settings_str = status_col.get("settings_str", "{}")
            settings = json.loads(settings_str) if settings_str else {}
            labels = settings.get("labels", {})

            return [
                {
                    "id": str(idx),
                    "name": label_data.get("label", ""),
                }
                for idx, label_data in labels.items()
            ]
        except (json.JSONDecodeError, KeyError):
            return []

    def format_description(self, markdown: str) -> Any:
        """
        Convert markdown to Monday.com-compatible format.

        Monday.com supports markdown in updates, so we return as-is.
        """
        return markdown

    # -------------------------------------------------------------------------
    # File Attachment Methods
    # -------------------------------------------------------------------------

    def upload_file(
        self,
        issue_key: str,
        file_path: str,
        column_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Upload a file to an item.

        Args:
            issue_key: Item ID
            file_path: Path to file to upload
            column_id: Optional file column ID (if None, uploads as attachment)

        Returns:
            Upload result with file information
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would upload file {file_path} to {issue_key}")
            return {"id": "file:dry-run"}

        return self._client.upload_file(issue_key, file_path, column_id)

    def get_item_files(self, issue_key: str) -> list[dict[str, Any]]:
        """
        Get all files attached to an item.

        Args:
            issue_key: Item ID

        Returns:
            List of file information dictionaries
        """
        return self._client.get_item_files(issue_key)

    # -------------------------------------------------------------------------
    # Timeline/Gantt Methods
    # -------------------------------------------------------------------------

    def _get_timeline_column_id(self) -> str | None:
        """Get timeline column ID, auto-detecting if not set."""
        return self._get_column_id("timeline", "Timeline")

    def _get_start_date_column_id(self) -> str | None:
        """Get start date column ID, auto-detecting if not set."""
        return self._get_column_id("date", "Start Date")

    def _get_end_date_column_id(self) -> str | None:
        """Get end date column ID, auto-detecting if not set."""
        return self._get_column_id("date", "End Date")

    def set_timeline_dates(
        self,
        issue_key: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> bool:
        """
        Set timeline dates for an item (for Gantt view).

        Args:
            issue_key: Item ID
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would set timeline dates for {issue_key}: "
                f"start={start_date}, end={end_date}"
            )
            return True

        timeline_col_id = self._get_timeline_column_id()
        self._client.update_timeline_dates(
            issue_key,
            start_date=start_date,
            end_date=end_date,
            timeline_column_id=timeline_col_id,
        )
        self.logger.info(f"Set timeline dates for {issue_key}")
        return True

    def get_timeline_dates(self, issue_key: str) -> dict[str, str | None]:
        """
        Get timeline dates from an item.

        Args:
            issue_key: Item ID

        Returns:
            Dictionary with 'start_date' and 'end_date' keys
        """
        return self._client.get_timeline_dates(issue_key)

    # -------------------------------------------------------------------------
    # Webhook Methods
    # -------------------------------------------------------------------------

    def create_webhook(
        self,
        url: str,
        event: str = "change_column_value",
    ) -> dict[str, Any]:
        """
        Create a webhook subscription for the board.

        Monday.com webhooks notify when items on a board change.
        Supported events:
        - change_column_value: When a column value changes
        - create_item: When a new item is created
        - create_update: When an update/comment is created
        - change_status: When status changes
        - change_name: When item name changes
        - create_subitem: When a subitem is created

        Args:
            url: Webhook URL to receive events
            event: Event type to subscribe to (default: change_column_value)

        Returns:
            Webhook subscription data
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would create webhook for board {self.board_id}")
            return {"id": "webhook:dry-run", "board_id": self.board_id, "url": url}

        return self._client.create_webhook(
            board_id=self.board_id,
            url=url,
            event=event,
        )

    def list_webhooks(self) -> list[dict[str, Any]]:
        """
        List webhook subscriptions for the board.

        Returns:
            List of webhook subscriptions
        """
        return self._client.list_webhooks(board_id=self.board_id)

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

    def verify_webhook(self, webhook_id: str) -> dict[str, Any]:
        """
        Verify a webhook subscription.

        Args:
            webhook_id: Webhook ID to verify

        Returns:
            Webhook verification data
        """
        return self._client.verify_webhook(webhook_id)

    # -------------------------------------------------------------------------
    # Private Methods
    # -------------------------------------------------------------------------

    def _parse_item(self, data: dict) -> IssueData:
        """Parse Monday.com API response into IssueData."""
        # Determine issue type
        is_subitem = False  # We'd need parent info to determine this
        issue_type = "Sub-task" if is_subitem else "Story"

        # Get status
        status = "Unknown"
        status_col_id = self._get_status_column_id()
        if status_col_id:
            for col_val in data.get("column_values", []):
                if col_val.get("id") == status_col_id:
                    status = col_val.get("text", "Unknown")
                    break

        # Get story points
        story_points = None
        sp_col_id = self._get_story_points_column_id()
        if sp_col_id:
            for col_val in data.get("column_values", []):
                if col_val.get("id") == sp_col_id:
                    parsed_value = self._parse_column_value(col_val)
                    if parsed_value is not None:
                        story_points = float(parsed_value)
                    break

        # Parse subitems
        subtasks = []
        for subitem in data.get("subitems", []):
            subtasks.append(
                IssueData(
                    key=subitem.get("id", ""),
                    summary=subitem.get("name", ""),
                    status="Unknown",
                    issue_type="Sub-task",
                )
            )

        # Parse comments/updates
        comments = []
        for update in data.get("updates", []):
            comments.append(
                {
                    "id": update.get("id"),
                    "body": update.get("body"),
                    "author": update.get("creator", {}).get("name"),
                    "created": update.get("created_at"),
                }
            )

        return IssueData(
            key=data.get("id", ""),
            summary=data.get("name", ""),
            description=None,  # Monday.com doesn't have a description field
            status=status,
            issue_type=issue_type,
            assignee=None,  # Would need to parse from column values
            story_points=story_points,
            subtasks=subtasks,
            comments=comments,
        )
