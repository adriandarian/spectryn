"""
OpenTelemetry Support - Tracing and metrics for spectra.

Provides optional OpenTelemetry instrumentation for:
- Distributed tracing of sync operations
- Metrics collection (counters, histograms)
- Export to OTLP endpoints (Jaeger, Zipkin, etc.) or Prometheus

Usage:
    # Enable via CLI
    spectra --otel-enable --otel-endpoint http://localhost:4317 ...

    # Or via environment variables
    OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317 spectra --otel-enable ...
"""

from __future__ import annotations

import functools
import logging
import os
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, TypeVar, cast


# Type variable for generic decorators
F = TypeVar("F", bound=Callable[..., Any])

logger = logging.getLogger(__name__)

# Track whether OpenTelemetry is available
OTEL_AVAILABLE = False

try:
    from opentelemetry import metrics, trace
    from opentelemetry.metrics import Counter, Histogram, Meter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import (
        ConsoleMetricExporter,
        MetricExporter,
        PeriodicExportingMetricReader,
    )
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
        ConsoleSpanExporter,
        SpanExporter,
    )
    from opentelemetry.trace import Span, Status, StatusCode

    OTEL_AVAILABLE = True
except ImportError:
    # OpenTelemetry not installed - provide stubs
    pass


# Track whether Prometheus exporter is available
PROMETHEUS_AVAILABLE = False

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        generate_latest,
    )
    from prometheus_client import (
        REGISTRY as PROM_REGISTRY,
    )
    from prometheus_client import (
        Counter as PromCounter,
    )
    from prometheus_client import (
        Gauge as PromGauge,
    )
    from prometheus_client import (
        Histogram as PromHistogram,
    )
    from prometheus_client import (
        start_http_server as prom_start_http_server,
    )

    PROMETHEUS_AVAILABLE = True
except ImportError:
    pass


@dataclass
class TelemetryConfig:
    """Configuration for OpenTelemetry instrumentation."""

    enabled: bool = False
    service_name: str = "spectra"
    service_version: str = "2.0.0"

    # OTLP exporter settings
    otlp_endpoint: str | None = None
    otlp_insecure: bool = True
    otlp_headers: dict[str, str] = field(default_factory=dict)

    # Console exporter (for debugging)
    console_export: bool = False

    # Metrics settings
    metrics_enabled: bool = True
    metrics_port: int = 9464  # Prometheus metrics port

    # Prometheus HTTP server settings
    prometheus_enabled: bool = False
    prometheus_port: int = 9090
    prometheus_host: str = "0.0.0.0"

    @classmethod
    def from_env(cls) -> TelemetryConfig:
        """Create config from environment variables."""
        return cls(
            enabled=os.getenv("OTEL_ENABLED", "").lower() in ("true", "1", "yes"),
            service_name=os.getenv("OTEL_SERVICE_NAME", "spectra"),
            otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
            otlp_insecure=os.getenv("OTEL_EXPORTER_OTLP_INSECURE", "true").lower() in ("true", "1"),
            console_export=os.getenv("OTEL_CONSOLE_EXPORT", "").lower() in ("true", "1"),
            metrics_enabled=os.getenv("OTEL_METRICS_ENABLED", "true").lower() in ("true", "1"),
            prometheus_enabled=os.getenv("PROMETHEUS_ENABLED", "").lower() in ("true", "1", "yes"),
            prometheus_port=int(os.getenv("PROMETHEUS_PORT", "9090")),
            prometheus_host=os.getenv("PROMETHEUS_HOST", "0.0.0.0"),
        )


