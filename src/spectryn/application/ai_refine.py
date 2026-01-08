"""
AI Story Refiner - Analyze stories for ambiguity or missing acceptance criteria.

Uses LLM providers to analyze user stories and identify:
- Ambiguous language and unclear requirements
- Missing or weak acceptance criteria
- Vague user descriptions (As a / I want / So that)
- Incomplete subtasks
- Inconsistent story points estimates
- Missing technical notes for complex stories
"""

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum

from spectryn.core.domain.entities import UserStory


logger = logging.getLogger(__name__)


class IssueSeverity(Enum):
    """Severity of a quality issue."""

    CRITICAL = "critical"  # Must fix before implementation
    WARNING = "warning"  # Should review and consider fixing
    SUGGESTION = "suggestion"  # Nice to have improvement


class IssueCategory(Enum):
    """Category of a quality issue."""

    AMBIGUITY = "ambiguity"  # Unclear or vague language
    ACCEPTANCE_CRITERIA = "acceptance_criteria"  # Missing or weak AC
    DESCRIPTION = "description"  # User story format issues
    TESTABILITY = "testability"  # Hard to verify/test
    SCOPE = "scope"  # Story too large or undefined scope
    ESTIMATION = "estimation"  # Story points don't match complexity
    TECHNICAL = "technical"  # Missing technical details
    DEPENDENCIES = "dependencies"  # Unclear dependencies


@dataclass
class QualityIssue:
    """A single quality issue found in a story."""

    severity: IssueSeverity
    category: IssueCategory
    message: str
    suggestion: str
    original_text: str = ""  # The problematic text
    suggested_text: str = ""  # Suggested replacement


@dataclass
class StoryAnalysis:
    """Analysis result for a single story."""

    story_id: str
    story_title: str
    issues: list[QualityIssue] = field(default_factory=list)
    quality_score: int = 100  # 0-100 quality score
    suggested_improvements: list[str] = field(default_factory=list)
    suggested_acceptance_criteria: list[str] = field(default_factory=list)
    estimated_effort_accuracy: str = ""  # "appropriate", "underestimated", "overestimated"

    @property
    def critical_count(self) -> int:
        """Count of critical issues."""
        return sum(1 for i in self.issues if i.severity == IssueSeverity.CRITICAL)

    @property
    def warning_count(self) -> int:
        """Count of warning issues."""
        return sum(1 for i in self.issues if i.severity == IssueSeverity.WARNING)

    @property
    def suggestion_count(self) -> int:
        """Count of suggestion issues."""
        return sum(1 for i in self.issues if i.severity == IssueSeverity.SUGGESTION)

    @property
    def is_ready(self) -> bool:
        """Whether the story is ready for implementation."""
        return self.critical_count == 0


@dataclass
class RefinementResult:
    """Result of AI story refinement analysis."""

    success: bool = True
    analyses: list[StoryAnalysis] = field(default_factory=list)
    overall_score: int = 100  # Average quality score
    raw_response: str = ""
    error: str | None = None
    tokens_used: int = 0
    model_used: str = ""
    provider_used: str = ""

    @property
    def stories_ready(self) -> int:
        """Count of stories ready for implementation."""
        return sum(1 for a in self.analyses if a.is_ready)

    @property
    def stories_need_work(self) -> int:
        """Count of stories needing refinement."""
        return sum(1 for a in self.analyses if not a.is_ready)


@dataclass
class RefinementOptions:
    """Options for story refinement analysis."""

    # What to check
    check_ambiguity: bool = True
    check_acceptance_criteria: bool = True
    check_testability: bool = True
    check_scope: bool = True
    check_estimation: bool = True

    # Generation options
    generate_missing_ac: bool = True
    generate_suggestions: bool = True
    max_suggestions_per_story: int = 5

    # Strictness
    min_acceptance_criteria: int = 2
    max_story_points: int = 13  # Stories above this should be split

    # Context
    project_context: str = ""
    tech_stack: str = ""


