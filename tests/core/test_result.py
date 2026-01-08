"""Tests for the Result type pattern."""

import pytest

from spectryn.core.result import (
    BatchItem,
    BatchResult,
    Err,
    Ok,
    OperationError,
    Result,
    ResultError,
)


# =============================================================================
# Ok Tests
# =============================================================================


class TestOk:
    """Test the Ok variant."""

    def test_is_ok(self):
        result = Ok(42)
        assert result.is_ok()
        assert not result.is_err()

    def test_ok_returns_value(self):
        result = Ok(42)
        assert result.ok() == 42

    def test_err_returns_none(self):
        result = Ok(42)
        assert result.err() is None

    def test_unwrap(self):
        result = Ok(42)
        assert result.unwrap() == 42

    def test_unwrap_err_raises(self):
        result = Ok(42)
        with pytest.raises(ResultError):
            result.unwrap_err()

    def test_unwrap_or_returns_value(self):
        result = Ok(42)
        assert result.unwrap_or(0) == 42

    def test_expect(self):
        result = Ok(42)
        assert result.expect("should have value") == 42

    def test_bool_is_truthy(self):
        result = Ok(42)
        assert bool(result)

    def test_repr(self):
        result = Ok(42)
        assert repr(result) == "Ok(42)"


# =============================================================================
# Err Tests
# =============================================================================


class TestErr:
    """Test the Err variant."""

    def test_is_err(self):
        result = Err("error")
        assert result.is_err()
        assert not result.is_ok()

    def test_ok_returns_none(self):
        result = Err("error")
        assert result.ok() is None

    def test_err_returns_error(self):
        result = Err("error")
        assert result.err() == "error"

    def test_unwrap_raises(self):
        result = Err("error")
        with pytest.raises(ResultError) as exc:
            result.unwrap()
        assert "error" in str(exc.value)

    def test_unwrap_err(self):
        result = Err("error")
        assert result.unwrap_err() == "error"

    def test_unwrap_or_returns_default(self):
        result = Err("error")
        assert result.unwrap_or(0) == 0

    def test_expect_raises_with_message(self):
        result = Err("error")
        with pytest.raises(ResultError) as exc:
            result.expect("custom message")
        assert "custom message" in str(exc.value)

    def test_bool_is_falsy(self):
        result = Err("error")
        assert not bool(result)

    def test_repr(self):
        result = Err("error")
        assert repr(result) == "Err('error')"


# =============================================================================
# Transformation Tests
# =============================================================================


class TestTransformations:
    """Test map, and_then, etc."""

    def test_map_ok(self):
        result = Ok(21).map(lambda x: x * 2)
        assert result.unwrap() == 42

    def test_map_err_unchanged(self):
        result: Result[int, str] = Err("error")
        mapped = result.map(lambda x: x * 2)
        assert mapped.is_err()
        assert mapped.unwrap_err() == "error"

    def test_map_err_ok_unchanged(self):
        result = Ok(42)
        mapped = result.map_err(lambda e: f"wrapped: {e}")
        assert mapped.is_ok()
        assert mapped.unwrap() == 42

    def test_map_err_transforms_error(self):
        result: Result[int, str] = Err("error")
        mapped = result.map_err(lambda e: f"wrapped: {e}")
        assert mapped.unwrap_err() == "wrapped: error"

    def test_and_then_ok(self):
        def double_if_positive(x: int) -> Result[int, str]:
            if x > 0:
                return Ok(x * 2)
            return Err("must be positive")

        result = Ok(21).and_then(double_if_positive)
        assert result.unwrap() == 42

    def test_and_then_short_circuits_on_err(self):
        called = False

        def should_not_call(x: int) -> Result[int, str]:
            nonlocal called
            called = True
            return Ok(x)

        result: Result[int, str] = Err("error")
        result.and_then(should_not_call)

        assert not called

    def test_or_else_ok_unchanged(self):
        result = Ok(42)
        recovered = result.or_else(lambda e: Ok(0))
        assert recovered.unwrap() == 42

    def test_or_else_recovers_from_err(self):
        result: Result[int, str] = Err("error")
        recovered = result.or_else(lambda e: Ok(0))
        assert recovered.unwrap() == 0

    def test_unwrap_or_else(self):
        result: Result[int, str] = Err("error")
        value = result.unwrap_or_else(lambda e: len(e))
        assert value == 5  # len("error")


