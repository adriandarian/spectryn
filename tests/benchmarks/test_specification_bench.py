"""
Benchmarks for the Specification pattern.

Tests performance of specification operations including:
- Evaluation (is_satisfied_by)
- Composition (and, or, not)
- Collection operations (filter, count, first)
"""

import pytest
from md2jira.core.specification import (
    Specification,
    PredicateSpec,
    AlwaysTrue,
    AlwaysFalse,
    StatusSpec,
    IssueTypeSpec,
    HasSubtasksSpec,
    TitleMatchesSpec,
    StoryPointsSpec,
    all_of,
    any_of,
    none_of,
)
from md2jira.core.domain import UserStory, Status


# =============================================================================
# Evaluation Benchmarks
# =============================================================================

class TestSpecificationEvaluation:
    """Benchmark specification evaluation."""
    
    def test_predicate_spec_evaluation(self, benchmark, story_list_small):
        """Benchmark PredicateSpec evaluation."""
        spec = PredicateSpec(lambda s: s.story_points > 5, "high_points")
        story = story_list_small[0]
        benchmark(spec.is_satisfied_by, story)
    
    def test_status_spec_evaluation(self, benchmark, story_list_small):
        """Benchmark StatusSpec evaluation."""
        spec = StatusSpec("In Progress", "Done")
        story = story_list_small[0]
        benchmark(spec.is_satisfied_by, story)
    
    def test_title_matches_evaluation(self, benchmark, story_list_small):
        """Benchmark TitleMatchesSpec evaluation."""
        spec = TitleMatchesSpec("feature")
        story = story_list_small[0]
        benchmark(spec.is_satisfied_by, story)
    
    def test_has_subtasks_evaluation(self, benchmark, story_list_small):
        """Benchmark HasSubtasksSpec evaluation."""
        spec = HasSubtasksSpec()
        story = story_list_small[0]
        benchmark(spec.is_satisfied_by, story)
    
    def test_story_points_range_evaluation(self, benchmark, story_list_small):
        """Benchmark StoryPointsSpec evaluation."""
        spec = StoryPointsSpec(min_points=3, max_points=8)
        story = story_list_small[0]
        benchmark(spec.is_satisfied_by, story)


# =============================================================================
# Composition Benchmarks
# =============================================================================

class TestSpecificationComposition:
    """Benchmark specification composition."""
    
    def test_and_composition(self, benchmark, story_list_small):
        """Benchmark AND composition."""
        spec1 = StatusSpec("In Progress")
        spec2 = HasSubtasksSpec()
        combined = spec1.and_(spec2)
        story = story_list_small[0]
        benchmark(combined.is_satisfied_by, story)
    
    def test_or_composition(self, benchmark, story_list_small):
        """Benchmark OR composition."""
        spec1 = StatusSpec("Done")
        spec2 = StatusSpec("In Progress")
        combined = spec1.or_(spec2)
        story = story_list_small[0]
        benchmark(combined.is_satisfied_by, story)
    
    def test_not_composition(self, benchmark, story_list_small):
        """Benchmark NOT composition."""
        spec = StatusSpec("Done").not_()
        story = story_list_small[0]
        benchmark(spec.is_satisfied_by, story)
    
    def test_complex_composition(self, benchmark, story_list_small):
        """Benchmark complex composition."""
        spec = (
            (StatusSpec("In Progress") | StatusSpec("Done"))
            & HasSubtasksSpec()
            & ~StatusSpec("Cancelled")
        )
        story = story_list_small[0]
        benchmark(spec.is_satisfied_by, story)
    
    def test_all_of_composition(self, benchmark, story_list_small):
        """Benchmark all_of builder."""
        spec = all_of(
            StatusSpec("In Progress"),
            HasSubtasksSpec(),
            StoryPointsSpec(min_points=1),
        )
        story = story_list_small[0]
        benchmark(spec.is_satisfied_by, story)
    
    def test_any_of_composition(self, benchmark, story_list_small):
        """Benchmark any_of builder."""
        spec = any_of(
            StatusSpec("Done"),
            StatusSpec("In Progress"),
            StatusSpec("Planned"),
        )
        story = story_list_small[0]
        benchmark(spec.is_satisfied_by, story)


# =============================================================================
# Collection Benchmarks
# =============================================================================

class TestSpecificationCollection:
    """Benchmark specification collection operations."""
    
    def test_filter_small(self, benchmark, story_list_small):
        """Benchmark filter on 100 items."""
        spec = StatusSpec("In Progress")
        benchmark(spec.filter, story_list_small)
    
    def test_filter_medium(self, benchmark, story_list_medium):
        """Benchmark filter on 1000 items."""
        spec = StatusSpec("In Progress")
        benchmark(spec.filter, story_list_medium)
    
    def test_filter_large(self, benchmark, story_list_large):
        """Benchmark filter on 10000 items."""
        spec = StatusSpec("In Progress")
        benchmark(spec.filter, story_list_large)
    
    def test_count_small(self, benchmark, story_list_small):
        """Benchmark count on 100 items."""
        spec = StatusSpec("In Progress")
        benchmark(spec.count, story_list_small)
    
    def test_count_medium(self, benchmark, story_list_medium):
        """Benchmark count on 1000 items."""
        spec = StatusSpec("In Progress")
        benchmark(spec.count, story_list_medium)
    
    def test_first_small(self, benchmark, story_list_small):
        """Benchmark first on 100 items."""
        spec = StatusSpec("In Progress")
        benchmark(spec.first, story_list_small)
    
    def test_any_satisfy_small(self, benchmark, story_list_small):
        """Benchmark any_satisfy on 100 items."""
        spec = StatusSpec("In Progress")
        benchmark(spec.any_satisfy, story_list_small)
    
    def test_all_satisfy_small(self, benchmark, story_list_small):
        """Benchmark all_satisfy on 100 items."""
        spec = StatusSpec("In Progress")
        benchmark(spec.all_satisfy, story_list_small)
    
    def test_complex_filter_medium(self, benchmark, story_list_medium):
        """Benchmark complex filter on 1000 items."""
        spec = (
            StatusSpec("In Progress", "Done")
            & HasSubtasksSpec()
            & StoryPointsSpec(min_points=3)
        )
        benchmark(spec.filter, story_list_medium)

