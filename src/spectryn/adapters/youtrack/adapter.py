"""
YouTrack Adapter - Implements IssueTrackerPort for JetBrains YouTrack.

This is the main entry point for YouTrack integration.
Maps the generic IssueTrackerPort interface to YouTrack's issue model.

Key mappings:
- Epic -> Epic issue type
- Story -> Task or User Story issue type
- Subtask -> Subtask issue type
- Status -> State field
- Priority -> Priority field
- Story Points -> Story points custom field
"""

import contextlib
import logging
from typing import Any

from spectryn.core.domain.enums import Priority, Status
from spectryn.core.ports.config_provider import YouTrackConfig
from spectryn.core.ports.issue_tracker import (
    IssueData,
    IssueLink,
    IssueTrackerError,
    IssueTrackerPort,
    LinkType,
    NotFoundError,
    TransitionError,
)

from .client import YouTrackApiClient


class YouTrackAdapter(IssueTrackerPort):
    """
    YouTrack implementation of the IssueTrackerPort.

    Translates between domain entities and YouTrack's REST API.

    YouTrack concepts:
    - Project: Container for issues (like a Jira project)
    - Issue: Work item (Epic, Task, User Story, Subtask, Bug, etc.)
    - State: Workflow state (Open, In Progress, Done, etc.)
    - Priority: Priority level (Critical, High, Normal, Low)
    - Custom Fields: Extensible fields (Story Points, etc.)
    - Links: Issue-to-issue relationships
    """

    def __init__(
        self,
        config: YouTrackConfig,
        dry_run: bool = True,
    ):
        """
        Initialize the YouTrack adapter.

        Args:
            config: YouTrack configuration
            dry_run: If True, don't make changes
        """
        self.config = config
        self._dry_run = dry_run
        self.logger = logging.getLogger("YouTrackAdapter")

        # API client
        self._client = YouTrackApiClient(
            url=config.url,
            token=config.token,
            dry_run=dry_run,
        )

        # Cache for states and priorities
        self._states_cache: list[dict[str, Any]] | None = None
        self._priorities_cache: list[dict[str, Any]] | None = None

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Properties
    # -------------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "YouTrack"

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
        """Fetch a single issue by key."""
        data = self._client.get_issue(issue_key)
        return self._parse_issue(data)

    def get_epic_children(self, epic_key: str) -> list[IssueData]:
        """Fetch all children of an epic."""
        # YouTrack uses links to connect epics to their children
        # Search for issues that are linked to this epic
        children_data = self._client.get_epic_children(epic_key)
        return [self._parse_issue(child) for child in children_data]

    def get_issue_comments(self, issue_key: str) -> list[dict]:
        """Fetch all comments on an issue."""
        return self._client.get_issue_comments(issue_key)

    def get_issue_status(self, issue_key: str) -> str:
        """Get the current status of an issue."""
        issue = self._client.get_issue(issue_key)
        return self._extract_status(issue)

    def search_issues(self, query: str, max_results: int = 50) -> list[IssueData]:
        """
        Search for issues using YouTrack Query Language (YQL).

        Args:
            query: YQL query (e.g., "project: PROJ State: Open")
            max_results: Maximum results to return
        """
        issues = self._client.search_issues(query, max_results=max_results)
        return [self._parse_issue(issue) for issue in issues]

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Write Operations
    # -------------------------------------------------------------------------

    def update_issue_description(self, issue_key: str, description: Any) -> bool:
        """Update an issue's description."""
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would update description for {issue_key}")
            return True

        # YouTrack uses Markdown for descriptions
        body = description if isinstance(description, str) else str(description)

        self._client.update_issue(issue_key, description=body)
        self.logger.info(f"Updated description for {issue_key}")
        return True

    def update_issue_story_points(self, issue_key: str, story_points: float) -> bool:
        """Update an issue's story points."""
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would update story points for {issue_key} to {story_points}"
            )
            return True

        # Update story points via custom field
        if self.config.story_points_field:
            # YouTrack custom fields need to be updated via the customFields array
            # This is a simplified implementation - may need adjustment
            custom_field_update: dict[str, Any] = {
                self.config.story_points_field: story_points,
            }
            self._client.update_issue(
                issue_key,
                **custom_field_update,  # type: ignore[arg-type]
            )
            self.logger.info(f"Updated story points for {issue_key} to {story_points}")
        else:
            self.logger.warning(f"Story points field not configured, cannot update {issue_key}")
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
        """Create a subtask under a parent issue."""
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would create subtask '{summary[:50]}...' under {parent_key}"
            )
            # Return mock ID for dry-run mode
            return f"{parent_key}-subtask"

        body = description if isinstance(description, str) else str(description)

        # Prepare issue data
        issue_data: dict[str, Any] = {}
        if story_points and self.config.story_points_field:
            issue_data[self.config.story_points_field] = story_points
        if assignee:
            issue_data["assignee"] = {"login": assignee}
        if priority:
            priority_value = self._map_priority_to_youtrack(priority)
            if priority_value:
                issue_data[self.config.priority_field] = {"name": priority_value}

        # Create the subtask
        result = self._client.create_issue(
            project_id=project_key or self.config.project_id,
            summary=summary,
            issue_type=self.config.subtask_type,
            description=body,
            **issue_data,
        )

        # Link to parent
        if result.get("idReadable"):
            subtask_id = result["idReadable"]
            try:
                self._client.create_link(parent_key, subtask_id, "subtask of")
            except IssueTrackerError as e:
                self.logger.warning(f"Failed to link subtask to parent: {e}")

            self.logger.info(f"Created subtask {subtask_id} under {parent_key}")
            return str(subtask_id)

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

        updates: dict[str, Any] = {}

        if description is not None:
            updates["description"] = (
                description if isinstance(description, str) else str(description)
            )

        if story_points is not None and self.config.story_points_field:
            updates[self.config.story_points_field] = story_points

        if assignee is not None:
            updates["assignee"] = {"login": assignee}

        if priority_id is not None:
            updates[self.config.priority_field] = {"name": priority_id}

        if updates:
            self._client.update_issue(issue_key, **updates)
            self.logger.info(f"Updated subtask {issue_key}")

        return True

    def add_comment(self, issue_key: str, body: Any) -> bool:
        """Add a comment to an issue."""
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would add comment to {issue_key}")
            return True

        comment_text = body if isinstance(body, str) else str(body)
        self._client.add_comment(issue_key, comment_text)
        self.logger.info(f"Added comment to {issue_key}")
        return True

    def transition_issue(self, issue_key: str, target_status: str) -> bool:
        """Transition an issue to a new status."""
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would transition {issue_key} to {target_status}")
            return True

        # Map status to YouTrack state name
        state_name = self._map_status_to_youtrack_state(target_status)

        try:
            self._client.transition_issue(issue_key, state_name)
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
        """Get available transitions for an issue."""
        # Get available states for the project
        states = self._get_available_states()
        return [{"id": state.get("name", ""), "name": state.get("name", "")} for state in states]

    def format_description(self, markdown: str) -> Any:
        """
        Convert markdown to YouTrack-compatible format.

        YouTrack uses Markdown natively, so we just return the input.
        """
        return markdown

    # -------------------------------------------------------------------------
    # Link Operations
    # -------------------------------------------------------------------------

    def get_issue_links(self, issue_key: str) -> list[IssueLink]:
        """Get all links for an issue."""
        links_data = self._client.get_issue_links(issue_key)
        links: list[IssueLink] = []

        for link_data in links_data:
            link_type_name = link_data.get("linkType", {}).get("name", "").lower()
            target_issue = link_data.get("target", {}).get("idReadable", "")

            if target_issue:
                link_type = self._map_youtrack_link_type(link_type_name)
                links.append(
                    IssueLink(
                        link_type=link_type,
                        target_key=target_issue,
                        source_key=issue_key,
                    )
                )

        return links

    def create_link(
        self,
        source_key: str,
        target_key: str,
        link_type: LinkType,
    ) -> bool:
        """Create a link between two issues."""
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would create link: {source_key} {link_type.value} {target_key}"
            )
            return True

        youtrack_link_type = self._map_link_type_to_youtrack(link_type)
        try:
            self._client.create_link(source_key, target_key, youtrack_link_type)
            self.logger.info(f"Created link: {source_key} {link_type.value} {target_key}")
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
        """Delete a link between issues."""
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would delete link: {source_key} -> {target_key}")
            return True

        # YouTrack API doesn't have a direct delete link endpoint
        # This would need to be implemented via command execution
        self.logger.warning("Delete link not yet implemented for YouTrack")
        return False

    def get_link_types(self) -> list[dict[str, Any]]:
        """Get available link types from YouTrack."""
        # Common YouTrack link types
        return [
            {"name": "depends on", "inward": "is dependency of", "outward": "depends on"},
            {"name": "relates to", "inward": "relates to", "outward": "relates to"},
            {"name": "duplicates", "inward": "is duplicated by", "outward": "duplicates"},
            {"name": "blocks", "inward": "is blocked by", "outward": "blocks"},
        ]

    # -------------------------------------------------------------------------
    # Custom Fields Operations
    # -------------------------------------------------------------------------

    def get_project_custom_fields(self) -> list[dict[str, Any]]:
        """
        Get all custom field definitions for the configured project.

        Returns:
            List of custom field definitions with id, name, type, etc.
        """
        fields = self._client.get_project_custom_fields(self.config.project_id)
        return [
            {
                "id": f.get("id", ""),
                "name": f.get("name", ""),
                "field_name": f.get("field", {}).get("name", ""),
                "field_type": f.get("field", {}).get("fieldType", {}).get("presentation", ""),
            }
            for f in fields
        ]

    def get_issue_custom_fields(self, issue_key: str) -> list[dict[str, Any]]:
        """
        Get all custom field values for an issue.

        Args:
            issue_key: Issue key (e.g., "PROJ-123")

        Returns:
            List of custom field values with name, value, type, etc.
        """
        fields = self._client.get_issue_custom_fields(issue_key)
        result = []
        for field in fields:
            value = field.get("value")
            # Extract the actual value depending on type
            if isinstance(value, dict):
                # Enum, state, user, etc.
                extracted_value = (
                    value.get("name")
                    or value.get("login")
                    or value.get("presentation")
                    or value.get("text")
                )
            elif isinstance(value, list):
                # Multi-value fields
                extracted_value = [
                    v.get("name") or v.get("login") or str(v) for v in value if isinstance(v, dict)
                ]
            else:
                extracted_value = value

            result.append(
                {
                    "id": field.get("id", ""),
                    "name": field.get("name", ""),
                    "value": extracted_value,
                    "raw_value": value,
                    "type": field.get("$type", ""),
                }
            )
        return result

    def get_issue_custom_field(
        self,
        issue_key: str,
        field_name: str,
    ) -> Any | None:
        """
        Get a specific custom field value for an issue.

        Args:
            issue_key: Issue key (e.g., "PROJ-123")
            field_name: Custom field name

        Returns:
            The custom field value, or None if not found
        """
        fields = self.get_issue_custom_fields(issue_key)
        for field in fields:
            if field.get("name") == field_name:
                return field.get("value")
        return None

    def update_issue_custom_field(
        self,
        issue_key: str,
        field_name: str,
        value: Any,
    ) -> bool:
        """
        Update a custom field value for an issue.

        Args:
            issue_key: Issue key (e.g., "PROJ-123")
            field_name: Custom field name
            value: New value (format depends on field type)
                   - Simple values: str, int, float
                   - Enum/state fields: "value_name" (will be wrapped automatically)
                   - User fields: "username" (will be wrapped automatically)
                   - Date fields: timestamp in milliseconds or ISO date string

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would update custom field '{field_name}' for {issue_key} to {value}"
            )
            return True

        try:
            self._client.update_issue_custom_field(issue_key, field_name, value)
            self.logger.info(f"Updated custom field '{field_name}' for {issue_key}")
            return True
        except (NotFoundError, IssueTrackerError) as e:
            self.logger.error(f"Failed to update custom field: {e}")
            return False

    def get_custom_field_options(
        self,
        field_name: str,
    ) -> list[dict[str, Any]]:
        """
        Get available options for an enum-like custom field.

        Args:
            field_name: Custom field name

        Returns:
            List of available options with name, id, etc.
        """
        # Get the field definition to find the bundle
        fields = self._client.get_project_custom_fields(self.config.project_id)
        for field in fields:
            if field.get("name") == field_name or field.get("field", {}).get("name") == field_name:
                # Try to get the bundle values
                field_def = field.get("field", {})
                field_type = field_def.get("fieldType", {}).get("id", "")

                # Determine bundle type from field type
                if "EnumBundleElement" in field_type:
                    bundle_type = "enum"
                elif "StateBundleElement" in field_type:
                    bundle_type = "state"
                elif "OwnedBundleElement" in field_type:
                    bundle_type = "ownedField"
                else:
                    # Field doesn't have a bundle
                    return []

                # Get bundle ID from field
                bundle_id = field_def.get("bundle", {}).get("id")
                if bundle_id:
                    bundle = self._client.get_custom_field_bundle(bundle_type, bundle_id)
                    values = bundle.get("values", [])
                    return [
                        {
                            "id": v.get("id", ""),
                            "name": v.get("name", ""),
                            "description": v.get("description", ""),
                            "color": v.get("color", {}).get("id")
                            if isinstance(v.get("color"), dict)
                            else None,
                        }
                        for v in values
                    ]
        return []

    # -------------------------------------------------------------------------
    # Bulk Operations
    # -------------------------------------------------------------------------

    def bulk_create_issues(
        self,
        issues: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Create multiple issues in a batch.

        Args:
            issues: List of issue data dictionaries, each containing:
                    - summary: Issue summary (required)
                    - description: Issue description (optional)
                    - Additional fields as needed

        Returns:
            List of created issue data with keys
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would create {len(issues)} issues in bulk")
            return [
                {"key": f"{self.config.project_id}-{i}", "status": "dry-run"}
                for i in range(len(issues))
            ]

        # Add project to each issue
        prepared_issues = []
        for issue in issues:
            prepared = dict(issue)
            prepared["project"] = {"id": self.config.project_id}
            prepared_issues.append(prepared)

        results = self._client.bulk_create_issues(prepared_issues)
        return [{"key": r.get("idReadable", r.get("id", "")), **r} for r in results]

    def bulk_update_issues(
        self,
        updates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Update multiple issues in a batch.

        Args:
            updates: List of update dictionaries, each containing:
                     - id: Issue key (e.g., "PROJ-123")
                     - Fields to update (summary, description, etc.)

        Returns:
            List of update results
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would update {len(updates)} issues in bulk")
            return [{"id": u.get("id"), "status": "dry-run"} for u in updates]

        return self._client.bulk_update_issues(updates)

    def bulk_delete_issues(
        self,
        issue_keys: list[str],
    ) -> list[dict[str, Any]]:
        """
        Delete multiple issues in a batch.

        Args:
            issue_keys: List of issue keys to delete

        Returns:
            List of deletion results
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would delete {len(issue_keys)} issues in bulk")
            return [{"id": key, "status": "dry-run"} for key in issue_keys]

        return self._client.bulk_delete_issues(issue_keys)

    def bulk_transition_issues(
        self,
        issue_keys: list[str],
        target_status: str,
        comment: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Transition multiple issues to a new status.

        Args:
            issue_keys: List of issue keys
            target_status: Target status name
            comment: Optional comment for the transition

        Returns:
            List of transition results
        """
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would transition {len(issue_keys)} issues to '{target_status}'"
            )
            return [{"id": key, "status": "dry-run"} for key in issue_keys]

        # Map status to YouTrack state
        youtrack_state = self._map_status_to_youtrack_state(target_status)
        command = f"State {youtrack_state}"

        return self._client.bulk_execute_command(issue_keys, command, comment)

    # -------------------------------------------------------------------------
    # File Attachment Operations
    # -------------------------------------------------------------------------

    def get_issue_attachments(self, issue_key: str) -> list[dict[str, Any]]:
        """
        Get all file attachments for an issue.

        Args:
            issue_key: Issue key (e.g., "PROJ-123")

        Returns:
            List of attachment dictionaries with id, name, size, etc.
        """
        attachments = self._client.get_issue_attachments(issue_key)
        return [
            {
                "id": a.get("id", ""),
                "name": a.get("name", ""),
                "url": a.get("url", ""),
                "size": a.get("size", 0),
                "mime_type": a.get("mimeType", ""),
                "created": a.get("created"),
                "author": a.get("author", {}).get("login") or a.get("author", {}).get("name"),
            }
            for a in attachments
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
            issue_key: Issue key (e.g., "PROJ-123")
            file_path: Path to file to upload
            name: Optional attachment name

        Returns:
            Attachment information dictionary
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would upload {file_path} to {issue_key}")
            return {"id": "attachment:dry-run", "name": name or file_path}

        result = self._client.upload_attachment(issue_key, file_path, name)
        self.logger.info(f"Uploaded attachment to {issue_key}: {result.get('name')}")
        return result

    def delete_attachment(
        self,
        issue_key: str,
        attachment_id: str,
    ) -> bool:
        """
        Delete a file attachment from an issue.

        Args:
            issue_key: Issue key (e.g., "PROJ-123")
            attachment_id: Attachment ID to delete

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would delete attachment {attachment_id} from {issue_key}")
            return True

        try:
            self._client.delete_attachment(issue_key, attachment_id)
            self.logger.info(f"Deleted attachment {attachment_id} from {issue_key}")
            return True
        except (NotFoundError, IssueTrackerError) as e:
            self.logger.error(f"Failed to delete attachment: {e}")
            return False

    def download_attachment(
        self,
        issue_key: str,
        attachment_id: str,
        download_path: str,
    ) -> bool:
        """
        Download an attachment to a local file.

        Args:
            issue_key: Issue key (e.g., "PROJ-123")
            attachment_id: Attachment ID to download
            download_path: Path to save the file

        Returns:
            True if download was successful
        """
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would download attachment {attachment_id} to {download_path}"
            )
            return True

        try:
            result = self._client.download_attachment(issue_key, attachment_id, download_path)
            self.logger.info(f"Downloaded attachment {attachment_id} to {result}")
            return result is not None
        except (NotFoundError, IssueTrackerError) as e:
            self.logger.error(f"Failed to download attachment: {e}")
            return False

    # -------------------------------------------------------------------------
    # Workflow & Commands Operations
    # -------------------------------------------------------------------------

    def execute_command(
        self,
        issue_key: str,
        command: str,
        comment: str | None = None,
    ) -> bool:
        """
        Execute a YouTrack command on an issue.

        Args:
            issue_key: Issue key (e.g., "PROJ-123")
            command: Command string (e.g., "State In Progress", "Priority Critical")
            comment: Optional comment to add

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would execute command '{command}' on {issue_key}")
            return True

        try:
            self._client.execute_command(issue_key, command, comment)
            self.logger.info(f"Executed command '{command}' on {issue_key}")
            return True
        except IssueTrackerError as e:
            self.logger.error(f"Failed to execute command: {e}")
            return False

    def get_available_commands(self, issue_key: str) -> list[dict[str, Any]]:
        """
        Get available commands for an issue.

        Args:
            issue_key: Issue key

        Returns:
            List of available commands
        """
        return self._client.get_available_commands(issue_key)

    # -------------------------------------------------------------------------
    # Due Dates Operations
    # -------------------------------------------------------------------------

    def get_issue_due_date(self, issue_key: str) -> str | None:
        """
        Get the due date for an issue.

        Args:
            issue_key: Issue key (e.g., "PROJ-123")

        Returns:
            Due date as ISO 8601 string, or None if not set
        """
        timestamp = self._client.get_issue_due_date(issue_key)
        if timestamp is None:
            return None

        # Convert timestamp to ISO string
        from datetime import datetime, timezone

        dt = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
        return dt.isoformat()

    def update_issue_due_date(
        self,
        issue_key: str,
        due_date: str | None,
    ) -> bool:
        """
        Set or clear the due date for an issue.

        Args:
            issue_key: Issue key (e.g., "PROJ-123")
            due_date: Due date in ISO 8601 format, or None to clear

        Returns:
            True if successful
        """
        if self._dry_run:
            action = "clear" if due_date is None else f"set to {due_date}"
            self.logger.info(f"[DRY-RUN] Would {action} due date for {issue_key}")
            return True

        try:
            self._client.set_issue_due_date(issue_key, due_date)
            action = "Cleared" if due_date is None else f"Set to {due_date}"
            self.logger.info(f"{action} due date for {issue_key}")
            return True
        except (NotFoundError, IssueTrackerError) as e:
            self.logger.error(f"Failed to update due date: {e}")
            return False

    # -------------------------------------------------------------------------
    # Tags/Labels Operations
    # -------------------------------------------------------------------------

    def get_issue_tags(self, issue_key: str) -> list[dict[str, Any]]:
        """
        Get all tags for an issue.

        Args:
            issue_key: Issue key (e.g., "PROJ-123")

        Returns:
            List of tag dictionaries with id, name, color
        """
        tags = self._client.get_issue_tags(issue_key)
        return [
            {
                "id": t.get("id", ""),
                "name": t.get("name", ""),
                "color": t.get("color", {}).get("background")
                if isinstance(t.get("color"), dict)
                else None,
            }
            for t in tags
        ]

    def add_issue_tag(self, issue_key: str, tag_name: str) -> bool:
        """
        Add a tag to an issue.

        Args:
            issue_key: Issue key (e.g., "PROJ-123")
            tag_name: Tag name to add

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would add tag '{tag_name}' to {issue_key}")
            return True

        try:
            self._client.add_issue_tag(issue_key, tag_name)
            self.logger.info(f"Added tag '{tag_name}' to {issue_key}")
            return True
        except IssueTrackerError as e:
            self.logger.error(f"Failed to add tag: {e}")
            return False

    def remove_issue_tag(self, issue_key: str, tag_name: str) -> bool:
        """
        Remove a tag from an issue.

        Args:
            issue_key: Issue key (e.g., "PROJ-123")
            tag_name: Tag name to remove

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would remove tag '{tag_name}' from {issue_key}")
            return True

        try:
            self._client.remove_issue_tag(issue_key, tag_name)
            self.logger.info(f"Removed tag '{tag_name}' from {issue_key}")
            return True
        except IssueTrackerError as e:
            self.logger.error(f"Failed to remove tag: {e}")
            return False

    def get_available_tags(self) -> list[dict[str, Any]]:
        """
        Get all available tags for the project.

        Returns:
            List of available tag dictionaries
        """
        tags = self._client.get_project_tags(self.config.project_id)
        return [
            {
                "id": t.get("id", ""),
                "name": t.get("name", ""),
                "color": t.get("color", {}).get("background")
                if isinstance(t.get("color"), dict)
                else None,
            }
            for t in tags
        ]

    # -------------------------------------------------------------------------
    # Watchers/Observers Operations
    # -------------------------------------------------------------------------

    def get_issue_watchers(self, issue_key: str) -> list[dict[str, Any]]:
        """
        Get all watchers for an issue.

        Args:
            issue_key: Issue key (e.g., "PROJ-123")

        Returns:
            List of watcher dictionaries with login, name, email
        """
        watchers = self._client.get_issue_watchers(issue_key)
        return [
            {
                "id": w.get("id", ""),
                "login": w.get("login", ""),
                "name": w.get("name", ""),
                "email": w.get("email", ""),
            }
            for w in watchers
        ]

    def add_issue_watcher(self, issue_key: str, user_login: str) -> bool:
        """
        Add a watcher to an issue.

        Args:
            issue_key: Issue key (e.g., "PROJ-123")
            user_login: User login to add as watcher

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would add watcher '{user_login}' to {issue_key}")
            return True

        try:
            self._client.add_issue_watcher(issue_key, user_login)
            self.logger.info(f"Added watcher '{user_login}' to {issue_key}")
            return True
        except IssueTrackerError as e:
            self.logger.error(f"Failed to add watcher: {e}")
            return False

    def remove_issue_watcher(self, issue_key: str, user_login: str) -> bool:
        """
        Remove a watcher from an issue.

        Args:
            issue_key: Issue key (e.g., "PROJ-123")
            user_login: User login to remove

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would remove watcher '{user_login}' from {issue_key}")
            return True

        try:
            self._client.remove_issue_watcher(issue_key, user_login)
            self.logger.info(f"Removed watcher '{user_login}' from {issue_key}")
            return True
        except (NotFoundError, IssueTrackerError) as e:
            self.logger.error(f"Failed to remove watcher: {e}")
            return False

    def is_watching(self, issue_key: str, user_login: str | None = None) -> bool:
        """
        Check if a user is watching an issue.

        Args:
            issue_key: Issue key (e.g., "PROJ-123")
            user_login: User login to check (defaults to current user)

        Returns:
            True if the user is watching
        """
        return self._client.is_watching(issue_key, user_login)

    # -------------------------------------------------------------------------
    # Agile Boards Operations
    # -------------------------------------------------------------------------

    def get_agile_boards(self) -> list[dict[str, Any]]:
        """
        Get all agile boards.

        Returns:
            List of board dictionaries with id, name, owner, projects
        """
        boards = self._client.get_agile_boards()
        return [
            {
                "id": b.get("id", ""),
                "name": b.get("name", ""),
                "owner": b.get("owner", {}).get("login") or b.get("owner", {}).get("name"),
                "projects": [p.get("shortName") for p in b.get("projects", [])],
            }
            for b in boards
        ]

    def get_agile_board(self, board_id: str) -> dict[str, Any]:
        """
        Get a specific agile board.

        Args:
            board_id: Board ID

        Returns:
            Board information with sprints
        """
        board = self._client.get_agile_board(board_id)
        return {
            "id": board.get("id", ""),
            "name": board.get("name", ""),
            "owner": board.get("owner", {}).get("login") or board.get("owner", {}).get("name"),
            "projects": [p.get("shortName") for p in board.get("projects", [])],
            "sprints": [
                {"id": s.get("id"), "name": s.get("name")} for s in board.get("sprints", [])
            ],
        }

    # -------------------------------------------------------------------------
    # Sprints/Iterations Operations
    # -------------------------------------------------------------------------

    def get_board_sprints(self, board_id: str) -> list[dict[str, Any]]:
        """
        Get all sprints for an agile board.

        Args:
            board_id: Board ID

        Returns:
            List of sprint dictionaries
        """
        sprints = self._client.get_board_sprints(board_id)
        return [
            {
                "id": s.get("id", ""),
                "name": s.get("name", ""),
                "start": s.get("start"),
                "finish": s.get("finish"),
                "goal": s.get("goal"),
                "is_default": s.get("isDefault", False),
                "archived": s.get("archived", False),
            }
            for s in sprints
        ]

    def get_sprint(self, board_id: str, sprint_id: str) -> dict[str, Any]:
        """
        Get a specific sprint with issues.

        Args:
            board_id: Board ID
            sprint_id: Sprint ID

        Returns:
            Sprint information with issues
        """
        sprint = self._client.get_sprint(board_id, sprint_id)
        return {
            "id": sprint.get("id", ""),
            "name": sprint.get("name", ""),
            "start": sprint.get("start"),
            "finish": sprint.get("finish"),
            "goal": sprint.get("goal"),
            "issues": [
                {"key": i.get("idReadable"), "summary": i.get("summary")}
                for i in sprint.get("issues", [])
            ],
        }

    def create_sprint(
        self,
        board_id: str,
        name: str,
        start: str | None = None,
        finish: str | None = None,
        goal: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a new sprint.

        Args:
            board_id: Board ID
            name: Sprint name
            start: Start date as ISO string
            finish: End date as ISO string
            goal: Sprint goal

        Returns:
            Created sprint data
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would create sprint '{name}'")
            return {"id": "sprint:dry-run", "name": name}

        # Convert ISO dates to timestamps
        start_ts = self._iso_to_timestamp(start) if start else None
        finish_ts = self._iso_to_timestamp(finish) if finish else None

        result = self._client.create_sprint(board_id, name, start_ts, finish_ts, goal)
        self.logger.info(f"Created sprint '{name}' on board {board_id}")
        return result

    def add_issue_to_sprint(
        self,
        board_id: str,
        sprint_id: str,
        issue_key: str,
    ) -> bool:
        """
        Add an issue to a sprint.

        Args:
            board_id: Board ID
            sprint_id: Sprint ID
            issue_key: Issue key to add

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would add {issue_key} to sprint {sprint_id}")
            return True

        try:
            self._client.add_issue_to_sprint(board_id, sprint_id, issue_key)
            self.logger.info(f"Added {issue_key} to sprint {sprint_id}")
            return True
        except IssueTrackerError as e:
            self.logger.error(f"Failed to add issue to sprint: {e}")
            return False

    def remove_issue_from_sprint(self, issue_key: str) -> bool:
        """
        Remove an issue from its current sprint.

        Args:
            issue_key: Issue key

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would remove {issue_key} from sprint")
            return True

        try:
            self._client.remove_issue_from_sprint(issue_key)
            self.logger.info(f"Removed {issue_key} from sprint")
            return True
        except IssueTrackerError as e:
            self.logger.error(f"Failed to remove issue from sprint: {e}")
            return False

    # -------------------------------------------------------------------------
    # Time Tracking Operations
    # -------------------------------------------------------------------------

    def get_issue_work_items(self, issue_key: str) -> list[dict[str, Any]]:
        """
        Get all work items (time entries) for an issue.

        Args:
            issue_key: Issue key

        Returns:
            List of work item dictionaries
        """
        items = self._client.get_issue_work_items(issue_key)
        return [
            {
                "id": i.get("id", ""),
                "author": i.get("author", {}).get("login") or i.get("author", {}).get("name"),
                "date": i.get("date"),
                "duration_minutes": i.get("duration", {}).get("minutes", 0),
                "duration_display": i.get("duration", {}).get("presentation", ""),
                "description": i.get("text"),
                "type": i.get("type", {}).get("name") if i.get("type") else None,
            }
            for i in items
        ]

    def add_work_item(
        self,
        issue_key: str,
        duration_minutes: int,
        description: str | None = None,
        work_type: str | None = None,
    ) -> dict[str, Any]:
        """
        Add a work item (log time) to an issue.

        Args:
            issue_key: Issue key
            duration_minutes: Duration in minutes
            description: Work description
            work_type: Work type name

        Returns:
            Created work item
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would add {duration_minutes}m work to {issue_key}")
            return {"id": "work:dry-run", "duration_minutes": duration_minutes}

        result = self._client.add_work_item(
            issue_key, duration_minutes, None, description, work_type
        )
        self.logger.info(f"Added {duration_minutes}m work to {issue_key}")
        return result

    def delete_work_item(self, issue_key: str, work_item_id: str) -> bool:
        """
        Delete a work item.

        Args:
            issue_key: Issue key
            work_item_id: Work item ID to delete

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would delete work item {work_item_id}")
            return True

        try:
            self._client.delete_work_item(issue_key, work_item_id)
            self.logger.info(f"Deleted work item {work_item_id} from {issue_key}")
            return True
        except (NotFoundError, IssueTrackerError) as e:
            self.logger.error(f"Failed to delete work item: {e}")
            return False

    def get_time_tracking(self, issue_key: str) -> dict[str, Any]:
        """
        Get time tracking summary for an issue.

        Args:
            issue_key: Issue key

        Returns:
            Time tracking info with estimate and spent time
        """
        settings = self._client.get_time_tracking_settings(issue_key)
        return {
            "enabled": settings.get("enabled", False),
            "estimate_minutes": settings.get("estimate", {}).get("minutes"),
            "estimate_display": settings.get("estimate", {}).get("presentation"),
            "spent_minutes": settings.get("spentTime", {}).get("minutes"),
            "spent_display": settings.get("spentTime", {}).get("presentation"),
        }

    def set_time_estimate(
        self,
        issue_key: str,
        original_estimate: str | int | None = None,
        remaining_estimate: str | int | None = None,
    ) -> bool:
        """
        Set time estimate for an issue.

        Args:
            issue_key: Issue key
            original_estimate: Estimate in minutes, or string format, or None to clear
            remaining_estimate: Remaining estimate (not used in YouTrack)

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would set estimate for {issue_key} to {original_estimate}")
            return True

        try:
            # Convert string to minutes if needed
            estimate_minutes: int | None = None
            if original_estimate is not None:
                if isinstance(original_estimate, int):
                    estimate_minutes = original_estimate
                elif isinstance(original_estimate, str):
                    # Parse string format like "2h" or "30m"
                    import re

                    match = re.match(r"(\d+)([hm])?", original_estimate.lower())
                    if match:
                        value = int(match.group(1))
                        unit = match.group(2) or "m"
                        estimate_minutes = value * 60 if unit == "h" else value
                    else:
                        estimate_minutes = int(original_estimate)

            self._client.set_time_estimate(issue_key, estimate_minutes)
            self.logger.info(f"Set estimate for {issue_key} to {estimate_minutes}m")
            return True
        except IssueTrackerError as e:
            self.logger.error(f"Failed to set time estimate: {e}")
            return False

    # -------------------------------------------------------------------------
    # Issue History/Activity Operations
    # -------------------------------------------------------------------------

    def get_issue_history(self, issue_key: str) -> list[dict[str, Any]]:
        """
        Get change history for an issue.

        Args:
            issue_key: Issue key

        Returns:
            List of change dictionaries
        """
        return self._client.get_issue_changes(issue_key)

    def get_issue_activities(
        self,
        issue_key: str,
        categories: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get activity feed for an issue.

        Args:
            issue_key: Issue key
            categories: Filter by category (e.g., "IssueCreatedCategory")

        Returns:
            List of activity items
        """
        return self._client.get_issue_activities(issue_key, categories)

    # -------------------------------------------------------------------------
    # Mentions Operations
    # -------------------------------------------------------------------------

    def add_comment_with_mentions(
        self,
        issue_key: str,
        text: str,
        mentions: list[str] | None = None,
    ) -> bool:
        """
        Add a comment with @mentions.

        Args:
            issue_key: Issue key
            text: Comment text
            mentions: List of usernames to mention

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would add comment with mentions to {issue_key}")
            return True

        try:
            self._client.add_comment_with_mentions(issue_key, text, mentions)
            self.logger.info(f"Added comment with mentions to {issue_key}")
            return True
        except IssueTrackerError as e:
            self.logger.error(f"Failed to add comment: {e}")
            return False

    def get_mentionable_users(self, query: str = "") -> list[dict[str, Any]]:
        """
        Get users that can be mentioned.

        Args:
            query: Search query

        Returns:
            List of user dictionaries
        """
        users = self._client.get_mentionable_users(query)
        return [
            {
                "id": u.get("id", ""),
                "login": u.get("login", ""),
                "name": u.get("name", ""),
                "email": u.get("email", ""),
            }
            for u in users
        ]

    # -------------------------------------------------------------------------
    # Private Methods
    # -------------------------------------------------------------------------

    def _iso_to_timestamp(self, iso_string: str) -> int:
        """Convert ISO 8601 string to Unix timestamp in milliseconds."""
        from datetime import datetime

        try:
            dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
            return int(dt.timestamp() * 1000)
        except ValueError:
            return 0

    def _parse_issue(self, data: dict[str, Any]) -> IssueData:
        """Parse YouTrack API response into IssueData."""
        issue_id = data.get("idReadable", data.get("id", ""))
        summary = data.get("summary", "")
        description = data.get("description", "")
        issue_type = data.get("type", {}).get("name", "")

        # Extract status
        status = self._extract_status(data)

        # Extract assignee
        assignee = None
        if data.get("assignee"):
            assignee = data.get("assignee", {}).get("login") or data.get("assignee", {}).get("name")

        # Extract story points
        story_points = self._extract_story_points(data)

        # Extract subtasks (from links)
        subtasks: list[IssueData] = []
        links = data.get("links", [])
        for link in links:
            link_type = link.get("linkType", {}).get("name", "").lower()
            if "subtask" in link_type:
                target = link.get("target", {})
                if target:
                    subtask_id = target.get("idReadable", target.get("id", ""))
                    if subtask_id:
                        try:
                            subtask_data = self._client.get_issue(subtask_id)
                            subtasks.append(self._parse_issue(subtask_data))
                        except IssueTrackerError:
                            pass  # Skip if subtask can't be fetched

        # Extract comments
        comments: list[dict] = []
        with contextlib.suppress(IssueTrackerError):
            comments = self.get_issue_comments(issue_id)

        return IssueData(
            key=issue_id,
            summary=summary,
            description=description,
            status=status,
            issue_type=issue_type,
            assignee=assignee,
            story_points=story_points,
            subtasks=subtasks,
            comments=comments,
        )

    def _extract_status(self, data: dict[str, Any]) -> str:
        """Extract status from issue data."""
        # Look for State field
        custom_fields = data.get("customFields", [])
        for field in custom_fields:
            field_name = field.get("name", "")
            if field_name in {self.config.status_field, "State"}:
                value = field.get("value")
                if isinstance(value, dict):
                    name = value.get("name", "")
                    return str(name) if name else "Open"
                if isinstance(value, str):
                    return value
        return "Open"  # Default

    def _extract_story_points(self, data: dict[str, Any]) -> float | None:
        """Extract story points from issue custom fields."""
        if not self.config.story_points_field:
            return None

        custom_fields = data.get("customFields", [])
        for field in custom_fields:
            field_id = field.get("id", "")
            field_name = field.get("name", "").lower()
            if (
                field_id == self.config.story_points_field
                or "story point" in field_name
                or "point" in field_name
            ):
                value = field.get("value")
                if value is not None:
                    try:
                        return float(value)
                    except (ValueError, TypeError):
                        pass
        return None

    def _get_available_states(self) -> list[dict[str, Any]]:
        """Get available states for the project, caching the result."""
        if self._states_cache is None:
            try:
                self._states_cache = self._client.get_available_states(self.config.project_id)
            except IssueTrackerError:
                self._states_cache = []
        return self._states_cache or []

    def _map_status_to_youtrack_state(self, status: str) -> str:
        """Map status string to YouTrack state name."""
        status_enum = Status.from_string(status)

        # Try to find matching state in available states
        states = self._get_available_states()
        status_lower = status.lower()

        # Common mappings
        status_mapping = {
            Status.DONE: ["done", "resolved", "closed", "complete"],
            Status.IN_PROGRESS: ["in progress", "working", "active"],
            Status.IN_REVIEW: ["in review", "review", "testing"],
            Status.OPEN: ["open", "to do", "todo"],
            Status.PLANNED: ["planned", "backlog", "new"],
            Status.CANCELLED: ["cancelled", "canceled", "won't fix"],
        }

        # Try exact match first
        for state in states:
            state_name = state.get("name", "").lower()
            if status_lower == state_name:
                name = state.get("name", "")
                return str(name) if name else "Open"

        # Try mapping
        for target_status, aliases in status_mapping.items():
            if status_enum == target_status:
                for alias in aliases:
                    for state in states:
                        state_name = state.get("name", "").lower()
                        if alias in state_name or state_name in alias:
                            name = state.get("name", "")
                            return str(name) if name else "Open"

        # Default fallback
        if status_enum == Status.DONE:
            return "Done"
        if status_enum == Status.IN_PROGRESS:
            return "In Progress"
        if status_enum == Status.OPEN:
            return "Open"
        return "Open"

    def _map_priority_to_youtrack(self, priority: str | None) -> str | None:
        """Map priority string to YouTrack priority name."""
        if not priority:
            return None

        priority_enum = Priority.from_string(priority)

        # Try to find matching priority in available priorities
        priorities = self._get_available_priorities()
        priority_lower = priority.lower()

        # Try exact match first
        for prio in priorities:
            prio_name = prio.get("name", "").lower()
            if priority_lower == prio_name:
                name = prio.get("name", "")
                return str(name) if name else None

        # Common mappings
        priority_mapping = {
            Priority.CRITICAL: ["critical", "blocker", "highest"],
            Priority.HIGH: ["high", "major"],
            Priority.MEDIUM: ["medium", "normal"],
            Priority.LOW: ["low", "minor", "trivial"],
        }

        for target_priority, aliases in priority_mapping.items():
            if priority_enum == target_priority:
                for alias in aliases:
                    for prio in priorities:
                        prio_name = prio.get("name", "").lower()
                        if alias in prio_name or prio_name in alias:
                            name = prio.get("name", "")
                            return str(name) if name else None

        # Default fallback
        if priority_enum == Priority.CRITICAL:
            return "Critical"
        if priority_enum == Priority.HIGH:
            return "High"
        if priority_enum == Priority.LOW:
            return "Low"
        return "Normal"

    def _get_available_priorities(self) -> list[dict[str, Any]]:
        """Get available priorities, caching the result."""
        if self._priorities_cache is None:
            try:
                self._priorities_cache = self._client.get_available_priorities()
            except IssueTrackerError:
                self._priorities_cache = []
        return self._priorities_cache or []

    def _map_youtrack_link_type(self, link_type_name: str) -> LinkType:
        """Map YouTrack link type name to LinkType enum."""
        link_type_lower = link_type_name.lower()

        mapping = {
            "depends on": LinkType.DEPENDS_ON,
            "is dependency of": LinkType.IS_DEPENDENCY_OF,
            "relates to": LinkType.RELATES_TO,
            "duplicates": LinkType.DUPLICATES,
            "is duplicated by": LinkType.IS_DUPLICATED_BY,
            "blocks": LinkType.BLOCKS,
            "is blocked by": LinkType.IS_BLOCKED_BY,
            "subtask of": LinkType.RELATES_TO,  # Subtasks use relates to
        }

        return mapping.get(link_type_lower, LinkType.RELATES_TO)

    def _map_link_type_to_youtrack(self, link_type: LinkType) -> str:
        """Map LinkType enum to YouTrack link type name."""
        mapping = {
            LinkType.DEPENDS_ON: "depends on",
            LinkType.IS_DEPENDENCY_OF: "is dependency of",
            LinkType.RELATES_TO: "relates to",
            LinkType.DUPLICATES: "duplicates",
            LinkType.IS_DUPLICATED_BY: "is duplicated by",
            LinkType.BLOCKS: "blocks",
            LinkType.IS_BLOCKED_BY: "is blocked by",
        }

        return mapping.get(link_type, "relates to")
