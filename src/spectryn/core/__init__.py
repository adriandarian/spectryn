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

# Import domain first (has canonical IssueType enum)
# Import constants (IssueType alias will override domain's - we'll fix that below)
from .constants import *
from .container import (
    CircularDependencyError,
    Container,
    ContainerError,
    Lifecycle,
    ServiceNotFoundError,
    get_container,
    reset_container,
)
from .domain import *

# Re-import the domain IssueType to make it the canonical export
from .domain.enums import IssueType
from .exceptions import *
from .ports import *
from .result import (
    BatchItem,
    BatchResult,
    Err,
    Ok,
    OperationError,
    OperationResult,
    Result,
    ResultError,
)
from .services import (
    create_sync_orchestrator,
    create_test_container,
    register_defaults,
    register_for_sync,
)
from .specification import (
    HasDescriptionSpec,
    HasKeySpec,
    HasSubtasksSpec,
    IssueTypeSpec,
    MatchedSpec,
    PredicateSpec,
    Specification,
    StatusSpec,
    StoryPointsSpec,
    TitleMatchesSpec,
    UnmatchedSpec,
    all_of,
    any_of,
    none_of,
)
