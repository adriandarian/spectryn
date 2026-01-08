"""
Plane.so API Client - REST API client for Plane.so.

This handles the raw HTTP communication with Plane.so.
The PlaneAdapter uses this to implement the IssueTrackerPort.

Plane.so API Documentation: https://docs.plane.so/api-reference
Rate Limits: Varies by instance (self-hosted vs cloud)
"""

import logging
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter

from spectryn.adapters.async_base import (
    RETRYABLE_STATUS_CODES,
    TokenBucketRateLimiter,
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


class PlaneRateLimiter(TokenBucketRateLimiter):
    """
    Plane.so-specific rate limiter.

    Plane.so rate limits vary by instance (cloud vs self-hosted).
    This implementation uses conservative defaults.
    """

    def __init__(
        self,
        requests_per_second: float = 10.0,  # Conservative default
        burst_size: int = 20,
    ):
        """
        Initialize the Plane rate limiter.

        Args:
            requests_per_second: Maximum sustained request rate.
            burst_size: Maximum burst capacity.
        """
        super().__init__(
            requests_per_second=requests_per_second,
            burst_size=burst_size,
            logger_name="PlaneRateLimiter",
        )


class PlaneApiClient:
    """
    Low-level Plane.so REST API client.

    Handles authentication, request/response, rate limiting, and error handling.

    Features:
    - API token authentication
    - Automatic retry with exponential backoff
    - Rate limiting
    - Connection pooling
    - Support for self-hosted instances
    """

    BASE_URL = "https://api.plane.so"

    # Default retry configuration
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_INITIAL_DELAY = 1.0
    DEFAULT_MAX_DELAY = 60.0
    DEFAULT_BACKOFF_FACTOR = 2.0
    DEFAULT_JITTER = 0.1

    # Default rate limiting (conservative)
    DEFAULT_REQUESTS_PER_SECOND = 10.0
    DEFAULT_BURST_SIZE = 20

    # Connection pool settings
    DEFAULT_TIMEOUT = 30.0

    def __init__(
        self,
        api_token: str,
        workspace_slug: str,
        project_id: str,
        api_url: str = BASE_URL,
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
        Initialize the Plane client.

        Args:
            api_token: Plane API token
            workspace_slug: Workspace slug (e.g., 'my-workspace')
            project_id: Project ID (UUID)
            api_url: Plane API base URL (defaults to cloud, override for self-hosted)
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
        self.api_token = api_token
        self.workspace_slug = workspace_slug
        self.project_id = project_id
        self.api_url = api_url.rstrip("/")
        self.dry_run = dry_run
        self.timeout = timeout
        self.logger = logging.getLogger("PlaneApiClient")

        # Retry configuration
        self.max_retries = max_retries
        self.current_initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.jitter = jitter

        # Rate limiting
        self._rate_limiter: PlaneRateLimiter | None = None
        if requests_per_second is not None and requests_per_second > 0:
            self._rate_limiter = PlaneRateLimiter(
                requests_per_second=requests_per_second,
                burst_size=burst_size,
            )

        # Headers for Plane API
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_token}",
        }

        # Configure session with connection pooling
        self._session = requests.Session()
        self._session.headers.update(self.headers)
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)  # For self-hosted instances

        # Cache
        self._current_user: dict | None = None
        self._project_cache: dict | None = None
        self._states_cache: list[dict] = []
        self._priorities_cache: list[dict] = []

    # -------------------------------------------------------------------------
    # Core Request Methods
    # -------------------------------------------------------------------------

    def request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | list[Any]:
        """
        Make an authenticated request to Plane API with rate limiting and retry.

        Args:
            method: HTTP method
            endpoint: API endpoint (e.g., 'workspaces/{slug}/projects/{id}/issues')
            params: Query parameters
            json: JSON body for POST/PUT requests
            **kwargs: Additional arguments for requests

        Returns:
            JSON response (dict or list)

        Raises:
            IssueTrackerError: On API errors
        """
        # Build full URL
        if endpoint.startswith("/"):
            url = f"{self.api_url}{endpoint}"
        else:
            url = f"{self.api_url}/{endpoint}"

        last_exception: Exception | None = None

        for attempt in range(self.max_retries + 1):
            # Apply rate limiting
            if self._rate_limiter is not None:
                self._rate_limiter.acquire()

            try:
                if "timeout" not in kwargs:
                    kwargs["timeout"] = self.timeout

                response = self._session.request(method, url, params=params, json=json, **kwargs)

                # Update rate limiter from response headers
                if self._rate_limiter is not None:
                    self._rate_limiter.update_from_response(response)

                # Check for retryable status codes
                if response.status_code in RETRYABLE_STATUS_CODES:
                    retry_after = get_retry_after(response)
                    delay = calculate_delay(
                        attempt,
                        initial_delay=self.current_initial_delay,
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
                            f"Plane rate limit exceeded for {endpoint}",
                            retry_after=retry_after,
                        )
                    raise TransientError(
                        f"Plane server error {response.status_code} for {endpoint}"
                    )

                return self._handle_response(response, endpoint)

            except requests.exceptions.ConnectionError as e:
                last_exception = e
                if attempt < self.max_retries:
                    delay = calculate_delay(
                        attempt,
                        initial_delay=self.current_initial_delay,
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
                        initial_delay=self.current_initial_delay,
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

    def _handle_response(
        self, response: requests.Response, endpoint: str
    ) -> dict[str, Any] | list[Any]:
        """Handle Plane API response and convert errors."""
        if response.status_code == 401:
            raise AuthenticationError("Plane authentication failed. Check your API token.")

        if response.status_code == 403:
            raise PermissionError("Permission denied to access Plane resource")

        if response.status_code == 404:
            raise NotFoundError(f"Plane resource not found: {endpoint}")

        if not response.ok:
            error_text = response.text[:500]
            raise IssueTrackerError(
                f"Plane API error {response.status_code} for {endpoint}: {error_text}"
            )

        # Plane returns JSON
        try:
            json_data: dict[str, Any] | list[Any] = response.json()
            return json_data
        except ValueError as e:
            raise IssueTrackerError(f"Invalid JSON response from Plane: {e}", cause=e)

    # -------------------------------------------------------------------------
    # Current User API
    # -------------------------------------------------------------------------

    def get_current_user(self) -> dict[str, Any]:
        """Get the current authenticated user."""
        if self._current_user is None:
            result = self.request("GET", "api/users/me/")
            assert isinstance(result, dict)
            self._current_user = result
        return self._current_user

    def test_connection(self) -> bool:
        """Test if the API connection and credentials are valid."""
        try:
            self.get_current_user()
            return True
        except IssueTrackerError:
            return False

    @property
    def is_connected(self) -> bool:
        """Check if the client has successfully connected."""
        return self._current_user is not None

    # -------------------------------------------------------------------------
    # Workspace & Project API
    # -------------------------------------------------------------------------

    def get_project(self) -> dict[str, Any]:
        """Get the configured project."""
        if self._project_cache is None:
            result = self.request(
                "GET",
                f"api/workspaces/{self.workspace_slug}/projects/{self.project_id}/",
            )
            assert isinstance(result, dict)
            self._project_cache = result
        return self._project_cache

    # -------------------------------------------------------------------------
    # States API
    # -------------------------------------------------------------------------

    def get_states(self) -> list[dict[str, Any]]:
        """Get all states for the project."""
        if not self._states_cache:
            result = self.request(
                "GET",
                f"api/workspaces/{self.workspace_slug}/projects/{self.project_id}/states/",
            )
            assert isinstance(result, list)
            self._states_cache = result
        return self._states_cache

    def get_state_by_name(self, name: str) -> dict[str, Any] | None:
        """Get a state by name (case-insensitive)."""
        states = self.get_states()
        name_lower = name.lower()
        for state in states:
            if state.get("name", "").lower() == name_lower:
                return state
        return None

    # -------------------------------------------------------------------------
    # Priorities API
    # -------------------------------------------------------------------------

    def get_priorities(self) -> list[dict[str, Any]]:
        """Get all priority options."""
        if not self._priorities_cache:
            # Plane priorities are typically: urgent, high, medium, low, none
            # This is a static list based on Plane's priority system
            self._priorities_cache = [
                {"key": "urgent", "label": "Urgent"},
                {"key": "high", "label": "High"},
                {"key": "medium", "label": "Medium"},
                {"key": "low", "label": "Low"},
                {"key": "none", "label": "None"},
            ]
        return self._priorities_cache

    def get_priority_by_key(self, key: str) -> dict[str, Any] | None:
        """Get a priority by key."""
        priorities = self.get_priorities()
        key_lower = key.lower()
        for priority in priorities:
            if priority.get("key", "").lower() == key_lower:
                return priority
        return None

    # -------------------------------------------------------------------------
    # Issues API
    # -------------------------------------------------------------------------

    def get_issue(self, issue_id: str) -> dict[str, Any]:
        """Get an issue by ID."""
        result = self.request(
            "GET",
            f"api/workspaces/{self.workspace_slug}/projects/{self.project_id}/issues/{issue_id}/",
        )
        assert isinstance(result, dict)
        return result

    def get_issues(
        self,
        state: str | None = None,
        priority: str | None = None,
        assignee: str | None = None,
        limit: int = 50,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get issues for the project.

        Args:
            state: Filter by state
            priority: Filter by priority
            assignee: Filter by assignee ID
            limit: Maximum number of results
            filters: Additional filters as dict (e.g., {"labels": ["bug"], "cycle": "cycle-id"})
        """
        params: dict[str, Any] = {"limit": limit}
        if state:
            params["state"] = state
        if priority:
            params["priority"] = priority
        if assignee:
            params["assignee"] = assignee
        if filters:
            params.update(filters)

        result = self.request(
            "GET",
            f"api/workspaces/{self.workspace_slug}/projects/{self.project_id}/issues/",
            params=params,
        )
        assert isinstance(result, list)
        return result

    def create_issue(
        self,
        name: str,
        description: str | None = None,
        state_id: str | None = None,
        priority: str | None = None,
        assignee_id: str | None = None,
        estimate_point: int | None = None,
        parent_id: str | None = None,
        cycle_id: str | None = None,
        module_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new issue."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would create issue '{name}'")
            return {
                "id": "dry-run-issue-id",
                "name": name,
                "project": self.project_id,
            }

        json_data: dict[str, Any] = {
            "name": name,
            "project": self.project_id,
        }
        if description:
            json_data["description"] = description
        if state_id:
            json_data["state"] = state_id
        if priority:
            json_data["priority"] = priority
        if assignee_id:
            json_data["assignee_ids"] = [assignee_id]
        if estimate_point is not None:
            json_data["estimate_point"] = estimate_point
        if parent_id:
            json_data["parent"] = parent_id
        if cycle_id:
            json_data["cycle"] = cycle_id
        if module_id:
            json_data["module"] = module_id

        result = self.request(
            "POST",
            f"api/workspaces/{self.workspace_slug}/projects/{self.project_id}/issues/",
            json=json_data,
        )
        assert isinstance(result, dict)
        return result

    def update_issue(
        self,
        issue_id: str,
        name: str | None = None,
        description: str | None = None,
        state_id: str | None = None,
        priority: str | None = None,
        assignee_id: str | None = None,
        estimate_point: int | None = None,
        parent_id: str | None = None,
    ) -> dict[str, Any]:
        """Update an existing issue."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would update issue {issue_id}")
            return {"id": issue_id}

        json_data: dict[str, Any] = {}
        if name is not None:
            json_data["name"] = name
        if description is not None:
            json_data["description"] = description
        if state_id is not None:
            json_data["state"] = state_id
        if priority is not None:
            json_data["priority"] = priority
        if assignee_id is not None:
            json_data["assignee_ids"] = [assignee_id]
        if estimate_point is not None:
            json_data["estimate_point"] = estimate_point
        if parent_id is not None:
            json_data["parent"] = parent_id

        if not json_data:
            return self.get_issue(issue_id)

        result = self.request(
            "PATCH",
            f"api/workspaces/{self.workspace_slug}/projects/{self.project_id}/issues/{issue_id}/",
            json=json_data,
        )
        assert isinstance(result, dict)
        return result

    def get_issue_comments(self, issue_id: str) -> list[dict[str, Any]]:
        """Get all comments on an issue."""
        result = self.request(
            "GET",
            f"api/workspaces/{self.workspace_slug}/projects/{self.project_id}/issues/{issue_id}/comments/",
        )
        assert isinstance(result, list)
        return result

    def add_comment(self, issue_id: str, comment: str) -> dict[str, Any]:
        """Add a comment to an issue."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would add comment to issue {issue_id}")
            return {"id": "dry-run-comment-id", "comment": comment}

        result = self.request(
            "POST",
            f"api/workspaces/{self.workspace_slug}/projects/{self.project_id}/issues/{issue_id}/comments/",
            json={"comment": comment},
        )
        assert isinstance(result, dict)
        return result

    # -------------------------------------------------------------------------
    # Cycles API
    # -------------------------------------------------------------------------

    def get_cycles(self) -> list[dict[str, Any]]:
        """Get all cycles for the project."""
        result = self.request(
            "GET",
            f"api/workspaces/{self.workspace_slug}/projects/{self.project_id}/cycles/",
        )
        assert isinstance(result, list)
        return result

    def get_cycle(self, cycle_id: str) -> dict[str, Any]:
        """Get a cycle by ID."""
        result = self.request(
            "GET",
            f"api/workspaces/{self.workspace_slug}/projects/{self.project_id}/cycles/{cycle_id}/",
        )
        assert isinstance(result, dict)
        return result

    def create_cycle(
        self,
        name: str,
        description: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """Create a new cycle."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would create cycle '{name}'")
            return {"id": "dry-run-cycle-id", "name": name}

        json_data: dict[str, Any] = {
            "name": name,
            "project": self.project_id,
        }
        if description:
            json_data["description"] = description
        if start_date:
            json_data["start_date"] = start_date
        if end_date:
            json_data["end_date"] = end_date

        result = self.request(
            "POST",
            f"api/workspaces/{self.workspace_slug}/projects/{self.project_id}/cycles/",
            json=json_data,
        )
        assert isinstance(result, dict)
        return result

    def get_cycle_issues(self, cycle_id: str) -> list[dict[str, Any]]:
        """Get all issues in a cycle."""
        result = self.request(
            "GET",
            f"api/workspaces/{self.workspace_slug}/projects/{self.project_id}/cycles/{cycle_id}/issues/",
        )
        assert isinstance(result, list)
        return result

    # -------------------------------------------------------------------------
    # Modules API
    # -------------------------------------------------------------------------

    def get_modules(self) -> list[dict[str, Any]]:
        """Get all modules for the project."""
        result = self.request(
            "GET",
            f"api/workspaces/{self.workspace_slug}/projects/{self.project_id}/modules/",
        )
        assert isinstance(result, list)
        return result

    def get_module(self, module_id: str) -> dict[str, Any]:
        """Get a module by ID."""
        result = self.request(
            "GET",
            f"api/workspaces/{self.workspace_slug}/projects/{self.project_id}/modules/{module_id}/",
        )
        assert isinstance(result, dict)
        return result

    def create_module(
        self,
        name: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Create a new module."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would create module '{name}'")
            return {"id": "dry-run-module-id", "name": name}

        json_data: dict[str, Any] = {
            "name": name,
            "project": self.project_id,
        }
        if description:
            json_data["description"] = description

        result = self.request(
            "POST",
            f"api/workspaces/{self.workspace_slug}/projects/{self.project_id}/modules/",
            json=json_data,
        )
        assert isinstance(result, dict)
        return result

    def get_module_issues(self, module_id: str) -> list[dict[str, Any]]:
        """Get all issues in a module."""
        result = self.request(
            "GET",
            f"api/workspaces/{self.workspace_slug}/projects/{self.project_id}/modules/{module_id}/issues/",
        )
        assert isinstance(result, list)
        return result

    # -------------------------------------------------------------------------
    # Views & Filters API
    # -------------------------------------------------------------------------

    def get_views(self) -> list[dict[str, Any]]:
        """
        Get all saved views/filters for the project.

        Returns:
            List of view definitions
        """
        result = self.request(
            "GET",
            f"api/workspaces/{self.workspace_slug}/projects/{self.project_id}/views/",
        )
        assert isinstance(result, list)
        return result

    def get_view(self, view_id: str) -> dict[str, Any]:
        """
        Get a specific view by ID.

        Args:
            view_id: View ID to retrieve

        Returns:
            View data with filters and configuration
        """
        result = self.request(
            "GET",
            f"api/workspaces/{self.workspace_slug}/projects/{self.project_id}/views/{view_id}/",
        )
        assert isinstance(result, dict)
        return result

    def get_view_issues(
        self,
        view_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Get issues from a specific view.

        Args:
            view_id: View ID
            limit: Maximum number of results

        Returns:
            List of issues matching the view filters
        """
        params: dict[str, Any] = {"limit": limit}
        result = self.request(
            "GET",
            f"api/workspaces/{self.workspace_slug}/projects/{self.project_id}/views/{view_id}/issues/",
            params=params,
        )
        assert isinstance(result, list)
        return result

    def create_view(
        self,
        name: str,
        filters: dict[str, Any],
        description: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a new saved view/filter.

        Args:
            name: View name
            filters: Filter criteria (e.g., {"state": "started", "priority": "high"})
            description: Optional view description

        Returns:
            Created view data
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would create view '{name}'")
            return {
                "id": "view:dry-run",
                "name": name,
                "filters": filters,
                "project": self.project_id,
            }

        json_data: dict[str, Any] = {
            "name": name,
            "filters": filters,
            "project": self.project_id,
        }
        if description:
            json_data["description"] = description

        result = self.request(
            "POST",
            f"api/workspaces/{self.workspace_slug}/projects/{self.project_id}/views/",
            json=json_data,
        )
        assert isinstance(result, dict)
        return result

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
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would update view {view_id}")
            return {"id": view_id}

        json_data: dict[str, Any] = {}
        if name is not None:
            json_data["name"] = name
        if filters is not None:
            json_data["filters"] = filters
        if description is not None:
            json_data["description"] = description

        if not json_data:
            return self.get_view(view_id)

        result = self.request(
            "PATCH",
            f"api/workspaces/{self.workspace_slug}/projects/{self.project_id}/views/{view_id}/",
            json=json_data,
        )
        assert isinstance(result, dict)
        return result

    def delete_view(self, view_id: str) -> bool:
        """
        Delete a saved view.

        Args:
            view_id: View ID to delete

        Returns:
            True if successful
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would delete view {view_id}")
            return True

        self.request(
            "DELETE",
            f"api/workspaces/{self.workspace_slug}/projects/{self.project_id}/views/{view_id}/",
        )
        return True

    # -------------------------------------------------------------------------
    # Webhooks API
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
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would create webhook for URL {url}")
            return {
                "id": "webhook:dry-run",
                "url": url,
                "events": events or [],
                "project": self.project_id,
            }

        json_data: dict[str, Any] = {
            "url": url,
            "project": self.project_id,
        }
        if events:
            json_data["events"] = events
        if secret:
            json_data["secret"] = secret

        result = self.request(
            "POST",
            f"api/workspaces/{self.workspace_slug}/projects/{self.project_id}/webhooks/",
            json=json_data,
        )
        assert isinstance(result, dict)
        return result

    def get_webhook(self, webhook_id: str) -> dict[str, Any]:
        """
        Get a webhook by ID.

        Args:
            webhook_id: Webhook ID to retrieve

        Returns:
            Webhook data
        """
        result = self.request(
            "GET",
            f"api/workspaces/{self.workspace_slug}/projects/{self.project_id}/webhooks/{webhook_id}/",
        )
        assert isinstance(result, dict)
        return result

    def list_webhooks(self) -> list[dict[str, Any]]:
        """
        List all webhooks for the project.

        Returns:
            List of webhook subscriptions
        """
        result = self.request(
            "GET",
            f"api/workspaces/{self.workspace_slug}/projects/{self.project_id}/webhooks/",
        )
        assert isinstance(result, list)
        return result

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
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would update webhook {webhook_id}")
            return {"id": webhook_id}

        json_data: dict[str, Any] = {}
        if url is not None:
            json_data["url"] = url
        if events is not None:
            json_data["events"] = events
        if secret is not None:
            json_data["secret"] = secret
        if is_active is not None:
            json_data["is_active"] = is_active

        if not json_data:
            return self.get_webhook(webhook_id)

        result = self.request(
            "PATCH",
            f"api/workspaces/{self.workspace_slug}/projects/{self.project_id}/webhooks/{webhook_id}/",
            json=json_data,
        )
        assert isinstance(result, dict)
        return result

    def delete_webhook(self, webhook_id: str) -> bool:
        """
        Delete a webhook subscription.

        Args:
            webhook_id: Webhook ID to delete

        Returns:
            True if successful
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would delete webhook {webhook_id}")
            return True

        self.request(
            "DELETE",
            f"api/workspaces/{self.workspace_slug}/projects/{self.project_id}/webhooks/{webhook_id}/",
        )
        return True

    # -------------------------------------------------------------------------
    # Attachments API
    # -------------------------------------------------------------------------

    def get_issue_attachments(self, issue_id: str) -> list[dict[str, Any]]:
        """
        Get all attachments for an issue.

        Args:
            issue_id: Issue ID

        Returns:
            List of attachment dictionaries with id, name, url, etc.
        """
        result = self.request(
            "GET",
            f"api/workspaces/{self.workspace_slug}/projects/{self.project_id}/issues/{issue_id}/attachments/",
        )
        assert isinstance(result, list)
        return result

    def upload_issue_attachment(
        self,
        issue_id: str,
        file_path: str,
        name: str | None = None,
    ) -> dict[str, Any]:
        """
        Upload a file attachment to an issue.

        Plane.so attachments use multipart/form-data.

        Args:
            issue_id: Issue ID
            file_path: Path to file to upload
            name: Optional attachment name (defaults to filename)

        Returns:
            Attachment information dictionary

        Raises:
            NotFoundError: If file doesn't exist
            IssueTrackerError: On upload failure
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would upload attachment {file_path} to issue {issue_id}")
            return {"id": "attachment:dry-run", "name": name or file_path}

        from pathlib import Path

        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            raise NotFoundError(f"File not found: {file_path}")

        attachment_name = name or file_path_obj.name
        url = f"{self.api_url}/api/workspaces/{self.workspace_slug}/projects/{self.project_id}/issues/{issue_id}/attachments/"

        # Apply rate limiting
        if self._rate_limiter is not None:
            self._rate_limiter.acquire()

        try:
            # Open file and upload using multipart/form-data
            with open(file_path_obj, "rb") as file_handle:
                files = {"file": (attachment_name, file_handle, "application/octet-stream")}

                # Remove Content-Type header for multipart upload
                headers = dict(self._session.headers)
                headers.pop("Content-Type", None)

                response = self._session.post(
                    url,
                    files=files,
                    headers=headers,
                    timeout=self.timeout,
                )

                # Update rate limiter
                if self._rate_limiter is not None:
                    self._rate_limiter.update_from_response(response)

                if response.status_code == 401:
                    raise AuthenticationError("Plane authentication failed. Check your API token.")

                if response.status_code == 403:
                    raise PermissionError("Permission denied")

                if response.status_code == 404:
                    raise NotFoundError(f"Issue not found: {issue_id}")

                if not response.ok:
                    error_text = response.text[:500] if response.text else ""
                    raise IssueTrackerError(
                        f"Plane attachment upload error {response.status_code}: {error_text}"
                    )

                try:
                    result = response.json()
                    assert isinstance(result, dict)
                    return result
                except ValueError:
                    return {"id": "unknown", "name": attachment_name}

        except requests.exceptions.RequestException as e:
            raise IssueTrackerError(f"Failed to upload attachment: {e}", cause=e)

    def delete_issue_attachment(self, issue_id: str, attachment_id: str) -> bool:
        """
        Delete an attachment from an issue.

        Args:
            issue_id: Issue ID
            attachment_id: Attachment ID to delete

        Returns:
            True if successful

        Raises:
            IssueTrackerError: On deletion failure
        """
        if self.dry_run:
            self.logger.info(
                f"[DRY-RUN] Would delete attachment {attachment_id} from issue {issue_id}"
            )
            return True

        url = f"{self.api_url}/api/workspaces/{self.workspace_slug}/projects/{self.project_id}/issues/{issue_id}/attachments/{attachment_id}/"

        # Apply rate limiting
        if self._rate_limiter is not None:
            self._rate_limiter.acquire()

        try:
            response = self._session.delete(url, timeout=self.timeout)

            # Update rate limiter
            if self._rate_limiter is not None:
                self._rate_limiter.update_from_response(response)

            if response.status_code == 401:
                raise AuthenticationError("Plane authentication failed. Check your API token.")

            if response.status_code == 403:
                raise PermissionError("Permission denied")

            if response.status_code == 404:
                raise NotFoundError(f"Attachment not found: {attachment_id}")

            if not response.ok:
                error_text = response.text[:500] if response.text else ""
                raise IssueTrackerError(
                    f"Plane attachment deletion error {response.status_code}: {error_text}"
                )

            return True

        except requests.exceptions.RequestException as e:
            raise IssueTrackerError(f"Failed to delete attachment: {e}", cause=e)

    def download_attachment(
        self,
        issue_id: str,
        attachment_id: str,
        download_path: str,
    ) -> bool:
        """
        Download an attachment to a local file.

        Args:
            issue_id: Issue ID
            attachment_id: Attachment ID
            download_path: Local path to save the file

        Returns:
            True if successful

        Raises:
            NotFoundError: If attachment doesn't exist
            IssueTrackerError: On download failure
        """
        # Get attachment info to find the download URL
        attachments = self.get_issue_attachments(issue_id)
        attachment_url: str | None = None
        attachment_name: str = "attachment"

        for att in attachments:
            if att.get("id") == attachment_id:
                attachment_url = att.get("url") or att.get("download_url")
                attachment_name = att.get("name", "attachment") or "attachment"
                break

        if not attachment_url:
            raise NotFoundError(f"Attachment not found: {attachment_id}")

        from pathlib import Path

        download_path_obj = Path(download_path)
        if download_path_obj.is_dir():
            download_path_obj = download_path_obj / attachment_name

        # Apply rate limiting
        if self._rate_limiter is not None:
            self._rate_limiter.acquire()

        try:
            response = self._session.get(attachment_url, timeout=self.timeout, stream=True)

            # Update rate limiter
            if self._rate_limiter is not None:
                self._rate_limiter.update_from_response(response)

            if not response.ok:
                raise IssueTrackerError(f"Failed to download attachment: {response.status_code}")

            with open(download_path_obj, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            self.logger.info(f"Downloaded attachment to {download_path_obj}")
            return True

        except requests.exceptions.RequestException as e:
            raise IssueTrackerError(f"Failed to download attachment: {e}", cause=e)

    # -------------------------------------------------------------------------
    # Resource Cleanup
    # -------------------------------------------------------------------------

    def close(self) -> None:
        """Close the client and release resources."""
        self._session.close()
        self.logger.debug("Closed HTTP session")

    def __enter__(self) -> "PlaneApiClient":
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
