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

from spectra.core.domain.enums import Priority, Status
from spectra.core.ports.config_provider import YouTrackConfig
from spectra.core.ports.issue_tracker import (
    IssueData,
    IssueLink,
    IssueTrackerError,
    IssueTrackerPort,
    LinkType,
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
    # Private Methods
    # -------------------------------------------------------------------------

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
