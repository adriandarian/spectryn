"""
Jira Adapter - Implements IssueTrackerPort for Atlassian Jira.

This is the main entry point for Jira integration.
"""

import logging
from typing import Any

from spectra.adapters.formatters.adf import ADFFormatter
from spectra.core.constants import IssueType, JiraField
from spectra.core.domain.value_objects import CommitRef
from spectra.core.ports.config_provider import TrackerConfig
from spectra.core.ports.issue_tracker import (
    IssueData,
    IssueLink,
    IssueTrackerError,
    IssueTrackerPort,
    LinkType,
)

from .batch import BatchResult, JiraBatchClient
from .client import JiraApiClient


class JiraAdapter(IssueTrackerPort):
    """
    Jira implementation of the IssueTrackerPort.

    Translates between domain entities and Jira's API.
    """

    # Default Jira field IDs (can be overridden)
    STORY_POINTS_FIELD = "customfield_10014"

    # Workflow transitions (varies by project)
    DEFAULT_TRANSITIONS = {
        "Analyze": {"to_open": "7"},
        "Open": {"to_in_progress": "4", "to_resolved": "5"},
        "In Progress": {"to_resolved": "5", "to_open": "301"},
    }

    def __init__(
        self,
        config: TrackerConfig,
        dry_run: bool = True,
        formatter: ADFFormatter | None = None,
    ):
        """
        Initialize the Jira adapter.

        Args:
            config: Tracker configuration
            dry_run: If True, don't make changes
            formatter: Optional custom ADF formatter
        """
        self.config = config
        self._dry_run = dry_run
        self.formatter = formatter or ADFFormatter()
        self.logger = logging.getLogger("JiraAdapter")

        self._client = JiraApiClient(
            base_url=config.url,
            email=config.email,
            api_token=config.api_token,
            dry_run=dry_run,
        )

        # Initialize batch client for bulk operations
        self._batch_client = JiraBatchClient(self._client)

        if config.story_points_field:
            self.STORY_POINTS_FIELD = config.story_points_field

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Properties
    # -------------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "Jira"

    @property
    def is_connected(self) -> bool:
        return self._client.is_connected

    def test_connection(self) -> bool:
        return self._client.test_connection()

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Read Operations
    # -------------------------------------------------------------------------

    def get_current_user(self) -> dict[str, Any]:
        return self._client.get_myself()

    def get_issue(self, issue_key: str) -> IssueData:
        fields = ",".join(JiraField.ISSUE_WITH_SUBTASKS)
        data = self._client.get(f"issue/{issue_key}", params={JiraField.FIELDS: fields})
        return self._parse_issue(data)

    def get_epic_children(self, epic_key: str) -> list[IssueData]:
        jql = f"{JiraField.PARENT} = {epic_key} ORDER BY {JiraField.KEY} ASC"
        data = self._client.search_jql(jql, list(JiraField.ISSUE_WITH_SUBTASKS))

        return [self._parse_issue(issue) for issue in data.get("issues", [])]

    def get_issue_comments(self, issue_key: str) -> list[dict]:
        data = self._client.get(f"issue/{issue_key}/comment")
        return data.get("comments", [])

    def get_issue_status(self, issue_key: str) -> str:
        data = self._client.get(f"issue/{issue_key}", params={JiraField.FIELDS: JiraField.STATUS})
        return data[JiraField.FIELDS][JiraField.STATUS][JiraField.NAME]

    def search_issues(self, query: str, max_results: int = 50) -> list[IssueData]:
        data = self._client.search_jql(query, list(JiraField.BASIC_FIELDS), max_results=max_results)
        return [self._parse_issue(issue) for issue in data.get("issues", [])]

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Write Operations
    # -------------------------------------------------------------------------

    def update_issue_description(self, issue_key: str, description: Any) -> bool:
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would update description for {issue_key}")
            return True

        # Convert to ADF if string
        if isinstance(description, str):
            description = self.formatter.format_text(description)

        self._client.put(
            f"issue/{issue_key}", json={JiraField.FIELDS: {JiraField.DESCRIPTION: description}}
        )
        self.logger.info(f"Updated description for {issue_key}")
        return True

    def update_issue_type(self, issue_key: str, issue_type: str) -> bool:
        """
        Change an issue's type.

        Args:
            issue_key: The issue key (e.g., 'PROJ-123').
            issue_type: The new issue type name (e.g., 'User Story').

        Returns:
            True if successful.
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would change {issue_key} type to '{issue_type}'")
            return True

        self._client.put(
            f"issue/{issue_key}",
            json={JiraField.FIELDS: {JiraField.ISSUETYPE: {JiraField.NAME: issue_type}}},
        )
        self.logger.info(f"Changed {issue_key} type to '{issue_type}'")
        return True

    def create_story(
        self,
        summary: str,
        description: Any,
        project_key: str,
        epic_key: str | None = None,
        story_points: int | None = None,
        priority: str | None = None,
        assignee: str | None = None,
        issue_type: str = "Story",
    ) -> str | None:
        """
        Create a new story issue in Jira.

        Args:
            summary: Story title/summary.
            description: Story description (can be string or ADF).
            project_key: Project key (e.g., 'PROJ').
            epic_key: Epic key to link to (e.g., 'PROJ-123').
            story_points: Optional story points.
            priority: Optional priority name.
            assignee: Optional assignee account ID.
            issue_type: Issue type name (default: 'Story').

        Returns:
            New issue key (e.g., 'PROJ-456') or None if dry-run.
        """
        if self._dry_run:
            self.logger.debug(f"[DRY-RUN] Would create {issue_type} '{summary[:50]}...'")
            return None

        # Auto-assign to current user if no assignee specified
        if assignee is None:
            import contextlib

            with contextlib.suppress(Exception):
                assignee = self._client.get_current_user_id()

        # Convert description to ADF if string
        if isinstance(description, str):
            description = self.formatter.format_text(description)

        fields: dict[str, Any] = {
            JiraField.PROJECT: {JiraField.KEY: project_key},
            JiraField.SUMMARY: summary[:255],
            JiraField.DESCRIPTION: description,
            JiraField.ISSUETYPE: {JiraField.NAME: issue_type},
        }

        # Link to epic (using parent field for next-gen projects, or epic link for classic)
        if epic_key:
            # Try parent field first (next-gen/team-managed projects)
            fields[JiraField.PARENT] = {JiraField.KEY: epic_key}

        if story_points is not None:
            fields[self.STORY_POINTS_FIELD] = float(story_points)

        if priority:
            fields[JiraField.PRIORITY] = {JiraField.NAME: priority}

        if assignee:
            fields[JiraField.ASSIGNEE] = {JiraField.ACCOUNT_ID: assignee}

        result = self._client.post("issue", json={"fields": fields})
        new_key = result.get("key")

        if new_key:
            self.logger.info(f"Created {issue_type} {new_key}: {summary[:50]}")

        return new_key

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
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would create subtask '{summary[:50]}...' under {parent_key}"
            )
            return None

        # Get current user if no assignee
        if assignee is None:
            assignee = self._client.get_current_user_id()

        # Convert description to ADF if string
        if isinstance(description, str):
            description = self.formatter.format_text(description)

        fields: dict[str, Any] = {
            JiraField.PROJECT: {JiraField.KEY: project_key},
            JiraField.PARENT: {JiraField.KEY: parent_key},
            JiraField.SUMMARY: summary[:255],
            JiraField.DESCRIPTION: description,
            JiraField.ISSUETYPE: {JiraField.NAME: IssueType.JIRA_SUBTASK},
            JiraField.ASSIGNEE: {JiraField.ACCOUNT_ID: assignee},
        }

        if story_points is not None:
            fields[self.STORY_POINTS_FIELD] = float(story_points)

        if priority is not None:
            fields[JiraField.PRIORITY] = {JiraField.NAME: priority}

        result = self._client.post("issue", json={"fields": fields})
        new_key = result.get("key")

        if new_key:
            self.logger.info(f"Created subtask {new_key} under {parent_key}")

        return new_key

    def update_subtask(
        self,
        issue_key: str,
        description: Any | None = None,
        story_points: int | None = None,
        assignee: str | None = None,
    ) -> bool:
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would update subtask {issue_key}")
            return True

        fields: dict[str, Any] = {}

        if description is not None:
            if isinstance(description, str):
                description = self.formatter.format_text(description)
            fields["description"] = description

        if story_points is not None:
            fields[self.STORY_POINTS_FIELD] = float(story_points)

        if assignee is not None:
            fields["assignee"] = {"accountId": assignee}

        if fields:
            self._client.put(f"issue/{issue_key}", json={"fields": fields})
            self.logger.info(f"Updated subtask {issue_key}")

        return True

    def add_comment(self, issue_key: str, body: Any) -> bool:
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would add comment to {issue_key}")
            return True

        if isinstance(body, str):
            body = self.formatter.format_text(body)

        self._client.post(f"issue/{issue_key}/comment", json={"body": body})
        self.logger.info(f"Added comment to {issue_key}")
        return True

    def transition_issue(self, issue_key: str, target_status: str) -> bool:
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would transition {issue_key} to {target_status}")
            return True

        current = self.get_issue_status(issue_key)
        if current.lower() == target_status.lower():
            return True

        # Get transition path
        target_lower = target_status.lower()

        if "resolved" in target_lower or "done" in target_lower:
            path = [
                ("Analyze", "7", None),
                ("Open", "4", None),
                ("In Progress", "5", "Done"),
            ]
        elif "progress" in target_lower:
            path = [
                ("Analyze", "7", None),
                ("Open", "4", None),
            ]
        elif "open" in target_lower:
            path = [("Analyze", "7", None)]
        else:
            self.logger.warning(f"Unknown target status: {target_status}")
            return False

        # Execute transitions
        for from_status, transition_id, resolution in path:
            current = self.get_issue_status(issue_key)
            if current == from_status:
                if not self._do_transition(issue_key, transition_id, resolution):
                    return False

        # Verify final status
        final = self.get_issue_status(issue_key)
        return target_lower in final.lower()

    def _do_transition(
        self, issue_key: str, transition_id: str, resolution: str | None = None
    ) -> bool:
        """Execute a single transition."""
        payload: dict[str, Any] = {"transition": {"id": transition_id}}

        if resolution:
            payload["fields"] = {"resolution": {"name": resolution}}

        try:
            self._client.post(f"issue/{issue_key}/transitions", json=payload)
            return True
        except IssueTrackerError as e:
            self.logger.error(f"Transition failed: {e}")
            return False

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Utility
    # -------------------------------------------------------------------------

    def get_available_transitions(self, issue_key: str) -> list[dict]:
        data = self._client.get(f"issue/{issue_key}/transitions")
        return data.get("transitions", [])

    def format_description(self, markdown: str) -> Any:
        return self.formatter.format_text(markdown)

    # -------------------------------------------------------------------------
    # Private Methods
    # -------------------------------------------------------------------------

    def _parse_issue(self, data: dict) -> IssueData:
        """Parse Jira API response into IssueData."""
        fields = data.get(JiraField.FIELDS, {})

        subtasks = []
        for st in fields.get(JiraField.SUBTASKS, []):
            subtasks.append(
                IssueData(
                    key=st[JiraField.KEY],
                    summary=st[JiraField.FIELDS][JiraField.SUMMARY],
                    status=st[JiraField.FIELDS][JiraField.STATUS][JiraField.NAME],
                    issue_type=IssueType.SUBTASK,
                )
            )

        return IssueData(
            key=data[JiraField.KEY],
            summary=fields.get(JiraField.SUMMARY, ""),
            description=fields.get(JiraField.DESCRIPTION),
            status=fields.get(JiraField.STATUS, {}).get(JiraField.NAME, ""),
            issue_type=fields.get(JiraField.ISSUETYPE, {}).get(JiraField.NAME, ""),
            subtasks=subtasks,
        )

    # -------------------------------------------------------------------------
    # Extended Methods (Jira-specific)
    # -------------------------------------------------------------------------

    def get_priorities(self) -> list[str]:
        """
        Get available priority names from Jira.

        Returns:
            List of priority names (e.g., ['Highest', 'High', 'Medium', 'Low', 'Lowest'])
        """
        try:
            data = self._client.get("priority")
            return [p.get("name", "") for p in data if p.get("name")]
        except Exception as e:
            self.logger.warning(f"Failed to fetch priorities: {e}")
            return []

    def get_project_issue_types(self, project_key: str) -> list[str]:
        """
        Get available issue types for a project.

        Args:
            project_key: Project key (e.g., 'UPP')

        Returns:
            List of issue type names
        """
        try:
            data = self._client.get(f"project/{project_key}")
            issue_types = data.get("issueTypes", [])
            return [it.get("name", "") for it in issue_types if it.get("name")]
        except Exception as e:
            self.logger.warning(f"Failed to fetch issue types: {e}")
            return []

    def update_issue_fields(
        self,
        issue_key: str,
        priority: str | None = None,
        assignee: str | None = None,
    ) -> bool:
        """
        Update issue fields (priority, assignee).

        Args:
            issue_key: The issue key.
            priority: Priority name to set.
            assignee: Assignee account ID.

        Returns:
            True if successful.
        """
        if self._dry_run:
            updates = []
            if priority:
                updates.append(f"priority={priority}")
            if assignee:
                updates.append(f"assignee={assignee}")
            if updates:
                self.logger.info(f"[DRY-RUN] Would update {issue_key}: {', '.join(updates)}")
            return True

        fields: dict[str, Any] = {}
        if priority:
            fields[JiraField.PRIORITY] = {JiraField.NAME: priority}
        if assignee:
            fields[JiraField.ASSIGNEE] = {JiraField.ACCOUNT_ID: assignee}

        if not fields:
            return True

        self._client.put(f"issue/{issue_key}", json={JiraField.FIELDS: fields})
        self.logger.info(f"Updated {issue_key} fields")
        return True

    def add_commits_comment(self, issue_key: str, commits: list[CommitRef]) -> bool:
        """Add a formatted commits table as a comment."""
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would add commits comment to {issue_key}")
            return True

        adf = self.formatter.format_commits_table(commits)
        return self.add_comment(issue_key, adf)

    def get_subtask_details(self, issue_key: str) -> dict[str, Any]:
        """Get full details of a subtask."""
        data = self._client.get(
            f"issue/{issue_key}",
            params={"fields": f"summary,description,assignee,status,{self.STORY_POINTS_FIELD}"},
        )

        fields = data.get("fields", {})
        return {
            "key": data["key"],
            "summary": fields.get("summary", ""),
            "description": fields.get("description"),
            "assignee": fields.get("assignee"),
            "story_points": fields.get(self.STORY_POINTS_FIELD),
            "status": fields.get("status", {}).get("name", ""),
        }

    # -------------------------------------------------------------------------
    # Link Operations (Cross-Project Linking)
    # -------------------------------------------------------------------------

    def get_issue_links(self, issue_key: str) -> list[IssueLink]:
        """
        Get all links for an issue.

        Args:
            issue_key: Issue to get links for

        Returns:
            List of IssueLinks
        """
        try:
            data = self._client.get(f"issue/{issue_key}", params={"fields": "issuelinks"})
        except IssueTrackerError as e:
            self.logger.error(f"Failed to get links for {issue_key}: {e}")
            return []

        links = []
        fields = data.get("fields", {})
        issue_links = fields.get("issuelinks", [])

        for link in issue_links:
            link_type_data = link.get("type", {})

            # Determine direction and get target
            if "outwardIssue" in link:
                target = link["outwardIssue"]
                link_name = link_type_data.get("outward", "relates to")
            elif "inwardIssue" in link:
                target = link["inwardIssue"]
                link_name = link_type_data.get("inward", "relates to")
            else:
                continue

            target_key = target.get("key", "")
            if target_key:
                links.append(
                    IssueLink(
                        link_type=LinkType.from_string(link_name),
                        target_key=target_key,
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
        """
        Create a link between two issues.

        Supports cross-project linking - issues can be in different Jira projects.

        Args:
            source_key: Source issue key (e.g., "PROJ-123")
            target_key: Target issue key (e.g., "OTHER-456")
            link_type: Type of link to create

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would create link: {source_key} {link_type.value} {target_key}"
            )
            return True

        # Determine inward/outward based on link type
        if link_type.is_outward:
            payload = {
                "type": {"name": link_type.jira_name},
                "outwardIssue": {"key": target_key},
                "inwardIssue": {"key": source_key},
            }
        else:
            payload = {
                "type": {"name": link_type.jira_name},
                "inwardIssue": {"key": target_key},
                "outwardIssue": {"key": source_key},
            }

        try:
            self._client.post("issueLink", json=payload)
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
        """
        Delete a link between issues.

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

        # Get existing links to find the link ID
        try:
            data = self._client.get(f"issue/{source_key}", params={"fields": "issuelinks"})
        except IssueTrackerError as e:
            self.logger.error(f"Failed to get links for deletion: {e}")
            return False

        fields = data.get("fields", {})
        issue_links = fields.get("issuelinks", [])

        for link in issue_links:
            link_id = link.get("id")
            if not link_id:
                continue

            # Check if this is the link we want to delete
            outward = link.get("outwardIssue", {}).get("key")
            inward = link.get("inwardIssue", {}).get("key")

            if target_key in (outward, inward):
                # If link_type specified, check it matches
                if link_type:
                    link_type_data = link.get("type", {})
                    link_name = link_type_data.get("name", "")
                    if link_name != link_type.jira_name:
                        continue

                try:
                    self._client.delete(f"issueLink/{link_id}")
                    self.logger.info(f"Deleted link: {source_key} -> {target_key}")
                    return True
                except IssueTrackerError as e:
                    self.logger.error(f"Failed to delete link: {e}")
                    return False

        self.logger.warning(f"Link not found: {source_key} -> {target_key}")
        return False

    def get_link_types(self) -> list[dict[str, Any]]:
        """
        Get available link types from Jira.

        Returns:
            List of link type definitions
        """
        try:
            data = self._client.get("issueLinkType")
            return data.get("issueLinkTypes", [])
        except IssueTrackerError as e:
            self.logger.error(f"Failed to get link types: {e}")
            return []

    def sync_links(
        self,
        issue_key: str,
        desired_links: list[tuple[str, str]],
    ) -> dict[str, int]:
        """
        Sync links for an issue to match the desired state.

        Args:
            issue_key: Issue to sync links for
            desired_links: List of (link_type, target_key) tuples

        Returns:
            Dict with created, deleted, unchanged counts
        """
        result = {"created": 0, "deleted": 0, "unchanged": 0}

        # Get existing links
        existing = self.get_issue_links(issue_key)
        existing_set = {(link.link_type.value, link.target_key) for link in existing}

        # Convert desired to set
        desired_set = set(desired_links)

        # Links to create
        to_create = desired_set - existing_set
        for link_type_str, target_key in to_create:
            link_type = LinkType.from_string(link_type_str)
            if self.create_link(issue_key, target_key, link_type):
                result["created"] += 1

        # Links to delete
        to_delete = existing_set - desired_set
        for link_type_str, target_key in to_delete:
            link_type = LinkType.from_string(link_type_str)
            if self.delete_link(issue_key, target_key, link_type):
                result["deleted"] += 1

        # Unchanged
        result["unchanged"] = len(existing_set & desired_set)

        return result

    # -------------------------------------------------------------------------
    # Batch Operations
    # -------------------------------------------------------------------------

    @property
    def batch_client(self) -> JiraBatchClient:
        """Get the batch client for bulk operations."""
        return self._batch_client

    def bulk_create_subtasks(
        self,
        parent_key: str,
        project_key: str,
        subtasks: list[dict[str, Any]],
        assignee: str | None = None,
    ) -> BatchResult:
        """
        Create multiple subtasks using Jira's bulk create API.

        More efficient than creating subtasks one by one.

        Args:
            parent_key: Parent issue key
            project_key: Project key
            subtasks: List of subtask data dicts
            assignee: Optional assignee for all subtasks

        Returns:
            BatchResult with created subtask keys
        """
        return self._batch_client.bulk_create_subtasks(
            parent_key=parent_key,
            project_key=project_key,
            subtasks=subtasks,
            assignee=assignee,
        )

    def bulk_update_descriptions(
        self,
        updates: list[tuple[str, Any]],
    ) -> BatchResult:
        """
        Update descriptions for multiple issues in parallel.

        Args:
            updates: List of (issue_key, description_adf) tuples

        Returns:
            BatchResult
        """
        return self._batch_client.bulk_update_descriptions(updates)

    def bulk_transition_issues(
        self,
        transitions: list[tuple[str, str]],
    ) -> BatchResult:
        """
        Transition multiple issues in parallel.

        Args:
            transitions: List of (issue_key, target_status) tuples

        Returns:
            BatchResult
        """
        return self._batch_client.bulk_transition_issues(transitions)

    def bulk_add_comments(
        self,
        comments: list[tuple[str, Any]],
    ) -> BatchResult:
        """
        Add comments to multiple issues in parallel.

        Args:
            comments: List of (issue_key, comment_body_adf) tuples

        Returns:
            BatchResult
        """
        return self._batch_client.bulk_add_comments(comments)

    # -------------------------------------------------------------------------
    # Async Operations (Optional - requires aiohttp)
    # -------------------------------------------------------------------------

    def get_async_client(self) -> "AsyncJiraAdapter":
        """
        Get an async-capable version of this adapter.

        Returns an AsyncJiraAdapter that implements AsyncIssueTrackerPort
        for parallel operations using asyncio.

        Requires aiohttp: pip install aiohttp

        Example:
            >>> async with adapter.get_async_client() as async_adapter:
            ...     issues = await async_adapter.get_issues_async(keys)

        Returns:
            AsyncJiraAdapter instance

        Raises:
            ImportError: If aiohttp is not installed
        """
        from .async_adapter import AsyncJiraAdapter

        return AsyncJiraAdapter(
            config=self.config,
            dry_run=self._dry_run,
            formatter=self.formatter,
        )
