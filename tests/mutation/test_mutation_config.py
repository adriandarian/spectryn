"""
Mutation testing configuration and helpers.

Mutation testing verifies the quality of tests by introducing small changes
(mutations) to the source code and checking if tests catch them.

To run mutation testing:
    pip install mutmut
    mutmut run --paths-to-mutate=src/spectra/core/domain

This module provides helpers for interpreting mutation testing results
and prioritizing which mutations to address.
"""

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest


@dataclass
class MutationResult:
    """Result of a mutation test run."""

    total: int
    killed: int
    survived: int
    timeout: int
    suspicious: int

    @property
    def score(self) -> float:
        """Calculate mutation score (killed / total)."""
        if self.total == 0:
            return 0.0
        return self.killed / self.total * 100

    @property
    def is_good(self) -> bool:
        """Check if mutation score is acceptable (>80%)."""
        return self.score >= 80.0


class TestMutationTestingSetup:
    """Tests to verify mutation testing setup is correct."""

    def test_mutmut_can_be_imported(self):
        """Test that mutmut is available (if installed)."""
        try:
            import mutmut

            assert True
        except ImportError:
            pytest.skip("mutmut not installed - install with: pip install mutmut")

    def test_target_files_exist(self):
        """Test that target files for mutation exist."""
        target_files = [
            "src/spectryn/core/domain/entities.py",
            "src/spectryn/core/domain/enums.py",
            "src/spectryn/core/domain/value_objects.py",
        ]

        project_root = Path(__file__).parent.parent.parent

        for file_path in target_files:
            full_path = project_root / file_path
            assert full_path.exists(), f"Target file not found: {file_path}"

    def test_tests_exist_for_domain(self):
        """Test that there are tests for domain entities."""
        tests_dir = Path(__file__).parent.parent

        domain_tests = list(tests_dir.glob("**/test_*domain*.py"))
        entity_tests = list(tests_dir.glob("**/test_*entities*.py"))
        property_tests = list(tests_dir.glob("**/test_*properties*.py"))

        all_tests = domain_tests + entity_tests + property_tests
        assert len(all_tests) >= 1, "Need tests for domain layer to run mutation testing"


class TestMutationTargets:
    """Verify key mutation targets are testable."""

    def test_status_from_string_is_testable(self):
        """Test Status.from_string is covered by tests."""
        from spectryn.core.domain.enums import Status

        # These should all be tested to catch mutations
        test_cases = [
            ("done", Status.DONE),
            ("in progress", Status.IN_PROGRESS),
            ("planned", Status.PLANNED),
            ("open", Status.OPEN),
        ]

        for input_str, expected in test_cases:
            result = Status.from_string(input_str)
            assert result == expected, f"Status.from_string('{input_str}') failed"

    def test_priority_from_string_is_testable(self):
        """Test Priority.from_string is covered by tests."""
        from spectryn.core.domain.enums import Priority

        test_cases = [
            ("critical", Priority.CRITICAL),
            ("high", Priority.HIGH),
            ("medium", Priority.MEDIUM),
            ("low", Priority.LOW),
        ]

        for input_str, expected in test_cases:
            result = Priority.from_string(input_str)
            assert result == expected, f"Priority.from_string('{input_str}') failed"

    def test_story_id_validation(self):
        """Test StoryId validation catches mutations."""
        from spectryn.core.domain.value_objects import StoryId

        # Valid IDs
        valid_ids = ["US-001", "PROJ-123", "A-1"]
        for id_str in valid_ids:
            story_id = StoryId(id_str)
            assert story_id.value == id_str

    def test_description_formatting(self):
        """Test Description is testable."""
        from spectryn.core.domain.value_objects import Description

        desc = Description(
            role="developer",
            want="to write tests",
            benefit="code quality improves",
        )

        assert desc.role == "developer"
        assert desc.want == "to write tests"
        assert desc.benefit == "code quality improves"


class TestMutationScoreTargets:
    """Define mutation score targets for different modules."""

    SCORE_TARGETS = {
        "core/domain/enums.py": 90,
        "core/domain/entities.py": 85,
        "core/domain/value_objects.py": 85,
        "adapters/parsers/markdown.py": 75,
    }

    def test_score_targets_are_reasonable(self):
        """Test that score targets are between 0-100."""
        for module, target in self.SCORE_TARGETS.items():
            assert 0 <= target <= 100, f"Invalid target for {module}: {target}"

    def test_high_value_targets_have_high_scores(self):
        """Test that critical modules have high mutation score targets."""
        critical_modules = [
            "core/domain/enums.py",
            "core/domain/entities.py",
        ]

        for module in critical_modules:
            if module in self.SCORE_TARGETS:
                assert self.SCORE_TARGETS[module] >= 80, f"{module} should have >=80% target"
