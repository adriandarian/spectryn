"""
AI Gap Analysis - Identify missing requirements.

Uses LLM providers to analyze user stories and identify:
- Missing user personas (roles not covered)
- Missing functional areas
- Missing non-functional requirements (security, performance, etc.)
- Missing edge cases
- Missing integrations
- Incomplete user journeys
"""

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum

from spectryn.core.domain.entities import UserStory


logger = logging.getLogger(__name__)


class GapCategory(Enum):
    """Category of identified gap."""

    PERSONA = "persona"  # Missing user roles
    FUNCTIONAL = "functional"  # Missing features/functionality
    NON_FUNCTIONAL = "non_functional"  # NFRs like security, performance
    EDGE_CASE = "edge_case"  # Missing error handling, edge cases
    INTEGRATION = "integration"  # Missing system integrations
    USER_JOURNEY = "user_journey"  # Incomplete flows
    ACCESSIBILITY = "accessibility"  # A11y gaps
    DATA = "data"  # Data handling gaps
    COMPLIANCE = "compliance"  # Regulatory/compliance gaps
    TESTING = "testing"  # Missing test scenarios


class GapPriority(Enum):
    """Priority of the identified gap."""

    CRITICAL = "critical"  # Must have for MVP
    HIGH = "high"  # Important for release
    MEDIUM = "medium"  # Should have
    LOW = "low"  # Nice to have


class GapConfidence(Enum):
    """Confidence level of gap identification."""

    HIGH = "high"  # Clearly missing
    MEDIUM = "medium"  # Likely missing
    LOW = "low"  # Possibly missing


@dataclass
class IdentifiedGap:
    """A gap identified in the requirements."""

    title: str
    description: str
    category: GapCategory
    priority: GapPriority
    confidence: GapConfidence = GapConfidence.MEDIUM
    related_stories: list[str] = field(default_factory=list)
    suggested_story: str = ""  # Suggested user story to fill gap
    rationale: str = ""  # Why this is considered a gap
    affected_areas: list[str] = field(default_factory=list)

    @property
    def priority_score(self) -> int:
        """Numeric priority score for sorting."""
        scores = {
            GapPriority.CRITICAL: 4,
            GapPriority.HIGH: 3,
            GapPriority.MEDIUM: 2,
            GapPriority.LOW: 1,
        }
        return scores.get(self.priority, 0)


@dataclass
class CategoryAnalysis:
    """Analysis for a specific gap category."""

    category: GapCategory
    gaps: list[IdentifiedGap] = field(default_factory=list)
    coverage_score: float = 0.0  # 0-100 estimated coverage
    recommendations: list[str] = field(default_factory=list)

    @property
    def gap_count(self) -> int:
        """Number of gaps in this category."""
        return len(self.gaps)

    @property
    def has_critical_gaps(self) -> bool:
        """Whether category has critical gaps."""
        return any(g.priority == GapPriority.CRITICAL for g in self.gaps)


@dataclass
class GapResult:
    """Result of gap analysis."""

    success: bool = True
    all_gaps: list[IdentifiedGap] = field(default_factory=list)
    category_analyses: list[CategoryAnalysis] = field(default_factory=list)
    personas_found: list[str] = field(default_factory=list)
    personas_missing: list[str] = field(default_factory=list)
    functional_areas: list[str] = field(default_factory=list)
    overall_coverage: float = 0.0  # 0-100
    summary: str = ""
    raw_response: str = ""
    error: str | None = None
    tokens_used: int = 0
    model_used: str = ""
    provider_used: str = ""

    @property
    def critical_gap_count(self) -> int:
        """Count of critical gaps."""
        return sum(1 for g in self.all_gaps if g.priority == GapPriority.CRITICAL)

    @property
    def high_gap_count(self) -> int:
        """Count of high priority gaps."""
        return sum(1 for g in self.all_gaps if g.priority == GapPriority.HIGH)

    @property
    def total_gap_count(self) -> int:
        """Total number of gaps."""
        return len(self.all_gaps)


@dataclass
class GapOptions:
    """Options for gap analysis."""

    # Categories to analyze
    check_personas: bool = True
    check_functional: bool = True
    check_nfr: bool = True
    check_edge_cases: bool = True
    check_integrations: bool = True
    check_accessibility: bool = True

    # Context
    project_context: str = ""
    expected_personas: list[str] = field(default_factory=list)
    expected_integrations: list[str] = field(default_factory=list)
    industry: str = ""  # e.g., "healthcare", "fintech"
    compliance_requirements: list[str] = field(default_factory=list)

    # Output
    min_confidence: GapConfidence = GapConfidence.LOW
    include_suggestions: bool = True


