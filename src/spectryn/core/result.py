"""
Result Type Pattern for spectra.

Provides a Result[T, E] type for explicit error handling without exceptions.
Inspired by Rust's Result type and functional programming patterns.

Benefits:
- Explicit error handling - errors are part of the type signature
- Composable - chain operations with map, and_then, etc.
- No hidden control flow - errors are values, not exceptions
- Better for async/parallel - errors don't interrupt batches

Usage:
    # Creating results
    result = Ok(42)                    # Success
    result = Err(MyError("oops"))      # Failure

    # Pattern matching
    match result:
        case Ok(value):
            print(f"Got {value}")
        case Err(error):
            print(f"Error: {error}")

    # Chaining operations
    result = (
        get_user(user_id)
        .and_then(lambda user: get_profile(user.profile_id))
        .map(lambda profile: profile.display_name)
        .unwrap_or("Unknown")
    )

    # Collecting multiple results
    results = [get_user(id) for id in user_ids]
    combined = Result.collect(results)  # Result[list[User], Error]

This module is designed to work alongside exceptions, not replace them entirely.
Use Result for operations where errors are expected and should be handled,
and exceptions for truly exceptional conditions.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import (
    Any,
    Generic,
    TypeVar,
    cast,
)


# Type variables
T = TypeVar("T")  # Success type
E = TypeVar("E")  # Error type
U = TypeVar("U")  # Mapped success type
F = TypeVar("F")  # Mapped error type


class ResultError(Exception):
    """Raised when unwrapping a Result fails."""


class Result(ABC, Generic[T, E]):
    """
    A Result type that represents either success (Ok) or failure (Err).

    This is an abstract base class - use Ok() and Err() to create instances.

    Type Parameters:
        T: The type of the success value
        E: The type of the error value

    Example:
        >>> def divide(a: int, b: int) -> Result[float, str]:
        ...     if b == 0:
        ...         return Err("Division by zero")
        ...     return Ok(a / b)
        ...
        >>> result = divide(10, 2)
        >>> print(result.unwrap())  # 5.0
    """

    __slots__ = ()

    # -------------------------------------------------------------------------
    # Abstract Methods
    # -------------------------------------------------------------------------

    @abstractmethod
    def is_ok(self) -> bool:
        """Return True if the result is Ok."""
        ...

    @abstractmethod
    def is_err(self) -> bool:
        """Return True if the result is Err."""
        ...

    @abstractmethod
    def ok(self) -> T | None:
        """Return the contained Ok value, or None if Err."""
        ...

    @abstractmethod
    def err(self) -> E | None:
        """Return the contained Err value, or None if Ok."""
        ...

    # -------------------------------------------------------------------------
    # Unwrapping
    # -------------------------------------------------------------------------

    @abstractmethod
    def unwrap(self) -> T:
        """
        Return the contained Ok value.

        Raises:
            ResultError: If the result is Err
        """
        ...

    @abstractmethod
    def unwrap_err(self) -> E:
        """
        Return the contained Err value.

        Raises:
            ResultError: If the result is Ok
        """
        ...

    @abstractmethod
    def unwrap_or(self, default: T) -> T:
        """Return the contained Ok value or a default."""
        ...

    @abstractmethod
    def unwrap_or_else(self, f: Callable[[E], T]) -> T:
        """Return the contained Ok value or compute from error."""
        ...

    @abstractmethod
    def expect(self, msg: str) -> T:
        """
        Return the contained Ok value.

        Args:
            msg: Error message if Err

        Raises:
            ResultError: With custom message if Err
        """
        ...

    # -------------------------------------------------------------------------
    # Transformations
    # -------------------------------------------------------------------------

    @abstractmethod
    def map(self, f: Callable[[T], U]) -> Result[U, E]:
        """
        Map a function over the Ok value.

        If Ok, returns Ok(f(value)).
        If Err, returns Err unchanged.
        """
        ...

    @abstractmethod
    def map_err(self, f: Callable[[E], F]) -> Result[T, F]:
        """
        Map a function over the Err value.

        If Err, returns Err(f(error)).
        If Ok, returns Ok unchanged.
        """
        ...

    @abstractmethod
    def and_then(self, f: Callable[[T], Result[U, E]]) -> Result[U, E]:
        """
        Chain another Result-returning operation.

        If Ok, returns f(value).
        If Err, returns Err unchanged.

        Also known as flatMap or bind.
        """
        ...

    @abstractmethod
    def or_else(self, f: Callable[[E], Result[T, F]]) -> Result[T, F]:
        """
        Chain an error recovery operation.

        If Ok, returns Ok unchanged.
        If Err, returns f(error).
        """
        ...

    # -------------------------------------------------------------------------
    # Inspection
    # -------------------------------------------------------------------------

    @abstractmethod
    def inspect(self, f: Callable[[T], None]) -> Result[T, E]:
        """
        Call a function on Ok value for side effects.

        Returns self unchanged.
        """
        ...

    @abstractmethod
    def inspect_err(self, f: Callable[[E], None]) -> Result[T, E]:
        """
        Call a function on Err value for side effects.

        Returns self unchanged.
        """
        ...

    # -------------------------------------------------------------------------
    # Conversion
    # -------------------------------------------------------------------------

    def to_optional(self) -> T | None:
        """Convert to Optional, discarding error info."""
        return self.ok()

    def to_exception(
        self, exception_factory: Callable[[E], Exception] = lambda e: ResultError(str(e))
    ) -> T:
        """
        Convert to value or raise exception.

        Useful for bridging Result to exception-based code.
        """
        if self.is_ok():
            return self.unwrap()
        raise exception_factory(self.unwrap_err())

    # -------------------------------------------------------------------------
    # Static Methods
    # -------------------------------------------------------------------------

    @staticmethod
    def collect(results: list[Result[T, E]]) -> Result[list[T], E]:
        """
        Collect a list of Results into a Result of list.

        Returns Ok(list of values) if all are Ok.
        Returns first Err if any is Err.

        Example:
            >>> results = [Ok(1), Ok(2), Ok(3)]
            >>> Result.collect(results)  # Ok([1, 2, 3])

            >>> results = [Ok(1), Err("bad"), Ok(3)]
            >>> Result.collect(results)  # Err("bad")
        """
        values: list[T] = []
        for result in results:
            if result.is_err():
                return Err(result.unwrap_err())
            values.append(result.unwrap())
        return Ok(values)

    @staticmethod
    def collect_all(results: list[Result[T, E]]) -> Result[list[T], list[E]]:
        """
        Collect all results, gathering all errors if any fail.

        Returns Ok(list of values) if all are Ok.
        Returns Err(list of errors) if any are Err.

        Example:
            >>> results = [Ok(1), Err("bad"), Err("worse")]
            >>> Result.collect_all(results)  # Err(["bad", "worse"])
        """
        values: list[T] = []
        errors: list[E] = []

        for result in results:
            if result.is_ok():
                values.append(result.unwrap())
            else:
                errors.append(result.unwrap_err())

        if errors:
            return Err(errors)
        return Ok(values)

    @staticmethod
    def from_optional(
        value: T | None,
        error: E,
    ) -> Result[T, E]:
        """
        Create a Result from an Optional value.

        Args:
            value: The optional value
            error: Error to use if value is None

        Returns:
            Ok(value) if value is not None, Err(error) otherwise
        """
        if value is not None:
            return Ok(value)
        return Err(error)

    @staticmethod
    def try_call(
        f: Callable[[], T],
        error_factory: Callable[[Exception], E] = lambda e: cast(E, e),
    ) -> Result[T, E]:
        """
        Wrap a function call that may raise an exception.

        Args:
            f: Function to call
            error_factory: Convert exception to error type

        Returns:
            Ok(result) if successful, Err(error) if exception raised

        Example:
            >>> result = Result.try_call(lambda: int("abc"))
            >>> result.is_err()  # True
        """
        try:
            return Ok(f())
        except Exception as e:
            return Err(error_factory(e))


@dataclass(frozen=True, slots=True)
class Ok(Result[T, Any]):
    """
    Success variant of Result.

    Contains the success value. All operations that depend on the value
    will use this value, while error-handling operations pass through unchanged.

    Example:
        >>> result = Ok(42)
        >>> result.unwrap()  # 42
        >>> result.map(lambda x: x * 2)  # Ok(84)
    """

    _value: T

    def is_ok(self) -> bool:
        """Return True since this is the Ok variant."""
        return True

    def is_err(self) -> bool:
        """Return False since this is the Ok variant."""
        return False

    def ok(self) -> T | None:
        """Return the contained value."""
        return self._value

    def err(self) -> None:
        """Return None since this is the Ok variant."""
        return

    def unwrap(self) -> T:
        """Return the contained value."""
        return self._value

    def unwrap_err(self) -> Any:
        """Raise ResultError since this is the Ok variant."""
        raise ResultError(f"Called unwrap_err on Ok: {self._value}")

    def unwrap_or(self, default: T) -> T:
        """Return the contained value, ignoring the default."""
        return self._value

    def unwrap_or_else(self, f: Callable[[Any], T]) -> T:
        """Return the contained value, ignoring the fallback function."""
        return self._value

    def expect(self, msg: str) -> T:
        """Return the contained value, ignoring the error message."""
        return self._value

    def map(self, f: Callable[[T], U]) -> Result[U, Any]:
        """Apply the function to the contained value and wrap in Ok."""
        return Ok(f(self._value))

    def map_err(self, f: Callable[[Any], F]) -> Result[T, F]:
        """Return self unchanged since there's no error to map."""
        return cast(Result[T, F], self)

    def and_then(self, f: Callable[[T], Result[U, Any]]) -> Result[U, Any]:
        """Apply the function to the contained value and return the result."""
        return f(self._value)

    def or_else(self, f: Callable[[Any], Result[T, F]]) -> Result[T, F]:
        """Return self unchanged since there's no error to recover from."""
        return cast(Result[T, F], self)

    def inspect(self, f: Callable[[T], None]) -> Result[T, Any]:
        """Call the function on the contained value for side effects."""
        f(self._value)
        return self

    def inspect_err(self, f: Callable[[Any], None]) -> Result[T, Any]:
        """Return self unchanged since there's no error to inspect."""
        return self

    def __repr__(self) -> str:
        """Return a string representation of the Ok result."""
        return f"Ok({self._value!r})"

    def __bool__(self) -> bool:
        """Ok is always truthy."""
        return True


