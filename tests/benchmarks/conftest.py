"""
Benchmark fixtures and utilities.

Provides common fixtures for performance testing.
"""

import pytest
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from md2jira.core.domain import (
    Epic,
    UserStory,
    Subtask,
    StoryId,
    Status,
    Priority,
    AcceptanceCriteria,
)
from md2jira.core.result import Ok, Err, Result
from md2jira.core.specification import StatusSpec, PredicateSpec


# =============================================================================
# Data Generators
# =============================================================================

def generate_subtask(index: int) -> Subtask:
    """Generate a subtask for benchmarking."""
    return Subtask(
        id=f"st-{index}",
        number=index,
        name=f"Subtask {index}: Implement feature component",
        description=f"Detailed description for subtask {index}",
        story_points=index % 5 + 1,
        status=Status.PLANNED if index % 3 == 0 else Status.DONE,
    )


def generate_story(index: int, num_subtasks: int = 5) -> UserStory:
    """Generate a user story for benchmarking."""
    return UserStory(
        id=StoryId(f"US-{index:03d}"),
        title=f"User Story {index}: Feature implementation for module",
        description=None,
        acceptance_criteria=AcceptanceCriteria.from_list([
            f"Criterion {i}" for i in range(3)
        ]),
        story_points=index % 13 + 1,
        priority=Priority.MEDIUM,
        status=Status.IN_PROGRESS if index % 2 == 0 else Status.PLANNED,
        subtasks=[generate_subtask(i) for i in range(num_subtasks)],
    )


def generate_epic(num_stories: int, subtasks_per_story: int = 5) -> Epic:
    """Generate an epic for benchmarking."""
    return Epic(
        key="BENCH-1",
        title="Benchmark Epic",
        stories=[generate_story(i, subtasks_per_story) for i in range(num_stories)],
    )


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def small_epic() -> Epic:
    """Small epic with 10 stories, 5 subtasks each (50 total subtasks)."""
    return generate_epic(10, 5)


@pytest.fixture
def medium_epic() -> Epic:
    """Medium epic with 50 stories, 10 subtasks each (500 total subtasks)."""
    return generate_epic(50, 10)


@pytest.fixture
def large_epic() -> Epic:
    """Large epic with 100 stories, 20 subtasks each (2000 total subtasks)."""
    return generate_epic(100, 20)


@pytest.fixture
def story_list_small() -> list[UserStory]:
    """List of 100 stories for filtering benchmarks."""
    return [generate_story(i) for i in range(100)]


@pytest.fixture
def story_list_medium() -> list[UserStory]:
    """List of 1000 stories for filtering benchmarks."""
    return [generate_story(i) for i in range(1000)]


@pytest.fixture
def story_list_large() -> list[UserStory]:
    """List of 10000 stories for filtering benchmarks."""
    return [generate_story(i) for i in range(10000)]


@pytest.fixture
def result_list_small() -> list[Result]:
    """List of 100 results for collection benchmarks."""
    return [Ok(i) if i % 10 != 0 else Err(f"error-{i}") for i in range(100)]


@pytest.fixture
def result_list_medium() -> list[Result]:
    """List of 1000 results for collection benchmarks."""
    return [Ok(i) if i % 10 != 0 else Err(f"error-{i}") for i in range(1000)]


# =============================================================================
# Benchmark Groups
# =============================================================================

@pytest.fixture
def benchmark_group_core():
    """Marker for core module benchmarks."""
    return "core"


@pytest.fixture
def benchmark_group_domain():
    """Marker for domain module benchmarks."""
    return "domain"


@pytest.fixture
def benchmark_group_specification():
    """Marker for specification benchmarks."""
    return "specification"

