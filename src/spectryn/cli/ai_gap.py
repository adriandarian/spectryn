"""
AI Gap Analysis CLI - Command handler for identifying missing requirements.

Uses LLM providers to analyze user stories and identify gaps in coverage.
"""

import json
from pathlib import Path

from .exit_codes import ExitCode
from .output import Colors, Console, Symbols


def run_ai_gap(
    console: Console,
    markdown_path: str | None = None,
    project_context: str | None = None,
    industry: str | None = None,
    expected_personas: list[str] | None = None,
    expected_integrations: list[str] | None = None,
    compliance: list[str] | None = None,
    no_suggestions: bool = False,
    output_format: str = "text",
) -> int:
    """
    Run the AI gap analysis command.

    Args:
        console: Console for output.
        markdown_path: Path to markdown file to analyze.
        project_context: Optional project context.
        industry: Optional industry context.
        expected_personas: List of expected user personas.
        expected_integrations: List of expected integrations.
        compliance: List of compliance requirements.
        no_suggestions: Skip generating story suggestions.
        output_format: Output format (text, json, yaml).

    Returns:
        Exit code.
    """
    from spectryn.adapters import MarkdownParser
    from spectryn.application.ai_gap import AIGapAnalyzer, GapOptions

    console.header(f"spectra Gap Analysis {Symbols.SEARCH}")

    # Validate input
    if not markdown_path:
        console.error("No markdown file specified. Use --input/-i or --markdown/-f")
        return ExitCode.CONFIG_ERROR

    if not Path(markdown_path).exists():
        console.error(f"File not found: {markdown_path}")
        return ExitCode.ERROR

    # Parse stories
    console.section("Parsing Stories")
    parser = MarkdownParser()

    try:
        stories = parser.parse_stories(Path(markdown_path))
        console.success(f"Parsed {len(stories)} stories from {Path(markdown_path).name}")
    except Exception as e:
        console.error(f"Failed to parse file: {e}")
        return ExitCode.ERROR

    if not stories:
        console.error("No stories found in the provided file")
        return ExitCode.ERROR

    # Show configuration
    console.section("Configuration")
    console.detail(f"Stories: {len(stories)}")
    if project_context:
        console.detail(f"Project: {project_context}")
    if industry:
        console.detail(f"Industry: {industry}")
    if expected_personas:
        console.detail(f"Expected personas: {', '.join(expected_personas)}")
    if expected_integrations:
        console.detail(f"Expected integrations: {', '.join(expected_integrations)}")
    if compliance:
        console.detail(f"Compliance: {', '.join(compliance)}")

    # Create options
    options = GapOptions(
        project_context=project_context or "",
        industry=industry or "",
        expected_personas=expected_personas or [],
        expected_integrations=expected_integrations or [],
        compliance_requirements=compliance or [],
        include_suggestions=not no_suggestions,
    )

    # Run analysis
    console.section("Analyzing Requirements")
    console.info("Calling LLM provider for gap analysis...")

    analyzer = AIGapAnalyzer(options)
    result = analyzer.analyze(stories, options)

    if not result.success:
        console.error(f"Analysis failed: {result.error}")
        return ExitCode.ERROR

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
        _format_text(result, console)

    # Return warning if critical/high gaps found
    if result.critical_gap_count > 0:
        return ExitCode.VALIDATION_ERROR
    if result.high_gap_count > 0:
        return ExitCode.VALIDATION_ERROR

    return ExitCode.SUCCESS


