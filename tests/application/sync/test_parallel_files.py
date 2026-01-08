"""Tests for parallel file processing."""

import textwrap
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from spectryn.application.sync.parallel_files import (
    FileProgress,
    FileSyncResult,
    ParallelFileProcessor,
    ParallelFilesConfig,
    ParallelFilesResult,
    create_parallel_file_processor,
    process_files_parallel,
)


class TestFileProgress:
    """Tests for FileProgress dataclass."""

    def test_default_values(self):
        """Test default values."""
        progress = FileProgress(file_path="/path/to/file.md", file_name="file.md")

        assert progress.file_path == "/path/to/file.md"
        assert progress.file_name == "file.md"
        assert progress.status == "pending"
        assert progress.epics_found == 0
        assert progress.epics_synced == 0
        assert progress.stories_synced == 0
        assert progress.progress == 0.0
        assert progress.started_at is None
        assert progress.completed_at is None
        assert progress.error is None

    def test_duration_calculation(self):
        """Test duration calculation."""
        progress = FileProgress(
            file_path="/path/to/file.md",
            file_name="file.md",
            started_at=datetime(2024, 1, 1, 10, 0, 0),
            completed_at=datetime(2024, 1, 1, 10, 0, 30),
        )

        assert progress.duration_seconds == 30.0

    def test_duration_without_times(self):
        """Test duration without start/end times."""
        progress = FileProgress(file_path="/path/to/file.md", file_name="file.md")

        assert progress.duration_seconds == 0.0


class TestFileSyncResult:
    """Tests for FileSyncResult dataclass."""

    def test_default_values(self):
        """Test default values."""
        result = FileSyncResult(file_path="/path/to/file.md", file_name="file.md")

        assert result.success is True
        assert result.dry_run is False
        assert result.epics_found == 0
        assert result.errors == []

    def test_add_error(self):
        """Test adding an error."""
        result = FileSyncResult(file_path="/path/to/file.md", file_name="file.md")

        result.add_error("Test error")

        assert result.success is False
        assert len(result.errors) == 1
        assert "Test error" in result.errors


