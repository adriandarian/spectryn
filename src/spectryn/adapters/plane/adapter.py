"""
Plane.so Adapter - Implements IssueTrackerPort for Plane.so.

This is the main entry point for Plane.so integration.
Maps the generic IssueTrackerPort interface to Plane's issue model.

Key mappings:
- Epic → Cycle or Module (configurable)
- Story → Issue
- Subtask → Sub-issue (issue with parent)
- Status → State
- Priority → Priority
- Story Points → Estimate Point
"""

import logging
from typing import Any

from spectryn.core.ports.config_provider import PlaneConfig
from spectryn.core.ports.issue_tracker import (
    IssueData,
    IssueTrackerError,
    IssueTrackerPort,
    NotFoundError,
    TransitionError,
)

from .client import PlaneApiClient


class PlaneAdapter(IssueTrackerPort):
    """
    Plane.so implementation of the IssueTrackerPort.

    Translates between domain entities and Plane's REST API.

    Plane concepts:
    - Workspace: Top-level organization
    - Project: Collection of issues (like a Jira project)
    - Cycle: Sprint/iteration (can represent Epic)
    - Module: Feature/epic grouping (can represent Epic)
    - Issue: Work item (like a story)
    - Sub-issue: Child of another issue (like a subtask)
    - State: Status (Backlog, Started, Completed, etc.)
    - Priority: Priority (Urgent, High, Medium, Low, None)
    - Estimate Point: Story points
    """

    def __init__(
        self,
        config: PlaneConfig,
        dry_run: bool = True,
    ):
        """
        Initialize the Plane adapter.

        Args:
            config: Plane configuration
            dry_run: If True, don't make changes
        """
        self._dry_run = dry_run
        self.config = config
        self.logger = logging.getLogger("PlaneAdapter")

        # API client
        self._client = PlaneApiClient(
            api_token=config.api_token,
            workspace_slug=config.workspace_slug,
            project_id=config.project_id,
            api_url=config.api_url,
            dry_run=dry_run,
        )

        # Cache for states and priorities
        self._states_cache: dict[str, dict] = {}  # name -> state
        self._priorities_cache: dict[str, dict] = {}  # key -> priority

    def _get_states(self) -> dict[str, dict]:
        """Get workflow states for the project, caching the result."""
        if not self._states_cache:
            states = self._client.get_states()
            self._states_cache = {state["name"].lower(): state for state in states}
        return self._states_cache

    def _find_state(self, name: str) -> dict | None:
        """Find a workflow state by name (case-insensitive)."""
        states = self._get_states()
        name_lower = name.lower()

        # Try exact match first
        if name_lower in states:
            return states[name_lower]

        # Try partial match
        for state_name, state in states.items():
            if name_lower in state_name or state_name in name_lower:
                return state

        # Try mapping via config
        mapped_name = self.config.status_mapping.get(name_lower)
        if mapped_name:
            mapped_lower = mapped_name.lower()
            if mapped_lower in states:
                return states[mapped_lower]

        # Try matching by type/group
        type_mapping = {
            "planned": ["backlog", "todo"],
            "open": ["backlog", "todo"],
            "in progress": ["started", "in progress"],
            "done": ["completed", "done"],
            "closed": ["completed", "done"],
            "cancelled": ["cancelled", "canceled"],
        }

        for _status_key, aliases in type_mapping.items():
            if name_lower in aliases or any(alias in name_lower for alias in aliases):
                for state_name, state in states.items():
                    if any(alias in state_name for alias in aliases):
                        return state

        return None

    def _get_priority_key(self, priority: str) -> str | None:
        """Convert priority name to Plane priority key."""
        priority_lower = priority.lower()

        # Try direct mapping via config
        if priority_lower in self.config.priority_mapping:
            return self.config.priority_mapping[priority_lower]

        # Try direct match
        priority_mapping = {
            "critical": "urgent",
            "high": "high",
            "medium": "medium",
            "low": "low",
            "none": "none",
        }

        return priority_mapping.get(priority_lower)

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Properties
    # -------------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "Plane"

    @property
    def is_connected(self) -> bool:
        return self._client.is_connected

    def test_connection(self) -> bool:
        if not self._client.test_connection():
            return False
        # Also verify project access
        try:
            self._client.get_project()
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
        Fetch a single issue by ID.

        Args:
            issue_key: Issue ID (UUID)
        """
        try:
            data = self._client.get_issue(issue_key)
        except NotFoundError:
            # Try searching by name or identifier
            issues = self._client.get_issues(limit=100)
            for issue in issues:
                if (
                    issue.get("id") == issue_key
                    or issue.get("sequence_id") == issue_key
                    or issue.get("name", "").startswith(issue_key)
                ):
                    data = issue
                    break
            else:
                raise NotFoundError(f"Issue not found: {issue_key}")

        return self._parse_issue(data)

    def get_epic_children(self, epic_key: str) -> list[IssueData]:
        """
        Fetch all children of an epic.

        In Plane, epics can be represented as Cycles or Modules.
        """
        try:
            if self.config.epic_as_cycle:
                # Try as cycle
                self._client.get_cycle(epic_key)  # Verify cycle exists
                issues = self._client.get_cycle_issues(epic_key)
                return [self._parse_issue(issue) for issue in issues]
            # Try as module
            self._client.get_module(epic_key)  # Verify module exists
            issues = self._client.get_module_issues(epic_key)
            return [self._parse_issue(issue) for issue in issues]
        except NotFoundError:
            pass

        # Try as parent issue
        try:
            issue = self._client.get_issue(epic_key)
            # Get all issues with this as parent
            all_issues = self._client.get_issues(limit=1000)
            children = [i for i in all_issues if i.get("parent") == issue.get("id")]
            return [self._parse_issue(child) for child in children]
        except NotFoundError:
            return []

    def get_issue_comments(self, issue_key: str) -> list[dict]:
        return self._client.get_issue_comments(issue_key)

    def get_issue_status(self, issue_key: str) -> str:
        """Get the current status (state) of an issue."""
        issue = self._client.get_issue(issue_key)
        state_id = issue.get("state")
        if state_id:
            states = self._get_states()
            for state in states.values():
                if state.get("id") == state_id:
                    return str(state.get("name", "Unknown"))
        return "Unknown"

    def search_issues(self, query: str, max_results: int = 50) -> list[IssueData]:
        """
        Search for issues.

        Plane doesn't have a full-text search API, so we search within the project.
        """
        issues = self._client.get_issues(limit=max_results)
        query_lower = query.lower()

        matching = []
        for issue in issues:
            name = issue.get("name", "").lower()
            desc = (
                issue.get("description", {}).get("html", "").lower()
                or issue.get("description", "").lower()
            )
            if query_lower in name or query_lower in desc:
                matching.append(self._parse_issue(issue))
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
        self._client.update_issue(issue_key, description=desc_str)
        self.logger.info(f"Updated description for {issue_key}")
        return True

    def update_issue_story_points(self, issue_key: str, story_points: float) -> bool:
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would update story points for {issue_key} to {story_points}"
            )
            return True

        self._client.update_issue(issue_key, estimate_point=int(story_points))
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
        Create a subtask (sub-issue in Plane).

        In Plane, sub-issues are regular issues with a parent.
        """
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would create subtask '{summary[:50]}...' under {parent_key}"
            )
            return None

        desc_str = description if isinstance(description, str) else str(description)

        # Get parent issue to verify it exists
        parent_issue = self._client.get_issue(parent_key)
        parent_id = parent_issue.get("id")

        # Map priority
        priority_key = None
        if priority:
            priority_key = self._get_priority_key(priority)

        result = self._client.create_issue(
            name=summary[:255],
            description=desc_str,
            estimate_point=story_points,
            priority=priority_key,
            assignee_id=assignee,
            parent_id=parent_id,
        )

        issue_id: str | None = result.get("id")
        if issue_id:
            self.logger.info(f"Created subtask {issue_id} under {parent_key}")
            return str(issue_id)
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
            updates["estimate_point"] = story_points

        if assignee is not None:
            updates["assignee_id"] = assignee

        if priority_id is not None:
            updates["priority"] = priority_id

        if updates:
            self._client.update_issue(issue_key, **updates)
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
        Transition an issue to a new state.

        Plane uses states instead of transitions.
        We find the target state and update the issue.
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would transition {issue_key} to {target_status}")
            return True

        target_state = self._find_state(target_status)
        if not target_state:
            available_states = list(self._get_states().keys())
            raise TransitionError(
                f"State not found: {target_status}. Available states: {available_states}",
                issue_key=issue_key,
            )

        try:
            self._client.update_issue(issue_key, state_id=target_state["id"])
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
        Get available transitions (states) for an issue.

        In Plane, any issue can transition to any state,
        so we return all states for the project.
        """
        states = self._get_states()
        return [
            {
                "id": state["id"],
                "name": state["name"],
                "type": state.get("group", ""),
            }
            for state in states.values()
        ]

    def format_description(self, markdown: str) -> Any:
        """
        Convert markdown to Plane-compatible format.

        Plane uses HTML/Markdown natively, so we just return the input.
        """
        return markdown

    # -------------------------------------------------------------------------
    # Private Methods
    # -------------------------------------------------------------------------

    def _parse_issue(self, data: dict) -> IssueData:
        """Parse Plane API response into IssueData."""
        # Determine issue type
        has_parent = data.get("parent") is not None
        issue_type = "Sub-task" if has_parent else "Story"

        # Get status from state
        state_id = data.get("state")
        status = "Unknown"
        if state_id:
            states = self._get_states()
            for state in states.values():
                if state.get("id") == state_id:
                    status = state.get("name", "Unknown")
                    break

        # Get assignee
        assignee = None
        assignee_ids = data.get("assignee_ids", [])
        if assignee_ids:
            # Plane returns assignee IDs, we'd need to fetch user details
            # For now, just use the first ID
            assignee = assignee_ids[0] if assignee_ids else None

        # Get estimate (story points)
        estimate = data.get("estimate_point")

        # Parse description
        description = data.get("description")
        if isinstance(description, dict):
            # Plane may return description as HTML object
            description = description.get("html") or description.get("text") or str(description)

        # Parse subtasks (sub-issues)
        subtasks: list[IssueData] = []
        # Sub-issues are fetched separately via get_epic_children with parent_id

        # Parse comments
        comments: list[dict[str, Any]] = []
        # Comments are fetched separately via get_issue_comments

        return IssueData(
            key=data.get("id", ""),
            summary=data.get("name", ""),
            description=description,
            status=status,
            issue_type=issue_type,
            assignee=assignee,
            story_points=float(estimate) if estimate else None,
            subtasks=subtasks,
            comments=comments,
        )

    # -------------------------------------------------------------------------
    # Extended Methods (Plane-specific)
    # -------------------------------------------------------------------------

    def create_cycle(
        self,
        name: str,
        description: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> str:
        """
        Create a cycle (epic in Plane terms).

        Returns the cycle ID.
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would create cycle '{name}'")
            return "cycle:dry-run"

        result = self._client.create_cycle(
            name=name,
            description=description,
            start_date=start_date,
            end_date=end_date,
        )

        cycle_id: str = result.get("id", "") or ""
        if cycle_id:
            self.logger.info(f"Created cycle {cycle_id}: {name}")
        return cycle_id

    def create_module(
        self,
        name: str,
        description: str | None = None,
    ) -> str:
        """
        Create a module (epic in Plane terms).

        Returns the module ID.
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would create module '{name}'")
            return "module:dry-run"

        result = self._client.create_module(
            name=name,
            description=description,
        )

        module_id: str = result.get("id", "") or ""
        if module_id:
            self.logger.info(f"Created module {module_id}: {name}")
        return module_id

    def create_issue(
        self,
        name: str,
        description: str | None = None,
        priority: str | None = None,
        estimate_point: int | None = None,
        assignee_id: str | None = None,
        state_name: str | None = None,
        cycle_id: str | None = None,
        module_id: str | None = None,
    ) -> str:
        """
        Create a new issue (story).

        Returns the issue ID.
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would create issue '{name}'")
            return "issue:dry-run"

        state_id = None
        if state_name:
            state = self._find_state(state_name)
            if state:
                state_id = state["id"]

        priority_key = None
        if priority:
            priority_key = self._get_priority_key(priority)

        result = self._client.create_issue(
            name=name,
            description=description,
            priority=priority_key,
            estimate_point=estimate_point,
            assignee_id=assignee_id,
            state_id=state_id,
            cycle_id=cycle_id,
            module_id=module_id,
        )

        issue_id: str = result.get("id", "") or ""
        if issue_id:
            self.logger.info(f"Created issue {issue_id}: {name}")
        return issue_id

    def get_project_info(self) -> dict[str, Any]:
        """Get information about the configured project."""
        return self._client.get_project()

    def list_states(self) -> list[dict[str, Any]]:
        """List all states for the project."""
        return list(self._get_states().values())

    def list_cycles(self) -> list[dict[str, Any]]:
        """List all cycles for the project."""
        return self._client.get_cycles()

    def list_modules(self) -> list[dict[str, Any]]:
        """List all modules for the project."""
        return self._client.get_modules()

    # -------------------------------------------------------------------------
    # Views & Filters Methods
    # -------------------------------------------------------------------------

    def get_views(self) -> list[dict[str, Any]]:
        """
        Get all saved views/filters for the project.

        Returns:
            List of view definitions with their filter criteria
        """
        return self._client.get_views()

    def get_view(self, view_id: str) -> dict[str, Any]:
        """
        Get a specific view by ID.

        Args:
            view_id: View ID to retrieve

        Returns:
            View data with filters and configuration
        """
        return self._client.get_view(view_id)

    def get_view_issues(self, view_id: str, limit: int = 50) -> list[IssueData]:
        """
        Get issues from a specific view.

        Args:
            view_id: View ID
            limit: Maximum number of results

        Returns:
            List of issues matching the view filters
        """
        issues = self._client.get_view_issues(view_id=view_id, limit=limit)
        return [self._parse_issue(issue) for issue in issues]

    def create_view(
        self,
        name: str,
        filters: dict[str, Any],
        description: str | None = None,
    ) -> str:
        """
        Create a new saved view/filter.

        Args:
            name: View name
            filters: Filter criteria (e.g., {"state": "started", "priority": "high"})
            description: Optional view description

        Returns:
            Created view ID
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would create view '{name}'")
            return "view:dry-run"

        result = self._client.create_view(name=name, filters=filters, description=description)
        view_id: str = result.get("id", "") or ""
        if view_id:
            self.logger.info(f"Created view {view_id}: {name}")
        return view_id

    def update_view(
        self,
        view_id: str,
        name: str | None = None,
        filters: dict[str, Any] | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """
        Update an existing view.

        Args:
            view_id: View ID to update
            name: New view name (optional)
            filters: New filter criteria (optional)
            description: New description (optional)

        Returns:
            Updated view data
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would update view {view_id}")
            return {"id": view_id}

        return self._client.update_view(
            view_id=view_id,
            name=name,
            filters=filters,
            description=description,
        )

    def delete_view(self, view_id: str) -> bool:
        """
        Delete a saved view.

        Args:
            view_id: View ID to delete

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would delete view {view_id}")
            return True

        return self._client.delete_view(view_id)

    def filter_issues(
        self,
        state: str | None = None,
        priority: str | None = None,
        assignee: str | None = None,
        cycle_id: str | None = None,
        module_id: str | None = None,
        labels: list[str] | None = None,
        limit: int = 50,
    ) -> list[IssueData]:
        """
        Filter issues using various criteria.

        Args:
            state: Filter by state name
            priority: Filter by priority key
            assignee: Filter by assignee ID
            cycle_id: Filter by cycle ID
            module_id: Filter by module ID
            labels: Filter by label names
            limit: Maximum number of results

        Returns:
            List of filtered issues
        """
        filters: dict[str, Any] = {}
        if cycle_id:
            filters["cycle"] = cycle_id
        if module_id:
            filters["module"] = module_id
        if labels:
            filters["labels"] = labels

        # Map state name to state ID if needed
        state_id = None
        if state:
            state_obj = self._find_state(state)
            if state_obj:
                state_id = state_obj.get("id")

        # Map priority name to priority key
        priority_key = None
        if priority:
            priority_key = self._get_priority_key(priority)

        issues = self._client.get_issues(
            state=state_id,
            priority=priority_key,
            assignee=assignee,
            limit=limit,
            filters=filters if filters else None,
        )
        return [self._parse_issue(issue) for issue in issues]

    # -------------------------------------------------------------------------
    # Webhook Methods
    # -------------------------------------------------------------------------

    def create_webhook(
        self,
        url: str,
        events: list[str] | None = None,
        secret: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a webhook subscription for the project.

        Plane.so webhooks notify when changes occur in the project.
        Supported events include:
        - issue.created, issue.updated, issue.deleted
        - cycle.created, cycle.updated, cycle.deleted
        - module.created, module.updated, module.deleted
        - comment.created, comment.updated

        Args:
            url: Webhook URL to receive events (must be HTTPS)
            events: Optional list of event types to subscribe to (defaults to all)
            secret: Optional secret for webhook signature verification

        Returns:
            Webhook subscription data
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would create webhook for URL {url}")
            return {
                "id": "webhook:dry-run",
                "url": url,
                "events": events or [],
                "project": self.config.project_id,
            }

        return self._client.create_webhook(url=url, events=events, secret=secret)

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
        secret: str | None = None,
        is_active: bool | None = None,
    ) -> dict[str, Any]:
        """
        Update a webhook subscription.

        Args:
            webhook_id: Webhook ID to update
            url: New webhook URL (optional)
            events: New event types (optional)
            secret: New secret (optional)
            is_active: New active status (optional)

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
            secret=secret,
            is_active=is_active,
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
    # Attachment Methods
    # -------------------------------------------------------------------------

    def get_issue_attachments(self, issue_key: str) -> list[dict[str, Any]]:
        """
        Get all file attachments for an issue.

        Args:
            issue_key: Issue ID

        Returns:
            List of attachment dictionaries with id, name, url, etc.
        """
        return self._client.get_issue_attachments(issue_key)

    def upload_attachment(
        self,
        issue_key: str,
        file_path: str,
        name: str | None = None,
    ) -> dict[str, Any]:
        """
        Upload a file attachment to an issue.

        Args:
            issue_key: Issue ID
            file_path: Path to file to upload
            name: Optional attachment name (defaults to filename)

        Returns:
            Attachment information dictionary
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would upload attachment {file_path} to issue {issue_key}")
            return {"id": "attachment:dry-run", "name": name or file_path}

        result = self._client.upload_issue_attachment(issue_key, file_path, name)
        self.logger.info(f"Uploaded attachment to {issue_key}: {result.get('name')}")
        return result

    def delete_attachment(self, issue_key: str, attachment_id: str) -> bool:
        """
        Delete a file attachment from an issue.

        Args:
            issue_key: Issue ID
            attachment_id: Attachment ID to delete

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would delete attachment {attachment_id} from issue {issue_key}"
            )
            return True

        try:
            self._client.delete_issue_attachment(issue_key, attachment_id)
            self.logger.info(f"Deleted attachment {attachment_id} from {issue_key}")
            return True
        except IssueTrackerError as e:
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
            issue_key: Issue ID
            attachment_id: Attachment ID
            download_path: Local path to save the file (directory or full path)

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would download attachment {attachment_id} from issue {issue_key}"
            )
            return True

        try:
            self._client.download_attachment(issue_key, attachment_id, download_path)
            self.logger.info(f"Downloaded attachment {attachment_id} to {download_path}")
            return True
        except IssueTrackerError as e:
            self.logger.error(f"Failed to download attachment: {e}")
            return False
