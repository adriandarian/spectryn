"""
Linear Adapter - Implements IssueTrackerPort for Linear.

This is the main entry point for Linear integration.
Maps the generic IssueTrackerPort interface to Linear's issue model.

Key mappings:
- Epic -> Project (Linear's project feature)
- Story -> Issue (top-level issue)
- Subtask -> Sub-issue (issue with parent)
- Status -> Workflow State
- Story Points -> Estimate (Linear's estimation)
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

from .client import LinearApiClient


class LinearAdapter(IssueTrackerPort):
    """
    Linear implementation of the IssueTrackerPort.

    Translates between domain entities and Linear's GraphQL API.

    Linear concepts:
    - Team: Organizational unit (like a Jira project)
    - Project: Collection of issues (like an epic)
    - Issue: Work item (like a story)
    - Sub-issue: Child of another issue (like a subtask)
    - Workflow State: Status (Backlog, Todo, In Progress, Done, etc.)
    - Estimate: Story points (Fibonacci or linear scale)
    """

    def __init__(
        self,
        api_key: str,
        team_key: str,
        dry_run: bool = True,
        api_url: str = "https://api.linear.app/graphql",
    ):
        """
        Initialize the Linear adapter.

        Args:
            api_key: Linear API key
            team_key: Team key (e.g., 'ENG') to scope operations
            dry_run: If True, don't make changes
            api_url: Linear GraphQL API URL
        """
        self._dry_run = dry_run
        self.team_key = team_key.upper()
        self.logger = logging.getLogger("LinearAdapter")

        # API client
        self._client = LinearApiClient(
            api_key=api_key,
            api_url=api_url,
            dry_run=dry_run,
        )

        # Cache for team and workflow states
        self._team: dict[str, Any] | None = None
        self._workflow_states: dict[str, dict] = {}  # name -> state
        self._batch_client: Any = None

    def _get_team(self) -> dict[str, Any]:
        """Get the configured team, caching the result."""
        if self._team is None:
            self._team = self._client.get_team_by_key(self.team_key)
            if not self._team:
                raise IssueTrackerError(
                    f"Team not found: {self.team_key}. Check LINEAR_TEAM_KEY or available teams."
                )
        return self._team

    def _get_team_id(self) -> str:
        """Get the team ID."""
        return self._get_team()["id"]

    def _get_workflow_states(self) -> dict[str, dict]:
        """Get workflow states for the team, caching the result."""
        if not self._workflow_states:
            team_id = self._get_team_id()
            states = self._client.get_workflow_states(team_id)
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
            "open": "backlog",
            "todo": "unstarted",
            "in progress": "started",
            "done": "completed",
            "closed": "completed",
            "cancelled": "canceled",
        }

        target_type = type_mapping.get(name_lower)
        if target_type:
            for state in states.values():
                if state.get("type", "").lower() == target_type:
                    return state

        return None

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Properties
    # -------------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "Linear"

    @property
    def is_connected(self) -> bool:
        return self._client.is_connected

    def test_connection(self) -> bool:
        if not self._client.test_connection():
            return False
        # Also verify team access
        try:
            self._get_team()
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
        Fetch a single issue by key.

        Args:
            issue_key: Issue identifier (e.g., 'ENG-123') or UUID
        """
        data = self._client.get_issue(issue_key)
        return self._parse_issue(data)

    def get_epic_children(self, epic_key: str) -> list[IssueData]:
        """
        Fetch all children of an epic (project).

        In Linear, epics are represented as Projects.
        """
        try:
            # Try as project first
            issues = self._client.get_project_issues(epic_key)
            return [self._parse_issue(issue) for issue in issues]
        except NotFoundError:
            pass

        # Try as parent issue
        try:
            issue = self._client.get_issue(epic_key)
            children = issue.get("children", {}).get("nodes", [])
            return [self._parse_issue(child) for child in children]
        except NotFoundError:
            return []

    def get_issue_comments(self, issue_key: str) -> list[dict]:
        return self._client.get_issue_comments(issue_key)

    def get_issue_status(self, issue_key: str) -> str:
        """Get the current status (workflow state) of an issue."""
        issue = self._client.get_issue(issue_key)
        state = issue.get("state", {})
        return state.get("name", "Unknown")

    def search_issues(self, query: str, max_results: int = 50) -> list[IssueData]:
        """
        Search for issues.

        Linear doesn't have a full-text search API like Jira's JQL,
        so we search within the configured team.
        """
        team_id = self._get_team_id()
        issues = self._client.search_issues(
            team_id=team_id,
            query_filter=query,
            first=max_results,
        )
        return [self._parse_issue(issue) for issue in issues]

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

        self._client.update_issue(issue_key, estimate=int(story_points))
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
        Create a subtask (sub-issue in Linear).

        In Linear, sub-issues are regular issues with a parent.
        """
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would create subtask '{summary[:50]}...' under {parent_key}"
            )
            return None

        team_id = self._get_team_id()
        desc_str = description if isinstance(description, str) else str(description)

        # Get parent issue ID
        parent_issue = self._client.get_issue(parent_key)
        parent_id = parent_issue.get("id")

        result = self._client.create_issue(
            team_id=team_id,
            title=summary[:255],
            description=desc_str,
            estimate=story_points,
            assignee_id=assignee,
            parent_id=parent_id,
        )

        identifier = result.get("identifier")
        if identifier:
            self.logger.info(f"Created subtask {identifier} under {parent_key}")
            return identifier
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
            updates["estimate"] = story_points

        if assignee is not None:
            updates["assignee_id"] = assignee

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
        Transition an issue to a new workflow state.

        Linear uses workflow states instead of transitions.
        We find the target state and update the issue.
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would transition {issue_key} to {target_status}")
            return True

        target_state = self._find_workflow_state(target_status)
        if not target_state:
            raise TransitionError(
                f"Workflow state not found: {target_status}. "
                f"Available states: {list(self._get_workflow_states().keys())}",
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
        Get available transitions (workflow states) for an issue.

        In Linear, any issue can transition to any workflow state,
        so we return all states for the team.
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
        Convert markdown to Linear-compatible format.

        Linear uses Markdown natively, so we just return the input.
        """
        return markdown

    # -------------------------------------------------------------------------
    # Private Methods
    # -------------------------------------------------------------------------

    def _parse_issue(self, data: dict) -> IssueData:
        """Parse Linear API response into IssueData."""
        # Determine issue type
        has_parent = data.get("parent") is not None
        has_children = bool(data.get("children", {}).get("nodes", []))

        if has_parent:
            issue_type = "Sub-task"
        elif has_children:
            issue_type = "Story"  # Parent issues are stories
        else:
            issue_type = "Story"

        # Get status from workflow state
        state = data.get("state", {})
        status = state.get("name", "Unknown")

        # Get assignee
        assignee = None
        if data.get("assignee"):
            assignee = data["assignee"].get("email") or data["assignee"].get("name")

        # Get estimate (story points)
        estimate = data.get("estimate")

        # Parse subtasks
        subtasks = []
        for child in data.get("children", {}).get("nodes", []):
            subtasks.append(
                IssueData(
                    key=child.get("identifier", child.get("id", "")),
                    summary=child.get("title", ""),
                    status=child.get("state", {}).get("name", ""),
                    issue_type="Sub-task",
                )
            )

        # Parse comments
        comments = []
        for comment in data.get("comments", {}).get("nodes", []):
            comments.append(
                {
                    "id": comment.get("id"),
                    "body": comment.get("body"),
                    "author": comment.get("user", {}).get("name"),
                    "created": comment.get("createdAt"),
                }
            )

        return IssueData(
            key=data.get("identifier", data.get("id", "")),
            summary=data.get("title", ""),
            description=data.get("description"),
            status=status,
            issue_type=issue_type,
            assignee=assignee,
            story_points=float(estimate) if estimate else None,
            subtasks=subtasks,
            comments=comments,
        )

    # -------------------------------------------------------------------------
    # Extended Methods (Linear-specific)
    # -------------------------------------------------------------------------

    def create_project(
        self,
        name: str,
        description: str | None = None,
    ) -> str:
        """
        Create a project (epic in Linear terms).

        Returns the project ID.
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would create project '{name}'")
            return "project:dry-run"

        team_id = self._get_team_id()
        result = self._client.create_project(
            name=name,
            team_ids=[team_id],
            description=description,
        )

        project_id = result.get("id", "")
        if project_id:
            self.logger.info(f"Created project {project_id}: {name}")
        return project_id

    def create_issue(
        self,
        title: str,
        description: str | None = None,
        priority: int | None = None,
        estimate: int | None = None,
        assignee_id: str | None = None,
        state_name: str | None = None,
    ) -> str:
        """
        Create a new issue (story).

        Returns the issue identifier (e.g., 'ENG-123').
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would create issue '{title}'")
            return f"{self.team_key}-0"

        team_id = self._get_team_id()

        state_id = None
        if state_name:
            state = self._find_workflow_state(state_name)
            if state:
                state_id = state["id"]

        result = self._client.create_issue(
            team_id=team_id,
            title=title,
            description=description,
            priority=priority,
            estimate=estimate,
            assignee_id=assignee_id,
            state_id=state_id,
        )

        identifier = result.get("identifier", "")
        if identifier:
            self.logger.info(f"Created issue {identifier}: {title}")
        return identifier

    def get_team_info(self) -> dict[str, Any]:
        """Get information about the configured team."""
        return self._get_team()

    def list_workflow_states(self) -> list[dict[str, Any]]:
        """List all workflow states for the team."""
        return list(self._get_workflow_states().values())

    def get_labels(self) -> list[dict[str, Any]]:
        """Get all labels for the team."""
        team_id = self._get_team_id()
        return self._client.get_labels(team_id)

    def create_label(
        self,
        name: str,
        color: str | None = None,
        description: str | None = None,
    ) -> str:
        """Create a new label. Returns the label ID."""
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would create label '{name}'")
            return "label:dry-run"

        team_id = self._get_team_id()
        result = self._client.create_label(
            team_id=team_id,
            name=name,
            color=color,
            description=description,
        )
        return result.get("id", "")

    # -------------------------------------------------------------------------
    # Batch operations
    # -------------------------------------------------------------------------
    @property
    def batch_client(self) -> Any:
        """Get the batch client for bulk operations."""
        if self._batch_client is None:
            from .batch import LinearBatchClient

            self._batch_client = LinearBatchClient(
                client=self._client,
            )
        return self._batch_client
