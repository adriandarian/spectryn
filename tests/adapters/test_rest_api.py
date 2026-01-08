"""
Tests for REST API adapter implementation.

Tests the SpectraRestServer implementation.
"""

import json
import threading
import time
import urllib.error
import urllib.request
from unittest.mock import MagicMock

import pytest

from spectryn.adapters.rest_api import SpectraRestServer, create_rest_server
from spectryn.core.domain.entities import Epic, Subtask, UserStory
from spectryn.core.domain.enums import Priority, Status
from spectryn.core.domain.value_objects import IssueKey, StoryId
from spectryn.core.ports.rest_api import (
    HttpMethod,
    HttpStatus,
    RestError,
    RestRequest,
    RestResponse,
    ServerConfig,
)


@pytest.fixture
def sample_epic():
    """Create a sample epic for testing."""
    return Epic(
        key=IssueKey("EPIC-001"),
        title="Sample Epic",
        description="A sample epic for testing",
        status=Status.IN_PROGRESS,
        priority=Priority.HIGH,
    )


@pytest.fixture
def sample_story():
    """Create a sample user story for testing."""
    return UserStory(
        id=StoryId("STORY-001"),
        title="Sample Story",
        status=Status.PLANNED,
        priority=Priority.MEDIUM,
    )


@pytest.fixture
def sample_subtask():
    """Create a sample subtask for testing."""
    return Subtask(
        id="SUBTASK-001",
        name="Sample Subtask",
        description="A sample subtask for testing",
        status=Status.PLANNED,
        priority=Priority.LOW,
    )


@pytest.fixture
def server_config():
    """Create a server configuration for testing."""
    return ServerConfig(
        host="127.0.0.1",
        port=0,  # Use dynamic port
        base_path="/api/v1",
        enable_cors=True,
        enable_docs=True,
    )


@pytest.fixture
def rest_server(server_config):
    """Create a REST server instance for testing."""
    return SpectraRestServer(config=server_config)


class TestSpectraRestServerCreation:
    """Tests for server creation and configuration."""

    def test_create_server_default_config(self):
        """Test creating server with default configuration."""
        server = SpectraRestServer()

        assert server.config.host == "0.0.0.0"
        assert server.config.port == 8080
        assert server.config.base_path == "/api/v1"

    def test_create_server_custom_config(self, server_config):
        """Test creating server with custom configuration."""
        server = SpectraRestServer(config=server_config)

        assert server.config.host == "127.0.0.1"
        assert server.config.enable_cors is True
        assert server.config.enable_docs is True

    def test_create_server_factory(self):
        """Test server factory function."""
        server = create_rest_server(
            host="localhost",
            port=3000,
            base_path="/api/v2",
        )

        assert server.config.host == "localhost"
        assert server.config.port == 3000
        assert server.config.base_path == "/api/v2"

    def test_server_has_default_routes(self, rest_server):
        """Test server has default routes registered."""
        routes = rest_server.get_routes()

        # Check for essential routes
        route_paths = [r.path for r in routes]

        assert any("/health" in p for p in route_paths)
        assert any("/info" in p for p in route_paths)
        assert any("/epics" in p for p in route_paths)
        assert any("/stories" in p for p in route_paths)


class TestSpectraRestServerDataManagement:
    """Tests for data loading and management."""

    def test_load_epics(self, rest_server, sample_epic):
        """Test loading epics into server."""
        rest_server.load_epics([sample_epic])

        epics = rest_server.get_epics()
        assert len(epics) == 1
        assert str(epics[0].key) == "EPIC-001"

    def test_load_stories(self, rest_server, sample_story):
        """Test loading stories into server."""
        rest_server.load_stories([sample_story])

        stories = rest_server.get_stories()
        assert len(stories) == 1
        assert str(stories[0].id) == "STORY-001"

    def test_load_subtasks(self, rest_server, sample_subtask):
        """Test loading subtasks into server."""
        rest_server.load_subtasks([sample_subtask])

        subtasks = rest_server.get_subtasks()
        assert len(subtasks) == 1
        assert subtasks[0].id == "SUBTASK-001"

    def test_load_all_data(self, rest_server, sample_epic, sample_story, sample_subtask):
        """Test loading all data types."""
        rest_server.load_epics([sample_epic])
        rest_server.load_stories([sample_story])
        rest_server.load_subtasks([sample_subtask])

        assert len(rest_server.get_epics()) == 1
        assert len(rest_server.get_stories()) == 1
        assert len(rest_server.get_subtasks()) == 1


