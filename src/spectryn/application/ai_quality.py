"""
AI Story Quality Scoring - Rate story quality based on best practices.

Uses LLM providers to analyze user stories and score them on:
- INVEST principles (Independent, Negotiable, Valuable, Estimable, Small, Testable)
- Description completeness
- Acceptance criteria quality
- Clarity and specificity
"""

import contextlib
import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum

from spectryn.core.domain.entities import UserStory


logger = logging.getLogger(__name__)


class QualityDimension(Enum):
    """Dimensions for quality scoring."""

    INDEPENDENT = "independent"  # Can be developed without dependencies
    NEGOTIABLE = "negotiable"  # Details can be discussed
    VALUABLE = "valuable"  # Delivers value to user/business
    ESTIMABLE = "estimable"  # Can estimate effort
    SMALL = "small"  # Can complete in one sprint
    TESTABLE = "testable"  # Has clear test criteria

    # Additional dimensions
    CLARITY = "clarity"  # Clear and unambiguous
    COMPLETENESS = "completeness"  # Has all required elements
    SPECIFICITY = "specificity"  # Specific, not vague
    AC_QUALITY = "ac_quality"  # Acceptance criteria quality


class QualityLevel(Enum):
    """Overall quality level."""

    EXCELLENT = "excellent"  # 90-100
    GOOD = "good"  # 70-89
    FAIR = "fair"  # 50-69
    POOR = "poor"  # 30-49
    NEEDS_WORK = "needs_work"  # 0-29


@dataclass
class DimensionScore:
    """Score for a single quality dimension."""

    dimension: QualityDimension
    score: int  # 0-100
    feedback: str
    suggestions: list[str] = field(default_factory=list)

    @property
    def level(self) -> str:
        """Get level description for this score."""
        if self.score >= 90:
            return "excellent"
        if self.score >= 70:
            return "good"
        if self.score >= 50:
            return "fair"
        if self.score >= 30:
            return "poor"
        return "needs_work"


@dataclass
class StoryQualityScore:
    """Quality score for a single story."""

    story_id: str
    story_title: str
    overall_score: int  # 0-100
    overall_level: QualityLevel
    dimension_scores: list[DimensionScore] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    improvement_suggestions: list[str] = field(default_factory=list)
    invest_score: int = 0  # Combined INVEST score

    @property
    def is_passing(self) -> bool:
        """Whether this story passes minimum quality threshold."""
        return self.overall_score >= 50

    @property
    def lowest_dimension(self) -> DimensionScore | None:
        """Get the lowest scoring dimension."""
        if not self.dimension_scores:
            return None
        return min(self.dimension_scores, key=lambda d: d.score)

    @property
    def highest_dimension(self) -> DimensionScore | None:
        """Get the highest scoring dimension."""
        if not self.dimension_scores:
            return None
        return max(self.dimension_scores, key=lambda d: d.score)


@dataclass
class QualityResult:
    """Result of AI quality scoring."""

    success: bool = True
    scores: list[StoryQualityScore] = field(default_factory=list)
    average_score: float = 0.0
    passing_count: int = 0
    failing_count: int = 0
    raw_response: str = ""
    error: str | None = None
    tokens_used: int = 0
    model_used: str = ""
    provider_used: str = ""

    @property
    def pass_rate(self) -> float:
        """Percentage of stories passing quality threshold."""
        total = len(self.scores)
        if total == 0:
            return 0.0
        return (self.passing_count / total) * 100


@dataclass
class QualityOptions:
    """Options for quality scoring."""

    # Dimensions to score
    score_invest: bool = True  # Score INVEST principles
    score_clarity: bool = True  # Score clarity
    score_completeness: bool = True  # Score completeness
    score_ac_quality: bool = True  # Score acceptance criteria

    # Thresholds
    min_passing_score: int = 50  # Minimum score to pass

    # Context
    project_context: str = ""
    tech_stack: str = ""