REFINER_SYSTEM_PROMPT = """You are an expert agile coach and requirements analyst.
Your task is to analyze user stories for quality issues and provide actionable improvement suggestions.

For each story, identify:
1. **Ambiguity**: Vague terms, unclear scope, multiple interpretations
2. **Acceptance Criteria**: Missing, incomplete, or untestable criteria
3. **Description Quality**: User story format issues (As a/I want/So that)
4. **Testability**: Hard to verify or measure success
5. **Scope Issues**: Story too large, mixing features, unclear boundaries
6. **Estimation Accuracy**: Story points vs complexity mismatch

Guidelines:
- Be specific about what's wrong and how to fix it
- Provide concrete replacement text where possible
- Suggest specific acceptance criteria if missing
- Flag stories that should be split
- Consider both functional and non-functional requirements

Always respond with valid JSON."""


def build_refinement_prompt(
    stories: list[UserStory],
    options: RefinementOptions,
) -> str:
    """Build the prompt for story refinement analysis."""
    context_parts = []
    if options.project_context:
        context_parts.append(f"Project Context: {options.project_context}")
    if options.tech_stack:
        context_parts.append(f"Tech Stack: {options.tech_stack}")

    context_section = (
        "\n".join(context_parts) if context_parts else "No additional context provided."
    )

    # Format stories for analysis
    stories_text = []
    for story in stories:
        story_text = f"""
### Story: {story.id} - {story.title}
**Story Points**: {story.story_points}
**Priority**: {story.priority.display_name}
**Status**: {story.status.display_name}

**Description**:
{_format_description(story)}

**Acceptance Criteria**:
{_format_acceptance_criteria(story)}

**Subtasks**:
{_format_subtasks(story)}
"""
        stories_text.append(story_text.strip())

    checks = []
    if options.check_ambiguity:
        checks.append("- Check for ambiguous language and unclear requirements")
    if options.check_acceptance_criteria:
        checks.append(
            f"- Verify acceptance criteria (minimum {options.min_acceptance_criteria} required)"
        )
    if options.check_testability:
        checks.append("- Assess testability of each story")
    if options.check_scope:
        checks.append(f"- Flag stories over {options.max_story_points} points for splitting")
    if options.check_estimation:
        checks.append("- Evaluate if story points match the apparent complexity")

    checks_section = "\n".join(checks) if checks else "- Perform general quality analysis"

    return f"""Analyze the following user stories for quality issues.

## Context
{context_section}

## Checks to Perform
{checks_section}

## Stories to Analyze
{chr(10).join(stories_text)}

## Output Format
Respond with a JSON object containing analysis for each story:

```json
{{
  "analyses": [
    {{
      "story_id": "US-001",
      "quality_score": 75,
      "issues": [
        {{
          "severity": "critical",
          "category": "acceptance_criteria",
          "message": "Story has no acceptance criteria",
          "suggestion": "Add specific, testable acceptance criteria",
          "original_text": "",
          "suggested_text": ""
        }},
        {{
          "severity": "warning",
          "category": "ambiguity",
          "message": "Term 'quickly' is ambiguous",
          "suggestion": "Define specific performance requirement",
          "original_text": "load quickly",
          "suggested_text": "load within 2 seconds"
        }}
      ],
      "suggested_acceptance_criteria": [
        "User can complete action within 3 clicks",
        "Error messages display within 500ms"
      ],
      "estimated_effort_accuracy": "appropriate",
      "suggested_improvements": [
        "Add edge case handling for empty states",
        "Consider accessibility requirements"
      ]
    }}
  ]
}}
```

Severity levels:
- "critical": Must fix before implementation
- "warning": Should review and consider fixing
- "suggestion": Nice to have improvement

Categories:
- "ambiguity": Unclear language
- "acceptance_criteria": AC issues
- "description": User story format
- "testability": Hard to test
- "scope": Story too large
- "estimation": Points mismatch
- "technical": Missing technical details
- "dependencies": Unclear dependencies

Analyze the stories now:"""


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


