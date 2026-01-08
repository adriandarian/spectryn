"""
Tests for OpenTelemetry support.

Tests telemetry configuration, tracing, and metrics collection.
"""

from unittest.mock import patch

import pytest

from spectryn.cli.telemetry import (
    OTEL_AVAILABLE,
    PROMETHEUS_AVAILABLE,
    TelemetryConfig,
    TelemetryProvider,
    configure_prometheus,
    configure_telemetry,
    get_prometheus_metrics,
    get_telemetry,
    timed_api_call,
    traced,
)


# =============================================================================
# TelemetryConfig Tests
# =============================================================================


class TestTelemetryConfig:
    """Tests for TelemetryConfig dataclass."""

    def test_default_values(self):
        """Test TelemetryConfig has sensible defaults."""
        config = TelemetryConfig()

        assert config.enabled is False
        assert config.service_name == "spectra"
        assert config.service_version == "2.0.0"
        assert config.otlp_endpoint is None
        assert config.otlp_insecure is True
        assert config.console_export is False
        assert config.metrics_enabled is True
        assert config.metrics_port == 9464

    def test_custom_values(self):
        """Test TelemetryConfig with custom values."""
        config = TelemetryConfig(
            enabled=True,
            service_name="custom-service",
            otlp_endpoint="http://localhost:4317",
            console_export=True,
        )

        assert config.enabled is True
        assert config.service_name == "custom-service"
        assert config.otlp_endpoint == "http://localhost:4317"
        assert config.console_export is True

    def test_from_env_default(self):
        """Test TelemetryConfig.from_env with no env vars."""
        with patch.dict("os.environ", {}, clear=True):
            config = TelemetryConfig.from_env()

        assert config.enabled is False
        assert config.service_name == "spectra"

    def test_from_env_enabled(self):
        """Test TelemetryConfig.from_env with OTEL_ENABLED."""
        env = {
            "OTEL_ENABLED": "true",
            "OTEL_SERVICE_NAME": "test-service",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://otel:4317",
        }
        with patch.dict("os.environ", env, clear=True):
            config = TelemetryConfig.from_env()

        assert config.enabled is True
        assert config.service_name == "test-service"
        assert config.otlp_endpoint == "http://otel:4317"

    def test_from_env_various_true_values(self):
        """Test from_env accepts various true values."""
        for value in ["true", "1", "yes", "TRUE", "Yes"]:
            with patch.dict("os.environ", {"OTEL_ENABLED": value}, clear=True):
                config = TelemetryConfig.from_env()
                assert config.enabled is True, f"Failed for value: {value}"

    def test_from_env_false_values(self):
        """Test from_env with false values."""
        for value in ["false", "0", "no", "other"]:
            with patch.dict("os.environ", {"OTEL_ENABLED": value}, clear=True):
                config = TelemetryConfig.from_env()
                assert config.enabled is False, f"Failed for value: {value}"


# =============================================================================
# TelemetryProvider Tests
# =============================================================================


