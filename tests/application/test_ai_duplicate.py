"""Tests for AI Duplicate Detection module."""

import json
from unittest.mock import MagicMock, patch

import pytest

from spectra.application.ai_duplicate import (
    AIDuplicateDetector,
    DuplicateOptions,
    DuplicateResult,
    DuplicateType,
    SimilarityLevel,
    SimilarityMatch,
    StoryDuplicates,
    build_duplicate_prompt,
    calculate_story_similarity,
    calculate_text_similarity,
    find_duplicates_text_based,
    parse_duplicate_response,
)
from spectra.core.domain.entities import UserStory
from spectra.core.domain.enums import Priority, Status
from spectra.core.domain.value_objects import AcceptanceCriteria, Description, StoryId


@pytest.fixture
def story_a() -> UserStory:
    """Create first story for comparison."""
    return UserStory(
        id=StoryId.from_string("US-001"),
        title="User Login with Email",
        description=Description(
            role="registered user",
            want="to log in with my email and password",
            benefit="I can access my account",
        ),
        acceptance_criteria=AcceptanceCriteria.from_list(
            [
                "Can enter email and password",
                "Form validates input",
                "Redirects to dashboard on success",
            ]
        ),
        story_points=5,
        priority=Priority.HIGH,
        status=Status.PLANNED,
        labels=["auth"],
    )


@pytest.fixture
def story_b_duplicate() -> UserStory:
    """Create a near-duplicate story."""
    return UserStory(
        id=StoryId.from_string("US-002"),
        title="User Login via Email",  # Very similar title
        description=Description(
            role="registered user",  # Same role
            want="to sign in using my email and password",  # Very similar
            benefit="I can access my personal account",  # Similar
        ),
        acceptance_criteria=AcceptanceCriteria.from_list(
            [
                "Can enter email and password",  # Same
                "Form validates email format",  # Similar
                "Redirects to home on success",  # Similar
            ]
        ),
        story_points=5,
        priority=Priority.HIGH,
        status=Status.PLANNED,
        labels=["auth"],
    )


@pytest.fixture
def story_c_different() -> UserStory:
    """Create a completely different story."""
    return UserStory(
        id=StoryId.from_string("US-003"),
        title="Product Search",
        description=Description(
            role="shopper",
            want="to search for products by keyword",
            benefit="I can find what I'm looking for",
        ),
        acceptance_criteria=AcceptanceCriteria.from_list(
            [
                "Search box is visible",
                "Results show matching products",
                "Can filter results",
            ]
        ),
        story_points=3,
        priority=Priority.MEDIUM,
        status=Status.PLANNED,
        labels=["search"],
    )


@pytest.fixture
def story_d_related() -> UserStory:
    """Create a related but different story."""
    return UserStory(
        id=StoryId.from_string("US-004"),
        title="Password Reset",
        description=Description(
            role="user who forgot password",
            want="to reset my password via email",
            benefit="I can regain access to my account",
        ),
        acceptance_criteria=AcceptanceCriteria.from_list(
            [
                "Can request password reset",
                "Receives email with reset link",
                "Can set new password",
            ]
        ),
        story_points=3,
        priority=Priority.HIGH,
        status=Status.PLANNED,
        labels=["auth"],
    )


class TestDuplicateOptions:
    """Tests for DuplicateOptions configuration."""

    def test_default_options(self) -> None:
        """Test default detection options."""
        options = DuplicateOptions()

        assert options.exact_threshold == 0.95
        assert options.high_threshold == 0.80
        assert options.medium_threshold == 0.60
        assert options.min_threshold == 0.40
        assert options.use_llm is True
        assert options.use_text_similarity is True

    def test_custom_options(self) -> None:
        """Test custom detection options."""
        options = DuplicateOptions(
            exact_threshold=0.90,
            min_threshold=0.50,
            use_llm=False,
        )

        assert options.exact_threshold == 0.90
        assert options.min_threshold == 0.50
        assert options.use_llm is False


class TestSimilarityLevel:
    """Tests for SimilarityLevel enum."""

    def test_level_values(self) -> None:
        """Test similarity level enum values."""
        assert SimilarityLevel.EXACT.value == "exact"
        assert SimilarityLevel.HIGH.value == "high"
        assert SimilarityLevel.MEDIUM.value == "medium"
        assert SimilarityLevel.LOW.value == "low"
        assert SimilarityLevel.NONE.value == "none"


class TestDuplicateType:
    """Tests for DuplicateType enum."""

    def test_type_values(self) -> None:
        """Test duplicate type enum values."""
        assert DuplicateType.EXACT_DUPLICATE.value == "exact_duplicate"
        assert DuplicateType.NEAR_DUPLICATE.value == "near_duplicate"
        assert DuplicateType.OVERLAPPING.value == "overlapping"
        assert DuplicateType.RELATED.value == "related"


