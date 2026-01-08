"""
Confluence REST API Client.

Low-level client for Confluence Cloud and Server REST APIs.
Handles authentication, rate limiting, and request retries.
"""

import base64
import logging
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from spectryn.core.constants import ApiDefaults, ContentType, HttpHeader
from spectryn.core.exceptions import OutputError


@dataclass
class ConfluenceConfig:
    """Configuration for Confluence client."""

    base_url: str  # e.g., https://yourcompany.atlassian.net/wiki
    username: str  # Email for Cloud, username for Server
    api_token: str  # API token for Cloud, password for Server
    is_cloud: bool = True
    timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0


class ConfluenceAPIError(OutputError):
    """
    Confluence API error.

    Low-level API error with HTTP response details.
    Inherits from OutputError for consistent exception hierarchy.
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_body: str | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class ConfluenceClient:
    """
    Low-level Confluence REST API client.

    Supports both Confluence Cloud and Server APIs.
    Cloud uses /wiki/rest/api/*, Server uses /rest/api/*.

    Features:
    - Basic auth (username + API token)
    - Connection pooling
    - Automatic retries with exponential backoff
    - Rate limit handling
    """

    def __init__(self, config: ConfluenceConfig) -> None:
        """
        Initialize the Confluence client.

        Args:
            config: ConfluenceConfig with connection details
        """
        self.config = config
        self.logger = logging.getLogger("ConfluenceClient")
        self._session: requests.Session | None = None

        # Determine API base path
        base = config.base_url.rstrip("/")
        if config.is_cloud:
            # Cloud: https://company.atlassian.net/wiki/rest/api
            if "/wiki" not in base:
                base = f"{base}/wiki"
            self._api_base = f"{base}/rest/api"
        else:
            # Server: https://confluence.company.com/rest/api
            self._api_base = f"{base}/rest/api"

    # -------------------------------------------------------------------------
    # Session Management
    # -------------------------------------------------------------------------

    def connect(self) -> None:
        """Create and configure the HTTP session."""
        self._session = requests.Session()

        # Set up basic auth
        auth_string = f"{self.config.username}:{self.config.api_token}"
        auth_bytes = base64.b64encode(auth_string.encode()).decode()

        self._session.headers.update(
            {
                HttpHeader.AUTHORIZATION: f"Basic {auth_bytes}",
                HttpHeader.CONTENT_TYPE: ContentType.JSON,
                HttpHeader.ACCEPT: ContentType.JSON,
                "X-Atlassian-Token": "no-check",  # Disable XSRF for API calls
            }
        )

        # Configure connection pooling and retries
        retry_strategy = Retry(
            total=self.config.max_retries,
            backoff_factor=self.config.retry_delay,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PUT", "DELETE"],
        )
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=ApiDefaults.POOL_CONNECTIONS,
            pool_maxsize=ApiDefaults.POOL_MAXSIZE,
        )
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)

        self.logger.info(f"Connected to Confluence at {self.config.base_url}")

    def disconnect(self) -> None:
        """Close the HTTP session."""
        if self._session:
            self._session.close()
            self._session = None
            self.logger.info("Disconnected from Confluence")

    @property
    def session(self) -> requests.Session:
        """Get the active session, connecting if needed."""
        if not self._session:
            self.connect()
        return self._session  # type: ignore

    # -------------------------------------------------------------------------
    # HTTP Request Handling
    # -------------------------------------------------------------------------

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict | None = None,
        json_data: dict | None = None,
        retry_count: int = 0,
    ) -> dict[str, Any]:
        """
        Make an HTTP request to the Confluence API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (e.g., /content)
            params: Query parameters
            json_data: JSON body data
            retry_count: Current retry attempt

        Returns:
            Parsed JSON response

        Raises:
            ConfluenceAPIError: On API errors
        """
        url = f"{self._api_base}{endpoint}"

        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                timeout=self.config.timeout,
            )

            # Handle rate limiting
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                if retry_count < self.config.max_retries:
                    self.logger.warning(f"Rate limited, waiting {retry_after}s")
                    time.sleep(retry_after)
                    return self._request(method, endpoint, params, json_data, retry_count + 1)
                raise ConfluenceAPIError(
                    f"Rate limit exceeded after {retry_count} retries",
                    status_code=429,
                )

            # Handle errors
            if not response.ok:
                error_msg = self._parse_error(response)
                raise ConfluenceAPIError(
                    error_msg,
                    status_code=response.status_code,
                    response_body=response.text,
                )

            # Return empty dict for 204 No Content
            if response.status_code == 204:
                return {}

            return response.json()

        except requests.exceptions.Timeout:
            if retry_count < self.config.max_retries:
                wait_time = self.config.retry_delay * (2**retry_count)
                self.logger.warning(f"Request timeout, retrying in {wait_time}s")
                time.sleep(wait_time)
                return self._request(method, endpoint, params, json_data, retry_count + 1)
            raise ConfluenceAPIError("Request timeout after retries")

        except requests.exceptions.RequestException as e:
            raise ConfluenceAPIError(f"Request failed: {e}")

    def _parse_error(self, response: requests.Response) -> str:
        """Parse error message from response."""
        try:
            data = response.json()
            if "message" in data:
                return data["message"]
            if "errorMessages" in data:
                return "; ".join(data["errorMessages"])
            if "errors" in data:
                return str(data["errors"])
        except Exception:
            pass
        return f"HTTP {response.status_code}: {response.reason}"

    # -------------------------------------------------------------------------
    # Space API
    # -------------------------------------------------------------------------

    def get_space(self, space_key: str) -> dict[str, Any]:
        """
        Get space by key.

        Args:
            space_key: Space key (e.g., "DEV")

        Returns:
            Space data
        """
        return self._request("GET", f"/space/{space_key}")

    def list_spaces(self, limit: int = 100) -> list[dict[str, Any]]:
        """
        List all spaces.

        Args:
            limit: Max spaces to return

        Returns:
            List of space data
        """
        result = self._request("GET", "/space", params={"limit": limit})
        return result.get("results", [])

    # -------------------------------------------------------------------------
    # Content/Page API
    # -------------------------------------------------------------------------

    def get_content(
        self,
        content_id: str,
        expand: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Get content/page by ID.

        Args:
            content_id: Content ID
            expand: Fields to expand (e.g., ["body.storage", "version"])

        Returns:
            Content data
        """
        params = {}
        if expand:
            params["expand"] = ",".join(expand)
        return self._request("GET", f"/content/{content_id}", params=params)

    def get_content_by_title(
        self,
        space_key: str,
        title: str,
        expand: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """
        Find content by title in a space.

        Args:
            space_key: Space key
            title: Page title
            expand: Fields to expand

        Returns:
            Content data or None if not found
        """
        params: dict[str, Any] = {
            "spaceKey": space_key,
            "title": title,
            "type": "page",
        }
        if expand:
            params["expand"] = ",".join(expand)

        result = self._request("GET", "/content", params=params)
        results = result.get("results", [])
        return results[0] if results else None

    def create_content(
        self,
        space_key: str,
        title: str,
        body: str,
        parent_id: str | None = None,
        content_type: str = "page",
    ) -> dict[str, Any]:
        """
        Create new content/page.

        Args:
            space_key: Target space
            title: Page title
            body: Page body (Confluence storage format)
            parent_id: Optional parent page ID
            content_type: Content type (page, blogpost)

        Returns:
            Created content data
        """
        data: dict[str, Any] = {
            "type": content_type,
            "title": title,
            "space": {"key": space_key},
            "body": {
                "storage": {
                    "value": body,
                    "representation": "storage",
                }
            },
        }

        if parent_id:
            data["ancestors"] = [{"id": parent_id}]

        return self._request("POST", "/content", json_data=data)

    def update_content(
        self,
        content_id: str,
        title: str,
        body: str,
        version: int,
        content_type: str = "page",
    ) -> dict[str, Any]:
        """
        Update existing content/page.

        Args:
            content_id: Content ID to update
            title: New title
            body: New body
            version: Current version number (incremented automatically)
            content_type: Content type

        Returns:
            Updated content data
        """
        data = {
            "type": content_type,
            "title": title,
            "body": {
                "storage": {
                    "value": body,
                    "representation": "storage",
                }
            },
            "version": {
                "number": version + 1,
            },
        }

        return self._request("PUT", f"/content/{content_id}", json_data=data)

    def delete_content(self, content_id: str) -> None:
        """
        Delete content/page.

        Args:
            content_id: Content ID to delete
        """
        self._request("DELETE", f"/content/{content_id}")

    # -------------------------------------------------------------------------
    # Labels API
    # -------------------------------------------------------------------------

    def get_labels(self, content_id: str) -> list[dict[str, Any]]:
        """
        Get labels for content.

        Args:
            content_id: Content ID

        Returns:
            List of labels
        """
        result = self._request("GET", f"/content/{content_id}/label")
        return result.get("results", [])

    def add_labels(self, content_id: str, labels: list[str]) -> list[dict[str, Any]]:
        """
        Add labels to content.

        Args:
            content_id: Content ID
            labels: List of label names

        Returns:
            Created labels
        """
        label_data = [{"name": label} for label in labels]
        result = self._request("POST", f"/content/{content_id}/label", json_data=label_data)
        return result.get("results", [])

    def remove_label(self, content_id: str, label: str) -> None:
        """
        Remove a label from content.

        Args:
            content_id: Content ID
            label: Label name to remove
        """
        self._request("DELETE", f"/content/{content_id}/label/{quote(label)}")

    # -------------------------------------------------------------------------
    # Search API
    # -------------------------------------------------------------------------

    def search(
        self,
        cql: str,
        limit: int = 25,
        expand: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search using CQL (Confluence Query Language).

        Args:
            cql: CQL query string
            limit: Max results
            expand: Fields to expand

        Returns:
            List of matching content
        """
        params: dict[str, Any] = {
            "cql": cql,
            "limit": limit,
        }
        if expand:
            params["expand"] = ",".join(expand)

        result = self._request("GET", "/content/search", params=params)
        return result.get("results", [])

    # -------------------------------------------------------------------------
    # User API
    # -------------------------------------------------------------------------

    def get_current_user(self) -> dict[str, Any]:
        """
        Get the current authenticated user.

        Returns:
            User data
        """
        return self._request("GET", "/user/current")

    # -------------------------------------------------------------------------
    # Child Pages API
    # -------------------------------------------------------------------------

    def get_child_pages(
        self,
        parent_id: str,
        limit: int = 100,
        expand: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get child pages of a parent.

        Args:
            parent_id: Parent page ID
            limit: Max results
            expand: Fields to expand

        Returns:
            List of child pages
        """
        params: dict[str, Any] = {"limit": limit}
        if expand:
            params["expand"] = ",".join(expand)

        result = self._request(
            "GET",
            f"/content/{parent_id}/child/page",
            params=params,
        )
        return result.get("results", [])
