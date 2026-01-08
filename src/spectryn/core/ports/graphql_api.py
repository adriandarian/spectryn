"""
GraphQL API Port - Abstract interface for GraphQL API server.

The GraphQL API provides a flexible query interface for Spectra data:
- Query epics, stories, subtasks
- Filter and paginate results
- Subscribe to real-time updates
- Execute mutations for sync operations

This port defines the contract for GraphQL server implementations.
"""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Generic, TypeVar


T = TypeVar("T")


class OperationType(Enum):
    """Types of GraphQL operations."""

    QUERY = "query"
    MUTATION = "mutation"
    SUBSCRIPTION = "subscription"


class ErrorCode(Enum):
    """GraphQL error codes for client handling."""

    # Validation errors
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_INPUT = "INVALID_INPUT"
    INVALID_QUERY = "INVALID_QUERY"

    # Authentication/Authorization
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"

    # Resource errors
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    ALREADY_EXISTS = "ALREADY_EXISTS"

    # Server errors
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"

    # Sync errors
    SYNC_IN_PROGRESS = "SYNC_IN_PROGRESS"
    SYNC_FAILED = "SYNC_FAILED"


@dataclass(frozen=True)
class GraphQLError:
    """
    A GraphQL error response.

    Follows the GraphQL specification for error formatting.

    Attributes:
        message: Human-readable error message.
        code: Machine-readable error code.
        path: Path to the field that caused the error.
        locations: Locations in the query that caused the error.
        extensions: Additional error metadata.
    """

    message: str
    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    path: list[str | int] | None = None
    locations: list[dict[str, int]] | None = None
    extensions: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to GraphQL-compliant error dictionary."""
        result: dict[str, Any] = {"message": self.message}

        if self.path:
            result["path"] = self.path

        if self.locations:
            result["locations"] = self.locations

        result["extensions"] = {
            "code": self.code.value,
            **self.extensions,
        }

        return result


@dataclass
class GraphQLRequest:
    """
    A GraphQL request.

    Attributes:
        query: The GraphQL query/mutation/subscription string.
        operation_name: Name of the operation to execute (if multiple).
        variables: Variables for the operation.
        extensions: Additional request extensions.
    """

    query: str
    operation_name: str | None = None
    variables: dict[str, Any] = field(default_factory=dict)
    extensions: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GraphQLRequest":
        """Create a request from a dictionary (e.g., JSON body)."""
        return cls(
            query=data.get("query", ""),
            operation_name=data.get("operationName"),
            variables=data.get("variables") or {},
            extensions=data.get("extensions") or {},
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result: dict[str, Any] = {"query": self.query}

        if self.operation_name:
            result["operationName"] = self.operation_name

        if self.variables:
            result["variables"] = self.variables

        if self.extensions:
            result["extensions"] = self.extensions

        return result


@dataclass
class GraphQLResponse:
    """
    A GraphQL response.

    Follows the GraphQL specification response format.

    Attributes:
        data: The query result data (None if errors prevented execution).
        errors: List of errors encountered during execution.
        extensions: Additional response metadata (e.g., timing, tracing).
    """

    data: dict[str, Any] | None = None
    errors: list[GraphQLError] = field(default_factory=list)
    extensions: dict[str, Any] = field(default_factory=dict)

    @property
    def has_errors(self) -> bool:
        """Check if response contains errors."""
        return len(self.errors) > 0

    @property
    def is_success(self) -> bool:
        """Check if response is successful (data present, no errors)."""
        return self.data is not None and not self.has_errors

    def to_dict(self) -> dict[str, Any]:
        """Convert to GraphQL-compliant response dictionary."""
        result: dict[str, Any] = {}

        if self.data is not None:
            result["data"] = self.data

        if self.errors:
            result["errors"] = [e.to_dict() for e in self.errors]

        if self.extensions:
            result["extensions"] = self.extensions

        return result

    @classmethod
    def error(cls, message: str, code: ErrorCode = ErrorCode.INTERNAL_ERROR) -> "GraphQLResponse":
        """Create an error-only response."""
        return cls(errors=[GraphQLError(message=message, code=code)])

    @classmethod
    def success(cls, data: dict[str, Any]) -> "GraphQLResponse":
        """Create a successful response."""
        return cls(data=data)


@dataclass
class PageInfo:
    """
    Pagination information for connections.

    Follows the Relay cursor-based pagination specification.

    Attributes:
        has_next_page: Whether more items exist after this page.
        has_previous_page: Whether more items exist before this page.
        start_cursor: Cursor pointing to the first item.
        end_cursor: Cursor pointing to the last item.
        total_count: Total number of items (optional).
    """

    has_next_page: bool = False
    has_previous_page: bool = False
    start_cursor: str | None = None
    end_cursor: str | None = None
    total_count: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result: dict[str, Any] = {
            "hasNextPage": self.has_next_page,
            "hasPreviousPage": self.has_previous_page,
        }

        if self.start_cursor:
            result["startCursor"] = self.start_cursor

        if self.end_cursor:
            result["endCursor"] = self.end_cursor

        if self.total_count is not None:
            result["totalCount"] = self.total_count

        return result


@dataclass
class Edge(Generic[T]):
    """
    An edge in a connection (node + cursor).

    Attributes:
        node: The actual item.
        cursor: Cursor for this item (for pagination).
    """

    node: T
    cursor: str

    def to_dict(self, node_serializer: Callable[[T], dict[str, Any]]) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "node": node_serializer(self.node),
            "cursor": self.cursor,
        }


@dataclass
class Connection(Generic[T]):
    """
    A paginated collection following Relay connection specification.

    Attributes:
        edges: List of edges (node + cursor pairs).
        page_info: Pagination metadata.
    """

    edges: list[Edge[T]]
    page_info: PageInfo

    def to_dict(self, node_serializer: Callable[[T], dict[str, Any]]) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "edges": [e.to_dict(node_serializer) for e in self.edges],
            "pageInfo": self.page_info.to_dict(),
        }


@dataclass
class SubscriptionEvent:
    """
    An event for GraphQL subscriptions.

    Attributes:
        subscription_id: ID of the subscription this event is for.
        event_type: Type of event (matches subscription field name).
        data: Event payload data.
        timestamp: When the event occurred.
    """

    subscription_id: str
    event_type: str
    data: dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "subscriptionId": self.subscription_id,
            "eventType": self.event_type,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class ExecutionContext:
    """
    Context passed to resolvers during execution.

    Attributes:
        request: The original GraphQL request.
        user: Authenticated user information (if any).
        request_id: Unique ID for this request (for tracing).
        start_time: When execution started.
        metadata: Additional context metadata.
    """

    request: GraphQLRequest
    user: dict[str, Any] | None = None
    request_id: str = field(default_factory=lambda: "")
    start_time: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Generate request ID if not provided."""
        if not self.request_id:
            from uuid import uuid4

            self.request_id = str(uuid4())


