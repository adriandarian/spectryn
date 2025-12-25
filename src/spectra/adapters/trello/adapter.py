"""
Trello Adapter - Implements IssueTrackerPort for Trello.

This is the main entry point for Trello integration.
Maps the generic IssueTrackerPort interface to Trello's card model.

Key mappings:
- Epic → Board or List (epic list)
- Story → Card
- Subtask → Checklist item or linked card
- Status → List (board lists)
- Priority → Labels
- Story Points → Custom field or card description
"""

import logging
from typing import Any

from spectra.core.ports.config_provider import TrelloConfig
from spectra.core.ports.issue_tracker import (
    IssueData,
    IssueTrackerError,
    IssueTrackerPort,
    NotFoundError,
    TransitionError,
)

from .client import TrelloApiClient


class TrelloAdapter(IssueTrackerPort):
    """
    Trello implementation of the IssueTrackerPort.

    Translates between domain entities and Trello's REST API.

    Trello concepts:
    - Board: Collection of lists and cards (like a project/epic)
    - List: Column on a board (like a status/state)
    - Card: Work item (like a story)
    - Checklist: Subtasks on a card
    - Label: Tags/priorities (color-coded)
    - Comment: Notes on a card
    """

    def __init__(
        self,
        config: TrelloConfig,
        dry_run: bool = True,
    ):
        """
        Initialize the Trello adapter.

        Args:
            config: Trello configuration
            dry_run: If True, don't make changes
        """
        self._dry_run = dry_run
        self.config = config
        self.logger = logging.getLogger("TrelloAdapter")

        # API client
        self._client = TrelloApiClient(
            api_key=config.api_key,
            api_token=config.api_token,
            board_id=config.board_id,
            api_url=config.api_url,
            dry_run=dry_run,
        )

        # Cache for lists and labels
        self._lists_cache: dict[str, dict] = {}  # name -> list data
        self._labels_cache: dict[str, dict] = {}  # name/color -> label data

    def _get_lists(self) -> dict[str, dict]:
        """Get all lists on the board, caching the result."""
        if not self._lists_cache:
            lists = self._client.get_board_lists()
            self._lists_cache = {list_data["name"]: list_data for list_data in lists}
        return self._lists_cache

    def _find_list(self, status_name: str) -> dict | None:
        """Find a list by status name."""
        # Check status_lists mapping first
        if status_name in self.config.status_lists:
            list_id_or_name = self.config.status_lists[status_name]
            # Try as ID first
            lists = self._get_lists()
            for list_data in lists.values():
                if list_data["id"] == list_id_or_name:
                    return list_data
            # Try as name
            if list_id_or_name in lists:
                return lists[list_id_or_name]

        # Try direct name match
        lists = self._get_lists()
        status_lower = status_name.lower()

        # Exact match
        for name, list_data in lists.items():
            if name.lower() == status_lower:
                return list_data

        # Partial match
        for name, list_data in lists.items():
            if status_lower in name.lower() or name.lower() in status_lower:
                return list_data

        # Try status mapping
        status_mapping = {
            "done": ["done", "complete", "finished", "closed"],
            "in progress": ["in progress", "doing", "active", "wip"],
            "planned": ["planned", "todo", "backlog", "to do"],
            "blocked": ["blocked", "on hold", "waiting"],
        }

        for _status_key, aliases in status_mapping.items():
            if status_lower in aliases:
                for name, list_data in lists.items():
                    if any(alias in name.lower() for alias in aliases):
                        return list_data

        return None

    def _get_labels(self) -> dict[str, dict]:
        """Get all labels on the board, caching the result."""
        if not self._labels_cache:
            labels = self._client.get_board_labels()
            # Index by both name and color
            self._labels_cache = {}
            for label in labels:
                if label.get("name"):
                    self._labels_cache[label["name"].lower()] = label
                if label.get("color"):
                    self._labels_cache[label["color"].lower()] = label
        return self._labels_cache

    def _find_label_for_priority(self, priority: str) -> dict | None:
        """Find or create a label for a priority."""
        priority_lower = priority.lower()

        # Check priority_labels mapping
        if priority_lower in self.config.priority_labels:
            color = self.config.priority_labels[priority_lower]
            label = self._client.get_label_by_color(color)
            if label:
                return label
            # Create if not found
            return self._client.create_label(color=color)

        # Try direct mapping
        priority_mapping = {
            "critical": "red",
            "high": "orange",
            "medium": "yellow",
            "low": "green",
        }

        priority_color: str | None = priority_mapping.get(priority_lower)
        if priority_color:
            label = self._client.get_label_by_color(priority_color)
            if label:
                return label
            return self._client.create_label(color=priority_color)

        return None

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Properties
    # -------------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "Trello"

    @property
    def is_connected(self) -> bool:
        return self._client.is_connected

    def test_connection(self) -> bool:
        if not self._client.test_connection():
            return False
        # Also verify board access
        try:
            self._client.get_board()
            return True
        except IssueTrackerError:
            return False

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Read Operations
    # -------------------------------------------------------------------------

    def get_current_user(self) -> dict[str, Any]:
        return self._client.get_current_user()

    def get_issue(self, issue_key: str) -> IssueData:
        """
        Fetch a single card by ID or short ID.

        Args:
            issue_key: Card ID or short ID
        """
        try:
            card = self._client.get_card(issue_key)
        except NotFoundError:
            # Try searching by short ID or name
            cards = self._client.get_board_cards()
            for c in cards:
                if c.get("shortLink") == issue_key or c.get("name", "").startswith(issue_key):
                    card = c
                    break
            else:
                raise NotFoundError(f"Card not found: {issue_key}")

        return self._parse_card(card)

    def get_epic_children(self, epic_key: str) -> list[IssueData]:
        """
        Fetch all children of an epic.

        In Trello, epics can be represented as:
        - A list (all cards in that list)
        - A label (all cards with that label)
        """
        try:
            # Try as list ID/name
            list_data = self._find_list(epic_key)
            if list_data:
                cards = self._client.get_list_cards(list_data["id"])
                return [self._parse_card(card) for card in cards]
        except Exception:
            pass

        # Try as label
        try:
            labels = self._get_labels()
            label = labels.get(epic_key.lower())
            if label:
                cards = self._client.get_board_cards()
                epic_cards = [
                    card
                    for card in cards
                    if any(l.get("id") == label["id"] for l in card.get("labels", []))
                ]
                return [self._parse_card(card) for card in epic_cards]
        except Exception:
            pass

        return []

    def get_issue_comments(self, issue_key: str) -> list[dict]:
        return self._client.get_card_comments(issue_key)

    def get_issue_status(self, issue_key: str) -> str:
        """Get the current status (list name) of a card."""
        card = self._client.get_card(issue_key)
        list_id = card.get("idList")
        if list_id:
            lists = self._get_lists()
            for list_data in lists.values():
                if list_data["id"] == list_id:
                    name = list_data.get("name", "Unknown")
                    return str(name)
        return "Unknown"

    def search_issues(self, query: str, max_results: int = 50) -> list[IssueData]:
        """
        Search for cards.

        Trello doesn't have a full-text search API, so we search within the board.
        """
        cards = self._client.get_board_cards()
        query_lower = query.lower()

        matching = []
        for card in cards:
            name = card.get("name", "").lower()
            desc = card.get("desc", "").lower()
            if query_lower in name or query_lower in desc:
                matching.append(self._parse_card(card))
                if len(matching) >= max_results:
                    break

        return matching

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Write Operations
    # -------------------------------------------------------------------------

    def update_issue_description(self, issue_key: str, description: Any) -> bool:
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would update description for {issue_key}")
            return True

        desc_str = description if isinstance(description, str) else str(description)
        self._client.update_card(issue_key, desc=desc_str)
        self.logger.info(f"Updated description for {issue_key}")
        return True

    def update_issue_story_points(self, issue_key: str, story_points: float) -> bool:
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would update story points for {issue_key} to {story_points}"
            )
            return True

        # Trello doesn't have native story points, so we add it to the description
        card = self._client.get_card(issue_key)
        desc = card.get("desc", "")
        # Update or add story points line
        lines = desc.split("\n")
        updated = False
        for i, line in enumerate(lines):
            if line.strip().startswith("**Story Points:**"):
                lines[i] = f"**Story Points:** {int(story_points)}"
                updated = True
                break

        if not updated:
            lines.insert(0, f"**Story Points:** {int(story_points)}")

        new_desc = "\n".join(lines)
        self._client.update_card(issue_key, desc=new_desc)
        self.logger.info(f"Updated story points for {issue_key} to {story_points}")
        return True

    def get_issue_due_date(self, issue_key: str) -> str | None:
        """
        Get the due date for an issue.

        Args:
            issue_key: Issue key (card ID)

        Returns:
            Due date in ISO 8601 format, or None if not set
        """
        card = self._client.get_card(issue_key)
        return card.get("due")

    def update_issue_due_date(
        self,
        issue_key: str,
        due_date: str | None,
    ) -> bool:
        """
        Set or clear the due date for an issue.

        Args:
            issue_key: Issue key (card ID)
            due_date: Due date in ISO 8601 format (e.g., "2024-01-15T12:00:00Z"),
                      or None to clear the due date

        Returns:
            True if successful
        """
        if self._dry_run:
            action = "clear" if due_date is None else f"set to {due_date}"
            self.logger.info(f"[DRY-RUN] Would {action} due date for {issue_key}")
            return True

        self._client.update_card(issue_key, due=due_date)
        action = "Cleared" if due_date is None else f"Set due date to {due_date} for"
        self.logger.info(f"{action} {issue_key}")
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
        Create a subtask.

        In Trello, subtasks can be:
        - Checklist items (default)
        - Linked cards (if subtask_mode is "linked_card")
        """
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would create subtask '{summary[:50]}...' under {parent_key}"
            )
            return None

        if self.config.subtask_mode == "linked_card":
            # Create a linked card
            parent_card = self._client.get_card(parent_key)
            parent_list_id: str | None = parent_card.get("idList")

            if not parent_list_id:
                raise IssueTrackerError(f"Parent card {parent_key} has no list ID")

            desc_str = description if isinstance(description, str) else str(description)
            if story_points:
                desc_str = f"**Story Points:** {story_points}\n\n{desc_str}"

            # Create card in same list
            card = self._client.create_card(
                name=summary,
                list_id=parent_list_id,
                desc=desc_str,
            )

            # Link to parent (add parent card ID to description)
            parent_desc = parent_card.get("desc", "")
            if f"[{summary}]({card['shortUrl']})" not in parent_desc:
                parent_desc += f"\n\n- [{summary}]({card['shortUrl']})"
                self._client.update_card(parent_key, desc=parent_desc)

            self.logger.info(f"Created subtask card {card['id']} under {parent_key}")
            return str(card["id"])
        # Create checklist item (default)
        card = self._client.get_card(parent_key)

        # Get or create checklist
        checklists = self._client.get_card_checklists(parent_key)
        checklist = checklists[0] if checklists else None

        if not checklist:
            checklist = self._client.create_checklist(parent_key, "Subtasks")

        # Add item to checklist
        item = self._client.add_checklist_item(
            checklist_id=checklist["id"],
            name=summary,
            checked=False,
        )

        # Add description as comment if provided
        if description:
            desc_str = description if isinstance(description, str) else str(description)
            self._client.add_comment(parent_key, f"**{summary}:**\n{desc_str}")

        self.logger.info(f"Created subtask checklist item '{summary}' under {parent_key}")
        return item.get("id")

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

        # For checklist items, we can't update them directly via API
        # For linked cards, update as normal card
        updates: dict[str, Any] = {}

        if description is not None:
            updates["desc"] = description if isinstance(description, str) else str(description)

        if story_points is not None:
            card = self._client.get_card(issue_key)
            desc = card.get("desc", "")
            lines = desc.split("\n")
            updated = False
            for i, line in enumerate(lines):
                if line.strip().startswith("**Story Points:**"):
                    lines[i] = f"**Story Points:** {story_points}"
                    updated = True
                    break
            if not updated:
                lines.insert(0, f"**Story Points:** {story_points}")
            updates["desc"] = "\n".join(lines)

        if updates:
            self._client.update_card(issue_key, **updates)
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
        Transition a card to a new list (status).

        Trello uses lists for status, so we move the card to the target list.
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would transition {issue_key} to {target_status}")
            return True

        target_list = self._find_list(target_status)
        if not target_list:
            raise TransitionError(
                f"List not found for status: {target_status}. "
                f"Available lists: {list(self._get_lists().keys())}",
                issue_key=issue_key,
            )

        try:
            self._client.move_card_to_list(issue_key, target_list["id"])
            self.logger.info(f"Transitioned {issue_key} to {target_list['name']}")
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
        Get available transitions (lists) for a card.

        In Trello, any card can move to any list on the board.
        """
        lists = self._get_lists()
        return [
            {
                "id": list_data["id"],
                "name": list_data["name"],
                "to": list_data["name"],
            }
            for list_data in lists.values()
        ]

    def format_description(self, markdown: str) -> Any:
        """
        Convert markdown to Trello-compatible format.

        Trello uses Markdown natively, so we just return the input.
        """
        return markdown

    # -------------------------------------------------------------------------
    # Webhook Methods
    # -------------------------------------------------------------------------

    def create_webhook(
        self,
        callback_url: str,
        model_id: str | None = None,
        description: str | None = None,
        active: bool = True,
    ) -> dict[str, Any]:
        """
        Create a webhook subscription for the board or a specific model.

        Trello webhooks notify when changes occur to the specified model.
        If model_id is not provided, defaults to the configured board.

        Args:
            callback_url: URL to receive webhook events
            model_id: Optional ID of board, card, or list to watch (defaults to board_id)
            description: Optional description for the webhook
            active: Whether the webhook is active (default: True)

        Returns:
            Webhook subscription data
        """
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would create webhook for model {model_id or self.config.board_id}"
            )
            return {
                "id": "webhook:dry-run",
                "idModel": model_id or self.config.board_id,
                "callbackURL": callback_url,
                "active": active,
            }

        return self._client.create_webhook(
            model_id=model_id or self.config.board_id,
            callback_url=callback_url,
            description=description,
            active=active,
        )

    def list_webhooks(self) -> list[dict[str, Any]]:
        """
        List webhook subscriptions for the authenticated token.

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
        callback_url: str | None = None,
        description: str | None = None,
        active: bool | None = None,
    ) -> dict[str, Any]:
        """
        Update a webhook subscription.

        Args:
            webhook_id: Webhook ID to update
            callback_url: New callback URL (optional)
            description: New description (optional)
            active: New active status (optional)

        Returns:
            Updated webhook data
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would update webhook {webhook_id}")
            return {"id": webhook_id}

        return self._client.update_webhook(
            webhook_id=webhook_id,
            callback_url=callback_url,
            description=description,
            active=active,
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
    # Power-Ups & Custom Fields Methods
    # -------------------------------------------------------------------------

    def get_installed_power_ups(self) -> list[dict[str, Any]]:
        """
        Get installed Power-Ups (plugins) for the board.

        Returns:
            List of installed Power-Ups with their metadata
        """
        return self._client.get_board_plugins()

    def get_custom_fields(self, card_id: str) -> list[dict[str, Any]]:
        """
        Get custom field values for a card.

        Custom fields are typically added by Power-Ups.
        This requires Power-Ups to be installed on the board.

        Args:
            card_id: Card ID

        Returns:
            List of custom field items with their values
        """
        return self._client.get_card_custom_fields(card_id)

    def get_board_custom_field_definitions(self) -> list[dict[str, Any]]:
        """
        Get all custom field definitions for the board.

        Returns:
            List of custom field definitions
        """
        return self._client.get_board_custom_fields()

    def set_custom_field(
        self,
        card_id: str,
        custom_field_id: str,
        value: str | int | float | bool | list[str] | None,
    ) -> bool:
        """
        Set a custom field value on a card.

        Args:
            card_id: Card ID
            custom_field_id: Custom field ID (get from get_board_custom_field_definitions)
            value: Value to set (type depends on custom field type)

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would set custom field {custom_field_id} on card {card_id}"
            )
            return True

        self._client.set_custom_field(card_id, custom_field_id, value)
        self.logger.info(f"Set custom field {custom_field_id} on card {card_id}")
        return True

    # -------------------------------------------------------------------------
    # Attachment Methods
    # -------------------------------------------------------------------------

    def get_card_attachments(self, card_id: str) -> list[dict[str, Any]]:
        """
        Get all attachments for a card.

        Args:
            card_id: Card ID

        Returns:
            List of attachment dictionaries with id, name, url, etc.
        """
        return self._client.get_card_attachments(card_id)

    def upload_card_attachment(
        self,
        card_id: str,
        file_path: str,
        name: str | None = None,
    ) -> dict[str, Any]:
        """
        Upload a file attachment to a card.

        Args:
            card_id: Card ID
            file_path: Path to file to upload
            name: Optional attachment name (defaults to filename)

        Returns:
            Attachment information dictionary
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would upload attachment {file_path} to card {card_id}")
            return {"id": "attachment:dry-run", "name": name or file_path}

        return self._client.upload_card_attachment(card_id, file_path, name)

    def delete_card_attachment(self, attachment_id: str) -> bool:
        """
        Delete an attachment from a card.

        Args:
            attachment_id: Attachment ID to delete

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would delete attachment {attachment_id}")
            return True

        self._client.delete_card_attachment(attachment_id)
        self.logger.info(f"Deleted attachment {attachment_id}")
        return True

    def get_custom_field_value(
        self,
        card_id: str,
        custom_field_name: str,
    ) -> str | int | float | bool | list[str] | None:
        """
        Get a custom field value from a card by field name.

        Args:
            card_id: Card ID
            custom_field_name: Custom field name (case-insensitive)

        Returns:
            Field value or None if not found
        """
        custom_fields = self._client.get_card_custom_fields(card_id)
        name_lower = custom_field_name.lower()

        for field_item in custom_fields:
            # Get field definition to check name
            field_id = field_item.get("idCustomField")
            if field_id:
                try:
                    field_def = self._client.get_custom_field_definition(field_id)
                    if field_def.get("name", "").lower() == name_lower:
                        # Extract value based on type
                        value: Any = field_item.get("value")
                        if isinstance(value, dict):
                            if "number" in value:
                                try:
                                    num_val = value["number"]
                                    return float(str(num_val))
                                except (ValueError, TypeError):
                                    pass
                            if "text" in value:
                                return str(value["text"])
                            if "checked" in value:
                                checked_val = value["checked"]
                                return str(checked_val) == "true"
                            if "date" in value:
                                return str(value["date"])
                        elif isinstance(value, list):
                            return [str(v) for v in value]  # Convert to list[str]
                        elif value is not None:
                            return str(value)
                        return None
                except Exception:
                    # If we can't get field definition, try to match by ID
                    pass

        return None

    # -------------------------------------------------------------------------
    # Private Methods
    # -------------------------------------------------------------------------

    def _parse_card(self, card_data: dict) -> IssueData:
        """Parse Trello card API response into IssueData."""
        # Get status (list name)
        list_id = card_data.get("idList")
        status = "Unknown"
        if list_id:
            lists = self._get_lists()
            for list_data in lists.values():
                if list_data["id"] == list_id:
                    status = list_data.get("name", "Unknown")
                    break

        # Get story points from description
        story_points = None
        desc = card_data.get("desc", "")
        for line in desc.split("\n"):
            if line.strip().startswith("**Story Points:**"):
                from contextlib import suppress

                with suppress(ValueError, IndexError):
                    story_points = float(line.split(":")[1].strip())
                break

        # Parse subtasks (checklist items)
        subtasks = []
        checklists = card_data.get("checklists", [])
        for checklist in checklists:
            for item in checklist.get("checkItems", []):
                subtasks.append(
                    IssueData(
                        key=item.get("id", ""),
                        summary=item.get("name", ""),
                        status="Done" if item.get("state") == "complete" else "In Progress",
                        issue_type="Subtask",
                    )
                )

        # Parse comments
        comments: list[dict[str, Any]] = []
        # Comments are fetched separately via get_card_comments

        # Parse due date
        due_date = card_data.get("due")  # ISO 8601 format from Trello

        return IssueData(
            key=card_data.get("id", ""),
            summary=card_data.get("name", ""),
            description=card_data.get("desc"),
            status=status,
            issue_type="Story",
            assignee=None,  # Trello doesn't expose assignee in basic card data
            story_points=story_points,
            due_date=due_date,
            subtasks=subtasks,
            comments=comments,
        )
