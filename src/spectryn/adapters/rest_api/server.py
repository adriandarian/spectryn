"""
REST API Server Implementation.

A zero-dependency REST API server using Python's stdlib http.server.
Provides full REST API functionality for Spectra without external dependencies.
"""

import json
import logging
import re
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlparse

from spectryn.core.domain.entities import Epic, Subtask, UserStory
from spectryn.core.domain.enums import Priority, Status
from spectryn.core.ports.rest_api import (
    ConflictError,
    ErrorCode,
    HttpMethod,
    HttpStatus,
    Middleware,
    NotFoundError,
    PagedResponse,
    RequestHandler,
    RestApiServerPort,
    RestError,
    RestRequest,
    RestResponse,
    RouteInfo,
    ServerConfig,
    ServerStats,
    ValidationError,
)


if TYPE_CHECKING:
    from spectryn.core.domain.events import EventBus


logger = logging.getLogger(__name__)


@dataclass
class DataStore:
    """In-memory data store for the REST API server."""

    epics: dict[str, Epic] = field(default_factory=dict)
    stories: list[UserStory] = field(default_factory=list)  # Stories not in epics
    subtasks: list[Subtask] = field(default_factory=list)  # Subtasks not in stories
    sync_sessions: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Route:
    """Internal route representation."""

    method: HttpMethod
    pattern: re.Pattern[str]
    path_template: str
    handler: RequestHandler
    description: str
    param_names: list[str]


