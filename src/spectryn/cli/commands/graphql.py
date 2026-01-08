"""
GraphQL API server command handler.

This module contains the handler for running Spectra as a GraphQL API server:
- run_graphql: Start the GraphQL API server

The server provides:
- Query endpoint for epics, stories, subtasks
- Mutation endpoint for sync operations
- Subscription endpoint for real-time updates (via WebSocket)
- GraphQL Playground for interactive exploration
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


__all__ = ["run_graphql"]


def run_graphql(args: "argparse.Namespace") -> int:
    """
    Run the GraphQL API server.

    Starts a GraphQL server that exposes Spectra's functionality
    via a GraphQL API, including queries for data and mutations
    for operations.

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

    # Get GraphQL server configuration from args
    host = getattr(args, "graphql_host", "0.0.0.0")
    port = getattr(args, "graphql_port", 8080)
    path = getattr(args, "graphql_path", "/graphql")
    enable_playground = not getattr(args, "no_playground", False)
    enable_introspection = not getattr(args, "no_introspection", False)

    console.info("Starting GraphQL API server...")
    console.info(f"  Host: {host}")
    console.info(f"  Port: {port}")
    console.info(f"  Endpoint: {path}")
    console.info(f"  Playground: {'enabled' if enable_playground else 'disabled'}")
    console.info(f"  Introspection: {'enabled' if enable_introspection else 'disabled'}")

    try:
        from spectryn.adapters.graphql_api import create_graphql_server

        # Create event bus if needed for subscriptions
        from spectryn.core.domain.events import EventBus

        event_bus = EventBus()

        # Create the server
        server = create_graphql_server(
            host=host,
            port=port,
            path=path,
            enable_playground=enable_playground,
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
            console.info("\nShutting down GraphQL server...")
            shutdown_event.set()

        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)

        # Start server
        console.success(f"GraphQL API server started at http://{host}:{port}{path}")
        if enable_playground:
            console.info(f"GraphQL Playground available at http://{host}:{port}{path}")

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
        console.success("GraphQL server stopped")

        return ExitCode.SUCCESS

    except ImportError as e:
        console.error(f"Failed to import GraphQL server components: {e}")
        console.error("Make sure you have the required dependencies installed.")
        return ExitCode.DEPENDENCY_ERROR

    except Exception as e:
        console.error(f"GraphQL server error: {e}")
        if getattr(args, "verbose", False):
            import traceback

            traceback.print_exc()
        return ExitCode.RUNTIME_ERROR


def _load_markdown_data(server, markdown_path: str, console: Console) -> None:
    """
    Load markdown data into the GraphQL server.

    Args:
        server: GraphQL server instance.
        markdown_path: Path to markdown file.
        console: Console for output.
    """
    try:
        from spectryn.adapters import MarkdownParser

        parser = MarkdownParser()
        content = Path(markdown_path).read_text(encoding="utf-8")
        epic = parser.parse(content)

        if epic:
            server.load_epic(epic)
            console.info(f"Loaded epic: {epic.key} with {len(epic.stories)} stories")
        else:
            console.warning("No epic found in markdown file")

    except Exception as e:
        console.warning(f"Failed to load markdown data: {e}")


async def run_graphql_async(args: "argparse.Namespace") -> int:
    """
    Async version of run_graphql for integration with async code.

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

    host = getattr(args, "graphql_host", "0.0.0.0")
    port = getattr(args, "graphql_port", 8080)
    path = getattr(args, "graphql_path", "/graphql")
    enable_playground = not getattr(args, "no_playground", False)

    try:
        from spectryn.adapters.graphql_api import create_graphql_server
        from spectryn.core.domain.events import EventBus

        event_bus = EventBus()
        server = create_graphql_server(
            host=host,
            port=port,
            path=path,
            enable_playground=enable_playground,
            event_bus=event_bus,
        )

        # Load data if provided
        markdown_path = getattr(args, "input", None) or getattr(args, "markdown", None)
        if markdown_path and Path(markdown_path).exists():
            _load_markdown_data(server, markdown_path, console)

        console.success(f"GraphQL API server started at http://{host}:{port}{path}")

        # Start and run until cancelled
        await server.start()

        try:
            # Wait indefinitely
            while server.is_running():
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await server.stop()

        return ExitCode.SUCCESS

    except Exception as e:
        console.error(f"GraphQL server error: {e}")
        return ExitCode.RUNTIME_ERROR
