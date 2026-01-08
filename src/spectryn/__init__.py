"""
spectra - Markdown to Jira Sync Tool

A production-grade CLI tool for synchronizing markdown documentation with Jira.

Architecture:
- core/domain: Pure domain entities and value objects
- core/ports: Abstract interfaces (ports)
- adapters/: Concrete implementations (adapters)
- application/: Use cases and orchestration
- cli/: Command line interface

Repository: https://github.com/adriandarian/spectra
"""

__version__ = "2.0.0"
__author__ = "Adrian Darian"

# Re-export main entry points for convenience
from .cli.app import main, run


__all__ = ["__version__", "main", "run"]