def parse_refinement_response(
    response: str,
    stories: list[UserStory],
) -> list[StoryAnalysis]:
    """Parse LLM response into StoryAnalysis objects."""
    analyses: list[StoryAnalysis] = []

    # Try to extract JSON from the response
    json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", response)
    if json_match:
        json_str = json_match.group(1)
    else:
        # Try to find raw JSON
        json_match = re.search(r"\{[\s\S]*\"analyses\"[\s\S]*\}", response)
        if json_match:
            json_str = json_match.group(0)
        else:
            logger.warning("Could not find JSON in response")
            return _create_fallback_analyses(stories)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON: {e}")
        return _create_fallback_analyses(stories)

    raw_analyses = data.get("analyses", [])

    # Create a mapping from story ID to story
    story_map = {str(s.id): s for s in stories}

    for raw in raw_analyses:
        story_id = raw.get("story_id", "")
        story = story_map.get(story_id)
        title = story.title if story else raw.get("story_title", "Unknown")

        issues = []
        for raw_issue in raw.get("issues", []):
            try:
                severity = IssueSeverity(raw_issue.get("severity", "suggestion"))
                category = IssueCategory(raw_issue.get("category", "ambiguity"))
                issues.append(
                    QualityIssue(
                        severity=severity,
                        category=category,
                        message=raw_issue.get("message", ""),
                        suggestion=raw_issue.get("suggestion", ""),
                        original_text=raw_issue.get("original_text", ""),
                        suggested_text=raw_issue.get("suggested_text", ""),
                    )
                )
            except (ValueError, KeyError) as e:
                logger.warning(f"Failed to parse issue: {e}")
                continue

        analysis = StoryAnalysis(
            story_id=story_id,
            story_title=title,
            issues=issues,
            quality_score=raw.get("quality_score", 100),
            suggested_acceptance_criteria=raw.get("suggested_acceptance_criteria", []),
            estimated_effort_accuracy=raw.get("estimated_effort_accuracy", ""),
            suggested_improvements=raw.get("suggested_improvements", []),
        )
        analyses.append(analysis)

    return analyses


def _create_fallback_analyses(stories: list[UserStory]) -> list[StoryAnalysis]:
    """Create basic analyses when LLM parsing fails."""
    analyses = []
    for story in stories:
        issues = []

        # Basic checks without LLM
        if not story.description:
            issues.append(
                QualityIssue(
                    severity=IssueSeverity.CRITICAL,
                    category=IssueCategory.DESCRIPTION,
                    message="Story has no description",
                    suggestion="Add user story format: As a X, I want Y, So that Z",
                )
            )

        if not story.acceptance_criteria or len(story.acceptance_criteria) == 0:
            issues.append(
                QualityIssue(
                    severity=IssueSeverity.CRITICAL,
                    category=IssueCategory.ACCEPTANCE_CRITERIA,
                    message="Story has no acceptance criteria",
                    suggestion="Add specific, testable acceptance criteria",
                )
            )

        if story.story_points > 13:
            issues.append(
                QualityIssue(
                    severity=IssueSeverity.WARNING,
                    category=IssueCategory.SCOPE,
                    message=f"Story has {story.story_points} points, consider splitting",
                    suggestion="Break down into smaller stories (max 13 points)",
                )
            )

        score = 100 - (len(issues) * 20)
        analyses.append(
            StoryAnalysis(
                story_id=str(story.id),
                story_title=story.title,
                issues=issues,
                quality_score=max(0, score),
            )
        )

    return analyses


