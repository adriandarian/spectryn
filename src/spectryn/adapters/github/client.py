"""
GitHub API Client - Low-level HTTP client for GitHub REST API.

This handles the raw HTTP communication with GitHub.
The GitHubAdapter uses this to implement the IssueTrackerPort.
"""

import logging
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter

from spectryn.adapters.async_base import (
    RETRYABLE_STATUS_CODES,
    GitHubRateLimiter,
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


class GitHubApiClient:
    """
    Low-level GitHub REST API client.

    Handles authentication, request/response, rate limiting, and error handling.

    Features:
    - Automatic retry with exponential backoff for transient failures
    - Proactive rate limiting aware of GitHub's X-RateLimit-* headers
    - Connection pooling for performance
    """

    API_VERSION = "2022-11-28"
    BASE_URL = "https://api.github.com"

    # Default retry configuration
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_INITIAL_DELAY = 1.0
    DEFAULT_MAX_DELAY = 60.0
    DEFAULT_BACKOFF_FACTOR = 2.0
    DEFAULT_JITTER = 0.1

    # Default rate limiting (conservative for authenticated users)
    DEFAULT_REQUESTS_PER_SECOND = 10.0
    DEFAULT_BURST_SIZE = 20

    # Connection pool settings
    DEFAULT_POOL_CONNECTIONS = 10
    DEFAULT_POOL_MAXSIZE = 10
    DEFAULT_TIMEOUT = 30.0

    def __init__(
        self,
        token: str,
        owner: str,
        repo: str,
        base_url: str = BASE_URL,
        dry_run: bool = True,
        max_retries: int = DEFAULT_MAX_RETRIES,
        initial_delay: float = DEFAULT_INITIAL_DELAY,
        max_delay: float = DEFAULT_MAX_DELAY,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
        jitter: float = DEFAULT_JITTER,
        requests_per_second: float | None = DEFAULT_REQUESTS_PER_SECOND,
        burst_size: int = DEFAULT_BURST_SIZE,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        """
        Initialize the GitHub client.

        Args:
            token: GitHub Personal Access Token or GitHub App token
            owner: Repository owner (user or organization)
            repo: Repository name
            base_url: GitHub API base URL (for GitHub Enterprise)
            dry_run: If True, don't make write operations
            max_retries: Maximum retry attempts for transient failures
            initial_delay: Initial retry delay in seconds
            max_delay: Maximum retry delay in seconds
            backoff_factor: Multiplier for exponential backoff
            jitter: Random jitter factor (0.1 = 10%)
            requests_per_second: Maximum request rate (None to disable)
            burst_size: Maximum burst capacity
            timeout: Request timeout in seconds
        """
        self.token = token
        self.owner = owner
        self.repo = repo
        self.base_url = base_url.rstrip("/")
        self.dry_run = dry_run
        self.timeout = timeout
        self.logger = logging.getLogger("GitHubApiClient")

        # Retry configuration
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.jitter = jitter

        # Rate limiting
        self._rate_limiter: GitHubRateLimiter | None = None
        if requests_per_second is not None and requests_per_second > 0:
            self._rate_limiter = GitHubRateLimiter(
                requests_per_second=requests_per_second,
                burst_size=burst_size,
            )

        # Headers for GitHub API
        self.headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": self.API_VERSION,
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
        Make an authenticated request to GitHub API with rate limiting and retry.

        Args:
            method: HTTP method
            endpoint: API endpoint (e.g., 'repos/{owner}/{repo}/issues')
            **kwargs: Additional arguments for requests

        Returns:
            JSON response (dict or list)

        Raises:
            IssueTrackerError: On API errors
        """
        # Support both absolute endpoints and repo-relative endpoints
        if endpoint.startswith("/"):
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
                            f"GitHub rate limit exceeded for {endpoint}",
                            retry_after=retry_after,
                            issue_key=endpoint,
                        )
                    raise TransientError(
                        f"GitHub server error {response.status_code} for {endpoint}",
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

    def patch(
        self,
        endpoint: str,
        json: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | list[Any]:
        """Perform a PATCH request. Respects dry_run mode."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would PATCH {endpoint}")
            return {}
        return self.request("PATCH", endpoint, json=json, **kwargs)

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
                return response.json()
            return {}

        status = response.status_code
        error_body = response.text[:500] if response.text else ""

        if status == 401:
            raise AuthenticationError("GitHub authentication failed. Check your token.")

        if status == 403:
            raise PermissionError(
                f"Permission denied for {endpoint}. Check token scopes.", issue_key=endpoint
            )

        if status == 404:
            raise NotFoundError(f"Not found: {endpoint}", issue_key=endpoint)

        raise IssueTrackerError(f"GitHub API error {status}: {error_body}", issue_key=endpoint)

    # -------------------------------------------------------------------------
    # Convenience Methods
    # -------------------------------------------------------------------------

    def repo_endpoint(self, path: str = "") -> str:
        """Get the full endpoint for a repo-scoped path."""
        base = f"repos/{self.owner}/{self.repo}"
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

    def get_current_user_login(self) -> str:
        """Get the current user's login name."""
        return self.get_authenticated_user().get("login", "")

    def test_connection(self) -> bool:
        """Test if the API connection and credentials are valid."""
        try:
            self.get_authenticated_user()
            # Also verify repo access
            self.get(self.repo_endpoint())
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

    def get_issue(self, issue_number: int) -> dict[str, Any]:
        """Get a single issue by number."""
        result = self.get(self.repo_endpoint(f"issues/{issue_number}"))
        return result if isinstance(result, dict) else {}

    def list_issues(
        self,
        state: str = "open",
        labels: list[str] | None = None,
        milestone: str | None = None,
        per_page: int = 100,
    ) -> list[dict[str, Any]]:
        """List issues in the repository."""
        params: dict[str, Any] = {
            "state": state,
            "per_page": per_page,
        }
        if labels:
            params["labels"] = ",".join(labels)
        if milestone:
            params["milestone"] = milestone

        result = self.get(self.repo_endpoint("issues"), params=params)
        return result if isinstance(result, list) else []

    def create_issue(
        self,
        title: str,
        body: str | None = None,
        labels: list[str] | None = None,
        milestone: int | None = None,
        assignees: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a new issue."""
        data: dict[str, Any] = {"title": title}
        if body:
            data["body"] = body
        if labels:
            data["labels"] = labels
        if milestone:
            data["milestone"] = milestone
        if assignees:
            data["assignees"] = assignees

        result = self.post(self.repo_endpoint("issues"), json=data)
        return result if isinstance(result, dict) else {}

    def update_issue(
        self,
        issue_number: int,
        title: str | None = None,
        body: str | None = None,
        state: str | None = None,
        labels: list[str] | None = None,
        milestone: int | None = None,
        assignees: list[str] | None = None,
    ) -> dict[str, Any]:
        """Update an existing issue."""
        data: dict[str, Any] = {}
        if title is not None:
            data["title"] = title
        if body is not None:
            data["body"] = body
        if state is not None:
            data["state"] = state
        if labels is not None:
            data["labels"] = labels
        if milestone is not None:
            data["milestone"] = milestone
        if assignees is not None:
            data["assignees"] = assignees

        result = self.patch(self.repo_endpoint(f"issues/{issue_number}"), json=data)
        return result if isinstance(result, dict) else {}

    def get_issue_comments(self, issue_number: int) -> list[dict[str, Any]]:
        """Get all comments on an issue."""
        result = self.get(self.repo_endpoint(f"issues/{issue_number}/comments"))
        return result if isinstance(result, list) else []

    def add_issue_comment(
        self,
        issue_number: int,
        body: str,
    ) -> dict[str, Any]:
        """Add a comment to an issue."""
        result = self.post(
            self.repo_endpoint(f"issues/{issue_number}/comments"), json={"body": body}
        )
        return result if isinstance(result, dict) else {}

    # -------------------------------------------------------------------------
    # Labels API
    # -------------------------------------------------------------------------

    def list_labels(self) -> list[dict[str, Any]]:
        """List all labels in the repository."""
        result = self.get(self.repo_endpoint("labels"))
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

        result = self.post(self.repo_endpoint("labels"), json=data)
        return result if isinstance(result, dict) else {}

    # -------------------------------------------------------------------------
    # Milestones API (used for epics)
    # -------------------------------------------------------------------------

    def get_milestone(self, milestone_number: int) -> dict[str, Any]:
        """Get a single milestone."""
        result = self.get(self.repo_endpoint(f"milestones/{milestone_number}"))
        return result if isinstance(result, dict) else {}

    def list_milestones(
        self,
        state: str = "open",
    ) -> list[dict[str, Any]]:
        """List all milestones."""
        result = self.get(self.repo_endpoint("milestones"), params={"state": state})
        return result if isinstance(result, list) else []

    def create_milestone(
        self,
        title: str,
        description: str | None = None,
        state: str = "open",
    ) -> dict[str, Any]:
        """Create a new milestone."""
        data: dict[str, Any] = {"title": title, "state": state}
        if description:
            data["description"] = description

        result = self.post(self.repo_endpoint("milestones"), json=data)
        return result if isinstance(result, dict) else {}

    def update_milestone(
        self,
        milestone_number: int,
        title: str | None = None,
        description: str | None = None,
        state: str | None = None,
    ) -> dict[str, Any]:
        """Update an existing milestone."""
        data: dict[str, Any] = {}
        if title is not None:
            data["title"] = title
        if description is not None:
            data["description"] = description
        if state is not None:
            data["state"] = state

        result = self.patch(self.repo_endpoint(f"milestones/{milestone_number}"), json=data)
        return result if isinstance(result, dict) else {}

    # -------------------------------------------------------------------------
    # Search API
    # -------------------------------------------------------------------------

    def search_issues(
        self,
        query: str,
        per_page: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Search for issues using GitHub search syntax.

        The query is automatically scoped to the current repo.
        """
        full_query = f"repo:{self.owner}/{self.repo} {query}"
        result = self.get("search/issues", params={"q": full_query, "per_page": per_page})
        if isinstance(result, dict):
            return result.get("items", [])
        return []

    # -------------------------------------------------------------------------
    # Resource Cleanup
    # -------------------------------------------------------------------------

    def close(self) -> None:
        """Close the client and release connection pool resources."""
        self._session.close()
        self.logger.debug("Closed HTTP session")

    def __enter__(self) -> "GitHubApiClient":
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

    @property
    def rate_limit_stats(self) -> dict[str, Any] | None:
        """Get rate limiter statistics."""
        if self._rate_limiter is None:
            return None
        return self._rate_limiter.stats
