"""Tests for parallel sync operations."""

import pytest

from spectra.application.sync.parallel import (
    ParallelSyncResult,
    is_parallel_available,
    run_async,
)


class TestParallelSyncResult:
    """Tests for ParallelSyncResult dataclass."""

    def test_default_values(self) -> None:
        """Test default values."""
        result = ParallelSyncResult(operation="test")

        assert result.operation == "test"
        assert result.total == 0
        assert result.successful == 0
        assert result.failed == 0
        assert result.results == []
        assert result.errors == []

    def test_with_data(self) -> None:
        """Test with data."""
        result = ParallelSyncResult(
            operation="fetch_issues",
            total=10,
            successful=8,
            failed=2,
            results=[{"key": "PROJ-1"}, {"key": "PROJ-2"}],
            errors=[("PROJ-3", "Not found"), ("PROJ-4", "Timeout")],
        )

        assert result.total == 10
        assert result.successful == 8
        assert result.failed == 2
        assert len(result.results) == 2
        assert len(result.errors) == 2

    def test_success_rate(self) -> None:
        """Test success rate calculation."""
        result = ParallelSyncResult(operation="test", total=10, successful=8, failed=2)

        assert result.success_rate == 0.8

    def test_success_rate_no_total(self) -> None:
        """Test success rate with zero total."""
        result = ParallelSyncResult(operation="test", total=0)

        assert result.success_rate == 1.0

    def test_all_succeeded_true(self) -> None:
        """Test all_succeeded when no failures."""
        result = ParallelSyncResult(operation="test", total=5, successful=5, failed=0)

        assert result.all_succeeded is True

    def test_all_succeeded_false(self) -> None:
        """Test all_succeeded when has failures."""
        result = ParallelSyncResult(operation="test", total=5, successful=4, failed=1)

        assert result.all_succeeded is False

    def test_str_representation(self) -> None:
        """Test string representation."""
        result = ParallelSyncResult(
            operation="update_descriptions", total=10, successful=8, failed=2
        )

        result_str = str(result)

        assert "update_descriptions" in result_str
        assert "8/10" in result_str
        assert "2 failed" in result_str


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
