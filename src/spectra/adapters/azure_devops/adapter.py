"""
Azure DevOps Adapter - Implements IssueTrackerPort for Azure DevOps.

This is the main entry point for Azure DevOps integration.
Maps the generic IssueTrackerPort interface to Azure DevOps work items.

Key mappings:
- Epic -> Epic work item type
- Story -> User Story work item type (or Story in some templates)
- Subtask -> Task work item type (linked to parent)
- Status -> Work item State
- Story Points -> Microsoft.VSTS.Scheduling.StoryPoints field
"""

import logging
import re
from typing import Any

from spectra.core.ports.issue_tracker import (
    IssueData,
    IssueTrackerError,
    IssueTrackerPort,
    TransitionError,
)

from .client import AzureDevOpsApiClient


class AzureDevOpsAdapter(IssueTrackerPort):
    """
    Azure DevOps implementation of the IssueTrackerPort.

    Translates between domain entities and Azure DevOps Work Items.

    Azure DevOps concepts:
    - Organization: Top-level container
    - Project: Collection of work items, repos, pipelines
    - Work Item: Generic work tracking entity (Epic, Feature, User Story, Task, Bug)
    - State: Workflow state (New, Active, Resolved, Closed, etc.)
    - Area Path: Hierarchical categorization
    - Iteration Path: Sprint/release planning
    """

    # Default work item type mappings (Agile process template)
    DEFAULT_EPIC_TYPE = "Epic"
    DEFAULT_STORY_TYPE = "User Story"
    DEFAULT_TASK_TYPE = "Task"

    def __init__(
        self,
        organization: str,
        project: str,
        pat: str,
        dry_run: bool = True,
        base_url: str = "https://dev.azure.com",
        epic_type: str = DEFAULT_EPIC_TYPE,
        story_type: str = DEFAULT_STORY_TYPE,
        task_type: str = DEFAULT_TASK_TYPE,
    ):
        """
        Initialize the Azure DevOps adapter.

        Args:
            organization: Azure DevOps organization name
            project: Project name
            pat: Personal Access Token
            dry_run: If True, don't make changes
            base_url: Azure DevOps base URL
            epic_type: Work item type for epics
            story_type: Work item type for stories
            task_type: Work item type for tasks/subtasks
        """
        self._dry_run = dry_run
        self.organization = organization
        self.project = project
        self.logger = logging.getLogger("AzureDevOpsAdapter")

        # Work item type mappings
        self.epic_type = epic_type
        self.story_type = story_type
        self.task_type = task_type

        # API client
        self._client = AzureDevOpsApiClient(
            organization=organization,
            project=project,
            pat=pat,
            base_url=base_url,
            dry_run=dry_run,
        )

        # Cache for states
        self._states_cache: dict[str, list[dict]] = {}

    def _get_states(self, work_item_type: str) -> list[dict]:
        """Get available states for a work item type, with caching."""
        if work_item_type not in self._states_cache:
            self._states_cache[work_item_type] = self._client.get_work_item_states(work_item_type)
        return self._states_cache[work_item_type]

    def _find_state(self, work_item_type: str, target: str) -> str | None:
        """Find a state by name (case-insensitive, partial match)."""
        states = self._get_states(work_item_type)
        target_lower = target.lower()

        # Try exact match first
        for state in states:
            if state.get("name", "").lower() == target_lower:
                return state["name"]

        # Try partial match
        for state in states:
            state_name = state.get("name", "").lower()
            if target_lower in state_name or state_name in target_lower:
                return state["name"]

        # Try common mappings
        state_mapping = {
            "open": ["new", "to do", "todo"],
            "in progress": ["active", "in progress", "doing", "committed"],
            "done": ["closed", "done", "resolved", "completed"],
            "closed": ["closed", "done", "resolved", "removed"],
        }

        if target_lower in state_mapping:
            for state in states:
                state_name = state.get("name", "").lower()
                if state_name in state_mapping[target_lower]:
                    return state["name"]

        return None

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Properties
    # -------------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "Azure DevOps"

    @property
    def is_connected(self) -> bool:
        return self._client.is_connected

    def test_connection(self) -> bool:
        return self._client.test_connection()

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Read Operations
    # -------------------------------------------------------------------------

    def get_current_user(self) -> dict[str, Any]:
        return self._client.get_connection_data()

    def get_issue(self, issue_key: str) -> IssueData:
        """
        Fetch a single work item by ID.

        Args:
            issue_key: Work item ID (numeric) or prefixed ID like "123"
        """
        work_item_id = self._parse_work_item_id(issue_key)
        data = self._client.get_work_item(work_item_id)
        return self._parse_work_item(data)

    def get_epic_children(self, epic_key: str) -> list[IssueData]:
        """Fetch all children of an epic."""
        work_item_id = self._parse_work_item_id(epic_key)
        children = self._client.get_work_item_children(work_item_id)
        return [self._parse_work_item(child) for child in children]

    def get_issue_comments(self, issue_key: str) -> list[dict]:
        work_item_id = self._parse_work_item_id(issue_key)
        comments = self._client.get_comments(work_item_id)
        return [
            {
                "id": c.get("id"),
                "body": c.get("text"),
                "author": c.get("createdBy", {}).get("displayName"),
                "created": c.get("createdDate"),
            }
            for c in comments
        ]

    def get_issue_status(self, issue_key: str) -> str:
        """Get the current state of a work item."""
        work_item_id = self._parse_work_item_id(issue_key)
        data = self._client.get_work_item(work_item_id, expand="Fields")
        fields = data.get("fields", {})
        return fields.get("System.State", "Unknown")

    def search_issues(self, query: str, max_results: int = 50) -> list[IssueData]:
        """
        Search for work items.

        The query is treated as a title search. For WIQL queries,
        use the client directly.
        """
        work_items = self._client.search_work_items(text=query, top=max_results)
        return [self._parse_work_item(wi) for wi in work_items]

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Write Operations
    # -------------------------------------------------------------------------

    def update_issue_description(self, issue_key: str, description: Any) -> bool:
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would update description for {issue_key}")
            return True

        work_item_id = self._parse_work_item_id(issue_key)
        desc_str = description if isinstance(description, str) else str(description)

        # Convert markdown to HTML for Azure DevOps
        html_desc = self._markdown_to_html(desc_str)

        self._client.update_work_item(work_item_id, description=html_desc)
        self.logger.info(f"Updated description for {work_item_id}")
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
        """Create a Task work item linked to the parent."""
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would create task '{summary[:50]}...' under {parent_key}")
            return None

        parent_id = self._parse_work_item_id(parent_key)
        desc_str = description if isinstance(description, str) else str(description)
        html_desc = self._markdown_to_html(desc_str)

        result = self._client.create_work_item(
            work_item_type=self.task_type,
            title=summary[:255],
            description=html_desc,
            parent_id=parent_id,
            story_points=float(story_points) if story_points else None,
            assigned_to=assignee,
        )

        new_id = result.get("id")
        if new_id:
            self.logger.info(f"Created task {new_id} under {parent_id}")
            return str(new_id)
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
            self.logger.info(f"[DRY-RUN] Would update task {issue_key}")
            return True

        work_item_id = self._parse_work_item_id(issue_key)

        updates: dict[str, Any] = {}

        if description is not None:
            desc_str = description if isinstance(description, str) else str(description)
            updates["description"] = self._markdown_to_html(desc_str)

        if story_points is not None:
            updates["story_points"] = float(story_points)

        if assignee is not None:
            updates["assigned_to"] = assignee

        if updates:
            self._client.update_work_item(work_item_id, **updates)
            self.logger.info(f"Updated task {work_item_id}")

        return True

    def add_comment(self, issue_key: str, body: Any) -> bool:
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would add comment to {issue_key}")
            return True

        work_item_id = self._parse_work_item_id(issue_key)
        comment_body = body if isinstance(body, str) else str(body)

        self._client.add_comment(work_item_id, comment_body)
        self.logger.info(f"Added comment to {work_item_id}")
        return True

    def transition_issue(self, issue_key: str, target_status: str) -> bool:
        """
        Transition a work item to a new state.

        Azure DevOps allows direct state changes without transitions.
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would transition {issue_key} to {target_status}")
            return True

        work_item_id = self._parse_work_item_id(issue_key)

        # Get current work item to determine type
        work_item = self._client.get_work_item(work_item_id, expand="Fields")
        work_item_type = work_item.get("fields", {}).get("System.WorkItemType", self.story_type)

        # Find the target state
        target_state = self._find_state(work_item_type, target_status)
        if not target_state:
            available = [s.get("name") for s in self._get_states(work_item_type)]
            raise TransitionError(
                f"State not found: {target_status}. Available: {available}",
                issue_key=issue_key,
            )

        try:
            self._client.update_work_item(work_item_id, state=target_state)
            self.logger.info(f"Transitioned {work_item_id} to {target_state}")
            return True
        except IssueTrackerError as e:
            raise TransitionError(
                f"Failed to transition {work_item_id} to {target_status}: {e}",
                issue_key=issue_key,
                cause=e,
            )

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Utility
    # -------------------------------------------------------------------------

    def get_available_transitions(self, issue_key: str) -> list[dict]:
        """
        Get available states for a work item.

        Azure DevOps doesn't have transitions like Jira - work items
        can typically move to any state directly.
        """
        work_item_id = self._parse_work_item_id(issue_key)
        work_item = self._client.get_work_item(work_item_id, expand="Fields")
        work_item_type = work_item.get("fields", {}).get("System.WorkItemType", self.story_type)

        states = self._get_states(work_item_type)
        return [
            {"id": s.get("name"), "name": s.get("name"), "category": s.get("category")}
            for s in states
        ]

    def format_description(self, markdown: str) -> Any:
        """
        Convert markdown to HTML for Azure DevOps.

        Azure DevOps uses HTML for rich text fields.
        """
        return self._markdown_to_html(markdown)

    # -------------------------------------------------------------------------
    # Private Methods
    # -------------------------------------------------------------------------

    def _parse_work_item_id(self, key: str) -> int:
        """Parse a work item key into an ID."""
        # Handle various formats
        # "123", "#123", "AB#123", etc.
        match = re.search(r"(\d+)", str(key))
        if match:
            return int(match.group(1))
        raise IssueTrackerError(f"Invalid work item key: {key}")

    def _parse_work_item(self, data: dict) -> IssueData:
        """Parse Azure DevOps work item into IssueData."""
        fields = data.get("fields", {})

        work_item_type = fields.get("System.WorkItemType", "")

        # Map work item type to our types
        if work_item_type.lower() == self.epic_type.lower():
            issue_type = "Epic"
        elif work_item_type.lower() == self.task_type.lower():
            issue_type = "Sub-task"
        else:
            issue_type = "Story"

        # Get assignee
        assignee = None
        assigned_to = fields.get("System.AssignedTo")
        if assigned_to:
            if isinstance(assigned_to, dict):
                assignee = assigned_to.get("uniqueName") or assigned_to.get("displayName")
            else:
                assignee = str(assigned_to)

        # Get story points
        story_points = fields.get("Microsoft.VSTS.Scheduling.StoryPoints")

        # Get children from relations
        subtasks = []
        relations = data.get("relations", [])
        for rel in relations:
            if rel.get("rel") == "System.LinkTypes.Hierarchy-Forward":
                # We'd need to fetch these separately for full data
                url = rel.get("url", "")
                if "/workItems/" in url:
                    child_id = url.split("/workItems/")[-1]
                    subtasks.append(
                        IssueData(
                            key=child_id,
                            summary=f"Child {child_id}",  # Placeholder
                            status="",
                            issue_type="Sub-task",
                        )
                    )

        return IssueData(
            key=str(data.get("id", "")),
            summary=fields.get("System.Title", ""),
            description=fields.get("System.Description"),
            status=fields.get("System.State", ""),
            issue_type=issue_type,
            assignee=assignee,
            story_points=float(story_points) if story_points else None,
            subtasks=subtasks,
            comments=[],
        )

    def _markdown_to_html(self, markdown: str) -> str:
        """
        Convert markdown to HTML for Azure DevOps.

        Basic conversion - for full fidelity, consider using a proper
        markdown library.
        """
        html = markdown

        # Headers
        html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
        html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
        html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)

        # Bold and italic
        html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
        html = re.sub(r"\*(.+?)\*", r"<em>\1</em>", html)

        # Code blocks
        html = re.sub(r"```(\w*)\n(.*?)```", r"<pre><code>\2</code></pre>", html, flags=re.DOTALL)
        html = re.sub(r"`([^`]+)`", r"<code>\1</code>", html)

        # Lists
        html = re.sub(r"^- (.+)$", r"<li>\1</li>", html, flags=re.MULTILINE)
        html = re.sub(r"(<li>.*</li>\n)+", r"<ul>\g<0></ul>", html)

        # Links
        html = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', html)

        # Paragraphs (simple - wrap non-tag lines)
        lines = html.split("\n")
        result = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith("<"):
                line = f"<p>{line}</p>"
            result.append(line)

        return "\n".join(result)

    # -------------------------------------------------------------------------
    # Extended Methods (Azure DevOps-specific)
    # -------------------------------------------------------------------------

    def create_epic(
        self,
        title: str,
        description: str | None = None,
        area_path: str | None = None,
        iteration_path: str | None = None,
    ) -> str:
        """Create an Epic work item."""
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would create epic '{title}'")
            return "0"

        html_desc = self._markdown_to_html(description) if description else None

        result = self._client.create_work_item(
            work_item_type=self.epic_type,
            title=title,
            description=html_desc,
            area_path=area_path,
            iteration_path=iteration_path,
        )

        work_item_id = result.get("id", 0)
        self.logger.info(f"Created epic {work_item_id}: {title}")
        return str(work_item_id)

    def create_user_story(
        self,
        title: str,
        description: str | None = None,
        parent_id: int | None = None,
        story_points: float | None = None,
        assigned_to: str | None = None,
        state: str | None = None,
        area_path: str | None = None,
        iteration_path: str | None = None,
        tags: list[str] | None = None,
    ) -> str:
        """Create a User Story work item."""
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would create user story '{title}'")
            return "0"

        html_desc = self._markdown_to_html(description) if description else None

        result = self._client.create_work_item(
            work_item_type=self.story_type,
            title=title,
            description=html_desc,
            parent_id=parent_id,
            story_points=story_points,
            assigned_to=assigned_to,
            state=state,
            area_path=area_path,
            iteration_path=iteration_path,
            tags=tags,
        )

        work_item_id = result.get("id", 0)
        self.logger.info(f"Created user story {work_item_id}: {title}")
        return str(work_item_id)

    def get_work_item_types(self) -> list[dict[str, Any]]:
        """Get all available work item types for the project."""
        return self._client.get_work_item_types()

    def query_wiql(self, wiql: str, top: int = 200) -> list[IssueData]:
        """Execute a WIQL query and return results."""
        work_items = self._client.query_work_items(wiql, top)
        return [self._parse_work_item(wi) for wi in work_items]