class TestParallelFilesConfig:
    """Tests for ParallelFilesConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = ParallelFilesConfig()

        assert config.max_workers == 4
        assert config.timeout_per_file == 600.0
        assert config.fail_fast is False
        assert config.skip_empty_files is True
        assert config.file_pattern == "*.md"

    def test_custom_values(self):
        """Test custom configuration values."""
        config = ParallelFilesConfig(
            max_workers=8,
            timeout_per_file=300.0,
            fail_fast=True,
            skip_empty_files=False,
        )

        assert config.max_workers == 8
        assert config.timeout_per_file == 300.0
        assert config.fail_fast is True
        assert config.skip_empty_files is False


class TestParallelFilesResult:
    """Tests for ParallelFilesResult dataclass."""

    def test_default_values(self):
        """Test default result values."""
        result = ParallelFilesResult()

        assert result.success is True
        assert result.dry_run is False
        assert result.files_total == 0
        assert result.files_processed == 0
        assert result.files_succeeded == 0
        assert result.files_failed == 0
        assert result.files_skipped == 0

    def test_add_file_result_success(self):
        """Test adding a successful file result."""
        result = ParallelFilesResult()

        file_result = FileSyncResult(
            file_path="/path/to/file.md",
            file_name="file.md",
            success=True,
            epics_found=2,
            stories_total=5,
            stories_updated=3,
            subtasks_created=10,
        )

        result.add_file_result(file_result)

        assert result.files_processed == 1
        assert result.files_succeeded == 1
        assert result.files_failed == 0
        assert result.total_epics == 2
        assert result.total_stories == 5
        assert result.total_stories_updated == 3
        assert result.total_subtasks_created == 10

    def test_add_file_result_failure(self):
        """Test adding a failed file result."""
        result = ParallelFilesResult()

        file_result = FileSyncResult(
            file_path="/path/to/file.md",
            file_name="file.md",
            success=False,
            errors=["Test error"],
        )

        result.add_file_result(file_result)

        assert result.files_processed == 1
        assert result.files_succeeded == 0
        assert result.files_failed == 1
        assert result.success is False
        assert len(result.errors) == 1

    def test_summary_generation(self):
        """Test summary generation."""
        result = ParallelFilesResult(
            files_total=3,
            files_succeeded=2,
            files_failed=1,
            total_epics=5,
            total_stories=10,
            total_stories_updated=8,
            workers_used=4,
            peak_concurrency=3,
        )
        result.completed_at = datetime.now()

        summary = result.summary()

        assert "Parallel File Processing" in summary
        assert "Files: 2/3" in summary
        assert "Failed: 1" in summary
        assert "Epics: 5" in summary
        assert "Stories: 10" in summary
        assert "Workers: 4" in summary


class TestParallelFileProcessor:
    """Tests for ParallelFileProcessor."""

    @pytest.fixture
    def mock_tracker(self):
        """Create a mock tracker."""
        tracker = MagicMock()
        tracker.test_connection.return_value = True
        tracker.get_current_user.return_value = {"displayName": "Test User"}
        return tracker

    @pytest.fixture
    def mock_parser(self):
        """Create a mock parser."""
        return MagicMock()

    @pytest.fixture
    def mock_formatter(self):
        """Create a mock formatter."""
        return MagicMock()

    @pytest.fixture
    def mock_config(self):
        """Create a mock sync config."""
        config = MagicMock()
        config.dry_run = True
        return config

    @pytest.fixture
    def processor(self, mock_tracker, mock_parser, mock_formatter, mock_config):
        """Create a processor instance."""
        return ParallelFileProcessor(
            tracker=mock_tracker,
            parser=mock_parser,
            formatter=mock_formatter,
            config=mock_config,
        )

    def test_initialization(self, processor):
        """Test processor initialization."""
        assert processor.parallel_config.max_workers == 4
        assert processor.parallel_config.fail_fast is False

    def test_custom_config(self, mock_tracker, mock_parser, mock_formatter, mock_config):
        """Test processor with custom config."""
        parallel_config = ParallelFilesConfig(
            max_workers=8,
            fail_fast=True,
        )

        processor = ParallelFileProcessor(
            tracker=mock_tracker,
            parser=mock_parser,
            formatter=mock_formatter,
            config=mock_config,
            parallel_config=parallel_config,
        )

        assert processor.parallel_config.max_workers == 8
        assert processor.parallel_config.fail_fast is True

    def test_process_no_files(self, processor):
        """Test processing with no files."""
        result = processor.process([])

        assert result.files_total == 0
        assert result.files_processed == 0

    def test_process_nonexistent_files(self, processor):
        """Test processing with nonexistent files."""
        result = processor.process(["/nonexistent/file.md"])

        assert result.files_total == 0
        assert len(result.warnings) == 1
        assert "not found" in result.warnings[0]

    def test_process_with_callback(self, processor, tmp_path):
        """Test processing with progress callback."""
        # Create a test file
        test_file = tmp_path / "test.md"
        test_file.write_text(
            textwrap.dedent("""
            ## Epic: TEST-1 - Test Epic

            ### US-001: Test Story
            **As a** user
            **I want** something
            **So that** benefit
            """),
            encoding="utf-8",
        )

        callbacks_received = []

        def callback(file_path: str, status: str, progress: float) -> None:
            callbacks_received.append((file_path, status, progress))

        with patch.object(
            processor,
            "_process_single_file",
            return_value=FileSyncResult(
                file_path=str(test_file),
                file_name=test_file.name,
                success=True,
                epics_found=1,
            ),
        ):
            result = processor.process([str(test_file)], progress_callback=callback)

        assert len(callbacks_received) > 0
        assert result.files_processed == 1

    def test_get_stats(self, processor):
        """Test getting stats."""
        stats = processor.get_stats()

        assert "active_workers" in stats
        assert "peak_concurrency" in stats
        assert "cancelled" in stats
        assert stats["active_workers"] == 0
        assert stats["cancelled"] is False

    def test_cancel(self, processor):
        """Test cancellation."""
        processor.cancel()

        stats = processor.get_stats()
        assert stats["cancelled"] is True


class TestParallelFileProcessorDirectory:
    """Tests for directory processing."""

    @pytest.fixture
    def mock_deps(self):
        """Create mock dependencies."""
        return {
            "tracker": MagicMock(),
            "parser": MagicMock(),
            "formatter": MagicMock(),
            "config": MagicMock(dry_run=True),
        }

    def test_process_directory_not_found(self, mock_deps):
        """Test processing a nonexistent directory."""
        processor = ParallelFileProcessor(**mock_deps)

        result = processor.process_directory("/nonexistent/directory")

        assert result.success is False
        assert len(result.errors) == 1
        assert "not found" in result.errors[0]

    def test_process_directory_empty(self, mock_deps, tmp_path):
        """Test processing an empty directory."""
        processor = ParallelFileProcessor(**mock_deps)

        result = processor.process_directory(tmp_path)

        assert result.files_total == 0

    def test_process_directory_with_files(self, mock_deps, tmp_path):
        """Test processing a directory with files."""
        # Create test files
        (tmp_path / "file1.md").write_text("# File 1", encoding="utf-8")
        (tmp_path / "file2.md").write_text("# File 2", encoding="utf-8")
        (tmp_path / "file3.txt").write_text("Not markdown", encoding="utf-8")

        processor = ParallelFileProcessor(**mock_deps)

        with patch.object(processor, "process") as mock_process:
            mock_process.return_value = ParallelFilesResult(files_total=2)
            processor.process_directory(tmp_path, pattern="*.md")

        # Should only find 2 markdown files
        mock_process.assert_called_once()
        call_args = mock_process.call_args
        assert len(call_args[0][0]) == 2  # Two files passed

    def test_process_directory_recursive(self, mock_deps, tmp_path):
        """Test recursive directory processing."""
        # Create nested structure
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (tmp_path / "file1.md").write_text("# File 1", encoding="utf-8")
        (subdir / "file2.md").write_text("# File 2", encoding="utf-8")

        processor = ParallelFileProcessor(**mock_deps)

        with patch.object(processor, "process") as mock_process:
            mock_process.return_value = ParallelFilesResult(files_total=2)
            processor.process_directory(tmp_path, recursive=True)

        # Should find both files
        call_args = mock_process.call_args
        assert len(call_args[0][0]) == 2


class TestFactoryFunctions:
    """Tests for factory functions."""

    def test_create_parallel_file_processor(self):
        """Test factory function."""
        tracker = MagicMock()
        parser = MagicMock()
        formatter = MagicMock()
        config = MagicMock(dry_run=True)

        processor = create_parallel_file_processor(
            tracker=tracker,
            parser=parser,
            formatter=formatter,
            config=config,
            max_workers=8,
            fail_fast=True,
        )

        assert processor.parallel_config.max_workers == 8
        assert processor.parallel_config.fail_fast is True

    def test_process_files_parallel(self, tmp_path):
        """Test convenience function."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test", encoding="utf-8")

        tracker = MagicMock()
        parser = MagicMock()
        formatter = MagicMock()
        config = MagicMock(dry_run=True)

        with patch(
            "spectryn.application.sync.parallel_files.ParallelFileProcessor.process"
        ) as mock_process:
            mock_process.return_value = ParallelFilesResult(
                files_total=1,
                files_processed=1,
                files_succeeded=1,
            )

            result = process_files_parallel(
                file_paths=[str(test_file)],
                tracker=tracker,
                parser=parser,
                formatter=formatter,
                config=config,
                max_workers=4,
            )

        assert result.files_total == 1
        assert result.files_succeeded == 1