@dataclass
class ServerConfig:
    """
    Configuration for the GraphQL server.

    Attributes:
        host: Host to bind to.
        port: Port to listen on.
        path: GraphQL endpoint path.
        enable_playground: Enable GraphQL Playground/GraphiQL.
        enable_introspection: Allow introspection queries.
        max_query_depth: Maximum query depth allowed.
        max_query_complexity: Maximum query complexity allowed.
        timeout: Request timeout in seconds.
        cors_origins: Allowed CORS origins (None = disabled).
        enable_subscriptions: Enable WebSocket subscriptions.
        subscription_path: WebSocket endpoint for subscriptions.
    """

    host: str = "0.0.0.0"
    port: int = 8080
    path: str = "/graphql"
    enable_playground: bool = True
    enable_introspection: bool = True
    max_query_depth: int = 15
    max_query_complexity: int = 1000
    timeout: float = 30.0
    cors_origins: list[str] | None = None
    enable_subscriptions: bool = True
    subscription_path: str = "/graphql/subscriptions"


@dataclass
class ServerStats:
    """
    Statistics for the GraphQL server.

    Attributes:
        started_at: When the server started.
        total_requests: Total requests received.
        successful_requests: Requests that completed successfully.
        failed_requests: Requests that failed.
        active_subscriptions: Currently active subscriptions.
        average_response_time_ms: Average response time.
        queries_by_operation: Count of queries by operation name.
    """

    started_at: datetime = field(default_factory=datetime.now)
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    active_subscriptions: int = 0
    average_response_time_ms: float = 0.0
    queries_by_operation: dict[str, int] = field(default_factory=dict)


