"""
Tenant-Aware Cache - Cache management with tenant isolation.

Extends the caching system to support per-tenant cache storage
with isolation and shared cache options.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

from spectra.core.tenant import (
    IsolationLevel,
    TenantManager,
    get_current_tenant,
    get_tenant_manager,
)


if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


T = TypeVar("T")


# =============================================================================
# Tenant Cache Entry
# =============================================================================


@dataclass
class CacheEntry:
    """
    A cached value with metadata.

    Attributes:
        key: Cache key
        value: Cached value
        tenant_id: Tenant that owns this entry
        created_at: When entry was created
        expires_at: When entry expires (ISO format)
        hits: Number of cache hits
        tags: Optional tags for grouping/invalidation
    """

    key: str
    value: Any
    tenant_id: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    expires_at: str | None = None
    hits: int = 0
    tags: list[str] = field(default_factory=list)

    def is_expired(self) -> bool:
        """Check if entry is expired."""
        if not self.expires_at:
            return False
        return datetime.fromisoformat(self.expires_at) < datetime.now()

    def touch(self) -> None:
        """Record a cache hit."""
        self.hits += 1

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "key": self.key,
            "value": self.value,
            "tenant_id": self.tenant_id,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "hits": self.hits,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CacheEntry:
        """Create from dictionary."""
        return cls(
            key=data["key"],
            value=data["value"],
            tenant_id=data["tenant_id"],
            created_at=data.get("created_at", datetime.now().isoformat()),
            expires_at=data.get("expires_at"),
            hits=data.get("hits", 0),
            tags=data.get("tags", []),
        )


# =============================================================================
# Tenant Cache Store
# =============================================================================


class TenantCacheStore:
    """
    File-based cache store with tenant isolation.

    Each tenant has its own cache directory. Cache entries
    are stored as individual JSON files for efficient access.
    """

    def __init__(
        self,
        cache_dir: Path | None = None,
        tenant_manager: TenantManager | None = None,
        tenant_id: str | None = None,
        default_ttl: float = 300.0,  # 5 minutes
        max_entries: int = 1000,
    ):
        """
        Initialize the tenant cache store.

        Args:
            cache_dir: Explicit cache directory
            tenant_manager: Tenant manager instance
            tenant_id: Explicit tenant ID
            default_ttl: Default TTL in seconds
            max_entries: Maximum cache entries
        """
        self._tenant_manager = tenant_manager
        self._explicit_tenant_id = tenant_id
        self._explicit_cache_dir = cache_dir
        self._default_ttl = default_ttl
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._memory_cache: dict[str, CacheEntry] = {}

        # Ensure cache directory exists
        self._ensure_cache_dir()

    def _ensure_cache_dir(self) -> None:
        """Ensure cache directory exists."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @property
    def cache_dir(self) -> Path:
        """Get the cache directory."""
        if self._explicit_cache_dir:
            return self._explicit_cache_dir

        manager = self._tenant_manager or get_tenant_manager()
        tenant_id = self._resolve_tenant_id()

        # Check isolation level
        tenant = manager.registry.get(tenant_id)
        if tenant and tenant.isolation_level == IsolationLevel.SHARED_CACHE:
            # Use shared cache directory
            return manager.base_dir / "cache" / "shared"

        # Use tenant-specific cache
        paths = manager.registry.get_paths(tenant_id)
        return paths.cache_dir

    @property
    def tenant_id(self) -> str:
        """Get the tenant ID."""
        return self._resolve_tenant_id()

    def _resolve_tenant_id(self) -> str:
        """Resolve the current tenant ID."""
        if self._explicit_tenant_id:
            return self._explicit_tenant_id

        current = get_current_tenant()
        if current:
            return current.id

        manager = self._tenant_manager or get_tenant_manager()
        return manager.current_tenant.id

    def _key_to_filename(self, key: str) -> str:
        """Convert cache key to filename."""
        # Hash the key to create a safe filename
        key_hash = hashlib.sha256(key.encode()).hexdigest()[:16]
        # Also include a sanitized version of the key for debugging
        safe_key = "".join(c if c.isalnum() else "_" for c in key)[:32]
        return f"{safe_key}_{key_hash}.json"

    def _get_cache_path(self, key: str) -> Path:
        """Get path to cache file for a key."""
        return self.cache_dir / self._key_to_filename(key)

    def get(self, key: str, default: T | None = None) -> T | Any | None:
        """
        Get a cached value.

        Args:
            key: Cache key
            default: Default value if not found

        Returns:
            Cached value or default
        """
        with self._lock:
            # Check memory cache first
            if key in self._memory_cache:
                entry = self._memory_cache[key]
                if not entry.is_expired():
                    entry.touch()
                    return entry.value
                del self._memory_cache[key]

            # Check file cache
            cache_path = self._get_cache_path(key)
            if cache_path.exists():
                try:
                    with open(cache_path) as f:
                        data = json.load(f)
                    entry = CacheEntry.from_dict(data)

                    if entry.is_expired():
                        cache_path.unlink()
                        return default

                    entry.touch()
                    self._memory_cache[key] = entry
                    return entry.value

                except (json.JSONDecodeError, KeyError):
                    cache_path.unlink()

            return default

    def set(
        self,
        key: str,
        value: Any,
        ttl: float | None = None,
        tags: list[str] | None = None,
    ) -> None:
        """
        Set a cached value.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (None for default)
            tags: Optional tags for grouping
        """
        ttl = ttl if ttl is not None else self._default_ttl

        with self._lock:
            # Calculate expiration
            from datetime import timedelta

            expires_at = (datetime.now() + timedelta(seconds=ttl)).isoformat() if ttl > 0 else None

            entry = CacheEntry(
                key=key,
                value=value,
                tenant_id=self.tenant_id,
                expires_at=expires_at,
                tags=tags or [],
            )

            # Store in memory
            self._memory_cache[key] = entry

            # Store to disk
            cache_path = self._get_cache_path(key)
            try:
                with open(cache_path, "w") as f:
                    json.dump(entry.to_dict(), f, indent=2)
            except Exception as e:
                logger.warning(f"Failed to write cache file {cache_path}: {e}")

            # Enforce max entries
            self._enforce_limits()

    def delete(self, key: str) -> bool:
        """
        Delete a cached value.

        Args:
            key: Cache key

        Returns:
            True if deleted
        """
        with self._lock:
            deleted = False

            # Remove from memory
            if key in self._memory_cache:
                del self._memory_cache[key]
                deleted = True

            # Remove from disk
            cache_path = self._get_cache_path(key)
            if cache_path.exists():
                cache_path.unlink()
                deleted = True

            return deleted

    def clear(self) -> int:
        """
        Clear all cached values for this tenant.

        Returns:
            Number of entries cleared
        """
        with self._lock:
            count = len(self._memory_cache)
            self._memory_cache.clear()

            # Clear disk cache
            if self.cache_dir.exists():
                for cache_file in self.cache_dir.glob("*.json"):
                    try:
                        cache_file.unlink()
                        count += 1
                    except Exception:
                        pass

            return count

    def invalidate_by_tag(self, tag: str) -> int:
        """
        Invalidate all entries with a specific tag.

        Args:
            tag: Tag to match

        Returns:
            Number of entries invalidated
        """
        with self._lock:
            count = 0

            # Check memory cache
            keys_to_remove = [k for k, v in self._memory_cache.items() if tag in v.tags]
            for key in keys_to_remove:
                del self._memory_cache[key]
                count += 1

            # Check disk cache
            for cache_file in self.cache_dir.glob("*.json"):
                try:
                    with open(cache_file) as f:
                        data = json.load(f)
                    if tag in data.get("tags", []):
                        cache_file.unlink()
                        count += 1
                except Exception:
                    pass

            return count

    def get_stats(self) -> dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        with self._lock:
            memory_count = len(self._memory_cache)
            disk_count = len(list(self.cache_dir.glob("*.json")))

            # Calculate total hits
            total_hits = sum(e.hits for e in self._memory_cache.values())

            # Calculate disk usage
            disk_usage = sum(f.stat().st_size for f in self.cache_dir.glob("*.json"))

            return {
                "tenant_id": self.tenant_id,
                "memory_entries": memory_count,
                "disk_entries": disk_count,
                "total_hits": total_hits,
                "disk_usage_bytes": disk_usage,
                "max_entries": self._max_entries,
                "default_ttl": self._default_ttl,
            }

    def _enforce_limits(self) -> None:
        """Enforce max entries limit by evicting LRU entries."""
        # Check total entries
        disk_files = list(self.cache_dir.glob("*.json"))
        total = len(disk_files)

        if total <= self._max_entries:
            return

        # Sort by modification time (oldest first)
        disk_files.sort(key=lambda f: f.stat().st_mtime)

        # Remove oldest entries
        to_remove = total - self._max_entries
        for cache_file in disk_files[:to_remove]:
            with contextlib.suppress(Exception):
                cache_file.unlink()

        # Clear memory cache to sync
        self._memory_cache.clear()