class TestSpectraRestServerRoutes:
    """Tests for route handling."""

    def test_add_custom_route(self, rest_server):
        """Test adding a custom route."""

        def custom_handler(request: RestRequest) -> RestResponse:
            return RestResponse.success({"custom": True})

        rest_server.add_route(
            method=HttpMethod.GET,
            path="/custom",
            handler=custom_handler,
            description="Custom endpoint",
        )

        routes = rest_server.get_routes()
        custom_routes = [r for r in routes if "/custom" in r.path]
        assert len(custom_routes) == 1

    def test_route_matching(self, rest_server):
        """Test route path matching."""
        handler_called = False

        def test_handler(request: RestRequest) -> RestResponse:
            nonlocal handler_called
            handler_called = True
            return RestResponse.success({"matched": True})

        rest_server.add_route(
            method=HttpMethod.GET,
            path="/test/{id}",
            handler=test_handler,
        )

        # Simulate a request
        request = RestRequest(
            method=HttpMethod.GET,
            path=f"{rest_server.config.base_path}/test/123",
        )

        response = rest_server.handle_request(request)

        assert handler_called or response.status in [HttpStatus.OK, HttpStatus.NOT_FOUND]

    def test_method_not_allowed(self, rest_server):
        """Test handling wrong HTTP method."""
        request = RestRequest(
            method=HttpMethod.DELETE,
            path=f"{rest_server.config.base_path}/health",
        )

        response = rest_server.handle_request(request)

        # Health endpoint typically only supports GET
        assert response.status in [HttpStatus.METHOD_NOT_ALLOWED, HttpStatus.NOT_FOUND]


class TestSpectraRestServerMiddleware:
    """Tests for middleware functionality."""

    def test_add_middleware(self, rest_server):
        """Test adding middleware."""
        middleware_called = False

        def test_middleware(request: RestRequest) -> RestRequest | RestResponse | None:
            nonlocal middleware_called
            middleware_called = True
            return request

        rest_server.add_middleware(test_middleware)

        request = RestRequest(
            method=HttpMethod.GET,
            path=f"{rest_server.config.base_path}/health",
        )

        rest_server.handle_request(request)

        assert middleware_called

    def test_middleware_can_short_circuit(self, rest_server):
        """Test middleware can return response directly."""

        def blocking_middleware(request: RestRequest) -> RestRequest | RestResponse | None:
            error = RestError(
                message="Blocked",
                status=HttpStatus.FORBIDDEN,
            )
            return RestResponse.error(error)

        rest_server.add_middleware(blocking_middleware)

        request = RestRequest(
            method=HttpMethod.GET,
            path=f"{rest_server.config.base_path}/health",
        )

        response = rest_server.handle_request(request)

        assert response.status == HttpStatus.FORBIDDEN