# Type aliases for handlers
RequestMiddleware = Callable[
    [GraphQLRequest, ExecutionContext], GraphQLRequest | Awaitable[GraphQLRequest]
]
ResponseMiddleware = Callable[
    [GraphQLResponse, ExecutionContext], GraphQLResponse | Awaitable[GraphQLResponse]
]
SubscriptionHandler = Callable[[SubscriptionEvent], None | Awaitable[None]]


class GraphQLServerPort(ABC):
    """
    Abstract interface for GraphQL API server.

    Implementations must provide:
    - HTTP endpoint for queries/mutations
    - WebSocket endpoint for subscriptions (optional)
    - Schema introspection
    - Middleware support
    """

    @abstractmethod
    async def start(self) -> None:
        """
        Start the GraphQL server.

        Should bind to the configured host/port and begin accepting requests.
        """

    @abstractmethod
    async def stop(self) -> None:
        """
        Stop the GraphQL server.

        Should gracefully close connections and release resources.
        """

    @abstractmethod
    async def execute(
        self,
        request: GraphQLRequest,
        context: ExecutionContext | None = None,
    ) -> GraphQLResponse:
        """
        Execute a GraphQL request.

        Args:
            request: The GraphQL request to execute.
            context: Execution context (created if not provided).

        Returns:
            The GraphQL response.
        """

    @abstractmethod
    def add_request_middleware(self, middleware: RequestMiddleware) -> None:
        """
        Add middleware to process requests before execution.

        Args:
            middleware: Function to process requests.
        """

    @abstractmethod
    def add_response_middleware(self, middleware: ResponseMiddleware) -> None:
        """
        Add middleware to process responses after execution.

        Args:
            middleware: Function to process responses.
        """

    @abstractmethod
    def get_schema_sdl(self) -> str:
        """
        Get the GraphQL schema in SDL format.

        Returns:
            The schema as a string in GraphQL SDL.
        """

    @abstractmethod
    def get_stats(self) -> ServerStats:
        """
        Get server statistics.

        Returns:
            Current server statistics.
        """

    @abstractmethod
    async def subscribe(
        self,
        subscription_id: str,
        request: GraphQLRequest,
        handler: SubscriptionHandler,
    ) -> None:
        """
        Create a subscription.

        Args:
            subscription_id: Unique ID for this subscription.
            request: The subscription query.
            handler: Callback for subscription events.
        """

    @abstractmethod
    async def unsubscribe(self, subscription_id: str) -> None:
        """
        Cancel a subscription.

        Args:
            subscription_id: ID of the subscription to cancel.
        """

    @abstractmethod
    def is_running(self) -> bool:
        """
        Check if the server is running.

        Returns:
            True if the server is running.
        """


class ResolverRegistry(ABC):
    """
    Registry for GraphQL resolvers.

    Resolvers are functions that return data for GraphQL fields.
    """

    @abstractmethod
    def register_query(
        self,
        field_name: str,
        resolver: Callable[..., Any],
    ) -> None:
        """
        Register a query resolver.

        Args:
            field_name: The Query field name.
            resolver: Function to resolve the field.
        """

    @abstractmethod
    def register_mutation(
        self,
        field_name: str,
        resolver: Callable[..., Any],
    ) -> None:
        """
        Register a mutation resolver.

        Args:
            field_name: The Mutation field name.
            resolver: Function to resolve the field.
        """

    @abstractmethod
    def register_subscription(
        self,
        field_name: str,
        subscribe: Callable[..., Any],
        resolve: Callable[..., Any] | None = None,
    ) -> None:
        """
        Register a subscription resolver.

        Args:
            field_name: The Subscription field name.
            subscribe: Function to create subscription source.
            resolve: Function to resolve subscription events.
        """

    @abstractmethod
    def register_type_resolver(
        self,
        type_name: str,
        field_name: str,
        resolver: Callable[..., Any],
    ) -> None:
        """
        Register a field resolver for a specific type.

        Args:
            type_name: The GraphQL type name.
            field_name: The field name on the type.
            resolver: Function to resolve the field.
        """

    @abstractmethod
    def get_resolver(
        self,
        type_name: str,
        field_name: str,
    ) -> Callable[..., Any] | None:
        """
        Get a registered resolver.

        Args:
            type_name: The type name (Query, Mutation, or a custom type).
            field_name: The field name.

        Returns:
            The resolver function, or None if not registered.
        """