GAP_SYSTEM_PROMPT = """You are an expert requirements analyst specializing in identifying gaps and missing requirements.

Your task is to analyze user stories and identify what's missing:

## Gap Categories

1. **Persona Gaps**: Missing user roles (e.g., admin users not considered)
2. **Functional Gaps**: Missing features needed for complete functionality
3. **Non-Functional Gaps**: Missing NFRs (security, performance, scalability, etc.)
4. **Edge Case Gaps**: Missing error handling, unusual scenarios
5. **Integration Gaps**: Missing connections to other systems
6. **User Journey Gaps**: Incomplete flows (e.g., no logout after login)
7. **Accessibility Gaps**: Missing a11y considerations
8. **Data Gaps**: Missing data handling (backup, privacy, retention)
9. **Compliance Gaps**: Missing regulatory requirements
10. **Testing Gaps**: Missing test scenarios

## Analysis Approach

1. Read all stories to understand scope
2. Identify what's there vs what should be there
3. Consider industry standards and best practices
4. Think about the complete user journey
5. Consider edge cases and failure modes

Be thorough but prioritize:
- Critical gaps that block basic functionality
- High priority gaps for production readiness
- Medium/Low for completeness

Always respond with valid JSON."""


def build_gap_prompt(
    stories: list[UserStory],
    options: GapOptions,
) -> str:
    """Build the prompt for gap analysis."""
    # Extract personas from stories
    personas = set()
    functional_areas = set()

    for story in stories:
        if story.description:
            personas.add(story.description.role.lower())
        for label in story.labels:
            functional_areas.add(label.lower())

    # Format stories
    stories_text = []
    for story in stories:
        desc = ""
        if story.description:
            desc = f"As a {story.description.role}, I want {story.description.want}, so that {story.description.benefit}"

        ac_count = len(story.acceptance_criteria) if story.acceptance_criteria else 0
        story_text = f"""
### {story.id}: {story.title}
{desc}
AC: {ac_count} criteria | Labels: {", ".join(story.labels) if story.labels else "(none)"}
"""
        stories_text.append(story_text.strip())

    # Build category list
    categories = []
    if options.check_personas:
        categories.append("persona")
    if options.check_functional:
        categories.append("functional")
    if options.check_nfr:
        categories.append("non_functional")
    if options.check_edge_cases:
        categories.append("edge_case")
    if options.check_integrations:
        categories.append("integration")
    if options.check_accessibility:
        categories.append("accessibility")

    context_section = ""
    if options.project_context:
        context_section += f"\n**Project**: {options.project_context}"
    if options.industry:
        context_section += f"\n**Industry**: {options.industry}"
    if options.expected_personas:
        context_section += f"\n**Expected Personas**: {', '.join(options.expected_personas)}"
    if options.expected_integrations:
        context_section += (
            f"\n**Expected Integrations**: {', '.join(options.expected_integrations)}"
        )
    if options.compliance_requirements:
        context_section += f"\n**Compliance**: {', '.join(options.compliance_requirements)}"

    return f"""Analyze the following user stories and identify gaps in requirements coverage.

## Context
{context_section or "No additional context provided."}

## Current Coverage
- **Personas found**: {", ".join(sorted(personas)) or "(none)"}
- **Functional areas**: {", ".join(sorted(functional_areas)) or "(none)"}
- **Story count**: {len(stories)}

## Categories to Analyze
{", ".join(categories)}

## User Stories
{chr(10).join(stories_text)}

## Output Format
Respond with a JSON object:

```json
{{
  "gaps": [
    {{
      "title": "Missing Admin Dashboard",
      "description": "No stories cover administrative functions",
      "category": "functional",
      "priority": "high",
      "confidence": "high",
      "related_stories": ["US-001", "US-003"],
      "suggested_story": "As an admin, I want to view system metrics so that I can monitor health",
      "rationale": "Admin users need oversight capabilities",
      "affected_areas": ["admin", "monitoring"]
    }}
  ],
  "category_analyses": [
    {{
      "category": "persona",
      "coverage_score": 60,
      "recommendations": ["Add admin user stories", "Consider support staff persona"]
    }}
  ],
  "personas_found": ["customer", "user"],
  "personas_missing": ["admin", "support staff"],
  "functional_areas": ["auth", "shopping"],
  "overall_coverage": 65,
  "summary": "Good feature coverage but missing admin and NFR stories"
}}
```

Categories: persona, functional, non_functional, edge_case, integration, user_journey, accessibility, data, compliance, testing
Priorities: critical, high, medium, low
Confidence: high, medium, low

Analyze and identify gaps now:"""