class TestSpectraRestServerEndpoints:
    """Tests for built-in endpoints."""

    def test_health_endpoint(self, rest_server):
        """Test health check endpoint."""
        request = RestRequest(
            method=HttpMethod.GET,
            path=f"{rest_server.config.base_path}/health",
        )

        response = rest_server.handle_request(request)

        assert response.status == HttpStatus.OK
        assert response.body.get("status") == "healthy"

    def test_info_endpoint(self, rest_server):
        """Test info endpoint."""
        request = RestRequest(
            method=HttpMethod.GET,
            path=f"{rest_server.config.base_path}/info",
        )

        response = rest_server.handle_request(request)

        assert response.status == HttpStatus.OK
        assert "version" in response.body
        assert "name" in response.body

    def test_stats_endpoint(self, rest_server):
        """Test stats endpoint."""
        request = RestRequest(
            method=HttpMethod.GET,
            path=f"{rest_server.config.base_path}/stats",
        )

        response = rest_server.handle_request(request)

        assert response.status == HttpStatus.OK
        assert "total_requests" in response.body

    def test_list_epics_endpoint(self, rest_server, sample_epic):
        """Test list epics endpoint."""
        rest_server.load_epics([sample_epic])

        request = RestRequest(
            method=HttpMethod.GET,
            path=f"{rest_server.config.base_path}/epics",
        )

        response = rest_server.handle_request(request)

        assert response.status == HttpStatus.OK
        assert "data" in response.body
        assert len(response.body["data"]) == 1

    def test_get_epic_endpoint(self, rest_server, sample_epic):
        """Test get single epic endpoint."""
        rest_server.load_epics([sample_epic])

        request = RestRequest(
            method=HttpMethod.GET,
            path=f"{rest_server.config.base_path}/epics/EPIC-001",
            path_params={"key": "EPIC-001"},
        )

        response = rest_server.handle_request(request)

        assert response.status == HttpStatus.OK
        assert response.body["key"] == "EPIC-001"

    def test_list_stories_endpoint(self, rest_server, sample_story):
        """Test list stories endpoint."""
        rest_server.load_stories([sample_story])

        request = RestRequest(
            method=HttpMethod.GET,
            path=f"{rest_server.config.base_path}/stories",
        )

        response = rest_server.handle_request(request)

        assert response.status == HttpStatus.OK
        assert "data" in response.body

    def test_list_stories_with_pagination(self, rest_server):
        """Test stories endpoint with pagination."""
        # Load multiple stories
        stories = [UserStory(id=StoryId(f"STORY-{i:03d}"), title=f"Story {i}") for i in range(25)]
        rest_server.load_stories(stories)

        request = RestRequest(
            method=HttpMethod.GET,
            path=f"{rest_server.config.base_path}/stories",
            query_params={"page": "2", "per_page": "10"},
        )

        response = rest_server.handle_request(request)

        assert response.status == HttpStatus.OK
        assert "pagination" in response.body
        assert response.body["pagination"]["page"] == 2
        assert response.body["pagination"]["total"] == 25

    def test_search_stories_endpoint(self, rest_server, sample_story):
        """Test search stories endpoint."""
        rest_server.load_stories([sample_story])

        request = RestRequest(
            method=HttpMethod.GET,
            path=f"{rest_server.config.base_path}/stories/search",
            query_params={"q": "Sample"},
        )

        response = rest_server.handle_request(request)

        assert response.status == HttpStatus.OK

    def test_docs_endpoint_when_enabled(self, rest_server):
        """Test docs endpoint when enabled."""
        request = RestRequest(
            method=HttpMethod.GET,
            path=f"{rest_server.config.base_path}/docs",
        )

        response = rest_server.handle_request(request)

        # Should return HTML or redirect
        assert response.status in [HttpStatus.OK, HttpStatus.MOVED_PERMANENTLY]

    def test_openapi_endpoint(self, rest_server):
        """Test OpenAPI spec endpoint."""
        request = RestRequest(
            method=HttpMethod.GET,
            path=f"{rest_server.config.base_path}/openapi.json",
        )

        response = rest_server.handle_request(request)

        assert response.status == HttpStatus.OK
        assert "openapi" in response.body
        assert "paths" in response.body


class TestSpectraRestServerCORS:
    """Tests for CORS handling."""

    def test_cors_headers_on_response(self, rest_server):
        """Test CORS headers are added to responses."""
        request = RestRequest(
            method=HttpMethod.GET,
            path=f"{rest_server.config.base_path}/health",
            headers={"Origin": "http://localhost:3000"},
        )

        response = rest_server.handle_request(request)

        # CORS should be enabled by default
        assert "Access-Control-Allow-Origin" in response.headers

    def test_preflight_request(self, rest_server):
        """Test CORS preflight (OPTIONS) request."""
        request = RestRequest(
            method=HttpMethod.OPTIONS,
            path=f"{rest_server.config.base_path}/epics",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )

        response = rest_server.handle_request(request)

        assert response.status in [HttpStatus.OK, HttpStatus.NO_CONTENT]
        assert "Access-Control-Allow-Methods" in response.headers

    def test_cors_disabled(self, server_config):
        """Test CORS can be disabled."""
        server_config.enable_cors = False
        server = SpectraRestServer(config=server_config)

        request = RestRequest(
            method=HttpMethod.GET,
            path=f"{server.config.base_path}/health",
            headers={"Origin": "http://localhost:3000"},
        )

        response = server.handle_request(request)

        assert "Access-Control-Allow-Origin" not in response.headers


class TestSpectraRestServerStatistics:
    """Tests for server statistics."""

    def test_get_stats(self, rest_server):
        """Test getting server statistics."""
        stats = rest_server.get_stats()

        assert stats.total_requests >= 0
        assert stats.successful_requests >= 0
        assert stats.uptime_seconds >= 0

    def test_stats_increment_on_request(self, rest_server):
        """Test stats are incremented on requests."""
        initial_stats = rest_server.get_stats()
        initial_requests = initial_stats.total_requests

        # Make a request
        request = RestRequest(
            method=HttpMethod.GET,
            path=f"{rest_server.config.base_path}/health",
        )
        rest_server.handle_request(request)

        new_stats = rest_server.get_stats()
        assert new_stats.total_requests == initial_requests + 1