class TelemetryProvider:
    """
    Manages OpenTelemetry tracing and metrics.

    Provides a unified interface for instrumentation that gracefully
    degrades when OpenTelemetry is not installed.
    """

    _instance: TelemetryProvider | None = None

    def __init__(self, config: TelemetryConfig):
        """
        Initialize the telemetry provider.

        Args:
            config: Telemetry configuration.
        """
        self.config = config
        self._tracer: Any | None = None
        self._meter: Any | None = None
        self._initialized = False
        self._prometheus_initialized = False

        # OpenTelemetry Metrics
        self._sync_counter: Any | None = None
        self._sync_duration: Any | None = None
        self._stories_counter: Any | None = None
        self._api_calls_counter: Any | None = None
        self._api_duration: Any | None = None
        self._errors_counter: Any | None = None

        # Prometheus Metrics (direct prometheus_client)
        self._prom_sync_counter: Any | None = None
        self._prom_sync_duration: Any | None = None
        self._prom_stories_counter: Any | None = None
        self._prom_api_calls_counter: Any | None = None
        self._prom_api_duration: Any | None = None
        self._prom_errors_counter: Any | None = None
        self._prom_active_syncs: Any | None = None

    @classmethod
    def get_instance(cls) -> TelemetryProvider:
        """Get the singleton telemetry provider."""
        if cls._instance is None:
            config = TelemetryConfig.from_env()
            cls._instance = cls(config)
        return cls._instance

    @classmethod
    def configure(cls, config: TelemetryConfig) -> TelemetryProvider:
        """
        Configure the telemetry provider.

        Args:
            config: Telemetry configuration.

        Returns:
            The configured provider instance.
        """
        cls._instance = cls(config)
        if config.enabled:
            cls._instance.initialize()
        return cls._instance

    def initialize(self) -> bool:
        """
        Initialize OpenTelemetry providers and exporters.

        Returns:
            True if initialization succeeded, False otherwise.
        """
        if self._initialized:
            return True

        if not OTEL_AVAILABLE:
            logger.warning(
                "OpenTelemetry not available. Install with: pip install spectra[telemetry]"
            )
            return False

        if not self.config.enabled:
            logger.debug("Telemetry disabled by configuration")
            return False

        try:
            self._setup_tracing()
            if self.config.metrics_enabled:
                self._setup_metrics()
            self._initialized = True
            logger.info(
                f"OpenTelemetry initialized: service={self.config.service_name}, "
                f"endpoint={self.config.otlp_endpoint or 'console'}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to initialize OpenTelemetry: {e}")
            return False

    def initialize_prometheus(self) -> bool:
        """
        Initialize Prometheus metrics server.

        Starts an HTTP server that exposes metrics in Prometheus format.

        Returns:
            True if initialization succeeded, False otherwise.
        """
        if self._prometheus_initialized:
            return True

        if not PROMETHEUS_AVAILABLE:
            logger.warning(
                "prometheus_client not available. Install with: pip install prometheus_client"
            )
            return False

        if not self.config.prometheus_enabled:
            logger.debug("Prometheus disabled by configuration")
            return False

        try:
            self._setup_prometheus_metrics()
            self._start_prometheus_server()
            self._prometheus_initialized = True
            logger.info(
                f"Prometheus metrics server started on "
                f"http://{self.config.prometheus_host}:{self.config.prometheus_port}/metrics"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Prometheus: {e}")
            return False

    def _setup_prometheus_metrics(self) -> None:
        """Set up Prometheus metrics collectors."""
        # Sync operations
        self._prom_sync_counter = PromCounter(
            "spectra_sync_total",
            "Total number of sync operations",
            ["epic_key", "success"],
        )

        self._prom_sync_duration = PromHistogram(
            "spectra_sync_duration_seconds",
            "Duration of sync operations in seconds",
            ["epic_key"],
            buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
        )

        # Story metrics
        self._prom_stories_counter = PromCounter(
            "spectra_stories_processed_total",
            "Total number of stories processed",
            ["epic_key", "operation"],
        )

        # API calls
        self._prom_api_calls_counter = PromCounter(
            "spectra_api_calls_total",
            "Total number of API calls",
            ["operation", "success"],
        )

        self._prom_api_duration = PromHistogram(
            "spectra_api_duration_milliseconds",
            "Duration of API calls in milliseconds",
            ["operation"],
            buckets=(10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000),
        )

        # Errors
        self._prom_errors_counter = PromCounter(
            "spectra_errors_total",
            "Total number of errors",
            ["error_type", "operation"],
        )

        # Active syncs gauge
        self._prom_active_syncs = PromGauge(
            "spectra_active_syncs",
            "Number of currently active sync operations",
        )

        # Info metric
        PromGauge(
            "spectra_info",
            "spectra version and service information",
            ["version", "service_name"],
        ).labels(
            version=self.config.service_version,
            service_name=self.config.service_name,
        ).set(1)

    def _start_prometheus_server(self) -> None:
        """Start the Prometheus HTTP server."""
        prom_start_http_server(
            port=self.config.prometheus_port,
            addr=self.config.prometheus_host,
        )

    def _setup_tracing(self) -> None:
        """Set up the tracer provider and exporters."""
        resource = Resource.create(
            {
                SERVICE_NAME: self.config.service_name,
                "service.version": self.config.service_version,
            }
        )

        provider = TracerProvider(resource=resource)

        # Add exporters
        if self.config.otlp_endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                    OTLPSpanExporter,
                )

                exporter = OTLPSpanExporter(
                    endpoint=self.config.otlp_endpoint,
                    insecure=self.config.otlp_insecure,
                )
                provider.add_span_processor(BatchSpanProcessor(exporter))
                logger.debug(f"OTLP trace exporter configured: {self.config.otlp_endpoint}")
            except ImportError:
                logger.warning("OTLP exporter not available, falling back to console")
                self.config.console_export = True

        if self.config.console_export:
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

        trace.set_tracer_provider(provider)
        self._tracer = trace.get_tracer(self.config.service_name, self.config.service_version)

    def _setup_metrics(self) -> None:
        """Set up the meter provider and exporters."""
        resource = Resource.create(
            {
                SERVICE_NAME: self.config.service_name,
                "service.version": self.config.service_version,
            }
        )

        readers = []

        if self.config.otlp_endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
                    OTLPMetricExporter,
                )

                exporter = OTLPMetricExporter(
                    endpoint=self.config.otlp_endpoint,
                    insecure=self.config.otlp_insecure,
                )
                readers.append(PeriodicExportingMetricReader(exporter))
                logger.debug(f"OTLP metric exporter configured: {self.config.otlp_endpoint}")
            except ImportError:
                logger.warning("OTLP metric exporter not available")

        if self.config.console_export:
            readers.append(PeriodicExportingMetricReader(ConsoleMetricExporter()))

        if readers:
            provider = MeterProvider(resource=resource, metric_readers=readers)
            metrics.set_meter_provider(provider)
            self._meter = metrics.get_meter(self.config.service_name, self.config.service_version)
            self._create_metrics()

    def _create_metrics(self) -> None:
        """Create standard metrics."""
        if not self._meter:
            return

        # Sync operations
        self._sync_counter = self._meter.create_counter(
            name="spectra.sync.total",
            description="Total number of sync operations",
            unit="1",
        )

        self._sync_duration = self._meter.create_histogram(
            name="spectra.sync.duration",
            description="Duration of sync operations",
            unit="s",
        )

        # Story metrics
        self._stories_counter = self._meter.create_counter(
            name="spectra.stories.processed",
            description="Number of stories processed",
            unit="1",
        )

        # API calls
        self._api_calls_counter = self._meter.create_counter(
            name="spectra.api.calls",
            description="Number of API calls made",
            unit="1",
        )

        self._api_duration = self._meter.create_histogram(
            name="spectra.api.duration",
            description="Duration of API calls",
            unit="ms",
        )

        # Errors
        self._errors_counter = self._meter.create_counter(
            name="spectra.errors.total",
            description="Total number of errors",
            unit="1",
        )

    @property
    def tracer(self) -> Any:
        """Get the tracer instance."""
        return self._tracer

    @property
    def meter(self) -> Any:
        """Get the meter instance."""
        return self._meter

    @contextmanager
    def span(
        self,
        name: str,
        attributes: dict[str, Any] | None = None,
        record_exception: bool = True,
    ) -> Generator[Any | None, None, None]:
        """
        Create a tracing span context manager.

        Args:
            name: Span name.
            attributes: Optional span attributes.
            record_exception: Whether to record exceptions.

        Yields:
            The span object (or None if tracing is disabled).
        """
        if not self._tracer:
            yield None
            return

        with self._tracer.start_as_current_span(name, attributes=attributes) as span:
            try:
                yield span
            except Exception as e:
                if record_exception and span:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                raise

    def record_sync(
        self,
        success: bool,
        duration_seconds: float,
        stories_count: int = 0,
        epic_key: str | None = None,
    ) -> None:
        """
        Record sync operation metrics.

        Args:
            success: Whether the sync was successful.
            duration_seconds: Duration of the sync.
            stories_count: Number of stories processed.
            epic_key: Optional epic key.
        """
        epic = epic_key or "unknown"
        success_str = str(success).lower()

        # OpenTelemetry metrics
        attributes = {
            "success": success_str,
            "epic_key": epic,
        }

        if self._sync_counter:
            self._sync_counter.add(1, attributes)

        if self._sync_duration:
            self._sync_duration.record(duration_seconds, attributes)

        if self._stories_counter and stories_count > 0:
            self._stories_counter.add(stories_count, attributes)

        # Prometheus metrics
        if self._prom_sync_counter:
            self._prom_sync_counter.labels(epic_key=epic, success=success_str).inc()

        if self._prom_sync_duration:
            self._prom_sync_duration.labels(epic_key=epic).observe(duration_seconds)

        if self._prom_stories_counter and stories_count > 0:
            self._prom_stories_counter.labels(epic_key=epic, operation="sync").inc(stories_count)

    def record_api_call(
        self,
        operation: str,
        success: bool,
        duration_ms: float,
        endpoint: str | None = None,
    ) -> None:
        """
        Record API call metrics.

        Args:
            operation: Operation name (e.g., "get_issue", "create_subtask").
            success: Whether the call succeeded.
            duration_ms: Duration in milliseconds.
            endpoint: Optional API endpoint.
        """
        success_str = str(success).lower()

        # OpenTelemetry metrics
        attributes = {
            "operation": operation,
            "success": success_str,
        }
        if endpoint:
            attributes["endpoint"] = endpoint

        if self._api_calls_counter:
            self._api_calls_counter.add(1, attributes)

        if self._api_duration:
            self._api_duration.record(duration_ms, attributes)

        # Prometheus metrics
        if self._prom_api_calls_counter:
            self._prom_api_calls_counter.labels(operation=operation, success=success_str).inc()

        if self._prom_api_duration:
            self._prom_api_duration.labels(operation=operation).observe(duration_ms)

    def record_error(
        self,
        error_type: str,
        operation: str | None = None,
    ) -> None:
        """
        Record an error.

        Args:
            error_type: Type of error.
            operation: Optional operation that caused the error.
        """
        op = operation or "unknown"

        # OpenTelemetry metrics
        attributes = {
            "error_type": error_type,
        }
        if operation:
            attributes["operation"] = operation

        if self._errors_counter:
            self._errors_counter.add(1, attributes)

        # Prometheus metrics
        if self._prom_errors_counter:
            self._prom_errors_counter.labels(error_type=error_type, operation=op).inc()

    @contextmanager
    def sync_in_progress(self) -> Generator[None, None, None]:
        """
        Context manager to track active sync operations.

        Updates the active_syncs gauge while sync is running.

        Yields:
            None
        """
        if self._prom_active_syncs:
            self._prom_active_syncs.inc()
        try:
            yield
        finally:
            if self._prom_active_syncs:
                self._prom_active_syncs.dec()

    def shutdown(self) -> None:
        """Shutdown the telemetry provider."""
        if not self._initialized:
            return

        try:
            if OTEL_AVAILABLE:
                # Flush traces
                provider = trace.get_tracer_provider()
                if hasattr(provider, "force_flush"):
                    provider.force_flush()
                if hasattr(provider, "shutdown"):
                    provider.shutdown()

                # Flush metrics
                meter_provider = metrics.get_meter_provider()
                if hasattr(meter_provider, "force_flush"):
                    meter_provider.force_flush()
                if hasattr(meter_provider, "shutdown"):
                    meter_provider.shutdown()

            logger.debug("OpenTelemetry shutdown complete")
        except Exception as e:
            logger.warning(f"Error during telemetry shutdown: {e}")