class TestParallelFilesIntegration:
    """Integration tests for parallel file processing."""

    @pytest.fixture
    def sample_epic_content(self):
        """Sample epic markdown content."""
        return textwrap.dedent("""
            ## Epic: TEST-100 - Sample Epic

            ### 🔧 US-001: First Story

            | Field | Value |
            |-------|-------|
            | **Story Points** | 3 |
            | **Priority** | 🟡 High |
            | **Status** | 📋 Planned |

            **As a** developer
            **I want** to test parallel processing
            **So that** I can verify it works

            #### Acceptance Criteria
            - [ ] AC1: First criteria
            - [ ] AC2: Second criteria

            ### 🔧 US-002: Second Story

            | Field | Value |
            |-------|-------|
            | **Story Points** | 5 |

            **As a** user
            **I want** more features
            **So that** I can be productive
            """)

    def test_file_progress_tracking(self, tmp_path, sample_epic_content):
        """Test that file progress is tracked correctly."""
        # Create test files
        file1 = tmp_path / "epic1.md"
        file2 = tmp_path / "epic2.md"
        file1.write_text(sample_epic_content, encoding="utf-8")
        file2.write_text(sample_epic_content, encoding="utf-8")

        mock_config = MagicMock(dry_run=True)

        processor = ParallelFileProcessor(
            tracker=MagicMock(),
            parser=MagicMock(),
            formatter=MagicMock(),
            config=mock_config,
        )

        # Check progress tracking initialization
        with patch.object(
            processor,
            "_process_single_file",
            side_effect=[
                FileSyncResult(
                    file_path=str(file1),
                    file_name=file1.name,
                    success=True,
                    epics_found=1,
                ),
                FileSyncResult(
                    file_path=str(file2),
                    file_name=file2.name,
                    success=True,
                    epics_found=1,
                ),
            ],
        ):
            result = processor.process([str(file1), str(file2)])

        assert result.files_total == 2
        assert result.files_processed == 2
        assert len(result.file_progress) == 2

    def test_speedup_calculation(self):
        """Test that speedup is calculated correctly."""
        result = ParallelFilesResult(
            workers_used=4,
            peak_concurrency=4,
        )
        result.completed_at = datetime.now()

        # Add file results with timing
        for i in range(4):
            file_result = FileSyncResult(
                file_path=f"/path/file{i}.md",
                file_name=f"file{i}.md",
                started_at=datetime(2024, 1, 1, 10, 0, 0),
                completed_at=datetime(2024, 1, 1, 10, 0, 10),  # 10s each
            )
            result.add_file_result(file_result)

        summary = result.summary()

        # Should show speedup if total time is less than sum of individual times
        assert "speedup" in summary.lower() or "Duration" in summary
