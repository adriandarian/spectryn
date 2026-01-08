"""Tests for AI Gap Analysis module."""

import json
from unittest.mock import MagicMock, patch

import pytest

from spectryn.application.ai_gap import (
    AIGapAnalyzer,
    CategoryAnalysis,
    GapCategory,
    GapConfidence,
    GapOptions,
    GapPriority,
    GapResult,
    IdentifiedGap,
    analyze_gaps_fallback,
    build_gap_prompt,
    parse_gap_response,
)
from spectryn.core.domain.entities import UserStory
from spectryn.core.domain.enums import Priority, Status
from spectryn.core.domain.value_objects import AcceptanceCriteria, Description, StoryId


@pytest.fixture
def login_story() -> UserStory:
    """Create a login story."""
    return UserStory(
        id=StoryId.from_string("US-001"),
        title="User Login",
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
def registration_story() -> UserStory:
    """Create a registration story."""
    return UserStory(
        id=StoryId.from_string("US-002"),
        title="User Registration",
        description=Description(
            role="new user",
            want="to create an account",
            benefit="I can access the platform",
        ),
        acceptance_criteria=AcceptanceCriteria.from_list(
            [
                "Can enter email, password, name",
                "Validates email format",
                "Shows confirmation",
            ]
        ),
        story_points=5,
        priority=Priority.HIGH,
        status=Status.PLANNED,
        labels=["auth"],
    )


@pytest.fixture
def product_search_story() -> UserStory:
    """Create a product search story."""
    return UserStory(
        id=StoryId.from_string("US-003"),
        title="Product Search",
        description=Description(
            role="customer",
            want="to search for products by keyword",
            benefit="I can find what I need",
        ),
        acceptance_criteria=AcceptanceCriteria.from_list(
            [
                "Search box is visible",
                "Results show matching products",
            ]
        ),
        story_points=3,
        priority=Priority.MEDIUM,
        status=Status.PLANNED,
        labels=["search", "products"],
    )


class TestGapCategory:
    """Tests for GapCategory enum."""

    def test_category_values(self) -> None:
        """Test gap category enum values."""
        assert GapCategory.PERSONA.value == "persona"
        assert GapCategory.FUNCTIONAL.value == "functional"
        assert GapCategory.NON_FUNCTIONAL.value == "non_functional"
        assert GapCategory.EDGE_CASE.value == "edge_case"
        assert GapCategory.INTEGRATION.value == "integration"
        assert GapCategory.ACCESSIBILITY.value == "accessibility"


class TestGapPriority:
    """Tests for GapPriority enum."""

    def test_priority_values(self) -> None:
        """Test gap priority enum values."""
        assert GapPriority.CRITICAL.value == "critical"
        assert GapPriority.HIGH.value == "high"
        assert GapPriority.MEDIUM.value == "medium"
        assert GapPriority.LOW.value == "low"


class TestGapConfidence:
    """Tests for GapConfidence enum."""

    def test_confidence_values(self) -> None:
        """Test gap confidence enum values."""
        assert GapConfidence.HIGH.value == "high"
        assert GapConfidence.MEDIUM.value == "medium"
        assert GapConfidence.LOW.value == "low"


class TestIdentifiedGap:
    """Tests for IdentifiedGap dataclass."""

    def test_gap_creation(self) -> None:
        """Test creating an identified gap."""
        gap = IdentifiedGap(
            title="Missing Admin Dashboard",
            description="No stories cover admin functionality",
            category=GapCategory.FUNCTIONAL,
            priority=GapPriority.HIGH,
            confidence=GapConfidence.HIGH,
            related_stories=["US-001"],
            suggested_story="As an admin, I want to view metrics",
            rationale="Admins need oversight capabilities",
        )

        assert gap.title == "Missing Admin Dashboard"
        assert gap.category == GapCategory.FUNCTIONAL
        assert gap.priority == GapPriority.HIGH
        assert gap.priority_score == 3

    def test_priority_scores(self) -> None:
        """Test priority score calculation."""
        critical = IdentifiedGap(
            title="Critical",
            description="",
            category=GapCategory.FUNCTIONAL,
            priority=GapPriority.CRITICAL,
        )
        low = IdentifiedGap(
            title="Low",
            description="",
            category=GapCategory.FUNCTIONAL,
            priority=GapPriority.LOW,
        )

        assert critical.priority_score == 4
        assert low.priority_score == 1


class TestCategoryAnalysis:
    """Tests for CategoryAnalysis dataclass."""

    def test_gap_count(self) -> None:
        """Test gap count property."""
        gap1 = IdentifiedGap(
            title="Gap 1",
            description="",
            category=GapCategory.PERSONA,
            priority=GapPriority.HIGH,
        )
        gap2 = IdentifiedGap(
            title="Gap 2",
            description="",
            category=GapCategory.PERSONA,
            priority=GapPriority.MEDIUM,
        )

        analysis = CategoryAnalysis(
            category=GapCategory.PERSONA,
            gaps=[gap1, gap2],
            coverage_score=60.0,
        )

        assert analysis.gap_count == 2
        assert analysis.has_critical_gaps is False

    def test_has_critical_gaps(self) -> None:
        """Test detecting critical gaps."""
        critical_gap = IdentifiedGap(
            title="Critical",
            description="",
            category=GapCategory.FUNCTIONAL,
            priority=GapPriority.CRITICAL,
        )

        analysis = CategoryAnalysis(
            category=GapCategory.FUNCTIONAL,
            gaps=[critical_gap],
        )

        assert analysis.has_critical_gaps is True


class TestGapResult:
    """Tests for GapResult dataclass."""

    def test_default_success(self) -> None:
        """Test default success state."""
        result = GapResult()
        assert result.success is True
        assert result.all_gaps == []
        assert result.total_gap_count == 0

    def test_gap_counts(self) -> None:
        """Test gap count properties."""
        result = GapResult(
            all_gaps=[
                IdentifiedGap(
                    title="Critical",
                    description="",
                    category=GapCategory.FUNCTIONAL,
                    priority=GapPriority.CRITICAL,
                ),
                IdentifiedGap(
                    title="High",
                    description="",
                    category=GapCategory.FUNCTIONAL,
                    priority=GapPriority.HIGH,
                ),
                IdentifiedGap(
                    title="Low",
                    description="",
                    category=GapCategory.FUNCTIONAL,
                    priority=GapPriority.LOW,
                ),
            ]
        )

        assert result.critical_gap_count == 1
        assert result.high_gap_count == 1
        assert result.total_gap_count == 3


class TestGapOptions:
    """Tests for GapOptions configuration."""

    def test_default_options(self) -> None:
        """Test default gap options."""
        options = GapOptions()

        assert options.check_personas is True
        assert options.check_functional is True
        assert options.check_nfr is True
        assert options.check_edge_cases is True
        assert options.include_suggestions is True

    def test_custom_options(self) -> None:
        """Test custom gap options."""
        options = GapOptions(
            project_context="E-commerce platform",
            industry="retail",
            expected_personas=["admin", "customer", "guest"],
            compliance_requirements=["GDPR", "PCI-DSS"],
        )

        assert options.project_context == "E-commerce platform"
        assert options.industry == "retail"
        assert "admin" in options.expected_personas
        assert "GDPR" in options.compliance_requirements


class TestBuildGapPrompt:
    """Tests for prompt building."""

    def test_basic_prompt(self, login_story: UserStory) -> None:
        """Test basic prompt generation."""
        options = GapOptions()
        prompt = build_gap_prompt([login_story], options)

        assert "US-001" in prompt
        assert "User Login" in prompt
        assert "registered user" in prompt
        assert "gap" in prompt.lower()

    def test_prompt_with_context(self, login_story: UserStory) -> None:
        """Test prompt with project context."""
        options = GapOptions(
            project_context="Healthcare app",
            industry="healthcare",
            expected_personas=["doctor", "patient", "admin"],
            compliance_requirements=["HIPAA"],
        )
        prompt = build_gap_prompt([login_story], options)

        assert "Healthcare app" in prompt
        assert "healthcare" in prompt
        assert "doctor, patient, admin" in prompt
        assert "HIPAA" in prompt


class TestParseGapResponse:
    """Tests for parsing LLM responses."""

    def test_parse_valid_response(self, login_story: UserStory) -> None:
        """Test parsing valid JSON response."""
        response = json.dumps(
            {
                "gaps": [
                    {
                        "title": "Missing Logout",
                        "description": "No logout story found",
                        "category": "user_journey",
                        "priority": "high",
                        "confidence": "high",
                        "related_stories": ["US-001"],
                        "suggested_story": "As a user, I want to log out",
                        "rationale": "Incomplete auth flow",
                        "affected_areas": ["auth"],
                    }
                ],
                "category_analyses": [
                    {
                        "category": "user_journey",
                        "coverage_score": 50,
                        "recommendations": ["Add logout story"],
                    }
                ],
                "personas_found": ["registered user"],
                "personas_missing": ["admin"],
                "functional_areas": ["auth"],
                "overall_coverage": 60,
                "summary": "Auth flow incomplete",
            }
        )

        result = parse_gap_response(response, [login_story])

        assert result.success is True
        assert len(result.all_gaps) == 1
        assert result.all_gaps[0].title == "Missing Logout"
        assert result.all_gaps[0].priority == GapPriority.HIGH
        assert result.overall_coverage == 60
        assert "admin" in result.personas_missing

    def test_parse_filters_invalid_stories(self, login_story: UserStory) -> None:
        """Test that invalid story IDs are filtered."""
        response = json.dumps(
            {
                "gaps": [
                    {
                        "title": "Gap",
                        "description": "",
                        "category": "functional",
                        "priority": "medium",
                        "related_stories": ["US-999", "US-001"],
                    }
                ]
            }
        )

        result = parse_gap_response(response, [login_story])

        # US-999 should be filtered out
        assert result.all_gaps[0].related_stories == ["US-001"]


class TestAnalyzeGapsFallback:
    """Tests for fallback gap analysis."""

    def test_detects_missing_personas(self, login_story: UserStory) -> None:
        """Test detecting missing common personas."""
        options = GapOptions()
        result = analyze_gaps_fallback([login_story], options)

        # Should find some missing personas (admin, support, guest, anonymous)
        assert len(result.personas_missing) > 0
        assert "registered user" in result.personas_found

    def test_detects_missing_logout(self, login_story: UserStory) -> None:
        """Test detecting login without logout."""
        options = GapOptions()
        result = analyze_gaps_fallback([login_story], options)

        # Should find missing logout
        logout_gaps = [g for g in result.all_gaps if "logout" in g.title.lower()]
        assert len(logout_gaps) == 1
        assert logout_gaps[0].priority == GapPriority.HIGH

    def test_calculates_coverage(
        self, login_story: UserStory, registration_story: UserStory
    ) -> None:
        """Test coverage calculation."""
        options = GapOptions()
        result = analyze_gaps_fallback([login_story, registration_story], options)

        # Should calculate some coverage
        assert result.overall_coverage >= 0
        assert result.overall_coverage <= 100


class TestAIGapAnalyzer:
    """Tests for AIGapAnalyzer class."""

    def test_analyze_empty_stories(self) -> None:
        """Test analyzing empty story list."""
        analyzer = AIGapAnalyzer()
        result = analyzer.analyze([])

        assert result.success is False
        assert "No stories provided" in result.error

    def test_analyze_with_fallback(
        self, login_story: UserStory, registration_story: UserStory
    ) -> None:
        """Test analysis falls back without LLM."""
        with patch("spectryn.adapters.llm.create_llm_manager") as mock_manager:
            mock_manager.side_effect = Exception("LLM not configured")

            analyzer = AIGapAnalyzer()
            result = analyzer.analyze([login_story, registration_story])

            # Should use fallback
            assert result.success is True
            assert len(result.all_gaps) > 0
            assert result.summary is not None

    def test_analyze_with_mocked_llm(
        self, login_story: UserStory, product_search_story: UserStory
    ) -> None:
        """Test analysis with mocked LLM."""
        mock_response_content = json.dumps(
            {
                "gaps": [
                    {
                        "title": "Missing Admin Stories",
                        "description": "No admin functionality",
                        "category": "persona",
                        "priority": "high",
                        "confidence": "high",
                        "suggested_story": "As an admin, I want to manage users",
                    }
                ],
                "personas_found": ["registered user", "customer"],
                "personas_missing": ["admin", "support"],
                "overall_coverage": 65,
                "summary": "Good user coverage but missing admin",
            }
        )

        with patch("spectryn.adapters.llm.create_llm_manager") as mock_manager:
            mock_mgr = MagicMock()
            mock_mgr.is_available.return_value = True

            mock_response = MagicMock()
            mock_response.content = mock_response_content
            mock_response.total_tokens = 300
            mock_response.model = "claude-3"
            mock_response.provider = "anthropic"
            mock_mgr.prompt.return_value = mock_response

            mock_manager.return_value = mock_mgr

            analyzer = AIGapAnalyzer()
            result = analyzer.analyze([login_story, product_search_story])

            assert result.success is True
            assert result.overall_coverage == 65
            assert "admin" in result.personas_missing
            assert result.provider_used == "anthropic"

    def test_analyze_with_options(self, login_story: UserStory) -> None:
        """Test analysis with custom options."""
        options = GapOptions(
            project_context="Banking app",
            industry="fintech",
            expected_personas=["customer", "teller", "manager"],
            compliance_requirements=["PCI-DSS", "SOC2"],
        )

        with patch("spectryn.adapters.llm.create_llm_manager") as mock_manager:
            mock_manager.side_effect = Exception("LLM not configured")

            analyzer = AIGapAnalyzer(options)
            result = analyzer.analyze([login_story])

            assert result.success is True
