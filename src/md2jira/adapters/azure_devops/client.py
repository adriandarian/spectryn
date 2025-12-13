"""
Azure DevOps API Client - REST client for Azure DevOps Work Items API.

This handles the raw HTTP communication with Azure DevOps.
The AzureDevOpsAdapter uses this to implement the IssueTrackerPort.

Azure DevOps API Documentation:
https://learn.microsoft.com/en-us/rest/api/azure/devops/
"""

import base64
import logging
import random
import threading
import time
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter

from ...core.ports.issue_tracker import (
    IssueTrackerError,
    AuthenticationError,
    NotFoundError,
    PermissionError,
    RateLimitError,
    TransientError,
)


# HTTP status codes that should trigger retry
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class AzureDevOpsRateLimiter:
    """
    Rate limiter for Azure DevOps API.
    
    Azure DevOps has varying rate limits based on the service and tier.
    Default limits are fairly generous but we use conservative defaults.
    """
    
    def __init__(
        self,
        requests_per_second: float = 10.0,
        burst_size: int = 20,
    ):
        """
        Initialize the rate limiter.
        
        Args:
            requests_per_second: Maximum sustained request rate.
            burst_size: Maximum tokens in bucket (allows short bursts).
        """
        self.requests_per_second = requests_per_second
        self.burst_size = max(1, burst_size)
        
        # Token bucket state
        self._tokens = float(burst_size)
        self._last_update = time.monotonic()
        self._lock = threading.Lock()
        
        # Rate limit tracking from headers
        self._retry_after: float | None = None
        
        # Statistics
        self._total_requests = 0
        self._total_wait_time = 0.0
        
        self.logger = logging.getLogger("AzureDevOpsRateLimiter")
    
    def acquire(self, timeout: float | None = None) -> bool:
        """
        Acquire a token, waiting if necessary.
        
        Args:
            timeout: Maximum time to wait in seconds.
            
        Returns:
            True if token was acquired, False if timeout was reached.
        """
        start_time = time.monotonic()
        
        while True:
            with self._lock:
                # Check if we need to wait due to rate limit response
                if self._retry_after is not None:
                    wait_time = self._retry_after - time.time()
                    if wait_time > 0:
                        self.logger.warning(f"Rate limit: waiting {wait_time:.1f}s")
                        self._total_wait_time += wait_time
                        self._lock.release()
                        try:
                            time.sleep(wait_time)
                        finally:
                            self._lock.acquire()
                        self._retry_after = None
                        continue
                    self._retry_after = None
                
                self._refill_tokens()
                
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    self._total_requests += 1
                    return True
                
                tokens_needed = 1.0 - self._tokens
                wait_time = tokens_needed / self.requests_per_second
            
            if timeout is not None:
                elapsed = time.monotonic() - start_time
                if elapsed >= timeout:
                    return False
                wait_time = min(wait_time, timeout - elapsed)
            
            if wait_time > 0.01:
                self.logger.debug(f"Rate limit: waiting {wait_time:.3f}s for token")
            
            self._total_wait_time += wait_time
            time.sleep(wait_time)
    
    def _refill_tokens(self) -> None:
        """Refill tokens based on elapsed time. Must be called with lock held."""
        now = time.monotonic()
        elapsed = now - self._last_update
        self._last_update = now
        
        new_tokens = elapsed * self.requests_per_second
        self._tokens = min(self.burst_size, self._tokens + new_tokens)
    
    def update_from_response(self, response: requests.Response) -> None:
        """Update rate limiter based on Azure DevOps response headers."""
        with self._lock:
            # Check for Retry-After header
            retry_after = response.headers.get("Retry-After")
            if retry_after is not None:
                try:
                    self._retry_after = time.time() + float(retry_after)
                except ValueError:
                    pass
            
            if response.status_code == 429:
                old_rate = self.requests_per_second
                self.requests_per_second = max(0.5, self.requests_per_second * 0.5)
                self.logger.warning(
                    f"Rate limited, reducing rate from "
                    f"{old_rate:.1f} to {self.requests_per_second:.1f} req/s"
                )
    
    @property
    def stats(self) -> dict[str, Any]:
        """Get rate limiter statistics."""
        with self._lock:
            return {
                "total_requests": self._total_requests,
                "total_wait_time": self._total_wait_time,
                "average_wait_time": (
                    self._total_wait_time / self._total_requests
                    if self._total_requests > 0 else 0.0
                ),
                "available_tokens": self._tokens,
                "requests_per_second": self.requests_per_second,
            }
    
    def reset(self) -> None:
        """Reset the rate limiter to initial state."""
        with self._lock:
            self._tokens = float(self.burst_size)
            self._last_update = time.monotonic()
            self._total_requests = 0
            self._total_wait_time = 0.0
            self._retry_after = None


