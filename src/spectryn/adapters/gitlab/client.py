"""
GitLab API Client - Low-level HTTP client for GitLab REST API v4.

This handles the raw HTTP communication with GitLab.
The GitLabAdapter uses this to implement the IssueTrackerPort.
"""

import logging
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter

from spectryn.adapters.async_base import (
    RETRYABLE_STATUS_CODES,
    calculate_delay,
    get_retry_after,
)
from spectryn.core.ports.issue_tracker import (
    AuthenticationError,
    IssueTrackerError,
    NotFoundError,
    PermissionError,
    RateLimitError,
    TransientError,
)


class GitLabRateLimiter:
    """Simple rate limiter for GitLab API (2000 requests/hour per user)."""

    def __init__(self, requests_per_hour: float = 2000.0):
        """
        Initialize rate limiter.

        Args:
            requests_per_hour: Maximum requests per hour
        """
        self.requests_per_hour = requests_per_hour
        self.requests_per_second = requests_per_hour / 3600.0
        self.last_request_time: float = 0.0
        self.min_delay = 1.0 / self.requests_per_second if self.requests_per_second > 0 else 0.0

    def acquire(self) -> None:
        """Acquire permission to make a request."""
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < self.min_delay:
            sleep_time = self.min_delay - elapsed
            time.sleep(sleep_time)
        self.last_request_time = time.time()

    def update_from_response(self, response: requests.Response) -> None:
        """Update rate limiter state from response headers."""
        # GitLab doesn't provide rate limit headers like GitHub
        # We rely on our own rate limiting


