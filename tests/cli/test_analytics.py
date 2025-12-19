"""
Tests for usage analytics (opt-in).

Tests analytics collection, storage, and privacy.
"""

import json

import pytest

from spectra.cli.analytics import (
    AnalyticsConfig,
    AnalyticsData,
    AnalyticsManager,
    UsageEvent,
    configure_analytics,
    format_analytics_display,
    get_analytics,
    show_analytics_info,
)


# =============================================================================
# UsageEvent Tests
# =============================================================================


class TestUsageEvent:
    """Tests for UsageEvent dataclass."""

    def test_default_values(self):
        """Test UsageEvent has sensible defaults."""
        event = UsageEvent(event_type="sync")

        assert event.event_type == "sync"
        assert event.stories_count == 0
        assert event.subtasks_count == 0
        assert event.success is True
        assert event.error_type is None
        assert event.duration_seconds == 0.0
        assert event.features == []
        assert event.timestamp is not None

    def test_custom_values(self):
        """Test UsageEvent with custom values."""
        event = UsageEvent(
            event_type="sync",
            stories_count=5,
            subtasks_count=10,
            success=False,
            error_type="AuthenticationError",
            duration_seconds=2.5,
            features=["dry_run", "incremental"],
        )

        assert event.stories_count == 5
        assert event.subtasks_count == 10
        assert event.success is False
        assert event.error_type == "AuthenticationError"
        assert event.duration_seconds == 2.5
        assert "dry_run" in event.features

    def test_to_dict(self):
        """Test UsageEvent.to_dict()."""
        event = UsageEvent(
            event_type="validate",
            stories_count=3,
            success=True,
            features=["strict"],
        )

        data = event.to_dict()

        assert data["event_type"] == "validate"
        assert data["stories_count"] == 3
        assert data["success"] is True
        assert "strict" in data["features"]


# =============================================================================
# AnalyticsData Tests
# =============================================================================


class TestAnalyticsData:
    """Tests for AnalyticsData dataclass."""

    def test_default_values(self):
        """Test AnalyticsData has sensible defaults."""
        data = AnalyticsData()

        assert data.installation_id is not None
        assert len(data.installation_id) == 36  # UUID format
        assert data.app_version == "2.0.0"
        assert data.python_version is not None
        assert data.os_type is not None
        assert data.total_syncs == 0
        assert data.feature_usage == {}
        assert data.command_usage == {}
        assert data.error_counts == {}

    def test_to_dict(self):
        """Test AnalyticsData.to_dict()."""
        data = AnalyticsData(
            total_syncs=10,
            successful_syncs=8,
            failed_syncs=2,
            feature_usage={"dry_run": 5},
            command_usage={"sync": 10},
        )

        result = data.to_dict()

        assert "installation_id" in result
        assert result["stats"]["total_syncs"] == 10
        assert result["stats"]["successful_syncs"] == 8
        assert result["feature_usage"]["dry_run"] == 5
        assert result["command_usage"]["sync"] == 10

    def test_to_display_dict(self):
        """Test AnalyticsData.to_display_dict()."""
        data = AnalyticsData(
            total_syncs=5,
            successful_syncs=4,
            failed_syncs=1,
        )

        display = data.to_display_dict()

        assert "What we collect" in display
        assert "Usage statistics" in display
        assert display["Usage statistics"]["total_syncs"] == 5

    def test_installation_id_is_unique(self):
        """Test each AnalyticsData gets a unique installation ID."""
        data1 = AnalyticsData()
        data2 = AnalyticsData()

        assert data1.installation_id != data2.installation_id


# =============================================================================
# AnalyticsConfig Tests
# =============================================================================


class TestAnalyticsConfig:
    """Tests for AnalyticsConfig dataclass."""

    def test_default_values(self):
        """Test AnalyticsConfig has sensible defaults."""
        config = AnalyticsConfig()

        assert config.enabled is False
        assert config.data_dir is None
        assert config.remote_endpoint is None
        assert config.remote_enabled is False

    def test_storage_path_default(self):
        """Test storage_path defaults to ~/.spectra/analytics."""
        config = AnalyticsConfig()

        path = config.storage_path
        assert ".spectra" in str(path)
        assert "analytics" in str(path)

    def test_storage_path_custom(self):
        """Test storage_path with custom data_dir."""
        from pathlib import PurePosixPath

        config = AnalyticsConfig(data_dir="/custom/path")

        path = config.storage_path
        # Use PurePosixPath for cross-platform comparison
        assert PurePosixPath(path.as_posix()) == PurePosixPath("/custom/path")