class AzureDevOpsApiClient:
    """
    Low-level Azure DevOps REST API client.
    
    Handles authentication, request/response, rate limiting, and error handling.
    
    Features:
    - Personal Access Token (PAT) authentication
    - Automatic retry with exponential backoff
    - Rate limiting
    - Connection pooling
    """
    
    API_VERSION = "7.1"
    
    # Default retry configuration
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_INITIAL_DELAY = 1.0
    DEFAULT_MAX_DELAY = 60.0
    DEFAULT_BACKOFF_FACTOR = 2.0
    DEFAULT_JITTER = 0.1
    
    # Default rate limiting
    DEFAULT_REQUESTS_PER_SECOND = 10.0
    DEFAULT_BURST_SIZE = 20
    
    # Connection pool settings
    DEFAULT_TIMEOUT = 30.0
    
    def __init__(
        self,
        organization: str,
        project: str,
        pat: str,
        base_url: str = "https://dev.azure.com",
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
        Initialize the Azure DevOps client.
        
        Args:
            organization: Azure DevOps organization name
            project: Project name
            pat: Personal Access Token
            base_url: Azure DevOps base URL
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
        self.organization = organization
        self.project = project
        self.pat = pat
        self.base_url = base_url.rstrip("/")
        self.dry_run = dry_run
        self.timeout = timeout
        self.logger = logging.getLogger("AzureDevOpsApiClient")
        
        # Retry configuration
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.jitter = jitter
        
        # Rate limiting
        self._rate_limiter: AzureDevOpsRateLimiter | None = None
        if requests_per_second is not None and requests_per_second > 0:
            self._rate_limiter = AzureDevOpsRateLimiter(
                requests_per_second=requests_per_second,
                burst_size=burst_size,
            )
        
        # Build auth header (Basic auth with PAT)
        auth_string = base64.b64encode(f":{pat}".encode()).decode()
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Basic {auth_string}",
        }
        
        # Configure session with connection pooling
        self._session = requests.Session()
        self._session.headers.update(self.headers)
        
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10)
        self._session.mount("https://", adapter)
        
        # Cache
        self._current_user: Optional[dict] = None
        self._work_item_types: dict[str, dict] = {}
        self._team_settings: Optional[dict] = None
    
    # -------------------------------------------------------------------------
    # Core Request Methods
    # -------------------------------------------------------------------------
    
    def _build_url(self, endpoint: str, area: str = "wit") -> str:
        """
        Build the full API URL.
        
        Args:
            endpoint: API endpoint path
            area: API area (wit, core, etc.)
        """
        if endpoint.startswith("http"):
            return endpoint
        
        # Work Item Tracking API
        if area == "wit":
            return f"{self.base_url}/{self.organization}/{self.project}/_apis/wit/{endpoint}"
        # Core API (projects, teams)
        elif area == "core":
            return f"{self.base_url}/{self.organization}/_apis/{endpoint}"
        # Generic
        else:
            return f"{self.base_url}/{self.organization}/{self.project}/_apis/{endpoint}"
    
    def request(
        self,
        method: str,
        endpoint: str,
        area: str = "wit",
        **kwargs: Any,
    ) -> dict[str, Any] | list[Any]:
        """
        Make an authenticated request to Azure DevOps API.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            area: API area (wit, core, etc.)
            **kwargs: Additional arguments for requests
            
        Returns:
            JSON response (dict or list)
        """
        url = self._build_url(endpoint, area)
        
        # Add API version
        params = kwargs.get("params", {})
        params["api-version"] = self.API_VERSION
        kwargs["params"] = params
        
        last_exception: Exception | None = None
        
        for attempt in range(self.max_retries + 1):
            if self._rate_limiter is not None:
                self._rate_limiter.acquire()
            
            try:
                if "timeout" not in kwargs:
                    kwargs["timeout"] = self.timeout
                    
                response = self._session.request(method, url, **kwargs)
                
                if self._rate_limiter is not None:
                    self._rate_limiter.update_from_response(response)
                
                if response.status_code in RETRYABLE_STATUS_CODES:
                    delay = self._calculate_delay(attempt)
                    
                    if attempt < self.max_retries:
                        self.logger.warning(
                            f"Retryable error {response.status_code}, "
                            f"attempt {attempt + 1}/{self.max_retries + 1}, "
                            f"retrying in {delay:.2f}s"
                        )
                        time.sleep(delay)
                        continue
                    
                    if response.status_code == 429:
                        raise RateLimitError(
                            "Azure DevOps rate limit exceeded",
                            retry_after=int(delay),
                        )
                    else:
                        raise TransientError(
                            f"Azure DevOps server error {response.status_code}"
                        )
                
                return self._handle_response(response, endpoint)
                
            except requests.exceptions.ConnectionError as e:
                last_exception = e
                if attempt < self.max_retries:
                    delay = self._calculate_delay(attempt)
                    self.logger.warning(f"Connection error, retrying in {delay:.2f}s")
                    time.sleep(delay)
                    continue
                raise IssueTrackerError(f"Connection failed: {e}", cause=e)
                
            except requests.exceptions.Timeout as e:
                last_exception = e
                if attempt < self.max_retries:
                    delay = self._calculate_delay(attempt)
                    self.logger.warning(f"Timeout, retrying in {delay:.2f}s")
                    time.sleep(delay)
                    continue
                raise IssueTrackerError(f"Request timed out: {e}", cause=e)
        
        raise IssueTrackerError(
            f"Request failed after {self.max_retries + 1} attempts",
            cause=last_exception
        )
    
    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay before next retry using exponential backoff."""
        base_delay = self.initial_delay * (self.backoff_factor ** attempt)
        base_delay = min(base_delay, self.max_delay)
        
        jitter_range = base_delay * self.jitter
        jitter_value = random.uniform(-jitter_range, jitter_range)
        
        return max(0, base_delay + jitter_value)
    
    def get(self, endpoint: str, area: str = "wit", **kwargs: Any) -> dict[str, Any] | list[Any]:
        """Perform a GET request."""
        return self.request("GET", endpoint, area, **kwargs)
    
    def post(
        self,
        endpoint: str,
        area: str = "wit",
        json: Optional[Any] = None,
        **kwargs: Any,
    ) -> dict[str, Any] | list[Any]:
        """Perform a POST request. Respects dry_run mode."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would POST to {endpoint}")
            return {}
        return self.request("POST", endpoint, area, json=json, **kwargs)
    
    def patch(
        self,
        endpoint: str,
        area: str = "wit",
        json: Optional[Any] = None,
        **kwargs: Any,
    ) -> dict[str, Any] | list[Any]:
        """Perform a PATCH request. Respects dry_run mode."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would PATCH {endpoint}")
            return {}
        
        # Azure DevOps uses application/json-patch+json for updates
        headers = kwargs.pop("headers", {})
        headers["Content-Type"] = "application/json-patch+json"
        
        return self.request("PATCH", endpoint, area, json=json, headers=headers, **kwargs)
    
    def delete(self, endpoint: str, area: str = "wit", **kwargs: Any) -> dict[str, Any] | list[Any]:
        """Perform a DELETE request. Respects dry_run mode."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would DELETE {endpoint}")
            return {}
        return self.request("DELETE", endpoint, area, **kwargs)
    
    def _handle_response(
        self,
        response: requests.Response,
        endpoint: str
    ) -> dict[str, Any] | list[Any]:
        """Handle API response and convert errors."""
        if response.status_code == 401:
            raise AuthenticationError(
                "Azure DevOps authentication failed. Check your PAT."
            )
        
        if response.status_code == 403:
            raise PermissionError(
                f"Permission denied for {endpoint}",
                issue_key=endpoint
            )
        
        if response.status_code == 404:
            raise NotFoundError(
                f"Not found: {endpoint}",
                issue_key=endpoint
            )
        
        if not response.ok:
            raise IssueTrackerError(
                f"Azure DevOps API error {response.status_code}: {response.text[:500]}"
            )
        
        if response.text:
            return response.json()
        return {}
    
    # -------------------------------------------------------------------------
    # Connection & User
    # -------------------------------------------------------------------------
    
    def get_connection_data(self) -> dict[str, Any]:
        """Get connection data to verify authentication."""
        if self._current_user is None:
            result = self.get("connectionData", area="core")
            if isinstance(result, dict):
                self._current_user = result.get("authenticatedUser", {})
        return self._current_user or {}
    
    def get_current_user_id(self) -> str:
        """Get the current user's ID."""
        user = self.get_connection_data()
        return user.get("id", "")
    
    def get_current_user_name(self) -> str:
        """Get the current user's display name."""
        user = self.get_connection_data()
        return user.get("providerDisplayName", "")
    
    def test_connection(self) -> bool:
        """Test if the API connection and credentials are valid."""
        try:
            self.get_connection_data()
            return True
        except IssueTrackerError:
            return False
    
    @property
    def is_connected(self) -> bool:
        """Check if the client has successfully connected."""
        return self._current_user is not None
    
    # -------------------------------------------------------------------------
    # Work Items API
    # -------------------------------------------------------------------------
    
    def get_work_item(
        self,
        work_item_id: int,
        expand: str | None = "All",
    ) -> dict[str, Any]:
        """
        Get a work item by ID.
        
        Args:
            work_item_id: Work item ID
            expand: Fields to expand (None, Relations, Fields, Links, All)
        """
        params = {}
        if expand:
            params["$expand"] = expand
        
        result = self.get(f"workitems/{work_item_id}", params=params)
        return result if isinstance(result, dict) else {}
    
    def get_work_items(
        self,
        ids: list[int],
        expand: str | None = "All",
    ) -> list[dict[str, Any]]:
        """Get multiple work items by IDs."""
        if not ids:
            return []
        
        params: dict[str, Any] = {"ids": ",".join(str(i) for i in ids)}
        if expand:
            params["$expand"] = expand
        
        result = self.get("workitems", params=params)
        if isinstance(result, dict):
            return result.get("value", [])
        return result if isinstance(result, list) else []
    
    def create_work_item(
        self,
        work_item_type: str,
        title: str,
        description: str | None = None,
        state: str | None = None,
        assigned_to: str | None = None,
        parent_id: int | None = None,
        story_points: float | None = None,
        area_path: str | None = None,
        iteration_path: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Create a new work item.
        
        Args:
            work_item_type: Type (Epic, Feature, User Story, Task, Bug, etc.)
            title: Work item title
            description: HTML description
            state: Initial state
            assigned_to: Assignee email or display name
            parent_id: Parent work item ID for hierarchy
            story_points: Story points estimate
            area_path: Area path (defaults to project)
            iteration_path: Iteration/sprint path
            tags: List of tags
        """
        # Build JSON Patch document
        operations = [
            {"op": "add", "path": "/fields/System.Title", "value": title},
        ]
        
        if description:
            operations.append({
                "op": "add",
                "path": "/fields/System.Description",
                "value": description,
            })
        
        if state:
            operations.append({
                "op": "add",
                "path": "/fields/System.State",
                "value": state,
            })
        
        if assigned_to:
            operations.append({
                "op": "add",
                "path": "/fields/System.AssignedTo",
                "value": assigned_to,
            })
        
        if area_path:
            operations.append({
                "op": "add",
                "path": "/fields/System.AreaPath",
                "value": area_path,
            })
        
        if iteration_path:
            operations.append({
                "op": "add",
                "path": "/fields/System.IterationPath",
                "value": iteration_path,
            })
        
        if story_points is not None:
            # Story Points field varies by process template
            operations.append({
                "op": "add",
                "path": "/fields/Microsoft.VSTS.Scheduling.StoryPoints",
                "value": story_points,
            })
        
        if tags:
            operations.append({
                "op": "add",
                "path": "/fields/System.Tags",
                "value": "; ".join(tags),
            })
        
        if parent_id:
            # Add parent link
            operations.append({
                "op": "add",
                "path": "/relations/-",
                "value": {
                    "rel": "System.LinkTypes.Hierarchy-Reverse",
                    "url": f"{self.base_url}/{self.organization}/{self.project}/_apis/wit/workItems/{parent_id}",
                },
            })
        
        result = self.patch(f"workitems/${work_item_type}", json=operations)
        return result if isinstance(result, dict) else {}
    
    def update_work_item(
        self,
        work_item_id: int,
        title: str | None = None,
        description: str | None = None,
        state: str | None = None,
        assigned_to: str | None = None,
        story_points: float | None = None,
        area_path: str | None = None,
        iteration_path: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Update an existing work item."""
        operations = []
        
        if title is not None:
            operations.append({
                "op": "replace",
                "path": "/fields/System.Title",
                "value": title,
            })
        
        if description is not None:
            operations.append({
                "op": "replace",
                "path": "/fields/System.Description",
                "value": description,
            })
        
        if state is not None:
            operations.append({
                "op": "replace",
                "path": "/fields/System.State",
                "value": state,
            })
        
        if assigned_to is not None:
            operations.append({
                "op": "replace",
                "path": "/fields/System.AssignedTo",
                "value": assigned_to,
            })
        
        if story_points is not None:
            operations.append({
                "op": "replace",
                "path": "/fields/Microsoft.VSTS.Scheduling.StoryPoints",
                "value": story_points,
            })
        
        if area_path is not None:
            operations.append({
                "op": "replace",
                "path": "/fields/System.AreaPath",
                "value": area_path,
            })
        
        if iteration_path is not None:
            operations.append({
                "op": "replace",
                "path": "/fields/System.IterationPath",
                "value": iteration_path,
            })
        
        if tags is not None:
            operations.append({
                "op": "replace",
                "path": "/fields/System.Tags",
                "value": "; ".join(tags),
            })
        
        if not operations:
            return {}
        
        result = self.patch(f"workitems/{work_item_id}", json=operations)
        return result if isinstance(result, dict) else {}
    
    def get_work_item_children(self, work_item_id: int) -> list[dict[str, Any]]:
        """Get child work items of a parent."""
        work_item = self.get_work_item(work_item_id, expand="Relations")
        relations = work_item.get("relations", [])
        
        child_ids = []
        for rel in relations:
            if rel.get("rel") == "System.LinkTypes.Hierarchy-Forward":
                # Extract ID from URL
                url = rel.get("url", "")
                if "/workItems/" in url:
                    child_id = url.split("/workItems/")[-1]
                    try:
                        child_ids.append(int(child_id))
                    except ValueError:
                        pass
        
        if not child_ids:
            return []
        
        return self.get_work_items(child_ids)
    
    def add_comment(self, work_item_id: int, text: str) -> dict[str, Any]:
        """Add a comment to a work item."""
        result = self.post(
            f"workitems/{work_item_id}/comments",
            json={"text": text},
        )
        return result if isinstance(result, dict) else {}
    
    def get_comments(self, work_item_id: int) -> list[dict[str, Any]]:
        """Get all comments on a work item."""
        result = self.get(f"workitems/{work_item_id}/comments")
        if isinstance(result, dict):
            return result.get("comments", [])
        return []
    
    # -------------------------------------------------------------------------
    # WIQL (Work Item Query Language)
    # -------------------------------------------------------------------------
    
    def query_work_items(
        self,
        wiql: str,
        top: int = 200,
    ) -> list[dict[str, Any]]:
        """
        Execute a WIQL query and return work items.
        
        Args:
            wiql: WIQL query string
            top: Maximum results
        """
        # Execute query to get IDs
        result = self.post(
            "wiql",
            json={"query": wiql},
            params={"$top": top},
        )
        
        if not isinstance(result, dict):
            return []
        
        work_items = result.get("workItems", [])
        if not work_items:
            return []
        
        # Get full work item data
        ids = [wi["id"] for wi in work_items[:top]]
        return self.get_work_items(ids)
    
    def search_work_items(
        self,
        text: str | None = None,
        work_item_type: str | None = None,
        state: str | None = None,
        assigned_to: str | None = None,
        top: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Search for work items using WIQL.
        
        Args:
            text: Text to search in title
            work_item_type: Filter by type
            state: Filter by state
            assigned_to: Filter by assignee
            top: Maximum results
        """
        conditions = [f"[System.TeamProject] = '{self.project}'"]
        
        if text:
            conditions.append(f"[System.Title] Contains '{text}'")
        if work_item_type:
            conditions.append(f"[System.WorkItemType] = '{work_item_type}'")
        if state:
            conditions.append(f"[System.State] = '{state}'")
        if assigned_to:
            conditions.append(f"[System.AssignedTo] = '{assigned_to}'")
        
        wiql = f"SELECT [System.Id] FROM WorkItems WHERE {' AND '.join(conditions)} ORDER BY [System.Id] DESC"
        
        return self.query_work_items(wiql, top)
    
    # -------------------------------------------------------------------------
    # Work Item Types & States
    # -------------------------------------------------------------------------
    
    def get_work_item_types(self) -> list[dict[str, Any]]:
        """Get all work item types for the project."""
        result = self.get("workitemtypes")
        if isinstance(result, dict):
            return result.get("value", [])
        return result if isinstance(result, list) else []
    
    def get_work_item_type(self, type_name: str) -> dict[str, Any]:
        """Get a specific work item type."""
        if type_name in self._work_item_types:
            return self._work_item_types[type_name]
        
        result = self.get(f"workitemtypes/{type_name}")
        if isinstance(result, dict):
            self._work_item_types[type_name] = result
            return result
        return {}
    
    def get_work_item_states(self, type_name: str) -> list[dict[str, Any]]:
        """Get available states for a work item type."""
        result = self.get(f"workitemtypes/{type_name}/states")
        if isinstance(result, dict):
            return result.get("value", [])
        return result if isinstance(result, list) else []
    
    # -------------------------------------------------------------------------
    # Resource Cleanup
    # -------------------------------------------------------------------------
    
    def close(self) -> None:
        """Close the client and release resources."""
        self._session.close()
        self.logger.debug("Closed HTTP session")
    
    def __enter__(self) -> "AzureDevOpsApiClient":
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

