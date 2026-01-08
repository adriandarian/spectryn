"""
File Cache - File-based persistent cache.

Stores cache entries as JSON files for persistence across restarts.
"""

from __future__ import annotations

import contextlib
import json
import logging
import time
from pathlib import Path
from typing import Any

from .backend import CacheBackend, CacheEntry, CacheStats


class FileCache(CacheBackend):
    """
    File-based persistent cache.

    Stores each cache entry as a JSON file in a directory.
    Useful for caching data that should persist across process restarts.

    Features:
    - Persistence across restarts
    - TTL support via expiration timestamps in files
    - Tag-based invalidation via metadata
    - Automatic cleanup of expired entries

    Example:
        >>> cache = FileCache(
        ...     cache_dir="~/.spectra/cache",
        ...     default_ttl=3600,  # 1 hour
        ... )
        >>> cache.set("issue:PROJ-123", issue_data)
    """

    def __init__(
        self,
        cache_dir: str | Path = "~/.spectra/cache",
        default_ttl: float | None = 3600.0,  # 1 hour default
        cleanup_on_start: bool = True,
    ):
        """
        Initialize the file cache.

        Args:
            cache_dir: Directory to store cache files
            default_ttl: Default TTL in seconds
            cleanup_on_start: Whether to clean expired entries on init
        """
        self.cache_dir = Path(cache_dir).expanduser()
        self.default_ttl = default_ttl
        self._stats = CacheStats()

        self.logger = logging.getLogger("FileCache")

        # Create cache directory
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Create subdirectories for organization
        (self.cache_dir / "entries").mkdir(exist_ok=True)
        (self.cache_dir / "tags").mkdir(exist_ok=True)

        if cleanup_on_start:
            self._cleanup_expired()

    def _key_to_path(self, key: str) -> Path:
        """Convert a cache key to a file path."""
        # Replace problematic characters
        safe_key = key.replace("/", "_").replace(":", "_")
        return self.cache_dir / "entries" / f"{safe_key}.json"

    def _tag_to_path(self, tag: str) -> Path:
        """Convert a tag to a file path."""
        safe_tag = tag.replace("/", "_").replace(":", "_")
        return self.cache_dir / "tags" / f"{safe_tag}.json"

    def get(self, key: str) -> Any | None:
        """Get a value from the cache."""
        path = self._key_to_path(key)

        if not path.exists():
            self._stats.record_miss()
            return None

        try:
            data = json.loads(path.read_text())
            entry = self._dict_to_entry(data)

            if entry.is_expired:
                self.delete(key)
                self._stats.record_expiration()
                self._stats.record_miss()
                return None

            entry.record_hit()
            self._stats.record_hit()

            # Update hit count in file
            data["hit_count"] = entry.hit_count
            path.write_text(json.dumps(data))

            return entry.value

        except (json.JSONDecodeError, KeyError) as e:
            self.logger.warning(f"Corrupt cache entry {key}: {e}")
            self.delete(key)
            self._stats.record_miss()
            return None

    def set(
        self,
        key: str,
        value: Any,
        ttl: float | None = None,
        tags: set[str] | None = None,
    ) -> None:
        """Set a value in the cache."""
        path = self._key_to_path(key)

        if ttl is None:
            ttl = self.default_ttl

        expires_at = None
        if ttl is not None:
            expires_at = time.time() + ttl

        entry_data = {
            "value": value,
            "created_at": time.time(),
            "expires_at": expires_at,
            "tags": list(tags) if tags else [],
            "hit_count": 0,
        }

        try:
            path.write_text(json.dumps(entry_data, default=str))

            # Update tag indexes
            if tags:
                for tag in tags:
                    self._add_key_to_tag(tag, key)

            self._stats.record_set()

        except (OSError, TypeError) as e:
            self.logger.error(f"Failed to cache {key}: {e}")

    def delete(self, key: str) -> bool:
        """Delete a key from the cache."""
        path = self._key_to_path(key)

        if not path.exists():
            return False

        try:
            # Read tags before deleting
            data = json.loads(path.read_text())
            tags = data.get("tags", [])

            # Remove from tag indexes
            for tag in tags:
                self._remove_key_from_tag(tag, key)

            path.unlink()
            self._stats.record_delete()
            return True

        except (json.JSONDecodeError, OSError) as e:
            self.logger.warning(f"Error deleting {key}: {e}")
            with contextlib.suppress(OSError):
                path.unlink()
            return False

    def exists(self, key: str) -> bool:
        """Check if a key exists and is not expired."""
        path = self._key_to_path(key)

        if not path.exists():
            return False

        try:
            data = json.loads(path.read_text())
            entry = self._dict_to_entry(data)

            if entry.is_expired:
                self.delete(key)
                return False

            return True

        except (json.JSONDecodeError, KeyError):
            return False

    def clear(self) -> int:
        """Clear all entries from the cache."""
        count = 0

        entries_dir = self.cache_dir / "entries"
        for path in entries_dir.glob("*.json"):
            try:
                path.unlink()
                count += 1
            except OSError:
                pass

        # Clear tag indexes
        tags_dir = self.cache_dir / "tags"
        for path in tags_dir.glob("*.json"):
            with contextlib.suppress(OSError):
                path.unlink()

        return count

    def invalidate_by_tag(self, tag: str) -> int:
        """Invalidate all entries with a given tag."""
        tag_path = self._tag_to_path(tag)

        if not tag_path.exists():
            return 0

        try:
            keys = json.loads(tag_path.read_text())
            count = 0

            for key in keys:
                if self.delete(key):
                    count += 1

            # Remove tag index
            with contextlib.suppress(OSError):
                tag_path.unlink()

            return count

        except (json.JSONDecodeError, OSError):
            return 0

    def get_stats(self) -> CacheStats:
        """Get cache statistics."""
        return self._stats

    @property
    def size(self) -> int:
        """Get the current number of entries in the cache."""
        entries_dir = self.cache_dir / "entries"
        return len(list(entries_dir.glob("*.json")))

    def _dict_to_entry(self, data: dict) -> CacheEntry:
        """Convert a dictionary to a CacheEntry."""
        return CacheEntry(
            value=data["value"],
            created_at=data.get("created_at", time.time()),
            expires_at=data.get("expires_at"),
            tags=set(data.get("tags", [])),
            hit_count=data.get("hit_count", 0),
        )

    def _add_key_to_tag(self, tag: str, key: str) -> None:
        """Add a key to a tag index."""
        tag_path = self._tag_to_path(tag)

        keys: list[str] = []
        if tag_path.exists():
            try:
                keys = json.loads(tag_path.read_text())
            except json.JSONDecodeError:
                keys = []

        if key not in keys:
            keys.append(key)
            tag_path.write_text(json.dumps(keys))

    def _remove_key_from_tag(self, tag: str, key: str) -> None:
        """Remove a key from a tag index."""
        tag_path = self._tag_to_path(tag)

        if not tag_path.exists():
            return

        try:
            keys = json.loads(tag_path.read_text())
            if key in keys:
                keys.remove(key)
                if keys:
                    tag_path.write_text(json.dumps(keys))
                else:
                    tag_path.unlink()
        except (json.JSONDecodeError, OSError):
            pass

    def _cleanup_expired(self) -> None:
        """Remove all expired entries."""
        entries_dir = self.cache_dir / "entries"
        expired_count = 0

        for path in entries_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text())
                entry = self._dict_to_entry(data)

                if entry.is_expired:
                    key = path.stem  # filename without extension
                    self.delete(key)
                    expired_count += 1

            except (json.JSONDecodeError, KeyError, OSError):
                # Remove corrupt entries
                try:
                    path.unlink()
                    expired_count += 1
                except OSError:
                    pass

        if expired_count > 0:
            self.logger.debug(f"Cleaned up {expired_count} expired/corrupt entries")