QUALITY_SYSTEM_PROMPT = """You are an expert agile coach and quality assurance specialist.
Your task is to analyze user stories and score their quality based on best practices.

## INVEST Principles

Score each story against INVEST criteria (0-100 each):

1. **Independent** (0-100): Can be developed without depending on other stories
   - 100: Fully standalone
   - 50: Some dependencies but manageable
   - 0: Tightly coupled, can't be done alone

2. **Negotiable** (0-100): Details can be discussed and refined
   - 100: High-level, room for discussion
   - 50: Some flexibility
   - 0: Too prescriptive, implementation details specified

3. **Valuable** (0-100): Delivers clear value to user or business
   - 100: Clear, significant value proposition
   - 50: Some value, could be clearer
   - 0: No clear value, technical task

4. **Estimable** (0-100): Team can estimate effort required
   - 100: Clear scope, easy to estimate
   - 50: Some ambiguity but estimable
   - 0: Too vague, can't estimate

5. **Small** (0-100): Can be completed in one sprint
   - 100: 1-5 story points
   - 70: 6-8 story points
   - 50: 9-13 story points
   - 0: 14+ points or unclear

6. **Testable** (0-100): Has clear, verifiable acceptance criteria
   - 100: Clear AC, easily testable
   - 50: Some AC but could be clearer
   - 0: No AC or untestable

## Additional Dimensions

7. **Clarity** (0-100): Clear, unambiguous language
8. **Completeness** (0-100): Has description, AC, and necessary details
9. **Specificity** (0-100): Specific rather than vague
10. **AC Quality** (0-100): Acceptance criteria are well-written

Provide specific, actionable improvement suggestions for low-scoring dimensions.

Always respond with valid JSON."""


def build_quality_prompt(
    stories: list[UserStory],
    options: QualityOptions,
) -> str:
    """Build the prompt for quality scoring."""
    context_parts = []
    if options.project_context:
        context_parts.append(f"Project Context: {options.project_context}")
    if options.tech_stack:
        context_parts.append(f"Tech Stack: {options.tech_stack}")

    context_section = (
        "\n".join(context_parts) if context_parts else "No additional context provided."
    )

    # Format stories
    stories_text = []
    for story in stories:
        ac_text = _format_acceptance_criteria(story)
        ac_count = len(story.acceptance_criteria) if story.acceptance_criteria else 0

        story_text = f"""
### {story.id}: {story.title}

**Story Points**: {story.story_points or "Not estimated"}
**Priority**: {story.priority.display_name}
**Labels**: {", ".join(story.labels) if story.labels else "(none)"}

**Description**:
{_format_description(story)}

**Acceptance Criteria** ({ac_count}):
{ac_text}

**Technical Notes**: {story.technical_notes or "(none)"}
"""
        stories_text.append(story_text.strip())

    dimensions = []
    if options.score_invest:
        dimensions.extend(
            ["independent", "negotiable", "valuable", "estimable", "small", "testable"]
        )
    if options.score_clarity:
        dimensions.append("clarity")
    if options.score_completeness:
        dimensions.append("completeness")
    if options.score_ac_quality:
        dimensions.append("ac_quality")

    return f"""Score the quality of the following user stories.

## Context
{context_section}

## Dimensions to Score
{", ".join(dimensions)}

## Stories to Score
{chr(10).join(stories_text)}

## Output Format
Respond with a JSON object containing quality scores:

```json
{{
  "scores": [
    {{
      "story_id": "US-001",
      "story_title": "User Login",
      "overall_score": 75,
      "overall_level": "good",
      "invest_score": 78,
      "dimension_scores": [
        {{
          "dimension": "independent",
          "score": 90,
          "feedback": "Story can be developed independently",
          "suggestions": []
        }},
        {{
          "dimension": "testable",
          "score": 60,
          "feedback": "Acceptance criteria could be more specific",
          "suggestions": ["Add specific validation rules", "Include error scenarios"]
        }}
      ],
      "strengths": ["Clear value proposition", "Good description format"],
      "weaknesses": ["AC could be more specific", "Missing edge cases"],
      "improvement_suggestions": [
        "Add acceptance criteria for error handling",
        "Specify input validation rules"
      ]
    }}
  ]
}}
```

Quality levels: "excellent" (90+), "good" (70-89), "fair" (50-69), "poor" (30-49), "needs_work" (0-29)
Dimensions: "independent", "negotiable", "valuable", "estimable", "small", "testable", "clarity", "completeness", "specificity", "ac_quality"

Score the stories now:"""


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


