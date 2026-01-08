"""
Tests for health check endpoint.

Tests health server, status tracking, and HTTP endpoints.
"""

import json
import threading
import time
from unittest.mock import Mock
from urllib.error import URLError
from urllib.request import urlopen

import pytest

from spectryn.cli.health import (
    HealthConfig,
    HealthServer,
    HealthStatus,
    configure_health,
    get_health_server,
)


# =============================================================================
# HealthStatus Tests
# =============================================================================


class TestHealthStatus:
    """Tests for HealthStatus dataclass."""

    def test_default_values(self):
        """Test HealthStatus has sensible defaults."""
        status = HealthStatus()

        assert status.healthy is True
        assert status.ready is True
        assert status.components == {}
        assert status.version == "2.0.0"
        assert status.service_name == "spectra"
        assert status.uptime_seconds == 0.0
        assert status.syncs_total == 0

    def test_custom_values(self):
        """Test HealthStatus with custom values."""
        status = HealthStatus(
            healthy=False,
            ready=False,
            components={"tracker": True, "database": False},
            uptime_seconds=123.45,
            syncs_total=10,
            syncs_successful=8,
            syncs_failed=2,
        )

        assert status.healthy is False
        assert status.ready is False
        assert status.components["tracker"] is True
        assert status.components["database"] is False
        assert status.syncs_total == 10

    def test_to_dict(self):
        """Test HealthStatus.to_dict()."""
        status = HealthStatus(
            healthy=True,
            ready=True,
            components={"tracker": True},
            uptime_seconds=100.5,
            syncs_total=5,
            syncs_successful=4,
            syncs_failed=1,
            last_sync="2025-01-01T00:00:00Z",
        )

        data = status.to_dict()

        assert data["status"] == "healthy"
        assert data["ready"] is True
        assert data["version"] == "2.0.0"
        assert data["uptime_seconds"] == 100.5
        assert data["components"]["tracker"] == "up"
        assert data["stats"]["syncs_total"] == 5
        assert data["stats"]["syncs_successful"] == 4
        assert data["stats"]["syncs_failed"] == 1

    def test_to_dict_unhealthy(self):
        """Test HealthStatus.to_dict() when unhealthy."""
        status = HealthStatus(
            healthy=False,
            components={"tracker": False},
        )

        data = status.to_dict()

        assert data["status"] == "unhealthy"
        assert data["components"]["tracker"] == "down"


# =============================================================================
# HealthConfig Tests
# =============================================================================


class TestHealthConfig:
    """Tests for HealthConfig dataclass."""

    def test_default_values(self):
        """Test HealthConfig has sensible defaults."""
        config = HealthConfig()

        assert config.enabled is False
        assert config.port == 8080
        assert config.host == "0.0.0.0"
        assert config.check_tracker is True
        assert config.check_interval_seconds == 30.0

    def test_custom_values(self):
        """Test HealthConfig with custom values."""
        config = HealthConfig(
            enabled=True,
            port=9000,
            host="127.0.0.1",
            check_tracker=False,
        )

        assert config.enabled is True
        assert config.port == 9000
        assert config.host == "127.0.0.1"
        assert config.check_tracker is False


# =============================================================================
# HealthServer Tests
# =============================================================================


