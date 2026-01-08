"""
Tests for watch mode - auto-sync on file changes.
"""

import tempfile
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from spectryn.application.watch import (
    FileChange,
    FileWatcher,
    WatchDisplay,
    WatchEvent,
    WatchOrchestrator,
    WatchStats,
)


class TestFileChange:
    """Tests for FileChange dataclass."""

    def test_str(self):
        """Test string representation."""
        change = FileChange(
            path="/test/file.md",
            event=WatchEvent.MODIFIED,
        )

        result = str(change)
        assert "modified" in result
        assert "/test/file.md" in result

    def test_event_types(self):
        """Test different event types."""
        for event in WatchEvent:
            change = FileChange(path="/test.md", event=event)
            assert change.event == event


class TestWatchStats:
    """Tests for WatchStats dataclass."""

    def test_initial_state(self):
        """Test initial state of stats."""
        stats = WatchStats()

        assert stats.changes_detected == 0
        assert stats.syncs_triggered == 0
        assert stats.syncs_successful == 0
        assert stats.syncs_failed == 0
        assert len(stats.errors) == 0

    def test_uptime_formatted(self):
        """Test uptime formatting."""
        stats = WatchStats()

        # Just started - should be "0s" or similar
        formatted = stats.uptime_formatted
        assert "s" in formatted

    def test_uptime_seconds(self):
        """Test uptime calculation."""
        stats = WatchStats()
        time.sleep(0.1)

        assert stats.uptime_seconds >= 0.1


class TestFileWatcher:
    """Tests for FileWatcher class."""

    def test_start_stop(self, tmp_path):
        """Test starting and stopping the watcher."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test content")

        watcher = FileWatcher(str(test_file), poll_interval=0.1)
        watcher.start()

        assert watcher._running

        watcher.stop()

        assert not watcher._running

    def test_file_not_found(self):
        """Test error when file doesn't exist."""
        watcher = FileWatcher("/nonexistent/file.md")

        with pytest.raises(FileNotFoundError):
            watcher.start()

    def test_detect_modification(self, tmp_path):
        """Test detecting file modifications."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Initial content")

        changes_detected = []

        watcher = FileWatcher(str(test_file), debounce_seconds=0.1, poll_interval=0.1)
        watcher.on_change(lambda c: changes_detected.append(c))
        watcher.start()

        # Modify the file
        time.sleep(0.2)  # Wait for initial poll
        test_file.write_text("# Modified content")

        # Wait for detection
        time.sleep(0.5)
        watcher.stop()

        # Should have detected the change
        assert len(changes_detected) >= 1
        assert any(c.event == WatchEvent.MODIFIED for c in changes_detected)

    def test_debouncing(self, tmp_path):
        """Test that rapid changes are debounced."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Initial")

        changes_detected = []

        watcher = FileWatcher(str(test_file), debounce_seconds=0.5, poll_interval=0.1)
        watcher.on_change(lambda c: changes_detected.append(c))
        watcher.start()

        time.sleep(0.2)

        # Make rapid changes
        for i in range(5):
            test_file.write_text(f"# Version {i}")
            time.sleep(0.05)

        # Wait for debounce
        time.sleep(0.7)
        watcher.stop()

        # Should have fewer changes than modifications due to debouncing
        assert len(changes_detected) < 5

    def test_multiple_callbacks(self, tmp_path):
        """Test registering multiple callbacks."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Initial")

        callback1_called = []
        callback2_called = []

        watcher = FileWatcher(str(test_file), debounce_seconds=0.1, poll_interval=0.1)
        watcher.on_change(lambda c: callback1_called.append(c))
        watcher.on_change(lambda c: callback2_called.append(c))
        watcher.start()

        time.sleep(0.2)
        test_file.write_text("# Modified")
        time.sleep(0.4)
        watcher.stop()

        # Both callbacks should be called
        assert len(callback1_called) >= 1
        assert len(callback2_called) >= 1

    def test_compute_hash_consistency(self, tmp_path):
        """Test that hash computation is consistent."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test content")

        watcher = FileWatcher(str(test_file))
        hash1 = watcher._compute_hash()
        hash2 = watcher._compute_hash()

        assert hash1 == hash2

        # Change content
        test_file.write_text("# Different content")
        hash3 = watcher._compute_hash()

        assert hash1 != hash3


