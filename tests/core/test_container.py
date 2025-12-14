"""Tests for the dependency injection container."""

import pytest
from abc import ABC, abstractmethod

from md2jira.core.container import (
    Container,
    Lifecycle,
    ServiceNotFoundError,
    CircularDependencyError,
    get_container,
    reset_container,
)


# =============================================================================
# Test Interfaces and Implementations
# =============================================================================

class IService(ABC):
    """Test interface."""
    
    @abstractmethod
    def do_something(self) -> str:
        pass


class ServiceA(IService):
    """Test implementation A."""
    
    def __init__(self, value: str = "A"):
        self.value = value
    
    def do_something(self) -> str:
        return f"ServiceA: {self.value}"


class ServiceB(IService):
    """Test implementation B."""
    
    def do_something(self) -> str:
        return "ServiceB"


class DependentService:
    """Service that depends on IService."""
    
    def __init__(self, dependency: IService):
        self.dependency = dependency
    
    def do_work(self) -> str:
        return f"Working with {self.dependency.do_something()}"


# =============================================================================
# Container Tests
# =============================================================================

class TestContainerBasics:
    """Test basic container operations."""
    
    def test_register_and_get(self):
        """Test basic registration and resolution."""
        container = Container()
        container.register(IService, lambda c: ServiceA())
        
        service = container.get(IService)
        
        assert isinstance(service, ServiceA)
        assert service.do_something() == "ServiceA: A"
    
    def test_register_instance(self):
        """Test registering an existing instance."""
        container = Container()
        instance = ServiceA("custom")
        container.register_instance(IService, instance)
        
        service = container.get(IService)
        
        assert service is instance
        assert service.value == "custom"
    
    def test_service_not_found(self):
        """Test that ServiceNotFoundError is raised for missing services."""
        container = Container()
        
        with pytest.raises(ServiceNotFoundError) as exc:
            container.get(IService)
        
        assert "IService" in str(exc.value)
    
    def test_try_get_returns_none(self):
        """Test try_get returns None for missing services."""
        container = Container()
        
        result = container.try_get(IService)
        
        assert result is None
    
    def test_has_service(self):
        """Test checking if a service is registered."""
        container = Container()
        
        assert not container.has(IService)
        
        container.register(IService, lambda c: ServiceA())
        
        assert container.has(IService)
    
    def test_method_chaining(self):
        """Test that register methods support chaining."""
        container = (
            Container()
            .register(IService, lambda c: ServiceA())
            .register_instance(DependentService, DependentService(ServiceB()))
        )
        
        assert container.has(IService)
        assert container.has(DependentService)


class TestLifecycles:
    """Test singleton vs transient lifecycles."""
    
    def test_singleton_returns_same_instance(self):
        """Test that singleton returns the same instance."""
        container = Container()
        container.register(IService, lambda c: ServiceA(), Lifecycle.SINGLETON)
        
        service1 = container.get(IService)
        service2 = container.get(IService)
        
        assert service1 is service2
    
    def test_transient_returns_new_instances(self):
        """Test that transient returns new instances."""
        container = Container()
        container.register(IService, lambda c: ServiceA(), Lifecycle.TRANSIENT)
        
        service1 = container.get(IService)
        service2 = container.get(IService)
        
        assert service1 is not service2
    
    def test_register_factory_creates_transient(self):
        """Test register_factory creates transient services."""
        container = Container()
        container.register_factory(IService, lambda c: ServiceA())
        
        service1 = container.get(IService)
        service2 = container.get(IService)
        
        assert service1 is not service2
    
    def test_reset_singletons(self):
        """Test resetting singleton instances."""
        container = Container()
        container.register(IService, lambda c: ServiceA())
        
        service1 = container.get(IService)
        
        container.reset_singletons()
        
        service2 = container.get(IService)
        
        assert service1 is not service2