def parse_quality_response(
    response: str,
    stories: list[UserStory],
    options: QualityOptions,
) -> list[StoryQualityScore]:
    """Parse LLM response into StoryQualityScore objects."""
    scores: list[StoryQualityScore] = []

    # Try to extract JSON from the response
    json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", response)
    if json_match:
        json_str = json_match.group(1)
    else:
        json_match = re.search(r"\{[\s\S]*\"scores\"[\s\S]*\}", response)
        if json_match:
            json_str = json_match.group(0)
        else:
            logger.warning("Could not find JSON in response")
            return _create_fallback_scores(stories, options)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON: {e}")
        return _create_fallback_scores(stories, options)

    raw_scores = data.get("scores", [])

    # Create a mapping from story ID to story
    story_map = {str(s.id): s for s in stories}

    for raw in raw_scores:
        story_id = raw.get("story_id", "")
        story = story_map.get(story_id)

        if not story:
            continue

        # Parse dimension scores
        dimension_scores = []
        for raw_dim in raw.get("dimension_scores", []):
            with contextlib.suppress(ValueError):
                dim = QualityDimension(raw_dim.get("dimension", "clarity"))
                dimension_scores.append(
                    DimensionScore(
                        dimension=dim,
                        score=raw_dim.get("score", 50),
                        feedback=raw_dim.get("feedback", ""),
                        suggestions=raw_dim.get("suggestions", []),
                    )
                )

        # Parse overall level
        try:
            overall_level = QualityLevel(raw.get("overall_level", "fair"))
        except ValueError:
            overall_level = QualityLevel.FAIR

        score = StoryQualityScore(
            story_id=story_id,
            story_title=story.title,
            overall_score=raw.get("overall_score", 50),
            overall_level=overall_level,
            dimension_scores=dimension_scores,
            strengths=raw.get("strengths", []),
            weaknesses=raw.get("weaknesses", []),
            improvement_suggestions=raw.get("improvement_suggestions", []),
            invest_score=raw.get("invest_score", 0),
        )
        scores.append(score)

    return scores


def _create_fallback_scores(
    stories: list[UserStory],
    options: QualityOptions,
) -> list[StoryQualityScore]:
    """Create basic quality scores when LLM parsing fails."""
    scores = []

    for story in stories:
        dimension_scores = []
        total_score = 0
        count = 0

        # Score based on available data
        has_description = story.description is not None
        has_ac = story.acceptance_criteria and len(story.acceptance_criteria) > 0
        has_points = story.story_points and story.story_points > 0
        ac_count = len(story.acceptance_criteria) if story.acceptance_criteria else 0

        # Completeness
        completeness = 0
        if has_description:
            completeness += 40
        if has_ac:
            completeness += 40
        if has_points:
            completeness += 20
        dimension_scores.append(
            DimensionScore(
                dimension=QualityDimension.COMPLETENESS,
                score=completeness,
                feedback="Based on available story elements",
                suggestions=[] if completeness >= 80 else ["Add missing elements"],
            )
        )
        total_score += completeness
        count += 1

        # Testable
        testable = 0
        if ac_count >= 3:
            testable = 80
        elif ac_count >= 1:
            testable = 50
        else:
            testable = 20
        dimension_scores.append(
            DimensionScore(
                dimension=QualityDimension.TESTABLE,
                score=testable,
                feedback=f"Story has {ac_count} acceptance criteria",
                suggestions=[] if testable >= 70 else ["Add more acceptance criteria"],
            )
        )
        total_score += testable
        count += 1

        # Small
        small = 70
        if story.story_points:
            if story.story_points <= 5:
                small = 100
            elif story.story_points <= 8:
                small = 80
            elif story.story_points <= 13:
                small = 50
            else:
                small = 30
        dimension_scores.append(
            DimensionScore(
                dimension=QualityDimension.SMALL,
                score=small,
                feedback=f"Story is {story.story_points or 'not'} estimated",
                suggestions=[] if small >= 70 else ["Consider splitting this story"],
            )
        )
        total_score += small
        count += 1

        # Valuable
        valuable = 50
        if has_description and story.description and story.description.benefit:
            valuable = 80 if len(story.description.benefit) > 20 else 60
        dimension_scores.append(
            DimensionScore(
                dimension=QualityDimension.VALUABLE,
                score=valuable,
                feedback="Based on 'so that' clause",
                suggestions=[] if valuable >= 70 else ["Clarify the business value"],
            )
        )
        total_score += valuable
        count += 1

        overall_score = total_score // count if count > 0 else 50

        # Determine level
        if overall_score >= 90:
            level = QualityLevel.EXCELLENT
        elif overall_score >= 70:
            level = QualityLevel.GOOD
        elif overall_score >= 50:
            level = QualityLevel.FAIR
        elif overall_score >= 30:
            level = QualityLevel.POOR
        else:
            level = QualityLevel.NEEDS_WORK

        # Build strengths and weaknesses
        strengths = []
        weaknesses = []
        for ds in dimension_scores:
            if ds.score >= 70:
                strengths.append(f"{ds.dimension.value}: {ds.feedback}")
            elif ds.score < 50:
                weaknesses.append(f"{ds.dimension.value}: {ds.feedback}")

        scores.append(
            StoryQualityScore(
                story_id=str(story.id),
                story_title=story.title,
                overall_score=overall_score,
                overall_level=level,
                dimension_scores=dimension_scores,
                strengths=strengths,
                weaknesses=weaknesses,
                improvement_suggestions=[s for ds in dimension_scores for s in ds.suggestions],
                invest_score=overall_score,
            )
        )

    return scores


