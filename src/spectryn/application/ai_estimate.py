"""
AI Estimation - Suggest story points based on complexity.

Uses LLM providers to analyze user stories and suggest appropriate
story point estimates based on:
- Technical complexity
- Scope and requirements
- Acceptance criteria count
- Subtask breakdown
- Historical patterns
- Risk factors
"""

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum

from spectryn.core.domain.entities import UserStory


logger = logging.getLogger(__name__)


class EstimationScale(Enum):
    """Story point estimation scale."""

    FIBONACCI = "fibonacci"  # 1, 2, 3, 5, 8, 13, 21
    LINEAR = "linear"  # 1, 2, 3, 4, 5, 6, 7, 8
    TSHIRT = "tshirt"  # XS=1, S=2, M=3, L=5, XL=8, XXL=13


class ComplexityFactor(Enum):
    """Factors that affect story complexity."""

    TECHNICAL = "technical"  # Technical difficulty
    SCOPE = "scope"  # Amount of work
    UNCERTAINTY = "uncertainty"  # Unknowns and risks
    DEPENDENCIES = "dependencies"  # External dependencies
    TESTING = "testing"  # Testing requirements
    INTEGRATION = "integration"  # Integration complexity


@dataclass
class ComplexityBreakdown:
    """Breakdown of complexity factors for a story."""

    technical: int = 3  # 1-5 scale
    scope: int = 3
    uncertainty: int = 3
    dependencies: int = 1
    testing: int = 2
    integration: int = 2

    @property
    def average(self) -> float:
        """Average complexity score."""
        factors = [
            self.technical,
            self.scope,
            self.uncertainty,
            self.dependencies,
            self.testing,
            self.integration,
        ]
        return sum(factors) / len(factors)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "technical": self.technical,
            "scope": self.scope,
            "uncertainty": self.uncertainty,
            "dependencies": self.dependencies,
            "testing": self.testing,
            "integration": self.integration,
            "average": round(self.average, 2),
        }


@dataclass
class EstimationSuggestion:
    """Estimation suggestion for a single story."""

    story_id: str
    story_title: str
    current_points: int
    suggested_points: int
    confidence: str  # "high", "medium", "low"
    reasoning: str
    complexity: ComplexityBreakdown = field(default_factory=ComplexityBreakdown)
    risk_factors: list[str] = field(default_factory=list)
    comparison_notes: str = ""  # Notes comparing to similar stories

    @property
    def points_changed(self) -> bool:
        """Whether the suggested points differ from current."""
        return self.current_points != self.suggested_points

    @property
    def change_direction(self) -> str:
        """Direction of change: 'increase', 'decrease', or 'same'."""
        if self.suggested_points > self.current_points:
            return "increase"
        if self.suggested_points < self.current_points:
            return "decrease"
        return "same"

    @property
    def points_difference(self) -> int:
        """Difference between suggested and current points."""
        return self.suggested_points - self.current_points


@dataclass
class EstimationResult:
    """Result of AI estimation analysis."""

    success: bool = True
    suggestions: list[EstimationSuggestion] = field(default_factory=list)
    total_current_points: int = 0
    total_suggested_points: int = 0
    raw_response: str = ""
    error: str | None = None
    tokens_used: int = 0
    model_used: str = ""
    provider_used: str = ""

    @property
    def stories_changed(self) -> int:
        """Count of stories with changed estimates."""
        return sum(1 for s in self.suggestions if s.points_changed)

    @property
    def points_difference(self) -> int:
        """Total difference in story points."""
        return self.total_suggested_points - self.total_current_points


@dataclass
class EstimationOptions:
    """Options for AI estimation."""

    # Estimation scale
    scale: EstimationScale = EstimationScale.FIBONACCI

    # Valid story points for the scale
    valid_points: list[int] = field(default_factory=lambda: [1, 2, 3, 5, 8, 13, 21])

    # Context
    project_context: str = ""
    tech_stack: str = ""
    team_velocity: int = 0  # Average points per sprint

    # Estimation factors to consider
    consider_technical_complexity: bool = True
    consider_scope: bool = True
    consider_uncertainty: bool = True
    consider_dependencies: bool = True

    # Reference stories for calibration
    reference_stories: list[tuple[str, int]] = field(default_factory=list)


