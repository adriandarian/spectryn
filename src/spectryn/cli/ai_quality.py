"""
AI Story Quality Scoring CLI - Command handler for rating story quality.

Uses LLM providers to analyze stories and score them based on
INVEST principles and other quality dimensions.
"""

import json
from pathlib import Path

from .exit_codes import ExitCode
from .output import Colors, Console, Symbols


def run_ai_quality(
    console: Console,
    markdown_path: str | None = None,
    story_ids: list[str] | None = None,
    min_score: int = 50,
    show_details: bool = True,
    project_context: str | None = None,
    tech_stack: str | None = None,
    output_format: str = "text",
) -> int:
    """
    Run the AI quality scoring command.

    Args:
        console: Console for output.
        markdown_path: Path to markdown file containing stories.
        story_ids: Optional list of specific story IDs to score.
        min_score: Minimum passing score threshold.
        show_details: Show detailed dimension scores.
        project_context: Optional project context.
        tech_stack: Optional tech stack info.
        output_format: Output format (text, json, yaml).

    Returns:
        Exit code.
    """
    from spectryn.adapters import MarkdownParser
    from spectryn.application.ai_quality import (
        AIQualityScorer,
        QualityOptions,
    )

    console.header(f"spectra Quality Scoring {Symbols.STAR}")

    # Validate input
    if not markdown_path:
        console.error("No markdown file specified. Use --input/-i or --markdown/-f")
        return ExitCode.CONFIG_ERROR

    if not Path(markdown_path).exists():
        console.error(f"File not found: {markdown_path}")
        return ExitCode.FILE_NOT_FOUND

    console.info(f"File: {markdown_path}")

    # Parse markdown to get stories
    console.section("Parsing Stories")
    try:
        parser = MarkdownParser()
        stories = parser.parse_stories(Path(markdown_path))
    except Exception as e:
        console.error(f"Failed to parse markdown: {e}")
        return ExitCode.ERROR

    if not stories:
        console.error("No stories found in the markdown file")
        return ExitCode.ERROR

    # Filter by story IDs if specified
    if story_ids:
        filtered = [s for s in stories if str(s.id) in story_ids]
        if not filtered:
            console.error(f"No stories found matching IDs: {', '.join(story_ids)}")
            console.info(f"Available IDs: {', '.join(str(s.id) for s in stories)}")
            return ExitCode.ERROR
        stories = filtered

    console.success(f"Found {len(stories)} stories to score")

    # Show configuration
    console.section("Configuration")
    console.detail(f"Minimum passing score: {min_score}")
    console.detail(f"Show details: {'yes' if show_details else 'no'}")

    # Create options
    options = QualityOptions(
        min_passing_score=min_score,
        project_context=project_context or "",
        tech_stack=tech_stack or "",
    )

    # Run scoring
    console.section("Scoring Story Quality")
    console.info("Calling LLM provider for quality analysis...")

    scorer = AIQualityScorer(options)
    result = scorer.score(stories, options)

    if not result.success:
        console.error(f"Scoring failed: {result.error}")
        return ExitCode.ERROR

    if not result.scores:
        console.warning("No quality scores returned")
        return ExitCode.SUCCESS

    # Show LLM info
    if result.provider_used:
        console.detail(f"Provider: {result.provider_used}")
        console.detail(f"Model: {result.model_used}")
        if result.tokens_used > 0:
            console.detail(f"Tokens used: {result.tokens_used}")

    # Output based on format
    if output_format == "json":
        output = _format_json(result)
        print(output)
    elif output_format == "yaml":
        output = _format_yaml(result)
        print(output)
    else:
        _format_text(result, console, show_details, min_score)

    # Return appropriate exit code
    if result.failing_count > 0:
        return ExitCode.VALIDATION_ERROR

    return ExitCode.SUCCESS


