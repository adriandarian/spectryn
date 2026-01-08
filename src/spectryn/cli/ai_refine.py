"""
AI Story Refiner CLI - Command handler for analyzing stories for quality issues.

Uses LLM providers to identify ambiguity, missing acceptance criteria,
and other issues that should be addressed before implementation.
"""

import json
from pathlib import Path

from .exit_codes import ExitCode
from .output import Colors, Console, Symbols


def run_ai_refine(
    console: Console,
    markdown_path: str | None = None,
    story_ids: list[str] | None = None,
    check_ambiguity: bool = True,
    check_acceptance_criteria: bool = True,
    check_testability: bool = True,
    check_scope: bool = True,
    check_estimation: bool = True,
    generate_ac: bool = True,
    min_ac: int = 2,
    max_story_points: int = 13,
    project_context: str | None = None,
    tech_stack: str | None = None,
    output_format: str = "text",
    show_suggestions: bool = True,
) -> int:
    """
    Run the AI story refinement command.

    Args:
        console: Console for output.
        markdown_path: Path to markdown file containing stories.
        story_ids: Optional list of specific story IDs to analyze.
        check_ambiguity: Check for ambiguous language.
        check_acceptance_criteria: Check for missing/weak AC.
        check_testability: Check for testability issues.
        check_scope: Check for scope issues.
        check_estimation: Check estimation accuracy.
        generate_ac: Generate suggested acceptance criteria.
        min_ac: Minimum acceptance criteria required.
        max_story_points: Maximum story points before splitting.
        project_context: Optional project context.
        tech_stack: Optional tech stack info.
        output_format: Output format (text, json, yaml).
        show_suggestions: Show improvement suggestions.

    Returns:
        Exit code.
    """
    from spectryn.adapters import MarkdownParser
    from spectryn.application.ai_refine import (
        AIStoryRefiner,
        RefinementOptions,
    )

    console.header(f"spectra AI Story Refiner {Symbols.MAGNIFYING_GLASS}")

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

    console.success(f"Found {len(stories)} stories to analyze")

    # Show configuration
    console.section("Configuration")
    checks = []
    if check_ambiguity:
        checks.append("ambiguity")
    if check_acceptance_criteria:
        checks.append("acceptance criteria")
    if check_testability:
        checks.append("testability")
    if check_scope:
        checks.append("scope")
    if check_estimation:
        checks.append("estimation")

    console.detail(f"Checks: {', '.join(checks)}")
    console.detail(f"Min acceptance criteria: {min_ac}")
    console.detail(f"Max story points: {max_story_points}")
    if project_context:
        console.detail(f"Project context: {project_context[:50]}...")

    # Create options
    options = RefinementOptions(
        check_ambiguity=check_ambiguity,
        check_acceptance_criteria=check_acceptance_criteria,
        check_testability=check_testability,
        check_scope=check_scope,
        check_estimation=check_estimation,
        generate_missing_ac=generate_ac,
        generate_suggestions=show_suggestions,
        min_acceptance_criteria=min_ac,
        max_story_points=max_story_points,
        project_context=project_context or "",
        tech_stack=tech_stack or "",
    )

    # Run analysis
    console.section("Analyzing Stories")
    console.info("Calling LLM provider for quality analysis...")

    refiner = AIStoryRefiner(options)
    result = refiner.refine(stories, options)

    if not result.success:
        console.error(f"Analysis failed: {result.error}")
        return ExitCode.ERROR

    if not result.analyses:
        console.warning("No analysis results returned")
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
        _format_text(result, console, show_suggestions)

    # Return code based on critical issues
    if result.stories_need_work > 0:
        return ExitCode.VALIDATION_ERROR  # Indicates issues found
    return ExitCode.SUCCESS