ESTIMATION_SYSTEM_PROMPT = """You are an expert agile coach with deep experience in story point estimation.
Your task is to analyze user stories and suggest appropriate story point estimates.

Use the Fibonacci scale (1, 2, 3, 5, 8, 13, 21) for estimates:
- 1: Trivial change, very small scope
- 2: Simple task, well-understood
- 3: Small but requires some work
- 5: Medium complexity, typical story size
- 8: Complex story, significant work
- 13: Very complex, consider splitting
- 21: Epic-sized, should definitely be split

Consider these factors:
1. **Technical Complexity**: How technically challenging is the work?
2. **Scope**: How much needs to be built/changed?
3. **Uncertainty**: How well-defined are the requirements?
4. **Dependencies**: External systems, teams, or data needed?
5. **Testing**: How much testing is required?
6. **Integration**: How much integration work is needed?

Provide confidence levels:
- "high": Very confident in the estimate
- "medium": Reasonable estimate but some unknowns
- "low": Significant uncertainty, estimate is rough

Always respond with valid JSON."""


def build_estimation_prompt(
    stories: list[UserStory],
    options: EstimationOptions,
) -> str:
    """Build the prompt for story estimation."""
    context_parts = []
    if options.project_context:
        context_parts.append(f"Project Context: {options.project_context}")
    if options.tech_stack:
        context_parts.append(f"Tech Stack: {options.tech_stack}")
    if options.team_velocity:
        context_parts.append(f"Team Velocity: {options.team_velocity} points/sprint")

    context_section = (
        "\n".join(context_parts) if context_parts else "No additional context provided."
    )

    # Format reference stories if provided
    reference_section = ""
    if options.reference_stories:
        refs = []
        for title, points in options.reference_stories:
            refs.append(f"- {title}: {points} points")
        reference_section = f"""
## Reference Stories (for calibration)
{chr(10).join(refs)}
"""

    # Format stories for estimation
    stories_text = []
    for story in stories:
        ac_text = _format_acceptance_criteria(story)
        subtasks_text = _format_subtasks(story)

        story_text = f"""
### Story: {story.id} - {story.title}
**Current Story Points**: {story.story_points}
**Priority**: {story.priority.display_name}

**Description**:
{_format_description(story)}

**Acceptance Criteria**:
{ac_text}

**Subtasks**:
{subtasks_text}
"""
        stories_text.append(story_text.strip())

    scale_info = f"Use the {options.scale.value} scale: {options.valid_points}"

    return f"""Analyze the following user stories and suggest appropriate story point estimates.

## Context
{context_section}

## Estimation Scale
{scale_info}
{reference_section}
## Stories to Estimate
{chr(10).join(stories_text)}

## Output Format
Respond with a JSON object containing estimation suggestions:

```json
{{
  "suggestions": [
    {{
      "story_id": "US-001",
      "current_points": 3,
      "suggested_points": 5,
      "confidence": "high",
      "reasoning": "Story involves integration with external API and requires comprehensive error handling",
      "complexity": {{
        "technical": 4,
        "scope": 3,
        "uncertainty": 2,
        "dependencies": 3,
        "testing": 3,
        "integration": 4
      }},
      "risk_factors": [
        "External API documentation may be incomplete",
        "Authentication flow adds complexity"
      ],
      "comparison_notes": "Similar in complexity to authentication stories"
    }}
  ]
}}
```

Complexity scores are 1-5:
- 1: Very low / trivial
- 2: Low / simple
- 3: Medium / typical
- 4: High / challenging
- 5: Very high / complex

Analyze and estimate now:"""


def _format_description(story: UserStory) -> str:
    """Format story description for analysis."""
    if story.description:
        return f"""As a {story.description.role}
I want {story.description.want}
So that {story.description.benefit}"""
    return "(No description provided)"


def _format_acceptance_criteria(story: UserStory) -> str:
    """Format acceptance criteria for analysis."""
    if story.acceptance_criteria and len(story.acceptance_criteria) > 0:
        lines = []
        for ac, checked in story.acceptance_criteria:
            checkbox = "[x]" if checked else "[ ]"
            lines.append(f"- {checkbox} {ac}")
        return "\n".join(lines)
    return "(No acceptance criteria)"


def _format_subtasks(story: UserStory) -> str:
    """Format subtasks for analysis."""
    if story.subtasks:
        lines = []
        for st in story.subtasks:
            lines.append(f"- {st.name} ({st.story_points} SP)")
        return "\n".join(lines)
    return "(No subtasks)"


