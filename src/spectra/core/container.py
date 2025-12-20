"""
Dependency Injection Container for spectra.

A lightweight DI container that provides:
- Factory-based service registration
- Singleton and transient lifecycles
- Scoped containers for testing
- Easy override mechanism for tests

This is a simple container focused on the specific needs of spectra,
not a full-featured DI framework. It prioritizes simplicity and testability.

Usage:
    # Production
    container = Container()
    container.register_defaults()

    tracker = container.get(IssueTrackerPort)

    # Testing with overrides
    with container.override(IssueTrackerPort, mock_tracker):
        result = my_function()  # Uses mock_tracker

Design Principles:
    1. Explicit over implicit - no magic autowiring
    2. Factories over instances - late binding for configuration
    3. Thread-safe - safe for concurrent use
    4. Test-friendly - easy to override for testing
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum, auto
from threading import Lock
from typing import Any, Generic, TypeVar, cast


T = TypeVar("T")
logger = logging.getLogger("Container")


class Lifecycle(Enum):
    """Service lifecycle options."""

    SINGLETON = auto()  # Single instance for container lifetime
    TRANSIENT = auto()  # New instance each time
    SCOPED = auto()  # Single instance per scope (for future use)


@dataclass
class ServiceDescriptor(Generic[T]):
    """Describes how to create a service."""

    service_type: type[T]
    factory: Callable[[Container], T]
    lifecycle: Lifecycle = Lifecycle.SINGLETON
    instance: T | None = field(default=None, repr=False)


class ContainerError(Exception):
    """Raised when container operations fail."""


class ServiceNotFoundError(ContainerError):
    """Raised when a requested service is not registered."""


class CircularDependencyError(ContainerError):
    """Raised when circular dependencies are detected."""


class Container:
    """
    Lightweight dependency injection container.

    Supports factory-based registration with singleton/transient lifecycles.
    Thread-safe and test-friendly with override support.

    Example:
        >>> container = Container()
        >>> container.register(IssueTrackerPort, lambda c: JiraAdapter(...))
        >>> tracker = container.get(IssueTrackerPort)
    """

    def __init__(self, parent: Container | None = None) -> None:
        """
        Initialize the container.

        Args:
            parent: Optional parent container for hierarchical resolution
        """
        self._services: dict[type, ServiceDescriptor] = {}
        self._overrides: dict[type, Any] = {}
        self._lock = Lock()
        self._resolving: set[type] = set()  # For circular dependency detection
        self._parent = parent

    # -------------------------------------------------------------------------
    # Registration
    # -------------------------------------------------------------------------

    def register(
        self,
        service_type: type[T],
        factory: Callable[[Container], T],
        lifecycle: Lifecycle = Lifecycle.SINGLETON,
    ) -> Container:
        """
        Register a service factory.

        Args:
            service_type: The type/interface to register
            factory: Factory function that creates the service
            lifecycle: SINGLETON (default) or TRANSIENT

        Returns:
            Self for method chaining
        """
        with self._lock:
            self._services[service_type] = ServiceDescriptor(
                service_type=service_type,
                factory=factory,
                lifecycle=lifecycle,
            )
        return self

    def register_instance(
        self,
        service_type: type[T],
        instance: T,
    ) -> Container:
        """
        Register an existing instance as a singleton.

        Args:
            service_type: The type/interface to register
            instance: The instance to use

        Returns:
            Self for method chaining
        """
        with self._lock:
            self._services[service_type] = ServiceDescriptor(
                service_type=service_type,
                factory=lambda c: instance,
                lifecycle=Lifecycle.SINGLETON,
                instance=instance,
            )
        return self

    def register_factory(
        self,
        service_type: type[T],
        factory: Callable[[Container], T],
    ) -> Container:
        """
        Register a transient factory (new instance each time).

        Args:
            service_type: The type/interface to register
            factory: Factory function

        Returns:
            Self for method chaining
        """
        return self.register(service_type, factory, Lifecycle.TRANSIENT)

    # -------------------------------------------------------------------------
    # Resolution
    # -------------------------------------------------------------------------

    def get(self, service_type: type[T]) -> T:
        """
        Resolve a service by type.

        Args:
            service_type: The type to resolve

        Returns:
            The service instance

        Raises:
            ServiceNotFoundError: If service is not registered
            CircularDependencyError: If circular dependency detected
        """
        # Check overrides first (for testing)
        with self._lock:
            if service_type in self._overrides:
                return cast(T, self._overrides[service_type])

        # Try to resolve from this container
        descriptor = self._get_descriptor(service_type)

        if descriptor is None:
            # Try parent container
            if self._parent is not None:
                return self._parent.get(service_type)
            raise ServiceNotFoundError(f"Service not registered: {service_type.__name__}")

        return self._resolve(cast(ServiceDescriptor[T], descriptor))

    def try_get(self, service_type: type[T]) -> T | None:
        """
        Try to resolve a service, returning None if not found.

        Args:
            service_type: The type to resolve

        Returns:
            The service instance or None
        """
        try:
            return self.get(service_type)
        except ServiceNotFoundError:
            return None

    def has(self, service_type: type) -> bool:
        """Check if a service is registered."""
        with self._lock:
            if service_type in self._services:
                return True
        if self._parent is not None:
            return self._parent.has(service_type)
        return False

    def _get_descriptor(self, service_type: type) -> ServiceDescriptor | None:
        """Get service descriptor if registered."""
        with self._lock:
            return self._services.get(service_type)

    def _resolve(self, descriptor: ServiceDescriptor[T]) -> T:
        """Resolve a service from its descriptor."""
        # Check for circular dependencies
        if descriptor.service_type in self._resolving:
            raise CircularDependencyError(
                f"Circular dependency detected: {descriptor.service_type.__name__}"
            )

        # For singletons, check if already created
        if descriptor.lifecycle == Lifecycle.SINGLETON:
            with self._lock:
                if descriptor.instance is not None:
                    return descriptor.instance

        # Create new instance
        try:
            self._resolving.add(descriptor.service_type)
            instance = descriptor.factory(self)
        finally:
            self._resolving.discard(descriptor.service_type)

        # Cache singleton instances
        if descriptor.lifecycle == Lifecycle.SINGLETON:
            with self._lock:
                descriptor.instance = instance

        return instance

    # -------------------------------------------------------------------------
    # Testing Support
    # -------------------------------------------------------------------------

    @contextmanager
    def override(
        self,
        service_type: type[T],
        instance: T,
    ) -> Iterator[None]:
        """
        Temporarily override a service for testing.

        Args:
            service_type: The type to override
            instance: The mock/test instance to use

        Example:
            >>> with container.override(IssueTrackerPort, mock_tracker):
            ...     result = sync_function()  # Uses mock_tracker
        """
        with self._lock:
            old_override = self._overrides.get(service_type)
            self._overrides[service_type] = instance

        try:
            yield
        finally:
            with self._lock:
                if old_override is None:
                    self._overrides.pop(service_type, None)
                else:
                    self._overrides[service_type] = old_override

    @contextmanager
    def override_many(
        self,
        overrides: dict[type, Any],
    ) -> Iterator[None]:
        """
        Temporarily override multiple services.

        Args:
            overrides: Dict mapping types to mock instances
        """
        with self._lock:
            old_overrides = {t: self._overrides.get(t) for t in overrides}
            self._overrides.update(overrides)

        try:
            yield
        finally:
            with self._lock:
                for service_type, old_value in old_overrides.items():
                    if old_value is None:
                        self._overrides.pop(service_type, None)
                    else:
                        self._overrides[service_type] = old_value

    def create_scope(self) -> Container:
        """
        Create a child container for scoped services.

        The child container inherits registrations from the parent
        but can have its own overrides and scoped instances.

        Returns:
            New child Container
        """
        return Container(parent=self)

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def clear(self) -> None:
        """Clear all registrations and instances."""
        with self._lock:
            self._services.clear()
            self._overrides.clear()
            self._resolving.clear()

    def reset_singletons(self) -> None:
        """Reset all singleton instances (useful for testing)."""
        with self._lock:
            for descriptor in self._services.values():
                if descriptor.lifecycle == Lifecycle.SINGLETON:
                    descriptor.instance = None


# =============================================================================
# Global Container
# =============================================================================

_container: Container | None = None
_container_lock = Lock()


def get_container() -> Container:
    """
    Get the global container singleton.

    Creates the container on first call.

    Returns:
        The global Container instance
    """
    global _container
    with _container_lock:
        if _container is None:
            _container = Container()
        return _container


def reset_container() -> None:
    """Reset the global container (for testing)."""
    global _container
    with _container_lock:
        if _container is not None:
            _container.clear()
        _container = None


__all__ = [
    "CircularDependencyError",
    "Container",
    "ContainerError",
    "Lifecycle",
    "ServiceDescriptor",
    "ServiceNotFoundError",
    "get_container",
    "reset_container",
]