def _format_text(result, console: Console, show_details: bool, min_score: int) -> None:
    """Format quality results as human-readable text."""
    console.section("Quality Report")
    console.print()

    # Summary
    console.print(f"  Stories scored: {len(result.scores)}")
    console.print(f"  Average score: {_format_score(result.average_score)}")
    console.print(
        f"  {Colors.GREEN}Passing ({'>='}{min_score}): {result.passing_count}{Colors.RESET}"
    )
    if result.failing_count > 0:
        console.print(f"  {Colors.RED}Failing: {result.failing_count}{Colors.RESET}")
    console.print(f"  Pass rate: {result.pass_rate:.1f}%")
    console.print()

    # Per-story scores
    console.section("Story Scores")

    for score in sorted(result.scores, key=lambda s: s.overall_score, reverse=True):
        # Story header with score bar
        score_bar = _create_score_bar(score.overall_score)
        level_color = _get_level_color(score.overall_level.value)

        console.print(
            f"  {score_bar} {level_color}{score.overall_score:3d}{Colors.RESET} "
            f"{Colors.BOLD}{score.story_id}{Colors.RESET}: {score.story_title}"
        )
        console.print(f"     Level: {level_color}{score.overall_level.value}{Colors.RESET}")

        if show_details and score.dimension_scores:
            # INVEST scores
            invest_dims = [
                "independent",
                "negotiable",
                "valuable",
                "estimable",
                "small",
                "testable",
            ]
            invest_scores = [d for d in score.dimension_scores if d.dimension.value in invest_dims]
            if invest_scores:
                invest_strs = []
                for d in invest_scores:
                    color = _get_score_color(d.score)
                    initial = d.dimension.value[0].upper()
                    invest_strs.append(f"{color}{initial}:{d.score}{Colors.RESET}")
                console.print(f"     INVEST: {' '.join(invest_strs)}")

            # Other scores
            other_scores = [
                d for d in score.dimension_scores if d.dimension.value not in invest_dims
            ]
            if other_scores:
                other_strs = []
                for d in other_scores:
                    color = _get_score_color(d.score)
                    name = d.dimension.value[:4]
                    other_strs.append(f"{color}{name}:{d.score}{Colors.RESET}")
                console.print(f"     Other: {' '.join(other_strs)}")

        # Strengths
        if score.strengths:
            console.print(f"     {Colors.GREEN}Strengths:{Colors.RESET}")
            for strength in score.strengths[:2]:
                console.print(f"       + {strength}")

        # Weaknesses
        if score.weaknesses:
            console.print(f"     {Colors.RED}Weaknesses:{Colors.RESET}")
            for weakness in score.weaknesses[:2]:
                console.print(f"       - {weakness}")

        # Improvement suggestions
        if score.improvement_suggestions and score.overall_score < 70:
            console.print(f"     {Colors.YELLOW}Suggestions:{Colors.RESET}")
            for suggestion in score.improvement_suggestions[:2]:
                console.print(f"       → {suggestion}")

        console.print()

    # Worst performing stories
    if result.failing_count > 0:
        console.section("Stories Needing Improvement")
        failing = [s for s in result.scores if not s.is_passing]
        for score in sorted(failing, key=lambda s: s.overall_score)[:3]:
            console.print(
                f"  {Colors.RED}•{Colors.RESET} {score.story_id} ({score.overall_score}): "
                f"{score.story_title}"
            )
            if score.lowest_dimension:
                console.print(
                    f"    Lowest: {score.lowest_dimension.dimension.value} "
                    f"({score.lowest_dimension.score})"
                )
        console.print()

    # Next steps
    console.section("Next Steps")
    if result.failing_count > 0:
        console.item(f"Review and improve {result.failing_count} failing stories")
        console.item("Add missing acceptance criteria")
        console.item("Clarify vague descriptions")
    else:
        console.item("All stories pass quality threshold!")
        console.item("Consider raising the threshold for higher quality")


def _create_score_bar(score: int) -> str:
    """Create a visual score bar."""
    filled = score // 10
    empty = 10 - filled

    if score >= 70:
        color = Colors.GREEN
    elif score >= 50:
        color = Colors.YELLOW
    else:
        color = Colors.RED

    return f"{color}{'█' * filled}{Colors.DIM}{'░' * empty}{Colors.RESET}"


def _format_score(score: float) -> str:
    """Format score with color."""
    if score >= 70:
        return f"{Colors.GREEN}{score:.1f}{Colors.RESET}"
    if score >= 50:
        return f"{Colors.YELLOW}{score:.1f}{Colors.RESET}"
    return f"{Colors.RED}{score:.1f}{Colors.RESET}"


def _get_level_color(level: str) -> str:
    """Get color for quality level."""
    colors = {
        "excellent": Colors.GREEN,
        "good": Colors.GREEN,
        "fair": Colors.YELLOW,
        "poor": Colors.RED,
        "needs_work": Colors.RED,
    }
    return colors.get(level, Colors.RESET)


def _get_score_color(score: int) -> str:
    """Get color for numeric score."""
    if score >= 70:
        return Colors.GREEN
    if score >= 50:
        return Colors.YELLOW
    return Colors.RED


def _format_json(result) -> str:
    """Format quality results as JSON."""
    data = {
        "success": result.success,
        "average_score": result.average_score,
        "passing_count": result.passing_count,
        "failing_count": result.failing_count,
        "pass_rate": result.pass_rate,
        "provider": result.provider_used,
        "model": result.model_used,
        "scores": [
            {
                "story_id": s.story_id,
                "story_title": s.story_title,
                "overall_score": s.overall_score,
                "overall_level": s.overall_level.value,
                "invest_score": s.invest_score,
                "is_passing": s.is_passing,
                "dimension_scores": [
                    {
                        "dimension": d.dimension.value,
                        "score": d.score,
                        "feedback": d.feedback,
                        "suggestions": d.suggestions,
                    }
                    for d in s.dimension_scores
                ],
                "strengths": s.strengths,
                "weaknesses": s.weaknesses,
                "improvement_suggestions": s.improvement_suggestions,
            }
            for s in result.scores
        ],
    }
    return json.dumps(data, indent=2)


def _format_yaml(result) -> str:
    """Format quality results as YAML."""
    try:
        import yaml

        data = {
            "average_score": round(result.average_score, 1),
            "pass_rate": f"{result.pass_rate:.1f}%",
            "scores": [
                {
                    "story_id": s.story_id,
                    "score": s.overall_score,
                    "level": s.overall_level.value,
                    "passing": s.is_passing,
                    "suggestions": s.improvement_suggestions[:3]
                    if s.improvement_suggestions
                    else [],
                }
                for s in result.scores
            ],
        }
        return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    except ImportError:
        return _format_json(result)