def parse_estimation_response(
    response: str,
    stories: list[UserStory],
    options: EstimationOptions,
) -> list[EstimationSuggestion]:
    """Parse LLM response into EstimationSuggestion objects."""
    suggestions: list[EstimationSuggestion] = []

    # Try to extract JSON from the response
    json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", response)
    if json_match:
        json_str = json_match.group(1)
    else:
        # Try to find raw JSON
        json_match = re.search(r"\{[\s\S]*\"suggestions\"[\s\S]*\}", response)
        if json_match:
            json_str = json_match.group(0)
        else:
            logger.warning("Could not find JSON in response")
            return _create_fallback_estimates(stories, options)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON: {e}")
        return _create_fallback_estimates(stories, options)

    raw_suggestions = data.get("suggestions", [])

    # Create a mapping from story ID to story
    story_map = {str(s.id): s for s in stories}

    for raw in raw_suggestions:
        story_id = raw.get("story_id", "")
        story = story_map.get(story_id)

        if not story:
            continue

        # Parse complexity breakdown
        raw_complexity = raw.get("complexity", {})
        complexity = ComplexityBreakdown(
            technical=raw_complexity.get("technical", 3),
            scope=raw_complexity.get("scope", 3),
            uncertainty=raw_complexity.get("uncertainty", 3),
            dependencies=raw_complexity.get("dependencies", 1),
            testing=raw_complexity.get("testing", 2),
            integration=raw_complexity.get("integration", 2),
        )

        suggested_points = raw.get("suggested_points", story.story_points)
        # Normalize to valid scale
        suggested_points = _normalize_to_scale(suggested_points, options.valid_points)

        suggestion = EstimationSuggestion(
            story_id=story_id,
            story_title=story.title,
            current_points=story.story_points,
            suggested_points=suggested_points,
            confidence=raw.get("confidence", "medium"),
            reasoning=raw.get("reasoning", ""),
            complexity=complexity,
            risk_factors=raw.get("risk_factors", []),
            comparison_notes=raw.get("comparison_notes", ""),
        )
        suggestions.append(suggestion)

    return suggestions


def _normalize_to_scale(points: int, valid_points: list[int]) -> int:
    """Normalize points to the closest value in the scale."""
    if points in valid_points:
        return points
    # Find closest valid point
    return min(valid_points, key=lambda x: abs(x - points))


def _create_fallback_estimates(
    stories: list[UserStory],
    options: EstimationOptions,
) -> list[EstimationSuggestion]:
    """Create basic estimates when LLM parsing fails."""
    suggestions = []

    for story in stories:
        # Simple heuristic-based estimation
        estimated_points = _heuristic_estimate(story, options)

        suggestions.append(
            EstimationSuggestion(
                story_id=str(story.id),
                story_title=story.title,
                current_points=story.story_points,
                suggested_points=estimated_points,
                confidence="low",
                reasoning="Fallback estimate based on story structure",
                complexity=ComplexityBreakdown(),
                risk_factors=[],
            )
        )

    return suggestions


def _heuristic_estimate(story: UserStory, options: EstimationOptions) -> int:
    """Simple heuristic-based estimation."""
    base_points = 3  # Default medium

    # Adjust based on acceptance criteria count
    ac_count = len(story.acceptance_criteria) if story.acceptance_criteria else 0
    if ac_count == 0:
        base_points = 3  # Unknown complexity
    elif ac_count <= 2:
        base_points = 2
    elif ac_count <= 4:
        base_points = 3
    elif ac_count <= 6:
        base_points = 5
    else:
        base_points = 8

    # Adjust based on subtask count
    subtask_count = len(story.subtasks) if story.subtasks else 0
    if subtask_count > 5:
        base_points = max(base_points, 8)
    elif subtask_count > 3:
        base_points = max(base_points, 5)

    # Normalize to scale
    return _normalize_to_scale(base_points, options.valid_points)


