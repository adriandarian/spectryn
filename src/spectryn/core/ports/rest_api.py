"""
REST API Port - Abstract interface for REST API server.

The REST API provides a standard HTTP interface for Spectra data:
- GET endpoints for reading epics, stories, subtasks
- POST/PUT/PATCH endpoints for creating/updating resources
- DELETE endpoints for removing resources
- Standard HTTP status codes and JSON responses

This port defines the contract for REST API server implementations.
"""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class HttpMethod(Enum):
    """HTTP methods supported by the REST API."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    OPTIONS = "OPTIONS"
    HEAD = "HEAD"


class HttpStatus(Enum):
    """HTTP status codes."""

    # Success
    OK = 200
    CREATED = 201
    ACCEPTED = 202
    NO_CONTENT = 204

    # Redirection
    MOVED_PERMANENTLY = 301
    FOUND = 302
    NOT_MODIFIED = 304

    # Client errors
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    METHOD_NOT_ALLOWED = 405
    CONFLICT = 409
    UNPROCESSABLE_ENTITY = 422
    TOO_MANY_REQUESTS = 429

    # Server errors
    INTERNAL_SERVER_ERROR = 500
    NOT_IMPLEMENTED = 501
    BAD_GATEWAY = 502
    SERVICE_UNAVAILABLE = 503


class ErrorCode(Enum):
    """Application-specific error codes for REST API responses."""

    # Validation errors
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_INPUT = "INVALID_INPUT"
    MISSING_FIELD = "MISSING_FIELD"
    INVALID_FORMAT = "INVALID_FORMAT"

    # Authentication/Authorization
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    INVALID_TOKEN = "INVALID_TOKEN"

    # Resource errors
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    RESOURCE_LOCKED = "RESOURCE_LOCKED"

    # Server errors
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"

    # Sync-specific errors
    SYNC_IN_PROGRESS = "SYNC_IN_PROGRESS"
    SYNC_FAILED = "SYNC_FAILED"
    TRACKER_UNAVAILABLE = "TRACKER_UNAVAILABLE"


@dataclass(frozen=True)
class RestError:
    """
    A REST API error response.

    Follows common REST API error formatting conventions.

    Attributes:
        message: Human-readable error message.
        code: Machine-readable error code.
        status: HTTP status code.
        details: Additional error details.
        path: Request path that caused the error.
        timestamp: When the error occurred.
    """

    message: str
    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    status: HttpStatus = HttpStatus.INTERNAL_SERVER_ERROR
    details: dict[str, Any] = field(default_factory=dict)
    path: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to REST-compliant error dictionary."""
        return {
            "error": {
                "message": self.message,
                "code": self.code.value,
                "status": self.status.value,
                "details": self.details if self.details else None,
                "path": self.path,
                "timestamp": self.timestamp.isoformat(),
            }
        }


@dataclass
class RestRequest:
    """
    A REST API request.

    Attributes:
        method: HTTP method.
        path: Request path (e.g., /api/v1/epics/123).
        query_params: URL query parameters.
        headers: Request headers.
        body: Request body (parsed JSON).
        path_params: Extracted path parameters (e.g., {"id": "123"}).
        client_ip: Client IP address.
        request_id: Unique request identifier for tracing.
    """

    method: HttpMethod
    path: str
    query_params: dict[str, str | list[str]] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    body: dict[str, Any] | list[Any] | None = None
    path_params: dict[str, str] = field(default_factory=dict)
    client_ip: str = ""
    request_id: str = field(default_factory=lambda: "")

    def __post_init__(self) -> None:
        """Generate request ID if not provided."""
        if not self.request_id:
            from uuid import uuid4

            object.__setattr__(self, "request_id", str(uuid4()))

    def get_header(self, name: str, default: str | None = None) -> str | None:
        """Get a header value (case-insensitive)."""
        name_lower = name.lower()
        for key, value in self.headers.items():
            if key.lower() == name_lower:
                return value
        return default

    def get_query_param(self, name: str, default: str | None = None) -> str | None:
        """Get a single query parameter value."""
        value = self.query_params.get(name)
        if isinstance(value, list):
            return value[0] if value else default
        return value if value is not None else default

    def get_query_param_list(self, name: str) -> list[str]:
        """Get a query parameter as a list."""
        value = self.query_params.get(name)
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "method": self.method.value,
            "path": self.path,
            "query_params": self.query_params,
            "headers": {k: v for k, v in self.headers.items() if k.lower() != "authorization"},
            "path_params": self.path_params,
            "client_ip": self.client_ip,
            "request_id": self.request_id,
            "has_body": self.body is not None,
        }


