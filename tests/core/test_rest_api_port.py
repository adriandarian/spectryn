"""
Tests for REST API port interface.

Tests the abstract interface and data types for REST API servers.
"""

from datetime import datetime

import pytest

from spectryn.core.ports.rest_api import (
    ConflictError,
    ErrorCode,
    HttpMethod,
    HttpStatus,
    NotFoundError,
    PagedResponse,
    RestApiError,
    RestError,
    RestRequest,
    RestResponse,
    RouteInfo,
    ServerConfig,
    ServerStats,
    ValidationError,
)


class TestRestError:
    """Tests for RestError dataclass."""

    def test_default_error(self):
        """Test default error creation."""
        error = RestError(message="Something went wrong")

        assert error.message == "Something went wrong"
        assert error.code == ErrorCode.INTERNAL_ERROR
        assert error.status == HttpStatus.INTERNAL_SERVER_ERROR
        assert error.details == {}
        assert error.path is None

    def test_error_with_all_fields(self):
        """Test error with all fields specified."""
        error = RestError(
            message="Not found",
            code=ErrorCode.NOT_FOUND,
            status=HttpStatus.NOT_FOUND,
            details={"resource": "epic", "id": "123"},
            path="/api/v1/epics/123",
        )

        assert error.message == "Not found"
        assert error.code == ErrorCode.NOT_FOUND
        assert error.status == HttpStatus.NOT_FOUND
        assert error.details == {"resource": "epic", "id": "123"}
        assert error.path == "/api/v1/epics/123"

    def test_to_dict(self):
        """Test conversion to dictionary."""
        error = RestError(
            message="Validation failed",
            code=ErrorCode.VALIDATION_ERROR,
            status=HttpStatus.BAD_REQUEST,
            details={"field": "title"},
            path="/api/v1/stories",
        )

        result = error.to_dict()

        assert "error" in result
        assert result["error"]["message"] == "Validation failed"
        assert result["error"]["code"] == "VALIDATION_ERROR"
        assert result["error"]["status"] == 400
        assert result["error"]["details"] == {"field": "title"}
        assert result["error"]["path"] == "/api/v1/stories"


class TestRestRequest:
    """Tests for RestRequest dataclass."""

    def test_basic_request(self):
        """Test basic request creation."""
        request = RestRequest(
            method=HttpMethod.GET,
            path="/api/v1/epics",
        )

        assert request.method == HttpMethod.GET
        assert request.path == "/api/v1/epics"
        assert request.query_params == {}
        assert request.headers == {}
        assert request.body is None
        assert request.path_params == {}
        assert request.request_id  # Auto-generated

    def test_request_with_all_fields(self):
        """Test request with all fields."""
        request = RestRequest(
            method=HttpMethod.POST,
            path="/api/v1/epics",
            query_params={"page": "1", "per_page": "20"},
            headers={"Content-Type": "application/json", "Authorization": "Bearer token"},
            body={"name": "New Epic"},
            path_params={"id": "123"},
            client_ip="127.0.0.1",
            request_id="req-123",
        )

        assert request.method == HttpMethod.POST
        assert request.body == {"name": "New Epic"}
        assert request.request_id == "req-123"
        assert request.client_ip == "127.0.0.1"

    def test_get_header_case_insensitive(self):
        """Test header retrieval is case-insensitive."""
        request = RestRequest(
            method=HttpMethod.GET,
            path="/api/v1/test",
            headers={"Content-Type": "application/json"},
        )

        assert request.get_header("content-type") == "application/json"
        assert request.get_header("CONTENT-TYPE") == "application/json"
        assert request.get_header("Content-Type") == "application/json"

    def test_get_header_default(self):
        """Test header retrieval with default."""
        request = RestRequest(method=HttpMethod.GET, path="/test")

        assert request.get_header("X-Custom") is None
        assert request.get_header("X-Custom", "default") == "default"

    def test_get_query_param(self):
        """Test query parameter retrieval."""
        request = RestRequest(
            method=HttpMethod.GET,
            path="/test",
            query_params={"page": "1", "tags": ["a", "b"]},
        )

        assert request.get_query_param("page") == "1"
        assert request.get_query_param("missing") is None
        assert request.get_query_param("missing", "default") == "default"
        # List values return first element
        assert request.get_query_param("tags") == "a"

    def test_get_query_param_list(self):
        """Test query parameter list retrieval."""
        request = RestRequest(
            method=HttpMethod.GET,
            path="/test",
            query_params={"single": "value", "multi": ["a", "b", "c"]},
        )

        assert request.get_query_param_list("single") == ["value"]
        assert request.get_query_param_list("multi") == ["a", "b", "c"]
        assert request.get_query_param_list("missing") == []

    def test_to_dict(self):
        """Test conversion to dictionary."""
        request = RestRequest(
            method=HttpMethod.GET,
            path="/api/v1/epics",
            headers={"Authorization": "Bearer secret"},
            body={"test": "data"},
        )

        result = request.to_dict()

        assert result["method"] == "GET"
        assert result["path"] == "/api/v1/epics"
        # Authorization header should be excluded
        assert "Authorization" not in result["headers"]
        assert result["has_body"] is True


