"""
Async Linear Adapter - Async implementation of IssueTrackerPort for Linear.

Provides high-performance parallel operations using asyncio and aiohttp.
Use this for bulk operations that benefit from concurrent API calls.

Example:
    >>> async with AsyncLinearAdapter(api_key, team_key, dry_run=False) as adapter:
    ...     # Fetch multiple issues in parallel
    ...     issues = await adapter.get_issues_async(issue_keys)
    ...
    ...     # Update descriptions in parallel
    ...     results = await adapter.update_descriptions_async(updates)
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from types import TracebackType
from typing import TYPE_CHECKING, Any

from spectra.core.ports.async_tracker import AsyncIssueTrackerPort
from spectra.core.ports.issue_tracker import IssueData


if TYPE_CHECKING:
    import aiohttp

try:
    import aiohttp

    ASYNC_AVAILABLE = True
except ImportError:
    ASYNC_AVAILABLE = False
    aiohttp = None  # type: ignore[assignment]


DEFAULT_API_URL = "https://api.linear.app/graphql"


class AsyncLinearAdapter(AsyncIssueTrackerPort):
    """
    Async Linear implementation of AsyncIssueTrackerPort.

    Wraps aiohttp to provide high-level async operations for Linear's GraphQL API.
    Use via the context manager pattern for proper resource management.

    Requires aiohttp: pip install spectra[async]
    """

    def __init__(
        self,
        api_key: str,
        team_key: str,
        dry_run: bool = True,
        api_url: str = DEFAULT_API_URL,
        concurrency: int = 10,
        timeout: int = 30,
    ):
        """
        Initialize the async Linear adapter.

        Args:
            api_key: Linear API key
            team_key: Team key (e.g., 'ENG') to scope operations
            dry_run: If True, don't make changes
            api_url: Linear GraphQL API URL
            concurrency: Max parallel requests
            timeout: Request timeout in seconds
        """
        if not ASYNC_AVAILABLE:
            raise ImportError(
                "Async support requires aiohttp. Install with: pip install spectra[async]"
            )

        self.api_key = api_key
        self.team_key = team_key.upper()
        self._dry_run = dry_run
        self.api_url = api_url
        self._concurrency = concurrency
        self.timeout = timeout
        self.logger = logging.getLogger("AsyncLinearAdapter")

        self._session: aiohttp.ClientSession | None = None
        self._semaphore: Any = None
        self._team_id: str | None = None

    async def connect(self) -> None:
        """Establish async connection."""
        import asyncio

        self._semaphore = asyncio.Semaphore(self._concurrency)
        self._session = aiohttp.ClientSession(
            headers={
                "Content-Type": "application/json",
                "Authorization": self.api_key,
            },
            timeout=aiohttp.ClientTimeout(total=self.timeout),
        )

        # Fetch team ID
        team_query = """
        query GetTeam($teamKey: String!) {
            team(key: $teamKey) {
                id
            }
        }
        """
        data = await self._execute_graphql(team_query, {"teamKey": self.team_key})
        team = data.get("team", {})
        self._team_id = team.get("id")
        if not self._team_id:
            raise ValueError(f"Team not found: {self.team_key}")

        self.logger.debug("Async Linear connection established")

    async def disconnect(self) -> None:
        """Close async connection."""
        if self._session:
            await self._session.close()
            self._session = None
            self.logger.debug("Async Linear connection closed")

    async def __aenter__(self) -> AsyncLinearAdapter:
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.disconnect()

    def _ensure_connected(self) -> aiohttp.ClientSession:
        """Ensure client is connected."""
        if self._session is None:
            raise RuntimeError("Async adapter not connected. Use 'async with' context manager.")
        return self._session

    async def _execute_graphql(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a GraphQL query/mutation."""
        session = self._ensure_connected()

        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        async with self._semaphore, session.post(self.api_url, json=payload) as response:
            if response.status >= 400:
                text = await response.text()
                raise Exception(f"API error {response.status}: {text}")

            data = await response.json()
            if "errors" in data:
                errors = data["errors"]
                error_messages = [e.get("message", str(e)) for e in errors]
                raise Exception(f"GraphQL errors: {'; '.join(error_messages)}")

            return data.get("data", {})

    # -------------------------------------------------------------------------
    # Async Read Operations
    # -------------------------------------------------------------------------

    async def get_issue_async(self, issue_key: str) -> IssueData:
        """Fetch a single issue asynchronously."""
        query = """
        query GetIssue($identifier: String!) {
            issue(identifier: $identifier) {
                id
                identifier
                title
                description
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
                estimate
                parent {
                    id
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
        data = await self._execute_graphql(query, {"identifier": issue_key})
        issue = data.get("issue", {})
        return self._parse_issue(issue)

    async def get_issues_async(self, issue_keys: Sequence[str]) -> list[IssueData]:
        """Fetch multiple issues in parallel."""
        import asyncio

        tasks = [self.get_issue_async(key) for key in issue_keys]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        issues = []
        for result in results:
            if isinstance(result, IssueData):
                issues.append(result)
            else:
                self.logger.warning(f"Failed to fetch issue: {result}")

        return issues

    async def get_epic_children_async(self, epic_key: str) -> list[IssueData]:
        """Fetch all children of an epic (project) asynchronously."""
        # Try as project first
        query = """
        query GetProjectIssues($projectId: String!) {
            project(id: $projectId) {
                issues {
                    nodes {
                        id
                        identifier
                        title
                        description
                        state {
                            name
                        }
                        assignee {
                            email
                        }
                        estimate
                    }
                }
            }
        }
        """
        try:
            data = await self._execute_graphql(query, {"projectId": epic_key})
            project = data.get("project", {})
            issues = project.get("issues", {}).get("nodes", [])
            return [self._parse_issue(issue) for issue in issues]
        except Exception:
            pass

        # Try as parent issue
        parent_issue = await self.get_issue_async(epic_key)
        return parent_issue.subtasks if hasattr(parent_issue, "subtasks") else []

    async def search_issues_async(self, query: str, max_results: int = 50) -> list[IssueData]:
        """Search for issues asynchronously."""
        if not self._team_id:
            return []

        search_query = """
        query SearchIssues($teamId: String!, $first: Int!, $query: String!) {
            issues(
                filter: {
                    team: { id: { eq: $teamId } }
                    title: { containsIgnoreCase: $query }
                }
                first: $first
            ) {
                nodes {
                    id
                    identifier
                    title
                    description
                    state {
                        name
                    }
                    assignee {
                        email
                    }
                    estimate
                }
            }
        }
        """
        data = await self._execute_graphql(
            search_query, {"teamId": self._team_id, "first": max_results, "query": query}
        )
        issues = data.get("issues", {}).get("nodes", [])
        return [self._parse_issue(issue) for issue in issues]

    # -------------------------------------------------------------------------
    # Async Write Operations
    # -------------------------------------------------------------------------

    async def update_descriptions_async(
        self,
        updates: Sequence[tuple[str, Any]],
    ) -> list[tuple[str, bool, str | None]]:
        """Update multiple issue descriptions in parallel."""
        import asyncio

        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would update {len(updates)} descriptions")
            return [(key, True, None) for key, _ in updates]

        mutation = """
        mutation UpdateIssue($issueId: String!, $description: String!) {
            issueUpdate(id: $issueId, input: { description: $description }) {
                success
                issue {
                    id
                }
            }
        }
        """

        async def update_one(key: str, desc: Any) -> tuple[str, bool, str | None]:
            try:
                # Get issue ID from identifier
                issue = await self.get_issue_async(key)
                issue_id = issue.key if hasattr(issue, "key") else key

                await self._execute_graphql(
                    mutation, {"issueId": issue_id, "description": str(desc)}
                )
                return (key, True, None)
            except Exception as e:
                return (key, False, str(e))

        tasks = [update_one(key, desc) for key, desc in updates]
        return await asyncio.gather(*tasks)

    async def create_subtasks_async(
        self,
        subtasks: Sequence[dict[str, Any]],
    ) -> list[tuple[str | None, bool, str | None]]:
        """Create multiple subtasks in parallel."""
        import asyncio

        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would create {len(subtasks)} subtasks")
            return [(None, True, None) for _ in subtasks]

        if not self._team_id:
            return [(None, False, "Team ID not available") for _ in subtasks]

        mutation = """
        mutation CreateIssue($input: IssueCreateInput!) {
            issueCreate(input: $input) {
                success
                issue {
                    id
                    identifier
                }
            }
        }
        """

        async def create_one(st: dict[str, Any]) -> tuple[str | None, bool, str | None]:
            try:
                # Get parent issue ID
                parent_key = st.get("parent_key", "")
                parent_issue = await self.get_issue_async(parent_key)
                parent_id = parent_issue.key if hasattr(parent_issue, "key") else parent_key

                input_data: dict[str, Any] = {
                    "teamId": self._team_id,
                    "title": st.get("summary", "")[:255],
                    "description": str(st.get("description", "")),
                    "parentId": parent_id,
                }

                if st.get("story_points"):
                    input_data["estimate"] = int(st["story_points"])

                if st.get("assignee"):
                    input_data["assigneeId"] = st["assignee"]

                data = await self._execute_graphql(mutation, {"input": input_data})
                result = data.get("issueCreate", {})
                if result.get("success"):
                    issue = result.get("issue", {})
                    return (issue.get("identifier"), True, None)
                return (None, False, "Mutation failed")
            except Exception as e:
                return (None, False, str(e))

        tasks = [create_one(st) for st in subtasks]
        return await asyncio.gather(*tasks)

    async def transition_issues_async(
        self,
        transitions: Sequence[tuple[str, str]],
    ) -> list[tuple[str, bool, str | None]]:
        """Transition multiple issues in parallel."""
        import asyncio

        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would transition {len(transitions)} issues")
            return [(key, True, None) for key, _ in transitions]

        # First, get workflow states
        states_query = """
        query GetWorkflowStates($teamId: String!) {
            workflowStates(filter: { team: { id: { eq: $teamId } } }) {
                nodes {
                    id
                    name
                    type
                }
            }
        }
        """
        states_data = await self._execute_graphql(states_query, {"teamId": self._team_id})
        states = states_data.get("workflowStates", {}).get("nodes", [])
        state_map = {s["name"].lower(): s["id"] for s in states}

        mutation = """
        mutation UpdateIssueState($issueId: String!, $stateId: String!) {
            issueUpdate(id: $issueId, input: { stateId: $stateId }) {
                success
                issue {
                    id
                }
            }
        }
        """

        async def transition_one(key: str, status: str) -> tuple[str, bool, str | None]:
            try:
                issue = await self.get_issue_async(key)
                issue_id = issue.key if hasattr(issue, "key") else key

                # Find matching state
                status_lower = status.lower()
                state_id = None
                for name, sid in state_map.items():
                    if status_lower in name or name in status_lower:
                        state_id = sid
                        break

                if not state_id:
                    return (key, False, f"State not found: {status}")

                await self._execute_graphql(mutation, {"issueId": issue_id, "stateId": state_id})
                return (key, True, None)
            except Exception as e:
                return (key, False, str(e))

        tasks = [transition_one(key, status) for key, status in transitions]
        return await asyncio.gather(*tasks)

    async def add_comments_async(
        self,
        comments: Sequence[tuple[str, Any]],
    ) -> list[tuple[str, bool, str | None]]:
        """Add comments to multiple issues in parallel."""
        import asyncio

        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would add {len(comments)} comments")
            return [(key, True, None) for key, _ in comments]

        mutation = """
        mutation CreateComment($input: CommentCreateInput!) {
            commentCreate(input: $input) {
                success
                comment {
                    id
                }
            }
        }
        """

        async def add_one(key: str, body: Any) -> tuple[str, bool, str | None]:
            try:
                issue = await self.get_issue_async(key)
                issue_id = issue.key if hasattr(issue, "key") else key

                await self._execute_graphql(
                    mutation, {"input": {"body": str(body), "issueId": issue_id}}
                )
                return (key, True, None)
            except Exception as e:
                return (key, False, str(e))

        tasks = [add_one(key, body) for key, body in comments]
        return await asyncio.gather(*tasks)

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def _parse_issue(self, data: dict) -> IssueData:
        """Parse Linear API response into IssueData."""
        has_parent = data.get("parent") is not None
        issue_type = "Sub-task" if has_parent else "Story"

        state = data.get("state", {})
        status = state.get("name", "Unknown")

        assignee = None
        if data.get("assignee"):
            assignee = data["assignee"].get("email") or data["assignee"].get("name")

        estimate = data.get("estimate")

        subtasks = []
        for child in data.get("children", {}).get("nodes", []):
            subtasks.append(
                IssueData(
                    key=child.get("identifier", child.get("id", "")),
                    summary=child.get("title", ""),
                    status=child.get("state", {}).get("name", ""),
                    issue_type="Sub-task",
                )
            )

        comments = []
        for comment in data.get("comments", {}).get("nodes", []):
            comments.append(
                {
                    "id": comment.get("id"),
                    "body": comment.get("body"),
                    "author": comment.get("user", {}).get("name"),
                    "created": comment.get("createdAt"),
                }
            )

        return IssueData(
            key=data.get("identifier", data.get("id", "")),
            summary=data.get("title", ""),
            description=data.get("description"),
            status=status,
            issue_type=issue_type,
            assignee=assignee,
            story_points=float(estimate) if estimate else None,
            subtasks=subtasks,
            comments=comments,
        )


def is_async_available() -> bool:
    """Check if async operations are available."""
    return ASYNC_AVAILABLE


__all__ = ["ASYNC_AVAILABLE", "AsyncLinearAdapter", "is_async_available"]