class TestHealthServer:
    """Tests for HealthServer class."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset the singleton instance before each test."""
        HealthServer._instance = None
        yield
        HealthServer._instance = None

    def test_get_instance_none_initially(self):
        """Test get_instance returns None initially."""
        assert HealthServer.get_instance() is None

    def test_configure_sets_instance(self):
        """Test configure sets the singleton."""
        config = HealthConfig()
        server = HealthServer.configure(config)

        assert server is not None
        assert HealthServer.get_instance() is server

    def test_start_when_disabled(self):
        """Test start returns False when disabled."""
        config = HealthConfig(enabled=False)
        server = HealthServer(config)

        result = server.start()
        assert result is False

    def test_get_status(self):
        """Test get_status returns current status."""
        config = HealthConfig()
        server = HealthServer(config)

        status = server.get_status()

        assert isinstance(status, HealthStatus)
        assert status.healthy is True
        assert status.uptime_seconds >= 0

    def test_record_sync_success(self):
        """Test record_sync increments counters."""
        config = HealthConfig()
        server = HealthServer(config)

        server.record_sync(success=True)
        server.record_sync(success=True)
        server.record_sync(success=False)

        status = server.get_status()
        assert status.syncs_total == 3
        assert status.syncs_successful == 2
        assert status.syncs_failed == 1

    def test_set_ready(self):
        """Test set_ready updates readiness."""
        config = HealthConfig()
        server = HealthServer(config)

        server.set_ready(False)
        status = server.get_status()
        assert status.ready is False

        server.set_ready(True)
        status = server.get_status()
        assert status.ready is True

    def test_set_component_status(self):
        """Test set_component_status updates component health."""
        config = HealthConfig()
        server = HealthServer(config)

        server.set_component_status("tracker", True)
        server.set_component_status("database", False)

        status = server.get_status()
        assert status.components["tracker"] is True
        assert status.components["database"] is False
        assert status.healthy is False  # One component is down

    def test_set_component_status_all_healthy(self):
        """Test overall health when all components are healthy."""
        config = HealthConfig()
        server = HealthServer(config)

        server.set_component_status("tracker", True)
        server.set_component_status("database", True)

        status = server.get_status()
        assert status.healthy is True

    def test_set_tracker_check(self):
        """Test set_tracker_check sets callback."""
        config = HealthConfig()
        server = HealthServer(config)

        check = Mock(return_value=True)
        server.set_tracker_check(check)

        assert server._tracker_check is check

    def test_stop_when_not_running(self):
        """Test stop when server is not running."""
        config = HealthConfig()
        server = HealthServer(config)

        # Should not raise
        server.stop()


# =============================================================================
# HTTP Server Tests (with actual server)
# =============================================================================


class TestHealthServerHTTP:
    """Tests for health server HTTP endpoints."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset the singleton instance before each test."""
        HealthServer._instance = None
        yield
        # Clean up any running servers
        if HealthServer._instance:
            HealthServer._instance.stop()
        HealthServer._instance = None

    @pytest.fixture
    def running_server(self):
        """Create and start a health server on a random port."""
        import socket

        # Find a free port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            port = s.getsockname()[1]

        config = HealthConfig(
            enabled=True,
            port=port,
            host="127.0.0.1",
            check_tracker=False,
        )
        server = HealthServer.configure(config)
        server.start()

        # Wait for server to start
        time.sleep(0.1)

        yield server, port

        server.stop()

    def test_root_endpoint(self, running_server):
        """Test / endpoint returns available endpoints."""
        _server, port = running_server

        response = urlopen(f"http://127.0.0.1:{port}/")
        data = json.loads(response.read())

        assert data["service"] == "spectra"
        assert "/health" in data["endpoints"]
        assert "/live" in data["endpoints"]
        assert "/ready" in data["endpoints"]

    def test_health_endpoint(self, running_server):
        """Test /health endpoint."""
        _server, port = running_server

        response = urlopen(f"http://127.0.0.1:{port}/health")
        data = json.loads(response.read())

        assert response.getcode() == 200
        assert data["status"] == "healthy"
        assert "uptime_seconds" in data

    def test_live_endpoint(self, running_server):
        """Test /live endpoint."""
        _server, port = running_server

        response = urlopen(f"http://127.0.0.1:{port}/live")
        data = json.loads(response.read())

        assert response.getcode() == 200
        assert data["status"] == "alive"

    def test_ready_endpoint(self, running_server):
        """Test /ready endpoint when ready."""
        _server, port = running_server

        response = urlopen(f"http://127.0.0.1:{port}/ready")
        data = json.loads(response.read())

        assert response.getcode() == 200
        assert data["status"] == "ready"

    def test_ready_endpoint_not_ready(self, running_server):
        """Test /ready endpoint when not ready."""
        server, port = running_server
        server.set_ready(False)

        try:
            urlopen(f"http://127.0.0.1:{port}/ready")
            pytest.fail("Expected 503 error")
        except URLError as e:
            assert e.code == 503

    def test_metrics_endpoint(self, running_server):
        """Test /metrics endpoint."""
        server, port = running_server
        server.record_sync(success=True)
        server.record_sync(success=False)

        response = urlopen(f"http://127.0.0.1:{port}/metrics")
        data = json.loads(response.read())

        assert response.getcode() == 200
        assert data["syncs"]["total"] == 2
        assert data["syncs"]["successful"] == 1
        assert data["syncs"]["failed"] == 1

    def test_health_endpoint_unhealthy(self, running_server):
        """Test /health endpoint when unhealthy."""
        server, port = running_server
        server.set_component_status("tracker", False)

        try:
            urlopen(f"http://127.0.0.1:{port}/health")
            pytest.fail("Expected 503 error")
        except URLError as e:
            assert e.code == 503

    def test_404_endpoint(self, running_server):
        """Test unknown endpoint returns 404."""
        _server, port = running_server

        try:
            urlopen(f"http://127.0.0.1:{port}/unknown")
            pytest.fail("Expected 404 error")
        except URLError as e:
            assert e.code == 404


