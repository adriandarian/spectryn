"""
Usage Analytics - Opt-in anonymous usage statistics.

Provides privacy-respecting analytics for understanding usage patterns.
All analytics are:
- Strictly opt-in (disabled by default)
- Anonymous (no PII, no project names, no issue keys)
- Transparent (users can see exactly what is collected)
- Local-first (stored locally, optionally sent to remote)

Data Collected (when enabled):
- spectra version
- Python version
- OS type (not hostname)
- Feature usage counts (which commands are used)
- Sync statistics (counts only, not content)
- Error types (not messages or stack traces)

Usage:
    # Enable analytics
    spectra --analytics --input EPIC.md --epic PROJ-123

    # Show what would be collected
    spectra --analytics-show

    # Clear local analytics data
    spectra --analytics-clear
"""

from __future__ import annotations

import json
import logging
import platform
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)

# Version
ANALYTICS_VERSION = "1.0"
APP_VERSION = "2.0.0"


@dataclass
class UsageEvent:
    """A single usage event."""

    event_type: str  # e.g., "sync", "validate", "init"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Counts (no content)
    stories_count: int = 0
    subtasks_count: int = 0

    # Outcome
    success: bool = True
    error_type: str | None = None  # e.g., "AuthenticationError" (not message)

    # Duration
    duration_seconds: float = 0.0

    # Features used
    features: list[str] = field(default_factory=list)  # e.g., ["dry_run", "incremental"]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "stories_count": self.stories_count,
            "subtasks_count": self.subtasks_count,
            "success": self.success,
            "error_type": self.error_type,
            "duration_seconds": round(self.duration_seconds, 2),
            "features": self.features,
        }


@dataclass
class AnalyticsData:
    """Aggregated analytics data."""

    # Anonymous installation ID (random UUID, not tied to user)
    installation_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # Environment (anonymous)
    analytics_version: str = ANALYTICS_VERSION
    app_version: str = APP_VERSION
    python_version: str = field(
        default_factory=lambda: f"{sys.version_info.major}.{sys.version_info.minor}"
    )
    os_type: str = field(default_factory=lambda: platform.system())

    # Aggregated stats
    total_syncs: int = 0
    successful_syncs: int = 0
    failed_syncs: int = 0
    total_stories_synced: int = 0

    # Feature usage counts
    feature_usage: dict[str, int] = field(default_factory=dict)

    # Command usage counts
    command_usage: dict[str, int] = field(default_factory=dict)

    # Error type counts (not messages)
    error_counts: dict[str, int] = field(default_factory=dict)

    # Time tracking
    first_use: str | None = None
    last_use: str | None = None

    # Recent events (last 100)
    recent_events: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "installation_id": self.installation_id,
            "analytics_version": self.analytics_version,
            "app_version": self.app_version,
            "python_version": self.python_version,
            "os_type": self.os_type,
            "stats": {
                "total_syncs": self.total_syncs,
                "successful_syncs": self.successful_syncs,
                "failed_syncs": self.failed_syncs,
                "total_stories_synced": self.total_stories_synced,
            },
            "feature_usage": self.feature_usage,
            "command_usage": self.command_usage,
            "error_counts": self.error_counts,
            "first_use": self.first_use,
            "last_use": self.last_use,
        }

    def to_display_dict(self) -> dict[str, Any]:
        """Convert to user-friendly display format."""
        return {
            "What we collect": {
                "installation_id": f"{self.installation_id[:8]}... (random, not tied to you)",
                "app_version": self.app_version,
                "python_version": self.python_version,
                "os_type": self.os_type,
            },
            "Usage statistics": {
                "total_syncs": self.total_syncs,
                "successful_syncs": self.successful_syncs,
                "failed_syncs": self.failed_syncs,
                "total_stories_synced": self.total_stories_synced,
            },
            "Feature usage": self.feature_usage or {"(none recorded)": 0},
            "Command usage": self.command_usage or {"(none recorded)": 0},
            "Error types": self.error_counts or {"(none recorded)": 0},
        }


@dataclass
class AnalyticsConfig:
    """Configuration for usage analytics."""

    enabled: bool = False

    # Storage
    data_dir: str | None = None  # Defaults to ~/.spectra/analytics

    # Remote reporting (future feature)
    remote_endpoint: str | None = None
    remote_enabled: bool = False

    @property
    def storage_path(self) -> Path:
        """Get the analytics storage path."""
        if self.data_dir:
            return Path(self.data_dir)

        # Default to ~/.spectra/analytics
        home = Path.home()
        return home / ".spectra" / "analytics"


