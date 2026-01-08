"""
Lazy Proxy - Lazy loading proxies for domain entities.

Provides transparent lazy loading for UserStory and other entities,
loading expensive fields only when accessed.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generic, TypeVar

from .cache import FieldCache, get_global_cache
from .collections import LazyList


T = TypeVar("T")


class LazyField(Enum):
    """Fields that support lazy loading."""

    COMMENTS = "comments"
    SUBTASKS = "subtasks"
    ATTACHMENTS = "attachments"
    LINKS = "links"
    COMMITS = "commits"
    DESCRIPTION = "description"
    ACCEPTANCE_CRITERIA = "acceptance_criteria"
    TECHNICAL_NOTES = "technical_notes"


@dataclass
class LazyLoadingConfig:
    """Configuration for lazy loading behavior."""

    # Which fields to lazy load
    lazy_fields: set[LazyField] = field(
        default_factory=lambda: {
            LazyField.COMMENTS,
            LazyField.ATTACHMENTS,
            LazyField.COMMITS,
        }
    )

    # Cache settings
    use_cache: bool = True
    cache_ttl: float = 300.0  # 5 minutes default

    # Prefetch settings
    prefetch_on_access: set[LazyField] = field(default_factory=set)

    # Batch loading
    batch_size: int = 10

    @classmethod
    def eager(cls) -> "LazyLoadingConfig":
        """Create config that loads everything eagerly (no lazy loading)."""
        return cls(lazy_fields=set())

    @classmethod
    def minimal(cls) -> "LazyLoadingConfig":
        """Create config that lazy loads as much as possible."""
        return cls(
            lazy_fields={
                LazyField.COMMENTS,
                LazyField.SUBTASKS,
                LazyField.ATTACHMENTS,
                LazyField.LINKS,
                LazyField.COMMITS,
                LazyField.DESCRIPTION,
                LazyField.ACCEPTANCE_CRITERIA,
                LazyField.TECHNICAL_NOTES,
            }
        )


class LazyLoader(Generic[T]):
    """
    A descriptor that loads a value lazily.

    Usage:
        class MyClass:
            expensive_data = LazyLoader()

            def __init__(self):
                self._expensive_data_loader = lambda: fetch_data()

        obj = MyClass()
        # Data loaded on first access
        data = obj.expensive_data
    """

    def __init__(
        self,
        field_name: str | None = None,
        cache: FieldCache | None = None,
        cache_key_prefix: str = "",
    ):
        """
        Initialize lazy loader.

        Args:
            field_name: Name of the field (auto-detected if None)
            cache: Cache instance (uses global if None)
            cache_key_prefix: Prefix for cache keys
        """
        self.field_name = field_name
        self.cache = cache
        self.cache_key_prefix = cache_key_prefix
        self._attr_name: str | None = None

    def __set_name__(self, owner: type, name: str) -> None:
        """Called when descriptor is assigned to class attribute."""
        self._attr_name = name
        if self.field_name is None:
            self.field_name = name

    def __get__(self, obj: Any | None, objtype: type | None = None) -> Any:
        if obj is None:
            return self

        # Check for cached/loaded value
        value_attr = f"_lazy_{self._attr_name}_value"
        if hasattr(obj, value_attr):
            return getattr(obj, value_attr)

        # Check for loader
        loader_attr = f"_lazy_{self._attr_name}_loader"
        if not hasattr(obj, loader_attr):
            return None

        loader = getattr(obj, loader_attr)
        if loader is None:
            return None

        # Load value
        cache = self.cache or get_global_cache()
        cache_key = f"{self.cache_key_prefix}{self._attr_name}:{id(obj)}"

        if cache:
            cached = cache.get(cache_key)
            if cached is not None:
                setattr(obj, value_attr, cached)
                return cached

        value = loader()
        setattr(obj, value_attr, value)

        if cache:
            cache.set(cache_key, value)

        return value

    def __set__(self, obj: Any, value: Any) -> None:
        value_attr = f"_lazy_{self._attr_name}_value"
        setattr(obj, value_attr, value)


class LazyProxy(Generic[T]):
    """
    A proxy that wraps an object and intercepts field access.

    Allows selective lazy loading of specific fields.

    Usage:
        story = UserStory(...)
        lazy_story = LazyProxy(
            story,
            lazy_fields={
                "comments": lambda: fetch_comments(story.id),
                "attachments": lambda: fetch_attachments(story.id),
            }
        )

        # Access triggers loading
        comments = lazy_story.comments
    """

    def __init__(
        self,
        wrapped: T,
        lazy_fields: dict[str, Callable[[], Any]] | None = None,
        cache: FieldCache | None = None,
        cache_key: str | None = None,
    ):
        """
        Initialize lazy proxy.

        Args:
            wrapped: The object to wrap
            lazy_fields: Field name -> loader function mapping
            cache: Cache instance
            cache_key: Base cache key for this object
        """
        object.__setattr__(self, "_wrapped", wrapped)
        object.__setattr__(self, "_lazy_fields", lazy_fields or {})
        object.__setattr__(self, "_loaded_fields", {})
        object.__setattr__(self, "_cache", cache or get_global_cache())
        object.__setattr__(self, "_cache_key", cache_key or str(id(wrapped)))
        object.__setattr__(self, "_lock", threading.Lock())

    def __getattr__(self, name: str) -> Any:
        wrapped = object.__getattribute__(self, "_wrapped")
        lazy_fields = object.__getattribute__(self, "_lazy_fields")
        loaded_fields = object.__getattribute__(self, "_loaded_fields")

        # Check if this is a lazy field
        if name in lazy_fields:
            # Check if already loaded
            if name in loaded_fields:
                return loaded_fields[name]

            # Check cache
            cache = object.__getattribute__(self, "_cache")
            cache_key = object.__getattribute__(self, "_cache_key")
            full_key = f"{cache_key}:{name}"

            if cache:
                cached = cache.get(full_key)
                if cached is not None:
                    loaded_fields[name] = cached
                    return cached

            # Load the field
            lock = object.__getattribute__(self, "_lock")
            with lock:
                # Double-check after acquiring lock
                if name in loaded_fields:
                    return loaded_fields[name]

                loader = lazy_fields[name]
                value = loader()
                loaded_fields[name] = value

                if cache:
                    cache.set(full_key, value)

                return value

        # Not a lazy field, get from wrapped
        return getattr(wrapped, name)

    def __setattr__(self, name: str, value: Any) -> None:
        lazy_fields = object.__getattribute__(self, "_lazy_fields")
        loaded_fields = object.__getattribute__(self, "_loaded_fields")

        if name in lazy_fields:
            loaded_fields[name] = value
        else:
            wrapped = object.__getattribute__(self, "_wrapped")
            setattr(wrapped, name, value)

    def __repr__(self) -> str:
        wrapped = object.__getattribute__(self, "_wrapped")
        lazy_fields = object.__getattribute__(self, "_lazy_fields")
        loaded_fields = object.__getattribute__(self, "_loaded_fields")

        lazy_status = []
        for field in lazy_fields:
            status = "loaded" if field in loaded_fields else "lazy"
            lazy_status.append(f"{field}={status}")

        return f"LazyProxy({wrapped!r}, {', '.join(lazy_status)})"

    @property
    def _unwrap(self) -> T:
        """Get the wrapped object."""
        wrapped: T = object.__getattribute__(self, "_wrapped")
        return wrapped

    def _is_loaded(self, field: str) -> bool:
        """Check if a lazy field has been loaded."""
        loaded_fields = object.__getattribute__(self, "_loaded_fields")
        return field in loaded_fields

    def _preload(self, *fields: str) -> None:
        """Preload specific lazy fields."""
        for field in fields:
            getattr(self, field)

    def _preload_all(self) -> None:
        """Preload all lazy fields."""
        lazy_fields = object.__getattribute__(self, "_lazy_fields")
        for field in lazy_fields:
            getattr(self, field)


class LazyStory:
    """
    A lazy-loading wrapper for UserStory.

    Provides transparent lazy loading for expensive fields like
    comments, attachments, and commits.

    Usage:
        # Create from tracker data
        story = LazyStory.from_tracker(
            story_key="PROJ-123",
            basic_data=basic_story_data,
            tracker=issue_tracker,
        )

        # Basic fields available immediately
        print(story.title)
        print(story.status)

        # Comments loaded on demand
        for comment in story.comments:
            print(comment)
    """

    def __init__(
        self,
        story_id: str,
        title: str,
        status: str = "planned",
        priority: str = "medium",
        story_points: int = 0,
        assignee: str | None = None,
        labels: list[str] | None = None,
        sprint: str | None = None,
        external_key: str | None = None,
        external_url: str | None = None,
    ):
        """Initialize with basic story data."""
        self.story_id = story_id
        self.title = title
        self.status = status
        self.priority = priority
        self.story_points = story_points
        self.assignee = assignee
        self.labels = labels or []
        self.sprint = sprint
        self.external_key = external_key
        self.external_url = external_url

        # Lazy fields
        self._comments: LazyList[Any] | None = None
        self._subtasks: LazyList[Any] | None = None
        self._attachments: LazyList[str] | None = None
        self._commits: LazyList[Any] | None = None
        self._links: LazyList[tuple[str, str]] | None = None
        self._description: Any | None = None
        self._description_loaded: bool = False
        self._acceptance_criteria: Any | None = None
        self._acceptance_criteria_loaded: bool = False
        self._technical_notes: str | None = None
        self._technical_notes_loaded: bool = False

        # Loaders (to be set by factory methods)
        self._comments_loader: Callable[[], list[Any]] | None = None
        self._subtasks_loader: Callable[[], list[Any]] | None = None
        self._attachments_loader: Callable[[], list[str]] | None = None
        self._commits_loader: Callable[[], list[Any]] | None = None
        self._links_loader: Callable[[], list[tuple[str, str]]] | None = None
        self._description_loader: Callable[[], Any] | None = None
        self._acceptance_criteria_loader: Callable[[], Any] | None = None
        self._technical_notes_loader: Callable[[], str] | None = None

    @property
    def comments(self) -> list[Any]:
        """Get comments (lazy loaded)."""
        if self._comments is None:
            if self._comments_loader:
                self._comments = LazyList(self._comments_loader)
            else:
                self._comments = LazyList(initial_data=[])
        return list(self._comments)

    @comments.setter
    def comments(self, value: list[Any]) -> None:
        self._comments = LazyList(initial_data=value)

    @property
    def subtasks(self) -> list[Any]:
        """Get subtasks (lazy loaded)."""
        if self._subtasks is None:
            if self._subtasks_loader:
                self._subtasks = LazyList(self._subtasks_loader)
            else:
                self._subtasks = LazyList(initial_data=[])
        return list(self._subtasks)

    @subtasks.setter
    def subtasks(self, value: list[Any]) -> None:
        self._subtasks = LazyList(initial_data=value)

    @property
    def attachments(self) -> list[str]:
        """Get attachments (lazy loaded)."""
        if self._attachments is None:
            if self._attachments_loader:
                self._attachments = LazyList(self._attachments_loader)
            else:
                self._attachments = LazyList(initial_data=[])
        return list(self._attachments)

    @attachments.setter
    def attachments(self, value: list[str]) -> None:
        self._attachments = LazyList(initial_data=value)

    @property
    def commits(self) -> list[Any]:
        """Get commits (lazy loaded)."""
        if self._commits is None:
            if self._commits_loader:
                self._commits = LazyList(self._commits_loader)
            else:
                self._commits = LazyList(initial_data=[])
        return list(self._commits)

    @commits.setter
    def commits(self, value: list[Any]) -> None:
        self._commits = LazyList(initial_data=value)

    @property
    def links(self) -> list[tuple[str, str]]:
        """Get links (lazy loaded)."""
        if self._links is None:
            if self._links_loader:
                self._links = LazyList(self._links_loader)
            else:
                self._links = LazyList(initial_data=[])
        return list(self._links)

    @links.setter
    def links(self, value: list[tuple[str, str]]) -> None:
        self._links = LazyList(initial_data=value)

    @property
    def description(self) -> Any:
        """Get description (lazy loaded)."""
        if not self._description_loaded:
            if self._description_loader:
                self._description = self._description_loader()
            self._description_loaded = True
        return self._description

    @description.setter
    def description(self, value: Any) -> None:
        self._description = value
        self._description_loaded = True

    @property
    def acceptance_criteria(self) -> Any:
        """Get acceptance criteria (lazy loaded)."""
        if not self._acceptance_criteria_loaded:
            if self._acceptance_criteria_loader:
                self._acceptance_criteria = self._acceptance_criteria_loader()
            self._acceptance_criteria_loaded = True
        return self._acceptance_criteria

    @acceptance_criteria.setter
    def acceptance_criteria(self, value: Any) -> None:
        self._acceptance_criteria = value
        self._acceptance_criteria_loaded = True

    @property
    def technical_notes(self) -> str:
        """Get technical notes (lazy loaded)."""
        if not self._technical_notes_loaded:
            if self._technical_notes_loader:
                self._technical_notes = self._technical_notes_loader()
            self._technical_notes_loaded = True
        return self._technical_notes or ""

    @technical_notes.setter
    def technical_notes(self, value: str) -> None:
        self._technical_notes = value
        self._technical_notes_loaded = True

    def set_loader(
        self,
        field: LazyField,
        loader: Callable[[], Any],
    ) -> None:
        """Set loader for a lazy field."""
        loader_map = {
            LazyField.COMMENTS: "_comments_loader",
            LazyField.SUBTASKS: "_subtasks_loader",
            LazyField.ATTACHMENTS: "_attachments_loader",
            LazyField.COMMITS: "_commits_loader",
            LazyField.LINKS: "_links_loader",
            LazyField.DESCRIPTION: "_description_loader",
            LazyField.ACCEPTANCE_CRITERIA: "_acceptance_criteria_loader",
            LazyField.TECHNICAL_NOTES: "_technical_notes_loader",
        }
        setattr(self, loader_map[field], loader)

    def is_loaded(self, field: LazyField) -> bool:
        """Check if a lazy field has been loaded."""
        loaded_map = {
            LazyField.COMMENTS: lambda: self._comments is not None and self._comments.is_loaded,
            LazyField.SUBTASKS: lambda: self._subtasks is not None and self._subtasks.is_loaded,
            LazyField.ATTACHMENTS: lambda: self._attachments is not None
            and self._attachments.is_loaded,
            LazyField.COMMITS: lambda: self._commits is not None and self._commits.is_loaded,
            LazyField.LINKS: lambda: self._links is not None and self._links.is_loaded,
            LazyField.DESCRIPTION: lambda: self._description_loaded,
            LazyField.ACCEPTANCE_CRITERIA: lambda: self._acceptance_criteria_loaded,
            LazyField.TECHNICAL_NOTES: lambda: self._technical_notes_loaded,
        }
        return loaded_map[field]()

    def preload(self, *fields: LazyField) -> None:
        """Preload specific lazy fields."""
        for field in fields:
            getattr(self, field.value)

    def preload_all(self) -> None:
        """Preload all lazy fields."""
        for field in LazyField:
            getattr(self, field.value)

    @classmethod
    def from_basic_data(
        cls,
        story_id: str,
        title: str,
        **kwargs: Any,
    ) -> "LazyStory":
        """Create a LazyStory from basic data."""
        return cls(story_id=story_id, title=title, **kwargs)

    def __repr__(self) -> str:
        loaded = [f.value for f in LazyField if self.is_loaded(f)]
        return f"LazyStory(id={self.story_id!r}, title={self.title!r}, loaded={loaded})"