# =============================================================================
# AnalyticsManager Tests
# =============================================================================


class TestAnalyticsManager:
    """Tests for AnalyticsManager class."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset the singleton instance before each test."""
        AnalyticsManager._instance = None
        yield
        AnalyticsManager._instance = None

    def test_get_instance_none_initially(self):
        """Test get_instance returns None initially."""
        assert AnalyticsManager.get_instance() is None

    def test_configure_sets_instance(self):
        """Test configure sets the singleton."""
        config = AnalyticsConfig()
        manager = AnalyticsManager.configure(config)

        assert manager is not None
        assert AnalyticsManager.get_instance() is manager

    def test_initialize_when_disabled(self):
        """Test initialize returns False when disabled."""
        config = AnalyticsConfig(enabled=False)
        manager = AnalyticsManager(config)

        result = manager.initialize()
        assert result is False

    def test_is_enabled_false_by_default(self):
        """Test is_enabled returns False by default."""
        config = AnalyticsConfig(enabled=False)
        manager = AnalyticsManager(config)

        assert manager.is_enabled() is False

    def test_record_sync_when_disabled(self):
        """Test record_sync does nothing when disabled."""
        config = AnalyticsConfig(enabled=False)
        manager = AnalyticsManager(config)

        # Should not raise
        manager.record_sync(
            success=True,
            stories_count=5,
        )

    def test_record_command_when_disabled(self):
        """Test record_command does nothing when disabled."""
        config = AnalyticsConfig(enabled=False)
        manager = AnalyticsManager(config)

        # Should not raise
        manager.record_command("validate")

    def test_get_data_when_not_initialized(self):
        """Test get_data returns None when not initialized."""
        config = AnalyticsConfig(enabled=False)
        manager = AnalyticsManager(config)

        assert manager.get_data() is None


class TestAnalyticsManagerWithStorage:
    """Tests for AnalyticsManager with actual storage."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset the singleton instance before each test."""
        AnalyticsManager._instance = None
        yield
        AnalyticsManager._instance = None

    @pytest.fixture
    def temp_analytics_dir(self, tmp_path):
        """Create a temporary analytics directory."""
        analytics_dir = tmp_path / "analytics"
        analytics_dir.mkdir()
        return analytics_dir

    def test_initialize_creates_data(self, temp_analytics_dir):
        """Test initialize creates analytics data."""
        config = AnalyticsConfig(
            enabled=True,
            data_dir=str(temp_analytics_dir),
        )
        manager = AnalyticsManager(config)

        result = manager.initialize()

        assert result is True
        assert manager.get_data() is not None

    def test_record_sync_updates_counts(self, temp_analytics_dir):
        """Test record_sync updates sync counts."""
        config = AnalyticsConfig(
            enabled=True,
            data_dir=str(temp_analytics_dir),
        )
        manager = AnalyticsManager(config)
        manager.initialize()

        manager.record_sync(success=True, stories_count=5)
        manager.record_sync(success=True, stories_count=3)
        manager.record_sync(success=False, error_type="NetworkError")

        data = manager.get_data()
        assert data.total_syncs == 3
        assert data.successful_syncs == 2
        assert data.failed_syncs == 1
        assert data.total_stories_synced == 8
        assert data.error_counts.get("NetworkError") == 1

    def test_record_command_updates_usage(self, temp_analytics_dir):
        """Test record_command updates command usage."""
        config = AnalyticsConfig(
            enabled=True,
            data_dir=str(temp_analytics_dir),
        )
        manager = AnalyticsManager(config)
        manager.initialize()

        manager.record_command("validate")
        manager.record_command("validate")
        manager.record_command("init")

        data = manager.get_data()
        assert data.command_usage["validate"] == 2
        assert data.command_usage["init"] == 1

    def test_record_features_updates_usage(self, temp_analytics_dir):
        """Test features are tracked."""
        config = AnalyticsConfig(
            enabled=True,
            data_dir=str(temp_analytics_dir),
        )
        manager = AnalyticsManager(config)
        manager.initialize()

        manager.record_sync(
            success=True,
            features=["dry_run", "incremental"],
        )
        manager.record_sync(
            success=True,
            features=["dry_run"],
        )

        data = manager.get_data()
        assert data.feature_usage["dry_run"] == 2
        assert data.feature_usage["incremental"] == 1

    def test_data_persisted_to_file(self, temp_analytics_dir):
        """Test data is saved to file."""
        config = AnalyticsConfig(
            enabled=True,
            data_dir=str(temp_analytics_dir),
        )
        manager = AnalyticsManager(config)
        manager.initialize()

        manager.record_sync(success=True, stories_count=10)

        # Check file was created
        data_file = temp_analytics_dir / "usage.json"
        assert data_file.exists()

        # Check content
        with open(data_file) as f:
            saved = json.load(f)

        assert saved["stats"]["total_syncs"] == 1
        assert saved["stats"]["total_stories_synced"] == 10

    def test_data_loaded_on_init(self, temp_analytics_dir):
        """Test data is loaded from existing file on init."""
        # Create existing data file
        data_file = temp_analytics_dir / "usage.json"
        existing_data = {
            "installation_id": "existing-id-123",
            "stats": {
                "total_syncs": 100,
                "successful_syncs": 90,
                "failed_syncs": 10,
                "total_stories_synced": 500,
            },
            "feature_usage": {"dry_run": 50},
            "command_usage": {"sync": 100},
            "error_counts": {},
        }
        with open(data_file, "w") as f:
            json.dump(existing_data, f)

        # Initialize manager
        config = AnalyticsConfig(
            enabled=True,
            data_dir=str(temp_analytics_dir),
        )
        manager = AnalyticsManager(config)
        manager.initialize()

        data = manager.get_data()
        assert data.installation_id == "existing-id-123"
        assert data.total_syncs == 100
        assert data.feature_usage["dry_run"] == 50

    def test_clear_data(self, temp_analytics_dir):
        """Test clear_data removes file and resets data."""
        config = AnalyticsConfig(
            enabled=True,
            data_dir=str(temp_analytics_dir),
        )
        manager = AnalyticsManager(config)
        manager.initialize()

        manager.record_sync(success=True, stories_count=10)

        # Verify data exists
        data_file = temp_analytics_dir / "usage.json"
        assert data_file.exists()

        # Clear data
        result = manager.clear_data()
        assert result is True

        # Verify file removed
        assert not data_file.exists()

        # Verify in-memory data reset
        data = manager.get_data()
        assert data.total_syncs == 0