class TestDependencyResolution:
    """Test dependency resolution."""
    
    def test_factory_receives_container(self):
        """Test that factories receive the container."""
        container = Container()
        container.register(IService, lambda c: ServiceA())
        container.register(
            DependentService,
            lambda c: DependentService(c.get(IService))
        )
        
        dependent = container.get(DependentService)
        
        assert "ServiceA" in dependent.do_work()
    
    def test_circular_dependency_detection(self):
        """Test that circular dependencies are detected."""
        container = Container()
        
        # A depends on B, B depends on A
        container.register(
            ServiceA,
            lambda c: ServiceA(c.get(ServiceB).do_something())  # type: ignore
        )
        container.register(
            ServiceB,
            lambda c: c.get(ServiceA) or ServiceB()  # type: ignore
        )
        
        with pytest.raises(CircularDependencyError):
            container.get(ServiceA)


class TestOverrides:
    """Test override functionality for testing."""
    
    def test_override_context_manager(self):
        """Test overriding a service temporarily."""
        container = Container()
        container.register(IService, lambda c: ServiceA())
        
        mock = ServiceB()
        
        with container.override(IService, mock):
            service = container.get(IService)
            assert isinstance(service, ServiceB)
        
        # After context, original is restored
        service = container.get(IService)
        assert isinstance(service, ServiceA)
    
    def test_override_many(self):
        """Test overriding multiple services."""
        container = Container()
        container.register(IService, lambda c: ServiceA())
        container.register(DependentService, lambda c: DependentService(ServiceA()))
        
        mock_service = ServiceB()
        mock_dependent = DependentService(ServiceB())
        
        with container.override_many({
            IService: mock_service,
            DependentService: mock_dependent,
        }):
            assert container.get(IService) is mock_service
            assert container.get(DependentService) is mock_dependent
        
        # Restored after context
        assert isinstance(container.get(IService), ServiceA)
    
    def test_nested_overrides(self):
        """Test nested override contexts."""
        container = Container()
        container.register(IService, lambda c: ServiceA("original"))
        
        with container.override(IService, ServiceA("first")):
            assert container.get(IService).value == "first"
            
            with container.override(IService, ServiceA("second")):
                assert container.get(IService).value == "second"
            
            # Inner context ended, back to first override
            assert container.get(IService).value == "first"
        
        # All contexts ended, back to original
        assert container.get(IService).value == "original"


class TestChildContainers:
    """Test hierarchical container resolution."""
    
    def test_child_resolves_from_parent(self):
        """Test that child containers can resolve from parent."""
        parent = Container()
        parent.register(IService, lambda c: ServiceA())
        
        child = parent.create_scope()
        
        service = child.get(IService)
        assert isinstance(service, ServiceA)
    
    def test_child_can_override_parent(self):
        """Test that child containers can override parent services."""
        parent = Container()
        parent.register(IService, lambda c: ServiceA())
        
        child = parent.create_scope()
        child.register(IService, lambda c: ServiceB())
        
        parent_service = parent.get(IService)
        child_service = child.get(IService)
        
        assert isinstance(parent_service, ServiceA)
        assert isinstance(child_service, ServiceB)
    
    def test_child_has_checks_parent(self):
        """Test that has() checks parent container."""
        parent = Container()
        parent.register(IService, lambda c: ServiceA())
        
        child = parent.create_scope()
        
        assert child.has(IService)


class TestGlobalContainer:
    """Test global container singleton."""
    
    def test_get_container_returns_singleton(self):
        """Test that get_container returns the same instance."""
        reset_container()
        
        container1 = get_container()
        container2 = get_container()
        
        assert container1 is container2
    
    def test_reset_container_clears_global(self):
        """Test that reset_container clears the global container."""
        reset_container()
        
        container1 = get_container()
        container1.register(IService, lambda c: ServiceA())
        
        reset_container()
        
        container2 = get_container()
        assert not container2.has(IService)
        assert container1 is not container2

