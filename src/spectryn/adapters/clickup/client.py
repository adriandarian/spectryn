"""
ClickUp API Client - REST client for ClickUp API v2.

This handles the raw HTTP/REST communication with ClickUp.
The ClickUpAdapter uses this to implement the IssueTrackerPort.

ClickUp API Documentation: https://clickup.com/api
"""

import logging
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter

from spectryn.adapters.async_base import (
    RETRYABLE_STATUS_CODES,
    calculate_delay,
)
from spectryn.core.ports.issue_tracker import (
    AuthenticationError,
    IssueTrackerError,
    NotFoundError,
    PermissionError,
    RateLimitError,
    TransientError,
)


class ClickUpRateLimiter:
    """
    Rate limiter for ClickUp API.

    ClickUp rate limits: 100 requests per minute per API token.
    """

    def __init__(self, requests_per_minute: float = 100.0):
        """
        Initialize rate limiter.

        Args:
            requests_per_minute: Maximum requests per minute
        """
        self.requests_per_minute = requests_per_minute
        self.request_times: list[float] = []
        self.logger = logging.getLogger("ClickUpRateLimiter")

    def acquire(self) -> None:
        """Acquire permission to make a request."""
        now = time.time()

        # Remove requests older than 60 seconds
        self.request_times = [t for t in self.request_times if now - t < 60.0]

        # If we're at the limit, wait
        if len(self.request_times) >= self.requests_per_minute:
            oldest_request = min(self.request_times)
            wait_time = 60.0 - (now - oldest_request) + 0.1  # Add small buffer
            if wait_time > 0:
                self.logger.debug(f"Rate limit reached, waiting {wait_time:.2f}s")
                time.sleep(wait_time)
                # Clean up again after waiting
                now = time.time()
                self.request_times = [t for t in self.request_times if now - t < 60.0]

        self.request_times.append(time.time())

    def update_from_response(self, response: requests.Response) -> None:
        """Update rate limiter state from response headers."""
        # ClickUp doesn't expose rate limit headers consistently
        # We rely on our own tracking