class AnalyticsManager:
    """
    Manages usage analytics collection and storage.

    All analytics are opt-in and anonymous.
    """

    _instance: AnalyticsManager | None = None

    def __init__(self, config: AnalyticsConfig):
        """
        Initialize the analytics manager.

        Args:
            config: Analytics configuration.
        """
        self.config = config
        self._data: AnalyticsData | None = None
        self._initialized = False

    @classmethod
    def get_instance(cls) -> AnalyticsManager | None:
        """Get the singleton analytics manager instance."""
        return cls._instance

    @classmethod
    def configure(cls, config: AnalyticsConfig) -> AnalyticsManager:
        """
        Configure the analytics manager.

        Args:
            config: Analytics configuration.

        Returns:
            The configured manager instance.
        """
        cls._instance = cls(config)
        if config.enabled:
            cls._instance.initialize()
        return cls._instance

    def initialize(self) -> bool:
        """
        Initialize analytics (load existing data or create new).

        Returns:
            True if initialization succeeded.
        """
        if self._initialized:
            return True

        if not self.config.enabled:
            logger.debug("Analytics disabled")
            return False

        try:
            self._load_or_create_data()
            self._initialized = True
            logger.debug(f"Analytics initialized: {self.config.storage_path}")
            return True
        except Exception as e:
            logger.warning(f"Failed to initialize analytics: {e}")
            return False

    def _load_or_create_data(self) -> None:
        """Load existing analytics data or create new."""
        data_file = self.config.storage_path / "usage.json"

        if data_file.exists():
            try:
                with open(data_file) as f:
                    raw = json.load(f)

                self._data = AnalyticsData(
                    installation_id=raw.get("installation_id", str(uuid.uuid4())),
                    app_version=APP_VERSION,
                    total_syncs=raw.get("stats", {}).get("total_syncs", 0),
                    successful_syncs=raw.get("stats", {}).get("successful_syncs", 0),
                    failed_syncs=raw.get("stats", {}).get("failed_syncs", 0),
                    total_stories_synced=raw.get("stats", {}).get("total_stories_synced", 0),
                    feature_usage=raw.get("feature_usage", {}),
                    command_usage=raw.get("command_usage", {}),
                    error_counts=raw.get("error_counts", {}),
                    first_use=raw.get("first_use"),
                    last_use=raw.get("last_use"),
                    recent_events=raw.get("recent_events", []),
                )
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Corrupted analytics data, starting fresh: {e}")
                self._data = AnalyticsData()
        else:
            self._data = AnalyticsData()
            self._data.first_use = datetime.now(timezone.utc).isoformat()

    def _save_data(self) -> None:
        """Save analytics data to disk."""
        if not self._data:
            return

        try:
            # Ensure directory exists
            self.config.storage_path.mkdir(parents=True, exist_ok=True)

            data_file = self.config.storage_path / "usage.json"

            # Prepare data for saving
            save_data = self._data.to_dict()
            save_data["recent_events"] = self._data.recent_events[-100:]  # Keep last 100

            with open(data_file, "w") as f:
                json.dump(save_data, f, indent=2)

        except Exception as e:
            logger.warning(f"Failed to save analytics: {e}")

    def record_event(self, event: UsageEvent) -> None:
        """
        Record a usage event.

        Args:
            event: The usage event to record.
        """
        if not self.config.enabled or not self._data:
            return

        # Update aggregated stats
        if event.event_type == "sync":
            self._data.total_syncs += 1
            if event.success:
                self._data.successful_syncs += 1
            else:
                self._data.failed_syncs += 1
            self._data.total_stories_synced += event.stories_count

        # Update command usage
        cmd = event.event_type
        self._data.command_usage[cmd] = self._data.command_usage.get(cmd, 0) + 1

        # Update feature usage
        for feature in event.features:
            self._data.feature_usage[feature] = self._data.feature_usage.get(feature, 0) + 1

        # Update error counts
        if event.error_type:
            self._data.error_counts[event.error_type] = (
                self._data.error_counts.get(event.error_type, 0) + 1
            )

        # Update timestamps
        self._data.last_use = event.timestamp

        # Add to recent events
        self._data.recent_events.append(event.to_dict())
        if len(self._data.recent_events) > 100:
            self._data.recent_events = self._data.recent_events[-100:]

        # Save to disk
        self._save_data()

    def record_sync(
        self,
        success: bool,
        stories_count: int = 0,
        subtasks_count: int = 0,
        duration_seconds: float = 0.0,
        features: list[str] | None = None,
        error_type: str | None = None,
    ) -> None:
        """
        Record a sync operation.

        Args:
            success: Whether the sync was successful.
            stories_count: Number of stories synced.
            subtasks_count: Number of subtasks synced.
            duration_seconds: Duration of the sync.
            features: Features used (e.g., ["dry_run", "incremental"]).
            error_type: Type of error if failed (e.g., "AuthenticationError").
        """
        event = UsageEvent(
            event_type="sync",
            success=success,
            stories_count=stories_count,
            subtasks_count=subtasks_count,
            duration_seconds=duration_seconds,
            features=features or [],
            error_type=error_type,
        )
        self.record_event(event)

    def record_command(self, command: str, features: list[str] | None = None) -> None:
        """
        Record a command usage.

        Args:
            command: Command name (e.g., "validate", "init", "generate").
            features: Features used.
        """
        event = UsageEvent(
            event_type=command,
            features=features or [],
        )
        self.record_event(event)

    def get_data(self) -> AnalyticsData | None:
        """
        Get the current analytics data.

        Returns:
            Current analytics data or None if not initialized.
        """
        return self._data

    def get_display_data(self) -> dict[str, Any]:
        """
        Get analytics data in a user-friendly format.

        Returns:
            Dictionary showing what is collected.
        """
        if not self._data:
            return {"status": "Analytics not enabled"}

        return self._data.to_display_dict()

    def clear_data(self) -> bool:
        """
        Clear all analytics data.

        Returns:
            True if cleared successfully.
        """
        try:
            data_file = self.config.storage_path / "usage.json"
            if data_file.exists():
                data_file.unlink()

            # Reset in-memory data
            self._data = AnalyticsData()
            self._data.first_use = datetime.now(timezone.utc).isoformat()

            logger.info("Analytics data cleared")
            return True
        except Exception as e:
            logger.error(f"Failed to clear analytics: {e}")
            return False

    def is_enabled(self) -> bool:
        """Check if analytics is enabled."""
        return self.config.enabled and self._initialized


