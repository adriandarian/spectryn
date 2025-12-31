"""
Lazy Collections - Deferred-loading collection types.

Provides lazy versions of list and dict that load data on first access.
"""

import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar


T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")


@dataclass
class LazyCollection(Generic[T]):
    """
    Base class for lazy-loading collections.

    Defers data loading until first access.
    """

    _loader: Callable[[], list[T]] | None = None
    _data: list[T] | None = None
    _loaded: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _ensure_loaded(self) -> None:
        """Load data if not already loaded."""
        if self._loaded:
            return

        with self._lock:
            if self._loaded:
                return

            if self._loader is not None:
                self._data = self._loader()
            else:
                self._data = []

            self._loaded = True

    @property
    def is_loaded(self) -> bool:
        """Check if data has been loaded."""
        return self._loaded

    def reload(self) -> None:
        """Force reload of data."""
        with self._lock:
            self._loaded = False
            self._data = None

        self._ensure_loaded()


class LazyList(Generic[T]):
    """
    A list that loads its contents lazily.

    Data is loaded on first access to any list operation.

    Usage:
        # Create with loader function
        comments = LazyList(lambda: fetch_comments("ISSUE-123"))

        # Data loaded on first access
        first_comment = comments[0]

        # Or iterate
        for comment in comments:
            print(comment)
    """

    def __init__(
        self,
        loader: Callable[[], list[T]] | None = None,
        initial_data: list[T] | None = None,
    ):
        """
        Initialize lazy list.

        Args:
            loader: Function to load data when needed
            initial_data: Pre-loaded data (skips lazy loading)
        """
        self._loader = loader
        self._data: list[T] | None = initial_data
        self._loaded = initial_data is not None
        self._lock = threading.Lock()

    def _ensure_loaded(self) -> list[T]:
        """Load data if not already loaded."""
        if self._loaded and self._data is not None:
            return self._data

        with self._lock:
            if self._loaded and self._data is not None:
                return self._data

            if self._loader is not None:
                self._data = self._loader()
            else:
                self._data = []

            self._loaded = True
            return self._data

    @property
    def is_loaded(self) -> bool:
        """Check if data has been loaded."""
        return self._loaded

    def reload(self) -> None:
        """Force reload of data."""
        with self._lock:
            self._loaded = False
            self._data = None
        self._ensure_loaded()

    # List interface methods

    def __getitem__(self, index: int | slice) -> T | list[T]:
        return self._ensure_loaded()[index]  # type: ignore[return-value]

    def __setitem__(self, index: int, value: T) -> None:
        self._ensure_loaded()[index] = value

    def __delitem__(self, index: int) -> None:
        del self._ensure_loaded()[index]

    def __len__(self) -> int:
        return len(self._ensure_loaded())

    def __iter__(self) -> Iterator[T]:
        return iter(self._ensure_loaded())

    def __contains__(self, item: Any) -> bool:
        return item in self._ensure_loaded()

    def __bool__(self) -> bool:
        return bool(self._ensure_loaded())

    def __repr__(self) -> str:
        if self._loaded:
            return f"LazyList({self._data!r})"
        return "LazyList(<not loaded>)"

    def append(self, item: T) -> None:
        self._ensure_loaded().append(item)

    def extend(self, items: list[T]) -> None:
        self._ensure_loaded().extend(items)

    def insert(self, index: int, item: T) -> None:
        self._ensure_loaded().insert(index, item)

    def remove(self, item: T) -> None:
        self._ensure_loaded().remove(item)

    def pop(self, index: int = -1) -> T:
        return self._ensure_loaded().pop(index)

    def clear(self) -> None:
        self._ensure_loaded().clear()

    def index(self, item: T, start: int = 0, stop: int | None = None) -> int:
        data = self._ensure_loaded()
        if stop is None:
            return data.index(item, start)
        return data.index(item, start, stop)

    def count(self, item: T) -> int:
        return self._ensure_loaded().count(item)

    def sort(self, *, key: Callable[[T], Any] | None = None, reverse: bool = False) -> None:
        self._ensure_loaded().sort(key=key, reverse=reverse)  # type: ignore[arg-type]

    def reverse(self) -> None:
        self._ensure_loaded().reverse()

    def copy(self) -> list[T]:
        return self._ensure_loaded().copy()

    def to_list(self) -> list[T]:
        """Convert to regular list."""
        return self._ensure_loaded().copy()


