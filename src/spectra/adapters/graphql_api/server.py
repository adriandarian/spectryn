"""
GraphQL Server Implementation.

Provides a lightweight GraphQL server that:
- Parses and executes GraphQL queries
- Supports queries, mutations, and subscriptions
- Integrates with Spectra's domain layer
- Can run as HTTP server or be embedded
"""

import base64
import http.server
import json
import logging
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from spectra.core.domain.entities import Epic, Subtask, UserStory
from spectra.core.domain.enums import Priority, Status
from spectra.core.domain.events import EventBus
from spectra.core.ports.graphql_api import (
    ExecutionContext,
    GraphQLRequest,
    GraphQLResponse,
    GraphQLServerPort,
    RequestMiddleware,
    ResolverRegistry,
    ResponseMiddleware,
    ServerConfig,
    ServerStats,
    SubscriptionHandler,
)

from .schema import (
    SCHEMA_SDL,
    GraphQLEpic,
    GraphQLPriority,
    GraphQLStatus,
    GraphQLStory,
    GraphQLSubtask,
    GraphQLSyncOperation,
    GraphQLSyncResult,
    GraphQLWorkspaceStats,
)


logger = logging.getLogger(__name__)


# Status/Priority mapping
STATUS_MAP = {
    Status.PLANNED: GraphQLStatus.PLANNED,
    Status.OPEN: GraphQLStatus.OPEN,
    Status.IN_PROGRESS: GraphQLStatus.IN_PROGRESS,
    Status.IN_REVIEW: GraphQLStatus.IN_REVIEW,
    Status.DONE: GraphQLStatus.DONE,
    Status.CANCELLED: GraphQLStatus.CANCELLED,
}

PRIORITY_MAP = {
    Priority.CRITICAL: GraphQLPriority.CRITICAL,
    Priority.HIGH: GraphQLPriority.HIGH,
    Priority.MEDIUM: GraphQLPriority.MEDIUM,
    Priority.LOW: GraphQLPriority.LOW,
}


def convert_subtask(subtask: Subtask) -> GraphQLSubtask:
    """Convert domain Subtask to GraphQL Subtask."""
    return GraphQLSubtask(
        id=subtask.id,
        number=subtask.number,
        name=subtask.name,
        description=subtask.description or None,
        story_points=subtask.story_points,
        status=STATUS_MAP.get(subtask.status, GraphQLStatus.PLANNED),
        priority=PRIORITY_MAP.get(subtask.priority, None) if subtask.priority else None,
        assignee=subtask.assignee,
        external_key=str(subtask.external_key) if subtask.external_key else None,
    )


def convert_story(story: UserStory, epic: Epic | None = None) -> GraphQLStory:
    """Convert domain UserStory to GraphQL Story."""
    return GraphQLStory(
        id=str(story.id),
        title=story.title,
        description=story.description.to_markdown() if story.description else None,
        acceptance_criteria=list(story.acceptance_criteria.items)
        if story.acceptance_criteria
        else [],
        technical_notes=story.technical_notes or None,
        story_points=story.story_points,
        priority=PRIORITY_MAP.get(story.priority, GraphQLPriority.MEDIUM),
        status=STATUS_MAP.get(story.status, GraphQLStatus.PLANNED),
        assignee=story.assignee,
        labels=story.labels,
        sprint=story.sprint,
        subtasks=[convert_subtask(st) for st in story.subtasks],
        commits=[{"hash": c.hash, "message": c.message} for c in story.commits],
        comments=[c.to_dict() for c in story.comments],
        attachments=story.attachments,
        external_key=str(story.external_key) if story.external_key else None,
        external_url=story.external_url,
        last_synced=story.last_synced,
        sync_status=story.sync_status,
    )


def convert_epic(epic: Epic) -> GraphQLEpic:
    """Convert domain Epic to GraphQL Epic."""
    return GraphQLEpic(
        key=str(epic.key),
        title=epic.title,
        summary=epic.summary or None,
        description=epic.description or None,
        status=STATUS_MAP.get(epic.status, GraphQLStatus.PLANNED),
        priority=PRIORITY_MAP.get(epic.priority, GraphQLPriority.MEDIUM),
        parent_key=str(epic.parent_key) if epic.parent_key else None,
        level=epic.level,
        stories=[convert_story(s, epic) for s in epic.stories],
        child_epics=[convert_epic(e) for e in epic.child_epics],
        created_at=epic.created_at,
        updated_at=epic.updated_at,
    )


def encode_cursor(value: str, offset: int) -> str:
    """Encode a cursor for pagination."""
    data = f"{value}:{offset}"
    return base64.b64encode(data.encode()).decode()