@dataclass(frozen=True, slots=True)
class Err(Result[Any, E]):
    """
    Error variant of Result.

    Contains the error value. All operations that depend on success
    will pass through unchanged, while error-handling operations use this error.

    Example:
        >>> result = Err("not found")
        >>> result.unwrap_or("default")  # "default"
        >>> result.map_err(lambda e: f"Error: {e}")  # Err("Error: not found")
    """

    _error: E

    def is_ok(self) -> bool:
        """Return False since this is the Err variant."""
        return False

    def is_err(self) -> bool:
        """Return True since this is the Err variant."""
        return True

    def ok(self) -> None:
        """Return None since this is the Err variant."""
        return

    def err(self) -> E | None:
        """Return the contained error."""
        return self._error

    def unwrap(self) -> Any:
        """Raise ResultError with the contained error."""
        raise ResultError(f"Called unwrap on Err: {self._error}")

    def unwrap_err(self) -> E:
        """Return the contained error."""
        return self._error

    def unwrap_or(self, default: Any) -> Any:
        """Return the default value since this is an error."""
        return default

    def unwrap_or_else(self, f: Callable[[E], Any]) -> Any:
        """Apply the fallback function to the error and return the result."""
        return f(self._error)

    def expect(self, msg: str) -> Any:
        """Raise ResultError with the custom message and contained error."""
        raise ResultError(f"{msg}: {self._error}")

    def map(self, f: Callable[[Any], U]) -> Result[U, E]:
        """Return self unchanged since there's no value to map."""
        return cast(Result[U, E], self)

    def map_err(self, f: Callable[[E], F]) -> Result[Any, F]:
        """Apply the function to the contained error and wrap in Err."""
        return Err(f(self._error))

    def and_then(self, f: Callable[[Any], Result[U, E]]) -> Result[U, E]:
        """Return self unchanged since there's no value to chain."""
        return cast(Result[U, E], self)

    def or_else(self, f: Callable[[E], Result[T, F]]) -> Result[T, F]:
        """Apply the recovery function to the error and return the result."""
        return f(self._error)

    def inspect(self, f: Callable[[Any], None]) -> Result[Any, E]:
        """Return self unchanged since there's no value to inspect."""
        return self

    def inspect_err(self, f: Callable[[E], None]) -> Result[Any, E]:
        """Call the function on the contained error for side effects."""
        f(self._error)
        return self

    def __repr__(self) -> str:
        """Return a string representation of the Err result."""
        return f"Err({self._error!r})"

    def __bool__(self) -> bool:
        """Err is always falsy."""
        return False