class TestSimilarityMatch:
    """Tests for SimilarityMatch dataclass."""

    def test_match_creation(self) -> None:
        """Test creating a similarity match."""
        match = SimilarityMatch(
            story_a_id="US-001",
            story_b_id="US-002",
            story_a_title="Login",
            story_b_title="Sign In",
            similarity_score=0.85,
            similarity_level=SimilarityLevel.HIGH,
            duplicate_type=DuplicateType.NEAR_DUPLICATE,
            confidence="high",
        )

        assert match.story_a_id == "US-001"
        assert match.percentage == 85
        assert match.is_likely_duplicate is True

    def test_is_likely_duplicate(self) -> None:
        """Test is_likely_duplicate property."""
        exact = SimilarityMatch(
            story_a_id="A",
            story_b_id="B",
            story_a_title="",
            story_b_title="",
            similarity_score=0.95,
            similarity_level=SimilarityLevel.EXACT,
            duplicate_type=DuplicateType.EXACT_DUPLICATE,
        )
        related = SimilarityMatch(
            story_a_id="A",
            story_b_id="B",
            story_a_title="",
            story_b_title="",
            similarity_score=0.50,
            similarity_level=SimilarityLevel.MEDIUM,
            duplicate_type=DuplicateType.RELATED,
        )

        assert exact.is_likely_duplicate is True
        assert related.is_likely_duplicate is False


class TestStoryDuplicates:
    """Tests for StoryDuplicates dataclass."""

    def test_duplicate_count(self) -> None:
        """Test duplicate_count property."""
        analysis = StoryDuplicates(
            story_id="US-001",
            story_title="Login",
            matches=[
                SimilarityMatch(
                    story_a_id="US-001",
                    story_b_id="US-002",
                    story_a_title="",
                    story_b_title="",
                    similarity_score=0.90,
                    similarity_level=SimilarityLevel.HIGH,
                    duplicate_type=DuplicateType.NEAR_DUPLICATE,
                ),
                SimilarityMatch(
                    story_a_id="US-001",
                    story_b_id="US-003",
                    story_a_title="",
                    story_b_title="",
                    similarity_score=0.50,
                    similarity_level=SimilarityLevel.MEDIUM,
                    duplicate_type=DuplicateType.RELATED,
                ),
            ],
            has_duplicates=True,
        )

        assert analysis.duplicate_count == 1  # Only the near_duplicate


class TestDuplicateResult:
    """Tests for DuplicateResult dataclass."""

    def test_default_success(self) -> None:
        """Test default success state."""
        result = DuplicateResult()
        assert result.success is True
        assert result.all_matches == []
        assert result.duplicate_rate == 0.0

    def test_duplicate_rate(self) -> None:
        """Test duplicate_rate property."""
        result = DuplicateResult(
            total_stories=10,
            stories_with_duplicates=3,
        )

        assert result.duplicate_rate == 30.0


class TestTextSimilarity:
    """Tests for text similarity functions."""

    def test_exact_match(self) -> None:
        """Test exact text match."""
        assert calculate_text_similarity("hello world", "hello world") == 1.0

    def test_similar_text(self) -> None:
        """Test similar text."""
        sim = calculate_text_similarity("User Login", "User Sign In")
        assert 0.5 < sim < 1.0

    def test_different_text(self) -> None:
        """Test different text."""
        sim = calculate_text_similarity("User Login", "Product Search")
        assert sim < 0.5

    def test_empty_text(self) -> None:
        """Test empty text."""
        assert calculate_text_similarity("", "hello") == 0.0
        assert calculate_text_similarity("hello", "") == 0.0


class TestStorySimilarity:
    """Tests for story similarity calculation."""

    def test_similar_stories(self, story_a: UserStory, story_b_duplicate: UserStory) -> None:
        """Test similarity between similar stories."""
        sim = calculate_story_similarity(story_a, story_b_duplicate)
        assert sim > 0.6  # Should be high similarity

    def test_different_stories(self, story_a: UserStory, story_c_different: UserStory) -> None:
        """Test similarity between different stories."""
        sim = calculate_story_similarity(story_a, story_c_different)
        assert sim < 0.4  # Should be low similarity


class TestFindDuplicatesTextBased:
    """Tests for text-based duplicate finding."""

    def test_finds_similar_stories(self, story_a: UserStory, story_b_duplicate: UserStory) -> None:
        """Test finding similar stories."""
        options = DuplicateOptions(min_threshold=0.40)
        matches = find_duplicates_text_based([story_a, story_b_duplicate], options)

        assert len(matches) >= 1
        assert matches[0].similarity_score > 0.5

    def test_no_duplicates_for_different(
        self, story_a: UserStory, story_c_different: UserStory
    ) -> None:
        """Test no duplicates for different stories."""
        options = DuplicateOptions(min_threshold=0.60)  # Higher threshold
        matches = find_duplicates_text_based([story_a, story_c_different], options)

        # Should not find any matches at 60% threshold
        assert len(matches) == 0


class TestBuildDuplicatePrompt:
    """Tests for prompt building."""

    def test_basic_prompt(self, story_a: UserStory, story_b_duplicate: UserStory) -> None:
        """Test basic prompt generation."""
        options = DuplicateOptions()
        prompt = build_duplicate_prompt([story_a, story_b_duplicate], options)

        assert "US-001" in prompt
        assert "US-002" in prompt
        assert "User Login" in prompt
        assert "similarity" in prompt.lower()

    def test_prompt_with_context(self, story_a: UserStory) -> None:
        """Test prompt with project context."""
        options = DuplicateOptions(project_context="E-commerce platform")
        prompt = build_duplicate_prompt([story_a], options)

        assert "E-commerce platform" in prompt


