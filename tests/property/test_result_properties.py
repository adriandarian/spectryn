"""
Property-based tests for the Result type.

Tests algebraic laws that Result should satisfy:
- Functor laws (map)
- Monad laws (and_then)
- Various invariants
"""

from hypothesis import assume, given
from hypothesis import strategies as st

from spectryn.core.result import Err, Ok, Result


# =============================================================================
# Strategies
# =============================================================================

# Strategy for any JSON-serializable value
json_values = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False) | st.text(),
    lambda children: st.lists(children) | st.dictionaries(st.text(), children),
    max_leaves=10,
)

# Strategy for simple values
simple_values = st.one_of(
    st.integers(),
    st.text(max_size=100),
    st.booleans(),
    st.floats(allow_nan=False, allow_infinity=False),
)

# Strategy for error messages
error_messages = st.text(min_size=1, max_size=100)

# Strategy for Ok results
ok_results = simple_values.map(Ok)

# Strategy for Err results
err_results = error_messages.map(Err)

# Strategy for any Result
any_result = st.one_of(ok_results, err_results)


# =============================================================================
# Functor Laws
# =============================================================================


class TestFunctorLaws:
    """
    Result should satisfy the Functor laws:
    1. Identity: result.map(id) == result
    2. Composition: result.map(f).map(g) == result.map(lambda x: g(f(x)))
    """

    @given(simple_values)
    def test_identity_law_ok(self, value):
        """map(id) should return the same result for Ok."""
        result = Ok(value)
        mapped = result.map(lambda x: x)

        assert mapped.is_ok()
        assert mapped.unwrap() == value

    @given(error_messages)
    def test_identity_law_err(self, error):
        """map(id) should return the same result for Err."""
        result: Result[int, str] = Err(error)
        mapped = result.map(lambda x: x)

        assert mapped.is_err()
        assert mapped.unwrap_err() == error

    @given(st.integers())
    def test_composition_law_ok(self, value):
        """map(f).map(g) == map(g ∘ f) for Ok."""

        def f(x):
            return x * 2

        def g(x):
            return x + 10

        result = Ok(value)

        # Map separately
        mapped_separate = result.map(f).map(g)

        # Map composed
        mapped_composed = result.map(lambda x: g(f(x)))

        assert mapped_separate.unwrap() == mapped_composed.unwrap()

    @given(st.integers(), error_messages)
    def test_composition_law_err(self, value, error):
        """map(f).map(g) == map(g ∘ f) for Err (both should be Err)."""

        def f(x):
            return x * 2

        def g(x):
            return x + 10

        result: Result[int, str] = Err(error)

        mapped_separate = result.map(f).map(g)
        mapped_composed = result.map(lambda x: g(f(x)))

        assert mapped_separate.is_err()
        assert mapped_composed.is_err()
        assert mapped_separate.unwrap_err() == mapped_composed.unwrap_err()


# =============================================================================
# Monad Laws
# =============================================================================


class TestMonadLaws:
    """
    Result should satisfy the Monad laws:
    1. Left identity: Ok(a).and_then(f) == f(a)
    2. Right identity: m.and_then(Ok) == m
    3. Associativity: m.and_then(f).and_then(g) == m.and_then(λx. f(x).and_then(g))
    """

    @given(st.integers())
    def test_left_identity(self, value):
        """Ok(a).and_then(f) == f(a)."""

        def f(x):
            return Ok(x * 2) if x > 0 else Err("non-positive")

        left = Ok(value).and_then(f)
        right = f(value)

        assert left.is_ok() == right.is_ok()
        if left.is_ok():
            assert left.unwrap() == right.unwrap()
        else:
            assert left.unwrap_err() == right.unwrap_err()

    @given(st.integers())
    def test_right_identity_ok(self, value):
        """m.and_then(Ok) == m for Ok."""
        m = Ok(value)
        result = m.and_then(Ok)

        assert result.is_ok()
        assert result.unwrap() == value

    @given(error_messages)
    def test_right_identity_err(self, error):
        """m.and_then(Ok) == m for Err."""
        m: Result[int, str] = Err(error)
        result = m.and_then(Ok)

        assert result.is_err()
        assert result.unwrap_err() == error

    @given(st.integers())
    def test_associativity(self, value):
        """m.and_then(f).and_then(g) == m.and_then(λx. f(x).and_then(g))."""

        def f(x):
            return Ok(x + 1)

        def g(x):
            return Ok(x * 2)

        m = Ok(value)

        # Left association
        left = m.and_then(f).and_then(g)

        # Right association
        right = m.and_then(lambda x: f(x).and_then(g))

        assert left.is_ok() == right.is_ok()
        if left.is_ok():
            assert left.unwrap() == right.unwrap()


# =============================================================================
# Result Invariants
# =============================================================================