# =============================================================================
# Operation Results - Common result types for the application
# =============================================================================


@dataclass(frozen=True)
class OperationError:
    """
    Standard error type for operations.

    Contains structured error information for consistent error handling.
    """

    code: str
    message: str
    details: dict[str, Any] | None = None
    cause: Exception | None = None

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"

    @classmethod
    def from_exception(cls, e: Exception, code: str = "UNKNOWN") -> OperationError:
        """Create from an exception."""
        return cls(
            code=code,
            message=str(e),
            cause=e,
        )

    @classmethod
    def not_found(cls, resource: str, key: str) -> OperationError:
        """Create a not-found error."""
        return cls(
            code="NOT_FOUND",
            message=f"{resource} not found: {key}",
            details={"resource": resource, "key": key},
        )

    @classmethod
    def validation(cls, message: str, field: str | None = None) -> OperationError:
        """Create a validation error."""
        return cls(
            code="VALIDATION",
            message=message,
            details={"field": field} if field else None,
        )

    @classmethod
    def permission(cls, action: str, resource: str) -> OperationError:
        """Create a permission error."""
        return cls(
            code="PERMISSION",
            message=f"Permission denied: cannot {action} {resource}",
            details={"action": action, "resource": resource},
        )

    @classmethod
    def network(cls, message: str, status_code: int | None = None) -> OperationError:
        """Create a network error."""
        return cls(
            code="NETWORK",
            message=message,
            details={"status_code": status_code} if status_code else None,
        )


