"""
Benchmarks for domain entities and operations.

Tests performance of domain operations including:
- Entity creation
- Title matching and normalization
- Serialization
- Epic traversal
"""

import pytest
from md2jira.core.domain import (
    Epic,
    UserStory,
    Subtask,
    StoryId,
    IssueKey,
    AcceptanceCriteria,
    Status,
    Priority,
)


# =============================================================================
# Entity Creation Benchmarks
# =============================================================================

class TestEntityCreation:
    """Benchmark entity creation."""
    
    def test_story_id_creation(self, benchmark):
        """Benchmark StoryId creation."""
        benchmark(StoryId, "US-001")
    
    def test_story_id_from_string(self, benchmark):
        """Benchmark StoryId.from_string."""
        benchmark(StoryId.from_string, "123")
    
    def test_issue_key_creation(self, benchmark):
        """Benchmark IssueKey creation."""
        benchmark(IssueKey, "PROJ-123")
    
    def test_subtask_creation(self, benchmark):
        """Benchmark Subtask creation."""
        def create():
            return Subtask(
                name="Test subtask",
                description="Description",
                story_points=3,
                status=Status.PLANNED,
            )
        benchmark(create)
    
    def test_story_creation(self, benchmark):
        """Benchmark UserStory creation."""
        def create():
            return UserStory(
                id=StoryId("US-001"),
                title="Test story",
                story_points=5,
                priority=Priority.HIGH,
                status=Status.IN_PROGRESS,
            )
        benchmark(create)
    
    def test_story_creation_with_subtasks(self, benchmark):
        """Benchmark UserStory creation with subtasks."""
        subtasks = [
            Subtask(name=f"Subtask {i}", story_points=1)
            for i in range(10)
        ]
        
        def create():
            return UserStory(
                id=StoryId("US-001"),
                title="Test story",
                subtasks=subtasks.copy(),
            )
        benchmark(create)
    
    def test_acceptance_criteria_creation(self, benchmark):
        """Benchmark AcceptanceCriteria creation."""
        items = [f"Criterion {i}" for i in range(10)]
        benchmark(AcceptanceCriteria.from_list, items)


# =============================================================================
# Matching Benchmarks
# =============================================================================

class TestMatching:
    """Benchmark matching operations."""
    
    def test_story_normalize_title(self, benchmark, story_list_small):
        """Benchmark title normalization."""
        story = story_list_small[0]
        benchmark(story.normalize_title)
    
    def test_story_matches_title_positive(self, benchmark, story_list_small):
        """Benchmark title matching (match found)."""
        story = story_list_small[0]
        benchmark(story.matches_title, story.title)
    
    def test_story_matches_title_negative(self, benchmark, story_list_small):
        """Benchmark title matching (no match)."""
        story = story_list_small[0]
        benchmark(story.matches_title, "completely different title xyz")
    
    def test_subtask_normalize_name(self, benchmark, story_list_small):
        """Benchmark subtask name normalization."""
        subtask = story_list_small[0].subtasks[0]
        benchmark(subtask.normalize_name)
    
    def test_subtask_matches(self, benchmark, story_list_small):
        """Benchmark subtask matching."""
        subtask1 = story_list_small[0].subtasks[0]
        subtask2 = story_list_small[1].subtasks[0]
        benchmark(subtask1.matches, subtask2)


# =============================================================================
# Serialization Benchmarks
# =============================================================================

class TestSerialization:
    """Benchmark serialization operations."""
    
    def test_subtask_to_dict(self, benchmark, story_list_small):
        """Benchmark Subtask.to_dict."""
        subtask = story_list_small[0].subtasks[0]
        benchmark(subtask.to_dict)
    
    def test_story_id_str(self, benchmark):
        """Benchmark StoryId string conversion."""
        story_id = StoryId("US-001")
        benchmark(str, story_id)
    
    def test_issue_key_str(self, benchmark):
        """Benchmark IssueKey string conversion."""
        key = IssueKey("PROJ-123")
        benchmark(str, key)
    
    def test_acceptance_criteria_iteration(self, benchmark):
        """Benchmark AcceptanceCriteria iteration."""
        ac = AcceptanceCriteria.from_list([f"Criterion {i}" for i in range(20)])
        benchmark(list, ac)


# =============================================================================
# Epic Traversal Benchmarks
# =============================================================================

class TestEpicTraversal:
    """Benchmark epic traversal operations."""
    
    def test_small_epic_story_iteration(self, benchmark, small_epic):
        """Benchmark iterating stories in small epic."""
        benchmark(list, small_epic.stories)
    
    def test_medium_epic_story_iteration(self, benchmark, medium_epic):
        """Benchmark iterating stories in medium epic."""
        benchmark(list, medium_epic.stories)
    
    def test_large_epic_story_iteration(self, benchmark, large_epic):
        """Benchmark iterating stories in large epic."""
        benchmark(list, large_epic.stories)
    
    def test_small_epic_subtask_count(self, benchmark, small_epic):
        """Benchmark counting subtasks in small epic."""
        def count():
            return sum(len(s.subtasks) for s in small_epic.stories)
        benchmark(count)
    
    def test_medium_epic_subtask_count(self, benchmark, medium_epic):
        """Benchmark counting subtasks in medium epic."""
        def count():
            return sum(len(s.subtasks) for s in medium_epic.stories)
        benchmark(count)
    
    def test_large_epic_subtask_count(self, benchmark, large_epic):
        """Benchmark counting subtasks in large epic."""
        def count():
            return sum(len(s.subtasks) for s in large_epic.stories)
        benchmark(count)
    
    def test_find_story_by_title(self, benchmark, medium_epic):
        """Benchmark finding story by title in medium epic."""
        target = "User Story 25"
        
        def find():
            for story in medium_epic.stories:
                if target in story.title:
                    return story
            return None
        
        benchmark(find)
    
    def test_filter_done_stories(self, benchmark, medium_epic):
        """Benchmark filtering done stories in medium epic."""
        def filter_done():
            return [s for s in medium_epic.stories if s.status == Status.DONE]
        benchmark(filter_done)


# =============================================================================
# Container Benchmarks
# =============================================================================

class TestContainerOperations:
    """Benchmark DI container operations."""
    
    def test_container_register(self, benchmark):
        """Benchmark container registration."""
        from md2jira.core.container import Container
        
        container = Container()
        
        class IService:
            pass
        
        class ServiceImpl(IService):
            pass
        
        def register():
            container.register(IService, lambda c: ServiceImpl())
        
        benchmark(register)
    
    def test_container_get_singleton(self, benchmark):
        """Benchmark container singleton resolution."""
        from md2jira.core.container import Container
        
        container = Container()
        
        class IService:
            pass
        
        class ServiceImpl(IService):
            pass
        
        container.register(IService, lambda c: ServiceImpl())
        # Warm up
        container.get(IService)
        
        benchmark(container.get, IService)
    
    def test_container_get_transient(self, benchmark):
        """Benchmark container transient resolution."""
        from md2jira.core.container import Container, Lifecycle
        
        container = Container()
        
        class IService:
            pass
        
        class ServiceImpl(IService):
            pass
        
        container.register(IService, lambda c: ServiceImpl(), Lifecycle.TRANSIENT)
        
        benchmark(container.get, IService)