class TestRestResponse:
    """Tests for RestResponse dataclass."""

    def test_success_response(self):
        """Test success response creation."""
        response = RestResponse(
            status=HttpStatus.OK,
            body={"data": "value"},
        )

        assert response.status == HttpStatus.OK
        assert response.body == {"data": "value"}

    def test_success_factory(self):
        """Test success factory method."""
        response = RestResponse.success(
            data={"items": []},
            status=HttpStatus.OK,
            request_id="req-123",
        )

        assert response.status == HttpStatus.OK
        assert response.body == {"items": []}
        assert response.request_id == "req-123"

    def test_created_factory(self):
        """Test created factory method."""
        response = RestResponse.created(
            data={"id": "123"},
            location="/api/v1/epics/123",
        )

        assert response.status == HttpStatus.CREATED
        assert response.body == {"id": "123"}
        assert response.headers["Location"] == "/api/v1/epics/123"

    def test_no_content_factory(self):
        """Test no content factory method."""
        response = RestResponse.no_content()

        assert response.status == HttpStatus.NO_CONTENT
        assert response.body is None

    def test_error_factory(self):
        """Test error factory method."""
        error = RestError(
            message="Not found",
            code=ErrorCode.NOT_FOUND,
            status=HttpStatus.NOT_FOUND,
        )

        response = RestResponse.error(error)

        assert response.status == HttpStatus.NOT_FOUND
        assert "error" in response.body

    def test_not_found_factory(self):
        """Test not found factory method."""
        response = RestResponse.not_found(
            message="Epic not found",
            path="/api/v1/epics/123",
        )

        assert response.status == HttpStatus.NOT_FOUND
        assert response.body["error"]["message"] == "Epic not found"

    def test_bad_request_factory(self):
        """Test bad request factory method."""
        response = RestResponse.bad_request(
            message="Invalid input",
            details={"field": "title", "error": "required"},
        )

        assert response.status == HttpStatus.BAD_REQUEST
        assert response.body["error"]["details"]["field"] == "title"

    def test_internal_error_factory(self):
        """Test internal error factory method."""
        response = RestResponse.internal_error(message="Database error")

        assert response.status == HttpStatus.INTERNAL_SERVER_ERROR
        assert response.body["error"]["message"] == "Database error"


class TestPagedResponse:
    """Tests for PagedResponse dataclass."""

    def test_default_paged_response(self):
        """Test default paged response."""
        paged = PagedResponse(
            items=[{"id": 1}, {"id": 2}],
            total=100,
        )

        assert paged.items == [{"id": 1}, {"id": 2}]
        assert paged.total == 100
        assert paged.page == 1
        assert paged.per_page == 20
        assert paged.total_pages == 5
        assert paged.has_next is True
        assert paged.has_prev is False

    def test_paged_response_calculations(self):
        """Test pagination calculations."""
        paged = PagedResponse(
            items=[{"id": 1}],
            total=45,
            page=3,
            per_page=10,
        )

        assert paged.total_pages == 5
        assert paged.has_next is True
        assert paged.has_prev is True

    def test_paged_response_last_page(self):
        """Test last page detection."""
        paged = PagedResponse(
            items=[{"id": 1}],
            total=30,
            page=3,
            per_page=10,
        )

        assert paged.total_pages == 3
        assert paged.has_next is False
        assert paged.has_prev is True

    def test_to_dict(self):
        """Test conversion to dictionary."""
        paged = PagedResponse(
            items=[{"id": 1}],
            total=50,
            page=2,
            per_page=10,
        )

        result = paged.to_dict()

        assert "data" in result
        assert "pagination" in result
        assert result["pagination"]["total"] == 50
        assert result["pagination"]["page"] == 2
        assert result["pagination"]["per_page"] == 10
        assert result["pagination"]["total_pages"] == 5
        assert result["pagination"]["has_next"] is True
        assert result["pagination"]["has_prev"] is True


class TestServerConfig:
    """Tests for ServerConfig dataclass."""

    def test_default_config(self):
        """Test default configuration."""
        config = ServerConfig()

        assert config.host == "0.0.0.0"
        assert config.port == 8080
        assert config.base_path == "/api/v1"
        assert config.enable_cors is True
        assert config.cors_origins == ["*"]
        assert config.enable_docs is True
        assert config.docs_path == "/docs"
        assert config.max_request_size == 10 * 1024 * 1024
        assert config.request_timeout == 30.0

    def test_custom_config(self):
        """Test custom configuration."""
        config = ServerConfig(
            host="127.0.0.1",
            port=3000,
            base_path="/api/v2",
            enable_cors=False,
            enable_docs=False,
        )

        assert config.host == "127.0.0.1"
        assert config.port == 3000
        assert config.base_path == "/api/v2"
        assert config.enable_cors is False
        assert config.enable_docs is False