class TestResultInvariants:
    """Test invariants that should always hold for Result."""

    @given(simple_values)
    def test_ok_is_ok(self, value):
        """Ok is always is_ok and never is_err."""
        result = Ok(value)
        assert result.is_ok()
        assert not result.is_err()

    @given(error_messages)
    def test_err_is_err(self, error):
        """Err is always is_err and never is_ok."""
        result = Err(error)
        assert result.is_err()
        assert not result.is_ok()

    @given(simple_values)
    def test_ok_unwrap_returns_value(self, value):
        """unwrap on Ok returns the contained value."""
        result = Ok(value)
        assert result.unwrap() == value

    @given(error_messages)
    def test_err_unwrap_err_returns_error(self, error):
        """unwrap_err on Err returns the contained error."""
        result = Err(error)
        assert result.unwrap_err() == error

    @given(simple_values)
    def test_ok_optional_returns_value(self, value):
        """ok() on Ok returns the value."""
        result = Ok(value)
        assert result.ok() == value

    @given(error_messages)
    def test_err_optional_returns_none(self, error):
        """ok() on Err returns None."""
        result = Err(error)
        assert result.ok() is None

    @given(simple_values, simple_values)
    def test_unwrap_or_ok(self, value, default):
        """unwrap_or on Ok returns the value, not default."""
        result = Ok(value)
        assert result.unwrap_or(default) == value

    @given(error_messages, simple_values)
    def test_unwrap_or_err(self, error, default):
        """unwrap_or on Err returns the default."""
        result: Result[type(default), str] = Err(error)
        assert result.unwrap_or(default) == default

    @given(simple_values)
    def test_ok_bool_is_truthy(self, value):
        """Ok is truthy."""
        assert bool(Ok(value))

    @given(error_messages)
    def test_err_bool_is_falsy(self, error):
        """Err is falsy."""
        assert not bool(Err(error))


# =============================================================================
# Collection Properties
# =============================================================================


class TestCollectProperties:
    """Test properties of collect operations."""

    @given(st.lists(st.integers(), min_size=0, max_size=20))
    def test_collect_all_ok(self, values):
        """Collecting all Ok results gives Ok with all values."""
        results = [Ok(v) for v in values]
        combined = Result.collect(results)

        assert combined.is_ok()
        assert combined.unwrap() == values

    @given(st.lists(st.integers(), min_size=1, max_size=20), st.integers(min_value=0))
    def test_collect_with_err_fails(self, values, err_index):
        """Collecting with any Err gives Err."""
        assume(len(values) > 0)
        err_index = err_index % len(values)

        results: list[Result[int, str]] = [Ok(v) for v in values]
        results[err_index] = Err("error")

        combined = Result.collect(results)

        assert combined.is_err()
        assert combined.unwrap_err() == "error"

    @given(st.lists(st.integers(), min_size=0, max_size=20))
    def test_collect_all_gathers_all_values(self, values):
        """collect_all with all Ok gives Ok with all values."""
        results = [Ok(v) for v in values]
        combined = Result.collect_all(results)

        assert combined.is_ok()
        assert combined.unwrap() == values


# =============================================================================
# Map Error Properties
# =============================================================================


class TestMapErrProperties:
    """Test map_err properties."""

    @given(simple_values, error_messages)
    def test_map_err_on_ok_is_identity(self, value, _):
        """map_err on Ok should not change anything."""
        result = Ok(value)
        mapped = result.map_err(lambda e: f"wrapped: {e}")

        assert mapped.is_ok()
        assert mapped.unwrap() == value

    @given(error_messages)
    def test_map_err_transforms_error(self, error):
        """map_err on Err should transform the error."""
        result: Result[int, str] = Err(error)
        mapped = result.map_err(lambda e: f"wrapped: {e}")

        assert mapped.is_err()
        assert mapped.unwrap_err() == f"wrapped: {error}"


# =============================================================================
# Or Else Properties
# =============================================================================


class TestOrElseProperties:
    """Test or_else properties."""

    @given(simple_values)
    def test_or_else_on_ok_returns_ok(self, value):
        """or_else on Ok should return Ok unchanged."""
        result = Ok(value)
        recovered = result.or_else(lambda e: Ok("recovered"))

        assert recovered.is_ok()
        assert recovered.unwrap() == value

    @given(error_messages, simple_values)
    def test_or_else_on_err_recovers(self, error, recovery):
        """or_else on Err should apply recovery function."""
        result: Result[type(recovery), str] = Err(error)
        recovered = result.or_else(lambda e: Ok(recovery))

        assert recovered.is_ok()
        assert recovered.unwrap() == recovery


# =============================================================================
# Try Call Properties
# =============================================================================


class TestTryCallProperties:
    """Test try_call properties."""

    @given(simple_values)
    def test_try_call_success(self, value):
        """try_call with non-throwing function returns Ok."""
        result = Result.try_call(lambda: value)

        assert result.is_ok()
        assert result.unwrap() == value

    @given(error_messages)
    def test_try_call_exception(self, message):
        """try_call with throwing function returns Err."""

        def throw():
            raise ValueError(message)

        result = Result.try_call(throw)

        assert result.is_err()
        assert isinstance(result.unwrap_err(), ValueError)


# =============================================================================
# From Optional Properties
# =============================================================================


class TestFromOptionalProperties:
    """Test from_optional properties."""

    @given(simple_values, error_messages)
    def test_from_optional_some(self, value, error):
        """from_optional with value returns Ok."""
        result = Result.from_optional(value, error)

        assert result.is_ok()
        assert result.unwrap() == value

    @given(error_messages)
    def test_from_optional_none(self, error):
        """from_optional with None returns Err."""
        result = Result.from_optional(None, error)

        assert result.is_err()
        assert result.unwrap_err() == error