def parse_gap_response(response: str, stories: list[UserStory]) -> GapResult:
    """Parse LLM response into gap result."""
    result = GapResult()

    # Try to extract JSON
    json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", response)
    if json_match:
        json_str = json_match.group(1)
    else:
        json_match = re.search(r"\{[\s\S]*\"gaps\"[\s\S]*\}", response)
        if json_match:
            json_str = json_match.group(0)
        else:
            logger.warning("Could not find JSON in response")
            result.success = False
            result.error = "Failed to parse response"
            return result

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON: {e}")
        result.success = False
        result.error = f"JSON parse error: {e}"
        return result

    # Parse gaps
    valid_story_ids = {str(s.id) for s in stories}

    for raw_gap in data.get("gaps", []):
        # Parse category
        try:
            category = GapCategory(raw_gap.get("category", "functional"))
        except ValueError:
            category = GapCategory.FUNCTIONAL

        # Parse priority
        try:
            priority = GapPriority(raw_gap.get("priority", "medium"))
        except ValueError:
            priority = GapPriority.MEDIUM

        # Parse confidence
        try:
            confidence = GapConfidence(raw_gap.get("confidence", "medium"))
        except ValueError:
            confidence = GapConfidence.MEDIUM

        # Filter related stories to valid ones
        related = [s for s in raw_gap.get("related_stories", []) if s in valid_story_ids]

        gap = IdentifiedGap(
            title=raw_gap.get("title", "Unknown Gap"),
            description=raw_gap.get("description", ""),
            category=category,
            priority=priority,
            confidence=confidence,
            related_stories=related,
            suggested_story=raw_gap.get("suggested_story", ""),
            rationale=raw_gap.get("rationale", ""),
            affected_areas=raw_gap.get("affected_areas", []),
        )
        result.all_gaps.append(gap)

    # Parse category analyses
    for raw_cat in data.get("category_analyses", []):
        try:
            category = GapCategory(raw_cat.get("category", "functional"))
        except ValueError:
            continue

        cat_analysis = CategoryAnalysis(
            category=category,
            coverage_score=raw_cat.get("coverage_score", 0.0),
            recommendations=raw_cat.get("recommendations", []),
        )
        # Add gaps for this category
        cat_analysis.gaps = [g for g in result.all_gaps if g.category == category]
        result.category_analyses.append(cat_analysis)

    # Parse other fields
    result.personas_found = data.get("personas_found", [])
    result.personas_missing = data.get("personas_missing", [])
    result.functional_areas = data.get("functional_areas", [])
    result.overall_coverage = data.get("overall_coverage", 0.0)
    result.summary = data.get("summary", "")

    return result


