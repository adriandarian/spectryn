"""
AI Estimation CLI - Command handler for suggesting story point estimates.

Uses LLM providers to analyze story complexity and suggest appropriate
story point estimates.
"""

import json
from pathlib import Path

from .exit_codes import ExitCode
from .output import Colors, Console, Symbols


def run_ai_estimate(
    console: Console,
    markdown_path: str | None = None,
    story_ids: list[str] | None = None,
    scale: str = "fibonacci",
    project_context: str | None = None,
    tech_stack: str | None = None,
    team_velocity: int = 0,
    show_complexity: bool = True,
    show_reasoning: bool = True,
    output_format: str = "text",
    apply_changes: bool = False,
) -> int:
    """
    Run the AI estimation command.

    Args:
        console: Console for output.
        markdown_path: Path to markdown file containing stories.
        story_ids: Optional list of specific story IDs to estimate.
        scale: Estimation scale (fibonacci, linear, tshirt).
        project_context: Optional project context.
        tech_stack: Optional tech stack info.
        team_velocity: Team velocity (points/sprint).
        show_complexity: Show complexity breakdown.
        show_reasoning: Show estimation reasoning.
        output_format: Output format (text, json, yaml).
        apply_changes: Apply suggested estimates to the file.

    Returns:
        Exit code.
    """
    from spectryn.adapters import MarkdownParser
    from spectryn.application.ai_estimate import (
        AIEstimator,
        EstimationOptions,
        EstimationScale,
    )

    console.header(f"spectra AI Estimation {Symbols.CHART}")

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
        epic = parser.parse(Path(markdown_path))
    except Exception as e:
        console.error(f"Failed to parse markdown: {e}")
        return ExitCode.ERROR

    if not epic or not epic.stories:
        console.error("No stories found in the markdown file")
        return ExitCode.ERROR

    stories = epic.stories

    # Filter by story IDs if specified
    if story_ids:
        filtered = [s for s in stories if str(s.id) in story_ids]
        if not filtered:
            console.error(f"No stories found matching IDs: {', '.join(story_ids)}")
            console.info(f"Available IDs: {', '.join(str(s.id) for s in stories)}")
            return ExitCode.ERROR
        stories = filtered

    console.success(f"Found {len(stories)} stories to estimate")

    # Parse scale
    try:
        estimation_scale = EstimationScale(scale)
    except ValueError:
        console.warning(f"Unknown scale '{scale}', using fibonacci")
        estimation_scale = EstimationScale.FIBONACCI

    # Set valid points based on scale
    if estimation_scale == EstimationScale.FIBONACCI:
        valid_points = [1, 2, 3, 5, 8, 13, 21]
    elif estimation_scale == EstimationScale.LINEAR:
        valid_points = [1, 2, 3, 4, 5, 6, 7, 8]
    else:  # T-shirt
        valid_points = [1, 2, 3, 5, 8, 13]

    # Show configuration
    console.section("Configuration")
    console.detail(f"Scale: {estimation_scale.value} ({valid_points})")
    if team_velocity > 0:
        console.detail(f"Team velocity: {team_velocity} points/sprint")
    if project_context:
        console.detail(f"Project context: {project_context[:50]}...")

    # Create options
    options = EstimationOptions(
        scale=estimation_scale,
        valid_points=valid_points,
        project_context=project_context or "",
        tech_stack=tech_stack or "",
        team_velocity=team_velocity,
    )

    # Run estimation
    console.section("Analyzing Stories")
    console.info("Calling LLM provider for estimation analysis...")

    estimator = AIEstimator(options)
    result = estimator.estimate(stories, options)

    if not result.success:
        console.error(f"Estimation failed: {result.error}")
        return ExitCode.ERROR

    if not result.suggestions:
        console.warning("No estimation suggestions returned")
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
        _format_text(result, console, show_complexity, show_reasoning)

    # Apply changes if requested
    if apply_changes and result.stories_changed > 0:
        console.section("Applying Changes")
        applied = _apply_estimates(markdown_path, result, console)
        if applied:
            console.success(f"Updated {result.stories_changed} story estimates in {markdown_path}")
        else:
            console.error("Failed to apply changes")
            return ExitCode.ERROR

    return ExitCode.SUCCESS