# =============================================================================
# Cross-Tenant Cache Manager
# =============================================================================


class CrossTenantCacheManager:
    """
    Manage cache across multiple tenants.

    Useful for:
    - Administrative tasks
    - Cache warming
    - Global invalidation
    """

    def __init__(self, tenant_manager: TenantManager | None = None):
        """
        Initialize the cross-tenant cache manager.

        Args:
            tenant_manager: Tenant manager instance
        """
        self.manager = tenant_manager or get_tenant_manager()

    def clear_all(self, include_shared: bool = True) -> dict[str, int]:
        """
        Clear cache for all tenants.

        Args:
            include_shared: Also clear shared cache

        Returns:
            Dictionary of tenant_id -> cleared count
        """
        results = {}

        for tenant in self.manager.list_tenants():
            try:
                store = TenantCacheStore(
                    tenant_manager=self.manager,
                    tenant_id=tenant.id,
                )
                results[tenant.id] = store.clear()
            except Exception as e:
                logger.warning(f"Failed to clear cache for '{tenant.id}': {e}")
                results[tenant.id] = 0

        # Clear shared cache if requested
        if include_shared:
            shared_dir = self.manager.base_dir / "cache" / "shared"
            if shared_dir.exists():
                count = 0
                for cache_file in shared_dir.glob("*.json"):
                    try:
                        cache_file.unlink()
                        count += 1
                    except Exception:
                        pass
                results["__shared__"] = count

        return results

    def invalidate_by_tag_all(self, tag: str) -> dict[str, int]:
        """
        Invalidate entries by tag across all tenants.

        Args:
            tag: Tag to match

        Returns:
            Dictionary of tenant_id -> invalidated count
        """
        results = {}

        for tenant in self.manager.list_tenants():
            try:
                store = TenantCacheStore(
                    tenant_manager=self.manager,
                    tenant_id=tenant.id,
                )
                results[tenant.id] = store.invalidate_by_tag(tag)
            except Exception as e:
                logger.warning(f"Failed to invalidate cache for '{tenant.id}': {e}")
                results[tenant.id] = 0

        return results

    def get_all_stats(self) -> list[dict[str, Any]]:
        """
        Get cache statistics for all tenants.

        Returns:
            List of cache stats per tenant
        """
        stats = []

        for tenant in self.manager.list_tenants():
            try:
                store = TenantCacheStore(
                    tenant_manager=self.manager,
                    tenant_id=tenant.id,
                )
                tenant_stats = store.get_stats()
                tenant_stats["tenant_name"] = tenant.name
                stats.append(tenant_stats)
            except Exception as e:
                logger.warning(f"Failed to get cache stats for '{tenant.id}': {e}")

        return stats

    def get_total_usage(self) -> dict[str, Any]:
        """
        Get total cache usage across all tenants.

        Returns:
            Dictionary with total usage stats
        """
        all_stats = self.get_all_stats()

        return {
            "total_tenants": len(all_stats),
            "total_memory_entries": sum(s["memory_entries"] for s in all_stats),
            "total_disk_entries": sum(s["disk_entries"] for s in all_stats),
            "total_disk_usage_bytes": sum(s["disk_usage_bytes"] for s in all_stats),
            "total_hits": sum(s["total_hits"] for s in all_stats),
        }