class AIQualityScorer:
    """
    Scores user story quality using LLM analysis.

    Analyzes stories against INVEST principles and other
    quality dimensions.
    """

    def __init__(
        self,
        options: QualityOptions | None = None,
    ):
        """
        Initialize the scorer.

        Args:
            options: Scoring options. Uses defaults if not provided.
        """
        self.options = options or QualityOptions()
        self.logger = logging.getLogger(__name__)

    def score(
        self,
        stories: list[UserStory],
        options: QualityOptions | None = None,
    ) -> QualityResult:
        """
        Score story quality.

        Args:
            stories: List of user stories to score.
            options: Override scoring options.

        Returns:
            QualityResult with scores for each story.
        """
        from spectryn.adapters.llm import create_llm_manager

        opts = options or self.options
        result = QualityResult()

        if not stories:
            result.success = False
            result.error = "No stories provided for quality scoring"
            return result

        # Get LLM manager
        try:
            manager = create_llm_manager()
        except Exception as e:
            self.logger.warning(f"LLM not available, using fallback scoring: {e}")
            return self._build_result_from_fallback(stories, opts)

        if not manager.is_available():
            self.logger.warning("No LLM providers available, using fallback scoring")
            return self._build_result_from_fallback(stories, opts)

        # Build prompt
        prompt = build_quality_prompt(stories, opts)

        # Generate
        try:
            response = manager.prompt(
                user_message=prompt,
                system_prompt=QUALITY_SYSTEM_PROMPT,
            )

            result.raw_response = response.content
            result.tokens_used = response.total_tokens
            result.model_used = response.model
            result.provider_used = response.provider

        except Exception as e:
            self.logger.warning(f"LLM call failed, using fallback scoring: {e}")
            return self._build_result_from_fallback(stories, opts)

        # Parse response
        try:
            result.scores = parse_quality_response(response.content, stories, opts)

            if not result.scores:
                result.success = False
                result.error = "No scores could be parsed from the response"
                return self._build_result_from_fallback(stories, opts)

            self._update_result_stats(result, opts)

        except Exception as e:
            result.success = False
            result.error = f"Failed to parse quality response: {e}"
            return self._build_result_from_fallback(stories, opts)

        return result

    def _build_result_from_fallback(
        self,
        stories: list[UserStory],
        options: QualityOptions,
    ) -> QualityResult:
        """Build result from fallback scoring."""
        scores = _create_fallback_scores(stories, options)
        result = QualityResult(scores=scores)
        self._update_result_stats(result, options)
        return result

    def _update_result_stats(self, result: QualityResult, options: QualityOptions) -> None:
        """Update result statistics."""
        if not result.scores:
            return

        total = sum(s.overall_score for s in result.scores)
        result.average_score = total / len(result.scores)
        result.passing_count = sum(
            1 for s in result.scores if s.overall_score >= options.min_passing_score
        )
        result.failing_count = len(result.scores) - result.passing_count


def score_story_quality(
    stories: list[UserStory],
    project_context: str = "",
    tech_stack: str = "",
) -> QualityResult:
    """
    Convenience function to score story quality.

    Args:
        stories: List of user stories to score.
        project_context: Optional project context.
        tech_stack: Optional tech stack info.

    Returns:
        QualityResult with scores for each story.
    """
    options = QualityOptions(
        project_context=project_context,
        tech_stack=tech_stack,
    )

    scorer = AIQualityScorer(options)
    return scorer.score(stories, options)