class TestWatchOrchestrator:
    """Tests for WatchOrchestrator class."""

    @pytest.fixture
    def mock_orchestrator(self):
        """Create a mock sync orchestrator."""
        orchestrator = Mock()
        orchestrator.sync.return_value = Mock(
            success=True,
            stories_matched=2,
            stories_updated=1,
            subtasks_created=0,
            subtasks_updated=0,
            errors=[],
        )
        return orchestrator

    def test_initialization(self, mock_orchestrator, tmp_path):
        """Test orchestrator initialization."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        watch = WatchOrchestrator(
            orchestrator=mock_orchestrator,
            markdown_path=str(test_file),
            epic_key="PROJ-123",
        )

        assert watch.markdown_path == str(test_file)
        assert watch.epic_key == "PROJ-123"
        assert watch.stats.syncs_triggered == 0

    def test_start_async(self, mock_orchestrator, tmp_path):
        """Test async start mode."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        watch = WatchOrchestrator(
            orchestrator=mock_orchestrator,
            markdown_path=str(test_file),
            epic_key="PROJ-123",
        )

        watch.start_async()
        assert watch._running

        watch.stop()
        assert not watch._running

    def test_trigger_sync_on_change(self, mock_orchestrator, tmp_path):
        """Test that sync is triggered when file changes."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Initial")

        watch = WatchOrchestrator(
            orchestrator=mock_orchestrator,
            markdown_path=str(test_file),
            epic_key="PROJ-123",
            debounce_seconds=0.1,
            poll_interval=0.1,
        )

        watch.start_async()

        # Modify file
        time.sleep(0.2)
        test_file.write_text("# Modified content")

        # Wait for sync
        time.sleep(0.5)
        watch.stop()

        # Should have triggered a sync
        assert watch.stats.syncs_triggered >= 1
        mock_orchestrator.sync.assert_called()

    def test_callbacks(self, mock_orchestrator, tmp_path):
        """Test that callbacks are invoked."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Initial")

        change_callback_called = []
        sync_start_called = []
        sync_complete_called = []

        watch = WatchOrchestrator(
            orchestrator=mock_orchestrator,
            markdown_path=str(test_file),
            epic_key="PROJ-123",
            debounce_seconds=0.1,
            poll_interval=0.1,
            on_change_detected=lambda c: change_callback_called.append(c),
            on_sync_start=lambda: sync_start_called.append(True),
            on_sync_complete=lambda r: sync_complete_called.append(r),
        )

        watch.start_async()

        time.sleep(0.2)
        test_file.write_text("# Modified")
        time.sleep(0.5)
        watch.stop()

        assert len(change_callback_called) >= 1
        assert len(sync_start_called) >= 1
        assert len(sync_complete_called) >= 1

    def test_get_status(self, mock_orchestrator, tmp_path):
        """Test getting watch status."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        watch = WatchOrchestrator(
            orchestrator=mock_orchestrator,
            markdown_path=str(test_file),
            epic_key="PROJ-123",
        )

        watch.start_async()
        status = watch.get_status()

        # Check status while running
        assert status["running"] is True
        assert status["epic_key"] == "PROJ-123"
        assert "uptime" in status

        watch.stop()

        # Check status after stopping
        status_after = watch.get_status()
        assert status_after["running"] is False

    def test_sync_failure_handling(self, mock_orchestrator, tmp_path):
        """Test handling of sync failures."""
        mock_orchestrator.sync.return_value = Mock(
            success=False,
            errors=["Test error"],
        )

        test_file = tmp_path / "test.md"
        test_file.write_text("# Initial")

        watch = WatchOrchestrator(
            orchestrator=mock_orchestrator,
            markdown_path=str(test_file),
            epic_key="PROJ-123",
            debounce_seconds=0.1,
            poll_interval=0.1,
        )

        watch.start_async()

        time.sleep(0.2)
        test_file.write_text("# Modified")
        time.sleep(0.5)
        watch.stop()

        # Should have recorded the failure
        assert watch.stats.syncs_failed >= 1

    def test_sync_exception_handling(self, mock_orchestrator, tmp_path):
        """Test handling of sync exceptions."""
        mock_orchestrator.sync.side_effect = Exception("Test exception")

        test_file = tmp_path / "test.md"
        test_file.write_text("# Initial")

        watch = WatchOrchestrator(
            orchestrator=mock_orchestrator,
            markdown_path=str(test_file),
            epic_key="PROJ-123",
            debounce_seconds=0.1,
            poll_interval=0.1,
        )

        watch.start_async()

        time.sleep(0.2)
        test_file.write_text("# Modified")
        time.sleep(0.5)
        watch.stop()

        # Should have recorded the failure
        assert watch.stats.syncs_failed >= 1
        assert len(watch.stats.errors) >= 1


class TestWatchDisplay:
    """Tests for WatchDisplay class."""

    def test_show_start(self, capsys):
        """Test showing start message."""
        display = WatchDisplay(color=False)
        display.show_start("/test/file.md", "PROJ-123")

        captured = capsys.readouterr()
        assert "Watch Mode" in captured.out
        assert "/test/file.md" in captured.out
        assert "PROJ-123" in captured.out

    def test_show_start_quiet(self, capsys):
        """Test quiet mode suppresses output."""
        display = WatchDisplay(quiet=True)
        display.show_start("/test/file.md", "PROJ-123")

        captured = capsys.readouterr()
        assert captured.out == ""

    def test_show_change_detected(self, capsys):
        """Test showing change detected message."""
        display = WatchDisplay(color=False)
        change = FileChange(path="/test.md", event=WatchEvent.MODIFIED)
        display.show_change_detected(change)

        captured = capsys.readouterr()
        assert "Change detected" in captured.out

    def test_show_sync_complete_success(self, capsys):
        """Test showing successful sync complete."""
        display = WatchDisplay(color=False)
        result = Mock(
            success=True,
            stories_matched=5,
            stories_updated=2,
            subtasks_created=3,
            subtasks_updated=1,
        )
        display.show_sync_complete(result)

        captured = capsys.readouterr()
        assert "Sync complete" in captured.out

    def test_show_sync_complete_failure(self, capsys):
        """Test showing failed sync complete."""
        display = WatchDisplay(color=False)
        result = Mock(
            success=False,
            errors=["Error 1", "Error 2"],
        )
        display.show_sync_complete(result)

        captured = capsys.readouterr()
        assert "Sync failed" in captured.out

    def test_show_stop(self, capsys):
        """Test showing stop message."""
        display = WatchDisplay(color=False)
        stats = WatchStats()
        stats.syncs_successful = 5
        stats.syncs_failed = 1
        stats.changes_detected = 6

        display.show_stop(stats)

        captured = capsys.readouterr()
        assert "Watch Mode Stopped" in captured.out
        assert "5 successful" in captured.out
        assert "1 failed" in captured.out