# =============================================================================
# Inspection Tests
# =============================================================================


class TestInspection:
    """Test inspect methods."""

    def test_inspect_ok(self):
        inspected = []
        result = Ok(42).inspect(lambda x: inspected.append(x))
        assert inspected == [42]
        assert result.unwrap() == 42

    def test_inspect_not_called_on_err(self):
        inspected = []
        result: Result[int, str] = Err("error")
        result.inspect(lambda x: inspected.append(x))
        assert inspected == []

    def test_inspect_err(self):
        inspected = []
        result: Result[int, str] = Err("error")
        result.inspect_err(lambda e: inspected.append(e))
        assert inspected == ["error"]

    def test_inspect_err_not_called_on_ok(self):
        inspected = []
        result = Ok(42)
        result.inspect_err(lambda e: inspected.append(e))
        assert inspected == []


# =============================================================================
# Collection Tests
# =============================================================================


class TestCollect:
    """Test collect methods."""

    def test_collect_all_ok(self):
        results = [Ok(1), Ok(2), Ok(3)]
        combined = Result.collect(results)
        assert combined.unwrap() == [1, 2, 3]

    def test_collect_first_err(self):
        results: list[Result[int, str]] = [Ok(1), Err("bad"), Ok(3)]
        combined = Result.collect(results)
        assert combined.is_err()
        assert combined.unwrap_err() == "bad"

    def test_collect_all_gathers_errors(self):
        results: list[Result[int, str]] = [Ok(1), Err("bad"), Err("worse")]
        combined = Result.collect_all(results)
        assert combined.is_err()
        assert combined.unwrap_err() == ["bad", "worse"]

    def test_collect_all_with_no_errors(self):
        results = [Ok(1), Ok(2), Ok(3)]
        combined = Result.collect_all(results)
        assert combined.unwrap() == [1, 2, 3]


# =============================================================================
# Factory Tests
# =============================================================================


class TestFactories:
    """Test factory methods."""

    def test_from_optional_with_value(self):
        result = Result.from_optional(42, "was none")
        assert result.unwrap() == 42

    def test_from_optional_with_none(self):
        result = Result.from_optional(None, "was none")
        assert result.unwrap_err() == "was none"

    def test_try_call_success(self):
        result = Result.try_call(lambda: 42)
        assert result.unwrap() == 42

    def test_try_call_exception(self):
        result = Result.try_call(lambda: int("abc"))
        assert result.is_err()
        assert isinstance(result.unwrap_err(), ValueError)

    def test_try_call_with_factory(self):
        result = Result.try_call(lambda: int("abc"), error_factory=lambda e: f"parse error: {e}")
        assert "parse error" in result.unwrap_err()


# =============================================================================
# Conversion Tests
# =============================================================================


class TestConversion:
    """Test conversion methods."""

    def test_to_optional_ok(self):
        result = Ok(42)
        assert result.to_optional() == 42

    def test_to_optional_err(self):
        result = Err("error")
        assert result.to_optional() is None

    def test_to_exception_ok(self):
        result = Ok(42)
        assert result.to_exception() == 42

    def test_to_exception_err_raises(self):
        result = Err("error")
        with pytest.raises(ResultError):
            result.to_exception()

    def test_to_exception_with_factory(self):
        result = Err("not found")
        with pytest.raises(KeyError):
            result.to_exception(lambda e: KeyError(e))


# =============================================================================
# OperationError Tests
# =============================================================================


