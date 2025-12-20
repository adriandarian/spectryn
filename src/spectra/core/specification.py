"""
Specification Pattern for spectra.

The Specification pattern enables composable, reusable business rules
for filtering, matching, and validating objects.

Benefits:
- Composable: Combine specs with and_(), or_(), not_()
- Reusable: Define once, use everywhere
- Testable: Each spec is independently testable
- Readable: Express complex rules declaratively

Usage:
    # Define specifications
    is_done = StatusSpec("Done")
    is_high_priority = PrioritySpec(1, 2)
    needs_review = is_done.and_(HasLabelSpec("needs-review"))

    # Filter a list
    done_issues = [i for i in issues if is_done.is_satisfied_by(i)]

    # Or use the filter helper
    done_issues = is_done.filter(issues)

    # Combine specifications
    ready_for_release = (
        StatusSpec("Done")
        .and_(HasLabelSpec("tested"))
        .and_(HasLabelSpec("documented").not_())
    )

    # Use with any() / all()
    if any(needs_review.is_satisfied_by(i) for i in issues):
        notify_reviewers()

This module provides:
1. Base Specification class with composition operators
2. Common specifications for issues, stories, and domain objects
3. Utility functions for working with specifications
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import (
    Any,
    Generic,
    TypeVar,
)


T = TypeVar("T")


# =============================================================================
# Base Specification
# =============================================================================


class Specification(ABC, Generic[T]):
    """
    Abstract base class for specifications.

    A specification encapsulates a business rule that can be evaluated
    against a candidate object. Specifications can be combined using
    logical operators (and, or, not).

    Type Parameters:
        T: The type of object this specification applies to

    Example:
        >>> class IsAdult(Specification[Person]):
        ...     def is_satisfied_by(self, person: Person) -> bool:
        ...         return person.age >= 18
        ...
        >>> is_adult = IsAdult()
        >>> is_adult.is_satisfied_by(Person(age=21))  # True
    """

    @abstractmethod
    def is_satisfied_by(self, candidate: T) -> bool:
        """
        Check if the candidate satisfies this specification.

        Args:
            candidate: The object to check

        Returns:
            True if the specification is satisfied
        """
        ...

    def and_(self, other: Specification[T]) -> Specification[T]:
        """
        Combine with another specification using AND.

        Args:
            other: Another specification

        Returns:
            A new specification that is satisfied when both are satisfied
        """
        return AndSpecification(self, other)

    def or_(self, other: Specification[T]) -> Specification[T]:
        """
        Combine with another specification using OR.

        Args:
            other: Another specification

        Returns:
            A new specification that is satisfied when either is satisfied
        """
        return OrSpecification(self, other)

    def not_(self) -> Specification[T]:
        """
        Negate this specification.

        Returns:
            A new specification that is satisfied when this is not satisfied
        """
        return NotSpecification(self)

    def __and__(self, other: Specification[T]) -> Specification[T]:
        """Allow using & operator: spec1 & spec2."""
        return self.and_(other)

    def __or__(self, other: Specification[T]) -> Specification[T]:
        """Allow using | operator: spec1 | spec2."""
        return self.or_(other)

    def __invert__(self) -> Specification[T]:
        """Allow using ~ operator: ~spec."""
        return self.not_()

    # -------------------------------------------------------------------------
    # Collection Operations
    # -------------------------------------------------------------------------

    def filter(self, candidates: Iterable[T]) -> list[T]:
        """
        Filter a collection to only those satisfying this specification.

        Args:
            candidates: Collection to filter

        Returns:
            List of candidates that satisfy the specification
        """
        return [c for c in candidates if self.is_satisfied_by(c)]

    def any_satisfy(self, candidates: Iterable[T]) -> bool:
        """Check if any candidate satisfies this specification."""
        return any(self.is_satisfied_by(c) for c in candidates)

    def all_satisfy(self, candidates: Iterable[T]) -> bool:
        """Check if all candidates satisfy this specification."""
        return all(self.is_satisfied_by(c) for c in candidates)

    def count(self, candidates: Iterable[T]) -> int:
        """Count how many candidates satisfy this specification."""
        return sum(1 for c in candidates if self.is_satisfied_by(c))

    def first(self, candidates: Iterable[T]) -> T | None:
        """Find the first candidate that satisfies this specification."""
        for c in candidates:
            if self.is_satisfied_by(c):
                return c
        return None


# =============================================================================
# Composite Specifications
# =============================================================================


@dataclass(frozen=True)
class AndSpecification(Specification[T]):
    """Specification that requires both specs to be satisfied."""

    left: Specification[T]
    right: Specification[T]

    def is_satisfied_by(self, candidate: T) -> bool:
        return self.left.is_satisfied_by(candidate) and self.right.is_satisfied_by(candidate)

    def __repr__(self) -> str:
        return f"({self.left!r} AND {self.right!r})"


@dataclass(frozen=True)
class OrSpecification(Specification[T]):
    """Specification that requires either spec to be satisfied."""

    left: Specification[T]
    right: Specification[T]

    def is_satisfied_by(self, candidate: T) -> bool:
        return self.left.is_satisfied_by(candidate) or self.right.is_satisfied_by(candidate)

    def __repr__(self) -> str:
        return f"({self.left!r} OR {self.right!r})"


@dataclass(frozen=True)
class NotSpecification(Specification[T]):
    """Specification that negates another spec."""

    spec: Specification[T]

    def is_satisfied_by(self, candidate: T) -> bool:
        return not self.spec.is_satisfied_by(candidate)

    def __repr__(self) -> str:
        return f"(NOT {self.spec!r})"


# =============================================================================
# Factory Specifications
# =============================================================================


@dataclass(frozen=True)
class PredicateSpec(Specification[T]):
    """
    Specification from a predicate function.

    Useful for one-off specifications without creating a class.

    Example:
        >>> is_positive = PredicateSpec(lambda x: x > 0)
        >>> is_positive.is_satisfied_by(5)  # True
    """

    predicate: Callable[[T], bool]
    name: str = "predicate"

    def is_satisfied_by(self, candidate: T) -> bool:
        return self.predicate(candidate)

    def __repr__(self) -> str:
        return f"PredicateSpec({self.name})"


@dataclass(frozen=True)
class AlwaysTrue(Specification[T]):
    """Specification that always returns True."""

    def is_satisfied_by(self, candidate: T) -> bool:
        return True

    def __repr__(self) -> str:
        return "AlwaysTrue"


@dataclass(frozen=True)
class AlwaysFalse(Specification[T]):
    """Specification that always returns False."""

    def is_satisfied_by(self, candidate: T) -> bool:
        return False

    def __repr__(self) -> str:
        return "AlwaysFalse"


# =============================================================================
# Attribute Specifications
# =============================================================================


@dataclass(frozen=True)
class HasAttribute(Specification[T]):
    """Specification that checks if an object has an attribute with a value."""

    attribute: str
    value: Any

    def is_satisfied_by(self, candidate: T) -> bool:
        actual = getattr(candidate, self.attribute, None)
        return bool(actual == self.value)

    def __repr__(self) -> str:
        return f"HasAttribute({self.attribute}={self.value!r})"


@dataclass(frozen=True)
class AttributeIn(Specification[T]):
    """Specification that checks if an attribute value is in a set."""

    attribute: str
    values: frozenset[Any]

    def __init__(self, attribute: str, values: Iterable[Any]):
        object.__setattr__(self, "attribute", attribute)
        object.__setattr__(self, "values", frozenset(values))

    def is_satisfied_by(self, candidate: T) -> bool:
        actual = getattr(candidate, self.attribute, None)
        return bool(actual in self.values)

    def __repr__(self) -> str:
        return f"AttributeIn({self.attribute} in {set(self.values)!r})"


@dataclass(frozen=True)
class AttributeMatches(Specification[T]):
    """Specification that checks if an attribute matches a regex pattern."""

    attribute: str
    pattern: re.Pattern[str]

    def __init__(self, attribute: str, pattern: str | re.Pattern[str]):
        object.__setattr__(self, "attribute", attribute)
        if isinstance(pattern, str):
            object.__setattr__(self, "pattern", re.compile(pattern, re.IGNORECASE))
        else:
            object.__setattr__(self, "pattern", pattern)

    def is_satisfied_by(self, candidate: T) -> bool:
        actual = getattr(candidate, self.attribute, None)
        if actual is None:
            return False
        return bool(self.pattern.search(str(actual)))

    def __repr__(self) -> str:
        return f"AttributeMatches({self.attribute} ~ {self.pattern.pattern!r})"


@dataclass(frozen=True)
class AttributeContains(Specification[T]):
    """Specification that checks if an attribute contains a substring."""

    attribute: str
    substring: str
    case_sensitive: bool = False

    def is_satisfied_by(self, candidate: T) -> bool:
        actual = getattr(candidate, self.attribute, None)
        if actual is None:
            return False

        actual_str = str(actual)
        search_str = self.substring

        if not self.case_sensitive:
            actual_str = actual_str.lower()
            search_str = search_str.lower()

        return search_str in actual_str

    def __repr__(self) -> str:
        return f"AttributeContains({self.attribute} contains {self.substring!r})"


# =============================================================================
# Issue/Story Specifications
# =============================================================================


@dataclass(frozen=True)
class StatusSpec(Specification[Any]):
    """
    Specification for issue/story status.

    Example:
        >>> is_done = StatusSpec("Done")
        >>> is_in_progress = StatusSpec("In Progress", "In Review")
    """

    statuses: frozenset[str]

    def __init__(self, *statuses: str):
        object.__setattr__(self, "statuses", frozenset(s.lower() for s in statuses))

    def is_satisfied_by(self, candidate: Any) -> bool:
        status = getattr(candidate, "status", None)
        if status is None:
            return False
        # Handle both string and Status enum
        status_str = status.name if hasattr(status, "name") else str(status)
        return status_str.lower() in self.statuses

    def __repr__(self) -> str:
        return f"StatusSpec({', '.join(self.statuses)})"


@dataclass(frozen=True)
class IssueTypeSpec(Specification[Any]):
    """
    Specification for issue type.

    Example:
        >>> is_story = IssueTypeSpec("Story", "User Story")
        >>> is_bug = IssueTypeSpec("Bug")
    """

    types: frozenset[str]

    def __init__(self, *types: str):
        object.__setattr__(self, "types", frozenset(t.lower() for t in types))

    def is_satisfied_by(self, candidate: Any) -> bool:
        issue_type = getattr(candidate, "issue_type", None)
        if issue_type is None:
            return False
        return issue_type.lower() in self.types

    def __repr__(self) -> str:
        return f"IssueTypeSpec({', '.join(self.types)})"


@dataclass(frozen=True)
class HasSubtasksSpec(Specification[Any]):
    """Specification for issues that have subtasks."""

    def is_satisfied_by(self, candidate: Any) -> bool:
        subtasks = getattr(candidate, "subtasks", None)
        if subtasks is None:
            return False
        return len(subtasks) > 0

    def __repr__(self) -> str:
        return "HasSubtasks"


@dataclass(frozen=True)
class AllSubtasksMatchSpec(Specification[Any]):
    """Specification for issues where all subtasks match a spec."""

    subtask_spec: Specification[Any]

    def is_satisfied_by(self, candidate: Any) -> bool:
        subtasks = getattr(candidate, "subtasks", None)
        if not subtasks:
            return True  # Vacuously true for empty
        return self.subtask_spec.all_satisfy(subtasks)

    def __repr__(self) -> str:
        return f"AllSubtasksMatch({self.subtask_spec!r})"


@dataclass(frozen=True)
class AnySubtaskMatchesSpec(Specification[Any]):
    """Specification for issues where any subtask matches a spec."""

    subtask_spec: Specification[Any]

    def is_satisfied_by(self, candidate: Any) -> bool:
        subtasks = getattr(candidate, "subtasks", None)
        if not subtasks:
            return False
        return self.subtask_spec.any_satisfy(subtasks)

    def __repr__(self) -> str:
        return f"AnySubtaskMatches({self.subtask_spec!r})"


@dataclass(frozen=True)
class TitleMatchesSpec(Specification[Any]):
    """
    Specification for matching issue/story titles.

    Normalizes titles for comparison (lowercase, strips whitespace).

    Example:
        >>> matches_auth = TitleMatchesSpec("authentication")
        >>> matches_auth.is_satisfied_by(story)  # True if "Authentication" in title
    """

    pattern: str
    exact: bool = False

    def is_satisfied_by(self, candidate: Any) -> bool:
        title = getattr(candidate, "title", None) or getattr(candidate, "summary", None)
        if title is None:
            return False

        normalized_title = self._normalize(title)
        normalized_pattern = self._normalize(self.pattern)

        if self.exact:
            return normalized_title == normalized_pattern
        return normalized_pattern in normalized_title

    @staticmethod
    def _normalize(text: str) -> str:
        """Normalize text for comparison."""
        return " ".join(text.lower().split())

    def __repr__(self) -> str:
        mode = "exact" if self.exact else "contains"
        return f"TitleMatches({self.pattern!r}, {mode})"


@dataclass(frozen=True)
class HasKeySpec(Specification[Any]):
    """
    Specification for issues with a specific key.

    Example:
        >>> is_proj_123 = HasKeySpec("PROJ-123")
    """

    key: str

    def is_satisfied_by(self, candidate: Any) -> bool:
        candidate_key = getattr(candidate, "key", None)
        if candidate_key is None:
            return False
        return str(candidate_key).upper() == self.key.upper()

    def __repr__(self) -> str:
        return f"HasKey({self.key})"


@dataclass(frozen=True)
class KeyPrefixSpec(Specification[Any]):
    """
    Specification for issues with keys starting with a prefix.

    Example:
        >>> is_proj = KeyPrefixSpec("PROJ")
    """

    prefix: str

    def is_satisfied_by(self, candidate: Any) -> bool:
        key = getattr(candidate, "key", None)
        if key is None:
            return False
        return str(key).upper().startswith(self.prefix.upper())

    def __repr__(self) -> str:
        return f"KeyPrefix({self.prefix})"


@dataclass(frozen=True)
class HasDescriptionSpec(Specification[Any]):
    """Specification for issues that have a description."""

    def is_satisfied_by(self, candidate: Any) -> bool:
        description = getattr(candidate, "description", None)
        return description is not None and len(str(description).strip()) > 0

    def __repr__(self) -> str:
        return "HasDescription"


@dataclass(frozen=True)
class StoryPointsSpec(Specification[Any]):
    """
    Specification for story points range.

    Example:
        >>> small_stories = StoryPointsSpec(max_points=3)
        >>> medium_stories = StoryPointsSpec(min_points=3, max_points=8)
    """

    min_points: int | None = None
    max_points: int | None = None

    def is_satisfied_by(self, candidate: Any) -> bool:
        points = getattr(candidate, "story_points", None)
        if points is None:
            return False

        if self.min_points is not None and points < self.min_points:
            return False
        return not (self.max_points is not None and points > self.max_points)

    def __repr__(self) -> str:
        parts = []
        if self.min_points is not None:
            parts.append(f"min={self.min_points}")
        if self.max_points is not None:
            parts.append(f"max={self.max_points}")
        return f"StoryPoints({', '.join(parts)})"


# =============================================================================
# Sync-Specific Specifications
# =============================================================================


@dataclass(frozen=True)
class NeedsSyncSpec(Specification[Any]):
    """
    Specification for items that need synchronization.

    Checks if an item's content has changed from its synced state.
    """

    def is_satisfied_by(self, candidate: Any) -> bool:
        # Check for dirty flag
        is_dirty = getattr(candidate, "is_dirty", None)
        if isinstance(is_dirty, bool):
            return is_dirty
        if is_dirty is not None:
            return bool(is_dirty)

        # Check for sync state
        last_synced = getattr(candidate, "last_synced", None)
        last_modified = getattr(candidate, "last_modified", None)

        if last_synced is None:
            return True  # Never synced
        if last_modified is None:
            return False  # No modification info

        return bool(last_modified > last_synced)

    def __repr__(self) -> str:
        return "NeedsSync"


@dataclass(frozen=True)
class MatchedSpec(Specification[Any]):
    """
    Specification for items that have been matched to a remote counterpart.
    """

    def is_satisfied_by(self, candidate: Any) -> bool:
        external_key = getattr(candidate, "external_key", None)
        return external_key is not None

    def __repr__(self) -> str:
        return "IsMatched"


@dataclass(frozen=True)
class UnmatchedSpec(Specification[Any]):
    """
    Specification for items that haven't been matched yet.
    """

    def is_satisfied_by(self, candidate: Any) -> bool:
        external_key = getattr(candidate, "external_key", None)
        return external_key is None

    def __repr__(self) -> str:
        return "IsUnmatched"


# =============================================================================
# Builder Helpers
# =============================================================================


def all_of(*specs: Specification[T]) -> Specification[T]:
    """
    Create a specification that requires all specs to be satisfied.

    Example:
        >>> ready = all_of(StatusSpec("Done"), HasDescriptionSpec(), HasSubtasksSpec())
    """
    if not specs:
        return AlwaysTrue()

    result = specs[0]
    for spec in specs[1:]:
        result = result.and_(spec)
    return result


def any_of(*specs: Specification[T]) -> Specification[T]:
    """
    Create a specification that requires any spec to be satisfied.

    Example:
        >>> blocked = any_of(StatusSpec("Blocked"), StatusSpec("On Hold"))
    """
    if not specs:
        return AlwaysFalse()

    result = specs[0]
    for spec in specs[1:]:
        result = result.or_(spec)
    return result


def none_of(*specs: Specification[T]) -> Specification[T]:
    """
    Create a specification that requires none of the specs to be satisfied.

    Example:
        >>> not_blocked = none_of(StatusSpec("Blocked"), StatusSpec("Cancelled"))
    """
    return any_of(*specs).not_()


__all__ = [
    "AllSubtasksMatchSpec",
    "AlwaysFalse",
    "AlwaysTrue",
    "AndSpecification",
    "AnySubtaskMatchesSpec",
    "AttributeContains",
    "AttributeIn",
    "AttributeMatches",
    # Attribute
    "HasAttribute",
    "HasDescriptionSpec",
    "HasKeySpec",
    "HasSubtasksSpec",
    "IssueTypeSpec",
    "KeyPrefixSpec",
    "MatchedSpec",
    # Sync
    "NeedsSyncSpec",
    "NotSpecification",
    "OrSpecification",
    # Factory
    "PredicateSpec",
    # Base
    "Specification",
    # Issue/Story
    "StatusSpec",
    "StoryPointsSpec",
    "TitleMatchesSpec",
    "UnmatchedSpec",
    # Builders
    "all_of",
    "any_of",
    "none_of",
]