# =============================================================================
# Helper Functions Tests
# =============================================================================


class TestHelperFunctions:
    """Tests for helper functions."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset the singleton instance before each test."""
        HealthServer._instance = None
        yield
        if HealthServer._instance:
            HealthServer._instance.stop()
        HealthServer._instance = None

    def test_configure_health_disabled(self):
        """Test configure_health when disabled."""
        server = configure_health(enabled=False)

        assert isinstance(server, HealthServer)
        assert server.config.enabled is False

    def test_configure_health_with_port(self):
        """Test configure_health with custom port."""
        server = configure_health(
            enabled=False,
            port=9000,
            host="127.0.0.1",
        )

        assert server.config.port == 9000
        assert server.config.host == "127.0.0.1"

    def test_get_health_server_none(self):
        """Test get_health_server returns None initially."""
        result = get_health_server()
        assert result is None

    def test_get_health_server_after_configure(self):
        """Test get_health_server after configure."""
        configure_health(enabled=False)

        result = get_health_server()
        assert result is not None


# =============================================================================
# CLI Integration Tests
# =============================================================================


class TestCLIIntegration:
    """Tests for CLI integration."""

    def test_health_flags_in_parser(self, cli_parser):
        """Test --health-* flags are recognized."""
        args = cli_parser.parse_args(
            [
                "--health",
                "--health-port",
                "9000",
                "--health-host",
                "127.0.0.1",
                "--input",
                "epic.md",
                "--epic",
                "TEST-123",
            ]
        )

        assert args.health is True
        assert args.health_port == 9000
        assert args.health_host == "127.0.0.1"

    def test_health_default_port(self, cli_parser):
        """Test default health port."""
        args = cli_parser.parse_args(
            [
                "--health",
                "--input",
                "epic.md",
                "--epic",
                "TEST-123",
            ]
        )

        assert args.health_port == 8080

    def test_health_default_host(self, cli_parser):
        """Test default health host."""
        args = cli_parser.parse_args(
            [
                "--health",
                "--input",
                "epic.md",
                "--epic",
                "TEST-123",
            ]
        )

        assert args.health_host == "0.0.0.0"

    def test_health_disabled_by_default(self, cli_parser):
        """Test health is disabled by default."""
        args = cli_parser.parse_args(
            [
                "--input",
                "epic.md",
                "--epic",
                "TEST-123",
            ]
        )

        assert args.health is False


# =============================================================================
# Thread Safety Tests
# =============================================================================


class TestThreadSafety:
    """Tests for thread safety."""

    def test_concurrent_status_updates(self):
        """Test concurrent status updates are safe."""
        config = HealthConfig()
        server = HealthServer(config)

        errors = []

        def update_status():
            try:
                for _ in range(100):
                    server.record_sync(success=True)
                    server.set_component_status("test", True)
                    _ = server.get_status()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=update_status) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

        status = server.get_status()
        assert status.syncs_total == 500  # 5 threads * 100 syncs


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset the singleton instance before each test."""
        HealthServer._instance = None
        yield
        if HealthServer._instance:
            HealthServer._instance.stop()
        HealthServer._instance = None

    def test_start_twice(self):
        """Test starting server twice returns True."""
        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            port = s.getsockname()[1]

        config = HealthConfig(enabled=True, port=port, host="127.0.0.1")
        server = HealthServer(config)

        result1 = server.start()
        result2 = server.start()

        assert result1 is True
        assert result2 is True  # Already running

        server.stop()

    def test_stop_twice(self):
        """Test stopping server twice is safe."""
        config = HealthConfig(enabled=False)
        server = HealthServer(config)

        server.stop()
        server.stop()  # Should not raise

    def test_uptime_increases(self):
        """Test uptime increases over time."""
        config = HealthConfig()
        server = HealthServer(config)

        status1 = server.get_status()
        time.sleep(0.1)
        status2 = server.get_status()

        assert status2.uptime_seconds > status1.uptime_seconds
