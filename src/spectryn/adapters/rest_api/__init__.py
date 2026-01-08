"""
REST API adapter implementation.

This package provides a REST API server for Spectra, allowing
programmatic access to epics, stories, and sync operations.
"""

from .server import SpectraRestServer, create_rest_server


__all__ = [
    "SpectraRestServer",
    "create_rest_server",
]
