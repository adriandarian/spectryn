"""
GitLab Adapter - Implements IssueTrackerPort for GitLab Issues.

This is the main entry point for GitLab Issues integration.
Maps the generic IssueTrackerPort interface to GitLab's issue model.

Key mappings:
- Epic -> Milestone (default) or Epic issue type (Premium/Ultimate)
- Story -> Issue (with "story" label)
- Subtask -> Issue (linked via task list in parent body or separate issue)
- Status -> Issue state (opened/closed) + labels for workflow states
- Story Points -> Issue weight field
"""

import logging
import re
from typing import Any

from spectryn.core.ports.issue_tracker import (
    IssueData,
    IssueTrackerError,
    IssueTrackerPort,
    TransitionError,
)

from .client import GitLabApiClient


# Optional SDK client support
try:
    from .sdk_client import GITLAB_SDK_AVAILABLE, GitLabSdkClient
except ImportError:
    GITLAB_SDK_AVAILABLE = False
    GitLabSdkClient = None  # type: ignore[assignment, misc]


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


class GitLabAdapter(IssueTrackerPort):
    """
    GitLab implementation of the IssueTrackerPort.

    Translates between domain entities and GitLab's issue/milestone model.

    GitLab concepts:
    - Milestone: Collection of issues (like an epic)
    - Epic: Premium/Ultimate feature for epics (alternative to milestones)
    - Issue: Work item (like a story)
    - Weight: Story points (numeric field)
    - State: opened or closed
    - Labels: For categorization and workflow states
    """

    def __init__(
        self,
        token: str,
        project_id: str,
        dry_run: bool = True,
        base_url: str = "https://gitlab.com/api/v4",
        group_id: str | None = None,
        epic_label: str = DEFAULT_EPIC_LABEL,
        story_label: str = DEFAULT_STORY_LABEL,
        subtask_label: str = DEFAULT_SUBTASK_LABEL,
        status_labels: dict[str, str] | None = None,
        use_epics: bool = False,
        use_sdk: bool = False,
    ):
        """
        Initialize the GitLab adapter.

        Args:
            token: GitLab Personal Access Token or OAuth token
            project_id: Project ID (numeric or path like 'group/project')
            dry_run: If True, don't make changes
            base_url: GitLab API base URL (for self-hosted instances)
            group_id: Optional group ID for epics (Premium/Ultimate)
            epic_label: Label used to identify epics
            story_label: Label used to identify stories
            subtask_label: Label used to identify subtasks
            status_labels: Mapping of status names to label names
            use_epics: If True, use Epic issue type instead of milestones
            use_sdk: If True, use python-gitlab SDK instead of custom client
                    (requires: pip install spectra[gitlab])
        """
        self._dry_run = dry_run
        self.project_id = project_id
        self.group_id = group_id
        self.use_epics = use_epics
        self.logger = logging.getLogger("GitLabAdapter")

        # Labels configuration
        self.epic_label = epic_label
        self.story_label = story_label
        self.subtask_label = subtask_label
        self.status_labels = status_labels or DEFAULT_STATUS_LABELS

        # API client - choose between SDK and custom client
        # Type is a union since both clients implement the same interface
        self._client: GitLabApiClient | GitLabSdkClient  # type: ignore[valid-type]
        if use_sdk:
            if not GITLAB_SDK_AVAILABLE:
                raise ImportError(
                    "python-gitlab SDK is not installed. "
                    "Install it with: pip install spectra[gitlab] or pip install python-gitlab"
                )
            if GitLabSdkClient is None:
                raise ImportError("GitLabSdkClient is not available")
            self._client = GitLabSdkClient(
                token=token,
                project_id=project_id,
                base_url=base_url,
                dry_run=dry_run,
            )
            self.logger.info("Using python-gitlab SDK client")
        else:
            self._client = GitLabApiClient(
                token=token,
                project_id=project_id,
                base_url=base_url,
                dry_run=dry_run,
            )
            self.logger.info("Using custom GitLab API client")

        # Ensure required labels exist
        self._ensure_labels_exist()

    def _ensure_labels_exist(self) -> None:
        """Ensure required labels exist in the project."""
        if self._dry_run:
            return

        try:
            existing_labels = {label["name"].lower(): label for label in self._client.list_labels()}

            required_labels = [
                (self.epic_label, "#6f42c1", "Epic issue"),
                (self.story_label, "#0e8a16", "User story"),
                (self.subtask_label, "#fbca04", "Subtask"),
            ]

            # Add status labels
            status_colors = {
                "status:open": "#c5def5",
                "status:in-progress": "#0052cc",
                "status:done": "#0e8a16",
            }

            for status_label in self.status_labels.values():
                color = status_colors.get(status_label, "#ededed")
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
        return "GitLab"

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

        GitLab uses IID (internal ID), but we support formats like:
        - "123" (IID)
        - "#123" (with hash prefix)
        - "project#123" (full reference)
        """
        issue_iid = self._parse_issue_key(issue_key)
        data = self._client.get_issue(issue_iid)
        return self._parse_issue(data)

    def get_epic_children(self, epic_key: str) -> list[IssueData]:
        """
        Fetch all children of an epic.

        GitLab epics can be:
        1. A milestone - returns all issues in that milestone
        2. An epic (Premium/Ultimate) - returns linked issues
        3. An issue with epic label - returns issues referencing it
        """
        # Try parsing as milestone ID first
        try:
            if epic_key.startswith("milestone:"):
                milestone_id = int(epic_key.split(":")[1])
            else:
                milestone_id = int(epic_key)

            issues = self._client.list_issues(milestone=str(milestone_id))
            return [
                self._parse_issue(issue)
                for issue in issues
                if not self._has_label(issue, self.epic_label)
            ]
        except ValueError:
            pass

        # Try as epic IID (Premium/Ultimate)
        if self.use_epics and self.group_id:
            try:
                epic_iid = int(epic_key.lstrip("#"))
                # Note: GitLab API doesn't directly return linked issues
                # We need to search for issues with epic reference
                # Verify epic exists first
                self._client.get_epic(epic_iid, self.group_id)
                issues = self._client.list_issues()
                return [
                    self._parse_issue(issue)
                    for issue in issues
                    if self._has_epic_reference(issue, epic_iid)
                ]
            except (ValueError, IssueTrackerError):
                pass

        # Parse as issue reference
        issue_iid = self._parse_issue_key(epic_key)
        issue = self._client.get_issue(issue_iid)

        # If it's an epic issue, find issues referencing it
        if self._has_label(issue, self.epic_label):
            issues = self._client.list_issues()
            epic_ref = f"#{issue_iid}"
            return [
                self._parse_issue(i) for i in issues if epic_ref in (i.get("description", "") or "")
            ]

        return []

    def get_issue_comments(self, issue_key: str) -> list[dict]:
        issue_iid = self._parse_issue_key(issue_key)
        return self._client.get_issue_comments(issue_iid)

    def get_issue_status(self, issue_key: str) -> str:
        """
        Get the current status of an issue.

        Returns the status label if present, otherwise returns
        'opened' or 'closed' based on issue state.
        """
        issue_iid = self._parse_issue_key(issue_key)
        data = self._client.get_issue(issue_iid)

        # Check for status labels
        labels = [label["name"] for label in data.get("labels", [])]
        for status_name, label_name in self.status_labels.items():
            if label_name in labels:
                return status_name

        # Fall back to issue state (GitLab uses "opened" not "open")
        state = data.get("state", "opened")
        return "open" if state == "opened" else "closed"

    def search_issues(self, query: str, max_results: int = 50) -> list[IssueData]:
        """
        Search for issues using GitLab search.

        GitLab doesn't have a dedicated search API like GitHub,
        so we filter issues by labels and state.
        """
        # Parse simple queries like "label:bug state:opened"
        labels = []
        state = "opened"

        if "label:" in query:
            label_match = re.search(r"label:(\w+)", query)
            if label_match:
                labels.append(label_match.group(1))

        if "state:" in query:
            state_match = re.search(r"state:(\w+)", query)
            if state_match:
                state = state_match.group(1)

        issues = self._client.list_issues(state=state, labels=labels if labels else None)
        return [self._parse_issue(issue) for issue in issues[:max_results]]

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Write Operations
    # -------------------------------------------------------------------------

    def update_issue_description(self, issue_key: str, description: Any) -> bool:
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would update description for {issue_key}")
            return True

        issue_iid = self._parse_issue_key(issue_key)

        # GitLab uses Markdown natively
        body = description if isinstance(description, str) else str(description)

        self._client.update_issue(issue_iid, description=body)
        self.logger.info(f"Updated description for #{issue_iid}")
        return True

    def update_issue_story_points(self, issue_key: str, story_points: float) -> bool:
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would update story points for {issue_key} to {story_points}"
            )
            return True

        issue_iid = self._parse_issue_key(issue_key)

        # GitLab has a weight field for story points
        self._client.update_issue(issue_iid, weight=int(story_points))
        self.logger.info(f"Updated story points for #{issue_iid} to {story_points}")
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

        Creates a new issue with subtask label and links it to the parent.
        """
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would create subtask '{summary[:50]}...' under {parent_key}"
            )
            return None

        parent_iid = self._parse_issue_key(parent_key)
        body = description if isinstance(description, str) else str(description)

        # Create as separate issue
        labels = [self.subtask_label]

        # Link to parent in body
        full_body = f"Parent: #{parent_iid}\n\n{body}"

        result = self._client.create_issue(
            title=summary[:255],
            description=full_body,
            labels=labels,
            weight=story_points,
        )

        new_iid = result.get("iid")
        if new_iid:
            self.logger.info(f"Created subtask #{new_iid} under #{parent_iid}")
            return f"#{new_iid}"
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

        issue_iid = self._parse_issue_key(issue_key)

        updates: dict[str, Any] = {}

        if description is not None:
            desc_str = description if isinstance(description, str) else str(description)
            updates["description"] = desc_str

        if story_points is not None:
            updates["weight"] = story_points

        if updates:
            self._client.update_issue(issue_iid, **updates)
            self.logger.info(f"Updated subtask #{issue_iid}")

        return True

    def add_comment(self, issue_key: str, body: Any) -> bool:
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would add comment to {issue_key}")
            return True

        issue_iid = self._parse_issue_key(issue_key)
        comment_body = body if isinstance(body, str) else str(body)

        self._client.add_issue_comment(issue_iid, comment_body)
        self.logger.info(f"Added comment to #{issue_iid}")
        return True

    def transition_issue(self, issue_key: str, target_status: str) -> bool:
        """
        Transition an issue to a new status.

        GitLab only has opened/closed states, so we use labels for
        intermediate workflow states.
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would transition {issue_key} to {target_status}")
            return True

        issue_iid = self._parse_issue_key(issue_key)
        target_lower = target_status.lower()

        # Get current issue data
        issue = self._client.get_issue(issue_iid)
        current_labels = [label["name"] for label in issue.get("labels", [])]

        # Remove existing status labels
        new_labels = [label for label in current_labels if label not in self.status_labels.values()]

        # Add new status label
        target_label = self.status_labels.get(target_lower)
        if target_label:
            new_labels.append(target_label)

        # Determine if issue should be closed
        should_close = "done" in target_lower or "closed" in target_lower
        current_state = issue.get("state", "opened")

        try:
            updates: dict[str, Any] = {"labels": new_labels}
            if current_state == "opened" and should_close:
                updates["state_event"] = "close"
            elif current_state == "closed" and not should_close:
                updates["state_event"] = "reopen"

            self._client.update_issue(issue_iid, **updates)
            self.logger.info(f"Transitioned #{issue_iid} to {target_status}")
            return True

        except IssueTrackerError as e:
            raise TransitionError(
                f"Failed to transition #{issue_iid} to {target_status}: {e}",
                issue_key=issue_key,
                cause=e,
            )

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Utility
    # -------------------------------------------------------------------------

    def get_available_transitions(self, issue_key: str) -> list[dict]:
        """
        Get available transitions for an issue.

        For GitLab, transitions are simply the configured status labels.
        """
        return [
            {"id": status, "name": status, "label": label}
            for status, label in self.status_labels.items()
        ]

    def format_description(self, markdown: str) -> Any:
        """
        Convert markdown to GitLab-compatible format.

        GitLab uses Markdown natively, so we just return the input.
        """
        return markdown

    # -------------------------------------------------------------------------
    # Private Methods
    # -------------------------------------------------------------------------

    def _parse_issue_key(self, key: str) -> int:
        """
        Parse an issue key into an IID (internal ID).

        Supports formats:
        - "123" (IID)
        - "#123" (with hash prefix)
        - "project#123" (full reference)
        """
        # Remove hash prefix
        key = key.lstrip("#")

        # Handle full reference format
        if ("/" in key and "#" in key) or "#" in key:
            key = key.split("#")[-1]

        try:
            return int(key)
        except ValueError:
            raise IssueTrackerError(f"Invalid issue key: {key}")

    def _parse_issue(self, data: dict) -> IssueData:
        """Parse GitLab API response into IssueData."""
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
        state = data.get("state", "opened")
        status = "open" if state == "opened" else "closed"
        for status_name, label_name in self.status_labels.items():
            if label_name in labels:
                status = status_name
                break

        # Extract story points from weight field
        story_points = data.get("weight")

        # Get assignee
        assignee = None
        if data.get("assignees"):
            assignee = data["assignees"][0].get("username")

        # Parse subtasks from task lists in body
        subtasks = self._parse_task_list(data.get("description", "") or "")

        return IssueData(
            key=f"#{data['iid']}",
            summary=data.get("title", ""),
            description=data.get("description"),
            status=status,
            issue_type=issue_type,
            assignee=assignee,
            story_points=float(story_points) if story_points else None,
            subtasks=subtasks,
            comments=[],  # Comments loaded separately
        )

    def _parse_task_list(self, body: str) -> list[IssueData]:
        """
        Parse GitLab task list items from issue description.

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

    def _has_epic_reference(self, issue: dict, epic_iid: int) -> bool:
        """Check if an issue references an epic."""
        description = issue.get("description", "") or ""
        return f"#{epic_iid}" in description or f"epic:{epic_iid}" in description.lower()

    # -------------------------------------------------------------------------
    # Advanced Features - Merge Request Linking
    # -------------------------------------------------------------------------

    def get_merge_requests_for_issue(self, issue_key: str) -> list[dict[str, Any]]:
        """
        Get all merge requests linked to an issue.

        Args:
            issue_key: Issue key (e.g., "#123")

        Returns:
            List of merge request dictionaries
        """
        issue_iid = self._parse_issue_key(issue_key)
        return self._client.get_merge_requests_for_issue(issue_iid)

    def link_merge_request(
        self,
        merge_request_iid: int,
        issue_key: str,
        action: str = "closes",
    ) -> bool:
        """
        Link a merge request to an issue.

        GitLab automatically links MRs that reference issues using keywords:
        - "closes #123", "fixes #123", "resolves #123" - closes the issue
        - "relates to #123" - links without closing

        Args:
            merge_request_iid: Merge request IID
            issue_key: Issue key (e.g., "#123")
            action: Action keyword ("closes", "fixes", "resolves", "relates to")

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would link MR !{merge_request_iid} to {issue_key} with action '{action}'"
            )
            return True

        issue_iid = self._parse_issue_key(issue_key)
        return self._client.link_merge_request_to_issue(merge_request_iid, issue_iid, action)

    # -------------------------------------------------------------------------
    # Advanced Features - Issue Boards
    # -------------------------------------------------------------------------

    def list_boards(self) -> list[dict[str, Any]]:
        """
        List all issue boards in the project.

        Returns:
            List of board dictionaries
        """
        return self._client.list_boards()

    def get_board(self, board_id: int) -> dict[str, Any]:
        """
        Get a single board.

        Args:
            board_id: Board ID

        Returns:
            Board dictionary
        """
        return self._client.get_board(board_id)

    def get_board_lists(self, board_id: int) -> list[dict[str, Any]]:
        """
        Get all lists (columns) for a board.

        Args:
            board_id: Board ID

        Returns:
            List of board list dictionaries
        """
        return self._client.get_board_lists(board_id)

    def move_issue_to_board_list(
        self,
        issue_key: str,
        board_id: int,
        list_id: int,
    ) -> bool:
        """
        Move an issue to a specific board list.

        Args:
            issue_key: Issue key (e.g., "#123")
            board_id: Board ID
            list_id: List (column) ID

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(
                f"[DRY-RUN] Would move {issue_key} to board {board_id}, list {list_id}"
            )
            return True

        issue_iid = self._parse_issue_key(issue_key)
        return self._client.move_issue_to_board_list(issue_iid, board_id, list_id)

    def get_issue_board_position(self, issue_key: str) -> dict[str, Any] | None:
        """
        Get the board position for an issue.

        Args:
            issue_key: Issue key (e.g., "#123")

        Returns:
            Board position dictionary or None
        """
        issue_iid = self._parse_issue_key(issue_key)
        return self._client.get_issue_board_position(issue_iid)

    # -------------------------------------------------------------------------
    # Advanced Features - Time Tracking
    # -------------------------------------------------------------------------

    def get_issue_time_stats(self, issue_key: str) -> dict[str, Any]:
        """
        Get time tracking statistics for an issue.

        Returns time estimate and spent time.

        Args:
            issue_key: Issue key (e.g., "#123")

        Returns:
            Dictionary with time_stats (estimate, spent_time, human_estimate, human_total_spent_time)
        """
        issue_iid = self._parse_issue_key(issue_key)
        return self._client.get_issue_time_stats(issue_iid)

    def add_spent_time(
        self,
        issue_key: str,
        duration: str,
        summary: str | None = None,
    ) -> bool:
        """
        Add spent time to an issue.

        Args:
            issue_key: Issue key (e.g., "#123")
            duration: Time duration (e.g., "1h 30m", "2h", "45m")
            summary: Optional summary/note for the time entry

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would add {duration} spent time to {issue_key}")
            return True

        issue_iid = self._parse_issue_key(issue_key)
        result = self._client.add_spent_time(issue_iid, duration, summary)
        return isinstance(result, dict)

    def reset_spent_time(self, issue_key: str) -> bool:
        """
        Reset spent time for an issue.

        Args:
            issue_key: Issue key (e.g., "#123")

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would reset spent time for {issue_key}")
            return True

        issue_iid = self._parse_issue_key(issue_key)
        result = self._client.reset_spent_time(issue_iid)
        return isinstance(result, dict)

    def estimate_time(self, issue_key: str, duration: str) -> bool:
        """
        Set time estimate for an issue.

        Args:
            issue_key: Issue key (e.g., "#123")
            duration: Time estimate (e.g., "3h 30m", "1d", "2w")

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would set time estimate {duration} for {issue_key}")
            return True

        issue_iid = self._parse_issue_key(issue_key)
        result = self._client.estimate_time(issue_iid, duration)
        return isinstance(result, dict)

    def reset_time_estimate(self, issue_key: str) -> bool:
        """
        Reset time estimate for an issue.

        Args:
            issue_key: Issue key (e.g., "#123")

        Returns:
            True if successful
        """
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would reset time estimate for {issue_key}")
            return True

        issue_iid = self._parse_issue_key(issue_key)
        result = self._client.reset_time_estimate(issue_iid)
        return isinstance(result, dict)