class SpectraRestServer(RestApiServerPort):
    """
    REST API server implementation using stdlib http.server.

    Provides a complete REST API for Spectra without external dependencies.
    Suitable for development and light production use.

    Features:
    - RESTful endpoints for epics, stories, subtasks
    - Pagination support
    - Filtering and search
    - CORS support
    - Request/response middleware
    - OpenAPI-compatible documentation endpoint
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8080,
        base_path: str = "/api/v1",
        enable_cors: bool = True,
        cors_origins: list[str] | None = None,
        enable_docs: bool = True,
        event_bus: "EventBus | None" = None,
        config: ServerConfig | None = None,
    ):
        """
        Initialize REST API server.

        Args:
            host: Host to bind to.
            port: Port to listen on.
            base_path: Base path for all API routes.
            enable_cors: Whether to enable CORS.
            cors_origins: Allowed CORS origins (default: ["*"]).
            enable_docs: Whether to enable API documentation endpoint.
            event_bus: Optional event bus for sync events.
            config: Optional ServerConfig object (overrides individual params).
        """
        if config is not None:
            self._config = config
        else:
            self._config = ServerConfig(
                host=host,
                port=port,
                base_path=base_path,
                enable_cors=enable_cors,
                cors_origins=cors_origins or ["*"],
                enable_docs=enable_docs,
            )

        self._routes: list[Route] = []
        self._middleware: list[Middleware] = []
        self._data_store = DataStore()
        self._event_bus = event_bus

        self._server: HTTPServer | None = None
        self._server_thread: threading.Thread | None = None
        self._running = False
        self._stats = ServerStats()

        # Register built-in routes
        self._register_builtin_routes()

    def _register_builtin_routes(self) -> None:
        """Register built-in API routes."""
        # Health and info
        self.register_route(
            HttpMethod.GET,
            "/health",
            self._handle_health,
            "Health check endpoint",
        )
        self.register_route(
            HttpMethod.GET,
            "/info",
            self._handle_info,
            "Server information",
        )
        self.register_route(
            HttpMethod.GET,
            "/stats",
            self._handle_stats,
            "Server statistics",
        )

        # Documentation
        if self._config.enable_docs:
            self.register_route(
                HttpMethod.GET,
                "/docs",
                self._handle_docs,
                "API documentation",
            )
            self.register_route(
                HttpMethod.GET,
                "/openapi.json",
                self._handle_openapi,
                "OpenAPI specification",
            )

        # Epics
        self.register_route(
            HttpMethod.GET,
            "/epics",
            self._handle_list_epics,
            "List all epics",
        )
        self.register_route(
            HttpMethod.GET,
            "/epics/{key}",
            self._handle_get_epic,
            "Get a specific epic by key",
        )
        self.register_route(
            HttpMethod.POST,
            "/epics",
            self._handle_create_epic,
            "Create a new epic",
        )
        self.register_route(
            HttpMethod.PUT,
            "/epics/{key}",
            self._handle_update_epic,
            "Update an epic",
        )
        self.register_route(
            HttpMethod.DELETE,
            "/epics/{key}",
            self._handle_delete_epic,
            "Delete an epic",
        )

        # Stories
        self.register_route(
            HttpMethod.GET,
            "/stories",
            self._handle_list_stories,
            "List all stories across epics",
        )
        self.register_route(
            HttpMethod.GET,
            "/stories/search",
            self._handle_search_stories,
            "Search stories by query",
        )
        self.register_route(
            HttpMethod.GET,
            "/stories/{id}",
            self._handle_get_story,
            "Get a specific story by ID",
        )
        self.register_route(
            HttpMethod.POST,
            "/epics/{key}/stories",
            self._handle_create_story,
            "Create a new story in an epic",
        )
        self.register_route(
            HttpMethod.PUT,
            "/stories/{id}",
            self._handle_update_story,
            "Update a story",
        )
        self.register_route(
            HttpMethod.DELETE,
            "/stories/{id}",
            self._handle_delete_story,
            "Delete a story",
        )

        # Subtasks
        self.register_route(
            HttpMethod.GET,
            "/stories/{id}/subtasks",
            self._handle_list_subtasks,
            "List subtasks for a story",
        )
        self.register_route(
            HttpMethod.POST,
            "/stories/{id}/subtasks",
            self._handle_create_subtask,
            "Create a subtask for a story",
        )
        self.register_route(
            HttpMethod.PUT,
            "/subtasks/{id}",
            self._handle_update_subtask,
            "Update a subtask",
        )
        self.register_route(
            HttpMethod.DELETE,
            "/subtasks/{id}",
            self._handle_delete_subtask,
            "Delete a subtask",
        )

        # Sync operations
        self.register_route(
            HttpMethod.POST,
            "/sync",
            self._handle_sync,
            "Trigger a sync operation",
        )
        self.register_route(
            HttpMethod.GET,
            "/sync/status",
            self._handle_sync_status,
            "Get sync status",
        )
        self.register_route(
            HttpMethod.GET,
            "/sync/history",
            self._handle_sync_history,
            "Get sync history",
        )

        # Workspace
        self.register_route(
            HttpMethod.GET,
            "/workspace/stats",
            self._handle_workspace_stats,
            "Get workspace statistics",
        )

    def register_route(
        self,
        method: HttpMethod | str,
        path: str,
        handler: RequestHandler,
        description: str = "",
    ) -> None:
        """Register a route handler."""
        if isinstance(method, str):
            method = HttpMethod(method.upper())

        # Build full path with base path
        full_path = f"{self._config.base_path}{path}"

        # Extract parameter names and build regex pattern
        param_names: list[str] = []
        pattern_str = "^"

        parts = full_path.split("/")
        for part in parts:
            if not part:
                continue
            if part.startswith("{") and part.endswith("}"):
                param_name = part[1:-1]
                param_names.append(param_name)
                pattern_str += r"/([^/]+)"
            else:
                pattern_str += "/" + re.escape(part)

        pattern_str += "$"
        pattern = re.compile(pattern_str)

        route = Route(
            method=method,
            pattern=pattern,
            path_template=full_path,
            handler=handler,
            description=description,
            param_names=param_names,
        )
        self._routes.append(route)

    def add_middleware(self, middleware: Middleware) -> None:
        """Add a middleware function."""
        self._middleware.append(middleware)

    def start(self) -> Awaitable[None] | None:
        """Start the REST API server."""
        if self._running:
            return None

        self._stats = ServerStats(started_at=datetime.now())
        self._running = True

        # Create HTTP server
        handler = self._create_request_handler()
        self._server = HTTPServer((self._config.host, self._config.port), handler)

        # Start in a background thread
        self._server_thread = threading.Thread(target=self._server.serve_forever)
        self._server_thread.daemon = True
        self._server_thread.start()

        logger.info(
            f"REST API server started at http://{self._config.host}:{self._config.port}{self._config.base_path}"
        )
        return None

    def _start_sync(self) -> None:
        """Start the server synchronously (for CLI use)."""
        self.start()

    def _stop_sync(self) -> None:
        """Stop the server synchronously (for CLI use)."""
        self.stop()

    def stop(self) -> Awaitable[None] | None:
        """Stop the REST API server."""
        if not self._running:
            return None

        self._running = False

        if self._server:
            self._server.shutdown()
            self._server = None

        if self._server_thread:
            self._server_thread.join(timeout=5)
            self._server_thread = None

        logger.info("REST API server stopped")
        return None

    def is_running(self) -> bool:
        """Check if the server is running."""
        return self._running

    def get_stats(self) -> ServerStats:
        """Get server statistics."""
        return self._stats

    def get_routes(self) -> list[RouteInfo]:
        """Get list of registered routes."""
        return [
            RouteInfo(
                method=route.method,
                path=route.path_template,
                handler_name=route.handler.__name__,
                description=route.description,
            )
            for route in self._routes
        ]

    def get_config(self) -> ServerConfig:
        """Get server configuration."""
        return self._config

    @property
    def config(self) -> ServerConfig:
        """Get server configuration (property)."""
        return self._config

    def load_epic(self, epic: Epic) -> None:
        """Load an epic into the data store."""
        self._data_store.epics[str(epic.key)] = epic

    def load_epics(self, epics: list[Epic]) -> None:
        """Load multiple epics into the data store."""
        for epic in epics:
            self.load_epic(epic)

    def load_story(self, story: UserStory, epic: Epic | None = None) -> None:
        """Load a story into the data store.

        If an epic is provided, the story is added to that epic.
        Otherwise, it's added to a default epic if stories are tracked separately.
        """
        if epic:
            if str(epic.key) not in self._data_store.epics:
                self.load_epic(epic)
            self._data_store.epics[str(epic.key)].stories.append(story)
        else:
            self._data_store.stories.append(story)

    def load_stories(self, stories: list[UserStory], epic: Epic | None = None) -> None:
        """Load multiple stories into the data store."""
        for story in stories:
            self.load_story(story, epic)

    def load_subtask(self, subtask: Subtask) -> None:
        """Load a subtask into the data store."""
        self._data_store.subtasks.append(subtask)

    def load_subtasks(self, subtasks: list[Subtask]) -> None:
        """Load multiple subtasks into the data store."""
        for subtask in subtasks:
            self.load_subtask(subtask)

    def get_epics(self) -> list[Epic]:
        """Get all epics from the data store."""
        return list(self._data_store.epics.values())

    def get_stories(self) -> list[UserStory]:
        """Get all stories from all epics."""
        all_stories = list(self._data_store.stories)
        for epic in self._data_store.epics.values():
            all_stories.extend(epic.stories)
        return all_stories

    def get_subtasks(self) -> list[Subtask]:
        """Get all subtasks."""
        all_subtasks = list(self._data_store.subtasks)
        for story in self.get_stories():
            all_subtasks.extend(story.subtasks)
        return all_subtasks

    def get_port(self) -> int:
        """Get the actual port the server is running on."""
        if self._server:
            return self._server.server_port
        return self._config.port

    def add_route(
        self,
        method: HttpMethod,
        path: str,
        handler: RequestHandler,
        description: str = "",
        parameters: dict[str, str] | None = None,
    ) -> None:
        """Add a route (alias for register_route)."""
        self.register_route(method, path, handler, description)

    def handle_request(self, request: RestRequest) -> RestResponse:
        """Handle a request directly (for testing).

        Note: This is a synchronous-only implementation for unit testing.
        For async handlers, use the HTTP server directly.
        """
        # Run simple middleware (sync only, simplified signature)
        processed_request: RestRequest = request
        for middleware in self._middleware:
            mw_result = middleware(processed_request)  # type: ignore[call-arg]
            if isinstance(mw_result, RestResponse):
                return mw_result
            if mw_result is not None and isinstance(mw_result, RestRequest):
                processed_request = mw_result

        # Match route
        for route in self._routes:
            if route.method != request.method:
                continue

            match = route.pattern.match(request.path)
            if match:
                # Extract path parameters
                path_params = dict(zip(route.param_names, match.groups(), strict=False))
                # Create new request with path params
                updated_request = RestRequest(
                    method=request.method,
                    path=request.path,
                    query_params=request.query_params,
                    headers=request.headers,
                    body=request.body,
                    path_params=path_params,
                    client_ip=request.client_ip,
                    request_id=request.request_id,
                )

                # Update stats
                self._stats.total_requests += 1

                try:
                    response = route.handler(updated_request)
                    # Handle sync response only (type narrowing)
                    if not isinstance(response, RestResponse):
                        # If async, we can't handle it synchronously
                        return RestResponse.internal_error(
                            "Async handlers not supported in handle_request",
                            request_id=request.request_id,
                        )

                    if response.status.value < 400:
                        self._stats.successful_requests += 1
                    elif response.status.value < 500:
                        self._stats.client_errors += 1
                    else:
                        self._stats.server_errors += 1

                    # Add CORS headers if enabled
                    if self._config.enable_cors:
                        origin = request.get_header("Origin")
                        if origin:
                            response.headers["Access-Control-Allow-Origin"] = (
                                origin if "*" not in self._config.cors_origins else "*"
                            )
                            response.headers["Access-Control-Allow-Methods"] = (
                                "GET, POST, PUT, PATCH, DELETE, OPTIONS"
                            )
                            response.headers["Access-Control-Allow-Headers"] = (
                                "Content-Type, Authorization"
                            )

                    return response
                except Exception as e:
                    self._stats.server_errors += 1
                    self._stats.total_requests += 1
                    return RestResponse.internal_error(
                        str(e),
                        request_id=request.request_id,
                    )

        # Handle OPTIONS for CORS preflight
        if request.method == HttpMethod.OPTIONS and self._config.enable_cors:
            origin = request.get_header("Origin")
            response = RestResponse.no_content(request_id=request.request_id)
            if origin:
                response.headers["Access-Control-Allow-Origin"] = (
                    origin if "*" not in self._config.cors_origins else "*"
                )
                response.headers["Access-Control-Allow-Methods"] = (
                    "GET, POST, PUT, PATCH, DELETE, OPTIONS"
                )
                response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            return response

        # No matching route
        self._stats.client_errors += 1
        self._stats.total_requests += 1
        return RestResponse.not_found(
            f"No route found for {request.method.value} {request.path}",
            path=request.path,
            request_id=request.request_id,
        )

    def clear_data(self) -> None:
        """Clear all data from the data store."""
        self._data_store = DataStore()

    def _create_request_handler(self) -> type[BaseHTTPRequestHandler]:
        """Create the HTTP request handler class."""
        server = self

        class RequestHandler(BaseHTTPRequestHandler):
            """HTTP request handler for REST API."""

            def log_message(self, format: str, *args: Any) -> None:
                """Override to use Python logging."""
                logger.debug(f"{self.address_string()} - {format % args}")

            def do_GET(self) -> None:
                self._handle_request(HttpMethod.GET)

            def do_POST(self) -> None:
                self._handle_request(HttpMethod.POST)

            def do_PUT(self) -> None:
                self._handle_request(HttpMethod.PUT)

            def do_PATCH(self) -> None:
                self._handle_request(HttpMethod.PATCH)

            def do_DELETE(self) -> None:
                self._handle_request(HttpMethod.DELETE)

            def do_OPTIONS(self) -> None:
                """Handle CORS preflight requests."""
                if server._config.enable_cors:
                    self._send_cors_headers()
                    self.send_response(200)
                    self.end_headers()
                else:
                    self.send_error(405)

            def _handle_request(self, method: HttpMethod) -> None:
                """Handle an incoming request."""
                start_time = time.time()
                server._stats.total_requests += 1
                server._stats.active_connections += 1

                try:
                    # Parse URL
                    parsed = urlparse(self.path)
                    path = parsed.path
                    query_params = parse_qs(parsed.query)

                    # Flatten single-value query params
                    flat_params: dict[str, str | list[str]] = {}
                    for key, values in query_params.items():
                        flat_params[key] = values[0] if len(values) == 1 else values

                    # Parse headers
                    headers = dict(self.headers.items())

                    # Parse body for POST/PUT/PATCH
                    body: dict[str, Any] | list[Any] | None = None
                    if method in (HttpMethod.POST, HttpMethod.PUT, HttpMethod.PATCH):
                        content_length = int(self.headers.get("Content-Length", 0))
                        if content_length > 0:
                            raw_body = self.rfile.read(content_length)
                            try:
                                body = json.loads(raw_body.decode("utf-8"))
                            except json.JSONDecodeError:
                                self._send_error(HttpStatus.BAD_REQUEST, "Invalid JSON body")
                                return

                    # Find matching route
                    route, path_params = server._find_route(method, path)
                    if not route:
                        self._send_error(
                            HttpStatus.NOT_FOUND, f"No route found for {method.value} {path}"
                        )
                        return

                    # Build request object
                    request = RestRequest(
                        method=method,
                        path=path,
                        query_params=flat_params,
                        headers=headers,
                        body=body,
                        path_params=path_params,
                        client_ip=self.client_address[0],
                    )

                    # Execute handler with middleware
                    response = server._execute_handler(route.handler, request)

                    # Send response
                    self._send_response(response)

                    # Update stats
                    if 200 <= response.status.value < 300:
                        server._stats.successful_requests += 1
                    elif 400 <= response.status.value < 500:
                        server._stats.client_errors += 1
                    else:
                        server._stats.server_errors += 1

                except Exception as e:
                    logger.exception(f"Error handling request: {e}")
                    self._send_error(HttpStatus.INTERNAL_SERVER_ERROR, str(e))
                    server._stats.server_errors += 1

                finally:
                    server._stats.active_connections -= 1

                    # Update average response time
                    elapsed = (time.time() - start_time) * 1000
                    n = server._stats.total_requests
                    server._stats.avg_response_time_ms = (
                        server._stats.avg_response_time_ms * (n - 1) + elapsed
                    ) / n

            def _send_response(self, response: RestResponse) -> None:
                """Send a REST response."""
                self.send_response(response.status.value)

                # Set headers
                self.send_header("Content-Type", "application/json")
                if server._config.enable_cors:
                    self._send_cors_headers()

                for key, value in response.headers.items():
                    self.send_header(key, value)

                if response.request_id:
                    self.send_header("X-Request-ID", response.request_id)

                self.end_headers()

                # Send body
                if response.body is not None:
                    body_json = json.dumps(response.body, default=str)
                    self.wfile.write(body_json.encode("utf-8"))

            def _send_error(self, status: HttpStatus, message: str) -> None:
                """Send an error response."""
                self.send_response(status.value)
                self.send_header("Content-Type", "application/json")
                if server._config.enable_cors:
                    self._send_cors_headers()
                self.end_headers()

                error_body = {
                    "error": {
                        "message": message,
                        "status": status.value,
                    }
                }
                self.wfile.write(json.dumps(error_body).encode("utf-8"))

            def _send_cors_headers(self) -> None:
                """Send CORS headers."""
                origin = self.headers.get("Origin", "*")
                if "*" in server._config.cors_origins or origin in server._config.cors_origins:
                    self.send_header("Access-Control-Allow-Origin", origin)
                else:
                    self.send_header("Access-Control-Allow-Origin", server._config.cors_origins[0])
                self.send_header(
                    "Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS"
                )
                self.send_header(
                    "Access-Control-Allow-Headers", "Content-Type, Authorization, X-Request-ID"
                )
                self.send_header("Access-Control-Max-Age", "86400")

        return RequestHandler

    def _find_route(self, method: HttpMethod, path: str) -> tuple[Route | None, dict[str, str]]:
        """Find a matching route for the request."""
        for route in self._routes:
            if route.method != method:
                continue

            match = route.pattern.match(path)
            if match:
                # Extract path parameters
                path_params = {}
                for i, name in enumerate(route.param_names):
                    path_params[name] = match.group(i + 1)
                return route, path_params

        return None, {}

    def _execute_handler(self, handler: RequestHandler, request: RestRequest) -> RestResponse:
        """Execute a handler with middleware."""

        # Build middleware chain
        def final_handler(req: RestRequest) -> RestResponse:
            try:
                result = handler(req)
                if isinstance(result, RestResponse):
                    return result
                # Assume it's awaitable - but we're sync, so just call it
                return RestResponse.internal_error("Async handlers not supported in sync mode")
            except ValidationError as e:
                return RestResponse.bad_request(e.message, e.details)
            except NotFoundError as e:
                return RestResponse.not_found(e.message)
            except ConflictError as e:
                return RestResponse.error(e.to_error())
            except Exception as e:
                logger.exception(f"Handler error: {e}")
                return RestResponse.internal_error(str(e))

        # Apply middleware in reverse order
        current = final_handler
        for middleware in reversed(self._middleware):

            def make_next(mw: Middleware, next_handler: Callable) -> Callable:
                def wrapped(req: RestRequest) -> RestResponse:
                    result = mw(req, next_handler)
                    if isinstance(result, RestResponse):
                        return result
                    return RestResponse.internal_error("Async middleware not supported")

                return wrapped

            current = make_next(middleware, current)

        return current(request)

    # ==================== Built-in Route Handlers ====================

    def _handle_health(self, request: RestRequest) -> RestResponse:
        """Health check endpoint."""
        return RestResponse.success(
            {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "version": "1.0.0",
            },
            request_id=request.request_id,
        )

    def _handle_info(self, request: RestRequest) -> RestResponse:
        """Server information endpoint."""
        return RestResponse.success(
            {
                "name": "Spectra REST API",
                "version": "1.0.0",
                "base_path": self._config.base_path,
                "endpoints": len(self._routes),
                "docs_enabled": self._config.enable_docs,
                "cors_enabled": self._config.enable_cors,
            },
            request_id=request.request_id,
        )

    def _handle_stats(self, request: RestRequest) -> RestResponse:
        """Server statistics endpoint."""
        return RestResponse.success(
            self._stats.to_dict(),
            request_id=request.request_id,
        )

    def _handle_docs(self, request: RestRequest) -> RestResponse:
        """API documentation endpoint."""
        routes_by_tag: dict[str, list[dict[str, Any]]] = {}

        for route in self._routes:
            # Group by first path segment
            parts = route.path_template.split("/")
            tag = parts[3] if len(parts) > 3 else "general"

            if tag not in routes_by_tag:
                routes_by_tag[tag] = []

            routes_by_tag[tag].append(
                {
                    "method": route.method.value,
                    "path": route.path_template,
                    "description": route.description,
                    "parameters": route.param_names,
                }
            )

        return RestResponse.success(
            {
                "title": "Spectra REST API Documentation",
                "version": "1.0.0",
                "base_url": f"http://{self._config.host}:{self._config.port}{self._config.base_path}",
                "endpoints": routes_by_tag,
            },
            request_id=request.request_id,
        )

    def _handle_openapi(self, request: RestRequest) -> RestResponse:
        """OpenAPI specification endpoint."""
        paths: dict[str, Any] = {}

        for route in self._routes:
            path = route.path_template.replace("{", "{").replace("}", "}")
            if path not in paths:
                paths[path] = {}

            method_lower = route.method.value.lower()
            paths[path][method_lower] = {
                "summary": route.description,
                "parameters": [
                    {
                        "name": name,
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                    for name in route.param_names
                ],
                "responses": {
                    "200": {"description": "Success"},
                    "400": {"description": "Bad Request"},
                    "404": {"description": "Not Found"},
                    "500": {"description": "Internal Server Error"},
                },
            }

        openapi_spec = {
            "openapi": "3.0.0",
            "info": {
                "title": "Spectra REST API",
                "version": "1.0.0",
                "description": "REST API for Spectra - sync user stories to issue trackers",
            },
            "servers": [
                {
                    "url": f"http://{self._config.host}:{self._config.port}{self._config.base_path}",
                    "description": "Local server",
                }
            ],
            "paths": paths,
        }

        return RestResponse.success(openapi_spec, request_id=request.request_id)

    def _handle_list_epics(self, request: RestRequest) -> RestResponse:
        """List all epics."""
        page = int(request.get_query_param("page", "1") or "1")
        per_page = int(request.get_query_param("per_page", "20") or "20")

        epics = list(self._data_store.epics.values())

        # Apply pagination
        start = (page - 1) * per_page
        end = start + per_page
        page_epics = epics[start:end]

        items = [self._epic_to_dict(epic) for epic in page_epics]

        paged = PagedResponse(
            items=items,
            total=len(epics),
            page=page,
            per_page=per_page,
        )

        return RestResponse.success(paged.to_dict(), request_id=request.request_id)

    def _handle_get_epic(self, request: RestRequest) -> RestResponse:
        """Get a specific epic."""
        key = request.path_params.get("key", "")
        epic = self._data_store.epics.get(key)

        if not epic:
            return RestResponse.not_found(f"Epic not found: {key}", request_id=request.request_id)

        return RestResponse.success(
            self._epic_to_dict(epic, include_stories=True),
            request_id=request.request_id,
        )

    def _handle_create_epic(self, request: RestRequest) -> RestResponse:
        """Create a new epic."""
        from spectryn.core.domain.value_objects import IssueKey

        if not request.body or not isinstance(request.body, dict):
            return RestResponse.bad_request("Request body required", request_id=request.request_id)

        body = request.body
        key = body.get("key")
        title = body.get("title")

        if not key or not title:
            return RestResponse.bad_request(
                "Both 'key' and 'title' are required",
                details={"missing": ["key", "title"]},
                request_id=request.request_id,
            )

        if key in self._data_store.epics:
            error = RestError(
                message=f"Epic already exists: {key}",
                code=ErrorCode.CONFLICT,
                status=HttpStatus.CONFLICT,
            )
            return RestResponse.error(error, request_id=request.request_id)

        epic = Epic(key=IssueKey(key), title=title, description=body.get("description", ""))
        self._data_store.epics[key] = epic

        return RestResponse.created(
            self._epic_to_dict(epic),
            location=f"{self._config.base_path}/epics/{key}",
            request_id=request.request_id,
        )

    def _handle_update_epic(self, request: RestRequest) -> RestResponse:
        """Update an epic."""
        key = request.path_params.get("key", "")
        epic = self._data_store.epics.get(key)

        if not epic:
            return RestResponse.not_found(f"Epic not found: {key}", request_id=request.request_id)

        if not request.body or not isinstance(request.body, dict):
            return RestResponse.bad_request("Request body required", request_id=request.request_id)

        body = request.body

        # Update fields
        if "title" in body:
            epic.title = body["title"]
        if "description" in body:
            epic.description = body["description"]

        return RestResponse.success(self._epic_to_dict(epic), request_id=request.request_id)

    def _handle_delete_epic(self, request: RestRequest) -> RestResponse:
        """Delete an epic."""
        key = request.path_params.get("key", "")

        if key not in self._data_store.epics:
            return RestResponse.not_found(f"Epic not found: {key}", request_id=request.request_id)

        del self._data_store.epics[key]
        return RestResponse.no_content(request_id=request.request_id)

    def _handle_list_stories(self, request: RestRequest) -> RestResponse:
        """List all stories across all epics and standalone stories."""
        page = int(request.get_query_param("page", "1") or "1")
        per_page = int(request.get_query_param("per_page", "20") or "20")
        status_filter = request.get_query_param("status")
        priority_filter = request.get_query_param("priority")
        epic_filter = request.get_query_param("epic")

        all_stories: list[tuple[Epic | None, UserStory]] = []

        # Add stories from epics
        for epic in self._data_store.epics.values():
            if epic_filter and str(epic.key) != epic_filter:
                continue
            for story in epic.stories:
                # Apply filters
                if status_filter and story.status.name != status_filter.upper():
                    continue
                if priority_filter and story.priority.name != priority_filter.upper():
                    continue
                all_stories.append((epic, story))

        # Add standalone stories (only if no epic filter)
        if not epic_filter:
            for story in self._data_store.stories:
                if status_filter and story.status.name != status_filter.upper():
                    continue
                if priority_filter and story.priority.name != priority_filter.upper():
                    continue
                all_stories.append((None, story))

        # Apply pagination
        start = (page - 1) * per_page
        end = start + per_page
        page_stories = all_stories[start:end]

        items = [
            self._story_to_dict(story, epic_key=str(epic.key) if epic else None)
            for epic, story in page_stories
        ]

        paged = PagedResponse(
            items=items,
            total=len(all_stories),
            page=page,
            per_page=per_page,
        )

        return RestResponse.success(paged.to_dict(), request_id=request.request_id)

    def _handle_get_story(self, request: RestRequest) -> RestResponse:
        """Get a specific story."""
        story_id = request.path_params.get("id", "")

        for epic in self._data_store.epics.values():
            for story in epic.stories:
                if str(story.id) == story_id:
                    return RestResponse.success(
                        self._story_to_dict(story, epic_key=str(epic.key), include_subtasks=True),
                        request_id=request.request_id,
                    )

        return RestResponse.not_found(f"Story not found: {story_id}", request_id=request.request_id)

    def _handle_create_story(self, request: RestRequest) -> RestResponse:
        """Create a new story in an epic."""
        import uuid

        from spectryn.core.domain.value_objects import Description, StoryId

        key = request.path_params.get("key", "")
        epic = self._data_store.epics.get(key)

        if not epic:
            return RestResponse.not_found(f"Epic not found: {key}", request_id=request.request_id)

        if not request.body or not isinstance(request.body, dict):
            return RestResponse.bad_request("Request body required", request_id=request.request_id)

        body = request.body
        title = body.get("title")

        if not title:
            return RestResponse.bad_request("'title' is required", request_id=request.request_id)

        # Generate story ID
        story_id = StoryId(f"S-{uuid.uuid4().hex[:8].upper()}")

        # Parse description
        description = None
        if body.get("description"):
            desc = body["description"]
            if isinstance(desc, dict):
                description = Description(
                    role=desc.get("role", "user"),
                    want=desc.get("want", ""),
                    benefit=desc.get("benefit", ""),
                )
            else:
                description = Description.from_markdown(str(desc))
                if not description:
                    description = Description(
                        role="user",
                        want=str(desc),
                        benefit="achieve my goals",
                    )

        story = UserStory(
            id=story_id,
            title=title,
            description=description,
            story_points=body.get("story_points", 0),
            priority=Priority[body.get("priority", "MEDIUM").upper()],
            status=Status[body.get("status", "PLANNED").upper()],
            assignee=body.get("assignee"),
            labels=body.get("labels", []),
            sprint=body.get("sprint"),
        )

        epic.stories.append(story)

        return RestResponse.created(
            self._story_to_dict(story, epic_key=key),
            location=f"{self._config.base_path}/stories/{story.id}",
            request_id=request.request_id,
        )

    def _handle_update_story(self, request: RestRequest) -> RestResponse:
        """Update a story."""
        from spectryn.core.domain.value_objects import Description

        story_id = request.path_params.get("id", "")

        if not request.body or not isinstance(request.body, dict):
            return RestResponse.bad_request("Request body required", request_id=request.request_id)

        body = request.body

        for epic in self._data_store.epics.values():
            for story in epic.stories:
                if str(story.id) == story_id:
                    # Update fields
                    if "title" in body:
                        story.title = body["title"]
                    if "description" in body:
                        desc = body["description"]
                        if desc:
                            if isinstance(desc, dict):
                                story.description = Description(
                                    role=desc.get("role", "user"),
                                    want=desc.get("want", ""),
                                    benefit=desc.get("benefit", ""),
                                )
                            else:
                                parsed = Description.from_markdown(str(desc))
                                if parsed:
                                    story.description = parsed
                                else:
                                    story.description = Description(
                                        role="user",
                                        want=str(desc),
                                        benefit="achieve my goals",
                                    )
                        else:
                            story.description = None
                    if "story_points" in body:
                        story.story_points = body["story_points"]
                    if "priority" in body:
                        story.priority = Priority[body["priority"].upper()]
                    if "status" in body:
                        story.status = Status[body["status"].upper()]
                    if "assignee" in body:
                        story.assignee = body["assignee"]
                    if "labels" in body:
                        story.labels = body["labels"]
                    if "sprint" in body:
                        story.sprint = body["sprint"]

                    return RestResponse.success(
                        self._story_to_dict(story, epic_key=str(epic.key)),
                        request_id=request.request_id,
                    )

        return RestResponse.not_found(f"Story not found: {story_id}", request_id=request.request_id)

    def _handle_delete_story(self, request: RestRequest) -> RestResponse:
        """Delete a story."""
        story_id = request.path_params.get("id", "")

        for epic in self._data_store.epics.values():
            for i, story in enumerate(epic.stories):
                if str(story.id) == story_id:
                    epic.stories.pop(i)
                    return RestResponse.no_content(request_id=request.request_id)

        return RestResponse.not_found(f"Story not found: {story_id}", request_id=request.request_id)

    def _handle_search_stories(self, request: RestRequest) -> RestResponse:
        """Search stories by query."""
        query = request.get_query_param("q", "") or ""
        page = int(request.get_query_param("page", "1") or "1")
        per_page = int(request.get_query_param("per_page", "20") or "20")

        if not query:
            return RestResponse.bad_request(
                "Query parameter 'q' is required", request_id=request.request_id
            )

        query_lower = query.lower()
        results: list[tuple[Epic, UserStory]] = []

        for epic in self._data_store.epics.values():
            for story in epic.stories:
                # Search in title, description, labels
                if (
                    query_lower in story.title.lower()
                    or (
                        story.description
                        and query_lower in story.description.to_plain_text().lower()
                    )
                    or any(query_lower in label.lower() for label in story.labels)
                ):
                    results.append((epic, story))

        # Apply pagination
        start = (page - 1) * per_page
        end = start + per_page
        page_results = results[start:end]

        items = [self._story_to_dict(story, epic_key=str(epic.key)) for epic, story in page_results]

        paged = PagedResponse(
            items=items,
            total=len(results),
            page=page,
            per_page=per_page,
        )

        return RestResponse.success(paged.to_dict(), request_id=request.request_id)

    def _handle_list_subtasks(self, request: RestRequest) -> RestResponse:
        """List subtasks for a story."""
        story_id = request.path_params.get("id", "")

        for epic in self._data_store.epics.values():
            for story in epic.stories:
                if str(story.id) == story_id:
                    items = [self._subtask_to_dict(st) for st in story.subtasks]
                    return RestResponse.success(
                        {"data": items, "total": len(items)},
                        request_id=request.request_id,
                    )

        return RestResponse.not_found(f"Story not found: {story_id}", request_id=request.request_id)

    def _handle_create_subtask(self, request: RestRequest) -> RestResponse:
        """Create a subtask for a story."""
        story_id = request.path_params.get("id", "")

        if not request.body or not isinstance(request.body, dict):
            return RestResponse.bad_request("Request body required", request_id=request.request_id)

        body = request.body
        name = body.get("name")

        if not name:
            return RestResponse.bad_request("'name' is required", request_id=request.request_id)

        for epic in self._data_store.epics.values():
            for story in epic.stories:
                if str(story.id) == story_id:
                    # Find next subtask number
                    next_num = max((st.number for st in story.subtasks), default=0) + 1

                    subtask = Subtask(
                        id=f"{story.id}-{next_num}",
                        number=next_num,
                        name=name,
                        description=body.get("description", ""),
                        story_points=body.get("story_points", 0),
                        status=Status[body.get("status", "PLANNED").upper()],
                        priority=Priority[body.get("priority", "MEDIUM").upper()]
                        if body.get("priority")
                        else None,
                        assignee=body.get("assignee"),
                    )

                    story.subtasks.append(subtask)

                    return RestResponse.created(
                        self._subtask_to_dict(subtask),
                        location=f"{self._config.base_path}/subtasks/{subtask.id}",
                        request_id=request.request_id,
                    )

        return RestResponse.not_found(f"Story not found: {story_id}", request_id=request.request_id)

    def _handle_update_subtask(self, request: RestRequest) -> RestResponse:
        """Update a subtask."""
        subtask_id = request.path_params.get("id", "")

        if not request.body or not isinstance(request.body, dict):
            return RestResponse.bad_request("Request body required", request_id=request.request_id)

        body = request.body

        for epic in self._data_store.epics.values():
            for story in epic.stories:
                for subtask in story.subtasks:
                    if subtask.id == subtask_id:
                        # Update fields
                        if "name" in body:
                            subtask.name = body["name"]
                        if "description" in body:
                            subtask.description = body["description"]
                        if "story_points" in body:
                            subtask.story_points = body["story_points"]
                        if "status" in body:
                            subtask.status = Status[body["status"].upper()]
                        if "priority" in body:
                            subtask.priority = (
                                Priority[body["priority"].upper()] if body["priority"] else None
                            )
                        if "assignee" in body:
                            subtask.assignee = body["assignee"]

                        return RestResponse.success(
                            self._subtask_to_dict(subtask),
                            request_id=request.request_id,
                        )

        return RestResponse.not_found(
            f"Subtask not found: {subtask_id}", request_id=request.request_id
        )

    def _handle_delete_subtask(self, request: RestRequest) -> RestResponse:
        """Delete a subtask."""
        subtask_id = request.path_params.get("id", "")

        for epic in self._data_store.epics.values():
            for story in epic.stories:
                for i, subtask in enumerate(story.subtasks):
                    if subtask.id == subtask_id:
                        story.subtasks.pop(i)
                        return RestResponse.no_content(request_id=request.request_id)

        return RestResponse.not_found(
            f"Subtask not found: {subtask_id}", request_id=request.request_id
        )

    def _handle_sync(self, request: RestRequest) -> RestResponse:
        """Trigger a sync operation."""
        body = request.body if isinstance(request.body, dict) else {}

        # Record sync session
        session = {
            "id": f"sync-{len(self._data_store.sync_sessions) + 1}",
            "status": "completed",
            "started_at": datetime.now().isoformat(),
            "completed_at": datetime.now().isoformat(),
            "epics_synced": len(self._data_store.epics),
            "stories_synced": sum(len(e.stories) for e in self._data_store.epics.values()),
            "operation": body.get("operation", "push"),
        }
        self._data_store.sync_sessions.append(session)

        return RestResponse.success(
            {
                "message": "Sync completed successfully",
                "session": session,
            },
            request_id=request.request_id,
        )

    def _handle_sync_status(self, request: RestRequest) -> RestResponse:
        """Get sync status."""
        last_sync = self._data_store.sync_sessions[-1] if self._data_store.sync_sessions else None

        return RestResponse.success(
            {
                "status": "idle",
                "last_sync": last_sync,
                "total_syncs": len(self._data_store.sync_sessions),
            },
            request_id=request.request_id,
        )

    def _handle_sync_history(self, request: RestRequest) -> RestResponse:
        """Get sync history."""
        page = int(request.get_query_param("page", "1") or "1")
        per_page = int(request.get_query_param("per_page", "20") or "20")

        sessions = list(reversed(self._data_store.sync_sessions))

        # Apply pagination
        start = (page - 1) * per_page
        end = start + per_page
        page_sessions = sessions[start:end]

        paged = PagedResponse(
            items=page_sessions,
            total=len(sessions),
            page=page,
            per_page=per_page,
        )

        return RestResponse.success(paged.to_dict(), request_id=request.request_id)

    def _handle_workspace_stats(self, request: RestRequest) -> RestResponse:
        """Get workspace statistics."""
        total_epics = len(self._data_store.epics)
        total_stories = sum(len(e.stories) for e in self._data_store.epics.values())
        total_subtasks = sum(
            len(s.subtasks) for e in self._data_store.epics.values() for s in e.stories
        )
        total_points = sum(
            s.story_points for e in self._data_store.epics.values() for s in e.stories
        )

        # Status breakdown
        status_counts: dict[str, int] = {}
        for epic in self._data_store.epics.values():
            for story in epic.stories:
                status_name = story.status.name
                status_counts[status_name] = status_counts.get(status_name, 0) + 1

        # Priority breakdown
        priority_counts: dict[str, int] = {}
        for epic in self._data_store.epics.values():
            for story in epic.stories:
                priority_name = story.priority.name
                priority_counts[priority_name] = priority_counts.get(priority_name, 0) + 1

        return RestResponse.success(
            {
                "total_epics": total_epics,
                "total_stories": total_stories,
                "total_subtasks": total_subtasks,
                "total_story_points": total_points,
                "status_breakdown": status_counts,
                "priority_breakdown": priority_counts,
            },
            request_id=request.request_id,
        )

    # ==================== Data Conversion Helpers ====================

    def _epic_to_dict(self, epic: Epic, include_stories: bool = False) -> dict[str, Any]:
        """Convert Epic to dictionary."""
        result: dict[str, Any] = {
            "key": str(epic.key),
            "title": epic.title,
            "description": epic.description,
            "story_count": len(epic.stories),
            "total_points": sum(s.story_points for s in epic.stories),
            "completed_stories": sum(1 for s in epic.stories if s.status == Status.DONE),
        }

        if include_stories:
            result["stories"] = [self._story_to_dict(s) for s in epic.stories]

        return result

    def _story_to_dict(
        self,
        story: UserStory,
        epic_key: str | None = None,
        include_subtasks: bool = False,
    ) -> dict[str, Any]:
        """Convert UserStory to dictionary."""
        result: dict[str, Any] = {
            "id": str(story.id),
            "title": story.title,
            "description": story.description.to_plain_text() if story.description else None,
            "story_points": story.story_points,
            "status": story.status.name,
            "priority": story.priority.name,
            "assignee": story.assignee,
            "labels": story.labels,
            "sprint": story.sprint,
            "subtask_count": len(story.subtasks),
        }

        if epic_key:
            result["epic_key"] = epic_key

        if include_subtasks:
            result["subtasks"] = [self._subtask_to_dict(st) for st in story.subtasks]

        return result

    def _subtask_to_dict(self, subtask: Subtask) -> dict[str, Any]:
        """Convert Subtask to dictionary."""
        return {
            "id": subtask.id,
            "number": subtask.number,
            "name": subtask.name,
            "description": subtask.description,
            "story_points": subtask.story_points,
            "status": subtask.status.name,
            "priority": subtask.priority.name if subtask.priority else None,
            "assignee": subtask.assignee,
        }


def create_rest_server(
    host: str = "0.0.0.0",
    port: int = 8080,
    base_path: str = "/api/v1",
    enable_cors: bool = True,
    enable_docs: bool = True,
    event_bus: "EventBus | None" = None,
) -> SpectraRestServer:
    """
    Factory function to create a REST API server.

    Args:
        host: Host to bind to.
        port: Port to listen on.
        base_path: Base path for all API routes.
        enable_cors: Whether to enable CORS.
        enable_docs: Whether to enable API documentation.
        event_bus: Optional event bus for sync events.

    Returns:
        Configured REST API server instance.
    """
    return SpectraRestServer(
        host=host,
        port=port,
        base_path=base_path,
        enable_cors=enable_cors,
        enable_docs=enable_docs,
        event_bus=event_bus,
    )
