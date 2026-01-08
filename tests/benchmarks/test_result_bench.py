"""
Benchmarks for the Result type.

Tests performance of Result operations including:
- Creation (Ok/Err)
- Transformations (map, and_then)
- Collection (collect, collect_all)
- Unwrapping

Run with:
    pytest tests/benchmarks/ -v -m benchmark --benchmark-enable
"""

import pytest

from spectryn.core.result import Err, Ok, Result


# Mark all tests in this module as benchmark tests (skipped by default)
pytestmark = pytest.mark.benchmark


# =============================================================================
# Creation Benchmarks
# =============================================================================


class TestResultCreation:
    """Benchmark Result creation operations."""

    def test_ok_creation(self, benchmark):
        """Benchmark creating Ok results."""
        benchmark(Ok, 42)

    def test_err_creation(self, benchmark):
        """Benchmark creating Err results."""
        benchmark(Err, "error message")

    def test_ok_creation_complex(self, benchmark):
        """Benchmark creating Ok with complex data."""
        data = {"key": "value", "nested": {"a": 1, "b": 2}, "list": [1, 2, 3]}
        benchmark(Ok, data)


# =============================================================================
# Transformation Benchmarks
# =============================================================================


class TestResultTransformations:
    """Benchmark Result transformation operations."""

    def test_map_ok(self, benchmark):
        """Benchmark map on Ok."""
        result = Ok(42)
        benchmark(result.map, lambda x: x * 2)

    def test_map_err(self, benchmark):
        """Benchmark map on Err (should short-circuit)."""
        result = Err("error")
        benchmark(result.map, lambda x: x * 2)

    def test_and_then_ok(self, benchmark):
        """Benchmark and_then on Ok."""
        result = Ok(42)
        benchmark(result.and_then, lambda x: Ok(x * 2))

    def test_and_then_err(self, benchmark):
        """Benchmark and_then on Err (should short-circuit)."""
        result = Err("error")
        benchmark(result.and_then, lambda x: Ok(x * 2))

    def test_map_chain(self, benchmark):
        """Benchmark chained map operations."""
        result = Ok(1)

        def chain():
            return result.map(lambda x: x + 1).map(lambda x: x * 2).map(lambda x: x**2).map(str)

        benchmark(chain)

    def test_and_then_chain(self, benchmark):
        """Benchmark chained and_then operations."""
        result = Ok(1)

        def chain():
            return (
                result.and_then(lambda x: Ok(x + 1))
                .and_then(lambda x: Ok(x * 2))
                .and_then(lambda x: Ok(x**2))
            )

        benchmark(chain)


# =============================================================================
# Collection Benchmarks
# =============================================================================


class TestResultCollection:
    """Benchmark Result collection operations."""

    def test_collect_small_all_ok(self, benchmark, result_list_small):
        """Benchmark collect on 100 all-Ok results."""
        all_ok = [Ok(i) for i in range(100)]
        benchmark(Result.collect, all_ok)

    def test_collect_small_with_errors(self, benchmark, result_list_small):
        """Benchmark collect on 100 results with some errors."""
        benchmark(Result.collect, result_list_small)

    def test_collect_medium_all_ok(self, benchmark):
        """Benchmark collect on 1000 all-Ok results."""
        all_ok = [Ok(i) for i in range(1000)]
        benchmark(Result.collect, all_ok)

    def test_collect_all_small(self, benchmark, result_list_small):
        """Benchmark collect_all on 100 results."""
        benchmark(Result.collect_all, result_list_small)

    def test_collect_all_medium(self, benchmark, result_list_medium):
        """Benchmark collect_all on 1000 results."""
        benchmark(Result.collect_all, result_list_medium)


# =============================================================================
# Unwrapping Benchmarks
# =============================================================================


class TestResultUnwrapping:
    """Benchmark Result unwrapping operations."""

    def test_unwrap_ok(self, benchmark):
        """Benchmark unwrap on Ok."""
        result = Ok(42)
        benchmark(result.unwrap)

    def test_unwrap_or_ok(self, benchmark):
        """Benchmark unwrap_or on Ok."""
        result = Ok(42)
        benchmark(result.unwrap_or, 0)

    def test_unwrap_or_err(self, benchmark):
        """Benchmark unwrap_or on Err."""
        result = Err("error")
        benchmark(result.unwrap_or, 0)

    def test_unwrap_or_else_err(self, benchmark):
        """Benchmark unwrap_or_else on Err."""
        result = Err("error")
        benchmark(result.unwrap_or_else, lambda e: len(e))


# =============================================================================
# Factory Benchmarks
# =============================================================================


class TestResultFactories:
    """Benchmark Result factory methods."""

    def test_from_optional_some(self, benchmark):
        """Benchmark from_optional with value."""
        benchmark(Result.from_optional, 42, "was none")

    def test_from_optional_none(self, benchmark):
        """Benchmark from_optional with None."""
        benchmark(Result.from_optional, None, "was none")

    def test_try_call_success(self, benchmark):
        """Benchmark try_call with success."""
        benchmark(Result.try_call, lambda: 42)

    def test_try_call_exception(self, benchmark):
        """Benchmark try_call with exception."""

        def throw():
            raise ValueError("error")

        benchmark(Result.try_call, throw)
