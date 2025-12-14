"""
Health Check Endpoint - For containerized deployments.

Provides an HTTP server with health check endpoints for:
- Kubernetes liveness/readiness probes
- Docker HEALTHCHECK
- Load balancer health checks

Endpoints:
- /health  - Overall health status
- /live    - Liveness probe (is the process running?)
- /ready   - Readiness probe (can it accept traffic?)
- /metrics - Basic metrics (if Prometheus not enabled)

Usage:
    # Enable via CLI
    md2jira --health --health-port 8080 --markdown EPIC.md --epic PROJ-123
    
    # Check health
    curl http://localhost:8080/health
"""

from __future__ import annotations

import json
import logging
import socket
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class HealthStatus:
    """Health check status."""
    
    healthy: bool = True
    ready: bool = True
    
    # Component statuses
    components: dict[str, bool] = field(default_factory=dict)
    
    # Metadata
    version: str = "2.0.0"
    service_name: str = "md2jira"
    uptime_seconds: float = 0.0
    
    # Last check times
    last_check: Optional[str] = None
    last_sync: Optional[str] = None
    
    # Sync stats
    syncs_total: int = 0
    syncs_successful: int = 0
    syncs_failed: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "status": "healthy" if self.healthy else "unhealthy",
            "ready": self.ready,
            "version": self.version,
            "service": self.service_name,
            "uptime_seconds": round(self.uptime_seconds, 2),
            "last_check": self.last_check,
            "components": {
                name: "up" if status else "down"
                for name, status in self.components.items()
            },
            "stats": {
                "syncs_total": self.syncs_total,
                "syncs_successful": self.syncs_successful,
                "syncs_failed": self.syncs_failed,
                "last_sync": self.last_sync,
            },
        }


@dataclass
class HealthConfig:
    """Configuration for health check server."""
    
    enabled: bool = False
    port: int = 8080
    host: str = "0.0.0.0"
    
    # Check settings
    check_tracker: bool = True
    check_interval_seconds: float = 30.0
    
    # Timeouts
    tracker_timeout_seconds: float = 5.0