def traced(
    name: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> Callable[[F], F]:
    """
    Decorator to trace a function.

    Args:
        name: Span name (defaults to function name).
        attributes: Optional span attributes.

    Returns:
        Decorated function.

    Example:
        @traced("sync.process_story")
        def process_story(story_id: str) -> None:
            ...
    """

    def decorator(func: F) -> F:
        span_name = name or f"{func.__module__}.{func.__qualname__}"

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            provider = TelemetryProvider.get_instance()

            with provider.span(span_name, attributes=attributes):
                return func(*args, **kwargs)

        return wrapper  # type: ignore

    return decorator


def timed_api_call(operation: str) -> Callable[[F], F]:
    """
    Decorator to time and record API calls.

    Args:
        operation: Operation name for metrics.

    Returns:
        Decorated function.

    Example:
        @timed_api_call("get_issue")
        def get_issue(self, key: str) -> IssueData:
            ...
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            provider = TelemetryProvider.get_instance()
            start = time.perf_counter()
            success = True

            try:
                return func(*args, **kwargs)
            except Exception:
                success = False
                raise
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                provider.record_api_call(
                    operation=operation,
                    success=success,
                    duration_ms=duration_ms,
                )

        return wrapper  # type: ignore

    return decorator


# Convenience function to get the global provider
def get_telemetry() -> TelemetryProvider:
    """Get the global telemetry provider instance."""
    return TelemetryProvider.get_instance()


def configure_telemetry(
    enabled: bool = False,
    endpoint: str | None = None,
    service_name: str = "spectra",
    console_export: bool = False,
) -> TelemetryProvider:
    """
    Configure telemetry with the given settings.

    Args:
        enabled: Whether telemetry is enabled.
        endpoint: OTLP endpoint URL.
        service_name: Service name for traces/metrics.
        console_export: Whether to export to console (for debugging).

    Returns:
        The configured telemetry provider.
    """
    config = TelemetryConfig(
        enabled=enabled,
        service_name=service_name,
        otlp_endpoint=endpoint,
        console_export=console_export,
    )
    return TelemetryProvider.configure(config)


def configure_prometheus(
    enabled: bool = False,
    port: int = 9090,
    host: str = "0.0.0.0",
    service_name: str = "spectra",
) -> TelemetryProvider:
    """
    Configure and start Prometheus metrics server.

    Args:
        enabled: Whether Prometheus is enabled.
        port: Port to expose metrics on.
        host: Host address to bind to.
        service_name: Service name for metrics.

    Returns:
        The configured telemetry provider.
    """
    config = TelemetryConfig(
        prometheus_enabled=enabled,
        prometheus_port=port,
        prometheus_host=host,
        service_name=service_name,
    )
    provider = TelemetryProvider.configure(config)
    if enabled:
        provider.initialize_prometheus()
    return provider


def get_prometheus_metrics() -> bytes | None:
    """
    Get Prometheus metrics in text format.

    This can be used to expose metrics via a custom HTTP endpoint
    if you don't want to use the built-in server.

    Returns:
        Metrics in Prometheus text format, or None if not available.
    """
    if not PROMETHEUS_AVAILABLE:
        return None

    return cast(bytes, generate_latest(PROM_REGISTRY))