class TestTelemetryProvider:
    """Tests for TelemetryProvider class."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset the singleton instance before each test."""
        TelemetryProvider._instance = None
        yield
        TelemetryProvider._instance = None

    def test_get_instance_creates_singleton(self):
        """Test get_instance creates and returns singleton."""
        provider1 = TelemetryProvider.get_instance()
        provider2 = TelemetryProvider.get_instance()

        assert provider1 is provider2

    def test_configure_replaces_singleton(self):
        """Test configure replaces the singleton."""
        provider1 = TelemetryProvider.get_instance()

        config = TelemetryConfig(service_name="new-service")
        provider2 = TelemetryProvider.configure(config)

        assert provider1 is not provider2
        assert provider2.config.service_name == "new-service"

    def test_init_without_otel(self):
        """Test initialization without OpenTelemetry installed."""
        config = TelemetryConfig(enabled=True)
        provider = TelemetryProvider(config)

        # Should not crash, just log warning
        if not OTEL_AVAILABLE:
            result = provider.initialize()
            assert result is False

    def test_init_disabled(self):
        """Test initialization when disabled."""
        config = TelemetryConfig(enabled=False)
        provider = TelemetryProvider(config)

        result = provider.initialize()
        assert result is False

    def test_span_context_disabled(self):
        """Test span context when tracing is disabled."""
        config = TelemetryConfig(enabled=False)
        provider = TelemetryProvider(config)

        with provider.span("test-span") as span:
            assert span is None

    def test_record_sync_disabled(self):
        """Test record_sync when disabled (should not crash)."""
        config = TelemetryConfig(enabled=False)
        provider = TelemetryProvider(config)

        # Should not raise
        provider.record_sync(
            success=True,
            duration_seconds=1.5,
            stories_count=5,
            epic_key="TEST-100",
        )

    def test_record_api_call_disabled(self):
        """Test record_api_call when disabled (should not crash)."""
        config = TelemetryConfig(enabled=False)
        provider = TelemetryProvider(config)

        # Should not raise
        provider.record_api_call(
            operation="get_issue",
            success=True,
            duration_ms=150.5,
            endpoint="/rest/api/3/issue/TEST-123",
        )

    def test_record_error_disabled(self):
        """Test record_error when disabled (should not crash)."""
        config = TelemetryConfig(enabled=False)
        provider = TelemetryProvider(config)

        # Should not raise
        provider.record_error(
            error_type="AuthenticationError",
            operation="create_subtask",
        )

    def test_shutdown_not_initialized(self):
        """Test shutdown when not initialized (should not crash)."""
        config = TelemetryConfig(enabled=False)
        provider = TelemetryProvider(config)

        # Should not raise
        provider.shutdown()


# =============================================================================
# Decorator Tests
# =============================================================================


class TestTracedDecorator:
    """Tests for @traced decorator."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset the singleton instance before each test."""
        TelemetryProvider._instance = None
        yield
        TelemetryProvider._instance = None

    def test_traced_function_executes(self):
        """Test traced decorator allows function execution."""

        @traced("test.operation")
        def my_function(x: int, y: int) -> int:
            return x + y

        result = my_function(2, 3)
        assert result == 5

    def test_traced_preserves_function_metadata(self):
        """Test traced preserves function name and docstring."""

        @traced()
        def documented_function():
            """This is the docstring."""

        assert documented_function.__name__ == "documented_function"
        assert "docstring" in documented_function.__doc__

    def test_traced_with_custom_name(self):
        """Test traced with custom span name."""

        @traced("custom.span.name")
        def my_function():
            return 42

        result = my_function()
        assert result == 42

    def test_traced_with_attributes(self):
        """Test traced with span attributes."""

        @traced("test.op", attributes={"component": "test"})
        def my_function():
            return "done"

        result = my_function()
        assert result == "done"

    def test_traced_propagates_exception(self):
        """Test traced propagates exceptions."""

        @traced()
        def failing_function():
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            failing_function()