class AIStoryRefiner:
    """
    Analyzes user stories for quality issues using LLM.

    Identifies ambiguity, missing acceptance criteria, and other
    issues that should be addressed before implementation.
    """

    def __init__(
        self,
        options: RefinementOptions | None = None,
    ):
        """
        Initialize the story refiner.

        Args:
            options: Refinement options. Uses defaults if not provided.
        """
        self.options = options or RefinementOptions()
        self.logger = logging.getLogger(__name__)

    def refine(
        self,
        stories: list[UserStory],
        options: RefinementOptions | None = None,
    ) -> RefinementResult:
        """
        Analyze stories for quality issues.

        Args:
            stories: List of user stories to analyze.
            options: Override refinement options.

        Returns:
            RefinementResult with analysis for each story.
        """
        from spectryn.adapters.llm import create_llm_manager

        opts = options or self.options
        result = RefinementResult()

        if not stories:
            result.success = False
            result.error = "No stories provided for analysis"
            return result

        # Get LLM manager
        try:
            manager = create_llm_manager()
        except Exception as e:
            # Fallback to basic analysis without LLM
            self.logger.warning(f"LLM not available, using basic analysis: {e}")
            result.analyses = _create_fallback_analyses(stories)
            result.overall_score = (
                sum(a.quality_score for a in result.analyses) // len(result.analyses)
                if result.analyses
                else 0
            )
            return result

        if not manager.is_available():
            # Fallback to basic analysis
            self.logger.warning("No LLM providers available, using basic analysis")
            result.analyses = _create_fallback_analyses(stories)
            result.overall_score = (
                sum(a.quality_score for a in result.analyses) // len(result.analyses)
                if result.analyses
                else 0
            )
            return result

        # Build prompt
        prompt = build_refinement_prompt(stories, opts)

        # Generate
        try:
            response = manager.prompt(
                user_message=prompt,
                system_prompt=REFINER_SYSTEM_PROMPT,
            )

            result.raw_response = response.content
            result.tokens_used = response.total_tokens
            result.model_used = response.model
            result.provider_used = response.provider

        except Exception as e:
            # Fallback to basic analysis
            self.logger.warning(f"LLM call failed, using basic analysis: {e}")
            result.analyses = _create_fallback_analyses(stories)
            result.overall_score = (
                sum(a.quality_score for a in result.analyses) // len(result.analyses)
                if result.analyses
                else 0
            )
            return result

        # Parse response
        try:
            result.analyses = parse_refinement_response(response.content, stories)

            # Calculate overall score
            if result.analyses:
                result.overall_score = sum(a.quality_score for a in result.analyses) // len(
                    result.analyses
                )
            else:
                result.success = False
                result.error = "No analyses could be parsed from the response"

        except Exception as e:
            result.success = False
            result.error = f"Failed to parse refinement response: {e}"
            # Still provide fallback analyses
            result.analyses = _create_fallback_analyses(stories)

        return result

    def refine_from_markdown(
        self,
        markdown_path: str,
        options: RefinementOptions | None = None,
    ) -> RefinementResult:
        """
        Analyze stories from a markdown file.

        Args:
            markdown_path: Path to markdown file containing stories.
            options: Override refinement options.

        Returns:
            RefinementResult with analysis for each story.
        """
        from pathlib import Path

        from spectryn.adapters import MarkdownParser

        result = RefinementResult()

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

        return self.refine(epic.stories, options)


def refine_stories(
    stories: list[UserStory],
    project_context: str = "",
    tech_stack: str = "",
    check_ambiguity: bool = True,
    check_acceptance_criteria: bool = True,
) -> RefinementResult:
    """
    Convenience function to analyze stories for quality issues.

    Args:
        stories: List of user stories to analyze.
        project_context: Optional project context.
        tech_stack: Optional tech stack info.
        check_ambiguity: Check for ambiguous language.
        check_acceptance_criteria: Check for missing/weak AC.

    Returns:
        RefinementResult with analysis for each story.
    """
    options = RefinementOptions(
        project_context=project_context,
        tech_stack=tech_stack,
        check_ambiguity=check_ambiguity,
        check_acceptance_criteria=check_acceptance_criteria,
    )

    refiner = AIStoryRefiner(options)
    return refiner.refine(stories, options)