# =============================================================================
# Helper Functions Tests
# =============================================================================


class TestHelperFunctions:
    """Tests for helper functions."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset the singleton instance before each test."""
        AnalyticsManager._instance = None
        yield
        AnalyticsManager._instance = None

    def test_configure_analytics_disabled(self):
        """Test configure_analytics when disabled."""
        manager = configure_analytics(enabled=False)

        assert isinstance(manager, AnalyticsManager)
        assert manager.is_enabled() is False

    def test_configure_analytics_with_dir(self, tmp_path):
        """Test configure_analytics with custom directory."""
        data_dir = tmp_path / "analytics"
        manager = configure_analytics(
            enabled=True,
            data_dir=str(data_dir),
        )

        assert manager.config.data_dir == str(data_dir)

    def test_get_analytics_none(self):
        """Test get_analytics returns None initially."""
        assert get_analytics() is None

    def test_get_analytics_after_configure(self):
        """Test get_analytics after configure."""
        configure_analytics(enabled=False)

        result = get_analytics()
        assert result is not None

    def test_show_analytics_info(self):
        """Test show_analytics_info returns description."""
        info = show_analytics_info()

        assert "opt-in" in info.lower()
        assert "anonymous" in info.lower()
        assert "NEVER collect" in info
        assert "--analytics" in info

    def test_format_analytics_display(self):
        """Test format_analytics_display formats data."""
        data = {
            "Section 1": {"key1": "value1", "key2": "value2"},
            "Section 2": {"count": 10},
        }

        output = format_analytics_display(data)

        assert "Section 1:" in output
        assert "key1: value1" in output
        assert "Section 2:" in output
        assert "count: 10" in output


# =============================================================================
# CLI Integration Tests
# =============================================================================