class TestTimedApiCallDecorator:
    """Tests for @timed_api_call decorator."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset the singleton instance before each test."""
        TelemetryProvider._instance = None
        yield
        TelemetryProvider._instance = None

    def test_timed_api_call_executes(self):
        """Test timed_api_call decorator allows function execution."""

        @timed_api_call("get_issue")
        def get_issue(key: str) -> dict:
            return {"key": key}

        result = get_issue("TEST-123")
        assert result == {"key": "TEST-123"}

    def test_timed_api_call_preserves_metadata(self):
        """Test timed_api_call preserves function metadata."""

        @timed_api_call("create")
        def create_thing():
            """Create a thing."""

        assert create_thing.__name__ == "create_thing"

    def test_timed_api_call_propagates_exception(self):
        """Test timed_api_call propagates exceptions."""

        @timed_api_call("failing_call")
        def failing_call():
            raise ConnectionError("Network error")

        with pytest.raises(ConnectionError, match="Network error"):
            failing_call()


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestHelperFunctions:
    """Tests for helper functions."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset the singleton instance before each test."""
        TelemetryProvider._instance = None
        yield
        TelemetryProvider._instance = None

    def test_get_telemetry_returns_provider(self):
        """Test get_telemetry returns a provider instance."""
        provider = get_telemetry()

        assert isinstance(provider, TelemetryProvider)

    def test_configure_telemetry_disabled(self):
        """Test configure_telemetry with disabled config."""
        provider = configure_telemetry(enabled=False)

        assert isinstance(provider, TelemetryProvider)
        assert provider.config.enabled is False

    def test_configure_telemetry_with_endpoint(self):
        """Test configure_telemetry with endpoint."""
        provider = configure_telemetry(
            enabled=True,
            endpoint="http://localhost:4317",
            service_name="test-service",
        )

        assert provider.config.enabled is True
        assert provider.config.otlp_endpoint == "http://localhost:4317"
        assert provider.config.service_name == "test-service"

    def test_configure_telemetry_console_export(self):
        """Test configure_telemetry with console export."""
        provider = configure_telemetry(
            enabled=True,
            console_export=True,
        )

        assert provider.config.console_export is True


# =============================================================================
# CLI Integration Tests
# =============================================================================


class TestCLIIntegration:
    """Tests for CLI integration."""

    def test_otel_flags_in_parser(self, cli_parser):
        """Test --otel-* flags are recognized."""
        args = cli_parser.parse_args(
            [
                "--otel-enable",
                "--otel-endpoint",
                "http://localhost:4317",
                "--otel-service-name",
                "test",
                "--otel-console",
                "--input",
                "epic.md",
                "--epic",
                "TEST-123",
            ]
        )

        assert args.otel_enable is True
        assert args.otel_endpoint == "http://localhost:4317"
        assert args.otel_service_name == "test"
        assert args.otel_console is True

    def test_otel_default_service_name(self, cli_parser):
        """Test default service name."""
        args = cli_parser.parse_args(
            [
                "--input",
                "epic.md",
                "--epic",
                "TEST-123",
            ]
        )

        assert args.otel_service_name == "spectra"

    def test_otel_disabled_by_default(self, cli_parser):
        """Test otel is disabled by default."""
        args = cli_parser.parse_args(
            [
                "--input",
                "epic.md",
                "--epic",
                "TEST-123",
            ]
        )

        assert args.otel_enable is False


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset the singleton instance before each test."""
        TelemetryProvider._instance = None
        yield
        TelemetryProvider._instance = None

    def test_double_initialization(self):
        """Test calling initialize twice."""
        config = TelemetryConfig(enabled=False)
        provider = TelemetryProvider(config)

        result1 = provider.initialize()
        result2 = provider.initialize()

        # Both should return False (disabled)
        assert result1 is False
        assert result2 is False

    def test_shutdown_twice(self):
        """Test calling shutdown twice."""
        config = TelemetryConfig(enabled=False)
        provider = TelemetryProvider(config)

        # Should not raise
        provider.shutdown()
        provider.shutdown()

    def test_tracer_property_when_disabled(self):
        """Test tracer property returns None when disabled."""
        config = TelemetryConfig(enabled=False)
        provider = TelemetryProvider(config)

        assert provider.tracer is None

    def test_meter_property_when_disabled(self):
        """Test meter property returns None when disabled."""
        config = TelemetryConfig(enabled=False)
        provider = TelemetryProvider(config)

        assert provider.meter is None

    def test_span_exception_handling(self):
        """Test span context handles exceptions properly."""
        config = TelemetryConfig(enabled=False)
        provider = TelemetryProvider(config)

        with pytest.raises(RuntimeError, match="Test error"), provider.span("test"):
            raise RuntimeError("Test error")

    def test_record_metrics_with_missing_epic(self):
        """Test record_sync with no epic key."""
        config = TelemetryConfig(enabled=False)
        provider = TelemetryProvider(config)

        # Should not raise
        provider.record_sync(
            success=True,
            duration_seconds=1.0,
            stories_count=3,
            epic_key=None,
        )

    def test_record_api_call_without_endpoint(self):
        """Test record_api_call without endpoint."""
        config = TelemetryConfig(enabled=False)
        provider = TelemetryProvider(config)

        # Should not raise
        provider.record_api_call(
            operation="test",
            success=True,
            duration_ms=100,
            endpoint=None,
        )


# =============================================================================
# Mock OpenTelemetry Tests (when OTel is available)
# =============================================================================


@pytest.mark.skipif(not OTEL_AVAILABLE, reason="OpenTelemetry not installed")
class TestWithOpenTelemetry:
    """Tests that require OpenTelemetry to be installed."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset the singleton instance before each test."""
        TelemetryProvider._instance = None
        yield
        TelemetryProvider._instance = None

    def test_initialize_with_console_export(self):
        """Test initialization with console export."""
        config = TelemetryConfig(
            enabled=True,
            console_export=True,
        )
        provider = TelemetryProvider(config)

        result = provider.initialize()
        assert result is True
        assert provider.tracer is not None

        provider.shutdown()

    def test_span_creation(self):
        """Test span creation with OTel."""
        config = TelemetryConfig(
            enabled=True,
            console_export=True,
        )
        provider = TelemetryProvider(config)
        provider.initialize()

        try:
            with provider.span("test.span", attributes={"key": "value"}) as span:
                assert span is not None
        finally:
            provider.shutdown()


