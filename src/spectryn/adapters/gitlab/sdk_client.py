"""
GitLab SDK Client - Optional wrapper around python-gitlab SDK.

This provides an alternative implementation using the official python-gitlab SDK
instead of our custom HTTP client. Users can opt-in by installing:
    pip install spectra[gitlab]

The SDK client implements the same interface as GitLabApiClient, allowing
seamless switching between implementations.
"""

import logging
from typing import Any


try:
    import gitlab
    from gitlab import Gitlab

    GITLAB_SDK_AVAILABLE = True
except ImportError:
    GITLAB_SDK_AVAILABLE = False
    Gitlab = None  # type: ignore[assignment, misc]

from spectryn.core.ports.issue_tracker import (
    AuthenticationError,
    IssueTrackerError,
    NotFoundError,
    PermissionError,
)


class GitLabSdkClient:
    """
    GitLab API client using python-gitlab SDK.

    This is an alternative to GitLabApiClient that uses the official
    python-gitlab SDK. It implements the same interface for compatibility.

    To use this client, install: pip install spectra[gitlab]
    """

    def __init__(
        self,
        token: str,
        project_id: str,
        base_url: str = "https://gitlab.com/api/v4",
        dry_run: bool = True,
    ):
        """
        Initialize the GitLab SDK client.

        Args:
            token: GitLab Personal Access Token or OAuth token
            project_id: Project ID (numeric or path like 'group/project')
            base_url: GitLab API base URL (for self-hosted instances)
            dry_run: If True, don't make write operations

        Raises:
            ImportError: If python-gitlab is not installed
        """
        if not GITLAB_SDK_AVAILABLE:
            raise ImportError(
                "python-gitlab SDK is not installed. "
                "Install it with: pip install spectra[gitlab] or pip install python-gitlab"
            )

        self.token = token
        self.project_id = project_id
        self.base_url = base_url.rstrip("/")
        self.dry_run = dry_run
        self.logger = logging.getLogger("GitLabSdkClient")

        # Initialize GitLab client
        self._gl = Gitlab(self.base_url, private_token=token)
        self._gl.auth()

        # Get project object
        try:
            self._project = self._gl.projects.get(project_id)
        except Exception as e:
            raise IssueTrackerError(f"Failed to get project {project_id}: {e}") from e

        # Cache
        self._current_user: dict[str, Any] | None = None

    # -------------------------------------------------------------------------
    # Connection & Authentication
    # -------------------------------------------------------------------------

    def get_authenticated_user(self) -> dict[str, Any]:
        """Get the currently authenticated user."""
        if self._current_user is None:
            user = self._gl.user
            self._current_user = {
                "id": user.id,
                "username": user.username,
                "name": user.name,
                "email": user.email,
            }
        return self._current_user if self._current_user else {}

    def get_current_user_username(self) -> str:
        """Get the current user's username."""
        user = self.get_authenticated_user()
        return str(user.get("username", "")) if user else ""

    def test_connection(self) -> bool:
        """Test if the API connection and credentials are valid."""
        try:
            self.get_authenticated_user()
            # Verify project access
            _ = self._project.id
            return True
        except Exception:
            return False

    @property
    def is_connected(self) -> bool:
        """Check if the client has successfully connected."""
        return self._current_user is not None

    # -------------------------------------------------------------------------
    # Issues API
    # -------------------------------------------------------------------------

    def get_issue(self, issue_iid: int) -> dict[str, Any]:
        """Get a single issue by IID."""
        try:
            issue = self._project.issues.get(issue_iid)
            return self._issue_to_dict(issue)
        except Exception as e:
            # Handle gitlab SDK exceptions
            if gitlab is not None and hasattr(gitlab, "exceptions"):
                gitlab_exceptions = gitlab.exceptions
                if isinstance(e, gitlab_exceptions.GitlabGetError):
                    if hasattr(e, "response_code") and e.response_code == 404:
                        raise NotFoundError(
                            f"Issue #{issue_iid} not found", issue_key=str(issue_iid)
                        ) from e
                    raise IssueTrackerError(f"Failed to get issue #{issue_iid}: {e}") from e
                if isinstance(e, gitlab_exceptions.GitlabAuthenticationError):
                    raise AuthenticationError("GitLab authentication failed") from e
                if isinstance(e, gitlab_exceptions.GitlabHttpError):
                    if hasattr(e, "response_code") and e.response_code == 403:
                        raise PermissionError(f"Permission denied for issue #{issue_iid}") from e
                    raise IssueTrackerError(f"GitLab API error: {e}") from e
            # Fallback for other exceptions
            raise IssueTrackerError(f"Failed to get issue #{issue_iid}: {e}") from e

    def list_issues(
        self,
        state: str = "opened",
        labels: list[str] | None = None,
        milestone: str | None = None,
        per_page: int = 100,
        page: int = 1,
    ) -> list[dict[str, Any]]:
        """List issues in the project."""
        try:
            issues = self._project.issues.list(
                state=state,
                labels=labels,
                milestone=milestone,
                per_page=per_page,
                page=page,
            )
            return [self._issue_to_dict(issue) for issue in issues]
        except Exception as e:
            raise IssueTrackerError(f"Failed to list issues: {e}") from e

    def create_issue(
        self,
        title: str,
        description: str | None = None,
        labels: list[str] | None = None,
        milestone_id: int | None = None,
        assignee_ids: list[int] | None = None,
        weight: int | None = None,
    ) -> dict[str, Any]:
        """Create a new issue."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would create issue: {title}")
            return {}

        try:
            issue_data: dict[str, Any] = {"title": title}
            if description:
                issue_data["description"] = description
            if labels:
                issue_data["labels"] = ",".join(labels)
            if milestone_id:
                issue_data["milestone_id"] = milestone_id
            if assignee_ids:
                issue_data["assignee_ids"] = assignee_ids
            if weight is not None:
                issue_data["weight"] = weight

            issue = self._project.issues.create(issue_data)
            return self._issue_to_dict(issue)
        except Exception as e:
            raise IssueTrackerError(f"Failed to create issue: {e}") from e

    def update_issue(
        self,
        issue_iid: int,
        title: str | None = None,
        description: str | None = None,
        state_event: str | None = None,
        labels: list[str] | None = None,
        milestone_id: int | None = None,
        assignee_ids: list[int] | None = None,
        weight: int | None = None,
    ) -> dict[str, Any]:
        """Update an existing issue."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would update issue #{issue_iid}")
            return {}

        try:
            issue = self._project.issues.get(issue_iid)
            update_data: dict[str, Any] = {}
            if title is not None:
                update_data["title"] = title
            if description is not None:
                update_data["description"] = description
            if state_event is not None:
                update_data["state_event"] = state_event
            if labels is not None:
                update_data["labels"] = ",".join(labels)
            if milestone_id is not None:
                update_data["milestone_id"] = milestone_id
            if assignee_ids is not None:
                update_data["assignee_ids"] = assignee_ids
            if weight is not None:
                update_data["weight"] = weight

            issue.save(**update_data)
            return self._issue_to_dict(issue)
        except Exception as e:
            raise IssueTrackerError(f"Failed to update issue #{issue_iid}: {e}") from e

    def get_issue_comments(self, issue_iid: int) -> list[dict[str, Any]]:
        """Get all notes (comments) on an issue."""
        try:
            issue = self._project.issues.get(issue_iid)
            notes = issue.notes.list()
            return [
                {
                    "id": note.id,
                    "body": note.body,
                    "author": {"username": note.author.get("username", "")},
                    "created_at": note.created_at,
                }
                for note in notes
            ]
        except Exception as e:
            raise IssueTrackerError(f"Failed to get comments for issue #{issue_iid}: {e}") from e

    def add_issue_comment(
        self,
        issue_iid: int,
        body: str,
    ) -> dict[str, Any]:
        """Add a note (comment) to an issue."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would add comment to issue #{issue_iid}")
            return {}

        try:
            issue = self._project.issues.get(issue_iid)
            note = issue.notes.create({"body": body})
            return {
                "id": note.id,
                "body": note.body,
            }
        except Exception as e:
            raise IssueTrackerError(f"Failed to add comment to issue #{issue_iid}: {e}") from e

    # -------------------------------------------------------------------------
    # Labels API
    # -------------------------------------------------------------------------

    def list_labels(self) -> list[dict[str, Any]]:
        """List all labels in the project."""
        try:
            labels = self._project.labels.list()
            return [
                {
                    "name": label.name,
                    "color": label.color,
                    "description": label.description,
                }
                for label in labels
            ]
        except Exception as e:
            raise IssueTrackerError(f"Failed to list labels: {e}") from e

    def create_label(
        self,
        name: str,
        color: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Create a new label."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would create label: {name}")
            return {}

        try:
            label_data: dict[str, Any] = {"name": name, "color": color}
            if description:
                label_data["description"] = description
            label = self._project.labels.create(label_data)
            return {
                "name": label.name,
                "color": label.color,
                "description": label.description,
            }
        except Exception as e:
            raise IssueTrackerError(f"Failed to create label: {e}") from e

    # -------------------------------------------------------------------------
    # Milestones API
    # -------------------------------------------------------------------------

    def get_milestone(self, milestone_id: int) -> dict[str, Any]:
        """Get a single milestone."""
        try:
            milestone = self._project.milestones.get(milestone_id)
            return {
                "id": milestone.id,
                "iid": milestone.iid,
                "title": milestone.title,
                "description": milestone.description,
                "state": milestone.state,
            }
        except Exception as e:
            raise IssueTrackerError(f"Failed to get milestone {milestone_id}: {e}") from e

    def list_milestones(
        self,
        state: str = "active",
    ) -> list[dict[str, Any]]:
        """List all milestones."""
        try:
            milestones = self._project.milestones.list(state=state)
            return [
                {
                    "id": m.id,
                    "iid": m.iid,
                    "title": m.title,
                    "description": m.description,
                    "state": m.state,
                }
                for m in milestones
            ]
        except Exception as e:
            raise IssueTrackerError(f"Failed to list milestones: {e}") from e

    def create_milestone(
        self,
        title: str,
        description: str | None = None,
        state: str = "active",
    ) -> dict[str, Any]:
        """Create a new milestone."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would create milestone: {title}")
            return {}

        try:
            milestone_data: dict[str, Any] = {"title": title, "state": state}
            if description:
                milestone_data["description"] = description
            milestone = self._project.milestones.create(milestone_data)
            return {
                "id": milestone.id,
                "iid": milestone.iid,
                "title": milestone.title,
                "description": milestone.description,
                "state": milestone.state,
            }
        except Exception as e:
            raise IssueTrackerError(f"Failed to create milestone: {e}") from e

    def update_milestone(
        self,
        milestone_id: int,
        title: str | None = None,
        description: str | None = None,
        state_event: str | None = None,
    ) -> dict[str, Any]:
        """Update an existing milestone."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would update milestone {milestone_id}")
            return {}

        try:
            milestone = self._project.milestones.get(milestone_id)
            update_data: dict[str, Any] = {}
            if title is not None:
                update_data["title"] = title
            if description is not None:
                update_data["description"] = description
            if state_event is not None:
                update_data["state_event"] = state_event
            milestone.save(**update_data)
            return {
                "id": milestone.id,
                "iid": milestone.iid,
                "title": milestone.title,
                "description": milestone.description,
                "state": milestone.state,
            }
        except Exception as e:
            raise IssueTrackerError(f"Failed to update milestone {milestone_id}: {e}") from e

    # -------------------------------------------------------------------------
    # Epics API (Premium/Ultimate feature)
    # -------------------------------------------------------------------------

    def get_epic(self, epic_iid: int, group_id: str) -> dict[str, Any]:
        """Get a single epic (requires Premium/Ultimate)."""
        try:
            group = self._gl.groups.get(group_id)
            epic = group.epics.get(epic_iid)
            return {
                "iid": epic.iid,
                "id": epic.id,
                "title": epic.title,
                "description": epic.description,
                "state": epic.state,
            }
        except Exception as e:
            raise IssueTrackerError(f"Failed to get epic {epic_iid}: {e}") from e

    def list_epics(
        self,
        group_id: str,
        state: str = "opened",
    ) -> list[dict[str, Any]]:
        """List all epics in a group (requires Premium/Ultimate)."""
        try:
            group = self._gl.groups.get(group_id)
            epics = group.epics.list(state=state)
            return [
                {
                    "iid": epic.iid,
                    "id": epic.id,
                    "title": epic.title,
                    "description": epic.description,
                    "state": epic.state,
                }
                for epic in epics
            ]
        except Exception as e:
            raise IssueTrackerError(f"Failed to list epics: {e}") from e

    # -------------------------------------------------------------------------
    # Merge Requests API
    # -------------------------------------------------------------------------

    def get_merge_request(self, merge_request_iid: int) -> dict[str, Any]:
        """Get a single merge request by IID."""
        try:
            mr = self._project.mergerequests.get(merge_request_iid)
            return {
                "iid": mr.iid,
                "id": mr.id,
                "title": mr.title,
                "description": mr.description,
                "state": mr.state,
            }
        except Exception as e:
            raise IssueTrackerError(f"Failed to get MR !{merge_request_iid}: {e}") from e

    def list_merge_requests(
        self,
        state: str = "opened",
        per_page: int = 100,
        page: int = 1,
    ) -> list[dict[str, Any]]:
        """List merge requests in the project."""
        try:
            mrs = self._project.mergerequests.list(state=state, per_page=per_page, page=page)
            return [
                {
                    "iid": mr.iid,
                    "id": mr.id,
                    "title": mr.title,
                    "description": mr.description,
                    "state": mr.state,
                }
                for mr in mrs
            ]
        except Exception as e:
            raise IssueTrackerError(f"Failed to list merge requests: {e}") from e

    def get_merge_requests_for_issue(self, issue_iid: int) -> list[dict[str, Any]]:
        """Get all merge requests that reference an issue."""
        try:
            all_mrs = self._project.mergerequests.list(state="all", per_page=100)
            issue_ref = f"#{issue_iid}"
            linked_mrs = []
            for mr in all_mrs:
                description = mr.description or ""
                title = mr.title or ""
                if issue_ref in description or issue_ref in title:
                    linked_mrs.append(
                        {
                            "iid": mr.iid,
                            "id": mr.id,
                            "title": mr.title,
                            "description": mr.description,
                            "state": mr.state,
                        }
                    )
            return linked_mrs
        except Exception as e:
            raise IssueTrackerError(f"Failed to get MRs for issue #{issue_iid}: {e}") from e

    def link_merge_request_to_issue(
        self,
        merge_request_iid: int,
        issue_iid: int,
        action: str = "closes",
    ) -> bool:
        """Link a merge request to an issue by updating MR description."""
        if self.dry_run:
            self.logger.info(
                f"[DRY-RUN] Would link MR !{merge_request_iid} to issue #{issue_iid} with '{action}'"
            )
            return True

        try:
            mr = self._project.mergerequests.get(merge_request_iid)
            current_description = mr.description or ""
            issue_ref = f"{action} #{issue_iid}"

            if f"#{issue_iid}" in current_description:
                return True

            new_description = f"{current_description}\n\n{issue_ref}".strip()
            mr.description = new_description
            mr.save()
            return True
        except Exception as e:
            raise IssueTrackerError(f"Failed to link MR to issue: {e}") from e

    def update_merge_request(
        self,
        merge_request_iid: int,
        title: str | None = None,
        description: str | None = None,
        state_event: str | None = None,
    ) -> dict[str, Any]:
        """Update a merge request."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would update MR !{merge_request_iid}")
            return {}

        try:
            mr = self._project.mergerequests.get(merge_request_iid)
            update_data: dict[str, Any] = {}
            if title is not None:
                update_data["title"] = title
            if description is not None:
                update_data["description"] = description
            if state_event is not None:
                update_data["state_event"] = state_event
            mr.save(**update_data)
            return {
                "iid": mr.iid,
                "id": mr.id,
                "title": mr.title,
                "description": mr.description,
                "state": mr.state,
            }
        except Exception as e:
            raise IssueTrackerError(f"Failed to update MR: {e}") from e

    # -------------------------------------------------------------------------
    # Issue Boards API
    # -------------------------------------------------------------------------

    def list_boards(self) -> list[dict[str, Any]]:
        """List all issue boards in the project."""
        try:
            boards = self._project.boards.list()
            return [
                {
                    "id": board.id,
                    "name": board.name,
                }
                for board in boards
            ]
        except Exception as e:
            raise IssueTrackerError(f"Failed to list boards: {e}") from e

    def get_board(self, board_id: int) -> dict[str, Any]:
        """Get a single board."""
        try:
            board = self._project.boards.get(board_id)
            return {
                "id": board.id,
                "name": board.name,
            }
        except Exception as e:
            raise IssueTrackerError(f"Failed to get board {board_id}: {e}") from e

    def get_board_lists(self, board_id: int) -> list[dict[str, Any]]:
        """Get all lists (columns) for a board."""
        try:
            board = self._project.boards.get(board_id)
            lists = board.lists.list()
            return [
                {
                    "id": lst.id,
                    "label": {"name": lst.label.get("name", "")} if lst.label else {},
                    "position": lst.position,
                }
                for lst in lists
            ]
        except Exception as e:
            raise IssueTrackerError(f"Failed to get board lists: {e}") from e

    def move_issue_to_board_list(
        self,
        issue_iid: int,
        board_id: int,
        list_id: int,
    ) -> bool:
        """Move an issue to a specific board list."""
        if self.dry_run:
            self.logger.info(
                f"[DRY-RUN] Would move issue #{issue_iid} to board {board_id}, list {list_id}"
            )
            return True

        try:
            board = self._project.boards.get(board_id)
            board_list = board.lists.get(list_id)
            issue = self._project.issues.get(issue_iid)
            # Move issue to list
            board_list.move_issue(issue.id)
            return True
        except Exception as e:
            raise IssueTrackerError(f"Failed to move issue to board list: {e}") from e

    def get_issue_board_position(self, issue_iid: int) -> dict[str, Any] | None:
        """Get the board position for an issue."""
        try:
            issue = self._project.issues.get(issue_iid)
            # Note: python-gitlab SDK doesn't directly expose board_position
            # We'd need to query boards to find where the issue is
            boards = self._project.boards.list()
            for board in boards:
                lists = board.lists.list()
                for lst in lists:
                    issues_in_list = lst.issues.list()
                    if any(i.id == issue.id for i in issues_in_list):
                        return {
                            "board_id": board.id,
                            "list_id": lst.id,
                        }
            return None
        except Exception as e:
            self.logger.warning(f"Failed to get board position: {e}")
            return None

    # -------------------------------------------------------------------------
    # Time Tracking API
    # -------------------------------------------------------------------------

    def get_issue_time_stats(self, issue_iid: int) -> dict[str, Any]:
        """Get time tracking statistics for an issue."""
        try:
            issue = self._project.issues.get(issue_iid)
            # Note: python-gitlab SDK doesn't directly expose time_stats
            # We need to use the API directly or parse from issue attributes
            # For now, return empty dict - this would need API call
            return {
                "time_estimate": getattr(issue, "time_estimate", 0),
                "total_time_spent": getattr(issue, "total_time_spent", 0),
            }
        except Exception as e:
            raise IssueTrackerError(f"Failed to get time stats: {e}") from e

    def add_spent_time(
        self,
        issue_iid: int,
        duration: str,
        summary: str | None = None,
    ) -> dict[str, Any]:
        """Add spent time to an issue."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would add {duration} spent time to issue #{issue_iid}")
            return {}

        try:
            issue = self._project.issues.get(issue_iid)
            # python-gitlab SDK doesn't have direct method, use manager
            issue.manager.add_spent_time(issue.id, duration=duration, summary=summary)
            return self.get_issue_time_stats(issue_iid)
        except Exception as e:
            raise IssueTrackerError(f"Failed to add spent time: {e}") from e

    def reset_spent_time(self, issue_iid: int) -> dict[str, Any]:
        """Reset spent time for an issue."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would reset spent time for issue #{issue_iid}")
            return {}

        try:
            issue = self._project.issues.get(issue_iid)
            issue.manager.reset_spent_time(issue.id)
            return self.get_issue_time_stats(issue_iid)
        except Exception as e:
            raise IssueTrackerError(f"Failed to reset spent time: {e}") from e

    def estimate_time(self, issue_iid: int, duration: str) -> dict[str, Any]:
        """Set time estimate for an issue."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would set time estimate {duration} for issue #{issue_iid}")
            return {}

        try:
            issue = self._project.issues.get(issue_iid)
            issue.manager.set_time_estimate(issue.id, duration=duration)
            return self.get_issue_time_stats(issue_iid)
        except Exception as e:
            raise IssueTrackerError(f"Failed to set time estimate: {e}") from e

    def reset_time_estimate(self, issue_iid: int) -> dict[str, Any]:
        """Reset time estimate for an issue."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would reset time estimate for issue #{issue_iid}")
            return {}

        try:
            issue = self._project.issues.get(issue_iid)
            issue.manager.reset_time_estimate(issue.id)
            return self.get_issue_time_stats(issue_iid)
        except Exception as e:
            raise IssueTrackerError(f"Failed to reset time estimate: {e}") from e

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def _issue_to_dict(self, issue: Any) -> dict[str, Any]:
        """Convert GitLab issue object to dictionary."""
        return {
            "iid": issue.iid,
            "id": issue.id,
            "title": issue.title,
            "description": issue.description,
            "state": issue.state,
            "labels": [{"name": label} for label in (issue.labels or [])],
            "assignees": [
                {"username": assignee.get("username", ""), "id": assignee.get("id")}
                for assignee in (issue.assignees or [])
            ],
            "weight": getattr(issue, "weight", None),
            "milestone": (
                {
                    "id": issue.milestone["id"],
                    "title": issue.milestone["title"],
                }
                if issue.milestone
                else None
            ),
        }

    def project_endpoint(self, path: str = "") -> str:
        """Get the full endpoint for a project-scoped path (for compatibility)."""
        import urllib.parse

        encoded_project_id = urllib.parse.quote(self.project_id, safe="")
        base = f"projects/{encoded_project_id}"
        if path:
            return f"{base}/{path}"
        return base

    def close(self) -> None:
        """Close the client and release resources."""
        # SDK doesn't need explicit cleanup
        self.logger.debug("SDK client closed")

    def __enter__(self) -> "GitLabSdkClient":
        """Context manager entry."""
        return self

    def __exit__(
        self,
        exc_type: type | None,
        exc_val: Exception | None,
        exc_tb: Any,
    ) -> None:
        """Context manager exit."""
        self.close()
