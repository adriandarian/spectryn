"""
Tests for watch mode - auto-sync on file changes.
"""

import pytest
import tempfile
import time
import threading
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

from md2jira.application.watch import (
    FileWatcher,
    WatchOrchestrator,
    WatchDisplay,
    WatchEvent,
    FileChange,
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
    
    def test_start_stop(self):
        """Test starting and stopping the watcher."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("# Test content")
            f.flush()
            
            try:
                watcher = FileWatcher(f.name, poll_interval=0.1)
                watcher.start()
                
                assert watcher._running
                
                watcher.stop()
                
                assert not watcher._running
            finally:
                Path(f.name).unlink()
    
    def test_file_not_found(self):
        """Test error when file doesn't exist."""
        watcher = FileWatcher("/nonexistent/file.md")
        
        with pytest.raises(FileNotFoundError):
            watcher.start()
    
    def test_detect_modification(self):
        """Test detecting file modifications."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("# Initial content")
            f.flush()
            
            changes_detected = []
            
            try:
                watcher = FileWatcher(f.name, debounce_seconds=0.1, poll_interval=0.1)
                watcher.on_change(lambda c: changes_detected.append(c))
                watcher.start()
                
                # Modify the file
                time.sleep(0.2)  # Wait for initial poll
                Path(f.name).write_text("# Modified content")
                
                # Wait for detection
                time.sleep(0.5)
                watcher.stop()
                
                # Should have detected the change
                assert len(changes_detected) >= 1
                assert any(c.event == WatchEvent.MODIFIED for c in changes_detected)
                
            finally:
                Path(f.name).unlink()
    
    def test_debouncing(self):
        """Test that rapid changes are debounced."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("# Initial")
            f.flush()
            
            changes_detected = []
            
            try:
                watcher = FileWatcher(f.name, debounce_seconds=0.5, poll_interval=0.1)
                watcher.on_change(lambda c: changes_detected.append(c))
                watcher.start()
                
                time.sleep(0.2)
                
                # Make rapid changes
                for i in range(5):
                    Path(f.name).write_text(f"# Version {i}")
                    time.sleep(0.05)
                
                # Wait for debounce
                time.sleep(0.7)
                watcher.stop()
                
                # Should have fewer changes than modifications due to debouncing
                assert len(changes_detected) < 5
                
            finally:
                Path(f.name).unlink()
    
    def test_multiple_callbacks(self):
        """Test registering multiple callbacks."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("# Initial")
            f.flush()
            
            callback1_called = []
            callback2_called = []
            
            try:
                watcher = FileWatcher(f.name, debounce_seconds=0.1, poll_interval=0.1)
                watcher.on_change(lambda c: callback1_called.append(c))
                watcher.on_change(lambda c: callback2_called.append(c))
                watcher.start()
                
                time.sleep(0.2)
                Path(f.name).write_text("# Modified")
                time.sleep(0.4)
                watcher.stop()
                
                # Both callbacks should be called
                assert len(callback1_called) >= 1
                assert len(callback2_called) >= 1
                
            finally:
                Path(f.name).unlink()
    
    def test_compute_hash_consistency(self):
        """Test that hash computation is consistent."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("# Test content")
            f.flush()
            
            try:
                watcher = FileWatcher(f.name)
                hash1 = watcher._compute_hash()
                hash2 = watcher._compute_hash()
                
                assert hash1 == hash2
                
                # Change content
                Path(f.name).write_text("# Different content")
                hash3 = watcher._compute_hash()
                
                assert hash1 != hash3
                
            finally:
                Path(f.name).unlink()


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
    
    def test_initialization(self, mock_orchestrator):
        """Test orchestrator initialization."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("# Test")
            f.flush()
            
            try:
                watch = WatchOrchestrator(
                    orchestrator=mock_orchestrator,
                    markdown_path=f.name,
                    epic_key="PROJ-123",
                )
                
                assert watch.markdown_path == f.name
                assert watch.epic_key == "PROJ-123"
                assert watch.stats.syncs_triggered == 0
                
            finally:
                Path(f.name).unlink()
    
    def test_start_async(self, mock_orchestrator):
        """Test async start mode."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("# Test")
            f.flush()
            
            try:
                watch = WatchOrchestrator(
                    orchestrator=mock_orchestrator,
                    markdown_path=f.name,
                    epic_key="PROJ-123",
                )
                
                watch.start_async()
                assert watch._running
                
                watch.stop()
                assert not watch._running
                
            finally:
                Path(f.name).unlink()
    
    def test_trigger_sync_on_change(self, mock_orchestrator):
        """Test that sync is triggered when file changes."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("# Initial")
            f.flush()
            
            try:
                watch = WatchOrchestrator(
                    orchestrator=mock_orchestrator,
                    markdown_path=f.name,
                    epic_key="PROJ-123",
                    debounce_seconds=0.1,
                    poll_interval=0.1,
                )
                
                watch.start_async()
                
                # Modify file
                time.sleep(0.2)
                Path(f.name).write_text("# Modified content")
                
                # Wait for sync
                time.sleep(0.5)
                watch.stop()
                
                # Should have triggered a sync
                assert watch.stats.syncs_triggered >= 1
                mock_orchestrator.sync.assert_called()
                
            finally:
                Path(f.name).unlink()
    
    def test_callbacks(self, mock_orchestrator):
        """Test that callbacks are invoked."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("# Initial")
            f.flush()
            
            change_callback_called = []
            sync_start_called = []
            sync_complete_called = []
            
            try:
                watch = WatchOrchestrator(
                    orchestrator=mock_orchestrator,
                    markdown_path=f.name,
                    epic_key="PROJ-123",
                    debounce_seconds=0.1,
                    poll_interval=0.1,
                    on_change_detected=lambda c: change_callback_called.append(c),
                    on_sync_start=lambda: sync_start_called.append(True),
                    on_sync_complete=lambda r: sync_complete_called.append(r),
                )
                
                watch.start_async()
                
                time.sleep(0.2)
                Path(f.name).write_text("# Modified")
                time.sleep(0.5)
                watch.stop()
                
                assert len(change_callback_called) >= 1
                assert len(sync_start_called) >= 1
                assert len(sync_complete_called) >= 1
                
            finally:
                Path(f.name).unlink()
    
    def test_get_status(self, mock_orchestrator):
        """Test getting watch status."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("# Test")
            f.flush()
            
            try:
                watch = WatchOrchestrator(
                    orchestrator=mock_orchestrator,
                    markdown_path=f.name,
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
                
            finally:
                Path(f.name).unlink()
    
    def test_sync_failure_handling(self, mock_orchestrator):
        """Test handling of sync failures."""
        mock_orchestrator.sync.return_value = Mock(
            success=False,
            errors=["Test error"],
        )
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("# Initial")
            f.flush()
            
            try:
                watch = WatchOrchestrator(
                    orchestrator=mock_orchestrator,
                    markdown_path=f.name,
                    epic_key="PROJ-123",
                    debounce_seconds=0.1,
                    poll_interval=0.1,
                )
                
                watch.start_async()
                
                time.sleep(0.2)
                Path(f.name).write_text("# Modified")
                time.sleep(0.5)
                watch.stop()
                
                # Should have recorded the failure
                assert watch.stats.syncs_failed >= 1
                
            finally:
                Path(f.name).unlink()
    
    def test_sync_exception_handling(self, mock_orchestrator):
        """Test handling of sync exceptions."""
        mock_orchestrator.sync.side_effect = Exception("Test exception")
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("# Initial")
            f.flush()
            
            try:
                watch = WatchOrchestrator(
                    orchestrator=mock_orchestrator,
                    markdown_path=f.name,
                    epic_key="PROJ-123",
                    debounce_seconds=0.1,
                    poll_interval=0.1,
                )
                
                watch.start_async()
                
                time.sleep(0.2)
                Path(f.name).write_text("# Modified")
                time.sleep(0.5)
                watch.stop()
                
                # Should have recorded the failure
                assert watch.stats.syncs_failed >= 1
                assert len(watch.stats.errors) >= 1
                
            finally:
                Path(f.name).unlink()


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