class AIEstimator:
    """
    Suggests story point estimates using LLM analysis.

    Analyzes story complexity, scope, and requirements to suggest
    appropriate story point estimates.
    """

    def __init__(
        self,
        options: EstimationOptions | None = None,
    ):
        """
        Initialize the estimator.

        Args:
            options: Estimation options. Uses defaults if not provided.
        """
        self.options = options or EstimationOptions()
        self.logger = logging.getLogger(__name__)

    def estimate(
        self,
        stories: list[UserStory],
        options: EstimationOptions | None = None,
    ) -> EstimationResult:
        """
        Analyze stories and suggest point estimates.

        Args:
            stories: List of user stories to estimate.
            options: Override estimation options.

        Returns:
            EstimationResult with suggestions for each story.
        """
        from spectryn.adapters.llm import create_llm_manager

        opts = options or self.options
        result = EstimationResult()

        if not stories:
            result.success = False
            result.error = "No stories provided for estimation"
            return result

        # Calculate current totals
        result.total_current_points = sum(s.story_points for s in stories)

        # Get LLM manager
        try:
            manager = create_llm_manager()
        except Exception as e:
            # Fallback to heuristic estimation
            self.logger.warning(f"LLM not available, using heuristic estimation: {e}")
            result.suggestions = _create_fallback_estimates(stories, opts)
            result.total_suggested_points = sum(s.suggested_points for s in result.suggestions)
            return result

        if not manager.is_available():
            # Fallback to heuristic estimation
            self.logger.warning("No LLM providers available, using heuristic estimation")
            result.suggestions = _create_fallback_estimates(stories, opts)
            result.total_suggested_points = sum(s.suggested_points for s in result.suggestions)
            return result

        # Build prompt
        prompt = build_estimation_prompt(stories, opts)

        # Generate
        try:
            response = manager.prompt(
                user_message=prompt,
                system_prompt=ESTIMATION_SYSTEM_PROMPT,
            )

            result.raw_response = response.content
            result.tokens_used = response.total_tokens
            result.model_used = response.model
            result.provider_used = response.provider

        except Exception as e:
            # Fallback to heuristic estimation
            self.logger.warning(f"LLM call failed, using heuristic estimation: {e}")
            result.suggestions = _create_fallback_estimates(stories, opts)
            result.total_suggested_points = sum(s.suggested_points for s in result.suggestions)
            return result

        # Parse response
        try:
            result.suggestions = parse_estimation_response(response.content, stories, opts)
            result.total_suggested_points = sum(s.suggested_points for s in result.suggestions)

            if not result.suggestions:
                result.success = False
                result.error = "No suggestions could be parsed from the response"
                # Fallback
                result.suggestions = _create_fallback_estimates(stories, opts)
                result.total_suggested_points = sum(s.suggested_points for s in result.suggestions)

        except Exception as e:
            result.success = False
            result.error = f"Failed to parse estimation response: {e}"
            result.suggestions = _create_fallback_estimates(stories, opts)
            result.total_suggested_points = sum(s.suggested_points for s in result.suggestions)

        return result

    def estimate_from_markdown(
        self,
        markdown_path: str,
        options: EstimationOptions | None = None,
    ) -> EstimationResult:
        """
        Estimate stories from a markdown file.

        Args:
            markdown_path: Path to markdown file containing stories.
            options: Override estimation options.

        Returns:
            EstimationResult with suggestions for each story.
        """
        from pathlib import Path

        from spectryn.adapters import MarkdownParser

        result = EstimationResult()

        # Parse the markdown file
        try:
            parser = MarkdownParser()
            epic = parser.parse_epic(Path(markdown_path))
        except Exception as e:
            result.success = False
            result.error = f"Failed to parse markdown file: {e}"
            return result

        if not epic or not epic.stories:
            result.success = False
            result.error = "No stories found in the markdown file"
            return result

        return self.estimate(epic.stories, options)


def estimate_stories(
    stories: list[UserStory],
    project_context: str = "",
    tech_stack: str = "",
    scale: str = "fibonacci",
) -> EstimationResult:
    """
    Convenience function to estimate story points.

    Args:
        stories: List of user stories to estimate.
        project_context: Optional project context.
        tech_stack: Optional tech stack info.
        scale: Estimation scale (fibonacci, linear, tshirt).

    Returns:
        EstimationResult with suggestions for each story.
    """
    try:
        estimation_scale = EstimationScale(scale)
    except ValueError:
        estimation_scale = EstimationScale.FIBONACCI

    # Set valid points based on scale
    if estimation_scale == EstimationScale.FIBONACCI:
        valid_points = [1, 2, 3, 5, 8, 13, 21]
    elif estimation_scale == EstimationScale.LINEAR:
        valid_points = [1, 2, 3, 4, 5, 6, 7, 8]
    else:  # T-shirt
        valid_points = [1, 2, 3, 5, 8, 13]

    options = EstimationOptions(
        scale=estimation_scale,
        valid_points=valid_points,
        project_context=project_context,
        tech_stack=tech_stack,
    )

    estimator = AIEstimator(options)
    return estimator.estimate(stories, options)