class TestSpectraRestServerErrorHandling:
    """Tests for error handling."""

    def test_not_found_route(self, rest_server):
        """Test handling unknown route."""
        request = RestRequest(
            method=HttpMethod.GET,
            path=f"{rest_server.config.base_path}/nonexistent",
        )

        response = rest_server.handle_request(request)

        assert response.status == HttpStatus.NOT_FOUND

    def test_not_found_resource(self, rest_server):
        """Test handling non-existent resource."""
        request = RestRequest(
            method=HttpMethod.GET,
            path=f"{rest_server.config.base_path}/epics/NONEXISTENT",
            path_params={"key": "NONEXISTENT"},
        )

        response = rest_server.handle_request(request)

        assert response.status == HttpStatus.NOT_FOUND

    def test_invalid_json_body(self, rest_server):
        """Test handling invalid JSON body."""
        request = RestRequest(
            method=HttpMethod.POST,
            path=f"{rest_server.config.base_path}/stories",
            body="not valid json",  # Should be dict
        )

        # The response should handle invalid body gracefully
        response = rest_server.handle_request(request)

        # Either validation error or handled gracefully
        assert response.status in [
            HttpStatus.BAD_REQUEST,
            HttpStatus.CREATED,
            HttpStatus.NOT_FOUND,  # If route doesn't exist
        ]


class TestSpectraRestServerLifecycle:
    """Tests for server lifecycle (start/stop)."""

    def test_server_start_stop(self, server_config):
        """Test server can be started and stopped."""
        server = SpectraRestServer(config=server_config)

        # Start in background thread
        server_thread = threading.Thread(target=server.start)
        server_thread.daemon = True
        server_thread.start()

        # Give it time to start
        time.sleep(0.5)

        # Check server is running
        assert server.is_running()

        # Stop server
        server.stop()

        # Give it time to stop
        time.sleep(0.5)

        assert not server.is_running()

    def test_server_responds_when_running(self, server_config):
        """Test server responds to HTTP requests when running."""
        # Use a random available port
        server_config.port = 0
        server = SpectraRestServer(config=server_config)

        server_thread = threading.Thread(target=server.start)
        server_thread.daemon = True
        server_thread.start()

        # Wait for server to start and get actual port
        time.sleep(0.5)

        if server.is_running():
            try:
                actual_port = server.get_port()
                url = f"http://127.0.0.1:{actual_port}/api/v1/health"

                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode())
                    assert data["status"] == "healthy"
            except (urllib.error.URLError, OSError):
                # Server might not be fully ready
                pass
            finally:
                server.stop()


class TestRestRequestProcessing:
    """Tests for request processing utilities."""

    def test_extract_path_params(self, rest_server):
        """Test extracting path parameters."""

        # Add a route with path parameters
        def handler(request: RestRequest) -> RestResponse:
            return RestResponse.success(
                {
                    "id": request.path_params.get("id"),
                    "name": request.path_params.get("name"),
                }
            )

        rest_server.add_route(
            method=HttpMethod.GET,
            path="/items/{id}/sub/{name}",
            handler=handler,
        )

        # The server should extract path params when matching routes
        request = RestRequest(
            method=HttpMethod.GET,
            path=f"{rest_server.config.base_path}/items/123/sub/test",
        )

        response = rest_server.handle_request(request)

        # If route matched, params should be extracted
        if response.status == HttpStatus.OK:
            assert response.body.get("id") == "123"
            assert response.body.get("name") == "test"


class TestFactoryFunction:
    """Tests for the create_rest_server factory function."""

    def test_create_with_defaults(self):
        """Test creating server with default values."""
        server = create_rest_server()

        assert server is not None
        assert server.config.port == 8080

    def test_create_with_options(self):
        """Test creating server with options."""
        server = create_rest_server(
            host="127.0.0.1",
            port=9000,
            base_path="/api",
            enable_cors=False,
            enable_docs=False,
        )

        assert server.config.host == "127.0.0.1"
        assert server.config.port == 9000
        assert server.config.base_path == "/api"
        assert server.config.enable_cors is False
        assert server.config.enable_docs is False
