"""
REST API server command handler.

This module contains the handler for running Spectra as a REST API server:
- run_rest_api: Start the REST API server

The server provides:
- RESTful endpoints for epics, stories, subtasks
- CRUD operations with standard HTTP verbs
- Pagination and filtering support
- OpenAPI documentation endpoint
"""

import asyncio
import logging
import signal
from pathlib import Path
from typing import TYPE_CHECKING

from spectryn.cli.exit_codes import ExitCode
from spectryn.cli.logging import setup_logging
from spectryn.cli.output import Console


if TYPE_CHECKING:
    import argparse


__all__ = ["run_rest_api"]


def run_rest_api(args: "argparse.Namespace") -> int:
    """
    Run the REST API server.

    Starts a REST API server that exposes Spectra's functionality
    via standard HTTP endpoints for CRUD operations.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code.
    """
    # Setup logging
    log_level = logging.DEBUG if getattr(args, "verbose", False) else logging.INFO
    log_format = getattr(args, "log_format", "text")
    setup_logging(level=log_level, log_format=log_format)

    # Create console
    console = Console(
        color=not getattr(args, "no_color", False),
        verbose=getattr(args, "verbose", False),
        quiet=getattr(args, "quiet", False),
    )

    # Get REST API server configuration from args
    host = getattr(args, "rest_host", "0.0.0.0")
    port = getattr(args, "rest_port", 8080)
    base_path = getattr(args, "rest_base_path", "/api/v1")
    enable_cors = not getattr(args, "no_cors", False)
    enable_docs = not getattr(args, "no_docs", False)

    console.info("Starting REST API server...")
    console.info(f"  Host: {host}")
    console.info(f"  Port: {port}")
    console.info(f"  Base Path: {base_path}")
    console.info(f"  CORS: {'enabled' if enable_cors else 'disabled'}")
    console.info(f"  Documentation: {'enabled' if enable_docs else 'disabled'}")

    try:
        from spectryn.adapters.rest_api import create_rest_server

        # Create event bus if needed
        from spectryn.core.domain.events import EventBus

        event_bus = EventBus()

        # Create the server
        server = create_rest_server(
            host=host,
            port=port,
            base_path=base_path,
            enable_cors=enable_cors,
            enable_docs=enable_docs,
            event_bus=event_bus,
        )

        # Load data if markdown file is provided
        markdown_path = getattr(args, "input", None) or getattr(args, "markdown", None)
        if markdown_path and Path(markdown_path).exists():
            console.info(f"Loading data from: {markdown_path}")
            _load_markdown_data(server, markdown_path, console)

        # Setup signal handlers for graceful shutdown
        shutdown_event = asyncio.Event()

        def handle_shutdown(signum, frame):
            console.info("\nShutting down REST API server...")
            shutdown_event.set()

        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)

        # Start server
        console.success(f"REST API server started at http://{host}:{port}{base_path}")
        if enable_docs:
            console.info(f"API documentation at http://{host}:{port}{base_path}/docs")
            console.info(f"OpenAPI spec at http://{host}:{port}{base_path}/openapi.json")

        # Run server (synchronous start, then wait for shutdown)
        server._start_sync()

        # Keep running until shutdown
        try:
            while server.is_running() and not shutdown_event.is_set():
                import time

                time.sleep(0.5)
        except KeyboardInterrupt:
            pass

        # Stop server
        server._stop_sync()
        console.success("REST API server stopped")

        return ExitCode.SUCCESS

    except ImportError as e:
        console.error(f"Failed to import REST API server components: {e}")
        console.error("Make sure you have the required dependencies installed.")
        return ExitCode.DEPENDENCY_ERROR

    except Exception as e:
        console.error(f"REST API server error: {e}")
        if getattr(args, "verbose", False):
            import traceback

            traceback.print_exc()
        return ExitCode.RUNTIME_ERROR


def _load_markdown_data(server, markdown_path: str, console: Console) -> None:
    """
    Load markdown data into the REST API server.

    Args:
        server: REST API server instance.
        markdown_path: Path to markdown file.
        console: Console for output.
    """
    try:
        from spectryn.adapters.parsers import MarkdownParser

        parser = MarkdownParser()
        with open(markdown_path, encoding="utf-8") as f:
            content = f.read()

        epics = parser.parse(content)

        for epic in epics:
            server.load_epic(epic)

        console.success(f"Loaded {len(epics)} epic(s) from markdown")

        # Log story counts
        total_stories = sum(len(e.stories) for e in epics)
        total_subtasks = sum(len(s.subtasks) for e in epics for s in e.stories)
        console.info(f"  Stories: {total_stories}")
        console.info(f"  Subtasks: {total_subtasks}")

    except Exception as e:
        console.warning(f"Failed to load markdown data: {e}")


async def run_rest_api_async(args: "argparse.Namespace") -> int:
    """
    Run the REST API server asynchronously.

    For use in async contexts or when integrating with other async services.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code.
    """
    # This implementation reuses the sync version for simplicity
    # A full async implementation could use aiohttp or similar
    return run_rest_api(args)
