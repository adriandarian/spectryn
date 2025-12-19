"""
GitHub Adapter - Implements IssueTrackerPort for GitHub Issues.

This is the main entry point for GitHub Issues integration.
Maps the generic IssueTrackerPort interface to GitHub's issue model.

Key mappings:
- Epic -> Milestone (with optional "epic" label for filtering)
- Story -> Issue (with "story" label)
- Subtask -> Issue (linked via task list in parent body)
- Status -> Issue state (open/closed) + labels for workflow states
"""

import contextlib
import logging
import re
from typing import Any

from spectra.core.ports.issue_tracker import (
    IssueData,
    IssueLink,
    IssueTrackerError,
    IssueTrackerPort,
    LinkType,
    TransitionError,
)

from .client import GitHubApiClient


# Default labels for issue types
DEFAULT_EPIC_LABEL = "epic"
DEFAULT_STORY_LABEL = "story"
DEFAULT_SUBTASK_LABEL = "subtask"

# Default labels for workflow states
DEFAULT_STATUS_LABELS = {
    "open": "status:open",
    "in progress": "status:in-progress",
    "done": "status:done",
    "closed": "status:done",
}


class GitHubAdapter(IssueTrackerPort):
    """
    GitHub implementation of the IssueTrackerPort.

    Translates between domain entities and GitHub's issue/milestone model.

    GitHub doesn't have native subtasks, so we use one of two approaches:
    1. Task lists in the parent issue body (default)
    2. Separate issues linked via labels (when subtasks_as_issues=True)

    Workflow status is tracked via labels since GitHub only has open/closed.
    """

    def __init__(
        self,
        token: str,
        owner: str,
        repo: str,
        dry_run: bool = True,
        base_url: str = "https://api.github.com",
        epic_label: str = DEFAULT_EPIC_LABEL,
        story_label: str = DEFAULT_STORY_LABEL,
        subtask_label: str = DEFAULT_SUBTASK_LABEL,
        status_labels: dict[str, str] | None = None,
        subtasks_as_issues: bool = False,
    ):
        """
        Initialize the GitHub adapter.

        Args:
            token: GitHub Personal Access Token
            owner: Repository owner (user or organization)
            repo: Repository name
            dry_run: If True, don't make changes
            base_url: GitHub API base URL (for GitHub Enterprise)
            epic_label: Label used to identify epics
            story_label: Label used to identify stories
            subtask_label: Label used to identify subtasks
            status_labels: Mapping of status names to label names
            subtasks_as_issues: If True, create subtasks as separate issues
        """
        self._dry_run = dry_run
        self.owner = owner
        self.repo = repo
        self.logger = logging.getLogger("GitHubAdapter")

        # Labels configuration
        self.epic_label = epic_label
        self.story_label = story_label
        self.subtask_label = subtask_label
        self.status_labels = status_labels or DEFAULT_STATUS_LABELS
        self.subtasks_as_issues = subtasks_as_issues

        # API client
        self._client = GitHubApiClient(
            token=token,
            owner=owner,
            repo=repo,
            base_url=base_url,
            dry_run=dry_run,
        )

        # Cache for issue -> milestone mappings
        self._milestone_cache: dict[int, dict] = {}

        # Ensure required labels exist
        self._ensure_labels_exist()

    def _ensure_labels_exist(self) -> None:
        """Ensure required labels exist in the repository."""
        if self._dry_run:
            return

        try:
            existing_labels = {label["name"].lower(): label for label in self._client.list_labels()}

            required_labels = [
                (self.epic_label, "6f42c1", "Epic issue"),
                (self.story_label, "0e8a16", "User story"),
                (self.subtask_label, "fbca04", "Subtask"),
            ]

            # Add status labels
            status_colors = {
                "status:open": "c5def5",
                "status:in-progress": "0052cc",
                "status:done": "0e8a16",
            }

            for status_label in self.status_labels.values():
                color = status_colors.get(status_label, "ededed")
                required_labels.append((status_label, color, f"Status: {status_label}"))

            for label_name, color, description in required_labels:
                if label_name.lower() not in existing_labels:
                    self.logger.info(f"Creating label: {label_name}")
                    self._client.create_label(label_name, color, description)

        except IssueTrackerError as e:
            self.logger.warning(f"Could not ensure labels exist: {e}")

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Properties
    # -------------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "GitHub"

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

        GitHub uses issue numbers, but we support formats like:
        - "123" (issue number)
        - "owner/repo#123" (full reference)
        - "#123" (with hash prefix)
        """
        issue_number = self._parse_issue_key(issue_key)
        data = self._client.get_issue(issue_number)
        return self._parse_issue(data)

    def get_epic_children(self, epic_key: str) -> list[IssueData]:
        """
        Fetch all children of an epic.

        GitHub epics can be:
        1. A milestone - returns all issues in that milestone
        2. An issue with epic label - returns issues referencing it
        """
        # Try parsing as milestone number first
        try:
            milestone_number = int(epic_key)
            issues = self._client.list_issues(milestone=str(milestone_number))
            return [
                self._parse_issue(issue)
                for issue in issues
                if not self._has_label(issue, self.epic_label)
            ]
        except ValueError:
            pass

        # Parse as issue reference
        issue_number = self._parse_issue_key(epic_key)

        # Search for issues mentioning this epic
        issues = self._client.search_issues(
            f"is:issue mentions:#{issue_number} label:{self.story_label}"
        )

        return [self._parse_issue(issue) for issue in issues]

    def get_issue_comments(self, issue_key: str) -> list[dict]:
        issue_number = self._parse_issue_key(issue_key)
        return self._client.get_issue_comments(issue_number)

    def get_issue_status(self, issue_key: str) -> str:
        """
        Get the current status of an issue.

        Returns the status label if present, otherwise returns
        'open' or 'closed' based on issue state.
        """
        issue_number = self._parse_issue_key(issue_key)
        data = self._client.get_issue(issue_number)

        # Check for status labels
        labels = [label["name"] for label in data.get("labels", [])]
        for status_name, label_name in self.status_labels.items():
            if label_name in labels:
                return status_name

        # Fall back to issue state
        return data.get("state", "open")

    def search_issues(self, query: str, max_results: int = 50) -> list[IssueData]:
        """
        Search for issues using GitHub search syntax.

        Examples:
        - "is:open label:bug"
        - "milestone:v1.0"
        - "assignee:username"
        """
        issues = self._client.search_issues(query, per_page=max_results)
        return [self._parse_issue(issue) for issue in issues]

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Write Operations
    # -------------------------------------------------------------------------

    def update_issue_description(self, issue_key: str, description: Any) -> bool:
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would update description for {issue_key}")
            return True

        issue_number = self._parse_issue_key(issue_key)

        # GitHub uses Markdown natively
        body = description if isinstance(description, str) else str(description)

        self._client.update_issue(issue_number, body=body)
        self.logger.info(f"Updated description for #{issue_number}")
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

        If subtasks_as_issues is True, creates a new issue with subtask label
        and links it to the parent. Otherwise, adds a task list item to the
        parent issue body.
        """
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would create subtask '{summary[:50]}...' under {parent_key}"
            )
            return None

        parent_number = self._parse_issue_key(parent_key)
        body = description if isinstance(description, str) else str(description)

        if self.subtasks_as_issues:
            # Create as separate issue
            labels = [self.subtask_label]

            # Add story points as label if provided
            if story_points:
                labels.append(f"points:{story_points}")

            # Link to parent in body
            full_body = f"Parent: #{parent_number}\n\n{body}"

            result = self._client.create_issue(
                title=summary[:255],
                body=full_body,
                labels=labels,
                assignees=[assignee] if assignee else None,
            )

            new_number = result.get("number")
            if new_number:
                self.logger.info(f"Created subtask #{new_number} under #{parent_number}")
                return f"#{new_number}"
            return None
        # Add to parent's task list
        self._add_task_to_parent(parent_number, summary, body)
        self.logger.info(f"Added task '{summary[:50]}...' to #{parent_number}")
        return None  # No separate key for inline tasks

    def _add_task_to_parent(
        self,
        parent_number: int,
        summary: str,
        description: str,
    ) -> None:
        """Add a task list item to the parent issue body."""
        parent = self._client.get_issue(parent_number)
        current_body = parent.get("body", "") or ""

        # Build task item (GitHub task list syntax)
        task_item = f"- [ ] **{summary}**"
        if description.strip():
            # Add description as indented text
            desc_lines = description.strip().split("\n")
            task_item += "\n" + "\n".join(f"  {line}" for line in desc_lines)

        # Find or create tasks section
        tasks_header = "\n\n## Tasks\n"
        if "## Tasks" in current_body:
            # Append to existing section
            new_body = current_body + f"\n{task_item}"
        else:
            # Create new section
            new_body = current_body + tasks_header + task_item

        self._client.update_issue(parent_number, body=new_body)

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

        issue_number = self._parse_issue_key(issue_key)

        updates: dict[str, Any] = {}

        if description is not None:
            updates["body"] = description if isinstance(description, str) else str(description)

        if assignee is not None:
            updates["assignees"] = [assignee]

        if story_points is not None:
            # Update points label
            issue = self._client.get_issue(issue_number)
            labels = [
                label["name"]
                for label in issue.get("labels", [])
                if not label["name"].startswith("points:")
            ]
            labels.append(f"points:{story_points}")
            updates["labels"] = labels

        if updates:
            self._client.update_issue(issue_number, **updates)
            self.logger.info(f"Updated subtask #{issue_number}")

        return True

    def add_comment(self, issue_key: str, body: Any) -> bool:
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would add comment to {issue_key}")
            return True

        issue_number = self._parse_issue_key(issue_key)
        comment_body = body if isinstance(body, str) else str(body)

        self._client.add_issue_comment(issue_number, comment_body)
        self.logger.info(f"Added comment to #{issue_number}")
        return True

    def transition_issue(self, issue_key: str, target_status: str) -> bool:
        """
        Transition an issue to a new status.

        GitHub only has open/closed states, so we use labels for
        intermediate workflow states.
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would transition {issue_key} to {target_status}")
            return True

        issue_number = self._parse_issue_key(issue_key)
        target_lower = target_status.lower()

        # Get current issue data
        issue = self._client.get_issue(issue_number)
        current_labels = [label["name"] for label in issue.get("labels", [])]

        # Remove existing status labels
        new_labels = [label for label in current_labels if label not in self.status_labels.values()]

        # Add new status label
        target_label = self.status_labels.get(target_lower)
        if target_label:
            new_labels.append(target_label)

        # Determine if issue should be closed
        should_close = "done" in target_lower or "closed" in target_lower
        current_state = issue.get("state", "open")
        new_state = "closed" if should_close else "open"

        try:
            updates: dict[str, Any] = {"labels": new_labels}
            if current_state != new_state:
                updates["state"] = new_state

            self._client.update_issue(issue_number, **updates)
            self.logger.info(f"Transitioned #{issue_number} to {target_status}")
            return True

        except IssueTrackerError as e:
            raise TransitionError(
                f"Failed to transition #{issue_number} to {target_status}: {e}",
                issue_key=issue_key,
                cause=e,
            )

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Utility
    # -------------------------------------------------------------------------

    def get_available_transitions(self, issue_key: str) -> list[dict]:
        """
        Get available transitions for an issue.

        For GitHub, transitions are simply the configured status labels.
        """
        return [
            {"id": status, "name": status, "label": label}
            for status, label in self.status_labels.items()
        ]

    def format_description(self, markdown: str) -> Any:
        """
        Convert markdown to GitHub-compatible format.

        GitHub uses Markdown natively, so we just return the input.
        Minor adjustments may be made for GitHub-Flavored Markdown.
        """
        return markdown

    # -------------------------------------------------------------------------
    # Private Methods
    # -------------------------------------------------------------------------

    def _parse_issue_key(self, key: str) -> int:
        """
        Parse an issue key into an issue number.

        Supports formats:
        - "123"
        - "#123"
        - "owner/repo#123"
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
        """Parse GitHub API response into IssueData."""
        labels = [label["name"] for label in data.get("labels", [])]

        # Determine issue type from labels
        if self.epic_label in labels:
            issue_type = "Epic"
        elif self.subtask_label in labels:
            issue_type = "Sub-task"
        elif self.story_label in labels:
            issue_type = "Story"
        else:
            issue_type = "Issue"

        # Determine status from labels and state
        status = data.get("state", "open")
        for status_name, label_name in self.status_labels.items():
            if label_name in labels:
                status = status_name
                break

        # Extract story points from labels
        story_points = None
        for label in labels:
            if label.startswith("points:"):
                with contextlib.suppress(ValueError, IndexError):
                    story_points = float(label.split(":")[1])

        # Get assignee
        assignee = None
        if data.get("assignee"):
            assignee = data["assignee"].get("login")

        # Parse subtasks from task lists in body
        subtasks = self._parse_task_list(data.get("body", "") or "")

        return IssueData(
            key=f"#{data['number']}",
            summary=data.get("title", ""),
            description=data.get("body"),
            status=status,
            issue_type=issue_type,
            assignee=assignee,
            story_points=story_points,
            subtasks=subtasks,
            comments=[],  # Comments loaded separately
        )

    def _parse_task_list(self, body: str) -> list[IssueData]:
        """
        Parse GitHub task list items from issue body.

        Format: - [ ] Task name or - [x] Completed task
        """
        subtasks = []

        # Match task list items
        task_pattern = r"^- \[([ x])\] (.+?)(?:\n(?:  .+\n)*)?$"
        for match in re.finditer(task_pattern, body, re.MULTILINE):
            completed = match.group(1) == "x"
            summary = match.group(2).strip()

            # Remove markdown bold markers
            summary = summary.replace("**", "")

            subtasks.append(
                IssueData(
                    key=f"task:{hash(summary) % 10000}",  # Synthetic key
                    summary=summary,
                    status="done" if completed else "open",
                    issue_type="Sub-task",
                )
            )

        return subtasks

    def _has_label(self, issue: dict, label_name: str) -> bool:
        """Check if an issue has a specific label."""
        labels = [label["name"].lower() for label in issue.get("labels", [])]
        return label_name.lower() in labels

    # -------------------------------------------------------------------------
    # Extended Methods (GitHub-specific)
    # -------------------------------------------------------------------------

    def create_epic(
        self,
        title: str,
        description: str,
        use_milestone: bool = True,
    ) -> str:
        """
        Create an epic.

        By default creates a milestone. If use_milestone is False,
        creates an issue with the epic label.
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would create epic '{title}'")
            return "milestone:0"

        if use_milestone:
            result = self._client.create_milestone(title, description)
            number = result.get("number", 0)
            self.logger.info(f"Created milestone {number}: {title}")
            return f"milestone:{number}"
        result = self._client.create_issue(
            title=title,
            body=description,
            labels=[self.epic_label],
        )
        number = result.get("number", 0)
        self.logger.info(f"Created epic issue #{number}: {title}")
        return f"#{number}"

    def create_story(
        self,
        title: str,
        description: str,
        epic_key: str | None = None,
        story_points: int | None = None,
        assignee: str | None = None,
    ) -> str:
        """Create a story issue."""
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would create story '{title}'")
            return "#0"

        labels = [self.story_label]
        if story_points:
            labels.append(f"points:{story_points}")

        milestone = None
        if epic_key:
            # Try parsing as milestone number
            try:
                if epic_key.startswith("milestone:"):
                    milestone = int(epic_key.split(":")[1])
                else:
                    milestone = int(epic_key)
            except ValueError:
                # Not a milestone, add reference in body
                description = f"Epic: {epic_key}\n\n{description}"

        result = self._client.create_issue(
            title=title,
            body=description,
            labels=labels,
            milestone=milestone,
            assignees=[assignee] if assignee else None,
        )

        number = result.get("number", 0)
        self.logger.info(f"Created story #{number}: {title}")
        return f"#{number}"

    def link_issue_to_milestone(
        self,
        issue_key: str,
        milestone_number: int,
    ) -> bool:
        """Link an issue to a milestone (epic)."""
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would link {issue_key} to milestone {milestone_number}")
            return True

        issue_number = self._parse_issue_key(issue_key)
        self._client.update_issue(issue_number, milestone=milestone_number)
        self.logger.info(f"Linked #{issue_number} to milestone {milestone_number}")
        return True

    # -------------------------------------------------------------------------
    # Link Operations (Cross-Issue Linking)
    # -------------------------------------------------------------------------

    def get_issue_links(self, issue_key: str) -> list[IssueLink]:
        """
        Get all links for an issue.

        GitHub doesn't have native issue links, so we parse the issue body
        for link references and check for cross-references in the timeline.

        Supported body formats:
        - **Blocks:** #123, #456
        - **Blocked by:** #789
        - **Related to:** owner/repo#123

        Args:
            issue_key: Issue to get links for

        Returns:
            List of IssueLinks
        """
        issue_number = self._parse_issue_key(issue_key)

        try:
            data = self._client.get_issue(issue_number)
        except IssueTrackerError as e:
            self.logger.error(f"Failed to get issue {issue_key}: {e}")
            return []

        links: list[IssueLink] = []
        body = data.get("body", "") or ""

        # Parse structured link references from body
        links.extend(self._parse_body_links(body, issue_key))

        return links

    def _parse_body_links(self, body: str, source_key: str) -> list[IssueLink]:
        """
        Parse issue links from the issue body.

        Supports formats:
        - **Blocks:** #123, #456
        - **Blocked by:** #789
        - **Related to:** #123
        - **Depends on:** owner/repo#123
        - **Duplicates:** #123
        """
        links: list[IssueLink] = []

        # Pattern definitions: (regex_pattern, link_type)
        link_patterns = [
            (r"\*\*Blocks[:\s]*\*\*\s*((?:#\d+(?:\s*,\s*)?)+)", LinkType.BLOCKS),
            (r"\*\*Blocked by[:\s]*\*\*\s*((?:#\d+(?:\s*,\s*)?)+)", LinkType.IS_BLOCKED_BY),
            (r"\*\*Related to[:\s]*\*\*\s*((?:#\d+(?:\s*,\s*)?)+)", LinkType.RELATES_TO),
            (r"\*\*Relates to[:\s]*\*\*\s*((?:#\d+(?:\s*,\s*)?)+)", LinkType.RELATES_TO),
            (r"\*\*Depends on[:\s]*\*\*\s*((?:#\d+(?:\s*,\s*)?)+)", LinkType.DEPENDS_ON),
            (r"\*\*Duplicates[:\s]*\*\*\s*((?:#\d+(?:\s*,\s*)?)+)", LinkType.DUPLICATES),
            (
                r"\*\*Is duplicated by[:\s]*\*\*\s*((?:#\d+(?:\s*,\s*)?)+)",
                LinkType.IS_DUPLICATED_BY,
            ),
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

        # Also check for cross-repo links (owner/repo#123)
        cross_repo_patterns = [
            (r"\*\*Blocks[:\s]*\*\*\s*((?:[\w-]+/[\w-]+#\d+(?:\s*,\s*)?)+)", LinkType.BLOCKS),
            (
                r"\*\*Related to[:\s]*\*\*\s*((?:[\w-]+/[\w-]+#\d+(?:\s*,\s*)?)+)",
                LinkType.RELATES_TO,
            ),
        ]

        for pattern, link_type in cross_repo_patterns:
            match = re.search(pattern, body, re.IGNORECASE)
            if match:
                refs_str = match.group(1)
                for ref in re.findall(r"([\w-]+/[\w-]+#\d+)", refs_str):
                    links.append(
                        IssueLink(
                            link_type=link_type,
                            target_key=ref,
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

        GitHub doesn't have native issue linking, so we add a formatted
        reference to the source issue's body.

        Args:
            source_key: Source issue key (e.g., "#123")
            target_key: Target issue key (e.g., "#456" or "owner/repo#789")
            link_type: Type of link to create

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would create link: {source_key} {link_type.value} {target_key}"
            )
            return True

        source_number = self._parse_issue_key(source_key)

        try:
            # Get current issue body
            issue = self._client.get_issue(source_number)
            current_body = issue.get("body", "") or ""

            # Add link to body
            new_body = self._add_link_to_body(current_body, target_key, link_type)

            if new_body != current_body:
                self._client.update_issue(source_number, body=new_body)
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
        """
        Add a link reference to the issue body.

        Creates or updates a Links section with formatted references.
        """
        # Normalize target key
        if not target_key.startswith("#") and "/" not in target_key:
            target_key = f"#{target_key}"

        # Map link types to section headers
        link_headers = {
            LinkType.BLOCKS: "Blocks",
            LinkType.IS_BLOCKED_BY: "Blocked by",
            LinkType.RELATES_TO: "Related to",
            LinkType.DUPLICATES: "Duplicates",
            LinkType.IS_DUPLICATED_BY: "Is duplicated by",
            LinkType.DEPENDS_ON: "Depends on",
            LinkType.IS_DEPENDENCY_OF: "Is dependency of",
            LinkType.CLONES: "Clones",
            LinkType.IS_CLONED_BY: "Is cloned by",
        }

        header = link_headers.get(link_type, "Related to")
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

        # Add new links section if not exists
        links_section = f"\n\n**{header}:** {target_key}"

        # Try to add before any existing sections like "## Tasks"
        if "## Tasks" in body:
            return body.replace("## Tasks", f"{links_section}\n\n## Tasks")
        if "## Links" in body:
            # Add after existing Links header
            return re.sub(r"(## Links\n)", rf"\1{links_section[2:]}\n", body)

        # Append to end
        return body.rstrip() + links_section

    def delete_link(
        self,
        source_key: str,
        target_key: str,
        link_type: LinkType | None = None,
    ) -> bool:
        """
        Delete a link between issues.

        Removes the reference from the source issue's body.

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

        source_number = self._parse_issue_key(source_key)

        try:
            issue = self._client.get_issue(source_number)
            current_body = issue.get("body", "") or ""

            # Remove link from body
            new_body = self._remove_link_from_body(current_body, target_key, link_type)

            if new_body != current_body:
                self._client.update_issue(source_number, body=new_body)
                self.logger.info(f"Deleted link: {source_key} -> {target_key}")

            return True
        except IssueTrackerError as e:
            self.logger.error(f"Failed to delete link: {e}")
            return False

    def _remove_link_from_body(
        self,
        body: str,
        target_key: str,
        link_type: LinkType | None = None,
    ) -> str:
        """Remove a link reference from the issue body."""
        # Normalize target key for matching
        target_patterns = [
            re.escape(target_key),
            re.escape(target_key.lstrip("#")),
            rf"#{re.escape(target_key.lstrip('#'))}",
        ]

        if link_type:
            # Remove from specific link type section
            headers = {
                LinkType.BLOCKS: "Blocks",
                LinkType.IS_BLOCKED_BY: "Blocked by",
                LinkType.RELATES_TO: "Related to",
                LinkType.DUPLICATES: "Duplicates",
                LinkType.DEPENDS_ON: "Depends on",
            }
            header = headers.get(link_type, "Related to")
            pattern = rf"(\*\*{header}[:\s]*\*\*\s*)(.+?)(\n|$)"

            def remove_target(match: re.Match) -> str:
                prefix = match.group(1)
                refs = match.group(2)
                suffix = match.group(3)

                for tp in target_patterns:
                    refs = re.sub(rf",?\s*{tp}", "", refs)
                    refs = re.sub(rf"{tp}\s*,?\s*", "", refs)

                refs = refs.strip().strip(",").strip()

                if not refs:
                    return ""  # Remove entire line if no refs left
                return f"{prefix}{refs}{suffix}"

            return re.sub(pattern, remove_target, body, flags=re.IGNORECASE)

        # Remove from any link type
        for tp in target_patterns:
            # Remove from comma-separated lists
            body = re.sub(rf",\s*{tp}", "", body)
            body = re.sub(rf"{tp}\s*,\s*", "", body)
            # Remove standalone
            body = re.sub(rf"\*\*\w+[:\s]*\*\*\s*{tp}\s*\n?", "", body)

        return body

    def get_link_types(self) -> list[dict[str, Any]]:
        """
        Get available link types.

        GitHub doesn't have native link types, so we return the standard
        link types supported by our body-parsing approach.
        """
        return [
            {"name": "Blocks", "inward": "is blocked by", "outward": "blocks"},
            {"name": "Relates", "inward": "relates to", "outward": "relates to"},
            {"name": "Duplicates", "inward": "is duplicated by", "outward": "duplicates"},
            {"name": "Depends", "inward": "is dependency of", "outward": "depends on"},
            {"name": "Clones", "inward": "is cloned by", "outward": "clones"},
        ]

    def sync_links(
        self,
        issue_key: str,
        desired_links: list[tuple[str, str]],
        delete_removed: bool = False,
    ) -> dict[str, int]:
        """
        Sync links for an issue to match desired state.

        Args:
            issue_key: Issue to sync links for
            desired_links: List of (link_type, target_key) tuples
            delete_removed: If True, delete links not in desired list

        Returns:
            Dict with counts: {created, deleted, unchanged, failed}
        """
        result = {"created": 0, "deleted": 0, "unchanged": 0, "failed": 0}

        # Get existing links
        existing = self.get_issue_links(issue_key)
        existing_set = {(link.link_type.value, link.target_key) for link in existing}
        desired_set = set(desired_links)

        # Create missing links
        to_create = desired_set - existing_set
        for link_type_str, target_key in to_create:
            link_type = LinkType.from_string(link_type_str)
            if self.create_link(issue_key, target_key, link_type):
                result["created"] += 1
            else:
                result["failed"] += 1

        # Delete removed links (if enabled)
        if delete_removed:
            to_delete = existing_set - desired_set
            for link_type_str, target_key in to_delete:
                link_type = LinkType.from_string(link_type_str)
                if self.delete_link(issue_key, target_key, link_type):
                    result["deleted"] += 1
                else:
                    result["failed"] += 1

        # Count unchanged
        result["unchanged"] = len(existing_set & desired_set)

        return result
