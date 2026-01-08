"""
Asana Adapter - Implements IssueTrackerPort for Asana.

Provides a thin wrapper around the Asana REST API so it can be used as an
output platform alongside Jira.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import requests


if TYPE_CHECKING:
    from .batch import AsanaBatchClient

from spectryn.core.exceptions import (
    AccessDeniedError,
    AuthenticationError,
    RateLimitError,
    ResourceNotFoundError,
    TrackerError,
    TransientError,
)
from spectryn.core.ports.config_provider import TrackerConfig
from spectryn.core.ports.issue_tracker import IssueData, IssueLink, IssueTrackerPort, LinkType


DEFAULT_BASE_URL = "https://app.asana.com/api/1.0"

# Standard custom field names
STORY_POINTS_FIELD = "Story Points"
PRIORITY_FIELD = "Priority"


class AsanaAdapter(IssueTrackerPort):
    """Asana implementation of the IssueTrackerPort."""

    def __init__(
        self,
        config: TrackerConfig,
        dry_run: bool = True,
        *,
        session: requests.Session | None = None,
        base_url: str | None = None,
        timeout: int = 30,
        custom_field_mappings: dict[str, str] | None = None,
    ) -> None:
        """
        Initialize the Asana adapter.

        Args:
            config: Tracker configuration (uses api_token and project_key).
            dry_run: If True, do not make state-changing requests.
            session: Optional custom requests session for testing.
            base_url: Optional override for Asana API URL.
            timeout: Request timeout in seconds.
            custom_field_mappings: Mapping of field names to Asana custom field GIDs.
        """
        self.config = config
        self._dry_run = dry_run
        self._session = session or requests.Session()
        self.base_url = (base_url or config.url or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self._connected = False
        self.logger = logging.getLogger("AsanaAdapter")

        # Custom field mappings: name -> GID
        self._custom_field_mappings = custom_field_mappings or {}
        self._custom_fields_cache: dict[str, dict[str, Any]] | None = None
        self._batch_client: AsanaBatchClient | None = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def name(self) -> str:
        return "Asana"

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.config.api_token}"}

    def _build_url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        url = self._build_url(path)
        response = self._session.request(
            method,
            url,
            headers=self._headers,
            params=params,
            json=json,
            timeout=self.timeout,
        )

        if response.status_code >= 400:
            self._handle_error(response)

        try:
            payload = response.json()
        except ValueError as exc:  # pragma: no cover - defensive
            raise TrackerError("Invalid response from Asana API") from exc

        return payload.get("data", payload)

    def _request_paginated(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> list[Any]:
        """
        Make a paginated GET request, following next_page cursors.

        Args:
            path: API endpoint path.
            params: Query parameters.
            limit: Optional maximum number of results to return.

        Returns:
            List of all items across all pages.
        """
        all_items: list[Any] = []
        request_params = dict(params) if params else {}
        offset: str | None = None

        while True:
            if offset:
                request_params["offset"] = offset

            url = self._build_url(path)
            response = self._session.request(
                "GET",
                url,
                headers=self._headers,
                params=request_params,
                timeout=self.timeout,
            )

            if response.status_code >= 400:
                self._handle_error(response)

            try:
                payload = response.json()
            except ValueError as exc:  # pragma: no cover - defensive
                raise TrackerError("Invalid response from Asana API") from exc

            data = payload.get("data", [])
            all_items.extend(data)

            # Check if we've hit the limit
            if limit and len(all_items) >= limit:
                return all_items[:limit]

            # Check for next page
            next_page = payload.get("next_page")
            if not next_page:
                break

            offset = next_page.get("offset")
            if not offset:
                break

        return all_items

    def _handle_error(self, response: requests.Response) -> None:
        status = response.status_code
        message = "Asana API request failed"
        try:
            payload = response.json()
            errors = payload.get("errors")
            if errors and isinstance(errors, list):
                message = errors[0].get("message", message)
        except ValueError:
            message = response.text or message

        if status == 401:
            raise AuthenticationError(message)
        if status == 403:
            raise AccessDeniedError(message)
        if status == 404:
            raise ResourceNotFoundError(message)
        if status == 429:
            raise RateLimitError(message)
        if status >= 500:
            raise TransientError(message)
        raise TrackerError(message)

    def _parse_issue(self, data: dict[str, Any]) -> IssueData:
        custom_fields = data.get("custom_fields", [])
        story_points = None
        for field in custom_fields:
            if field.get("name", "").lower() == "story points":
                try:
                    story_points = float(field.get("number_value", 0) or 0)
                except (TypeError, ValueError):
                    story_points = None

        assignee = data.get("assignee", {}) or {}
        status = "Done" if data.get("completed") else "In Progress"

        return IssueData(
            key=data.get("gid", ""),
            summary=data.get("name", ""),
            description=data.get("notes"),
            status=status,
            issue_type=data.get("resource_subtype", "task"),
            assignee=assignee.get("gid"),
            story_points=story_points,
            comments=[],
            links=[],
        )

    def _ensure_project(self, project_key: str | None) -> str:
        if project_key:
            return project_key
        if self.config.project_key:
            return self.config.project_key
        raise TrackerError("Asana project key is required for this operation")

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------
    def test_connection(self) -> bool:
        try:
            self.get_current_user()
            self._connected = True
            return True
        except TrackerError as exc:
            self.logger.debug("Asana connection failed: %s", exc)
            self._connected = False
            return False

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------
    def get_current_user(self) -> dict[str, Any]:
        result = self._request("GET", "/users/me")
        return result if isinstance(result, dict) else {}

    def get_issue(self, issue_key: str) -> IssueData:
        data = self._request(
            "GET",
            f"/tasks/{issue_key}",
            params={
                "opt_fields": "name,notes,completed,resource_subtype,assignee,custom_fields",
            },
        )
        return self._parse_issue(data)

    def get_epic_children(self, epic_key: str) -> list[IssueData]:
        project = self._ensure_project(epic_key)
        tasks = self._request_paginated(
            f"/projects/{project}/tasks",
            params={"opt_fields": "name,notes,completed,resource_subtype,assignee,custom_fields"},
        )
        return [self._parse_issue(task) for task in tasks]

    def get_issue_comments(self, issue_key: str) -> list[dict]:
        stories = self._request("GET", f"/tasks/{issue_key}/stories")
        return [story for story in stories if story.get("type") == "comment"]

    def get_issue_status(self, issue_key: str) -> str:
        issue = self.get_issue(issue_key)
        return issue.status

    def search_issues(self, query: str, max_results: int = 50) -> list[IssueData]:
        project = self._ensure_project(None)
        # Fetch all tasks (paginated), then filter client-side
        # Note: Asana doesn't support server-side text search on project tasks
        tasks = self._request_paginated(
            f"/projects/{project}/tasks",
            params={"opt_fields": "name,notes,completed,resource_subtype,assignee,custom_fields"},
        )

        matches: list[IssueData] = []
        query_lower = query.lower()
        for task in tasks:
            name = task.get("name", "").lower()
            if query_lower in name:
                matches.append(self._parse_issue(task))
            if len(matches) >= max_results:
                break
        return matches

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------
    def update_issue_description(self, issue_key: str, description: Any) -> bool:
        if self._dry_run:
            return True
        self._request("PUT", f"/tasks/{issue_key}", json={"data": {"notes": description}})
        return True

    def update_issue_story_points(self, issue_key: str, story_points: float) -> bool:
        if self._dry_run:
            self.logger.debug(
                "Dry run: would update story points for %s to %s", issue_key, story_points
            )
            return True

        self._request(
            "PUT",
            f"/tasks/{issue_key}",
            json={"data": {"custom_fields": {self.config.story_points_field: story_points}}},
        )
        self.logger.info("Updated story points for %s to %s", issue_key, story_points)
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
        if self._dry_run:
            self.logger.debug("Dry run: skipping Asana subtask creation")
            return None

        payload: dict[str, Any] = {
            "name": summary,
            "notes": description,
            "projects": [project_key],
        }
        if assignee:
            payload["assignee"] = assignee
        if story_points is not None:
            payload["custom_fields"] = {self.config.story_points_field: story_points}

        data = self._request("POST", f"/tasks/{parent_key}/subtasks", json={"data": payload})
        gid = data.get("gid") if isinstance(data, dict) else None
        return str(gid) if gid is not None else None

    def update_subtask(
        self,
        issue_key: str,
        description: Any | None = None,
        story_points: int | None = None,
        assignee: str | None = None,
        priority_id: str | None = None,
    ) -> bool:
        if self._dry_run:
            return True

        payload: dict[str, Any] = {}
        if description is not None:
            payload["notes"] = description
        if story_points is not None:
            payload.setdefault("custom_fields", {})[self.config.story_points_field] = story_points
        if assignee is not None:
            payload["assignee"] = assignee

        if not payload:
            return True

        self._request("PUT", f"/tasks/{issue_key}", json={"data": payload})
        return True

    def add_comment(self, issue_key: str, body: Any) -> bool:
        if self._dry_run:
            return True
        self._request("POST", f"/tasks/{issue_key}/stories", json={"data": {"text": str(body)}})
        return True

    def transition_issue(self, issue_key: str, target_status: str) -> bool:
        if self._dry_run:
            return True
        completed = target_status.lower() in {"done", "complete", "completed"}
        self._request("PUT", f"/tasks/{issue_key}", json={"data": {"completed": completed}})
        return True

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------
    def get_available_transitions(self, issue_key: str) -> list[dict]:
        return [
            {"name": "In Progress", "key": "in_progress"},
            {"name": "Done", "key": "done"},
        ]

    def format_description(self, markdown: str) -> str:
        return markdown

    # ------------------------------------------------------------------
    # Link operations (not supported by Asana)
    # ------------------------------------------------------------------
    def create_link(self, source_key: str, target_key: str, link_type: LinkType) -> bool:
        self.logger.debug(
            "Asana does not support explicit issue links; requested %s from %s to %s",
            link_type,
            source_key,
            target_key,
        )
        return False

    def delete_link(
        self, source_key: str, target_key: str, link_type: LinkType | None = None
    ) -> bool:
        self.logger.debug(
            "Asana does not support deleting explicit links; requested %s from %s to %s",
            link_type,
            source_key,
            target_key,
        )
        return False

    def get_issue_links(self, issue_key: str) -> list[IssueLink]:
        self.logger.debug("Asana issue links not supported for %s", issue_key)
        return []

    # ------------------------------------------------------------------
    # Batch operations
    # ------------------------------------------------------------------
    @property
    def batch_client(self) -> AsanaBatchClient:
        """Get the batch client for bulk operations."""
        if self._batch_client is None:
            from .batch import AsanaBatchClient

            self._batch_client = AsanaBatchClient(
                session=self._session,
                base_url=self.base_url,
                api_token=self.config.api_token,
                dry_run=self._dry_run,
                timeout=self.timeout,
            )
        return self._batch_client

    # ------------------------------------------------------------------
    # Custom fields
    # ------------------------------------------------------------------
    def get_project_custom_fields(self, project_key: str | None = None) -> list[dict[str, Any]]:
        """
        Get custom fields available for a project.

        Args:
            project_key: Project GID. Uses config if not provided.

        Returns:
            List of custom field definitions with gid, name, type, etc.
        """
        project = self._ensure_project(project_key)
        result = self._request(
            "GET",
            f"/projects/{project}/custom_field_settings",
            params={"opt_fields": "custom_field,custom_field.name,custom_field.type"},
        )

        fields = []
        for setting in result if isinstance(result, list) else []:
            cf = setting.get("custom_field", {})
            if cf:
                fields.append(cf)
        return fields

    def get_custom_field_gid(self, field_name: str) -> str | None:
        """
        Get the GID for a custom field by name.

        Uses cached field mappings when available.

        Args:
            field_name: Custom field name (case-insensitive).

        Returns:
            Field GID or None if not found.
        """
        # Check explicit mappings first
        if field_name in self._custom_field_mappings:
            return self._custom_field_mappings[field_name]

        # Load and cache fields if needed
        if self._custom_fields_cache is None:
            self._custom_fields_cache = {}
            try:
                fields = self.get_project_custom_fields()
                for field in fields:
                    name = field.get("name", "")
                    gid = field.get("gid", "")
                    if name and gid:
                        self._custom_fields_cache[name.lower()] = field
            except TrackerError:
                pass

        # Look up by name (case-insensitive)
        cache = self._custom_fields_cache
        if cache is None:
            return None
        cached_field: dict[str, Any] | None = cache.get(field_name.lower())
        return cached_field.get("gid") if cached_field else None

    def set_custom_field(
        self,
        issue_key: str,
        field_name: str,
        value: Any,
    ) -> bool:
        """
        Set a custom field value on a task.

        Args:
            issue_key: Task GID.
            field_name: Custom field name.
            value: Value to set (type depends on field type).

        Returns:
            True if successful.
        """
        if self._dry_run:
            self.logger.debug("Dry run: would set %s=%s on task %s", field_name, value, issue_key)
            return True

        field_gid = self.get_custom_field_gid(field_name)
        if not field_gid:
            self.logger.warning("Custom field not found: %s", field_name)
            return False

        self._request(
            "PUT",
            f"/tasks/{issue_key}",
            json={"data": {"custom_fields": {field_gid: value}}},
        )
        return True

    def get_custom_field_value(
        self,
        issue_key: str,
        field_name: str,
    ) -> Any:
        """
        Get a custom field value from a task.

        Args:
            issue_key: Task GID.
            field_name: Custom field name.

        Returns:
            Field value or None if not found.
        """
        data = self._request(
            "GET",
            f"/tasks/{issue_key}",
            params={"opt_fields": "custom_fields"},
        )

        for field in data.get("custom_fields", []):
            if field.get("name", "").lower() == field_name.lower():
                # Return appropriate value based on field type
                if "number_value" in field:
                    return field["number_value"]
                if "text_value" in field:
                    return field["text_value"]
                if "enum_value" in field:
                    return field.get("enum_value", {}).get("name")
                if "multi_enum_values" in field:
                    return [v.get("name") for v in field.get("multi_enum_values", [])]
                return field.get("display_value")

        return None