def _format_text(
    result,
    console: Console,
    show_complexity: bool,
    show_reasoning: bool,
) -> None:
    """Format estimation results as human-readable text."""
    console.section("Estimation Results")
    console.print()

    # Summary
    current = result.total_current_points
    suggested = result.total_suggested_points
    diff = result.points_difference

    if diff > 0:
        diff_text = f"{Colors.YELLOW}+{diff}{Colors.RESET}"
        summary_icon = Symbols.WARN
    elif diff < 0:
        diff_text = f"{Colors.GREEN}{diff}{Colors.RESET}"
        summary_icon = Symbols.CHECK
    else:
        diff_text = "0"
        summary_icon = Symbols.CHECK

    console.print(f"  {summary_icon} Total Points: {current} → {suggested} ({diff_text})")
    console.print(f"  Stories with changes: {result.stories_changed}/{len(result.suggestions)}")
    console.print()

    # Per-story suggestions
    for suggestion in result.suggestions:
        # Story header
        if suggestion.points_changed:
            if suggestion.change_direction == "increase":
                change_icon = f"{Colors.YELLOW}↑{Colors.RESET}"
                change_text = f"+{suggestion.points_difference}"
            else:
                change_icon = f"{Colors.GREEN}↓{Colors.RESET}"
                change_text = str(suggestion.points_difference)

            points_display = (
                f"{suggestion.current_points} → "
                f"{Colors.BOLD}{suggestion.suggested_points}{Colors.RESET} "
                f"({change_icon} {change_text})"
            )
        else:
            change_icon = f"{Colors.GREEN}✓{Colors.RESET}"
            points_display = f"{suggestion.current_points} {change_icon}"

        console.print(
            f"  {Colors.BOLD}{suggestion.story_id}{Colors.RESET}: {suggestion.story_title}"
        )
        console.print(f"     Points: {points_display}")
        console.print(f"     Confidence: {_format_confidence(suggestion.confidence)}")

        # Reasoning
        if show_reasoning and suggestion.reasoning:
            console.print(f"     {Colors.DIM}Reasoning: {suggestion.reasoning}{Colors.RESET}")

        # Complexity breakdown
        if show_complexity:
            c = suggestion.complexity
            console.print(
                f"     Complexity: T:{c.technical} S:{c.scope} U:{c.uncertainty} "
                f"D:{c.dependencies} Te:{c.testing} I:{c.integration} "
                f"(avg: {c.average:.1f})"
            )

        # Risk factors
        if suggestion.risk_factors:
            console.print(f"     {Colors.YELLOW}Risks:{Colors.RESET}")
            for risk in suggestion.risk_factors[:3]:
                console.print(f"       • {risk}")

        console.print()

    # Sprint impact
    if result.points_difference != 0:
        console.section("Impact Analysis")
        if result.points_difference > 0:
            console.print(
                f"  {Colors.YELLOW}{Symbols.WARN} Suggested estimates add "
                f"{result.points_difference} more points{Colors.RESET}"
            )
        else:
            console.print(
                f"  {Colors.GREEN}{Symbols.CHECK} Suggested estimates reduce "
                f"by {abs(result.points_difference)} points{Colors.RESET}"
            )
        console.print()

    # Next steps
    if result.stories_changed > 0:
        console.section("Next Steps")
        console.item("Review the suggested estimates with your team")
        console.item("Apply changes: spectra --estimate -f FILE --apply")
        console.item("Or manually update the story points in your markdown file")


def _format_confidence(confidence: str) -> str:
    """Format confidence level with color."""
    if confidence == "high":
        return f"{Colors.GREEN}high{Colors.RESET}"
    if confidence == "medium":
        return f"{Colors.YELLOW}medium{Colors.RESET}"
    return f"{Colors.RED}low{Colors.RESET}"


def _format_json(result) -> str:
    """Format estimation results as JSON."""
    data = {
        "success": result.success,
        "total_current_points": result.total_current_points,
        "total_suggested_points": result.total_suggested_points,
        "points_difference": result.points_difference,
        "stories_changed": result.stories_changed,
        "provider": result.provider_used,
        "model": result.model_used,
        "tokens_used": result.tokens_used,
        "suggestions": [
            {
                "story_id": s.story_id,
                "story_title": s.story_title,
                "current_points": s.current_points,
                "suggested_points": s.suggested_points,
                "points_changed": s.points_changed,
                "change_direction": s.change_direction,
                "confidence": s.confidence,
                "reasoning": s.reasoning,
                "complexity": s.complexity.to_dict(),
                "risk_factors": s.risk_factors,
                "comparison_notes": s.comparison_notes,
            }
            for s in result.suggestions
        ],
    }
    return json.dumps(data, indent=2)


def _format_yaml(result) -> str:
    """Format estimation results as YAML."""
    try:
        import yaml

        data = {
            "total_current_points": result.total_current_points,
            "total_suggested_points": result.total_suggested_points,
            "points_difference": result.points_difference,
            "suggestions": [
                {
                    "story_id": s.story_id,
                    "current_points": s.current_points,
                    "suggested_points": s.suggested_points,
                    "confidence": s.confidence,
                    "reasoning": s.reasoning,
                }
                for s in result.suggestions
            ],
        }
        return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    except ImportError:
        return _format_json(result)


def _apply_estimates(
    markdown_path: str,
    result,
    console: Console,
) -> bool:
    """Apply suggested estimates to the markdown file."""
    import re

    try:
        content = Path(markdown_path).read_text(encoding="utf-8")
        updated_content = content

        for suggestion in result.suggestions:
            if not suggestion.points_changed:
                continue

            # Update story points in metadata table
            # Pattern: | **Story Points** | N |
            pattern = rf"(\|\s*\*\*Story Points\*\*\s*\|\s*){suggestion.current_points}(\s*\|)"
            replacement = rf"\g<1>{suggestion.suggested_points}\g<2>"

            # Find the story section first to avoid updating wrong story
            story_pattern = (
                rf"(###[^\n]*{re.escape(suggestion.story_id)}[^\n]*\n[\s\S]*?)(?=###|\Z)"
            )
            story_match = re.search(story_pattern, updated_content)

            if story_match:
                story_section = story_match.group(0)
                updated_section = re.sub(pattern, replacement, story_section, count=1)
                updated_content = updated_content.replace(story_section, updated_section)

        Path(markdown_path).write_text(updated_content, encoding="utf-8")
        return True

    except Exception as e:
        console.error(f"Failed to update file: {e}")
        return False