class TestServerStats:
    """Tests for ServerStats dataclass."""

    def test_default_stats(self):
        """Test default statistics."""
        stats = ServerStats()

        assert stats.total_requests == 0
        assert stats.successful_requests == 0
        assert stats.client_errors == 0
        assert stats.server_errors == 0
        assert stats.avg_response_time_ms == 0.0
        assert stats.active_connections == 0
        assert stats.uptime_seconds >= 0

    def test_error_rate_calculation(self):
        """Test error rate calculation."""
        stats = ServerStats(
            total_requests=100,
            successful_requests=80,
            client_errors=15,
            server_errors=5,
        )

        assert stats.error_rate == 20.0

    def test_error_rate_zero_requests(self):
        """Test error rate with zero requests."""
        stats = ServerStats()
        assert stats.error_rate == 0.0

    def test_to_dict(self):
        """Test conversion to dictionary."""
        stats = ServerStats(
            total_requests=100,
            successful_requests=90,
            client_errors=8,
            server_errors=2,
            avg_response_time_ms=50.5,
        )

        result = stats.to_dict()

        assert result["total_requests"] == 100
        assert result["successful_requests"] == 90
        assert result["client_errors"] == 8
        assert result["server_errors"] == 2
        assert result["error_rate_percent"] == 10.0
        assert result["avg_response_time_ms"] == 50.5


class TestRouteInfo:
    """Tests for RouteInfo dataclass."""

    def test_route_info(self):
        """Test route info creation."""
        route = RouteInfo(
            method=HttpMethod.GET,
            path="/api/v1/epics/{id}",
            handler_name="get_epic",
            description="Get an epic by ID",
            parameters={"id": "Epic identifier"},
        )

        assert route.method == HttpMethod.GET
        assert route.path == "/api/v1/epics/{id}"
        assert route.handler_name == "get_epic"
        assert route.description == "Get an epic by ID"
        assert route.parameters["id"] == "Epic identifier"


class TestRestApiError:
    """Tests for REST API exception classes."""

    def test_rest_api_error(self):
        """Test base REST API error."""
        error = RestApiError(
            message="Something went wrong",
            code=ErrorCode.INTERNAL_ERROR,
            status=HttpStatus.INTERNAL_SERVER_ERROR,
            details={"context": "test"},
        )

        assert str(error) == "Something went wrong"
        assert error.code == ErrorCode.INTERNAL_ERROR
        assert error.status == HttpStatus.INTERNAL_SERVER_ERROR
        assert error.details == {"context": "test"}

        rest_error = error.to_error()
        assert rest_error.message == "Something went wrong"
        assert rest_error.code == ErrorCode.INTERNAL_ERROR

    def test_validation_error(self):
        """Test validation error."""
        error = ValidationError(
            message="Invalid input",
            details={"field": "title"},
        )

        assert error.code == ErrorCode.VALIDATION_ERROR
        assert error.status == HttpStatus.BAD_REQUEST

    def test_not_found_error(self):
        """Test not found error."""
        error = NotFoundError(message="Epic not found")

        assert error.code == ErrorCode.NOT_FOUND
        assert error.status == HttpStatus.NOT_FOUND

    def test_conflict_error(self):
        """Test conflict error."""
        error = ConflictError(
            message="Resource already exists",
            details={"existing_id": "123"},
        )

        assert error.code == ErrorCode.CONFLICT
        assert error.status == HttpStatus.CONFLICT


class TestHttpEnums:
    """Tests for HTTP enums."""

    def test_http_methods(self):
        """Test HTTP methods enum."""
        assert HttpMethod.GET.value == "GET"
        assert HttpMethod.POST.value == "POST"
        assert HttpMethod.PUT.value == "PUT"
        assert HttpMethod.PATCH.value == "PATCH"
        assert HttpMethod.DELETE.value == "DELETE"

    def test_http_status_codes(self):
        """Test HTTP status codes enum."""
        assert HttpStatus.OK.value == 200
        assert HttpStatus.CREATED.value == 201
        assert HttpStatus.NO_CONTENT.value == 204
        assert HttpStatus.BAD_REQUEST.value == 400
        assert HttpStatus.NOT_FOUND.value == 404
        assert HttpStatus.INTERNAL_SERVER_ERROR.value == 500

    def test_error_codes(self):
        """Test error codes enum."""
        assert ErrorCode.VALIDATION_ERROR.value == "VALIDATION_ERROR"
        assert ErrorCode.NOT_FOUND.value == "NOT_FOUND"
        assert ErrorCode.INTERNAL_ERROR.value == "INTERNAL_ERROR"
        assert ErrorCode.SYNC_FAILED.value == "SYNC_FAILED"