def analyze_gaps_fallback(
    stories: list[UserStory],
    options: GapOptions,
) -> GapResult:
    """Fallback gap analysis without LLM."""
    result = GapResult()

    # Extract existing personas
    personas: set[str] = set()
    for story in stories:
        if story.description:
            personas.add(story.description.role.lower())

    result.personas_found = sorted(personas)

    # Check for common missing personas
    common_personas = {"admin", "administrator", "support", "guest", "anonymous"}
    missing = common_personas - personas
    result.personas_missing = sorted(missing)

    # Add persona gaps
    for missing_persona in result.personas_missing:
        gap = IdentifiedGap(
            title=f"Missing {missing_persona.title()} User Stories",
            description=f"No stories found for {missing_persona} persona",
            category=GapCategory.PERSONA,
            priority=GapPriority.MEDIUM,
            confidence=GapConfidence.LOW,
            rationale="Common persona not covered",
            suggested_story=f"As a {missing_persona}, I want to [action], so that [benefit]",
        )
        result.all_gaps.append(gap)

    # Check for NFR gaps
    nfr_keywords = {
        "security": ["security", "auth", "permission", "encrypt"],
        "performance": ["performance", "speed", "fast", "optimize"],
        "accessibility": ["accessibility", "a11y", "screen reader", "wcag"],
        "error handling": ["error", "fail", "exception", "invalid"],
    }

    all_text = " ".join(
        f"{s.title} {s.description.want if s.description else ''}" for s in stories
    ).lower()

    for nfr, keywords in nfr_keywords.items():
        if not any(kw in all_text for kw in keywords):
            gap = IdentifiedGap(
                title=f"Missing {nfr.title()} Requirements",
                description=f"No stories explicitly address {nfr}",
                category=GapCategory.NON_FUNCTIONAL,
                priority=GapPriority.MEDIUM,
                confidence=GapConfidence.LOW,
                rationale=f"Common NFR ({nfr}) not explicitly covered",
            )
            result.all_gaps.append(gap)

    # Check for journey gaps (login without logout, etc.)
    has_login = any("login" in s.title.lower() or "sign in" in s.title.lower() for s in stories)
    has_logout = any("logout" in s.title.lower() or "sign out" in s.title.lower() for s in stories)

    if has_login and not has_logout:
        gap = IdentifiedGap(
            title="Missing Logout Functionality",
            description="Login stories exist but no logout story found",
            category=GapCategory.USER_JOURNEY,
            priority=GapPriority.HIGH,
            confidence=GapConfidence.HIGH,
            rationale="Incomplete authentication journey",
            suggested_story="As a logged-in user, I want to log out, so that I can secure my session",
        )
        result.all_gaps.append(gap)

    has_create = any("create" in s.title.lower() or "add" in s.title.lower() for s in stories)
    has_delete = any("delete" in s.title.lower() or "remove" in s.title.lower() for s in stories)

    if has_create and not has_delete:
        gap = IdentifiedGap(
            title="Missing Delete Functionality",
            description="Create/add stories exist but no delete/remove story found",
            category=GapCategory.FUNCTIONAL,
            priority=GapPriority.MEDIUM,
            confidence=GapConfidence.MEDIUM,
            rationale="Incomplete CRUD operations",
            suggested_story="As a user, I want to delete items, so that I can remove unwanted content",
        )
        result.all_gaps.append(gap)

    # Calculate coverage
    gaps_found = len(result.all_gaps)
    result.overall_coverage = max(0, 100 - (gaps_found * 10))

    result.summary = f"Found {len(result.all_gaps)} potential gaps using heuristic analysis"

    return result


class AIGapAnalyzer:
    """
    Analyzes user stories to identify missing requirements.

    Uses LLM analysis and heuristics to find gaps in coverage.
    """

    def __init__(self, options: GapOptions | None = None):
        """
        Initialize the analyzer.

        Args:
            options: Analysis options. Uses defaults if not provided.
        """
        self.options = options or GapOptions()
        self.logger = logging.getLogger(__name__)

    def analyze(
        self,
        stories: list[UserStory],
        options: GapOptions | None = None,
    ) -> GapResult:
        """
        Analyze stories for requirement gaps.

        Args:
            stories: List of user stories to analyze.
            options: Override analysis options.

        Returns:
            GapResult with identified gaps.
        """
        from spectryn.adapters.llm import create_llm_manager

        opts = options or self.options

        if not stories:
            return GapResult(
                success=False,
                error="No stories provided for gap analysis",
            )

        # Try LLM analysis first
        try:
            manager = create_llm_manager()
            if manager.is_available():
                prompt = build_gap_prompt(stories, opts)

                response = manager.prompt(
                    user_message=prompt,
                    system_prompt=GAP_SYSTEM_PROMPT,
                )

                result = parse_gap_response(response.content, stories)
                result.raw_response = response.content
                result.tokens_used = response.total_tokens
                result.model_used = response.model
                result.provider_used = response.provider

                # Filter by confidence
                if opts.min_confidence != GapConfidence.LOW:
                    min_level = 2 if opts.min_confidence == GapConfidence.MEDIUM else 3
                    confidence_scores = {
                        GapConfidence.LOW: 1,
                        GapConfidence.MEDIUM: 2,
                        GapConfidence.HIGH: 3,
                    }
                    result.all_gaps = [
                        g for g in result.all_gaps if confidence_scores[g.confidence] >= min_level
                    ]

                return result

        except Exception as e:
            self.logger.warning(f"LLM analysis failed: {e}")

        # Fallback to heuristic analysis
        return analyze_gaps_fallback(stories, opts)


def analyze_gaps(
    stories: list[UserStory],
    project_context: str = "",
    industry: str = "",
) -> GapResult:
    """
    Convenience function to analyze requirement gaps.

    Args:
        stories: List of user stories to analyze.
        project_context: Optional project context.
        industry: Optional industry context.

    Returns:
        GapResult with identified gaps.
    """
    options = GapOptions(
        project_context=project_context,
        industry=industry,
    )

    analyzer = AIGapAnalyzer(options)
    return analyzer.analyze(stories, options)
