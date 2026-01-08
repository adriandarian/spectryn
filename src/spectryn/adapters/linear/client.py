"""
Linear API Client - GraphQL client for Linear API.

This handles the raw HTTP/GraphQL communication with Linear.
The LinearAdapter uses this to implement the IssueTrackerPort.

Linear API Documentation: https://developers.linear.app/docs/graphql/working-with-the-graphql-api
"""

import logging
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter

from spectryn.adapters.async_base import (
    RETRYABLE_STATUS_CODES,
    LinearRateLimiter,
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


class LinearApiClient:
    """
    Low-level Linear GraphQL API client.

    Handles authentication, request/response, rate limiting, and error handling.

    Features:
    - GraphQL API with automatic query building
    - API key authentication
    - Automatic retry with exponential backoff
    - Rate limiting with awareness of Linear's limits
    - Connection pooling
    """

    API_URL = "https://api.linear.app/graphql"

    # Default retry configuration
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_INITIAL_DELAY = 1.0
    DEFAULT_MAX_DELAY = 60.0
    DEFAULT_BACKOFF_FACTOR = 2.0
    DEFAULT_JITTER = 0.1

    # Default rate limiting (conservative for Linear)
    DEFAULT_REQUESTS_PER_SECOND = 1.0  # ~3600/hour, under 1500 limit
    DEFAULT_BURST_SIZE = 10

    # Connection pool settings
    DEFAULT_TIMEOUT = 30.0

    def __init__(
        self,
        api_key: str,
        api_url: str = API_URL,
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
        Initialize the Linear client.

        Args:
            api_key: Linear API key
            api_url: Linear GraphQL API URL
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
        self.api_key = api_key
        self.api_url = api_url
        self.dry_run = dry_run
        self.timeout = timeout
        self.logger = logging.getLogger("LinearApiClient")

        # Retry configuration
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.jitter = jitter

        # Rate limiting
        self._rate_limiter: LinearRateLimiter | None = None
        if requests_per_second is not None and requests_per_second > 0:
            self._rate_limiter = LinearRateLimiter(
                requests_per_second=requests_per_second,
                burst_size=burst_size,
            )

        # Headers for Linear API
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": api_key,
        }

        # Configure session with connection pooling
        self._session = requests.Session()
        self._session.headers.update(self.headers)

        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10)
        self._session.mount("https://", adapter)

        # Cache
        self._viewer: dict | None = None
        self._team_cache: dict[str, dict] = {}
        self._workflow_states_cache: dict[str, list[dict]] = {}

    # -------------------------------------------------------------------------
    # Core GraphQL Methods
    # -------------------------------------------------------------------------

    def execute(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
    ) -> dict[str, Any]:
        """
        Execute a GraphQL query/mutation.

        Args:
            query: GraphQL query or mutation
            variables: Query variables
            operation_name: Optional operation name

        Returns:
            GraphQL response data

        Raises:
            IssueTrackerError: On API errors
        """
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        if operation_name:
            payload["operationName"] = operation_name

        last_exception: Exception | None = None

        for attempt in range(self.max_retries + 1):
            if self._rate_limiter is not None:
                self._rate_limiter.acquire()

            try:
                response = self._session.post(
                    self.api_url,
                    json=payload,
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
                        raise RateLimitError(
                            "Linear rate limit exceeded",
                            retry_after=int(delay),
                        )
                    raise TransientError(f"Linear server error {response.status_code}")

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
            f"Request failed after {self.max_retries + 1} attempts", cause=last_exception
        )

    def query(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a GraphQL query (read operation)."""
        return self.execute(query, variables)

    def mutate(
        self,
        mutation: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Execute a GraphQL mutation (write operation).

        Respects dry_run mode.
        """
        if self.dry_run:
            self.logger.info("[DRY-RUN] Would execute mutation")
            return {}
        return self.execute(mutation, variables)

    def _handle_response(self, response: requests.Response) -> dict[str, Any]:
        """Handle GraphQL response and convert errors."""
        if response.status_code == 401:
            raise AuthenticationError("Linear authentication failed. Check your API key.")

        if response.status_code == 403:
            raise PermissionError("Permission denied")

        if not response.ok:
            raise IssueTrackerError(
                f"Linear API error {response.status_code}: {response.text[:500]}"
            )

        data = response.json()

        # Check for GraphQL errors
        if "errors" in data:
            errors = data["errors"]
            error_messages = [e.get("message", str(e)) for e in errors]

            # Check for specific error types
            for error in errors:
                extensions = error.get("extensions", {})
                error_type = extensions.get("type", "")

                if error_type == "authentication":
                    raise AuthenticationError(error_messages[0])
                if error_type == "forbidden":
                    raise PermissionError(error_messages[0])
                if "not found" in error_messages[0].lower():
                    raise NotFoundError(error_messages[0])

            raise IssueTrackerError(f"GraphQL errors: {'; '.join(error_messages)}")

        return data.get("data", {})

    # -------------------------------------------------------------------------
    # Viewer (Current User) API
    # -------------------------------------------------------------------------

    def get_viewer(self) -> dict[str, Any]:
        """Get the current authenticated user."""
        if self._viewer is None:
            query = """
                query Viewer {
                    viewer {
                        id
                        name
                        email
                        displayName
                    }
                }
            """
            data = self.query(query)
            self._viewer = data.get("viewer", {})
        return self._viewer

    def get_viewer_id(self) -> str:
        """Get the current user's ID."""
        return self.get_viewer().get("id", "")

    def test_connection(self) -> bool:
        """Test if the API connection and credentials are valid."""
        try:
            self.get_viewer()
            return True
        except IssueTrackerError:
            return False

    @property
    def is_connected(self) -> bool:
        """Check if the client has successfully connected."""
        return self._viewer is not None

    # -------------------------------------------------------------------------
    # Teams API
    # -------------------------------------------------------------------------

    def get_teams(self) -> list[dict[str, Any]]:
        """Get all teams the user has access to."""
        query = """
            query Teams {
                teams {
                    nodes {
                        id
                        key
                        name
                        description
                    }
                }
            }
        """
        data = self.query(query)
        return data.get("teams", {}).get("nodes", [])

    def get_team(self, team_id: str) -> dict[str, Any]:
        """Get a specific team by ID."""
        if team_id in self._team_cache:
            return self._team_cache[team_id]

        query = """
            query Team($id: String!) {
                team(id: $id) {
                    id
                    key
                    name
                    description
                }
            }
        """
        data = self.query(query, {"id": team_id})
        team = data.get("team", {})
        self._team_cache[team_id] = team
        return team

    def get_team_by_key(self, key: str) -> dict[str, Any] | None:
        """Get a team by its key (e.g., 'ENG')."""
        teams = self.get_teams()
        for team in teams:
            if team.get("key", "").upper() == key.upper():
                self._team_cache[team["id"]] = team
                return team
        return None

    # -------------------------------------------------------------------------
    # Workflow States API
    # -------------------------------------------------------------------------

    def get_workflow_states(self, team_id: str) -> list[dict[str, Any]]:
        """Get all workflow states for a team."""
        if team_id in self._workflow_states_cache:
            return self._workflow_states_cache[team_id]

        query = """
            query WorkflowStates($teamId: String!) {
                workflowStates(filter: { team: { id: { eq: $teamId } } }) {
                    nodes {
                        id
                        name
                        type
                        position
                        color
                    }
                }
            }
        """
        data = self.query(query, {"teamId": team_id})
        states = data.get("workflowStates", {}).get("nodes", [])
        # Sort by position
        states.sort(key=lambda x: x.get("position", 0))
        self._workflow_states_cache[team_id] = states
        return states

    def get_workflow_state_by_name(
        self,
        team_id: str,
        name: str,
    ) -> dict[str, Any] | None:
        """Get a workflow state by name."""
        states = self.get_workflow_states(team_id)
        name_lower = name.lower()
        for state in states:
            if state.get("name", "").lower() == name_lower:
                return state
        return None

    # -------------------------------------------------------------------------
    # Issues API
    # -------------------------------------------------------------------------

    def get_issue(self, issue_id: str) -> dict[str, Any]:
        """
        Get an issue by ID or identifier.

        Args:
            issue_id: Issue UUID or identifier (e.g., 'ENG-123')
        """
        query = """
            query Issue($id: String!) {
                issue(id: $id) {
                    id
                    identifier
                    title
                    description
                    priority
                    estimate
                    state {
                        id
                        name
                        type
                    }
                    assignee {
                        id
                        name
                        email
                    }
                    team {
                        id
                        key
                        name
                    }
                    parent {
                        id
                        identifier
                    }
                    children {
                        nodes {
                            id
                            identifier
                            title
                            state {
                                name
                            }
                        }
                    }
                    labels {
                        nodes {
                            id
                            name
                            color
                        }
                    }
                    comments {
                        nodes {
                            id
                            body
                            user {
                                name
                            }
                            createdAt
                        }
                    }
                }
            }
        """
        data = self.query(query, {"id": issue_id})
        issue = data.get("issue")
        if not issue:
            raise NotFoundError(f"Issue not found: {issue_id}")
        return issue

    def search_issues(
        self,
        team_id: str | None = None,
        query_filter: str | None = None,
        first: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Search for issues.

        Args:
            team_id: Filter by team ID
            query_filter: Search query string
            first: Maximum number of results
        """
        # Build filter
        filter_parts = []
        if team_id:
            filter_parts.append(f'team: {{ id: {{ eq: "{team_id}" }} }}')

        filter_str = ""
        if filter_parts:
            filter_str = f"filter: {{ {', '.join(filter_parts)} }}"

        query = f"""
            query SearchIssues($first: Int!) {{
                issues({filter_str} first: $first) {{
                    nodes {{
                        id
                        identifier
                        title
                        description
                        priority
                        estimate
                        state {{
                            id
                            name
                            type
                        }}
                        assignee {{
                            id
                            name
                        }}
                        team {{
                            id
                            key
                        }}
                    }}
                }}
            }}
        """
        data = self.query(query, {"first": first})
        return data.get("issues", {}).get("nodes", [])

    def create_issue(
        self,
        team_id: str,
        title: str,
        description: str | None = None,
        priority: int | None = None,
        estimate: int | None = None,
        state_id: str | None = None,
        assignee_id: str | None = None,
        parent_id: str | None = None,
        label_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a new issue."""
        mutation = """
            mutation CreateIssue($input: IssueCreateInput!) {
                issueCreate(input: $input) {
                    success
                    issue {
                        id
                        identifier
                        title
                    }
                }
            }
        """

        input_data: dict[str, Any] = {
            "teamId": team_id,
            "title": title,
        }

        if description:
            input_data["description"] = description
        if priority is not None:
            input_data["priority"] = priority
        if estimate is not None:
            input_data["estimate"] = estimate
        if state_id:
            input_data["stateId"] = state_id
        if assignee_id:
            input_data["assigneeId"] = assignee_id
        if parent_id:
            input_data["parentId"] = parent_id
        if label_ids:
            input_data["labelIds"] = label_ids

        data = self.mutate(mutation, {"input": input_data})
        return data.get("issueCreate", {}).get("issue", {})

    def update_issue(
        self,
        issue_id: str,
        title: str | None = None,
        description: str | None = None,
        priority: int | None = None,
        estimate: int | None = None,
        state_id: str | None = None,
        assignee_id: str | None = None,
        parent_id: str | None = None,
    ) -> dict[str, Any]:
        """Update an existing issue."""
        mutation = """
            mutation UpdateIssue($id: String!, $input: IssueUpdateInput!) {
                issueUpdate(id: $id, input: $input) {
                    success
                    issue {
                        id
                        identifier
                        title
                    }
                }
            }
        """

        input_data: dict[str, Any] = {}

        if title is not None:
            input_data["title"] = title
        if description is not None:
            input_data["description"] = description
        if priority is not None:
            input_data["priority"] = priority
        if estimate is not None:
            input_data["estimate"] = estimate
        if state_id is not None:
            input_data["stateId"] = state_id
        if assignee_id is not None:
            input_data["assigneeId"] = assignee_id
        if parent_id is not None:
            input_data["parentId"] = parent_id

        if not input_data:
            return {}

        data = self.mutate(mutation, {"id": issue_id, "input": input_data})
        return data.get("issueUpdate", {}).get("issue", {})

    def get_issue_comments(self, issue_id: str) -> list[dict[str, Any]]:
        """Get all comments on an issue."""
        query = """
            query IssueComments($id: String!) {
                issue(id: $id) {
                    comments {
                        nodes {
                            id
                            body
                            user {
                                id
                                name
                                email
                            }
                            createdAt
                            updatedAt
                        }
                    }
                }
            }
        """
        data = self.query(query, {"id": issue_id})
        return data.get("issue", {}).get("comments", {}).get("nodes", [])

    def add_comment(self, issue_id: str, body: str) -> dict[str, Any]:
        """Add a comment to an issue."""
        mutation = """
            mutation CreateComment($input: CommentCreateInput!) {
                commentCreate(input: $input) {
                    success
                    comment {
                        id
                        body
                    }
                }
            }
        """

        data = self.mutate(mutation, {"input": {"issueId": issue_id, "body": body}})
        return data.get("commentCreate", {}).get("comment", {})

    # -------------------------------------------------------------------------
    # Projects (Epics) API
    # -------------------------------------------------------------------------

    def get_project(self, project_id: str) -> dict[str, Any]:
        """Get a project by ID."""
        query = """
            query Project($id: String!) {
                project(id: $id) {
                    id
                    name
                    description
                    state
                    progress
                    issues {
                        nodes {
                            id
                            identifier
                            title
                            state {
                                name
                            }
                        }
                    }
                }
            }
        """
        data = self.query(query, {"id": project_id})
        project = data.get("project")
        if not project:
            raise NotFoundError(f"Project not found: {project_id}")
        return project

    def get_project_issues(self, project_id: str) -> list[dict[str, Any]]:
        """Get all issues in a project."""
        project = self.get_project(project_id)
        return project.get("issues", {}).get("nodes", [])

    def create_project(
        self,
        name: str,
        team_ids: list[str],
        description: str | None = None,
    ) -> dict[str, Any]:
        """Create a new project."""
        mutation = """
            mutation CreateProject($input: ProjectCreateInput!) {
                projectCreate(input: $input) {
                    success
                    project {
                        id
                        name
                    }
                }
            }
        """

        input_data: dict[str, Any] = {
            "name": name,
            "teamIds": team_ids,
        }
        if description:
            input_data["description"] = description

        data = self.mutate(mutation, {"input": input_data})
        return data.get("projectCreate", {}).get("project", {})

    # -------------------------------------------------------------------------
    # Labels API
    # -------------------------------------------------------------------------

    def get_labels(self, team_id: str | None = None) -> list[dict[str, Any]]:
        """Get all labels, optionally filtered by team."""
        filter_str = ""
        if team_id:
            filter_str = f'filter: {{ team: {{ id: {{ eq: "{team_id}" }} }} }}'

        query = f"""
            query Labels {{
                issueLabels({filter_str}) {{
                    nodes {{
                        id
                        name
                        color
                        description
                    }}
                }}
            }}
        """
        data = self.query(query)
        return data.get("issueLabels", {}).get("nodes", [])

    def create_label(
        self,
        team_id: str,
        name: str,
        color: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Create a new label."""
        mutation = """
            mutation CreateLabel($input: IssueLabelCreateInput!) {
                issueLabelCreate(input: $input) {
                    success
                    issueLabel {
                        id
                        name
                        color
                    }
                }
            }
        """

        input_data: dict[str, Any] = {
            "teamId": team_id,
            "name": name,
        }
        if color:
            input_data["color"] = color
        if description:
            input_data["description"] = description

        data = self.mutate(mutation, {"input": input_data})
        return data.get("issueLabelCreate", {}).get("issueLabel", {})

    # -------------------------------------------------------------------------
    # Resource Cleanup
    # -------------------------------------------------------------------------

    def close(self) -> None:
        """Close the client and release resources."""
        self._session.close()
        self.logger.debug("Closed HTTP session")

    def __enter__(self) -> "LinearApiClient":
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
