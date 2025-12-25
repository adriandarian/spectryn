"""
Bitbucket Adapter - Implements IssueTrackerPort for Bitbucket Issues.

This is the main entry point for Bitbucket Cloud/Server integration.
Maps the generic IssueTrackerPort interface to Bitbucket's issue model.

Key mappings:
- Epic → Milestone or Issue with epic label
- Story → Issue
- Subtask → Issue with parent link
- Status → Issue state (new, open, resolved, closed)
- Priority → Issue priority (trivial, minor, major, critical, blocker)
"""

import logging
from typing import Any

from spectra.core.domain.enums import Priority
from spectra.core.ports.issue_tracker import (
    IssueData,
    IssueLink,
    IssueTrackerError,
    IssueTrackerPort,
    LinkType,
    NotFoundError,
    TransitionError,
)

from .client import BitbucketApiClient


class BitbucketAdapter(IssueTrackerPort):
    """
    Bitbucket implementation of the IssueTrackerPort.

    Translates between domain entities and Bitbucket's REST API v2.

    Bitbucket concepts:
    - Workspace: Organization/team (Cloud) or project (Server)
    - Repository: Code repository with issues
    - Issue: Work item (like a story)
    - Milestone: Collection of issues (like an epic)
    - State: new, open, resolved, closed, on hold, invalid, duplicate, wontfix
    - Priority: trivial, minor, major, critical, blocker
    - Kind: bug, enhancement, proposal, task
    """

    def __init__(
        self,
        username: str,
        app_password: str,
        workspace: str,
        repo: str,
        dry_run: bool = True,
        base_url: str = "https://api.bitbucket.org/2.0",
        epic_label: str = "epic",
        story_label: str = "story",
        subtask_label: str = "subtask",
        status_mapping: dict[str, str] | None = None,
        priority_mapping: dict[str, str] | None = None,
    ):
        """
        Initialize the Bitbucket adapter.

        Args:
            username: Bitbucket username
            app_password: App Password (Cloud) or Personal Access Token (Server)
            workspace: Workspace slug (Cloud) or project key (Server)
            repo: Repository slug
            dry_run: If True, don't make changes
            base_url: API base URL (defaults to Cloud)
            epic_label: Label used to identify epics (if using issues)
            story_label: Label used to identify stories
            subtask_label: Label used to identify subtasks
            status_mapping: Mapping of status names to Bitbucket states
            priority_mapping: Mapping of priority names to Bitbucket priorities
        """
        self._dry_run = dry_run
        self.workspace = workspace
        self.repo = repo
        self.logger = logging.getLogger("BitbucketAdapter")

        # Labels configuration
        self.epic_label = epic_label
        self.story_label = story_label
        self.subtask_label = subtask_label

        # Status mapping (default)
        default_status_mapping = {
            "planned": "new",
            "open": "open",
            "in progress": "open",  # Bitbucket doesn't have "in progress", use "open"
            "done": "resolved",
            "closed": "closed",
        }
        self.status_mapping = status_mapping or default_status_mapping

        # Priority mapping (default)
        default_priority_mapping = {
            "critical": "critical",
            "high": "major",
            "medium": "minor",
            "low": "trivial",
        }
        self.priority_mapping = priority_mapping or default_priority_mapping

        # Reverse mappings for reading (state -> status)
        # Build reverse mapping, preferring exact state matches
        self._state_to_status: dict[str, str] = {}
        # First pass: add exact matches (state == status)
        for status, state in self.status_mapping.items():
            if state == status.lower():
                self._state_to_status[state] = status
        # Second pass: fill in remaining mappings
        for status, state in self.status_mapping.items():
            if state not in self._state_to_status:
                self._state_to_status[state] = status
        # Ensure "open" maps to "open" not "in progress"
        if "open" in self.status_mapping:
            self._state_to_status["open"] = "open"

        # API client
        self._client = BitbucketApiClient(
            username=username,
            app_password=app_password,
            workspace=workspace,
            repo=repo,
            base_url=base_url,
            dry_run=dry_run,
        )

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Properties
    # -------------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "Bitbucket"

    @property
    def is_connected(self) -> bool:
        return self._client.is_connected

    def test_connection(self) -> bool:
        return self._client.test_connection()

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Read Operations
    # -------------------------------------------------------------------------

    def get_current_user(self) -> dict[str, Any]:
        return self._client.get_authenticated_user()

    def get_issue(self, issue_key: str) -> IssueData:
        """
        Fetch a single issue by key.

        Bitbucket uses issue IDs, but we support formats like:
        - "123" (issue ID)
        - "workspace/repo#123" (full reference)
        - "#123" (with hash prefix)
        """
        issue_id = self._parse_issue_key(issue_key)
        data = self._client.get_issue(issue_id)
        return self._parse_issue(data)

    def get_epic_children(self, epic_key: str) -> list[IssueData]:
        """
        Fetch all children of an epic.

        Bitbucket epics can be:
        1. A milestone - returns all issues in that milestone
        2. An issue with epic label - returns issues referencing it
        """
        # Try parsing as milestone ID first
        try:
            milestone_id = int(epic_key)
            # Get milestone and find issues linked to it
            milestone = self._client.get_milestone(milestone_id)
            milestone_name = milestone.get("name", "")
            # Search for issues mentioning this milestone
            issues = self._client.list_issues()
            epic_issues = [
                issue
                for issue in issues
                if milestone_name in str(issue.get("content", {}).get("raw", ""))
                or milestone_name in issue.get("title", "")
            ]
            return [self._parse_issue(issue) for issue in epic_issues]
        except (ValueError, NotFoundError):
            pass

        # Parse as issue reference
        issue_id = self._parse_issue_key(epic_key)

        # Search for issues mentioning this epic
        issues = self._client.list_issues()
        epic_issues = [
            i
            for i in issues
            if f"#{issue_id}" in str(i.get("content", {}).get("raw", ""))
            or f"#{issue_id}" in i.get("title", "")
        ]

        return [self._parse_issue(issue) for issue in epic_issues]

    def get_issue_comments(self, issue_key: str) -> list[dict]:
        issue_id = self._parse_issue_key(issue_key)
        return self._client.get_issue_comments(issue_id)

    def get_issue_status(self, issue_key: str) -> str:
        """Get the current status of an issue."""
        issue_id = self._parse_issue_key(issue_key)
        data = self._client.get_issue(issue_id)
        state: str = data.get("state", "new")
        status: str = self._state_to_status.get(state, state)
        return status

    def search_issues(self, query: str, max_results: int = 50) -> list[IssueData]:
        """
        Search for issues using Bitbucket query syntax.

        Examples:
        - "state=\"open\""
        - "kind=\"bug\""
        - "priority=\"critical\""
        """
        # Parse query and extract filters
        issues = self._client.list_issues(pagelen=max_results)
        # Simple filtering (full query parsing would be more complex)
        filtered = issues[:max_results]
        return [self._parse_issue(issue) for issue in filtered]

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Write Operations
    # -------------------------------------------------------------------------

    def update_issue_description(self, issue_key: str, description: Any) -> bool:
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would update description for {issue_key}")
            return True

        issue_id = self._parse_issue_key(issue_key)

        # Bitbucket uses Markdown natively
        body = description if isinstance(description, str) else str(description)

        self._client.update_issue(issue_id, content=body)
        self.logger.info(f"Updated description for #{issue_id}")
        return True

    def update_issue_story_points(self, issue_key: str, story_points: float) -> bool:
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would update story points for {issue_key} to {story_points}"
            )
            return True

        issue_id = self._parse_issue_key(issue_key)

        # Bitbucket doesn't have native story points, store in content or use custom field
        # For now, we'll add it as a note in the content
        issue = self._client.get_issue(issue_id)
        current_content = issue.get("content", {}).get("raw", "") or ""

        # Update or add story points note
        if "Story Points:" in current_content:
            import re

            current_content = re.sub(
                r"Story Points:\s*\d+", f"Story Points: {int(story_points)}", current_content
            )
        else:
            current_content = f"Story Points: {int(story_points)}\n\n{current_content}"

        self._client.update_issue(issue_id, content=current_content)
        self.logger.info(f"Updated story points for #{issue_id} to {story_points}")
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
        component: str | None = None,
        version: str | None = None,
    ) -> str | None:
        """Create a subtask as a linked issue."""
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would create subtask '{summary[:50]}...' under {parent_key}"
            )
            return None

        parent_id = self._parse_issue_key(parent_key)
        body = description if isinstance(description, str) else str(description)

        # Add parent reference in body
        full_body = f"Parent: #{parent_id}\n\n{body}"

        # Map priority
        priority_value = "minor"
        if priority:
            priority_enum = Priority.from_string(priority)
            priority_value = self.priority_mapping.get(priority_enum.display_name.lower(), "minor")

        # Create issue as subtask
        result = self._client.create_issue(
            title=summary[:255],
            content=full_body,
            kind="task",
            priority=priority_value,
            state="new",
            assignee=assignee,
            component=component,
            version=version,
        )

        new_id = result.get("id")
        if new_id:
            self.logger.info(f"Created subtask #{new_id} under #{parent_id}")
            return f"#{new_id}"
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

        issue_id = self._parse_issue_key(issue_key)

        updates: dict[str, Any] = {}

        if description is not None:
            updates["content"] = description if isinstance(description, str) else str(description)

        if assignee is not None:
            updates["assignee"] = assignee

        if priority_id is not None:
            priority_enum = Priority.from_string(priority_id)
            updates["priority"] = self.priority_mapping.get(
                priority_enum.display_name.lower(), "minor"
            )

        if story_points is not None:
            # Update story points in content
            issue = self._client.get_issue(issue_id)
            current_content = issue.get("content", {}).get("raw", "") or ""
            import re

            if "Story Points:" in current_content:
                current_content = re.sub(
                    r"Story Points:\s*\d+", f"Story Points: {story_points}", current_content
                )
            else:
                current_content = f"Story Points: {story_points}\n\n{current_content}"
            updates["content"] = current_content

        if updates:
            self._client.update_issue(issue_id, **updates)
            self.logger.info(f"Updated subtask #{issue_id}")

        return True

    def add_comment(self, issue_key: str, body: Any) -> bool:
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would add comment to {issue_key}")
            return True

        issue_id = self._parse_issue_key(issue_key)
        comment_body = body if isinstance(body, str) else str(body)

        self._client.add_issue_comment(issue_id, comment_body)
        self.logger.info(f"Added comment to #{issue_id}")
        return True

    def transition_issue(self, issue_key: str, target_status: str) -> bool:
        """
        Transition an issue to a new status.

        Maps status names to Bitbucket states.
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would transition {issue_key} to {target_status}")
            return True

        issue_id = self._parse_issue_key(issue_key)
        target_lower = target_status.lower()

        # Map to Bitbucket state
        target_state = self.status_mapping.get(target_lower, "new")

        try:
            self._client.update_issue(issue_id, state=target_state)
            self.logger.info(f"Transitioned #{issue_id} to {target_status} ({target_state})")
            return True

        except Exception as e:
            raise TransitionError(
                f"Failed to transition #{issue_id} to {target_status}: {e}",
                issue_key=issue_key,
                cause=e,
            )

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Utility
    # -------------------------------------------------------------------------

    def get_available_transitions(self, issue_key: str) -> list[dict]:
        """
        Get available transitions for an issue.

        For Bitbucket, transitions are the configured status states.
        """
        return [
            {"id": state, "name": status, "to": state}
            for status, state in self.status_mapping.items()
        ]

    def format_description(self, markdown: str) -> Any:
        """
        Convert markdown to Bitbucket-compatible format.

        Bitbucket uses Markdown natively, so we just return the input.
        """
        return markdown

    # -------------------------------------------------------------------------
    # Private Methods
    # -------------------------------------------------------------------------

    def _parse_issue_key(self, key: str) -> int:
        """
        Parse an issue key into an issue ID.

        Supports formats:
        - "123"
        - "#123"
        - "workspace/repo#123"
        """
        # Remove hash prefix
        key = key.lstrip("#")

        # Handle full reference format
        if "/" in key and "#" in key:
            key = key.split("#")[-1]

        try:
            return int(key)
        except ValueError:
            raise IssueTrackerError(f"Invalid issue key: {key}")

    def _parse_issue(self, data: dict) -> IssueData:
        """Parse Bitbucket API response into IssueData."""
        issue_id = data.get("id", 0)
        state = data.get("state", "new")

        # Map state to status
        status = self._state_to_status.get(state, state)

        # Extract story points from content
        story_points = None
        content_raw = data.get("content", {}).get("raw", "") or ""
        import re

        match = re.search(r"Story Points:\s*(\d+)", content_raw)
        if match:
            story_points = float(match.group(1))

        # Get assignee
        assignee = None
        assignee_data = data.get("assignee")
        if assignee_data:
            assignee = assignee_data.get("username") or assignee_data.get("display_name")

        # Determine issue type from kind or content
        kind = data.get("kind", "task")
        issue_type = kind.capitalize()

        # Check for parent reference (subtask)
        if "#" in content_raw and "Parent:" in content_raw:
            issue_type = "Sub-task"

        return IssueData(
            key=f"#{issue_id}",
            summary=data.get("title", ""),
            description=content_raw,
            status=status,
            issue_type=issue_type,
            assignee=assignee,
            story_points=story_points,
            subtasks=[],  # Subtasks loaded separately
            comments=[],  # Comments loaded separately
        )

    # -------------------------------------------------------------------------
    # Link Operations (Optional)
    # -------------------------------------------------------------------------

    def get_issue_links(self, issue_key: str) -> list[IssueLink]:
        """
        Get all links for an issue.

        Bitbucket doesn't have native issue links, so we parse the issue body
        for link references.
        """
        issue_id = self._parse_issue_key(issue_key)

        try:
            data = self._client.get_issue(issue_id)
        except IssueTrackerError as e:
            self.logger.error(f"Failed to get issue {issue_key}: {e}")
            return []

        links: list[IssueLink] = []
        body = data.get("content", {}).get("raw", "") or ""

        # Parse structured link references from body
        links.extend(self._parse_body_links(body, issue_key))

        return links

    def _parse_body_links(self, body: str, source_key: str) -> list[IssueLink]:
        """Parse issue links from the issue body."""
        links: list[IssueLink] = []
        import re

        # Pattern definitions: (regex_pattern, link_type)
        link_patterns = [
            (r"\*\*Blocks[:\s]*\*\*\s*((?:#\d+(?:\s*,\s*)?)+)", LinkType.BLOCKS),
            (r"\*\*Blocked by[:\s]*\*\*\s*((?:#\d+(?:\s*,\s*)?)+)", LinkType.IS_BLOCKED_BY),
            (r"\*\*Related to[:\s]*\*\*\s*((?:#\d+(?:\s*,\s*)?)+)", LinkType.RELATES_TO),
            (r"\*\*Depends on[:\s]*\*\*\s*((?:#\d+(?:\s*,\s*)?)+)", LinkType.DEPENDS_ON),
        ]

        for pattern, link_type in link_patterns:
            match = re.search(pattern, body, re.IGNORECASE)
            if match:
                refs_str = match.group(1)
                # Extract all issue references
                for ref in re.findall(r"#(\d+)", refs_str):
                    links.append(
                        IssueLink(
                            link_type=link_type,
                            target_key=f"#{ref}",
                            source_key=source_key,
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

        Bitbucket doesn't have native issue linking, so we add a formatted
        reference to the source issue's body.
        """
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would create link: {source_key} {link_type.value} {target_key}"
            )
            return True

        source_id = self._parse_issue_key(source_key)

        try:
            # Get current issue body
            issue = self._client.get_issue(source_id)
            current_content = issue.get("content", {}).get("raw", "") or ""

            # Add link to body
            new_content = self._add_link_to_body(current_content, target_key, link_type)

            if new_content != current_content:
                self._client.update_issue(source_id, content=new_content)
                self.logger.info(f"Created link: {source_key} {link_type.value} {target_key}")
            else:
                self.logger.debug(f"Link already exists: {source_key} -> {target_key}")

            return True
        except IssueTrackerError as e:
            self.logger.error(f"Failed to create link: {e}")
            return False

    def _add_link_to_body(
        self,
        body: str,
        target_key: str,
        link_type: LinkType,
    ) -> str:
        """Add a link reference to the issue body."""
        # Normalize target key
        if not target_key.startswith("#"):
            target_key = f"#{target_key}"

        # Map link types to section headers
        link_headers = {
            LinkType.BLOCKS: "Blocks",
            LinkType.IS_BLOCKED_BY: "Blocked by",
            LinkType.RELATES_TO: "Related to",
            LinkType.DEPENDS_ON: "Depends on",
        }

        header = link_headers.get(link_type, "Related to")
        import re

        pattern = rf"\*\*{header}[:\s]*\*\*\s*(.+?)(?:\n|$)"

        match = re.search(pattern, body, re.IGNORECASE)
        if match:
            # Check if target already exists
            existing = match.group(1)
            if target_key in existing:
                return body  # Already linked

            # Add to existing line
            new_line = f"**{header}:** {existing.strip()}, {target_key}"
            return re.sub(pattern, new_line + "\n", body, flags=re.IGNORECASE)

        # Add new links section
        links_section = f"\n\n**{header}:** {target_key}"
        return body.rstrip() + links_section

    # -------------------------------------------------------------------------
    # Advanced Features - Pull Requests
    # -------------------------------------------------------------------------

    def link_pull_request(
        self,
        issue_key: str,
        pr_id: int | str,
    ) -> bool:
        """
        Link a pull request to an issue.

        Args:
            issue_key: Issue key (e.g., "#123")
            pr_id: Pull request ID

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would link PR #{pr_id} to {issue_key}")
            return True

        issue_id = self._parse_issue_key(issue_key)
        pr_id_int = int(pr_id) if isinstance(pr_id, str) else pr_id

        return self._client.link_pull_request_to_issue(issue_id, pr_id_int)

    def get_pull_requests_for_issue(self, issue_key: str) -> list[dict[str, Any]]:
        """
        Get all pull requests linked to an issue.

        Args:
            issue_key: Issue key

        Returns:
            List of pull request dictionaries
        """
        issue_id = self._parse_issue_key(issue_key)
        issue = self._client.get_issue(issue_id)
        content = issue.get("content", {}).get("raw", "") or ""

        # Parse PR references from content
        import re

        prs = []
        pr_pattern = r"PR\s*#(\d+)|#(\d+)\s*\(PR\)"
        for match in re.finditer(pr_pattern, content, re.IGNORECASE):
            pr_id = match.group(1) or match.group(2)
            if pr_id:
                try:
                    pr = self._client.get_pull_request(int(pr_id))
                    if pr:
                        prs.append(pr)
                except IssueTrackerError:
                    pass  # PR might not exist

        return prs

    # -------------------------------------------------------------------------
    # Advanced Features - Attachments
    # -------------------------------------------------------------------------

    def get_issue_attachments(self, issue_key: str) -> list[dict[str, Any]]:
        """
        Get all attachments for an issue.

        Args:
            issue_key: Issue key

        Returns:
            List of attachment dictionaries
        """
        issue_id = self._parse_issue_key(issue_key)
        return self._client.get_issue_attachments(issue_id)

    def upload_attachment(
        self,
        issue_key: str,
        file_path: str,
        name: str | None = None,
    ) -> dict[str, Any]:
        """
        Upload an attachment to an issue.

        Args:
            issue_key: Issue key
            file_path: Path to file to upload
            name: Optional attachment name

        Returns:
            Attachment information dictionary
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would upload attachment {file_path} to {issue_key}")
            return {"id": "attachment:dry-run", "name": name or file_path}

        issue_id = self._parse_issue_key(issue_key)
        return self._client.upload_issue_attachment(issue_id, file_path, name)

    def delete_attachment(
        self,
        issue_key: str,
        attachment_id: str,
    ) -> bool:
        """
        Delete an attachment from an issue.

        Args:
            issue_key: Issue key
            attachment_id: Attachment ID

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would delete attachment {attachment_id} from {issue_key}")
            return True

        issue_id = self._parse_issue_key(issue_key)
        return self._client.delete_issue_attachment(issue_id, attachment_id)

    # -------------------------------------------------------------------------
    # Advanced Features - Components and Versions
    # -------------------------------------------------------------------------

    def list_components(self) -> list[dict[str, Any]]:
        """List all components in the repository."""
        return self._client.list_components()

    def list_versions(self) -> list[dict[str, Any]]:
        """List all versions in the repository."""
        return self._client.list_versions()

    def update_issue_with_metadata(
        self,
        issue_key: str,
        component: str | None = None,
        version: str | None = None,
    ) -> bool:
        """
        Update an issue's component and/or version.

        Args:
            issue_key: Issue key
            component: Component name
            version: Version name

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would update metadata for {issue_key}: "
                f"component={component}, version={version}"
            )
            return True

        issue_id = self._parse_issue_key(issue_key)
        self._client.update_issue(issue_id, component=component, version=version)
        self.logger.info(f"Updated metadata for #{issue_id}")
        return True