class TestOperationError:
    """Test OperationError factory methods."""

    def test_from_exception(self):
        try:
            raise ValueError("bad value")
        except ValueError as e:
            error = OperationError.from_exception(e, "VALIDATION")

        assert error.code == "VALIDATION"
        assert "bad value" in error.message
        assert error.cause is not None

    def test_not_found(self):
        error = OperationError.not_found("Issue", "PROJ-123")
        assert error.code == "NOT_FOUND"
        assert "PROJ-123" in error.message
        assert error.details["key"] == "PROJ-123"

    def test_validation(self):
        error = OperationError.validation("Invalid email", "email")
        assert error.code == "VALIDATION"
        assert error.details["field"] == "email"

    def test_permission(self):
        error = OperationError.permission("edit", "Issue")
        assert error.code == "PERMISSION"
        assert "edit" in error.message

    def test_str(self):
        error = OperationError("TEST", "Test message")
        assert str(error) == "[TEST] Test message"


# =============================================================================
# BatchResult Tests
# =============================================================================


class TestBatchResult:
    """Test BatchResult."""

    def test_succeeded(self):
        items = [
            BatchItem("a", Ok(1)),
            BatchItem("b", Err(OperationError("E", "error"))),
            BatchItem("c", Ok(3)),
        ]
        batch = BatchResult(items)

        assert batch.success_count == 2
        assert batch.failure_count == 1
        assert batch.total_count == 3

    def test_all_succeeded(self):
        items = [
            BatchItem("a", Ok(1)),
            BatchItem("b", Ok(2)),
        ]
        batch = BatchResult(items)

        assert batch.all_succeeded
        assert not batch.all_failed

    def test_all_failed(self):
        items = [
            BatchItem("a", Err(OperationError("E", "e1"))),
            BatchItem("b", Err(OperationError("E", "e2"))),
        ]
        batch = BatchResult(items)

        assert batch.all_failed
        assert not batch.all_succeeded

    def test_values(self):
        items = [
            BatchItem("a", Ok(1)),
            BatchItem("b", Err(OperationError("E", "error"))),
            BatchItem("c", Ok(3)),
        ]
        batch = BatchResult(items)

        assert batch.values() == [1, 3]

    def test_errors(self):
        items = [
            BatchItem("a", Ok(1)),
            BatchItem("b", Err(OperationError("E", "error"))),
        ]
        batch = BatchResult(items)

        assert len(batch.errors()) == 1
        assert batch.errors()[0].message == "error"

    def test_to_result_success(self):
        items = [
            BatchItem("a", Ok(1)),
            BatchItem("b", Ok(2)),
        ]
        batch = BatchResult(items)

        result = batch.to_result()
        assert result.is_ok()
        assert result.unwrap() == [1, 2]

    def test_to_result_failure(self):
        items = [
            BatchItem("a", Ok(1)),
            BatchItem("b", Err(OperationError("E", "error"))),
        ]
        batch = BatchResult(items)

        result = batch.to_result()
        assert result.is_err()
        assert len(result.unwrap_err()) == 1


# =============================================================================
# Pattern Matching Tests
# =============================================================================


class TestPatternMatching:
    """Test Python 3.10+ pattern matching."""

    def test_match_ok(self):
        result = Ok(42)

        match result:
            case Ok(value):
                matched = f"ok: {value}"
            case Err(error):
                matched = f"err: {error}"

        assert matched == "ok: 42"

    def test_match_err(self):
        result: Result[int, str] = Err("oops")

        match result:
            case Ok(value):
                matched = f"ok: {value}"
            case Err(error):
                matched = f"err: {error}"

        assert matched == "err: oops"


# =============================================================================
# Chaining Examples
# =============================================================================


class TestChaining:
    """Test realistic chaining examples."""

    def test_pipeline(self):
        """Test a realistic pipeline of operations."""

        def parse_int(s: str) -> Result[int, str]:
            try:
                return Ok(int(s))
            except ValueError:
                return Err(f"invalid integer: {s}")

        def validate_positive(n: int) -> Result[int, str]:
            if n > 0:
                return Ok(n)
            return Err("must be positive")

        def double(n: int) -> int:
            return n * 2

        # Success case
        result = parse_int("21").and_then(validate_positive).map(double)
        assert result.unwrap() == 42

        # Parse error
        result = parse_int("abc").and_then(validate_positive).map(double)
        assert "invalid integer" in result.unwrap_err()

        # Validation error
        result = parse_int("-5").and_then(validate_positive).map(double)
        assert "positive" in result.unwrap_err()