def configure_analytics(
    enabled: bool = False,
    data_dir: str | None = None,
) -> AnalyticsManager:
    """
    Configure usage analytics.

    Args:
        enabled: Whether analytics is enabled (opt-in).
        data_dir: Directory to store analytics data.

    Returns:
        The configured analytics manager.
    """
    config = AnalyticsConfig(
        enabled=enabled,
        data_dir=data_dir,
    )
    return AnalyticsManager.configure(config)


def get_analytics() -> AnalyticsManager | None:
    """Get the global analytics manager instance."""
    return AnalyticsManager.get_instance()


def show_analytics_info() -> str:
    """
    Get a human-readable description of what analytics collects.

    Returns:
        Description string.
    """
    return """
spectra Usage Analytics (Opt-In)
================================

When you enable analytics with --analytics, we collect ONLY:

✓ Anonymous installation ID (random UUID, not tied to you)
✓ spectra and Python versions
✓ Operating system type (e.g., "Linux", not hostname)
✓ Command usage counts (e.g., "sync: 10 times")
✓ Feature usage counts (e.g., "dry_run: 5 times")
✓ Sync statistics (counts only, not content)
✓ Error types (e.g., "AuthenticationError: 2", not messages)

We NEVER collect:
✗ Your name, email, or any personal information
✗ Project names, epic keys, or issue content
✗ Story titles, descriptions, or any text you write
✗ File paths or directory names
✗ IP addresses or location data
✗ Hostnames or machine identifiers

Data is stored locally at: ~/.spectra/analytics/usage.json

Commands:
  --analytics        Enable anonymous usage statistics
  --analytics-show   Show what data has been collected
  --analytics-clear  Delete all collected analytics data
""".strip()


def format_analytics_display(data: dict[str, Any]) -> str:
    """
    Format analytics data for display.

    Args:
        data: Analytics data dictionary.

    Returns:
        Formatted string.
    """
    lines = ["Analytics Data Collected", "=" * 40, ""]

    for section, content in data.items():
        lines.append(f"{section}:")
        if isinstance(content, dict):
            for key, value in content.items():
                lines.append(f"  {key}: {value}")
        else:
            lines.append(f"  {content}")
        lines.append("")

    return "\n".join(lines)