def decode_cursor(cursor: str) -> tuple[str, int]:
    """Decode a pagination cursor."""
    try:
        data = base64.b64decode(cursor.encode()).decode()
        parts = data.rsplit(":", 1)
        return parts[0], int(parts[1])
    except Exception:
        return "", 0


class SimpleResolverRegistry(ResolverRegistry):
    """Simple implementation of resolver registry."""

    def __init__(self) -> None:
        """Initialize the registry."""
        self._resolvers: dict[str, dict[str, Callable[..., Any]]] = {
            "Query": {},
            "Mutation": {},
            "Subscription": {},
        }

    def register_query(self, field_name: str, resolver: Callable[..., Any]) -> None:
        """Register a query resolver."""
        self._resolvers["Query"][field_name] = resolver

    def register_mutation(self, field_name: str, resolver: Callable[..., Any]) -> None:
        """Register a mutation resolver."""
        self._resolvers["Mutation"][field_name] = resolver

    def register_subscription(
        self,
        field_name: str,
        subscribe: Callable[..., Any],
        resolve: Callable[..., Any] | None = None,
    ) -> None:
        """Register a subscription resolver."""
        self._resolvers["Subscription"][field_name] = subscribe

    def register_type_resolver(
        self,
        type_name: str,
        field_name: str,
        resolver: Callable[..., Any],
    ) -> None:
        """Register a field resolver for a specific type."""
        if type_name not in self._resolvers:
            self._resolvers[type_name] = {}
        self._resolvers[type_name][field_name] = resolver

    def get_resolver(
        self,
        type_name: str,
        field_name: str,
    ) -> Callable[..., Any] | None:
        """Get a registered resolver."""
        type_resolvers = self._resolvers.get(type_name, {})
        return type_resolvers.get(field_name)


@dataclass
class DataStore:
    """
    In-memory data store for the GraphQL API.

    In a real implementation, this would be connected to the
    actual file parsing and tracker sync systems.
    """

    epics: dict[str, Epic] = field(default_factory=dict)
    active_syncs: dict[str, GraphQLSyncResult] = field(default_factory=dict)
    sync_history: list[GraphQLSyncResult] = field(default_factory=list)