@dataclass
class RestResponse:
    """
    A REST API response.

    Attributes:
        status: HTTP status code.
        body: Response body (will be JSON serialized).
        headers: Response headers.
        request_id: Request ID for tracing.
    """

    status: HttpStatus = HttpStatus.OK
    body: dict[str, Any] | list[Any] | None = None
    headers: dict[str, str] = field(default_factory=dict)
    request_id: str = ""

    @classmethod
    def success(
        cls,
        data: dict[str, Any] | list[Any] | None = None,
        status: HttpStatus = HttpStatus.OK,
        request_id: str = "",
    ) -> "RestResponse":
        """Create a success response."""
        return cls(status=status, body=data, request_id=request_id)

    @classmethod
    def created(
        cls,
        data: dict[str, Any],
        location: str | None = None,
        request_id: str = "",
    ) -> "RestResponse":
        """Create a 201 Created response."""
        headers = {}
        if location:
            headers["Location"] = location
        return cls(
            status=HttpStatus.CREATED,
            body=data,
            headers=headers,
            request_id=request_id,
        )

    @classmethod
    def no_content(cls, request_id: str = "") -> "RestResponse":
        """Create a 204 No Content response."""
        return cls(status=HttpStatus.NO_CONTENT, body=None, request_id=request_id)

    @classmethod
    def error(
        cls,
        error: RestError,
        request_id: str = "",
    ) -> "RestResponse":
        """Create an error response from a RestError."""
        return cls(
            status=error.status,
            body=error.to_dict(),
            request_id=request_id,
        )

    @classmethod
    def not_found(
        cls,
        message: str = "Resource not found",
        path: str | None = None,
        request_id: str = "",
    ) -> "RestResponse":
        """Create a 404 Not Found response."""
        error = RestError(
            message=message,
            code=ErrorCode.NOT_FOUND,
            status=HttpStatus.NOT_FOUND,
            path=path,
        )
        return cls.error(error, request_id)

    @classmethod
    def bad_request(
        cls,
        message: str = "Bad request",
        details: dict[str, Any] | None = None,
        request_id: str = "",
    ) -> "RestResponse":
        """Create a 400 Bad Request response."""
        error = RestError(
            message=message,
            code=ErrorCode.VALIDATION_ERROR,
            status=HttpStatus.BAD_REQUEST,
            details=details or {},
        )
        return cls.error(error, request_id)

    @classmethod
    def internal_error(
        cls,
        message: str = "Internal server error",
        request_id: str = "",
    ) -> "RestResponse":
        """Create a 500 Internal Server Error response."""
        error = RestError(
            message=message,
            code=ErrorCode.INTERNAL_ERROR,
            status=HttpStatus.INTERNAL_SERVER_ERROR,
        )
        return cls.error(error, request_id)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "status": self.status.value,
            "body": self.body,
            "headers": self.headers,
            "request_id": self.request_id,
        }