class TestCLIIntegration:
    """Tests for CLI integration."""

    def test_analytics_flags_in_parser(self, cli_parser):
        """Test --analytics-* flags are recognized."""
        args = cli_parser.parse_args(
            [
                "--analytics",
                "--input",
                "epic.md",
                "--epic",
                "TEST-123",
            ]
        )

        assert args.analytics is True

    def test_analytics_show_flag(self, cli_parser):
        """Test --analytics-show flag."""
        args = cli_parser.parse_args(["--analytics-show"])

        assert args.analytics_show is True

    def test_analytics_clear_flag(self, cli_parser):
        """Test --analytics-clear flag."""
        args = cli_parser.parse_args(["--analytics-clear"])

        assert args.analytics_clear is True

    def test_analytics_disabled_by_default(self, cli_parser):
        """Test analytics is disabled by default."""
        args = cli_parser.parse_args(
            [
                "--input",
                "epic.md",
                "--epic",
                "TEST-123",
            ]
        )

        assert args.analytics is False


# =============================================================================
# Privacy Tests
# =============================================================================


class TestPrivacy:
    """Tests to ensure analytics respects privacy."""

    def test_no_pii_in_data(self, tmp_path):
        """Test no PII is stored in analytics data."""
        AnalyticsManager._instance = None

        config = AnalyticsConfig(
            enabled=True,
            data_dir=str(tmp_path),
        )
        manager = AnalyticsManager(config)
        manager.initialize()

        # Record some events
        manager.record_sync(
            success=True,
            stories_count=5,
            features=["dry_run"],
        )

        # Check saved data
        data_file = tmp_path / "usage.json"
        with open(data_file) as f:
            saved = json.load(f)

        # Convert to string and check for PII patterns
        saved_str = json.dumps(saved)

        # Should not contain common PII patterns
        assert "@" not in saved_str  # No email
        assert "password" not in saved_str.lower()
        assert "secret" not in saved_str.lower()
        assert "token" not in saved_str.lower()

    def test_no_project_names_stored(self, tmp_path):
        """Test no project names or keys are stored."""
        AnalyticsManager._instance = None

        config = AnalyticsConfig(
            enabled=True,
            data_dir=str(tmp_path),
        )
        manager = AnalyticsManager(config)
        manager.initialize()

        # Record sync - note we don't pass epic_key
        manager.record_sync(success=True, stories_count=5)

        # Check saved data
        data_file = tmp_path / "usage.json"
        with open(data_file) as f:
            saved = json.load(f)

        saved_str = json.dumps(saved)

        # Should not contain project-specific data
        assert "PROJ-" not in saved_str
        assert "epic" not in saved_str.lower() or "epic_key" not in saved_str

    def test_error_type_only_not_message(self, tmp_path):
        """Test only error types are stored, not messages."""
        AnalyticsManager._instance = None

        config = AnalyticsConfig(
            enabled=True,
            data_dir=str(tmp_path),
        )
        manager = AnalyticsManager(config)
        manager.initialize()

        # Record error with type (message would be in the exception)
        manager.record_sync(
            success=False,
            error_type="AuthenticationError",  # Only type, no message
        )

        data = manager.get_data()

        # Only error type should be stored
        assert "AuthenticationError" in data.error_counts
        # No error messages or stack traces
        assert len(data.error_counts) == 1


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset the singleton instance before each test."""
        AnalyticsManager._instance = None
        yield
        AnalyticsManager._instance = None

    def test_corrupted_data_file(self, tmp_path):
        """Test handling of corrupted data file."""
        # Create corrupted file
        data_file = tmp_path / "usage.json"
        data_file.write_text("{ invalid json }")

        config = AnalyticsConfig(
            enabled=True,
            data_dir=str(tmp_path),
        )
        manager = AnalyticsManager(config)

        # Should not crash, should start fresh
        result = manager.initialize()
        assert result is True

        data = manager.get_data()
        assert data.total_syncs == 0  # Fresh start

    def test_many_events_limited(self, tmp_path):
        """Test recent events are limited to 100."""
        config = AnalyticsConfig(
            enabled=True,
            data_dir=str(tmp_path),
        )
        manager = AnalyticsManager(config)
        manager.initialize()

        # Record 150 events
        for i in range(150):
            manager.record_command(f"cmd_{i}")

        data = manager.get_data()

        # Should only keep last 100
        assert len(data.recent_events) <= 100

    def test_initialize_twice(self, tmp_path):
        """Test initializing twice returns True."""
        config = AnalyticsConfig(
            enabled=True,
            data_dir=str(tmp_path),
        )
        manager = AnalyticsManager(config)

        result1 = manager.initialize()
        result2 = manager.initialize()

        assert result1 is True
        assert result2 is True