# =============================================================================
# Cache Migration
# =============================================================================


class TenantCacheMigrator:
    """
    Migrate cache between tenants.

    Supports:
    - Copying cache entries
    - Moving cache entries
    - Bulk operations
    """

    def __init__(self, tenant_manager: TenantManager | None = None):
        """
        Initialize the cache migrator.

        Args:
            tenant_manager: Tenant manager instance
        """
        self.manager = tenant_manager or get_tenant_manager()

    def copy_cache(
        self,
        source_tenant_id: str,
        target_tenant_id: str,
        tags: list[str] | None = None,
    ) -> int:
        """
        Copy cache from one tenant to another.

        Args:
            source_tenant_id: Source tenant
            target_tenant_id: Target tenant
            tags: Optional tags to filter by

        Returns:
            Number of entries copied
        """
        source_store = TenantCacheStore(
            tenant_manager=self.manager,
            tenant_id=source_tenant_id,
        )
        target_store = TenantCacheStore(
            tenant_manager=self.manager,
            tenant_id=target_tenant_id,
        )

        count = 0

        for cache_file in source_store.cache_dir.glob("*.json"):
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                entry = CacheEntry.from_dict(data)

                # Filter by tags if specified
                if tags and not any(t in entry.tags for t in tags):
                    continue

                # Skip expired entries
                if entry.is_expired():
                    continue

                # Copy to target
                target_store.set(
                    key=entry.key,
                    value=entry.value,
                    tags=entry.tags,
                )
                count += 1

            except Exception as e:
                logger.warning(f"Failed to copy cache entry: {e}")

        return count


# =============================================================================
# Factory Functions
# =============================================================================


def create_tenant_cache_store(
    tenant_id: str | None = None,
    cache_dir: Path | None = None,
    **kwargs: Any,
) -> TenantCacheStore:
    """
    Create a tenant-aware cache store.

    Args:
        tenant_id: Explicit tenant ID
        cache_dir: Explicit cache directory
        **kwargs: Additional arguments for TenantCacheStore

    Returns:
        Configured TenantCacheStore
    """
    return TenantCacheStore(
        cache_dir=cache_dir,
        tenant_id=tenant_id,
        **kwargs,
    )


def get_tenant_cache_dir(tenant_id: str | None = None) -> Path:
    """
    Get the cache directory for a tenant.

    Args:
        tenant_id: Tenant ID (None for current)

    Returns:
        Path to cache directory
    """
    manager = get_tenant_manager()
    paths = manager.registry.get_paths(tenant_id) if tenant_id else manager.current_paths

    return paths.cache_dir


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "CacheEntry",
    "CrossTenantCacheManager",
    "TenantCacheMigrator",
    "TenantCacheStore",
    "create_tenant_cache_store",
    "get_tenant_cache_dir",
]