@dataclass
class PagedResponse:
    """
    A paginated REST API response.

    Attributes:
        items: List of items in this page.
        total: Total number of items across all pages.
        page: Current page number (1-indexed).
        per_page: Number of items per page.
        total_pages: Total number of pages.
    """

    items: list[dict[str, Any]]
    total: int
    page: int = 1
    per_page: int = 20

    @property
    def total_pages(self) -> int:
        """Calculate total number of pages."""
        if self.per_page <= 0:
            return 0
        return (self.total + self.per_page - 1) // self.per_page

    @property
    def has_next(self) -> bool:
        """Check if there's a next page."""
        return self.page < self.total_pages

    @property
    def has_prev(self) -> bool:
        """Check if there's a previous page."""
        return self.page > 1

    def to_dict(self) -> dict[str, Any]:
        """Convert to REST-compliant paginated response."""
        return {
            "data": self.items,
            "pagination": {
                "total": self.total,
                "page": self.page,
                "per_page": self.per_page,
                "total_pages": self.total_pages,
                "has_next": self.has_next,
                "has_prev": self.has_prev,
            },
        }


@dataclass
class RouteInfo:
    """
    Information about a registered route.

    Attributes:
        method: HTTP method.
        path: Route path pattern (e.g., /api/v1/epics/{id}).
        handler_name: Name of the handler function.
        description: Human-readable description.
        parameters: Path and query parameters.
    """

    method: HttpMethod
    path: str
    handler_name: str
    description: str = ""
    parameters: dict[str, str] = field(default_factory=dict)


@dataclass
class ServerConfig:
    """
    Configuration for the REST API server.

    Attributes:
        host: Host to bind to.
        port: Port to listen on.
        base_path: Base path for all routes (e.g., /api/v1).
        enable_cors: Whether to enable CORS.
        cors_origins: Allowed CORS origins.
        enable_docs: Whether to enable API documentation endpoint.
        docs_path: Path for API documentation.
        max_request_size: Maximum request body size in bytes.
        request_timeout: Request timeout in seconds.
    """

    host: str = "0.0.0.0"
    port: int = 8080
    base_path: str = "/api/v1"
    enable_cors: bool = True
    cors_origins: list[str] = field(default_factory=lambda: ["*"])
    enable_docs: bool = True
    docs_path: str = "/docs"
    max_request_size: int = 10 * 1024 * 1024  # 10MB
    request_timeout: float = 30.0


@dataclass
class ServerStats:
    """
    Statistics for the REST API server.

    Attributes:
        started_at: When the server started.
        total_requests: Total requests received.
        successful_requests: Requests with 2xx status.
        client_errors: Requests with 4xx status.
        server_errors: Requests with 5xx status.
        avg_response_time_ms: Average response time in milliseconds.
        requests_per_minute: Current requests per minute.
        active_connections: Currently active connections.
    """

    started_at: datetime = field(default_factory=datetime.now)
    total_requests: int = 0
    successful_requests: int = 0
    client_errors: int = 0
    server_errors: int = 0
    avg_response_time_ms: float = 0.0
    requests_per_minute: float = 0.0
    active_connections: int = 0

    @property
    def uptime_seconds(self) -> float:
        """Get server uptime in seconds."""
        return (datetime.now() - self.started_at).total_seconds()

    @property
    def error_rate(self) -> float:
        """Get error rate as a percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.client_errors + self.server_errors) / self.total_requests * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "started_at": self.started_at.isoformat(),
            "uptime_seconds": self.uptime_seconds,
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "client_errors": self.client_errors,
            "server_errors": self.server_errors,
            "error_rate_percent": round(self.error_rate, 2),
            "avg_response_time_ms": round(self.avg_response_time_ms, 2),
            "requests_per_minute": round(self.requests_per_minute, 2),
            "active_connections": self.active_connections,
        }


# Type aliases for middleware and handlers
RequestHandler = Callable[[RestRequest], RestResponse | Awaitable[RestResponse]]
Middleware = Callable[[RestRequest, RequestHandler], RestResponse | Awaitable[RestResponse]]


class RestApiError(Exception):
    """Base exception for REST API errors."""

    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.INTERNAL_ERROR,
        status: HttpStatus = HttpStatus.INTERNAL_SERVER_ERROR,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status
        self.details = details or {}

    def to_error(self) -> RestError:
        """Convert to RestError."""
        return RestError(
            message=self.message,
            code=self.code,
            status=self.status,
            details=self.details,
        )


class ValidationError(RestApiError):
    """Raised when request validation fails."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            code=ErrorCode.VALIDATION_ERROR,
            status=HttpStatus.BAD_REQUEST,
            details=details,
        )