def _format_text(result, console: Console) -> None:
    """Format gap results as human-readable text."""

    console.section("Gap Analysis Results")
    console.print()

    # Coverage summary
    coverage_color = (
        Colors.GREEN
        if result.overall_coverage >= 80
        else (Colors.YELLOW if result.overall_coverage >= 60 else Colors.RED)
    )
    console.print(
        f"  Overall Coverage: {coverage_color}{result.overall_coverage:.0f}%{Colors.RESET}"
    )
    console.print()

    # Gap counts by priority
    console.print(f"  {Colors.RED}Critical gaps:{Colors.RESET} {result.critical_gap_count}")
    console.print(f"  {Colors.YELLOW}High priority gaps:{Colors.RESET} {result.high_gap_count}")
    console.print(f"  Total gaps: {result.total_gap_count}")
    console.print()

    # Personas
    if result.personas_found or result.personas_missing:
        console.section("Persona Coverage")
        if result.personas_found:
            console.print(
                f"  {Colors.GREEN}Found:{Colors.RESET} {', '.join(result.personas_found)}"
            )
        if result.personas_missing:
            console.print(
                f"  {Colors.YELLOW}Missing:{Colors.RESET} {', '.join(result.personas_missing)}"
            )
        console.print()

    # Summary
    if result.summary:
        console.section("Summary")
        console.print(f"  {result.summary}")
        console.print()

    # Gaps by priority
    if result.all_gaps:
        console.section(f"{Colors.RED}Identified Gaps{Colors.RESET}")
        console.print()

        # Sort by priority
        sorted_gaps = sorted(result.all_gaps, key=lambda g: g.priority_score, reverse=True)

        for gap in sorted_gaps:
            priority_color = _get_priority_color(gap.priority)
            icon = _get_priority_icon(gap.priority)

            console.print(
                f"  {icon} {priority_color}[{gap.priority.value.upper()}]{Colors.RESET} {Colors.BOLD}{gap.title}{Colors.RESET}"
            )
            console.print(
                f"     Category: {gap.category.value} | Confidence: {gap.confidence.value}"
            )

            if gap.description:
                console.print(f"     {Colors.DIM}{gap.description}{Colors.RESET}")

            if gap.rationale:
                console.print(f"     {Colors.CYAN}Rationale:{Colors.RESET} {gap.rationale}")

            if gap.related_stories:
                console.print(f"     Related: {', '.join(gap.related_stories)}")

            if gap.affected_areas:
                console.print(f"     Affected areas: {', '.join(gap.affected_areas)}")

            if gap.suggested_story:
                console.print(f"     {Colors.GREEN}Suggested:{Colors.RESET} {gap.suggested_story}")

            console.print()

    # Category analysis
    if result.category_analyses:
        console.section("Category Coverage")
        for cat_analysis in sorted(result.category_analyses, key=lambda c: c.coverage_score):
            coverage_color = (
                Colors.GREEN
                if cat_analysis.coverage_score >= 80
                else (Colors.YELLOW if cat_analysis.coverage_score >= 60 else Colors.RED)
            )
            bar = _create_coverage_bar(cat_analysis.coverage_score)
            critical_indicator = (
                f" {Colors.RED}⚠{Colors.RESET}" if cat_analysis.has_critical_gaps else ""
            )

            console.print(
                f"  {bar} {coverage_color}{cat_analysis.coverage_score:.0f}%{Colors.RESET} "
                f"{cat_analysis.category.value}{critical_indicator}"
            )

            if cat_analysis.recommendations:
                for rec in cat_analysis.recommendations[:2]:
                    console.print(f"       → {rec}")

        console.print()

    # Next steps
    console.section("Next Steps")
    if result.critical_gap_count > 0:
        console.item(f"Address {result.critical_gap_count} critical gaps before release")
    if result.high_gap_count > 0:
        console.item(f"Review {result.high_gap_count} high priority gaps")
    if result.personas_missing:
        console.item(f"Add stories for missing personas: {', '.join(result.personas_missing)}")
    if result.total_gap_count == 0:
        console.item("No significant gaps found - requirements look complete")


def _get_priority_color(priority) -> str:
    """Get color for priority level."""
    from spectryn.application.ai_gap import GapPriority

    colors = {
        GapPriority.CRITICAL: Colors.RED,
        GapPriority.HIGH: Colors.YELLOW,
        GapPriority.MEDIUM: Colors.CYAN,
        GapPriority.LOW: Colors.DIM,
    }
    return colors.get(priority, Colors.RESET)


def _get_priority_icon(priority) -> str:
    """Get icon for priority level."""
    from spectryn.application.ai_gap import GapPriority

    icons = {
        GapPriority.CRITICAL: "🔴",
        GapPriority.HIGH: "🟡",
        GapPriority.MEDIUM: "🟢",
        GapPriority.LOW: "🔵",
    }
    return icons.get(priority, "○")


def _create_coverage_bar(score: float) -> str:
    """Create a visual coverage bar."""
    filled = int(score / 10)
    empty = 10 - filled

    if score >= 80:
        color = Colors.GREEN
    elif score >= 60:
        color = Colors.YELLOW
    else:
        color = Colors.RED

    return f"{color}{'█' * filled}{'░' * empty}{Colors.RESET}"


def _format_json(result) -> str:
    """Format gap results as JSON."""
    data = {
        "success": result.success,
        "overall_coverage": result.overall_coverage,
        "critical_gaps": result.critical_gap_count,
        "high_gaps": result.high_gap_count,
        "total_gaps": result.total_gap_count,
        "personas": {
            "found": result.personas_found,
            "missing": result.personas_missing,
        },
        "summary": result.summary,
        "gaps": [
            {
                "title": g.title,
                "description": g.description,
                "category": g.category.value,
                "priority": g.priority.value,
                "confidence": g.confidence.value,
                "related_stories": g.related_stories,
                "suggested_story": g.suggested_story,
                "rationale": g.rationale,
                "affected_areas": g.affected_areas,
            }
            for g in result.all_gaps
        ],
        "provider": result.provider_used,
        "model": result.model_used,
    }
    return json.dumps(data, indent=2)


def _format_yaml(result) -> str:
    """Format gap results as YAML."""
    try:
        import yaml

        data = {
            "coverage": f"{result.overall_coverage:.0f}%",
            "summary": result.summary,
            "personas": {
                "found": result.personas_found,
                "missing": result.personas_missing,
            },
            "gaps": [
                {
                    "title": g.title,
                    "category": g.category.value,
                    "priority": g.priority.value,
                    "suggestion": g.suggested_story or None,
                }
                for g in result.all_gaps
                if g.priority.value in ("critical", "high")
            ],
        }
        return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    except ImportError:
        return _format_json(result)