class GitLabApiClient:
    """
    Low-level GitLab REST API v4 client.

    Handles authentication, request/response, rate limiting, and error handling.

    Features:
    - Automatic retry with exponential backoff for transient failures
    - Proactive rate limiting (2000 requests/hour)
    - Connection pooling for performance
    - Support for GitLab.com and self-hosted instances
    """

    API_VERSION = "v4"
    BASE_URL = "https://gitlab.com/api/v4"

    # Default retry configuration
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_INITIAL_DELAY = 1.0
    DEFAULT_MAX_DELAY = 60.0
    DEFAULT_BACKOFF_FACTOR = 2.0
    DEFAULT_JITTER = 0.1

    # GitLab rate limiting: 2000 requests/hour per user
    DEFAULT_REQUESTS_PER_HOUR = 2000.0

    # Connection pool settings
    DEFAULT_POOL_CONNECTIONS = 10
    DEFAULT_POOL_MAXSIZE = 10
    DEFAULT_TIMEOUT = 30.0

    def __init__(
        self,
        token: str,
        project_id: str,
        base_url: str = BASE_URL,
        dry_run: bool = True,
        max_retries: int = DEFAULT_MAX_RETRIES,
        initial_delay: float = DEFAULT_INITIAL_DELAY,
        max_delay: float = DEFAULT_MAX_DELAY,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
        jitter: float = DEFAULT_JITTER,
        requests_per_hour: float = DEFAULT_REQUESTS_PER_HOUR,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        """
        Initialize the GitLab client.

        Args:
            token: GitLab Personal Access Token or OAuth token
            project_id: Project ID (numeric or path like 'group/project')
            base_url: GitLab API base URL (for self-hosted instances)
            dry_run: If True, don't make write operations
            max_retries: Maximum retry attempts for transient failures
            initial_delay: Initial retry delay in seconds
            max_delay: Maximum retry delay in seconds
            backoff_factor: Multiplier for exponential backoff
            jitter: Random jitter factor (0.1 = 10%)
            requests_per_hour: Maximum request rate per hour
            timeout: Request timeout in seconds
        """
        self.token = token
        self.project_id = project_id
        self.base_url = base_url.rstrip("/")
        self.dry_run = dry_run
        self.timeout = timeout
        self.logger = logging.getLogger("GitLabApiClient")

        # Retry configuration
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.jitter = jitter

        # Rate limiting
        self._rate_limiter: GitLabRateLimiter | None = None
        if requests_per_hour is not None and requests_per_hour > 0:
            self._rate_limiter = GitLabRateLimiter(requests_per_hour=requests_per_hour)

        # Headers for GitLab API
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        # Configure session with connection pooling
        self._session = requests.Session()
        self._session.headers.update(self.headers)

        adapter = HTTPAdapter(
            pool_connections=self.DEFAULT_POOL_CONNECTIONS,
            pool_maxsize=self.DEFAULT_POOL_MAXSIZE,
        )
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)

        # Cache
        self._current_user: dict | None = None

    # -------------------------------------------------------------------------
    # Core Request Methods
    # -------------------------------------------------------------------------

    def request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> dict[str, Any] | list[Any]:
        """
        Make an authenticated request to GitLab API with rate limiting and retry.

        Args:
            method: HTTP method
            endpoint: API endpoint (e.g., 'projects/:id/issues')
            **kwargs: Additional arguments for requests

        Returns:
            JSON response (dict or list)

        Raises:
            IssueTrackerError: On API errors
        """
        # Support both absolute endpoints and relative endpoints
        if endpoint.startswith("http"):
            url = endpoint
        elif endpoint.startswith("/"):
            url = f"{self.base_url}{endpoint}"
        else:
            url = f"{self.base_url}/{endpoint}"

        last_exception: Exception | None = None

        for attempt in range(self.max_retries + 1):
            # Apply rate limiting
            if self._rate_limiter is not None:
                self._rate_limiter.acquire()

            try:
                if "timeout" not in kwargs:
                    kwargs["timeout"] = self.timeout

                response = self._session.request(method, url, **kwargs)

                # Update rate limiter from response headers
                if self._rate_limiter is not None:
                    self._rate_limiter.update_from_response(response)

                # Check for retryable status codes
                if response.status_code in RETRYABLE_STATUS_CODES:
                    retry_after = get_retry_after(response)
                    delay = calculate_delay(
                        attempt,
                        initial_delay=self.initial_delay,
                        max_delay=self.max_delay,
                        backoff_factor=self.backoff_factor,
                        jitter=self.jitter,
                        retry_after=retry_after,
                    )

                    if attempt < self.max_retries:
                        self.logger.warning(
                            f"Retryable error {response.status_code} on {method} {endpoint}, "
                            f"attempt {attempt + 1}/{self.max_retries + 1}, "
                            f"retrying in {delay:.2f}s"
                        )
                        time.sleep(delay)
                        continue

                    if response.status_code == 429:
                        raise RateLimitError(
                            f"GitLab rate limit exceeded for {endpoint}",
                            retry_after=retry_after,
                            issue_key=endpoint,
                        )
                    raise TransientError(
                        f"GitLab server error {response.status_code} for {endpoint}",
                        issue_key=endpoint,
                    )

                return self._handle_response(response, endpoint)

            except requests.exceptions.ConnectionError as e:
                last_exception = e
                if attempt < self.max_retries:
                    delay = calculate_delay(
                        attempt,
                        initial_delay=self.initial_delay,
                        max_delay=self.max_delay,
                        backoff_factor=self.backoff_factor,
                        jitter=self.jitter,
                    )
                    self.logger.warning(
                        f"Connection error on {method} {endpoint}, retrying in {delay:.2f}s"
                    )
                    time.sleep(delay)
                    continue
                raise IssueTrackerError(f"Connection failed: {e}", cause=e)

            except requests.exceptions.Timeout as e:
                last_exception = e
                if attempt < self.max_retries:
                    delay = calculate_delay(
                        attempt,
                        initial_delay=self.initial_delay,
                        max_delay=self.max_delay,
                        backoff_factor=self.backoff_factor,
                        jitter=self.jitter,
                    )
                    self.logger.warning(f"Timeout on {method} {endpoint}, retrying in {delay:.2f}s")
                    time.sleep(delay)
                    continue
                raise IssueTrackerError(f"Request timed out: {e}", cause=e)

        raise IssueTrackerError(
            f"Request failed after {self.max_retries + 1} attempts", cause=last_exception
        )

    def get(self, endpoint: str, **kwargs: Any) -> dict[str, Any] | list[Any]:
        """Perform a GET request."""
        return self.request("GET", endpoint, **kwargs)

    def post(
        self,
        endpoint: str,
        json: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | list[Any]:
        """Perform a POST request. Respects dry_run mode."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would POST to {endpoint}")
            return {}
        return self.request("POST", endpoint, json=json, **kwargs)

    def put(
        self,
        endpoint: str,
        json: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | list[Any]:
        """Perform a PUT request. Respects dry_run mode."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would PUT to {endpoint}")
            return {}
        return self.request("PUT", endpoint, json=json, **kwargs)

    def delete(self, endpoint: str, **kwargs: Any) -> dict[str, Any] | list[Any]:
        """Perform a DELETE request. Respects dry_run mode."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would DELETE {endpoint}")
            return {}
        return self.request("DELETE", endpoint, **kwargs)

    # -------------------------------------------------------------------------
    # Response Handling
    # -------------------------------------------------------------------------

    def _handle_response(
        self, response: requests.Response, endpoint: str
    ) -> dict[str, Any] | list[Any]:
        """Handle API response and convert errors to typed exceptions."""
        if response.ok:
            if response.text:
                json_data: dict[str, Any] | list[Any] = response.json()
                return json_data
            return {}

        status = response.status_code
        error_body = response.text[:500] if response.text else ""

        if status == 401:
            raise AuthenticationError("GitLab authentication failed. Check your token.")

        if status == 403:
            raise PermissionError(
                f"Permission denied for {endpoint}. Check token scopes.", issue_key=endpoint
            )

        if status == 404:
            raise NotFoundError(f"Not found: {endpoint}", issue_key=endpoint)

        raise IssueTrackerError(f"GitLab API error {status}: {error_body}", issue_key=endpoint)

    # -------------------------------------------------------------------------
    # Convenience Methods
    # -------------------------------------------------------------------------

    def project_endpoint(self, path: str = "") -> str:
        """Get the full endpoint for a project-scoped path."""
        # URL encode project_id if it contains slashes (path format)
        import urllib.parse

        encoded_project_id = urllib.parse.quote(self.project_id, safe="")
        base = f"projects/{encoded_project_id}"
        if path:
            return f"{base}/{path}"
        return base

    def get_authenticated_user(self) -> dict[str, Any]:
        """Get the currently authenticated user."""
        if self._current_user is None:
            result = self.get("user")
            if isinstance(result, dict):
                self._current_user = result
            else:
                self._current_user = {}
        return self._current_user

    def get_current_user_username(self) -> str:
        """Get the current user's username."""
        user = self.get_authenticated_user()
        if isinstance(user, dict):
            username = user.get("username", "")
            return str(username) if username else ""
        return ""

    def test_connection(self) -> bool:
        """Test if the API connection and credentials are valid."""
        try:
            self.get_authenticated_user()
            # Also verify project access
            self.get(self.project_endpoint())
            return True
        except IssueTrackerError:
            return False

    @property
    def is_connected(self) -> bool:
        """Check if the client has successfully connected."""
        return self._current_user is not None

    # -------------------------------------------------------------------------
    # Issues API
    # -------------------------------------------------------------------------

    def get_issue(self, issue_iid: int) -> dict[str, Any]:
        """Get a single issue by IID (internal ID, not global ID)."""
        result = self.get(self.project_endpoint(f"issues/{issue_iid}"))
        return result if isinstance(result, dict) else {}

    def list_issues(
        self,
        state: str = "opened",
        labels: list[str] | None = None,
        milestone: str | None = None,
        per_page: int = 100,
        page: int = 1,
    ) -> list[dict[str, Any]]:
        """List issues in the project."""
        params: dict[str, Any] = {
            "state": state,
            "per_page": per_page,
            "page": page,
        }
        if labels:
            params["labels"] = ",".join(labels)
        if milestone:
            params["milestone"] = milestone

        result = self.get(self.project_endpoint("issues"), params=params)
        return result if isinstance(result, list) else []

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
        data: dict[str, Any] = {"title": title}
        if description:
            data["description"] = description
        if labels:
            data["labels"] = ",".join(labels)
        if milestone_id:
            data["milestone_id"] = milestone_id
        if assignee_ids:
            data["assignee_ids"] = assignee_ids
        if weight is not None:
            data["weight"] = weight

        result = self.post(self.project_endpoint("issues"), json=data)
        return result if isinstance(result, dict) else {}

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
        data: dict[str, Any] = {}
        if title is not None:
            data["title"] = title
        if description is not None:
            data["description"] = description
        if state_event is not None:
            data["state_event"] = state_event  # 'close' or 'reopen'
        if labels is not None:
            data["labels"] = ",".join(labels)
        if milestone_id is not None:
            data["milestone_id"] = milestone_id
        if assignee_ids is not None:
            data["assignee_ids"] = assignee_ids
        if weight is not None:
            data["weight"] = weight

        result = self.put(self.project_endpoint(f"issues/{issue_iid}"), json=data)
        return result if isinstance(result, dict) else {}

    def get_issue_comments(self, issue_iid: int) -> list[dict[str, Any]]:
        """Get all notes (comments) on an issue."""
        result = self.get(self.project_endpoint(f"issues/{issue_iid}/notes"))
        return result if isinstance(result, list) else []

    def add_issue_comment(
        self,
        issue_iid: int,
        body: str,
    ) -> dict[str, Any]:
        """Add a note (comment) to an issue."""
        result = self.post(self.project_endpoint(f"issues/{issue_iid}/notes"), json={"body": body})
        return result if isinstance(result, dict) else {}

    # -------------------------------------------------------------------------
    # Labels API
    # -------------------------------------------------------------------------

    def list_labels(self) -> list[dict[str, Any]]:
        """List all labels in the project."""
        result = self.get(self.project_endpoint("labels"))
        return result if isinstance(result, list) else []

    def create_label(
        self,
        name: str,
        color: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Create a new label."""
        data: dict[str, Any] = {"name": name, "color": color}
        if description:
            data["description"] = description

        result = self.post(self.project_endpoint("labels"), json=data)
        return result if isinstance(result, dict) else {}

    # -------------------------------------------------------------------------
    # Milestones API (used for epics)
    # -------------------------------------------------------------------------

    def get_milestone(self, milestone_id: int) -> dict[str, Any]:
        """Get a single milestone."""
        result = self.get(self.project_endpoint(f"milestones/{milestone_id}"))
        return result if isinstance(result, dict) else {}

    def list_milestones(
        self,
        state: str = "active",
    ) -> list[dict[str, Any]]:
        """List all milestones."""
        result = self.get(self.project_endpoint("milestones"), params={"state": state})
        return result if isinstance(result, list) else []

    def create_milestone(
        self,
        title: str,
        description: str | None = None,
        state: str = "active",
    ) -> dict[str, Any]:
        """Create a new milestone."""
        data: dict[str, Any] = {"title": title, "state": state}
        if description:
            data["description"] = description

        result = self.post(self.project_endpoint("milestones"), json=data)
        return result if isinstance(result, dict) else {}

    def update_milestone(
        self,
        milestone_id: int,
        title: str | None = None,
        description: str | None = None,
        state_event: str | None = None,
    ) -> dict[str, Any]:
        """Update an existing milestone."""
        data: dict[str, Any] = {}
        if title is not None:
            data["title"] = title
        if description is not None:
            data["description"] = description
        if state_event is not None:
            data["state_event"] = state_event  # 'close' or 'activate'

        result = self.put(self.project_endpoint(f"milestones/{milestone_id}"), json=data)
        return result if isinstance(result, dict) else {}

    # -------------------------------------------------------------------------
    # Epics API (Premium/Ultimate feature)
    # -------------------------------------------------------------------------

    def get_epic(self, epic_iid: int, group_id: str) -> dict[str, Any]:
        """Get a single epic (requires Premium/Ultimate)."""
        import urllib.parse

        encoded_group_id = urllib.parse.quote(group_id, safe="")
        result = self.get(f"groups/{encoded_group_id}/epics/{epic_iid}")
        return result if isinstance(result, dict) else {}

    def list_epics(
        self,
        group_id: str,
        state: str = "opened",
    ) -> list[dict[str, Any]]:
        """List all epics in a group (requires Premium/Ultimate)."""
        import urllib.parse

        encoded_group_id = urllib.parse.quote(group_id, safe="")
        result = self.get(f"groups/{encoded_group_id}/epics", params={"state": state})
        return result if isinstance(result, list) else []

    # -------------------------------------------------------------------------
    # Merge Requests API
    # -------------------------------------------------------------------------

    def get_merge_request(self, merge_request_iid: int) -> dict[str, Any]:
        """Get a single merge request by IID."""
        result = self.get(self.project_endpoint(f"merge_requests/{merge_request_iid}"))
        return result if isinstance(result, dict) else {}

    def list_merge_requests(
        self,
        state: str = "opened",
        per_page: int = 100,
        page: int = 1,
    ) -> list[dict[str, Any]]:
        """List merge requests in the project."""
        params: dict[str, Any] = {
            "state": state,
            "per_page": per_page,
            "page": page,
        }
        result = self.get(self.project_endpoint("merge_requests"), params=params)
        return result if isinstance(result, list) else []

    def get_merge_requests_for_issue(self, issue_iid: int) -> list[dict[str, Any]]:
        """Get all merge requests that reference an issue."""
        # GitLab automatically links MRs that reference issues in description/title
        # We can search for MRs that mention the issue
        all_mrs = self.list_merge_requests(state="all")
        issue_ref = f"#{issue_iid}"
        linked_mrs = []
        for mr in all_mrs:
            description = mr.get("description", "") or ""
            title = mr.get("title", "") or ""
            if issue_ref in description or issue_ref in title:
                linked_mrs.append(mr)
        return linked_mrs

    def link_merge_request_to_issue(
        self,
        merge_request_iid: int,
        issue_iid: int,
        action: str = "closes",
    ) -> bool:
        """
        Link a merge request to an issue by updating MR description.

        GitLab automatically links MRs that reference issues using keywords:
        - "closes #123", "fixes #123", "resolves #123" - closes the issue
        - "relates to #123" - links without closing

        Args:
            merge_request_iid: Merge request IID
            issue_iid: Issue IID to link
            action: Action keyword ("closes", "fixes", "resolves", "relates to")
        """
        mr = self.get_merge_request(merge_request_iid)
        current_description = mr.get("description", "") or ""
        issue_ref = f"{action} #{issue_iid}"

        # Check if already linked
        if f"#{issue_iid}" in current_description:
            return True

        # Add reference to description
        new_description = f"{current_description}\n\n{issue_ref}".strip()
        self.update_merge_request(merge_request_iid, description=new_description)
        return True

    def update_merge_request(
        self,
        merge_request_iid: int,
        title: str | None = None,
        description: str | None = None,
        state_event: str | None = None,
    ) -> dict[str, Any]:
        """Update a merge request."""
        data: dict[str, Any] = {}
        if title is not None:
            data["title"] = title
        if description is not None:
            data["description"] = description
        if state_event is not None:
            data["state_event"] = state_event  # 'close', 'reopen', 'merge'

        result = self.put(self.project_endpoint(f"merge_requests/{merge_request_iid}"), json=data)
        return result if isinstance(result, dict) else {}

    # -------------------------------------------------------------------------
    # Issue Boards API
    # -------------------------------------------------------------------------

    def list_boards(self) -> list[dict[str, Any]]:
        """List all issue boards in the project."""
        result = self.get(self.project_endpoint("boards"))
        return result if isinstance(result, list) else []

    def get_board(self, board_id: int) -> dict[str, Any]:
        """Get a single board."""
        result = self.get(self.project_endpoint(f"boards/{board_id}"))
        return result if isinstance(result, dict) else {}

    def get_board_lists(self, board_id: int) -> list[dict[str, Any]]:
        """Get all lists (columns) for a board."""
        result = self.get(self.project_endpoint(f"boards/{board_id}/lists"))
        return result if isinstance(result, list) else []

    def move_issue_to_board_list(
        self,
        issue_iid: int,
        board_id: int,
        list_id: int,
    ) -> bool:
        """Move an issue to a specific board list."""
        result = self.put(
            self.project_endpoint(f"boards/{board_id}/lists/{list_id}/issues/{issue_iid}")
        )
        return isinstance(result, dict)

    def get_issue_board_position(self, issue_iid: int) -> dict[str, Any] | None:
        """Get the board position for an issue."""
        result = self.get(self.project_endpoint(f"issues/{issue_iid}/board_position"))
        return result if isinstance(result, dict) else None

    # -------------------------------------------------------------------------
    # Time Tracking API
    # -------------------------------------------------------------------------

    def get_issue_time_stats(self, issue_iid: int) -> dict[str, Any]:
        """Get time tracking statistics for an issue."""
        result = self.get(self.project_endpoint(f"issues/{issue_iid}/time_stats"))
        return result if isinstance(result, dict) else {}

    def add_spent_time(
        self,
        issue_iid: int,
        duration: str,
        summary: str | None = None,
    ) -> dict[str, Any]:
        """
        Add spent time to an issue.

        Args:
            issue_iid: Issue IID
            duration: Time duration (e.g., "1h 30m", "2h", "45m")
            summary: Optional summary/note for the time entry

        Returns:
            Updated time stats
        """
        data: dict[str, Any] = {"duration": duration}
        if summary:
            data["summary"] = summary

        result = self.post(self.project_endpoint(f"issues/{issue_iid}/add_spent_time"), json=data)
        return result if isinstance(result, dict) else {}

    def reset_spent_time(self, issue_iid: int) -> dict[str, Any]:
        """Reset spent time for an issue."""
        result = self.post(self.project_endpoint(f"issues/{issue_iid}/reset_spent_time"))
        return result if isinstance(result, dict) else {}

    def estimate_time(self, issue_iid: int, duration: str) -> dict[str, Any]:
        """
        Set time estimate for an issue.

        Args:
            issue_iid: Issue IID
            duration: Time estimate (e.g., "3h 30m", "1d", "2w")

        Returns:
            Updated time stats
        """
        data = {"duration": duration}
        result = self.post(self.project_endpoint(f"issues/{issue_iid}/time_estimate"), json=data)
        return result if isinstance(result, dict) else {}

    def reset_time_estimate(self, issue_iid: int) -> dict[str, Any]:
        """Reset time estimate for an issue."""
        result = self.post(self.project_endpoint(f"issues/{issue_iid}/reset_time_estimate"))
        return result if isinstance(result, dict) else {}

    # -------------------------------------------------------------------------
    # Resource Cleanup
    # -------------------------------------------------------------------------

    def close(self) -> None:
        """Close the client and release connection pool resources."""
        self._session.close()
        self.logger.debug("Closed HTTP session")

    def __enter__(self) -> "GitLabApiClient":
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