class LazyDict(Generic[K, V]):
    """
    A dict that loads its contents lazily.

    Data is loaded on first access to any dict operation.

    Usage:
        # Create with loader function
        metadata = LazyDict(lambda: fetch_metadata("ISSUE-123"))

        # Data loaded on first access
        value = metadata["key"]

        # Or iterate
        for key, value in metadata.items():
            print(key, value)
    """

    def __init__(
        self,
        loader: Callable[[], dict[K, V]] | None = None,
        initial_data: dict[K, V] | None = None,
    ):
        """
        Initialize lazy dict.

        Args:
            loader: Function to load data when needed
            initial_data: Pre-loaded data (skips lazy loading)
        """
        self._loader = loader
        self._data: dict[K, V] | None = initial_data
        self._loaded = initial_data is not None
        self._lock = threading.Lock()

    def _ensure_loaded(self) -> dict[K, V]:
        """Load data if not already loaded."""
        if self._loaded and self._data is not None:
            return self._data

        with self._lock:
            if self._loaded and self._data is not None:
                return self._data

            if self._loader is not None:
                self._data = self._loader()
            else:
                self._data = {}

            self._loaded = True
            return self._data

    @property
    def is_loaded(self) -> bool:
        """Check if data has been loaded."""
        return self._loaded

    def reload(self) -> None:
        """Force reload of data."""
        with self._lock:
            self._loaded = False
            self._data = None
        self._ensure_loaded()

    # Dict interface methods

    def __getitem__(self, key: K) -> V:
        return self._ensure_loaded()[key]

    def __setitem__(self, key: K, value: V) -> None:
        self._ensure_loaded()[key] = value

    def __delitem__(self, key: K) -> None:
        del self._ensure_loaded()[key]

    def __len__(self) -> int:
        return len(self._ensure_loaded())

    def __iter__(self) -> Iterator[K]:
        return iter(self._ensure_loaded())

    def __contains__(self, key: Any) -> bool:
        return key in self._ensure_loaded()

    def __bool__(self) -> bool:
        return bool(self._ensure_loaded())

    def __repr__(self) -> str:
        if self._loaded:
            return f"LazyDict({self._data!r})"
        return "LazyDict(<not loaded>)"

    def get(self, key: K, default: V | None = None) -> V | None:
        return self._ensure_loaded().get(key, default)

    def keys(self) -> Any:
        return self._ensure_loaded().keys()

    def values(self) -> Any:
        return self._ensure_loaded().values()

    def items(self) -> Any:
        return self._ensure_loaded().items()

    def pop(self, key: K, *args: V) -> V:
        return self._ensure_loaded().pop(key, *args)  # type: ignore[arg-type]

    def update(self, other: dict[K, V]) -> None:
        self._ensure_loaded().update(other)

    def clear(self) -> None:
        self._ensure_loaded().clear()

    def setdefault(self, key: K, default: V) -> V:
        return self._ensure_loaded().setdefault(key, default)

    def to_dict(self) -> dict[K, V]:
        """Convert to regular dict."""
        return self._ensure_loaded().copy()


class PaginatedCollection(Generic[T]):
    """
    A collection that loads data in pages.

    Fetches additional pages as needed when iterating or accessing indices.

    Usage:
        # Create with page loader
        issues = PaginatedCollection(
            page_loader=lambda offset, limit: fetch_issues(offset, limit),
            page_size=50,
            total_count=500  # Optional, can be discovered
        )

        # Iterate (pages loaded on demand)
        for issue in issues:
            print(issue)

        # Random access (pages loaded as needed)
        issue_100 = issues[100]
    """

    def __init__(
        self,
        page_loader: Callable[[int, int], list[T]],
        page_size: int = 50,
        total_count: int | None = None,
    ):
        """
        Initialize paginated collection.

        Args:
            page_loader: Function(offset, limit) -> list[T]
            page_size: Number of items per page
            total_count: Total item count (None = discover)
        """
        self._page_loader = page_loader
        self._page_size = page_size
        self._total_count = total_count
        self._pages: dict[int, list[T]] = {}
        self._lock = threading.Lock()
        self._exhausted = False

    def _load_page(self, page_num: int) -> list[T]:
        """Load a specific page."""
        with self._lock:
            if page_num in self._pages:
                return self._pages[page_num]

            offset = page_num * self._page_size
            items = self._page_loader(offset, self._page_size)

            self._pages[page_num] = items

            # Detect if we've reached the end
            if len(items) < self._page_size:
                self._exhausted = True
                if self._total_count is None:
                    self._total_count = offset + len(items)

            return items

    def _get_page_for_index(self, index: int) -> tuple[int, int]:
        """Get page number and offset within page for an index."""
        page_num = index // self._page_size
        offset = index % self._page_size
        return page_num, offset

    def __getitem__(self, index: int) -> T:
        if index < 0:
            # Convert negative index
            if self._total_count is not None:
                index = self._total_count + index
            else:
                # Need to load all to get length
                self._load_all()
                if self._total_count is not None:
                    index = self._total_count + index
                else:
                    raise IndexError("list index out of range")

        page_num, offset = self._get_page_for_index(index)
        page = self._load_page(page_num)

        if offset >= len(page):
            raise IndexError("list index out of range")

        return page[offset]

    def __len__(self) -> int:
        if self._total_count is not None:
            return self._total_count

        # Need to load all to determine length
        self._load_all()
        return self._total_count or 0

    def __iter__(self) -> Iterator[T]:
        page_num = 0
        while True:
            page = self._load_page(page_num)
            if not page:
                break

            yield from page

            if len(page) < self._page_size:
                break

            page_num += 1

    def __bool__(self) -> bool:
        # Just check first page
        page = self._load_page(0)
        return bool(page)

    def __repr__(self) -> str:
        loaded = len(self._pages)
        total = self._total_count or "?"
        return f"PaginatedCollection(loaded={loaded} pages, total={total})"

    def _load_all(self) -> None:
        """Load all remaining pages."""
        page_num = 0
        while not self._exhausted:
            page = self._load_page(page_num)
            if len(page) < self._page_size:
                break
            page_num += 1

    @property
    def loaded_count(self) -> int:
        """Number of items currently loaded."""
        return sum(len(p) for p in self._pages.values())

    @property
    def page_count(self) -> int:
        """Number of pages currently loaded."""
        return len(self._pages)

    def to_list(self) -> list[T]:
        """Convert to regular list (loads all pages)."""
        return list(self)