class HealthCheckHandler(BaseHTTPRequestHandler):
    """HTTP request handler for health check endpoints."""
    
    # Reference to the health server (set by HealthServer)
    health_server: Optional["HealthServer"] = None
    
    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default logging to stderr."""
        logger.debug(f"Health check: {format % args}")
    
    def _send_json_response(self, status_code: int, data: dict) -> None:
        """Send a JSON response."""
        body = json.dumps(data, indent=2).encode("utf-8")
        
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(body)
    
    def do_GET(self) -> None:
        """Handle GET requests."""
        if self.health_server is None:
            self._send_json_response(500, {"error": "Server not configured"})
            return
        
        path = self.path.split("?")[0]  # Remove query string
        
        if path == "/health":
            self._handle_health()
        elif path == "/live" or path == "/liveness":
            self._handle_liveness()
        elif path == "/ready" or path == "/readiness":
            self._handle_readiness()
        elif path == "/metrics":
            self._handle_metrics()
        elif path == "/":
            self._handle_root()
        else:
            self._send_json_response(404, {"error": "Not found"})
    
    def _handle_root(self) -> None:
        """Handle root path - show available endpoints."""
        data = {
            "service": "md2jira",
            "endpoints": {
                "/health": "Overall health status",
                "/live": "Liveness probe",
                "/ready": "Readiness probe",
                "/metrics": "Basic metrics",
            },
        }
        self._send_json_response(200, data)
    
    def _handle_health(self) -> None:
        """Handle /health endpoint."""
        status = self.health_server.get_status()
        code = 200 if status.healthy else 503
        self._send_json_response(code, status.to_dict())
    
    def _handle_liveness(self) -> None:
        """Handle /live endpoint - is the process alive?"""
        # Liveness just checks if the server is responding
        self._send_json_response(200, {
            "status": "alive",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    
    def _handle_readiness(self) -> None:
        """Handle /ready endpoint - can it accept traffic?"""
        status = self.health_server.get_status()
        
        if status.ready:
            self._send_json_response(200, {
                "status": "ready",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        else:
            self._send_json_response(503, {
                "status": "not_ready",
                "reason": "Service is not ready to accept traffic",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
    
    def _handle_metrics(self) -> None:
        """Handle /metrics endpoint - basic metrics."""
        status = self.health_server.get_status()
        
        data = {
            "uptime_seconds": status.uptime_seconds,
            "syncs": {
                "total": status.syncs_total,
                "successful": status.syncs_successful,
                "failed": status.syncs_failed,
            },
            "components": status.components,
        }
        self._send_json_response(200, data)


class HealthServer:
    """
    HTTP server for health check endpoints.
    
    Runs in a background thread and provides health status
    for containerized deployments.
    """
    
    _instance: Optional["HealthServer"] = None
    
    def __init__(self, config: HealthConfig):
        """
        Initialize the health server.
        
        Args:
            config: Health check configuration.
        """
        self.config = config
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._start_time = time.time()
        
        # Status tracking
        self._status = HealthStatus(
            service_name="md2jira",
            version="2.0.0",
        )
        self._status_lock = threading.Lock()
        
        # Tracker check callback
        self._tracker_check: Optional[Callable[[], bool]] = None
        
        # Background health checker
        self._checker_thread: Optional[threading.Thread] = None
    
    @classmethod
    def get_instance(cls) -> Optional["HealthServer"]:
        """Get the singleton health server instance."""
        return cls._instance
    
    @classmethod
    def configure(cls, config: HealthConfig) -> "HealthServer":
        """
        Configure the health server.
        
        Args:
            config: Health check configuration.
            
        Returns:
            The configured server instance.
        """
        cls._instance = cls(config)
        return cls._instance
    
    def start(self) -> bool:
        """
        Start the health check server.
        
        Returns:
            True if started successfully, False otherwise.
        """
        if self._running:
            return True
        
        if not self.config.enabled:
            logger.debug("Health check server disabled")
            return False
        
        try:
            # Create handler class with reference to this server
            handler = type(
                "HealthHandler",
                (HealthCheckHandler,),
                {"health_server": self},
            )
            
            self._server = HTTPServer(
                (self.config.host, self.config.port),
                handler,
            )
            
            # Start server in background thread
            self._thread = threading.Thread(
                target=self._serve_forever,
                daemon=True,
                name="health-check-server",
            )
            self._thread.start()
            self._running = True
            
            # Start background health checker if tracker check is configured
            if self.config.check_tracker and self._tracker_check:
                self._start_background_checker()
            
            logger.info(
                f"Health check server started on "
                f"http://{self.config.host}:{self.config.port}/health"
            )
            return True
            
        except OSError as e:
            if e.errno == 48:  # Address already in use
                logger.error(f"Health check port {self.config.port} already in use")
            else:
                logger.error(f"Failed to start health check server: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to start health check server: {e}")
            return False
    
    def _serve_forever(self) -> None:
        """Serve requests until shutdown."""
        if self._server:
            self._server.serve_forever()
    
    def _start_background_checker(self) -> None:
        """Start background health checker thread."""
        self._checker_thread = threading.Thread(
            target=self._run_health_checks,
            daemon=True,
            name="health-checker",
        )
        self._checker_thread.start()
    
    def _run_health_checks(self) -> None:
        """Run periodic health checks."""
        while self._running:
            try:
                self._check_components()
            except Exception as e:
                logger.warning(f"Health check error: {e}")
            
            time.sleep(self.config.check_interval_seconds)
    
    def _check_components(self) -> None:
        """Check health of all components."""
        now = datetime.now(timezone.utc).isoformat()
        
        with self._status_lock:
            self._status.last_check = now
            self._status.uptime_seconds = time.time() - self._start_time
            
            # Check tracker if callback is set
            if self._tracker_check:
                try:
                    tracker_ok = self._tracker_check()
                    self._status.components["tracker"] = tracker_ok
                except Exception:
                    self._status.components["tracker"] = False
            
            # Update overall health
            self._status.healthy = all(self._status.components.values()) if self._status.components else True
    
    def set_tracker_check(self, check: Callable[[], bool]) -> None:
        """
        Set the tracker health check callback.
        
        Args:
            check: Callable that returns True if tracker is healthy.
        """
        self._tracker_check = check
    
    def get_status(self) -> HealthStatus:
        """
        Get current health status.
        
        Returns:
            Current health status.
        """
        with self._status_lock:
            self._status.uptime_seconds = time.time() - self._start_time
            return HealthStatus(
                healthy=self._status.healthy,
                ready=self._status.ready,
                components=dict(self._status.components),
                version=self._status.version,
                service_name=self._status.service_name,
                uptime_seconds=self._status.uptime_seconds,
                last_check=self._status.last_check,
                last_sync=self._status.last_sync,
                syncs_total=self._status.syncs_total,
                syncs_successful=self._status.syncs_successful,
                syncs_failed=self._status.syncs_failed,
            )
    
    def record_sync(self, success: bool) -> None:
        """
        Record a sync operation.
        
        Args:
            success: Whether the sync was successful.
        """
        with self._status_lock:
            self._status.syncs_total += 1
            if success:
                self._status.syncs_successful += 1
            else:
                self._status.syncs_failed += 1
            self._status.last_sync = datetime.now(timezone.utc).isoformat()
    
    def set_ready(self, ready: bool) -> None:
        """
        Set readiness status.
        
        Args:
            ready: Whether the service is ready.
        """
        with self._status_lock:
            self._status.ready = ready
    
    def set_component_status(self, name: str, healthy: bool) -> None:
        """
        Set a component's health status.
        
        Args:
            name: Component name.
            healthy: Whether the component is healthy.
        """
        with self._status_lock:
            self._status.components[name] = healthy
            self._status.healthy = all(self._status.components.values())
    
    def stop(self) -> None:
        """Stop the health check server."""
        self._running = False
        
        if self._server:
            self._server.shutdown()
            self._server = None
        
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None
        
        logger.debug("Health check server stopped")


def configure_health(
    enabled: bool = False,
    port: int = 8080,
    host: str = "0.0.0.0",
    check_tracker: bool = True,
) -> HealthServer:
    """
    Configure and optionally start the health check server.
    
    Args:
        enabled: Whether health checks are enabled.
        port: Port to listen on.
        host: Host address to bind to.
        check_tracker: Whether to check tracker connectivity.
        
    Returns:
        The configured health server.
    """
    config = HealthConfig(
        enabled=enabled,
        port=port,
        host=host,
        check_tracker=check_tracker,
    )
    server = HealthServer.configure(config)
    
    if enabled:
        server.start()
    
    return server


def get_health_server() -> Optional[HealthServer]:
    """Get the global health server instance."""
    return HealthServer.get_instance()