class NotFoundError(RestApiError):
    """Raised when a resource is not found."""

    def __init__(self, message: str = "Resource not found"):
        super().__init__(
            message=message,
            code=ErrorCode.NOT_FOUND,
            status=HttpStatus.NOT_FOUND,
        )


class ConflictError(RestApiError):
    """Raised when there's a resource conflict."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            code=ErrorCode.CONFLICT,
            status=HttpStatus.CONFLICT,
            details=details,
        )


class RestApiServerPort(ABC):
    """
    Abstract interface for REST API server implementations.

    This port defines the contract for running Spectra as a REST API server.
    Implementations may use different HTTP frameworks (stdlib, Flask, FastAPI).

    Example usage:
        server = create_rest_server(host="0.0.0.0", port=8080)
        server.register_route("GET", "/epics", list_epics_handler)
        server.register_route("GET", "/epics/{id}", get_epic_handler)
        await server.start()
    """

    @abstractmethod
    def register_route(
        self,
        method: HttpMethod | str,
        path: str,
        handler: RequestHandler,
        description: str = "",
    ) -> None:
        """
        Register a route handler.

        Args:
            method: HTTP method (GET, POST, etc.).
            path: Route path pattern with optional params (e.g., /epics/{id}).
            handler: Function to handle matching requests.
            description: Human-readable description for docs.
        """
        ...

    @abstractmethod
    def add_middleware(self, middleware: Middleware) -> None:
        """
        Add a middleware function.

        Middleware is executed in order for each request.
        Each middleware receives the request and next handler.

        Args:
            middleware: Middleware function.
        """
        ...

    @abstractmethod
    def start(self) -> Awaitable[None] | None:
        """
        Start the REST API server.

        May return an awaitable for async implementations.
        """
        ...

    @abstractmethod
    def stop(self) -> Awaitable[None] | None:
        """
        Stop the REST API server.

        May return an awaitable for async implementations.
        """
        ...

    @abstractmethod
    def is_running(self) -> bool:
        """Check if the server is currently running."""
        ...

    @abstractmethod
    def get_stats(self) -> ServerStats:
        """Get server statistics."""
        ...

    @abstractmethod
    def get_routes(self) -> list[RouteInfo]:
        """Get list of registered routes."""
        ...

    @abstractmethod
    def get_config(self) -> ServerConfig:
        """Get server configuration."""
        ...

    # Convenience methods with default implementations

    def get(self, path: str, description: str = "") -> Callable[[RequestHandler], RequestHandler]:
        """Decorator for registering GET handlers."""

        def decorator(handler: RequestHandler) -> RequestHandler:
            self.register_route(HttpMethod.GET, path, handler, description)
            return handler

        return decorator

    def post(self, path: str, description: str = "") -> Callable[[RequestHandler], RequestHandler]:
        """Decorator for registering POST handlers."""

        def decorator(handler: RequestHandler) -> RequestHandler:
            self.register_route(HttpMethod.POST, path, handler, description)
            return handler

        return decorator

    def put(self, path: str, description: str = "") -> Callable[[RequestHandler], RequestHandler]:
        """Decorator for registering PUT handlers."""

        def decorator(handler: RequestHandler) -> RequestHandler:
            self.register_route(HttpMethod.PUT, path, handler, description)
            return handler

        return decorator

    def patch(self, path: str, description: str = "") -> Callable[[RequestHandler], RequestHandler]:
        """Decorator for registering PATCH handlers."""

        def decorator(handler: RequestHandler) -> RequestHandler:
            self.register_route(HttpMethod.PATCH, path, handler, description)
            return handler

        return decorator

    def delete(
        self, path: str, description: str = ""
    ) -> Callable[[RequestHandler], RequestHandler]:
        """Decorator for registering DELETE handlers."""

        def decorator(handler: RequestHandler) -> RequestHandler:
            self.register_route(HttpMethod.DELETE, path, handler, description)
            return handler

        return decorator