# =============================================================================
# Prometheus Tests
# =============================================================================


class TestPrometheusConfig:
    """Tests for Prometheus configuration."""

    def test_prometheus_default_values(self):
        """Test TelemetryConfig has Prometheus defaults."""
        config = TelemetryConfig()

        assert config.prometheus_enabled is False
        assert config.prometheus_port == 9090
        assert config.prometheus_host == "0.0.0.0"

    def test_prometheus_custom_values(self):
        """Test TelemetryConfig with custom Prometheus values."""
        config = TelemetryConfig(
            prometheus_enabled=True,
            prometheus_port=8080,
            prometheus_host="127.0.0.1",
        )

        assert config.prometheus_enabled is True
        assert config.prometheus_port == 8080
        assert config.prometheus_host == "127.0.0.1"

    def test_from_env_prometheus(self):
        """Test from_env with Prometheus env vars."""
        env = {
            "PROMETHEUS_ENABLED": "true",
            "PROMETHEUS_PORT": "8080",
            "PROMETHEUS_HOST": "localhost",
        }
        with patch.dict("os.environ", env, clear=True):
            config = TelemetryConfig.from_env()

        assert config.prometheus_enabled is True
        assert config.prometheus_port == 8080
        assert config.prometheus_host == "localhost"


class TestPrometheusProvider:
    """Tests for Prometheus provider methods."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset the singleton instance before each test."""
        TelemetryProvider._instance = None
        yield
        TelemetryProvider._instance = None

    def test_initialize_prometheus_disabled(self):
        """Test initialize_prometheus when disabled."""
        config = TelemetryConfig(prometheus_enabled=False)
        provider = TelemetryProvider(config)

        result = provider.initialize_prometheus()
        assert result is False

    def test_initialize_prometheus_not_available(self):
        """Test initialize_prometheus when library not installed."""
        config = TelemetryConfig(prometheus_enabled=True)
        provider = TelemetryProvider(config)

        if not PROMETHEUS_AVAILABLE:
            result = provider.initialize_prometheus()
            assert result is False

    def test_sync_in_progress_context(self):
        """Test sync_in_progress context manager."""
        config = TelemetryConfig(prometheus_enabled=False)
        provider = TelemetryProvider(config)

        # Should not raise even without Prometheus
        with provider.sync_in_progress():
            pass

    def test_record_sync_with_prometheus_disabled(self):
        """Test record_sync when Prometheus is disabled."""
        config = TelemetryConfig(prometheus_enabled=False)
        provider = TelemetryProvider(config)

        # Should not raise
        provider.record_sync(
            success=True,
            duration_seconds=1.5,
            stories_count=5,
            epic_key="TEST-100",
        )

    def test_record_api_call_with_prometheus_disabled(self):
        """Test record_api_call when Prometheus is disabled."""
        config = TelemetryConfig(prometheus_enabled=False)
        provider = TelemetryProvider(config)

        # Should not raise
        provider.record_api_call(
            operation="get_issue",
            success=True,
            duration_ms=150,
        )

    def test_record_error_with_prometheus_disabled(self):
        """Test record_error when Prometheus is disabled."""
        config = TelemetryConfig(prometheus_enabled=False)
        provider = TelemetryProvider(config)

        # Should not raise
        provider.record_error(
            error_type="AuthError",
            operation="create_subtask",
        )