# Type alias for common operation result
OperationResult = Result[T, OperationError]


@dataclass(frozen=True)
class BatchItem(Generic[T]):
    """Result of a single item in a batch operation."""

    key: str
    result: Result[T, OperationError]

    @property
    def is_success(self) -> bool:
        return self.result.is_ok()

    @property
    def value(self) -> T | None:
        return self.result.ok()

    @property
    def error(self) -> OperationError | None:
        return self.result.err()


@dataclass
class BatchResult(Generic[T]):
    """
    Result of a batch operation.

    Contains individual results for each item, plus aggregate statistics.
    """

    items: list[BatchItem[T]]

    @property
    def succeeded(self) -> list[BatchItem[T]]:
        """Get all successful items."""
        return [item for item in self.items if item.is_success]

    @property
    def failed(self) -> list[BatchItem[T]]:
        """Get all failed items."""
        return [item for item in self.items if not item.is_success]

    @property
    def success_count(self) -> int:
        return len(self.succeeded)

    @property
    def failure_count(self) -> int:
        return len(self.failed)

    @property
    def total_count(self) -> int:
        return len(self.items)

    @property
    def all_succeeded(self) -> bool:
        return self.failure_count == 0

    @property
    def all_failed(self) -> bool:
        return self.success_count == 0

    def values(self) -> list[T]:
        """Get all successful values."""
        return [item.value for item in self.succeeded if item.value is not None]

    def errors(self) -> list[OperationError]:
        """Get all errors."""
        return [item.error for item in self.failed if item.error is not None]

    def to_result(self) -> Result[list[T], list[OperationError]]:
        """
        Convert to a single Result.

        Returns Ok with all values if all succeeded.
        Returns Err with all errors if any failed.
        """
        if self.all_succeeded:
            return Ok(self.values())
        return Err(self.errors())


# =============================================================================
# Async Result Utilities
# =============================================================================


async def async_try_call(
    coro: Any,  # Coroutine
    error_factory: Callable[[Exception], E] = lambda e: cast(E, e),
) -> Result[T, E]:
    """
    Wrap an async coroutine that may raise an exception.

    Args:
        coro: Async coroutine to await
        error_factory: Convert exception to error type

    Returns:
        Ok(result) if successful, Err(error) if exception raised
    """
    try:
        value = await coro
        return Ok(value)
    except Exception as e:
        return Err(error_factory(e))


__all__ = [
    "BatchItem",
    "BatchResult",
    "Err",
    "Ok",
    # Operation types
    "OperationError",
    "OperationResult",
    # Core types
    "Result",
    "ResultError",
    # Async utilities
    "async_try_call",
]
