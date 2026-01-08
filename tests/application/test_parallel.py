"""Tests for parallel sync operations."""

import pytest

from spectryn.application.sync.parallel import (
    EpicProgress,
    ParallelSyncConfig,
    ParallelSyncResult,
    is_parallel_available,
    run_async,
)


class TestParallelSyncResult:
    """Tests for ParallelSyncResult dataclass."""

    def test_default_values(self) -> None:
        """Test default values."""
        result = ParallelSyncResult()

        assert result.workers_used == 0
        assert result.peak_concurrency == 0
        assert result.epic_progress == []

    def test_with_data(self) -> None:
        """Test with data."""
        progress = [
            EpicProgress(epic_key="PROJ-1", epic_title="Epic 1", status="completed"),
            EpicProgress(epic_key="PROJ-2", epic_title="Epic 2", status="completed"),
        ]
        result = ParallelSyncResult(
            workers_used=4,
            peak_concurrency=2,
            epic_progress=progress,
        )

        assert result.workers_used == 4
        assert result.peak_concurrency == 2
        assert len(result.epic_progress) == 2

    def test_parallel_config(self) -> None:
        """Test parallel config is included."""
        config = ParallelSyncConfig(max_workers=8, fail_fast=True)
        result = ParallelSyncResult(parallel_config=config)

        assert result.parallel_config.max_workers == 8
        assert result.parallel_config.fail_fast is True

    def test_summary(self) -> None:
        """Test summary method."""
        result = ParallelSyncResult(
            workers_used=4,
            peak_concurrency=2,
        )

        summary = result.summary()

        assert "Workers: 4" in summary
        assert "Peak concurrency: 2" in summary


class TestRunAsync:
    """Tests for run_async helper function."""

    def test_run_async_success(self) -> None:
        """Test run_async executes coroutine."""

        async def simple_coro():
            return 42

        result = run_async(simple_coro())
        assert result == 42

    def test_run_async_with_exception(self) -> None:
        """Test run_async propagates exceptions."""

        async def failing_coro():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            run_async(failing_coro())


class TestIsParallelAvailable:
    """Tests for is_parallel_available function."""

    def test_is_parallel_available(self) -> None:
        """Test is_parallel_available returns boolean."""
        result = is_parallel_available()

        assert isinstance(result, bool)
        # May or may not be available depending on environment

    def test_returns_consistent_value(self) -> None:
        """Test returns same value on multiple calls."""
        result1 = is_parallel_available()
        result2 = is_parallel_available()

        assert result1 == result2
