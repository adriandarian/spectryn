"""
Core module - Pure domain logic with no external dependencies.

This module contains:
- domain/: Entities, value objects, and domain enums
- ports/: Abstract interfaces that adapters must implement
- exceptions: Centralized exception hierarchy
- constants: Application-wide constants and defaults
- container: Dependency injection container
- services: Service registration and factories
"""

from .domain import *
from .ports import *
from .exceptions import *
from .constants import *
from .container import (
    Container,
    Lifecycle,
    ContainerError,
    ServiceNotFoundError,
    CircularDependencyError,
    get_container,
    reset_container,
)
from .services import (
    register_defaults,
    register_for_sync,
    create_test_container,
    create_sync_orchestrator,
)