def _format_text(result, console: Console, show_suggestions: bool) -> None:
    """Format analysis results as human-readable text."""
    from spectryn.application.ai_refine import IssueSeverity

    console.section("Analysis Results")
    console.print()

    # Overall summary
    if result.overall_score >= 80:
        score_color = Colors.GREEN
        score_emoji = Symbols.CHECK
    elif result.overall_score >= 60:
        score_color = Colors.YELLOW
        score_emoji = Symbols.WARN
    else:
        score_color = Colors.RED
        score_emoji = Symbols.CROSS

    console.print(
        f"  {score_emoji} Overall Quality Score: {score_color}{result.overall_score}/100{Colors.RESET}"
    )
    console.print(f"  {Symbols.CHECK} Stories ready: {result.stories_ready}")
    console.print(f"  {Symbols.WARN} Stories need work: {result.stories_need_work}")
    console.print()

    # Per-story analysis
    for analysis in result.analyses:
        # Story header with score
        if analysis.quality_score >= 80:
            score_indicator = f"{Colors.GREEN}●{Colors.RESET}"
        elif analysis.quality_score >= 60:
            score_indicator = f"{Colors.YELLOW}●{Colors.RESET}"
        else:
            score_indicator = f"{Colors.RED}●{Colors.RESET}"

        console.print(
            f"  {score_indicator} {Colors.BOLD}{analysis.story_id}{Colors.RESET}: "
            f"{analysis.story_title}"
        )
        console.print(f"     Score: {analysis.quality_score}/100")

        if analysis.estimated_effort_accuracy:
            console.print(f"     Estimation: {analysis.estimated_effort_accuracy}")

        # Issues
        if analysis.issues:
            console.print()
            for issue in analysis.issues:
                if issue.severity == IssueSeverity.CRITICAL:
                    icon = f"{Colors.RED}{Symbols.CROSS}{Colors.RESET}"
                    severity_text = f"{Colors.RED}CRITICAL{Colors.RESET}"
                elif issue.severity == IssueSeverity.WARNING:
                    icon = f"{Colors.YELLOW}{Symbols.WARN}{Colors.RESET}"
                    severity_text = f"{Colors.YELLOW}WARNING{Colors.RESET}"
                else:
                    icon = f"{Colors.CYAN}{Symbols.INFO}{Colors.RESET}"
                    severity_text = f"{Colors.CYAN}SUGGESTION{Colors.RESET}"

                console.print(f"     {icon} [{severity_text}] {issue.message}")

                if issue.suggestion:
                    console.print(f"        {Colors.DIM}→ {issue.suggestion}{Colors.RESET}")

                if issue.original_text and issue.suggested_text:
                    console.print(
                        f'        {Colors.DIM}Change: "{issue.original_text}" → '
                        f'"{issue.suggested_text}"{Colors.RESET}'
                    )

        # Suggested acceptance criteria
        if show_suggestions and analysis.suggested_acceptance_criteria:
            console.print()
            console.print(f"     {Colors.CYAN}Suggested Acceptance Criteria:{Colors.RESET}")
            for ac in analysis.suggested_acceptance_criteria[:5]:
                console.print(f"       • {ac}")

        # Suggested improvements
        if show_suggestions and analysis.suggested_improvements:
            console.print()
            console.print(f"     {Colors.CYAN}Suggested Improvements:{Colors.RESET}")
            for imp in analysis.suggested_improvements[:3]:
                console.print(f"       • {imp}")

        console.print()
        console.print("  " + "-" * 60)
        console.print()

    # Summary
    total_critical = sum(a.critical_count for a in result.analyses)
    total_warnings = sum(a.warning_count for a in result.analyses)
    total_suggestions = sum(a.suggestion_count for a in result.analyses)

    console.section("Summary")
    if total_critical > 0:
        console.print(
            f"  {Colors.RED}{Symbols.CROSS} Critical issues: {total_critical}{Colors.RESET}"
        )
    if total_warnings > 0:
        console.print(f"  {Colors.YELLOW}{Symbols.WARN} Warnings: {total_warnings}{Colors.RESET}")
    if total_suggestions > 0:
        console.print(
            f"  {Colors.CYAN}{Symbols.INFO} Suggestions: {total_suggestions}{Colors.RESET}"
        )

    if total_critical == 0 and total_warnings == 0:
        console.print(f"  {Colors.GREEN}{Symbols.CHECK} All stories look good!{Colors.RESET}")

    console.print()

    # Next steps
    if total_critical > 0 or total_warnings > 0:
        console.section("Next Steps")
        console.item("Review and address critical issues before implementation")
        console.item("Consider suggested acceptance criteria for incomplete stories")
        console.item("Re-run analysis after making changes: spectra --refine -f FILE")


def _format_json(result) -> str:
    """Format analysis results as JSON."""
    data = {
        "success": result.success,
        "overall_score": result.overall_score,
        "stories_ready": result.stories_ready,
        "stories_need_work": result.stories_need_work,
        "provider": result.provider_used,
        "model": result.model_used,
        "tokens_used": result.tokens_used,
        "analyses": [
            {
                "story_id": a.story_id,
                "story_title": a.story_title,
                "quality_score": a.quality_score,
                "is_ready": a.is_ready,
                "critical_count": a.critical_count,
                "warning_count": a.warning_count,
                "suggestion_count": a.suggestion_count,
                "estimated_effort_accuracy": a.estimated_effort_accuracy,
                "issues": [
                    {
                        "severity": i.severity.value,
                        "category": i.category.value,
                        "message": i.message,
                        "suggestion": i.suggestion,
                        "original_text": i.original_text,
                        "suggested_text": i.suggested_text,
                    }
                    for i in a.issues
                ],
                "suggested_acceptance_criteria": a.suggested_acceptance_criteria,
                "suggested_improvements": a.suggested_improvements,
            }
            for a in result.analyses
        ],
    }
    return json.dumps(data, indent=2)


def _format_yaml(result) -> str:
    """Format analysis results as YAML."""
    try:
        import yaml

        data = {
            "success": result.success,
            "overall_score": result.overall_score,
            "stories_ready": result.stories_ready,
            "stories_need_work": result.stories_need_work,
            "analyses": [
                {
                    "story_id": a.story_id,
                    "quality_score": a.quality_score,
                    "is_ready": a.is_ready,
                    "issues": [
                        {
                            "severity": i.severity.value,
                            "category": i.category.value,
                            "message": i.message,
                            "suggestion": i.suggestion,
                        }
                        for i in a.issues
                    ],
                }
                for a in result.analyses
            ],
        }
        return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    except ImportError:
        # Fallback to JSON-like format
        return _format_json(result)