class TestParseDuplicateResponse:
    """Tests for parsing LLM responses."""

    def test_parse_valid_response(self, story_a: UserStory, story_b_duplicate: UserStory) -> None:
        """Test parsing valid JSON response."""
        response = json.dumps(
            {
                "matches": [
                    {
                        "story_a_id": "US-001",
                        "story_b_id": "US-002",
                        "similarity_score": 0.85,
                        "similarity_level": "high",
                        "duplicate_type": "near_duplicate",
                        "matching_elements": ["Same user persona", "Similar functionality"],
                        "differences": ["Minor wording differences"],
                        "recommendation": "Consider merging",
                        "confidence": "high",
                    }
                ],
                "duplicate_groups": [["US-001", "US-002"]],
            }
        )

        options = DuplicateOptions()
        matches, groups = parse_duplicate_response(response, [story_a, story_b_duplicate], options)

        assert len(matches) == 1
        assert matches[0].story_a_id == "US-001"
        assert matches[0].similarity_level == SimilarityLevel.HIGH
        assert matches[0].duplicate_type == DuplicateType.NEAR_DUPLICATE
        assert len(groups) == 1
        assert "US-001" in groups[0]

    def test_parse_filters_invalid_ids(
        self, story_a: UserStory, story_b_duplicate: UserStory
    ) -> None:
        """Test that invalid story IDs are filtered."""
        response = json.dumps(
            {
                "matches": [
                    {
                        "story_a_id": "US-999",  # Invalid
                        "story_b_id": "US-001",
                        "similarity_score": 0.90,
                        "similarity_level": "high",
                        "duplicate_type": "near_duplicate",
                    }
                ]
            }
        )

        options = DuplicateOptions()
        matches, _ = parse_duplicate_response(response, [story_a, story_b_duplicate], options)

        assert len(matches) == 0  # Invalid ID filtered


class TestAIDuplicateDetector:
    """Tests for AIDuplicateDetector class."""

    def test_detect_empty_stories(self) -> None:
        """Test detecting for empty story list."""
        detector = AIDuplicateDetector()
        result = detector.detect([])

        assert result.success is False
        assert "No stories provided" in result.error

    def test_detect_single_story(self, story_a: UserStory) -> None:
        """Test detecting for single story."""
        detector = AIDuplicateDetector()
        result = detector.detect([story_a])

        assert result.success is False
        assert "At least 2 stories" in result.error

    def test_detect_text_based_only(self, story_a: UserStory, story_b_duplicate: UserStory) -> None:
        """Test detection using text-based similarity only."""
        options = DuplicateOptions(use_llm=False)

        with patch("spectra.adapters.llm.create_llm_manager") as mock_manager:
            mock_manager.side_effect = Exception("LLM not configured")

            detector = AIDuplicateDetector(options)
            result = detector.detect([story_a, story_b_duplicate], options)

            assert result.success is True
            assert len(result.story_analyses) == 2
            # Should find similarity between these similar stories
            assert len(result.all_matches) >= 1

    def test_detect_with_mocked_llm(self, story_a: UserStory, story_b_duplicate: UserStory) -> None:
        """Test detection with mocked LLM."""
        mock_response_content = json.dumps(
            {
                "matches": [
                    {
                        "story_a_id": "US-001",
                        "story_b_id": "US-002",
                        "similarity_score": 0.88,
                        "similarity_level": "high",
                        "duplicate_type": "near_duplicate",
                        "matching_elements": ["Same persona", "Same functionality"],
                        "recommendation": "Merge these stories",
                        "confidence": "high",
                    }
                ],
                "duplicate_groups": [["US-001", "US-002"]],
            }
        )

        with patch("spectra.adapters.llm.create_llm_manager") as mock_manager:
            mock_mgr = MagicMock()
            mock_mgr.is_available.return_value = True

            mock_response = MagicMock()
            mock_response.content = mock_response_content
            mock_response.total_tokens = 200
            mock_response.model = "claude-3"
            mock_response.provider = "anthropic"
            mock_mgr.prompt.return_value = mock_response

            mock_manager.return_value = mock_mgr

            detector = AIDuplicateDetector()
            result = detector.detect([story_a, story_b_duplicate])

            assert result.success is True
            assert result.stories_with_duplicates >= 1
            assert len(result.duplicate_groups) >= 1
            assert result.provider_used == "anthropic"

    def test_no_duplicates_for_different_stories(
        self, story_a: UserStory, story_c_different: UserStory
    ) -> None:
        """Test that different stories don't match."""
        options = DuplicateOptions(use_llm=False, min_threshold=0.60)

        detector = AIDuplicateDetector(options)
        result = detector.detect([story_a, story_c_different], options)

        assert result.success is True
        # At 60% threshold, these should not match
        likely_duplicates = [m for m in result.all_matches if m.is_likely_duplicate]
        assert len(likely_duplicates) == 0
