"""
Bitbucket API Client - Low-level HTTP client for Bitbucket REST API v2.

This handles the raw HTTP communication with Bitbucket Cloud and Server.
The BitbucketAdapter uses this to implement the IssueTrackerPort.
"""

import base64
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


# Optional Server client using atlassian-python-api
try:
    from .server_client import (
        ATLASSIAN_API_AVAILABLE,
        BitbucketServerClient,
        is_server_url,
    )
except ImportError:
    ATLASSIAN_API_AVAILABLE = False
    BitbucketServerClient = None  # type: ignore[assignment, misc]

    def is_server_url(url: str) -> bool:
        """Fallback: determine if URL is Server based on pattern."""
        url_lower = url.lower()
        return "/rest/api" in url_lower or "api.bitbucket.org" not in url_lower


class BitbucketApiClient:
    """
    Low-level Bitbucket REST API v2 client.

    Handles authentication, request/response, rate limiting, and error handling.
    Supports both Bitbucket Cloud and Bitbucket Server (self-hosted).

    Features:
    - Basic Auth with App Password (Cloud) or Personal Access Token (Server)
    - Automatic retry with exponential backoff for transient failures
    - Rate limiting aware of Bitbucket's rate limits
    - Connection pooling for performance
    """

    API_VERSION = "2.0"
    BASE_URL_CLOUD = "https://api.bitbucket.org/2.0"
    BASE_URL_SERVER = "https://bitbucket.example.com/rest/api/2.0"

    # Default retry configuration
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_INITIAL_DELAY = 1.0
    DEFAULT_MAX_DELAY = 60.0
    DEFAULT_BACKOFF_FACTOR = 2.0
    DEFAULT_JITTER = 0.1

    # Rate limiting (Cloud: 1000 requests/hour, Server: varies)
    DEFAULT_REQUESTS_PER_SECOND = 0.3  # Conservative: ~1000/hour
    DEFAULT_BURST_SIZE = 5

    # Connection pool settings
    DEFAULT_POOL_CONNECTIONS = 10
    DEFAULT_POOL_MAXSIZE = 10
    DEFAULT_TIMEOUT = 30.0

    def __init__(
        self,
        username: str,
        app_password: str,
        workspace: str,
        repo: str,
        base_url: str = BASE_URL_CLOUD,
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
        Initialize the Bitbucket client.

        Args:
            username: Bitbucket username
            app_password: App Password (Cloud) or Personal Access Token (Server)
            workspace: Workspace slug (Cloud) or project key (Server)
            repo: Repository slug
            base_url: API base URL (defaults to Cloud)
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
        self.username = username
        self.app_password = app_password
        self.workspace = workspace
        self.repo = repo
        self.base_url = base_url.rstrip("/")
        self.dry_run = dry_run
        self.timeout = timeout
        self.logger = logging.getLogger("BitbucketApiClient")

        # Retry configuration
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.jitter = jitter

        # Simple rate limiting (token bucket would be better, but keeping it simple)
        self._requests_per_second = requests_per_second
        self._last_request_time = 0.0
        self._min_request_interval = 1.0 / requests_per_second if requests_per_second else 0.0

        # Basic Auth header
        credentials = f"{username}:{app_password}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        self.headers = {
            "Accept": "application/json",
            "Authorization": f"Basic {encoded_credentials}",
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

        # Optional: Use atlassian-python-api for Server if available
        self._server_client: Any | None = None
        self._use_atlassian_api = False

        if ATLASSIAN_API_AVAILABLE and is_server_url(self.base_url):
            try:
                # Extract base URL without /rest/api/2.0
                server_base = self.base_url.replace("/rest/api/2.0", "").replace("/rest/api", "")
                if BitbucketServerClient is not None:
                    self._server_client = BitbucketServerClient(
                        url=server_base,
                        username=username,
                        password=app_password,
                        project_key=workspace,
                        repo_slug=repo,
                        dry_run=dry_run,
                    )
                    self._use_atlassian_api = True
                    self.logger.info("Using atlassian-python-api for enhanced Server support")
            except Exception as e:
                self.logger.warning(
                    f"Failed to initialize atlassian-python-api client, "
                    f"falling back to REST API: {e}"
                )
                self._use_atlassian_api = False

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
        Make an authenticated request to Bitbucket API with rate limiting and retry.

        Args:
            method: HTTP method
            endpoint: API endpoint (e.g., 'repositories/{workspace}/{repo}/issues')
            **kwargs: Additional arguments for requests

        Returns:
            JSON response (dict or list)

        Raises:
            IssueTrackerError: On API errors
        """
        # Support both absolute endpoints and workspace-relative endpoints
        if endpoint.startswith("/"):
            url = f"{self.base_url}{endpoint}"
        elif endpoint.startswith("http"):
            url = endpoint
        else:
            url = f"{self.base_url}/{endpoint}"

        # Apply rate limiting
        if self._requests_per_second:
            self._wait_for_rate_limit()

        last_exception: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                if "timeout" not in kwargs:
                    kwargs["timeout"] = self.timeout

                response = self._session.request(method, url, **kwargs)

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
                            f"Bitbucket rate limit exceeded for {endpoint}",
                            retry_after=retry_after,
                            issue_key=endpoint,
                        )
                    raise TransientError(
                        f"Bitbucket server error {response.status_code} for {endpoint}",
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

    def _wait_for_rate_limit(self) -> None:
        """Wait if necessary to respect rate limits."""
        if self._min_request_interval <= 0:
            return

        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_request_interval:
            sleep_time = self._min_request_interval - elapsed
            time.sleep(sleep_time)

        self._last_request_time = time.time()

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
                json_result: Any = response.json()
                if isinstance(json_result, (dict, list)):
                    return json_result
                return {}
            return {}

        status = response.status_code
        error_body = response.text[:500] if response.text else ""

        if status == 401:
            raise AuthenticationError("Bitbucket authentication failed. Check your credentials.")

        if status == 403:
            raise PermissionError(
                f"Permission denied for {endpoint}. Check credentials and permissions.",
                issue_key=endpoint,
            )

        if status == 404:
            raise NotFoundError(f"Not found: {endpoint}", issue_key=endpoint)

        raise IssueTrackerError(f"Bitbucket API error {status}: {error_body}", issue_key=endpoint)

    # -------------------------------------------------------------------------
    # Convenience Methods
    # -------------------------------------------------------------------------

    def repo_endpoint(self, path: str = "") -> str:
        """Get the full endpoint for a repo-scoped path."""
        base = f"repositories/{self.workspace}/{self.repo}"
        if path:
            return f"{base}/{path}"
        return base

    def get_authenticated_user(self) -> dict[str, Any]:
        """Get the currently authenticated user."""
        # Use Server client if available
        if self._use_atlassian_api and self._server_client:
            self._current_user = self._server_client.get_current_user()
            return self._current_user

        if self._current_user is None:
            result = self.get("user")
            if isinstance(result, dict):
                self._current_user = result
            else:
                self._current_user = {}
        return self._current_user

    def test_connection(self) -> bool:
        """Test if the API connection and credentials are valid."""
        # Use Server client if available
        if self._use_atlassian_api and self._server_client:
            return self._server_client.test_connection()

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

    def get_issue(self, issue_id: int) -> dict[str, Any]:
        """Get a single issue by ID."""
        # Use Server client if available
        if self._use_atlassian_api and self._server_client:
            return self._server_client.get_issue(issue_id)

        result = self.get(self.repo_endpoint(f"issues/{issue_id}"))
        return result if isinstance(result, dict) else {}

    def list_issues(
        self,
        state: str | None = None,
        kind: str | None = None,
        page: int = 1,
        pagelen: int = 50,
    ) -> list[dict[str, Any]]:
        """
        List issues in the repository.

        Args:
            state: Filter by state (new, open, resolved, closed, on hold, invalid, duplicate, wontfix)
            kind: Filter by kind (bug, enhancement, proposal, task)
            page: Page number (1-indexed)
            pagelen: Number of results per page
        """
        # Use Server client if available
        if self._use_atlassian_api and self._server_client:
            return self._server_client.list_issues(
                state=state, kind=kind, page=page, pagelen=pagelen
            )

        params: dict[str, Any] = {
            "page": page,
            "pagelen": pagelen,
        }
        if state:
            params["q"] = f'state="{state}"'
        if kind:
            if "q" in params:
                params["q"] += f' AND kind="{kind}"'
            else:
                params["q"] = f'kind="{kind}"'

        result = self.get(self.repo_endpoint("issues"), params=params)
        if isinstance(result, dict):
            values = result.get("values", [])
            if isinstance(values, list):
                return values
        return []

    def create_issue(
        self,
        title: str,
        content: str | None = None,
        kind: str = "task",
        priority: str = "minor",
        state: str = "new",
        assignee: str | None = None,
        component: str | None = None,
        version: str | None = None,
    ) -> dict[str, Any]:
        """Create a new issue."""
        # Use Server client if available
        if self._use_atlassian_api and self._server_client:
            return self._server_client.create_issue(
                title=title,
                content=content,
                kind=kind,
                priority=priority,
                state=state,
                assignee=assignee,
                component=component,
                version=version,
            )

        data: dict[str, Any] = {
            "title": title,
            "kind": kind,
            "priority": priority,
            "state": state,
        }
        if content:
            data["content"] = {"raw": content, "markup": "markdown"}
        if assignee:
            data["assignee"] = {"username": assignee}
        if component:
            data["component"] = {"name": component}
        if version:
            data["version"] = {"name": version}

        result = self.post(self.repo_endpoint("issues"), json=data)
        return result if isinstance(result, dict) else {}

    def update_issue(
        self,
        issue_id: int,
        title: str | None = None,
        content: str | None = None,
        state: str | None = None,
        priority: str | None = None,
        kind: str | None = None,
        assignee: str | None = None,
        component: str | None = None,
        version: str | None = None,
    ) -> dict[str, Any]:
        """Update an existing issue."""
        data: dict[str, Any] = {}
        if title is not None:
            data["title"] = title
        if content is not None:
            data["content"] = {"raw": content, "markup": "markdown"}
        if state is not None:
            data["state"] = state
        if priority is not None:
            data["priority"] = priority
        if kind is not None:
            data["kind"] = kind
        if assignee is not None:
            data["assignee"] = {"username": assignee} if assignee else None
        if component is not None:
            data["component"] = {"name": component} if component else None
        if version is not None:
            data["version"] = {"name": version} if version else None

        result = self.put(self.repo_endpoint(f"issues/{issue_id}"), json=data)
        return result if isinstance(result, dict) else {}

    def get_issue_comments(self, issue_id: int) -> list[dict[str, Any]]:
        """Get all comments on an issue."""
        # Use Server client if available
        if self._use_atlassian_api and self._server_client:
            return self._server_client.get_issue_comments(issue_id)

        result = self.get(self.repo_endpoint(f"issues/{issue_id}/comments"))
        if isinstance(result, dict):
            values = result.get("values", [])
            if isinstance(values, list):
                return values
        return []

    def add_issue_comment(
        self,
        issue_id: int,
        content: str,
    ) -> dict[str, Any]:
        """Add a comment to an issue."""
        # Use Server client if available
        if self._use_atlassian_api and self._server_client:
            return self._server_client.add_issue_comment(issue_id, content)

        data = {"content": {"raw": content, "markup": "markdown"}}
        result = self.post(self.repo_endpoint(f"issues/{issue_id}/comments"), json=data)
        return result if isinstance(result, dict) else {}

    # -------------------------------------------------------------------------
    # Milestones API (used for epics)
    # -------------------------------------------------------------------------

    def list_milestones(
        self,
        state: str = "open",
    ) -> list[dict[str, Any]]:
        """List all milestones."""
        result = self.get(self.repo_endpoint("milestones"), params={"state": state})
        if isinstance(result, dict):
            values = result.get("values", [])
            if isinstance(values, list):
                return values
        return []

    def get_milestone(self, milestone_id: int) -> dict[str, Any]:
        """Get a single milestone."""
        result = self.get(self.repo_endpoint(f"milestones/{milestone_id}"))
        return result if isinstance(result, dict) else {}

    def create_milestone(
        self,
        name: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Create a new milestone."""
        data: dict[str, Any] = {"name": name}
        if description:
            data["description"] = description

        result = self.post(self.repo_endpoint("milestones"), json=data)
        return result if isinstance(result, dict) else {}

    # -------------------------------------------------------------------------
    # Pull Requests API
    # -------------------------------------------------------------------------

    def list_pull_requests(
        self,
        state: str = "OPEN",
        page: int = 1,
        pagelen: int = 50,
    ) -> list[dict[str, Any]]:
        """
        List pull requests in the repository.

        Args:
            state: Filter by state (OPEN, MERGED, DECLINED, SUPERSEDED)
            page: Page number (1-indexed)
            pagelen: Number of results per page
        """
        params: dict[str, Any] = {
            "page": page,
            "pagelen": pagelen,
            "state": state,
        }

        result = self.get(self.repo_endpoint("pullrequests"), params=params)
        if isinstance(result, dict):
            values = result.get("values", [])
            if isinstance(values, list):
                return values
        return []

    def get_pull_request(self, pr_id: int) -> dict[str, Any]:
        """Get a single pull request by ID."""
        result = self.get(self.repo_endpoint(f"pullrequests/{pr_id}"))
        return result if isinstance(result, dict) else {}

    def link_pull_request_to_issue(
        self,
        issue_id: int,
        pr_id: int,
    ) -> bool:
        """
        Link a pull request to an issue.

        Bitbucket doesn't have a direct API for this, so we add a reference
        in the issue content and/or use the PR's issue links field.
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would link PR #{pr_id} to issue #{issue_id}")
            return True

        # Get current issue
        issue = self.get_issue(issue_id)
        current_content = issue.get("content", {}).get("raw", "") or ""

        # Add PR reference if not already present
        pr_ref = f"PR #{pr_id}"
        if pr_ref not in current_content and f"#{pr_id}" not in current_content:
            # Add to Pull Requests section
            pr_section = f"\n\n**Pull Requests:** {pr_ref}"
            if "**Pull Requests:**" in current_content:
                # Append to existing section
                import re

                pattern = r"(\*\*Pull Requests:\*\*\s*)(.+?)(?=\n\n|\Z)"
                match = re.search(pattern, current_content, re.IGNORECASE)
                if match:
                    existing = match.group(2).strip()
                    new_content = current_content.replace(
                        match.group(0), f"{match.group(1)}{existing}, {pr_ref}"
                    )
                else:
                    new_content = current_content + f", {pr_ref}"
            else:
                new_content = current_content + pr_section

            self.update_issue(issue_id, content=new_content)

        return True

    # -------------------------------------------------------------------------
    # Attachments API
    # -------------------------------------------------------------------------

    def get_issue_attachments(self, issue_id: int) -> list[dict[str, Any]]:
        """
        Get all attachments for an issue.

        Note: Bitbucket Cloud/Server may have different attachment APIs.
        This implementation uses the standard issue attachments endpoint.
        """
        result = self.get(self.repo_endpoint(f"issues/{issue_id}/attachments"))
        if isinstance(result, dict):
            values = result.get("values", [])
            if isinstance(values, list):
                return values
        elif isinstance(result, list):
            return result
        return []

    def upload_issue_attachment(
        self,
        issue_id: int,
        file_path: str,
        name: str | None = None,
    ) -> dict[str, Any]:
        """
        Upload a file attachment to an issue.

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
            self.logger.info(f"[DRY-RUN] Would upload attachment {file_path} to issue #{issue_id}")
            return {"id": "attachment:dry-run", "name": name or file_path}

        from pathlib import Path

        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            raise NotFoundError(f"File not found: {file_path}")

        # Bitbucket uses multipart/form-data for file uploads
        url = f"{self.base_url}/{self.repo_endpoint(f'issues/{issue_id}/attachments')}"

        # Apply rate limiting
        self._wait_for_rate_limit()

        try:
            with open(file_path_obj, "rb") as f:
                files = {"file": (name or file_path_obj.name, f)}
                response = self._session.post(url, files=files, timeout=self.timeout)

            if response.ok:
                json_result: Any = response.json()
                if isinstance(json_result, dict):
                    return json_result
                return {}
            # Handle error response
            result = self._handle_response(response, url)
            if isinstance(result, dict):
                return result
            return {}

        except Exception as e:
            raise IssueTrackerError(f"Failed to upload attachment: {e}", cause=e)

    def delete_issue_attachment(self, issue_id: int, attachment_id: str) -> bool:
        """
        Delete an attachment from an issue.

        Args:
            issue_id: Issue ID
            attachment_id: Attachment ID

        Returns:
            True if successful
        """
        if self.dry_run:
            self.logger.info(
                f"[DRY-RUN] Would delete attachment {attachment_id} from issue #{issue_id}"
            )
            return True

        self.delete(self.repo_endpoint(f"issues/{issue_id}/attachments/{attachment_id}"))
        return True

    # -------------------------------------------------------------------------
    # Components and Versions API
    # -------------------------------------------------------------------------

    def list_components(self) -> list[dict[str, Any]]:
        """List all components in the repository."""
        result = self.get(self.repo_endpoint("components"))
        if isinstance(result, dict):
            values = result.get("values", [])
            if isinstance(values, list):
                return values
        elif isinstance(result, list):
            return result
        return []

    def list_versions(self) -> list[dict[str, Any]]:
        """List all versions in the repository."""
        result = self.get(self.repo_endpoint("versions"))
        if isinstance(result, dict):
            values = result.get("values", [])
            if isinstance(values, list):
                return values
        elif isinstance(result, list):
            return result
        return []

    # -------------------------------------------------------------------------
    # Resource Cleanup
    # -------------------------------------------------------------------------

    def close(self) -> None:
        """Close the client and release connection pool resources."""
        self._session.close()
        self.logger.debug("Closed HTTP session")

    def __enter__(self) -> "BitbucketApiClient":
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