class TestPrometheusHelperFunctions:
    """Tests for Prometheus helper functions."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset the singleton instance before each test."""
        TelemetryProvider._instance = None
        yield
        TelemetryProvider._instance = None

    def test_configure_prometheus_disabled(self):
        """Test configure_prometheus when disabled."""
        provider = configure_prometheus(enabled=False)

        assert isinstance(provider, TelemetryProvider)
        assert provider.config.prometheus_enabled is False

    def test_configure_prometheus_with_port(self):
        """Test configure_prometheus with custom port."""
        provider = configure_prometheus(
            enabled=False,  # Don't actually start server
            port=8080,
            host="127.0.0.1",
            service_name="test-service",
        )

        assert provider.config.prometheus_port == 8080
        assert provider.config.prometheus_host == "127.0.0.1"
        assert provider.config.service_name == "test-service"

    def test_get_prometheus_metrics_not_available(self):
        """Test get_prometheus_metrics when not installed."""
        if not PROMETHEUS_AVAILABLE:
            result = get_prometheus_metrics()
            assert result is None


class TestPrometheusCLIIntegration:
    """Tests for Prometheus CLI integration."""

    def test_prometheus_flags_in_parser(self, cli_parser):
        """Test --prometheus-* flags are recognized."""
        args = cli_parser.parse_args(
            [
                "--prometheus",
                "--prometheus-port",
                "8080",
                "--prometheus-host",
                "127.0.0.1",
                "--input",
                "epic.md",
                "--epic",
                "TEST-123",
            ]
        )

        assert args.prometheus is True
        assert args.prometheus_port == 8080
        assert args.prometheus_host == "127.0.0.1"

    def test_prometheus_default_port(self, cli_parser):
        """Test default Prometheus port."""
        args = cli_parser.parse_args(
            [
                "--prometheus",
                "--input",
                "epic.md",
                "--epic",
                "TEST-123",
            ]
        )

        assert args.prometheus_port == 9090

    def test_prometheus_default_host(self, cli_parser):
        """Test default Prometheus host."""
        args = cli_parser.parse_args(
            [
                "--prometheus",
                "--input",
                "epic.md",
                "--epic",
                "TEST-123",
            ]
        )

        assert args.prometheus_host == "0.0.0.0"

    def test_prometheus_disabled_by_default(self, cli_parser):
        """Test Prometheus is disabled by default."""
        args = cli_parser.parse_args(
            [
                "--input",
                "epic.md",
                "--epic",
                "TEST-123",
            ]
        )

        assert args.prometheus is False


@pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="prometheus_client not installed")
class TestWithPrometheus:
    """Tests that require prometheus_client to be installed."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset the singleton instance before each test."""
        TelemetryProvider._instance = None
        yield
        TelemetryProvider._instance = None

    def test_get_prometheus_metrics(self):
        """Test get_prometheus_metrics returns bytes."""
        result = get_prometheus_metrics()

        assert isinstance(result, bytes)
        # Should contain some metric content
        assert b"# " in result or len(result) > 0
