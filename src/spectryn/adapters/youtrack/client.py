"""
YouTrack API Client - Low-level HTTP client for YouTrack REST API.

This handles the raw HTTP communication with YouTrack.
The YouTrackAdapter uses this to implement the IssueTrackerPort.

YouTrack REST API documentation:
https://www.jetbrains.com/help/youtrack/server/rest-api.html
"""

import logging
import time
from types import TracebackType
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


class YouTrackApiClient:
    """
    Low-level YouTrack REST API client.

    Handles authentication, request/response, rate limiting, and error handling.

    Features:
    - Permanent Token authentication
    - Automatic retry with exponential backoff for transient failures
    - Rate limiting support
    - Connection pooling for performance
    """

    API_VERSION = "2023.2"  # YouTrack API version

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
    DEFAULT_POOL_CONNECTIONS = 10
    DEFAULT_POOL_MAXSIZE = 10
    DEFAULT_TIMEOUT = 30.0

    def __init__(
        self,
        url: str,
        token: str,
        dry_run: bool = True,
        max_retries: int = DEFAULT_MAX_RETRIES,
        initial_delay: float = DEFAULT_INITIAL_DELAY,
        max_delay: float = DEFAULT_MAX_DELAY,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
        jitter: float = DEFAULT_JITTER,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        """
        Initialize the YouTrack client.

        Args:
            url: YouTrack instance URL (e.g., https://youtrack.example.com)
            token: Permanent Token for authentication
            dry_run: If True, don't make write operations
            max_retries: Maximum retry attempts for transient failures
            initial_delay: Initial retry delay in seconds
            max_delay: Maximum retry delay in seconds
            backoff_factor: Multiplier for exponential backoff
            jitter: Random jitter factor (0.1 = 10%)
            timeout: Request timeout in seconds
        """
        self.base_url = url.rstrip("/")
        self.api_url = f"{self.base_url}/api"
        self.token = token
        self.dry_run = dry_run
        self.timeout = timeout
        self.logger = logging.getLogger("YouTrackApiClient")

        # Retry configuration
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.jitter = jitter

        # Headers for YouTrack API
        self.headers = {
            "Accept": "application/json",
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
        Make an authenticated request to YouTrack API with retry.

        Args:
            method: HTTP method
            endpoint: API endpoint (e.g., 'issues')
            **kwargs: Additional arguments for requests

        Returns:
            JSON response (dict or list)

        Raises:
            IssueTrackerError: On API errors
        """
        # Support both absolute endpoints and relative endpoints
        if endpoint.startswith("/"):
            url = f"{self.api_url}{endpoint}"
        elif endpoint.startswith("http"):
            url = endpoint
        else:
            url = f"{self.api_url}/{endpoint}"

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
                            f"YouTrack rate limit exceeded for {endpoint}",
                            retry_after=retry_after,
                            issue_key=endpoint,
                        )
                    raise TransientError(
                        f"YouTrack server error {response.status_code} for {endpoint}",
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
                try:
                    json_data = response.json()
                    # Ensure we return the correct type
                    if isinstance(json_data, (dict, list)):
                        return json_data
                    return {}
                except ValueError:
                    # Some endpoints return empty responses
                    return {}
            return {}

        status = response.status_code
        error_body = response.text[:500] if response.text else ""

        if status == 401:
            raise AuthenticationError("YouTrack authentication failed. Check your token.")

        if status == 403:
            raise PermissionError(
                f"Permission denied for {endpoint}. Check token permissions.", issue_key=endpoint
            )

        if status == 404:
            raise NotFoundError(f"Not found: {endpoint}", issue_key=endpoint)

        raise IssueTrackerError(f"YouTrack API error {status}: {error_body}", issue_key=endpoint)

    # -------------------------------------------------------------------------
    # Convenience Methods
    # -------------------------------------------------------------------------

    def get_current_user(self) -> dict[str, Any]:
        """Get the currently authenticated user."""
        if self._current_user is None:
            result = self.get("users/me")
            if isinstance(result, dict):
                self._current_user = result
            else:
                self._current_user = {}
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
    # Issues API
    # -------------------------------------------------------------------------

    def get_issue(self, issue_id: str, fields: str | None = None) -> dict[str, Any]:
        """
        Get a single issue by ID.

        Args:
            issue_id: Issue ID (e.g., "PROJ-123")
            fields: Optional comma-separated list of fields to return
        """
        params = {}
        if fields:
            params["fields"] = fields
        result = self.get(f"issues/{issue_id}", params=params)
        return result if isinstance(result, dict) else {}

    def create_issue(
        self,
        project_id: str,
        summary: str,
        issue_type: str,
        description: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Create a new issue.

        Args:
            project_id: Project ID
            summary: Issue summary/title
            issue_type: Issue type (e.g., "Task", "Epic", "Subtask")
            description: Issue description
            **kwargs: Additional fields (priority, assignee, etc.)
        """
        data: dict[str, Any] = {
            "project": {"id": project_id},
            "summary": summary,
            "type": {"name": issue_type},
        }
        if description:
            data["description"] = description

        # Add additional fields
        data.update(kwargs)

        result = self.post("issues", json=data)
        return result if isinstance(result, dict) else {}

    def update_issue(
        self,
        issue_id: str,
        summary: str | None = None,
        description: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Update an existing issue.

        Args:
            issue_id: Issue ID
            summary: New summary (optional)
            description: New description (optional)
            **kwargs: Additional fields to update
        """
        data: dict[str, Any] = {}
        if summary is not None:
            data["summary"] = summary
        if description is not None:
            data["description"] = description
        data.update(kwargs)

        result = self.put(f"issues/{issue_id}", json=data)
        return result if isinstance(result, dict) else {}

    def get_issue_comments(self, issue_id: str) -> list[dict[str, Any]]:
        """Get all comments on an issue."""
        result = self.get(f"issues/{issue_id}/comments")
        return result if isinstance(result, list) else []

    def add_comment(self, issue_id: str, text: str) -> dict[str, Any]:
        """Add a comment to an issue."""
        result = self.post(f"issues/{issue_id}/comments", json={"text": text})
        return result if isinstance(result, dict) else {}

    def get_issue_links(self, issue_id: str) -> list[dict[str, Any]]:
        """Get all links for an issue."""
        result = self.get(f"issues/{issue_id}/links")
        return result if isinstance(result, list) else []

    def create_link(
        self,
        source_id: str,
        target_id: str,
        link_type: str,
    ) -> dict[str, Any]:
        """
        Create a link between two issues.

        Args:
            source_id: Source issue ID
            target_id: Target issue ID
            link_type: Link type (e.g., "depends on", "relates to")
        """
        data = {
            "target": {"id": target_id},
            "linkType": {"name": link_type},
        }
        result = self.post(f"issues/{source_id}/links", json=data)
        return result if isinstance(result, dict) else {}

    def search_issues(
        self,
        query: str,
        fields: str | None = None,
        max_results: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Search for issues using YouTrack Query Language (YQL).

        Args:
            query: YQL query (e.g., "project: PROJ State: Open")
            fields: Optional comma-separated list of fields to return
            max_results: Maximum results to return
        """
        params: dict[str, Any] = {"query": query, "max": max_results}
        if fields:
            params["fields"] = fields

        result = self.get("issues", params=params)
        return result if isinstance(result, list) else []

    def get_project_issues(
        self,
        project_id: str,
        max_results: int = 50,
    ) -> list[dict[str, Any]]:
        """Get all issues in a project."""
        return self.search_issues(f"project: {project_id}", max_results=max_results)

    def get_epic_children(self, epic_id: str) -> list[dict[str, Any]]:
        """
        Get all children of an epic.

        Args:
            epic_id: Epic issue ID
        """
        # YouTrack uses links to connect epics to their children
        # Search for issues linked to this epic
        return self.search_issues(f"issue: {epic_id} and has: {epic_id}", max_results=1000)

    def get_available_states(self, project_id: str) -> list[dict[str, Any]]:
        """Get available states for a project."""
        result = self.get(f"admin/projects/{project_id}/customFields/State")
        if isinstance(result, dict):
            # Extract states from custom field definition
            states = result.get("values", [])
            return states if isinstance(states, list) else []
        return []

    def get_available_priorities(self) -> list[dict[str, Any]]:
        """Get available priorities."""
        result = self.get("admin/customFieldSettings/bundles/priority")
        if isinstance(result, dict):
            values = result.get("values", [])
            return values if isinstance(values, list) else []
        return []

    # -------------------------------------------------------------------------
    # Custom Fields API
    # -------------------------------------------------------------------------

    def get_project_custom_fields(self, project_id: str) -> list[dict[str, Any]]:
        """
        Get all custom field definitions for a project.

        Args:
            project_id: Project short name or ID

        Returns:
            List of custom field definitions with id, name, type, etc.
        """
        result = self.get(
            f"admin/projects/{project_id}/customFields",
            params={"fields": "id,name,field(id,name,fieldType(id,presentation))"},
        )
        return result if isinstance(result, list) else []

    def get_issue_custom_fields(self, issue_id: str) -> list[dict[str, Any]]:
        """
        Get all custom field values for an issue.

        Args:
            issue_id: Issue ID (e.g., "PROJ-123")

        Returns:
            List of custom field values with name, value, etc.
        """
        result = self.get(
            f"issues/{issue_id}/customFields",
            params={"fields": "id,name,value(id,name,presentation,text,login,email),$type"},
        )
        return result if isinstance(result, list) else []

    def get_issue_custom_field(
        self,
        issue_id: str,
        field_name: str,
    ) -> dict[str, Any] | None:
        """
        Get a specific custom field value for an issue.

        Args:
            issue_id: Issue ID (e.g., "PROJ-123")
            field_name: Custom field name

        Returns:
            Custom field value dict, or None if not found
        """
        fields = self.get_issue_custom_fields(issue_id)
        for field in fields:
            if field.get("name") == field_name:
                return field
        return None

    def update_issue_custom_field(
        self,
        issue_id: str,
        field_name: str,
        value: Any,
    ) -> dict[str, Any]:
        """
        Update a custom field value for an issue.

        Args:
            issue_id: Issue ID (e.g., "PROJ-123")
            field_name: Custom field name
            value: New value (format depends on field type)
                   - Simple values: str, int, float
                   - Enum fields: {"name": "value"} or just "value"
                   - User fields: {"login": "username"}
                   - Date fields: timestamp in milliseconds

        Returns:
            Updated custom field data
        """
        # First, find the field ID
        fields = self.get_issue_custom_fields(issue_id)
        field_id = None
        field_type = None

        for field in fields:
            if field.get("name") == field_name:
                field_id = field.get("id")
                field_type = field.get("$type", "")
                break

        if not field_id:
            raise NotFoundError(f"Custom field '{field_name}' not found for issue {issue_id}")

        # Format the value based on field type
        formatted_value: Any
        field_type_str = field_type or ""
        if isinstance(value, dict):
            # Already formatted (e.g., {"name": "value"})
            formatted_value = value
        elif "EnumBundle" in field_type_str or "StateBundle" in field_type_str:
            # Enum or state field - wrap in name dict
            formatted_value = {"name": str(value)}
        elif "User" in field_type_str:
            # User field - wrap in login dict
            formatted_value = {"login": str(value)}
        else:
            # Simple value (text, number, etc.)
            formatted_value = value

        result = self.post(
            f"issues/{issue_id}/customFields/{field_id}",
            json={"value": formatted_value},
        )
        return result if isinstance(result, dict) else {}

    def get_custom_field_bundle(
        self,
        bundle_type: str,
        bundle_id: str,
    ) -> dict[str, Any]:
        """
        Get a custom field bundle (available values for enum-like fields).

        Args:
            bundle_type: Bundle type (e.g., "enum", "state", "priority", "ownedField")
            bundle_id: Bundle ID

        Returns:
            Bundle data with available values
        """
        result = self.get(
            f"admin/customFieldSettings/bundles/{bundle_type}/{bundle_id}",
            params={"fields": "id,name,values(id,name,description,color)"},
        )
        return result if isinstance(result, dict) else {}

    def transition_issue(
        self,
        issue_id: str,
        state: str,
        comment: str | None = None,
    ) -> dict[str, Any]:
        """
        Transition an issue to a new state.

        Args:
            issue_id: Issue ID
            state: Target state name
            comment: Optional comment for the transition
        """
        data: dict[str, Any] = {"state": {"name": state}}
        if comment:
            data["comment"] = comment

        result = self.post(f"issues/{issue_id}/executeCommand", json=data)
        return result if isinstance(result, dict) else {}

    # -------------------------------------------------------------------------
    # Bulk Operations API
    # -------------------------------------------------------------------------

    def bulk_create_issues(
        self,
        issues: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Create multiple issues in a batch.

        Args:
            issues: List of issue data dictionaries, each containing:
                    - project: {"id": "PROJECT_ID"} or {"shortName": "PROJ"}
                    - summary: Issue summary
                    - description: Issue description (optional)
                    - Additional fields as needed

        Returns:
            List of created issue data dictionaries
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would create {len(issues)} issues in bulk")
            return [{"id": f"dry-run-{i}", "idReadable": f"PROJ-{i}"} for i in range(len(issues))]

        created = []
        for issue_data in issues:
            try:
                result = self.post("issues", json=issue_data)
                if isinstance(result, dict):
                    created.append(result)
            except IssueTrackerError as e:
                self.logger.error(f"Failed to create issue: {e}")
                created.append({"error": str(e), "data": issue_data})
        return created

    def bulk_update_issues(
        self,
        updates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Update multiple issues in a batch.

        Args:
            updates: List of update dictionaries, each containing:
                     - id: Issue ID (e.g., "PROJ-123")
                     - fields to update (summary, description, customFields, etc.)

        Returns:
            List of update results
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would update {len(updates)} issues in bulk")
            return [{"id": u.get("id"), "status": "dry-run"} for u in updates]

        results = []
        for update in updates:
            issue_id = update.pop("id", None)
            if not issue_id:
                results.append({"error": "Missing issue ID", "data": update})
                continue

            try:
                result = self.put(f"issues/{issue_id}", json=update)
                if isinstance(result, dict):
                    results.append(result)
                else:
                    results.append({"id": issue_id, "status": "updated"})
            except IssueTrackerError as e:
                self.logger.error(f"Failed to update issue {issue_id}: {e}")
                results.append({"id": issue_id, "error": str(e)})
        return results

    def bulk_delete_issues(
        self,
        issue_ids: list[str],
    ) -> list[dict[str, Any]]:
        """
        Delete multiple issues in a batch.

        Args:
            issue_ids: List of issue IDs to delete

        Returns:
            List of deletion results
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would delete {len(issue_ids)} issues in bulk")
            return [{"id": id, "status": "dry-run"} for id in issue_ids]

        results = []
        for issue_id in issue_ids:
            try:
                self.delete(f"issues/{issue_id}")
                results.append({"id": issue_id, "status": "deleted"})
            except IssueTrackerError as e:
                self.logger.error(f"Failed to delete issue {issue_id}: {e}")
                results.append({"id": issue_id, "error": str(e)})
        return results

    def bulk_execute_command(
        self,
        issue_ids: list[str],
        command: str,
        comment: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Execute a command on multiple issues.

        Args:
            issue_ids: List of issue IDs
            command: YouTrack command string (e.g., "State In Progress", "Priority Critical")
            comment: Optional comment to add

        Returns:
            List of command execution results
        """
        if self.dry_run:
            self.logger.info(
                f"[DRY-RUN] Would execute command '{command}' on {len(issue_ids)} issues"
            )
            return [{"id": id, "status": "dry-run"} for id in issue_ids]

        results = []
        for issue_id in issue_ids:
            try:
                data: dict[str, Any] = {"query": command}
                if comment:
                    data["comment"] = comment

                result = self.post(f"issues/{issue_id}/executeCommand", json=data)
                results.append({"id": issue_id, "status": "executed", "result": result})
            except IssueTrackerError as e:
                self.logger.error(f"Failed to execute command on {issue_id}: {e}")
                results.append({"id": issue_id, "error": str(e)})
        return results

    # -------------------------------------------------------------------------
    # Attachments API
    # -------------------------------------------------------------------------

    def get_issue_attachments(self, issue_id: str) -> list[dict[str, Any]]:
        """
        Get all attachments for an issue.

        Args:
            issue_id: Issue ID (e.g., "PROJ-123")

        Returns:
            List of attachment dictionaries
        """
        result = self.get(
            f"issues/{issue_id}/attachments",
            params={"fields": "id,name,url,size,mimeType,created,author(login,name)"},
        )
        return result if isinstance(result, list) else []

    def upload_attachment(
        self,
        issue_id: str,
        file_path: str,
        name: str | None = None,
    ) -> dict[str, Any]:
        """
        Upload a file attachment to an issue.

        Args:
            issue_id: Issue ID (e.g., "PROJ-123")
            file_path: Path to file to upload
            name: Optional attachment name (defaults to filename)

        Returns:
            Attachment information dictionary
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would upload {file_path} to {issue_id}")
            return {"id": "attachment:dry-run", "name": name or file_path}

        from pathlib import Path

        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            raise NotFoundError(f"File not found: {file_path}")

        file_name = name or file_path_obj.name
        url = f"{self.api_url}/issues/{issue_id}/attachments"

        with open(file_path_obj, "rb") as f:
            files = {"file": (file_name, f)}

            # Remove Content-Type for multipart upload
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
            result = response.json()
            if isinstance(result, list) and len(result) > 0:
                return dict(result[0]) if isinstance(result[0], dict) else {"id": "unknown"}
            return (
                dict(result) if isinstance(result, dict) else {"id": "unknown", "name": file_name}
            )
        except ValueError:
            return {"id": "unknown", "name": file_name}

    def delete_attachment(self, issue_id: str, attachment_id: str) -> bool:
        """
        Delete an attachment from an issue.

        Args:
            issue_id: Issue ID (e.g., "PROJ-123")
            attachment_id: Attachment ID to delete

        Returns:
            True if successful
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would delete attachment {attachment_id} from {issue_id}")
            return True

        self.delete(f"issues/{issue_id}/attachments/{attachment_id}")
        return True

    def download_attachment(
        self,
        issue_id: str,
        attachment_id: str,
        output_path: str,
    ) -> str:
        """
        Download an attachment to a local file.

        Args:
            issue_id: Issue ID (e.g., "PROJ-123")
            attachment_id: Attachment ID to download
            output_path: Path to save the file

        Returns:
            Path to the downloaded file
        """
        if self.dry_run:
            self.logger.info(
                f"[DRY-RUN] Would download attachment {attachment_id} to {output_path}"
            )
            return output_path

        # Get attachment info to find the URL
        attachments = self.get_issue_attachments(issue_id)
        attachment_url = None
        for att in attachments:
            if att.get("id") == attachment_id:
                attachment_url = att.get("url")
                break

        if not attachment_url:
            raise NotFoundError(f"Attachment {attachment_id} not found on {issue_id}")

        # Download the file
        response = self._session.get(attachment_url, timeout=self.timeout)
        if not response.ok:
            raise IssueTrackerError(f"Failed to download attachment: {response.status_code}")

        from pathlib import Path

        output_path_obj = Path(output_path)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)
        output_path_obj.write_bytes(response.content)

        return str(output_path_obj)

    # -------------------------------------------------------------------------
    # Workflow & Commands API
    # -------------------------------------------------------------------------

    def execute_command(
        self,
        issue_id: str,
        command: str,
        comment: str | None = None,
        run_as: str | None = None,
    ) -> dict[str, Any]:
        """
        Execute a YouTrack command on an issue.

        Args:
            issue_id: Issue ID (e.g., "PROJ-123")
            command: Command string (e.g., "State In Progress", "Priority Critical")
            comment: Optional comment to add
            run_as: Optional user login to run the command as

        Returns:
            Command execution result
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would execute command '{command}' on {issue_id}")
            return {"id": issue_id, "command": command, "status": "dry-run"}

        data: dict[str, Any] = {"query": command}
        if comment:
            data["comment"] = comment
        if run_as:
            data["runAs"] = run_as

        result = self.post(f"issues/{issue_id}/executeCommand", json=data)
        return result if isinstance(result, dict) else {}

    def get_available_commands(self, issue_id: str) -> list[dict[str, Any]]:
        """
        Get available commands for an issue based on current state.

        Args:
            issue_id: Issue ID

        Returns:
            List of available command suggestions
        """
        result = self.get(
            f"issues/{issue_id}/commands",
            params={"fields": "id,name,description"},
        )
        return result if isinstance(result, list) else []

    # -------------------------------------------------------------------------
    # Due Dates API
    # -------------------------------------------------------------------------

    def get_issue_due_date(self, issue_id: str) -> int | None:
        """
        Get the due date for an issue.

        Args:
            issue_id: Issue ID

        Returns:
            Due date as Unix timestamp (milliseconds), or None if not set
        """
        # Due date is typically stored in a custom field called "Due Date"
        fields = self.get_issue_custom_fields(issue_id)
        for field in fields:
            field_name = field.get("name", "").lower()
            if "due" in field_name and "date" in field_name:
                value = field.get("value")
                if isinstance(value, int):
                    return value
                if isinstance(value, dict):
                    return value.get("timestamp") or value.get("value")
        return None

    def set_issue_due_date(
        self,
        issue_id: str,
        due_date: int | str | None,
        field_name: str = "Due Date",
    ) -> dict[str, Any]:
        """
        Set or clear the due date for an issue.

        Args:
            issue_id: Issue ID
            due_date: Due date as Unix timestamp (ms), ISO date string, or None to clear
            field_name: Name of the due date custom field

        Returns:
            Update result
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would set due date for {issue_id} to {due_date}")
            return {"id": issue_id, "status": "dry-run"}

        # Convert ISO string to timestamp if needed
        if isinstance(due_date, str):
            from datetime import datetime

            try:
                dt = datetime.fromisoformat(due_date.replace("Z", "+00:00"))
                due_date = int(dt.timestamp() * 1000)
            except ValueError:
                pass

        return self.update_issue_custom_field(issue_id, field_name, due_date)

    # -------------------------------------------------------------------------
    # Tags API
    # -------------------------------------------------------------------------

    def get_issue_tags(self, issue_id: str) -> list[dict[str, Any]]:
        """
        Get all tags for an issue.

        Args:
            issue_id: Issue ID

        Returns:
            List of tag dictionaries
        """
        result = self.get(
            f"issues/{issue_id}/tags",
            params={"fields": "id,name,color(id,background,foreground)"},
        )
        return result if isinstance(result, list) else []

    def add_issue_tag(self, issue_id: str, tag_name: str) -> dict[str, Any]:
        """
        Add a tag to an issue.

        Args:
            issue_id: Issue ID
            tag_name: Tag name to add

        Returns:
            Tag information
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would add tag '{tag_name}' to {issue_id}")
            return {"name": tag_name, "status": "dry-run"}

        # Use command API to add tag
        return self.execute_command(issue_id, f"tag {tag_name}")

    def remove_issue_tag(self, issue_id: str, tag_name: str) -> dict[str, Any]:
        """
        Remove a tag from an issue.

        Args:
            issue_id: Issue ID
            tag_name: Tag name to remove

        Returns:
            Result of tag removal
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would remove tag '{tag_name}' from {issue_id}")
            return {"name": tag_name, "status": "dry-run"}

        # Use command API to remove tag
        return self.execute_command(issue_id, f"untag {tag_name}")

    def get_project_tags(self, project_id: str) -> list[dict[str, Any]]:
        """
        Get all tags available in a project.

        Args:
            project_id: Project short name or ID

        Returns:
            List of tag dictionaries
        """
        result = self.get(
            f"admin/projects/{project_id}/tags",
            params={"fields": "id,name,color(id,background,foreground)"},
        )
        return result if isinstance(result, list) else []

    # -------------------------------------------------------------------------
    # Watchers API
    # -------------------------------------------------------------------------

    def get_issue_watchers(self, issue_id: str) -> list[dict[str, Any]]:
        """
        Get all watchers for an issue.

        Args:
            issue_id: Issue ID

        Returns:
            List of watcher user dictionaries
        """
        result = self.get(
            f"issues/{issue_id}/watchers",
            params={"fields": "id,login,name,email"},
        )
        return result if isinstance(result, list) else []

    def add_issue_watcher(self, issue_id: str, user_login: str) -> dict[str, Any]:
        """
        Add a watcher to an issue.

        Args:
            issue_id: Issue ID
            user_login: User login to add as watcher

        Returns:
            Result of adding watcher
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would add watcher '{user_login}' to {issue_id}")
            return {"login": user_login, "status": "dry-run"}

        result = self.post(
            f"issues/{issue_id}/watchers",
            json={"login": user_login},
        )
        return result if isinstance(result, dict) else {}

    def remove_issue_watcher(self, issue_id: str, user_login: str) -> bool:
        """
        Remove a watcher from an issue.

        Args:
            issue_id: Issue ID
            user_login: User login to remove

        Returns:
            True if successful
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would remove watcher '{user_login}' from {issue_id}")
            return True

        # Find the watcher ID
        watchers = self.get_issue_watchers(issue_id)
        watcher_id = None
        for w in watchers:
            if w.get("login") == user_login:
                watcher_id = w.get("id")
                break

        if not watcher_id:
            raise NotFoundError(f"Watcher '{user_login}' not found on {issue_id}")

        self.delete(f"issues/{issue_id}/watchers/{watcher_id}")
        return True

    def is_watching(self, issue_id: str, user_login: str | None = None) -> bool:
        """
        Check if a user is watching an issue.

        Args:
            issue_id: Issue ID
            user_login: User login to check (defaults to current user)

        Returns:
            True if watching
        """
        watchers = self.get_issue_watchers(issue_id)
        if user_login is None:
            # Get current user
            current = self.get_current_user()
            user_login = current.get("login")

        return any(w.get("login") == user_login for w in watchers)

    # -------------------------------------------------------------------------
    # Agile Boards API
    # -------------------------------------------------------------------------

    def get_agile_boards(self) -> list[dict[str, Any]]:
        """
        Get all agile boards.

        Returns:
            List of agile board dictionaries
        """
        result = self.get(
            "agiles",
            params={"fields": "id,name,owner(login,name),projects(id,shortName)"},
        )
        return result if isinstance(result, list) else []

    def get_agile_board(self, board_id: str) -> dict[str, Any]:
        """
        Get a specific agile board.

        Args:
            board_id: Board ID

        Returns:
            Board information
        """
        result = self.get(
            f"agiles/{board_id}",
            params={"fields": "id,name,owner(login,name),projects(id,shortName),sprints(id,name)"},
        )
        return result if isinstance(result, dict) else {}

    def get_board_sprints(self, board_id: str) -> list[dict[str, Any]]:
        """
        Get all sprints for an agile board.

        Args:
            board_id: Board ID

        Returns:
            List of sprint dictionaries
        """
        result = self.get(
            f"agiles/{board_id}/sprints",
            params={"fields": "id,name,start,finish,goal,isDefault,archived"},
        )
        return result if isinstance(result, list) else []

    # -------------------------------------------------------------------------
    # Sprints API
    # -------------------------------------------------------------------------

    def get_sprint(self, board_id: str, sprint_id: str) -> dict[str, Any]:
        """
        Get a specific sprint.

        Args:
            board_id: Board ID
            sprint_id: Sprint ID

        Returns:
            Sprint information
        """
        result = self.get(
            f"agiles/{board_id}/sprints/{sprint_id}",
            params={
                "fields": "id,name,start,finish,goal,isDefault,archived,issues(id,idReadable,summary)"
            },
        )
        return result if isinstance(result, dict) else {}

    def create_sprint(
        self,
        board_id: str,
        name: str,
        start: int | None = None,
        finish: int | None = None,
        goal: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a new sprint.

        Args:
            board_id: Board ID
            name: Sprint name
            start: Start date as Unix timestamp (ms)
            finish: End date as Unix timestamp (ms)
            goal: Sprint goal

        Returns:
            Created sprint data
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would create sprint '{name}' on board {board_id}")
            return {"id": "sprint:dry-run", "name": name}

        data: dict[str, Any] = {"name": name}
        if start is not None:
            data["start"] = start
        if finish is not None:
            data["finish"] = finish
        if goal is not None:
            data["goal"] = goal

        result = self.post(f"agiles/{board_id}/sprints", json=data)
        return result if isinstance(result, dict) else {}

    def update_sprint(
        self,
        board_id: str,
        sprint_id: str,
        name: str | None = None,
        start: int | None = None,
        finish: int | None = None,
        goal: str | None = None,
        archived: bool | None = None,
    ) -> dict[str, Any]:
        """
        Update a sprint.

        Args:
            board_id: Board ID
            sprint_id: Sprint ID
            name: New name
            start: New start date
            finish: New end date
            goal: New goal
            archived: Archive status

        Returns:
            Updated sprint data
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would update sprint {sprint_id}")
            return {"id": sprint_id}

        data: dict[str, Any] = {}
        if name is not None:
            data["name"] = name
        if start is not None:
            data["start"] = start
        if finish is not None:
            data["finish"] = finish
        if goal is not None:
            data["goal"] = goal
        if archived is not None:
            data["archived"] = archived

        result = self.post(f"agiles/{board_id}/sprints/{sprint_id}", json=data)
        return result if isinstance(result, dict) else {}

    def add_issue_to_sprint(
        self,
        board_id: str,
        sprint_id: str,
        issue_id: str,
    ) -> dict[str, Any]:
        """
        Add an issue to a sprint.

        Args:
            board_id: Board ID
            sprint_id: Sprint ID
            issue_id: Issue ID to add

        Returns:
            Result
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would add {issue_id} to sprint {sprint_id}")
            return {"id": issue_id}

        # Use command API to add to sprint
        return self.execute_command(issue_id, f"Board {board_id} Sprint {sprint_id}")

    def remove_issue_from_sprint(self, issue_id: str) -> dict[str, Any]:
        """
        Remove an issue from its current sprint.

        Args:
            issue_id: Issue ID

        Returns:
            Result
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would remove {issue_id} from sprint")
            return {"id": issue_id}

        # Use command API to remove from sprint
        return self.execute_command(issue_id, "Sprint Unassigned")

    # -------------------------------------------------------------------------
    # Time Tracking API
    # -------------------------------------------------------------------------

    def get_issue_work_items(self, issue_id: str) -> list[dict[str, Any]]:
        """
        Get all work items (time entries) for an issue.

        Args:
            issue_id: Issue ID

        Returns:
            List of work item dictionaries
        """
        result = self.get(
            f"issues/{issue_id}/timeTracking/workItems",
            params={
                "fields": "id,author(login,name),date,duration(minutes,presentation),text,type(name)"
            },
        )
        return result if isinstance(result, list) else []

    def add_work_item(
        self,
        issue_id: str,
        duration_minutes: int,
        date: int | None = None,
        text: str | None = None,
        work_type: str | None = None,
    ) -> dict[str, Any]:
        """
        Add a work item (time entry) to an issue.

        Args:
            issue_id: Issue ID
            duration_minutes: Duration in minutes
            date: Date as Unix timestamp (ms), defaults to now
            text: Work description
            work_type: Work type name

        Returns:
            Created work item
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would add {duration_minutes}m work to {issue_id}")
            return {"id": "work:dry-run", "duration": {"minutes": duration_minutes}}

        data: dict[str, Any] = {"duration": {"minutes": duration_minutes}}
        if date is not None:
            data["date"] = date
        if text is not None:
            data["text"] = text
        if work_type is not None:
            data["type"] = {"name": work_type}

        result = self.post(f"issues/{issue_id}/timeTracking/workItems", json=data)
        return result if isinstance(result, dict) else {}

    def delete_work_item(self, issue_id: str, work_item_id: str) -> bool:
        """
        Delete a work item.

        Args:
            issue_id: Issue ID
            work_item_id: Work item ID to delete

        Returns:
            True if successful
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would delete work item {work_item_id}")
            return True

        self.delete(f"issues/{issue_id}/timeTracking/workItems/{work_item_id}")
        return True

    def get_time_tracking_settings(self, issue_id: str) -> dict[str, Any]:
        """
        Get time tracking settings for an issue.

        Args:
            issue_id: Issue ID

        Returns:
            Time tracking settings
        """
        result = self.get(
            f"issues/{issue_id}/timeTracking",
            params={
                "fields": "enabled,estimate(minutes,presentation),spentTime(minutes,presentation)"
            },
        )
        return result if isinstance(result, dict) else {}

    def set_time_estimate(
        self,
        issue_id: str,
        estimate_minutes: int | None,
    ) -> dict[str, Any]:
        """
        Set time estimate for an issue.

        Args:
            issue_id: Issue ID
            estimate_minutes: Estimate in minutes, or None to clear

        Returns:
            Updated time tracking data
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would set estimate for {issue_id} to {estimate_minutes}m")
            return {"estimate": {"minutes": estimate_minutes}}

        data: dict[str, Any] = {}
        if estimate_minutes is not None:
            data["estimate"] = {"minutes": estimate_minutes}
        else:
            data["estimate"] = None

        result = self.post(f"issues/{issue_id}/timeTracking", json=data)
        return result if isinstance(result, dict) else {}

    # -------------------------------------------------------------------------
    # Issue History/Activity API
    # -------------------------------------------------------------------------

    def get_issue_activities(
        self,
        issue_id: str,
        categories: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get activity/history for an issue.

        Args:
            issue_id: Issue ID
            categories: Filter by category (e.g., "IssueCreatedCategory", "CustomFieldCategory")

        Returns:
            List of activity items
        """
        params: dict[str, Any] = {
            "fields": "id,timestamp,author(login,name),added,removed,target,field(name)"
        }
        if categories:
            params["categories"] = ",".join(categories)

        result = self.get(f"issues/{issue_id}/activities", params=params)
        return result if isinstance(result, list) else []

    def get_issue_changes(self, issue_id: str) -> list[dict[str, Any]]:
        """
        Get change history for an issue (simplified activity feed).

        Args:
            issue_id: Issue ID

        Returns:
            List of change dictionaries
        """
        activities = self.get_issue_activities(issue_id)
        changes = []
        for activity in activities:
            change = {
                "id": activity.get("id", ""),
                "timestamp": activity.get("timestamp"),
                "author": activity.get("author", {}).get("login")
                or activity.get("author", {}).get("name"),
                "field": activity.get("field", {}).get("name") if activity.get("field") else None,
                "added": activity.get("added"),
                "removed": activity.get("removed"),
            }
            changes.append(change)
        return changes

    # -------------------------------------------------------------------------
    # Mentions API
    # -------------------------------------------------------------------------

    def add_comment_with_mentions(
        self,
        issue_id: str,
        text: str,
        mentions: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Add a comment with @mentions.

        Args:
            issue_id: Issue ID
            text: Comment text (can include @username mentions)
            mentions: Optional list of usernames to notify

        Returns:
            Created comment
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would add comment with mentions to {issue_id}")
            return {"id": "comment:dry-run", "text": text}

        # Format mentions into the text if provided separately
        if mentions:
            mention_text = " ".join(f"@{m}" for m in mentions)
            text = f"{text}\n\n{mention_text}"

        return self.add_comment(issue_id, text)

    def get_mentionable_users(self, query: str = "") -> list[dict[str, Any]]:
        """
        Get users that can be mentioned.

        Args:
            query: Search query for user names/logins

        Returns:
            List of user dictionaries
        """
        params: dict[str, Any] = {"fields": "id,login,name,email"}
        if query:
            params["query"] = query

        result = self.get("users", params=params)
        return result if isinstance(result, list) else []

    # -------------------------------------------------------------------------
    # Resource Cleanup
    # -------------------------------------------------------------------------

    def close(self) -> None:
        """Close the client and release connection pool resources."""
        self._session.close()
        self.logger.debug("Closed HTTP session")

    def __enter__(self) -> "YouTrackApiClient":
        """Context manager entry."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Context manager exit."""
        self.close()