class SpectraGraphQLServer(GraphQLServerPort):
    """
    GraphQL server for Spectra API.

    This implementation provides:
    - A simple query parser and executor
    - HTTP server for handling requests
    - Integration with domain entities
    - Subscription support via WebSocket bridge
    """

    def __init__(
        self,
        config: ServerConfig | None = None,
        event_bus: EventBus | None = None,
        data_store: DataStore | None = None,
    ):
        """
        Initialize the GraphQL server.

        Args:
            config: Server configuration.
            event_bus: Event bus for domain events.
            data_store: Data store for entities.
        """
        self._config = config or ServerConfig()
        self._event_bus = event_bus
        self._data_store = data_store or DataStore()

        self._registry = SimpleResolverRegistry()
        self._request_middlewares: list[RequestMiddleware] = []
        self._response_middlewares: list[ResponseMiddleware] = []
        self._subscriptions: dict[str, tuple[GraphQLRequest, SubscriptionHandler]] = {}

        self._server: http.server.HTTPServer | None = None
        self._server_thread: threading.Thread | None = None
        self._running = False
        self._stats = ServerStats()

        self._setup_resolvers()
        self._logger = logging.getLogger("SpectraGraphQLServer")

    def _setup_resolvers(self) -> None:
        """Set up default resolvers."""
        # Query resolvers
        self._registry.register_query("epic", self._resolve_epic)
        self._registry.register_query("epics", self._resolve_epics)
        self._registry.register_query("story", self._resolve_story)
        self._registry.register_query("stories", self._resolve_stories)
        self._registry.register_query("searchStories", self._resolve_search_stories)
        self._registry.register_query("workspaceStats", self._resolve_workspace_stats)
        self._registry.register_query("health", self._resolve_health)
        self._registry.register_query("activeSyncs", self._resolve_active_syncs)
        self._registry.register_query("syncHistory", self._resolve_sync_history)

        # Mutation resolvers
        self._registry.register_mutation("sync", self._resolve_sync)
        self._registry.register_mutation("cancelSync", self._resolve_cancel_sync)
        self._registry.register_mutation("createStory", self._resolve_create_story)
        self._registry.register_mutation("updateStory", self._resolve_update_story)
        self._registry.register_mutation("deleteStory", self._resolve_delete_story)
        self._registry.register_mutation("updateStoryStatus", self._resolve_update_story_status)
        self._registry.register_mutation("assignStory", self._resolve_assign_story)
        self._registry.register_mutation("validateMarkdown", self._resolve_validate_markdown)

    # ========================================================================
    # Query Resolvers
    # ========================================================================

    def _resolve_epic(
        self,
        context: ExecutionContext,
        key: str,
    ) -> dict[str, Any] | None:
        """Resolve a single epic by key."""
        epic = self._data_store.epics.get(key)
        if epic:
            return convert_epic(epic).to_dict()
        return None

    def _resolve_epics(
        self,
        context: ExecutionContext,
        filter: dict[str, Any] | None = None,
        pagination: dict[str, Any] | None = None,
        sort: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Resolve list of epics with filtering and pagination."""
        epics = list(self._data_store.epics.values())

        # Apply filters
        if filter:
            if filter.get("status"):
                statuses = {Status[s] for s in filter["status"]}
                epics = [e for e in epics if e.status in statuses]
            if filter.get("priority"):
                priorities = {Priority[p] for p in filter["priority"]}
                epics = [e for e in epics if e.priority in priorities]
            if filter.get("titleContains"):
                search = filter["titleContains"].lower()
                epics = [e for e in epics if search in e.title.lower()]
            if filter.get("keyPrefix"):
                prefix = filter["keyPrefix"]
                epics = [e for e in epics if str(e.key).startswith(prefix)]

        # Apply sorting
        if sort:
            field_name = sort.get("field", "key")
            ascending = sort.get("ascending", True)
            reverse = not ascending
            epics = sorted(epics, key=lambda e: getattr(e, field_name, ""), reverse=reverse)

        # Apply pagination
        first = pagination.get("first", 10) if pagination else 10
        after = pagination.get("after") if pagination else None

        start_idx = 0
        if after:
            _, offset = decode_cursor(after)
            start_idx = offset + 1

        end_idx = start_idx + first
        paginated = epics[start_idx:end_idx]

        # Build edges
        edges = []
        for i, epic in enumerate(paginated):
            cursor = encode_cursor(str(epic.key), start_idx + i)
            edges.append(
                {
                    "node": convert_epic(epic).to_dict(),
                    "cursor": cursor,
                }
            )

        page_info = {
            "hasNextPage": end_idx < len(epics),
            "hasPreviousPage": start_idx > 0,
            "startCursor": edges[0]["cursor"] if edges else None,
            "endCursor": edges[-1]["cursor"] if edges else None,
            "totalCount": len(epics),
        }

        return {"edges": edges, "pageInfo": page_info}

    def _resolve_story(
        self,
        context: ExecutionContext,
        id: str,
    ) -> dict[str, Any] | None:
        """Resolve a single story by ID."""
        for epic in self._data_store.epics.values():
            for story in epic.stories:
                if str(story.id) == id:
                    return convert_story(story, epic).to_dict()
        return None

    def _resolve_stories(
        self,
        context: ExecutionContext,
        filter: dict[str, Any] | None = None,
        pagination: dict[str, Any] | None = None,
        sort: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Resolve list of stories with filtering and pagination."""
        stories: list[tuple[UserStory, Epic]] = []
        for epic in self._data_store.epics.values():
            for story in epic.stories:
                stories.append((story, epic))

        # Apply filters
        if filter:
            if filter.get("status"):
                statuses = {Status[s] for s in filter["status"]}
                stories = [(s, e) for s, e in stories if s.status in statuses]
            if filter.get("priority"):
                priorities = {Priority[p] for p in filter["priority"]}
                stories = [(s, e) for s, e in stories if s.priority in priorities]
            if filter.get("assignee"):
                assignee = filter["assignee"]
                stories = [(s, e) for s, e in stories if s.assignee == assignee]
            if filter.get("labels"):
                required_labels = set(filter["labels"])
                stories = [(s, e) for s, e in stories if required_labels.issubset(set(s.labels))]
            if filter.get("sprint"):
                sprint = filter["sprint"]
                stories = [(s, e) for s, e in stories if s.sprint == sprint]
            if filter.get("titleContains"):
                search = filter["titleContains"].lower()
                stories = [(s, e) for s, e in stories if search in s.title.lower()]
            if filter.get("minPoints") is not None:
                min_pts = filter["minPoints"]
                stories = [(s, e) for s, e in stories if s.story_points >= min_pts]
            if filter.get("maxPoints") is not None:
                max_pts = filter["maxPoints"]
                stories = [(s, e) for s, e in stories if s.story_points <= max_pts]
            if filter.get("epicKey"):
                epic_key = filter["epicKey"]
                stories = [(s, e) for s, e in stories if str(e.key) == epic_key]

        # Apply sorting
        if sort:
            field_name = sort.get("field", "id")
            ascending = sort.get("ascending", True)
            reverse = not ascending

            def get_sort_key(item: tuple[UserStory, Epic]) -> Any:
                story, _ = item
                return getattr(story, field_name, "")

            stories = sorted(stories, key=get_sort_key, reverse=reverse)

        # Apply pagination
        first = pagination.get("first", 10) if pagination else 10
        after = pagination.get("after") if pagination else None

        start_idx = 0
        if after:
            _, offset = decode_cursor(after)
            start_idx = offset + 1

        end_idx = start_idx + first
        paginated = stories[start_idx:end_idx]

        # Build edges
        edges = []
        for i, (story, epic) in enumerate(paginated):
            cursor = encode_cursor(str(story.id), start_idx + i)
            edges.append(
                {
                    "node": convert_story(story, epic).to_dict(),
                    "cursor": cursor,
                }
            )

        page_info = {
            "hasNextPage": end_idx < len(stories),
            "hasPreviousPage": start_idx > 0,
            "startCursor": edges[0]["cursor"] if edges else None,
            "endCursor": edges[-1]["cursor"] if edges else None,
            "totalCount": len(stories),
        }

        return {"edges": edges, "pageInfo": page_info}

    def _resolve_search_stories(
        self,
        context: ExecutionContext,
        query: str,
        pagination: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Search stories by text."""
        query_lower = query.lower()
        stories: list[tuple[UserStory, Epic, float]] = []

        for epic in self._data_store.epics.values():
            for story in epic.stories:
                score = 0.0

                # Title match (highest weight)
                if query_lower in story.title.lower():
                    score += 10.0

                # Description match
                if story.description and query_lower in story.description.to_markdown().lower():
                    score += 5.0

                # Acceptance criteria match
                if story.acceptance_criteria:
                    for ac in story.acceptance_criteria.items:
                        if query_lower in ac.lower():
                            score += 3.0
                            break

                # Label match
                for label in story.labels:
                    if query_lower in label.lower():
                        score += 2.0

                if score > 0:
                    stories.append((story, epic, score))

        # Sort by relevance score
        stories.sort(key=lambda x: x[2], reverse=True)

        # Apply pagination
        first = pagination.get("first", 10) if pagination else 10
        after = pagination.get("after") if pagination else None

        start_idx = 0
        if after:
            _, offset = decode_cursor(after)
            start_idx = offset + 1

        end_idx = start_idx + first
        paginated = stories[start_idx:end_idx]

        # Build edges
        edges = []
        for i, (story, epic, _) in enumerate(paginated):
            cursor = encode_cursor(str(story.id), start_idx + i)
            edges.append(
                {
                    "node": convert_story(story, epic).to_dict(),
                    "cursor": cursor,
                }
            )

        page_info = {
            "hasNextPage": end_idx < len(stories),
            "hasPreviousPage": start_idx > 0,
            "startCursor": edges[0]["cursor"] if edges else None,
            "endCursor": edges[-1]["cursor"] if edges else None,
            "totalCount": len(stories),
        }

        return {"edges": edges, "pageInfo": page_info}

    def _resolve_workspace_stats(
        self,
        context: ExecutionContext,
    ) -> dict[str, Any]:
        """Resolve workspace statistics."""
        stats = GraphQLWorkspaceStats()

        for epic in self._data_store.epics.values():
            stats.total_epics += 1

            for story in epic.stories:
                stats.total_stories += 1
                stats.total_subtasks += len(story.subtasks)
                stats.total_story_points += story.story_points

                if story.status == Status.DONE:
                    stats.completed_story_points += story.story_points

                status_name = story.status.name
                stats.stories_by_status[status_name] = (
                    stats.stories_by_status.get(status_name, 0) + 1
                )

                priority_name = story.priority.name
                stats.stories_by_priority[priority_name] = (
                    stats.stories_by_priority.get(priority_name, 0) + 1
                )

        if stats.total_stories > 0:
            stats.average_story_points = stats.total_story_points / stats.total_stories
            stats.completion_percentage = (
                (stats.completed_story_points / stats.total_story_points) * 100
                if stats.total_story_points > 0
                else 0.0
            )

        return stats.to_dict()

    def _resolve_health(
        self,
        context: ExecutionContext,
    ) -> dict[str, Any]:
        """Resolve server health status."""

        uptime = (datetime.now() - self._stats.started_at).total_seconds()

        # Get memory usage (rough estimate)
        try:
            import resource

            memory_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 / 1024
        except ImportError:
            memory_mb = 0.0

        return {
            "healthy": True,
            "version": "1.0.0",
            "uptimeSeconds": uptime,
            "activeConnections": len(self._subscriptions),
            "memoryUsageMb": memory_mb,
        }

    def _resolve_active_syncs(
        self,
        context: ExecutionContext,
    ) -> list[dict[str, Any]]:
        """Resolve active sync sessions."""
        return [s.to_dict() for s in self._data_store.active_syncs.values()]

    def _resolve_sync_history(
        self,
        context: ExecutionContext,
        limit: int = 10,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Resolve sync history."""
        history = self._data_store.sync_history[offset : offset + limit]
        return [s.to_dict() for s in history]

    # ========================================================================
    # Mutation Resolvers
    # ========================================================================

    def _resolve_sync(
        self,
        context: ExecutionContext,
        input: dict[str, Any],
    ) -> dict[str, Any]:
        """Start a sync operation."""
        session_id = str(uuid4())
        started_at = datetime.now()

        # Create sync result (in progress)
        result = GraphQLSyncResult(
            success=False,
            session_id=session_id,
            operation=GraphQLSyncOperation[input.get("operation", "PUSH")],
            tracker=input.get("tracker", "JIRA"),
            epic_key=input.get("epicKey"),
            total_items=0,
            created=0,
            updated=0,
            matched=0,
            skipped=0,
            failed=0,
            changes=[],
            errors=[],
            started_at=started_at,
        )

        self._data_store.active_syncs[session_id] = result

        # In a real implementation, this would trigger the actual sync
        # For now, we just return the pending result
        return result.to_dict()

    def _resolve_cancel_sync(
        self,
        context: ExecutionContext,
        sessionId: str,
    ) -> bool:
        """Cancel an active sync."""
        if sessionId in self._data_store.active_syncs:
            del self._data_store.active_syncs[sessionId]
            return True
        return False

    def _resolve_create_story(
        self,
        context: ExecutionContext,
        epicKey: str,
        input: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a new story."""
        import uuid

        from spectra.core.domain.value_objects import AcceptanceCriteria, Description, StoryId

        epic = self._data_store.epics.get(epicKey)
        if not epic:
            raise ValueError(f"Epic not found: {epicKey}")

        # Generate a unique story ID
        story_id = StoryId(f"S-{uuid.uuid4().hex[:8].upper()}")

        # Parse description from string or structured input
        description = None
        if input.get("description"):
            desc_input = input["description"]
            if isinstance(desc_input, dict):
                description = Description(
                    role=desc_input.get("role", "user"),
                    want=desc_input.get("want", ""),
                    benefit=desc_input.get("benefit", ""),
                )
            else:
                # Try to parse from markdown, or create a simple one
                description = Description.from_markdown(str(desc_input))
                if not description:
                    # Fallback: use as "want" field
                    description = Description(
                        role="user",
                        want=str(desc_input),
                        benefit="achieve my goals",
                    )

        story = UserStory(
            id=story_id,
            title=input["title"],
            description=description,
            story_points=input.get("storyPoints", 0),
            priority=Priority[input.get("priority", "MEDIUM")],
            status=Status[input.get("status", "PLANNED")],
            assignee=input.get("assignee"),
            labels=input.get("labels", []),
            sprint=input.get("sprint"),
            acceptance_criteria=AcceptanceCriteria.from_list(input.get("acceptanceCriteria", [])),
            technical_notes=input.get("technicalNotes", ""),
        )

        epic.stories.append(story)
        return convert_story(story, epic).to_dict()

    def _resolve_update_story(
        self,
        context: ExecutionContext,
        id: str,
        input: dict[str, Any],
    ) -> dict[str, Any]:
        """Update an existing story."""
        from spectra.core.domain.value_objects import AcceptanceCriteria, Description

        for epic in self._data_store.epics.values():
            for story in epic.stories:
                if str(story.id) == id:
                    if "title" in input:
                        story.title = input["title"]
                    if "description" in input:
                        desc_input = input["description"]
                        if desc_input:
                            if isinstance(desc_input, dict):
                                story.description = Description(
                                    role=desc_input.get("role", "user"),
                                    want=desc_input.get("want", ""),
                                    benefit=desc_input.get("benefit", ""),
                                )
                            else:
                                # Try to parse from markdown, or create a simple one
                                parsed = Description.from_markdown(str(desc_input))
                                if parsed:
                                    story.description = parsed
                                else:
                                    story.description = Description(
                                        role="user",
                                        want=str(desc_input),
                                        benefit="achieve my goals",
                                    )
                        else:
                            story.description = None
                    if "storyPoints" in input:
                        story.story_points = input["storyPoints"]
                    if "priority" in input:
                        story.priority = Priority[input["priority"]]
                    if "status" in input:
                        story.status = Status[input["status"]]
                    if "assignee" in input:
                        story.assignee = input["assignee"]
                    if "labels" in input:
                        story.labels = input["labels"]
                    if "sprint" in input:
                        story.sprint = input["sprint"]
                    if "acceptanceCriteria" in input:
                        story.acceptance_criteria = AcceptanceCriteria.from_list(
                            input["acceptanceCriteria"]
                        )
                    if "technicalNotes" in input:
                        story.technical_notes = input["technicalNotes"]

                    return convert_story(story, epic).to_dict()

        raise ValueError(f"Story not found: {id}")

    def _resolve_delete_story(
        self,
        context: ExecutionContext,
        id: str,
    ) -> bool:
        """Delete a story."""
        for epic in self._data_store.epics.values():
            for i, story in enumerate(epic.stories):
                if str(story.id) == id:
                    epic.stories.pop(i)
                    return True
        return False

    def _resolve_update_story_status(
        self,
        context: ExecutionContext,
        id: str,
        status: str,
    ) -> dict[str, Any]:
        """Update story status."""
        for epic in self._data_store.epics.values():
            for story in epic.stories:
                if str(story.id) == id:
                    story.status = Status[status]
                    return convert_story(story, epic).to_dict()

        raise ValueError(f"Story not found: {id}")

    def _resolve_assign_story(
        self,
        context: ExecutionContext,
        id: str,
        assignee: str | None,
    ) -> dict[str, Any]:
        """Assign a story to a user."""
        for epic in self._data_store.epics.values():
            for story in epic.stories:
                if str(story.id) == id:
                    story.assignee = assignee
                    return convert_story(story, epic).to_dict()

        raise ValueError(f"Story not found: {id}")

    def _resolve_validate_markdown(
        self,
        context: ExecutionContext,
        path: str,
    ) -> dict[str, Any]:
        """Validate a markdown file."""
        # In a real implementation, this would call the validator
        return {
            "valid": True,
            "errors": [],
            "warnings": [],
            "path": path,
        }

    # ========================================================================
    # Server Port Implementation
    # ========================================================================

    async def start(self) -> None:
        """Start the GraphQL server."""
        self._start_sync()

    def _start_sync(self) -> None:
        """Synchronous start implementation."""
        if self._running:
            return

        server = self

        class GraphQLHandler(http.server.BaseHTTPRequestHandler):
            """HTTP handler for GraphQL requests."""

            def log_message(self, format: str, *args: Any) -> None:
                """Suppress default logging."""

            def do_OPTIONS(self) -> None:
                """Handle CORS preflight."""
                self.send_response(200)
                self._set_cors_headers()
                self.end_headers()

            def do_GET(self) -> None:
                """Handle GET requests (playground)."""
                if self.path == server._config.path:
                    if server._config.enable_playground:
                        self._serve_playground()
                    else:
                        self.send_error(405, "GET not allowed")
                else:
                    self.send_error(404, "Not Found")

            def do_POST(self) -> None:
                """Handle POST requests (GraphQL)."""
                if self.path == server._config.path:
                    self._handle_graphql()
                else:
                    self.send_error(404, "Not Found")

            def _set_cors_headers(self) -> None:
                """Set CORS headers."""
                if server._config.cors_origins:
                    origin = self.headers.get("Origin", "*")
                    if origin in server._config.cors_origins or "*" in server._config.cors_origins:
                        self.send_header("Access-Control-Allow-Origin", origin)
                        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                        self.send_header(
                            "Access-Control-Allow-Headers", "Content-Type, Authorization"
                        )

            def _serve_playground(self) -> None:
                """Serve GraphQL Playground HTML."""
                html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Spectra GraphQL Playground</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/graphql-playground-react/build/static/css/index.css" />
    <script src="https://cdn.jsdelivr.net/npm/graphql-playground-react/build/static/js/middleware.js"></script>
</head>
<body>
    <div id="root"></div>
    <script>
        window.addEventListener('load', function() {{
            GraphQLPlayground.init(document.getElementById('root'), {{
                endpoint: '{server._config.path}',
                settings: {{
                    'editor.theme': 'dark',
                    'editor.fontFamily': "'Source Code Pro', 'Consolas', 'Menlo', monospace",
                    'editor.fontSize': 14,
                    'request.credentials': 'same-origin',
                }}
            }});
        }});
    </script>
</body>
</html>"""
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self._set_cors_headers()
                self.end_headers()
                self.wfile.write(html.encode())

            def _handle_graphql(self) -> None:
                """Handle a GraphQL request."""
                try:
                    content_length = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(content_length)
                    data = json.loads(body.decode())

                    request = GraphQLRequest.from_dict(data)
                    context = ExecutionContext(request=request)

                    # Execute synchronously
                    response = server._execute_sync(request, context)

                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self._set_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps(response.to_dict()).encode())

                except json.JSONDecodeError:
                    self.send_error(400, "Invalid JSON")
                except Exception as e:
                    server._logger.exception("Error handling request")
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    error_response = GraphQLResponse.error(str(e))
                    self.wfile.write(json.dumps(error_response.to_dict()).encode())

        self._server = http.server.HTTPServer(
            (self._config.host, self._config.port),
            GraphQLHandler,
        )

        self._running = True
        self._stats = ServerStats()

        self._server_thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._server_thread.start()

        self._logger.info(
            f"GraphQL server started at http://{self._config.host}:{self._config.port}{self._config.path}"
        )

    async def stop(self) -> None:
        """Stop the GraphQL server."""
        self._stop_sync()

    def _stop_sync(self) -> None:
        """Synchronous stop implementation."""
        if not self._running:
            return

        self._running = False

        if self._server:
            self._server.shutdown()
            self._server = None

        if self._server_thread:
            self._server_thread.join(timeout=5.0)
            self._server_thread = None

        self._logger.info("GraphQL server stopped")

    async def execute(
        self,
        request: GraphQLRequest,
        context: ExecutionContext | None = None,
    ) -> GraphQLResponse:
        """Execute a GraphQL request."""
        return self._execute_sync(request, context)

    def _execute_sync(
        self,
        request: GraphQLRequest,
        context: ExecutionContext | None = None,
    ) -> GraphQLResponse:
        """Synchronous execute implementation."""
        start_time = time.time()
        self._stats.total_requests += 1

        if context is None:
            context = ExecutionContext(request=request)

        try:
            # Parse and execute query
            result = self._execute_query(request, context)

            elapsed_ms = (time.time() - start_time) * 1000
            self._stats.successful_requests += 1

            # Update average response time
            total_successful = self._stats.successful_requests
            prev_avg = self._stats.average_response_time_ms
            self._stats.average_response_time_ms = (
                prev_avg * (total_successful - 1) + elapsed_ms
            ) / total_successful

            return GraphQLResponse(
                data=result,
                extensions={
                    "timing": {"durationMs": elapsed_ms},
                    "requestId": context.request_id,
                },
            )

        except Exception as e:
            self._stats.failed_requests += 1
            self._logger.exception("Error executing query")
            return GraphQLResponse.error(str(e))

    def _execute_query(
        self,
        request: GraphQLRequest,
        context: ExecutionContext,
    ) -> dict[str, Any]:
        """Execute a parsed GraphQL query."""
        query = request.query.strip()

        # Simple query parser (handles basic queries/mutations)
        # In production, use a proper GraphQL parser like graphql-core

        # Detect operation type
        if query.startswith("mutation"):
            return self._execute_mutation(query, request.variables, context)
        if query.startswith("subscription"):
            raise ValueError("Subscriptions must use WebSocket")
        # Default to query
        return self._execute_query_operation(query, request.variables, context)

    def _execute_query_operation(
        self,
        query: str,
        variables: dict[str, Any],
        context: ExecutionContext,
    ) -> dict[str, Any]:
        """Execute a query operation."""
        result: dict[str, Any] = {}

        # Extract field selections (simple parser)
        # Format: query { field1 field2(arg: value) { subfield } }

        # Find fields in the query
        # This is a simplified parser - production would use graphql-core
        if "epic(" in query:
            key_match = re.search(r'epic\s*\(\s*key\s*:\s*["\']?([^"\')\s]+)', query)
            if key_match:
                key = key_match.group(1)
                # Check if it's a variable reference
                if key.startswith("$"):
                    key = variables.get(key[1:], key)
                result["epic"] = self._resolve_epic(context, key)

        if "epics" in query and "epic(" not in query:
            # Extract filter if present
            filter_arg = None
            pagination_arg = None
            result["epics"] = self._resolve_epics(context, filter_arg, pagination_arg)

        if "story(" in query:
            id_match = re.search(r'story\s*\(\s*id\s*:\s*["\']?([^"\')\s]+)', query)
            if id_match:
                story_id = id_match.group(1)
                if story_id.startswith("$"):
                    story_id = variables.get(story_id[1:], story_id)
                result["story"] = self._resolve_story(context, story_id)

        if "stories" in query and "story(" not in query:
            result["stories"] = self._resolve_stories(context)

        if "searchStories" in query:
            query_match = re.search(r'searchStories\s*\(\s*query\s*:\s*["\']([^"\']+)', query)
            if query_match:
                search_query = query_match.group(1)
                result["searchStories"] = self._resolve_search_stories(context, search_query)

        if "workspaceStats" in query:
            result["workspaceStats"] = self._resolve_workspace_stats(context)

        if "health" in query:
            result["health"] = self._resolve_health(context)

        if "activeSyncs" in query:
            result["activeSyncs"] = self._resolve_active_syncs(context)

        if "syncHistory" in query:
            result["syncHistory"] = self._resolve_sync_history(context)

        return result

    def _execute_mutation(
        self,
        query: str,
        variables: dict[str, Any],
        context: ExecutionContext,
    ) -> dict[str, Any]:
        """Execute a mutation operation."""
        result: dict[str, Any] = {}

        if "sync(" in query:
            input_data = variables.get("input", {})
            result["sync"] = self._resolve_sync(context, input_data)

        if "cancelSync(" in query:
            session_id = variables.get("sessionId", "")
            result["cancelSync"] = self._resolve_cancel_sync(context, session_id)

        if "createStory(" in query:
            epic_key = variables.get("epicKey", "")
            input_data = variables.get("input", {})
            result["createStory"] = self._resolve_create_story(context, epic_key, input_data)

        if "updateStory(" in query:
            story_id = variables.get("id", "")
            input_data = variables.get("input", {})
            result["updateStory"] = self._resolve_update_story(context, story_id, input_data)

        if "deleteStory(" in query:
            story_id = variables.get("id", "")
            result["deleteStory"] = self._resolve_delete_story(context, story_id)

        if "updateStoryStatus(" in query:
            story_id = variables.get("id", "")
            status = variables.get("status", "PLANNED")
            result["updateStoryStatus"] = self._resolve_update_story_status(
                context, story_id, status
            )

        if "assignStory(" in query:
            story_id = variables.get("id", "")
            assignee = variables.get("assignee")
            result["assignStory"] = self._resolve_assign_story(context, story_id, assignee)

        if "validateMarkdown(" in query:
            path = variables.get("path", "")
            result["validateMarkdown"] = self._resolve_validate_markdown(context, path)

        return result

    def add_request_middleware(self, middleware: RequestMiddleware) -> None:
        """Add middleware to process requests before execution."""
        self._request_middlewares.append(middleware)

    def add_response_middleware(self, middleware: ResponseMiddleware) -> None:
        """Add middleware to process responses after execution."""
        self._response_middlewares.append(middleware)

    def get_schema_sdl(self) -> str:
        """Get the GraphQL schema in SDL format."""
        return SCHEMA_SDL

    def get_stats(self) -> ServerStats:
        """Get server statistics."""
        return self._stats

    async def subscribe(
        self,
        subscription_id: str,
        request: GraphQLRequest,
        handler: SubscriptionHandler,
    ) -> None:
        """Create a subscription."""
        self._subscriptions[subscription_id] = (request, handler)
        self._stats.active_subscriptions = len(self._subscriptions)

    async def unsubscribe(self, subscription_id: str) -> None:
        """Cancel a subscription."""
        if subscription_id in self._subscriptions:
            del self._subscriptions[subscription_id]
            self._stats.active_subscriptions = len(self._subscriptions)

    def is_running(self) -> bool:
        """Check if the server is running."""
        return self._running

    # ========================================================================
    # Data Management
    # ========================================================================

    def load_epic(self, epic: Epic) -> None:
        """Load an epic into the data store."""
        self._data_store.epics[str(epic.key)] = epic

    def load_epics(self, epics: list[Epic]) -> None:
        """Load multiple epics into the data store."""
        for epic in epics:
            self.load_epic(epic)

    def clear_data(self) -> None:
        """Clear all data from the store."""
        self._data_store.epics.clear()
        self._data_store.active_syncs.clear()
        self._data_store.sync_history.clear()


def create_graphql_server(
    host: str = "0.0.0.0",
    port: int = 8080,
    path: str = "/graphql",
    enable_playground: bool = True,
    event_bus: EventBus | None = None,
) -> SpectraGraphQLServer:
    """
    Create a GraphQL server instance.

    Args:
        host: Host to bind to.
        port: Port to listen on.
        path: GraphQL endpoint path.
        enable_playground: Enable GraphQL Playground.
        event_bus: Event bus for domain events.

    Returns:
        Configured GraphQL server.
    """
    config = ServerConfig(
        host=host,
        port=port,
        path=path,
        enable_playground=enable_playground,
    )

    return SpectraGraphQLServer(config=config, event_bus=event_bus)