class ClickUpApiClient:
    """
    Low-level ClickUp REST API v2 client.

    Handles authentication, request/response, rate limiting, and error handling.

    Features:
    - REST API v2 with JSON responses
    - API token authentication
    - Automatic retry with exponential backoff
    - Rate limiting with awareness of ClickUp's limits (100 req/min)
    - Connection pooling
    """

    API_URL = "https://api.clickup.com/api/v2"

    # Default retry configuration
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_INITIAL_DELAY = 1.0
    DEFAULT_MAX_DELAY = 60.0
    DEFAULT_BACKOFF_FACTOR = 2.0
    DEFAULT_JITTER = 0.1

    # Default rate limiting (conservative for ClickUp)
    DEFAULT_REQUESTS_PER_MINUTE = 90.0  # Under 100 limit
    DEFAULT_BURST_SIZE = 10

    # Connection pool settings
    DEFAULT_TIMEOUT = 30.0

    def __init__(
        self,
        api_token: str,
        api_url: str = API_URL,
        dry_run: bool = True,
        max_retries: int = DEFAULT_MAX_RETRIES,
        initial_delay: float = DEFAULT_INITIAL_DELAY,
        max_delay: float = DEFAULT_MAX_DELAY,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
        jitter: float = DEFAULT_JITTER,
        requests_per_minute: float | None = DEFAULT_REQUESTS_PER_MINUTE,
        burst_size: int = DEFAULT_BURST_SIZE,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        """
        Initialize the ClickUp client.

        Args:
            api_token: ClickUp API token
            api_url: ClickUp API URL
            dry_run: If True, don't make write operations
            max_retries: Maximum retry attempts for transient failures
            initial_delay: Initial retry delay in seconds
            max_delay: Maximum retry delay in seconds
            backoff_factor: Multiplier for exponential backoff
            jitter: Random jitter factor (0.1 = 10%)
            requests_per_minute: Maximum request rate (None to disable)
            burst_size: Maximum burst capacity
            timeout: Request timeout in seconds
        """
        self.api_token = api_token
        self.api_url = api_url
        self.dry_run = dry_run
        self.timeout = timeout
        self.logger = logging.getLogger("ClickUpApiClient")

        # Retry configuration
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.jitter = jitter

        # Rate limiting
        self._rate_limiter: ClickUpRateLimiter | None = None
        if requests_per_minute is not None and requests_per_minute > 0:
            self._rate_limiter = ClickUpRateLimiter(
                requests_per_minute=requests_per_minute,
            )

        # Headers for ClickUp API
        self.headers = {
            "Authorization": api_token,
            "Content-Type": "application/json",
        }

        # Configure session with connection pooling
        self._session = requests.Session()
        self._session.headers.update(self.headers)

        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10)
        self._session.mount("https://", adapter)

        # Cache
        self._user: dict | None = None
        self._spaces_cache: dict[str, dict] = {}
        self._folders_cache: dict[str, dict] = {}
        self._lists_cache: dict[str, dict] = {}
        self._statuses_cache: dict[str, list[dict]] = {}

    # -------------------------------------------------------------------------
    # Core HTTP Methods
    # -------------------------------------------------------------------------

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Make an HTTP request to the ClickUp API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (without base URL)
            params: Query parameters
            json_data: JSON body for POST/PUT requests

        Returns:
            JSON response data

        Raises:
            IssueTrackerError: On API errors
        """
        url = f"{self.api_url}/{endpoint.lstrip('/')}"

        last_exception: Exception | None = None

        for attempt in range(self.max_retries + 1):
            if self._rate_limiter is not None:
                self._rate_limiter.acquire()

            try:
                response = self._session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_data,
                    timeout=self.timeout,
                )

                if self._rate_limiter is not None:
                    self._rate_limiter.update_from_response(response)

                if response.status_code in RETRYABLE_STATUS_CODES:
                    delay = calculate_delay(
                        attempt,
                        initial_delay=self.initial_delay,
                        max_delay=self.max_delay,
                        backoff_factor=self.backoff_factor,
                        jitter=self.jitter,
                    )

                    if attempt < self.max_retries:
                        self.logger.warning(
                            f"Retryable error {response.status_code}, "
                            f"attempt {attempt + 1}/{self.max_retries + 1}, "
                            f"retrying in {delay:.2f}s"
                        )
                        time.sleep(delay)
                        continue

                    if response.status_code == 429:
                        retry_after = int(response.headers.get("Retry-After", delay))
                        raise RateLimitError(
                            "ClickUp rate limit exceeded",
                            retry_after=retry_after,
                        )
                    raise TransientError(f"ClickUp server error {response.status_code}")

                return self._handle_response(response)

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
                    self.logger.warning(f"Connection error, retrying in {delay:.2f}s")
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
                    self.logger.warning(f"Timeout, retrying in {delay:.2f}s")
                    time.sleep(delay)
                    continue
                raise IssueTrackerError(f"Request timed out: {e}", cause=e)

        raise IssueTrackerError(
            f"Request failed after {self.max_retries + 1} attempts",
            cause=last_exception,
        )

    def _handle_response(self, response: requests.Response) -> dict[str, Any]:
        """Handle API response and convert errors."""
        if response.status_code == 401:
            raise AuthenticationError("ClickUp authentication failed. Check your API token.")

        if response.status_code == 403:
            raise PermissionError("Permission denied")

        if response.status_code == 404:
            raise NotFoundError("Resource not found")

        if not response.ok:
            error_text = response.text[:500]
            raise IssueTrackerError(f"ClickUp API error {response.status_code}: {error_text}")

        try:
            data = response.json()
        except ValueError:
            raise IssueTrackerError(f"Invalid JSON response: {response.text[:200]}")

        # ClickUp API wraps responses in a 'data' field for some endpoints
        if isinstance(data, dict) and "data" in data:
            return data["data"]  # type: ignore[no-any-return]

        return data  # type: ignore[no-any-return]

    # -------------------------------------------------------------------------
    # User API
    # -------------------------------------------------------------------------

    def get_user(self) -> dict[str, Any]:
        """Get the current authenticated user."""
        if self._user is None:
            data = self._request("GET", "/user")
            self._user = data.get("user", {})
        return self._user

    def test_connection(self) -> bool:
        """Test if the API connection and credentials are valid."""
        try:
            self.get_user()
            return True
        except IssueTrackerError:
            return False

    @property
    def is_connected(self) -> bool:
        """Check if the client has successfully connected."""
        return self._user is not None

    # -------------------------------------------------------------------------
    # Spaces API
    # -------------------------------------------------------------------------

    def get_spaces(self, team_id: str | None = None) -> list[dict[str, Any]]:
        """
        Get all spaces.

        Args:
            team_id: Optional team ID to filter by
        """
        endpoint = "/team" if team_id is None else f"/team/{team_id}/space"
        data = self._request("GET", endpoint)
        return data.get("spaces", [])

    def get_space(self, space_id: str) -> dict[str, Any]:
        """Get a specific space by ID."""
        if space_id in self._spaces_cache:
            return self._spaces_cache[space_id]

        data = self._request("GET", f"/space/{space_id}")
        space = data.get("space", {})
        self._spaces_cache[space_id] = space
        return space

    # -------------------------------------------------------------------------
    # Folders API
    # -------------------------------------------------------------------------

    def get_folders(self, space_id: str) -> list[dict[str, Any]]:
        """Get all folders in a space."""
        if space_id in self._folders_cache:
            return list(self._folders_cache[space_id].values())

        data = self._request("GET", f"/space/{space_id}/folder")
        folders = data.get("folders", [])
        # Cache folders by ID
        self._folders_cache[space_id] = {f["id"]: f for f in folders}
        return folders

    def get_folder(self, folder_id: str) -> dict[str, Any]:
        """Get a specific folder by ID."""
        data = self._request("GET", f"/folder/{folder_id}")
        return data.get("folder", {})

    # -------------------------------------------------------------------------
    # Lists API
    # -------------------------------------------------------------------------

    def get_lists(
        self, folder_id: str | None = None, list_id: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Get lists.

        Args:
            folder_id: Optional folder ID to get lists from
            list_id: Optional specific list ID
        """
        if list_id:
            data = self._request("GET", f"/list/{list_id}")
            return [data.get("list", {})]

        if folder_id:
            data = self._request("GET", f"/folder/{folder_id}/list")
            return data.get("lists", [])

        return []

    def get_list(self, list_id: str) -> dict[str, Any]:
        """Get a specific list by ID."""
        if list_id in self._lists_cache:
            return self._lists_cache[list_id]

        data = self._request("GET", f"/list/{list_id}")
        list_data = data.get("list", {})
        self._lists_cache[list_id] = list_data
        return list_data

    def get_list_statuses(self, list_id: str) -> list[dict[str, Any]]:
        """Get all statuses for a list."""
        if list_id in self._statuses_cache:
            return self._statuses_cache[list_id]

        list_data = self.get_list(list_id)
        statuses = list_data.get("statuses", {}).get("statuses", [])
        self._statuses_cache[list_id] = statuses
        return statuses

    # -------------------------------------------------------------------------
    # Tasks API
    # -------------------------------------------------------------------------

    def get_task(self, task_id: str) -> dict[str, Any]:
        """
        Get a task by ID.

        Args:
            task_id: Task ID
        """
        data = self._request("GET", f"/task/{task_id}")
        task = data.get("task", {})
        if not task:
            raise NotFoundError(f"Task not found: {task_id}")
        return task

    def get_tasks(
        self,
        list_id: str | None = None,
        folder_id: str | None = None,
        space_id: str | None = None,
        archived: bool = False,
        include_closed: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Get tasks.

        Args:
            list_id: Filter by list ID
            folder_id: Filter by folder ID
            space_id: Filter by space ID
            archived: Include archived tasks
            include_closed: Include closed tasks
        """
        params: dict[str, Any] = {
            "archived": str(archived).lower(),
            "include_closed": str(include_closed).lower(),
        }

        if list_id:
            endpoint = f"/list/{list_id}/task"
        elif folder_id:
            endpoint = f"/folder/{folder_id}/task"
        elif space_id:
            endpoint = f"/space/{space_id}/task"
        else:
            raise ValueError("Must provide list_id, folder_id, or space_id")

        data = self._request("GET", endpoint, params=params)
        return data.get("tasks", [])

    def create_task(
        self,
        list_id: str,
        name: str,
        description: str | None = None,
        status: str | None = None,
        priority: int | None = None,
        assignees: list[str] | None = None,
        due_date: int | None = None,
        due_date_time: bool = False,
        parent: str | None = None,
        custom_fields: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Create a new task."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would create task '{name}' in list {list_id}")
            return {"id": "dry-run-task-id", "name": name}

        payload: dict[str, Any] = {
            "name": name,
            "list_id": list_id,
        }

        if description:
            payload["description"] = description
        if status:
            payload["status"] = status
        if priority is not None:
            payload["priority"] = priority
        if assignees:
            payload["assignees"] = assignees
        if due_date:
            payload["due_date"] = due_date
            payload["due_date_time"] = due_date_time
        if parent:
            payload["parent"] = parent
        if custom_fields:
            payload["custom_fields"] = custom_fields

        data = self._request("POST", f"/list/{list_id}/task", json_data=payload)
        return data.get("task", {})

    def update_task(
        self,
        task_id: str,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
        priority: int | None = None,
        assignees: dict[str, list[str]] | None = None,
        due_date: int | None = None,
        due_date_time: bool = False,
        custom_fields: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Update an existing task."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would update task {task_id}")
            return {"id": task_id}

        payload: dict[str, Any] = {}

        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if status is not None:
            payload["status"] = status
        if priority is not None:
            payload["priority"] = priority
        if assignees is not None:
            payload["assignees"] = assignees
        if due_date is not None:
            payload["due_date"] = due_date
            payload["due_date_time"] = due_date_time
        if custom_fields is not None:
            payload["custom_fields"] = custom_fields

        if not payload:
            return {}

        data = self._request("PUT", f"/task/{task_id}", json_data=payload)
        return data.get("task", {})

    # -------------------------------------------------------------------------
    # Subtasks API
    # -------------------------------------------------------------------------

    def get_subtasks(self, task_id: str) -> list[dict[str, Any]]:
        """Get all subtasks for a task."""
        task = self.get_task(task_id)
        return task.get("subtasks", [])

    def create_subtask(
        self,
        list_id: str,
        parent_task_id: str,
        name: str,
        description: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """Create a subtask."""
        return self.create_task(
            list_id=list_id,
            name=name,
            description=description,
            status=status,
            parent=parent_task_id,
        )

    # -------------------------------------------------------------------------
    # Checklists API
    # -------------------------------------------------------------------------

    def get_checklists(self, task_id: str) -> list[dict[str, Any]]:
        """Get all checklists for a task."""
        task = self.get_task(task_id)
        return task.get("checklists", [])

    def create_checklist(self, task_id: str, name: str) -> dict[str, Any]:
        """Create a checklist on a task."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would create checklist '{name}' on task {task_id}")
            return {"id": "dry-run-checklist-id", "name": name}

        payload = {"name": name}
        data = self._request("POST", f"/task/{task_id}/checklist", json_data=payload)
        return data.get("checklist", {})

    def add_checklist_item(
        self,
        checklist_id: str,
        name: str,
        assignee: str | None = None,
        due_date: int | None = None,
    ) -> dict[str, Any]:
        """Add an item to a checklist."""
        if self.dry_run:
            self.logger.info(
                f"[DRY-RUN] Would add checklist item '{name}' to checklist {checklist_id}"
            )
            return {"id": "dry-run-item-id", "name": name}

        payload: dict[str, Any] = {"name": name}
        if assignee:
            payload["assignee"] = assignee
        if due_date:
            payload["due_date"] = due_date

        data = self._request("POST", f"/checklist/{checklist_id}/checklist_item", json_data=payload)
        return data.get("checklist_item", {})

    # -------------------------------------------------------------------------
    # Comments API
    # -------------------------------------------------------------------------

    def get_comments(self, task_id: str) -> list[dict[str, Any]]:
        """Get all comments on a task."""
        data = self._request("GET", f"/task/{task_id}/comment")
        return data.get("comments", [])

    def add_comment(
        self, task_id: str, comment_text: str, assignee: str | None = None
    ) -> dict[str, Any]:
        """Add a comment to a task."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would add comment to task {task_id}")
            return {"id": "dry-run-comment-id", "comment": [{"text": comment_text}]}

        payload: dict[str, Any] = {"comment_text": comment_text}
        if assignee:
            payload["assignee"] = assignee

        data = self._request("POST", f"/task/{task_id}/comment", json_data=payload)
        return data.get("comment", {})

    # -------------------------------------------------------------------------
    # Goals API (for Epics)
    # -------------------------------------------------------------------------

    def get_goals(self, team_id: str) -> list[dict[str, Any]]:
        """Get all goals for a team."""
        data = self._request("GET", f"/team/{team_id}/goal")
        return data.get("goals", [])

    def get_goal(self, goal_id: str) -> dict[str, Any]:
        """Get a specific goal by ID."""
        data = self._request("GET", f"/goal/{goal_id}")
        return data.get("goal", {})

    def create_goal(
        self,
        team_id: str,
        name: str,
        due_date: int | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Create a new goal (epic)."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would create goal '{name}'")
            return {"id": "dry-run-goal-id", "name": name}

        payload: dict[str, Any] = {"name": name}
        if due_date:
            payload["due_date"] = due_date
        if description:
            payload["description"] = description

        data = self._request("POST", f"/team/{team_id}/goal", json_data=payload)
        return data.get("goal", {})

    # -------------------------------------------------------------------------
    # Time Tracking API
    # -------------------------------------------------------------------------

    def get_time_entries(
        self,
        team_id: str,
        start_date: int | None = None,
        end_date: int | None = None,
        assignee: str | None = None,
        include_task_tags: bool = False,
        include_location_names: bool = False,
        space_id: str | None = None,
        folder_id: str | None = None,
        list_id: str | None = None,
        task_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get time entries.

        Args:
            team_id: Team ID
            start_date: Optional start date timestamp (milliseconds)
            end_date: Optional end date timestamp (milliseconds)
            assignee: Optional assignee user ID
            include_task_tags: Include task tags in response
            include_location_names: Include location names in response
            space_id: Optional space ID filter
            folder_id: Optional folder ID filter
            list_id: Optional list ID filter
            task_id: Optional task ID filter

        Returns:
            List of time entries
        """
        params: dict[str, Any] = {}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if assignee:
            params["assignee"] = assignee
        if include_task_tags:
            params["include_task_tags"] = "true"
        if include_location_names:
            params["include_location_names"] = "true"
        if space_id:
            params["space_id"] = space_id
        if folder_id:
            params["folder_id"] = folder_id
        if list_id:
            params["list_id"] = list_id
        if task_id:
            params["task_id"] = task_id

        data = self._request("GET", f"/team/{team_id}/time_entries", params=params)
        return data.get("data", [])

    def get_task_time_entries(self, task_id: str) -> list[dict[str, Any]]:
        """Get all time entries for a specific task."""
        data = self._request("GET", f"/task/{task_id}/time")
        return data.get("data", [])

    def create_time_entry(
        self,
        task_id: str,
        duration: int,
        start: int,
        billable: bool = False,
        description: str | None = None,
        tags: list[dict[str, Any]] | None = None,
        assignee: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a time entry for a task.

        Args:
            task_id: Task ID
            duration: Duration in milliseconds
            start: Start time timestamp (milliseconds)
            billable: Whether the time entry is billable
            description: Optional description
            tags: Optional list of tag objects
            assignee: Optional assignee user ID

        Returns:
            Created time entry
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would create time entry for task {task_id}")
            return {
                "id": "time-entry:dry-run",
                "task": {"id": task_id},
                "duration": duration,
            }

        payload: dict[str, Any] = {
            "duration": duration,
            "start": start,
            "billable": billable,
        }
        if description:
            payload["description"] = description
        if tags:
            payload["tags"] = tags
        if assignee:
            payload["assignee"] = assignee

        data = self._request("POST", f"/task/{task_id}/time", json_data=payload)
        return data.get("data", {})

    def update_time_entry(
        self,
        team_id: str,
        timer_id: str,
        duration: int | None = None,
        start: int | None = None,
        billable: bool | None = None,
        description: str | None = None,
        tags: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Update a time entry.

        Args:
            team_id: Team ID
            timer_id: Time entry ID
            duration: Optional new duration in milliseconds
            start: Optional new start time timestamp
            billable: Optional billable flag
            description: Optional new description
            tags: Optional new tags

        Returns:
            Updated time entry
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would update time entry {timer_id}")
            return {"id": timer_id}

        payload: dict[str, Any] = {}
        if duration is not None:
            payload["duration"] = duration
        if start is not None:
            payload["start"] = start
        if billable is not None:
            payload["billable"] = billable
        if description is not None:
            payload["description"] = description
        if tags is not None:
            payload["tags"] = tags

        if not payload:
            return {}

        data = self._request("PUT", f"/team/{team_id}/time_entries/{timer_id}", json_data=payload)
        return data.get("data", {})

    def delete_time_entry(self, team_id: str, timer_id: str) -> bool:
        """
        Delete a time entry.

        Args:
            team_id: Team ID
            timer_id: Time entry ID

        Returns:
            True if successful
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would delete time entry {timer_id}")
            return True

        self._request("DELETE", f"/team/{team_id}/time_entries/{timer_id}")
        return True

    def get_task_time_stats(self, task_id: str) -> dict[str, Any]:
        """
        Get time tracking statistics for a task.

        Args:
            task_id: Task ID

        Returns:
            Time stats including total time tracked, estimates, etc.
        """
        task = self.get_task(task_id)
        time_tracked = task.get("time_spent", 0)
        time_estimate = task.get("time_estimate", 0)

        # Get all time entries for more detailed stats
        time_entries = self.get_task_time_entries(task_id)
        total_duration = sum(entry.get("duration", 0) for entry in time_entries)

        return {
            "time_spent": time_tracked or total_duration,
            "time_estimate": time_estimate,
            "time_entries_count": len(time_entries),
        }

    # -------------------------------------------------------------------------
    # Dependencies & Relationships API
    # -------------------------------------------------------------------------

    def get_task_dependencies(self, task_id: str) -> list[dict[str, Any]]:
        """
        Get dependencies for a task.

        Args:
            task_id: Task ID

        Returns:
            List of dependency relationships
        """
        task = self.get_task(task_id)
        return task.get("dependencies", [])

    def create_task_dependency(
        self,
        task_id: str,
        depends_on_task_id: str,
        dependency_type: str = "waiting_on",
    ) -> dict[str, Any]:
        """
        Create a dependency relationship between tasks.

        Args:
            task_id: Task that depends on another
            depends_on_task_id: Task that is depended upon
            dependency_type: Type of dependency ('waiting_on' or 'blocked_by')

        Returns:
            Created dependency
        """
        if self.dry_run:
            self.logger.info(
                f"[DRY-RUN] Would create dependency: {task_id} depends on {depends_on_task_id}"
            )
            return {
                "task_id": task_id,
                "depends_on": depends_on_task_id,
                "type": dependency_type,
            }

        payload = {
            "depends_on": depends_on_task_id,
            "type": dependency_type,
        }

        data = self._request("POST", f"/task/{task_id}/dependency", json_data=payload)
        return data.get("data", {})

    def delete_task_dependency(self, task_id: str, depends_on_task_id: str) -> bool:
        """
        Delete a dependency relationship.

        Args:
            task_id: Task ID
            depends_on_task_id: Task ID to remove dependency on

        Returns:
            True if successful
        """
        if self.dry_run:
            self.logger.info(
                f"[DRY-RUN] Would delete dependency: {task_id} -> {depends_on_task_id}"
            )
            return True

        payload = {"depends_on": depends_on_task_id}

        self._request("DELETE", f"/task/{task_id}/dependency", json_data=payload)
        return True

    # -------------------------------------------------------------------------
    # Views API
    # -------------------------------------------------------------------------

    def get_views(
        self,
        team_id: str,
        view_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get views (Board, List, Calendar, etc.) for a team.

        Args:
            team_id: Team ID
            view_type: Optional view type filter ('board', 'list', 'calendar', 'table', 'timeline', 'gantt')

        Returns:
            List of views
        """
        params: dict[str, Any] = {}
        if view_type:
            params["view_type"] = view_type

        data = self._request("GET", f"/team/{team_id}/view", params=params)
        return data.get("views", [])

    def get_view(self, view_id: str) -> dict[str, Any]:
        """Get a specific view by ID."""
        data = self._request("GET", f"/view/{view_id}")
        return data.get("view", {})

    def get_view_tasks(
        self,
        view_id: str,
        page: int = 0,
        order_by: str | None = None,
        reverse: bool = False,
        subtasks: bool = False,
        statuses: list[str] | None = None,
        include_closed: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Get tasks from a view.

        Args:
            view_id: View ID
            page: Page number (default: 0)
            order_by: Optional field to order by
            reverse: Reverse order
            subtasks: Include subtasks
            statuses: Optional list of statuses to filter by
            include_closed: Include closed tasks

        Returns:
            List of tasks in the view
        """
        params: dict[str, Any] = {
            "page": page,
            "reverse": str(reverse).lower(),
            "subtasks": str(subtasks).lower(),
            "include_closed": str(include_closed).lower(),
        }
        if order_by:
            params["order_by"] = order_by
        if statuses:
            params["statuses"] = statuses

        data = self._request("GET", f"/view/{view_id}/task", params=params)
        return data.get("tasks", [])

    # -------------------------------------------------------------------------
    # Webhooks API
    # -------------------------------------------------------------------------

    def create_webhook(
        self,
        team_id: str,
        endpoint: str,
        client_id: str | None = None,
        events: list[str] | None = None,
        task_id: str | None = None,
        list_id: str | None = None,
        folder_id: str | None = None,
        space_id: str | None = None,
        health_check_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a webhook subscription.

        ClickUp webhooks notify when changes occur to tasks, lists, folders, or spaces.
        You can subscribe to specific events or all events.

        Args:
            team_id: Team ID to create webhook for
            endpoint: Webhook URL to receive events
            client_id: Optional client ID for webhook authentication
            events: Optional list of event types (defaults to all events)
            task_id: Optional task ID to watch (for task-specific webhooks)
            list_id: Optional list ID to watch (for list-specific webhooks)
            folder_id: Optional folder ID to watch (for folder-specific webhooks)
            space_id: Optional space ID to watch (for space-specific webhooks)
            health_check_id: Optional health check ID

        Returns:
            Webhook subscription data
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would create webhook for team {team_id}")
            return {
                "id": "webhook:dry-run",
                "team_id": team_id,
                "endpoint": endpoint,
            }

        payload: dict[str, Any] = {
            "endpoint": endpoint,
        }

        if client_id:
            payload["client_id"] = client_id
        if events:
            payload["events"] = events
        if task_id:
            payload["task_id"] = task_id
        if list_id:
            payload["list_id"] = list_id
        if folder_id:
            payload["folder_id"] = folder_id
        if space_id:
            payload["space_id"] = space_id
        if health_check_id:
            payload["health_check_id"] = health_check_id

        data = self._request("POST", f"/team/{team_id}/webhook", json_data=payload)
        return data.get("webhook", {})

    def get_webhook(self, webhook_id: str) -> dict[str, Any]:
        """Get a webhook by ID."""
        data = self._request("GET", f"/webhook/{webhook_id}")
        return data.get("webhook", {})

    def list_webhooks(self, team_id: str) -> list[dict[str, Any]]:
        """
        List all webhooks for a team.

        Args:
            team_id: Team ID to list webhooks for

        Returns:
            List of webhook subscriptions
        """
        data = self._request("GET", f"/team/{team_id}/webhook")
        return data.get("webhooks", [])

    def update_webhook(
        self,
        webhook_id: str,
        endpoint: str | None = None,
        events: list[str] | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """
        Update a webhook subscription.

        Args:
            webhook_id: Webhook ID to update
            endpoint: Optional new webhook URL
            events: Optional new list of event types
            status: Optional status ('active' or 'inactive')

        Returns:
            Updated webhook data
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would update webhook {webhook_id}")
            return {"id": webhook_id}

        payload: dict[str, Any] = {}
        if endpoint is not None:
            payload["endpoint"] = endpoint
        if events is not None:
            payload["events"] = events
        if status is not None:
            payload["status"] = status

        if not payload:
            return self.get_webhook(webhook_id)

        data = self._request("PUT", f"/webhook/{webhook_id}", json_data=payload)
        return data.get("webhook", {})

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

        self._request("DELETE", f"/webhook/{webhook_id}")
        return True

    # -------------------------------------------------------------------------
    # Attachments API
    # -------------------------------------------------------------------------

    def get_task_attachments(self, task_id: str) -> list[dict[str, Any]]:
        """
        Get all attachments for a task.

        Args:
            task_id: Task ID

        Returns:
            List of attachment dictionaries
        """
        # ClickUp returns attachments as part of the task data
        task = self.get_task(task_id)
        attachments = task.get("attachments", [])
        return attachments if isinstance(attachments, list) else []

    def upload_task_attachment(
        self,
        task_id: str,
        file_path: str,
        name: str | None = None,
    ) -> dict[str, Any]:
        """
        Upload a file attachment to a task.

        Args:
            task_id: Task ID
            file_path: Path to file to upload
            name: Optional attachment name (defaults to filename)

        Returns:
            Attachment information dictionary

        Raises:
            NotFoundError: If file doesn't exist
            IssueTrackerError: On upload failure
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would upload attachment {file_path} to task {task_id}")
            return {"id": "attachment:dry-run", "name": name or file_path}

        from pathlib import Path

        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            raise NotFoundError(f"File not found: {file_path}")

        attachment_name = name or file_path_obj.name
        url = f"{self.api_url}/task/{task_id}/attachment"

        # ClickUp uses multipart form upload
        with open(file_path_obj, "rb") as f:
            files = {"attachment": (attachment_name, f)}

            # Remove Content-Type header for multipart upload
            headers = dict(self._session.headers)
            headers.pop("Content-Type", None)

            response = self._session.post(
                url,
                files=files,
                headers=headers,
                timeout=self.timeout,
            )

        if not response.ok:
            raise IssueTrackerError(
                f"Failed to upload attachment: {response.status_code} - {response.text[:500]}"
            )

        try:
            return response.json()
        except ValueError:
            return {"id": "unknown", "name": attachment_name}

    def delete_task_attachment(self, attachment_id: str) -> bool:
        """
        Delete an attachment from a task.

        Args:
            attachment_id: Attachment ID

        Returns:
            True if successful
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would delete attachment {attachment_id}")
            return True

        self._request("DELETE", f"/attachment/{attachment_id}")
        return True

    # -------------------------------------------------------------------------
    # Resource Cleanup
    # -------------------------------------------------------------------------

    def close(self) -> None:
        """Close the client and release resources."""
        self._session.close()
        self.logger.debug("Closed HTTP session")

    def __enter__(self) -> "ClickUpApiClient":
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
