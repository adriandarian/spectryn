"""
AI Smart Splitting CLI - Command handler for suggesting story splits.

Uses LLM providers to analyze story size and complexity and suggest
how to split large stories into smaller, more manageable pieces.
"""

import json
from pathlib import Path

from .exit_codes import ExitCode
from .output import Colors, Console, Symbols


def run_ai_split(
    console: Console,
    markdown_path: str | None = None,
    story_ids: list[str] | None = None,
    max_points: int = 8,
    max_ac: int = 8,
    prefer_vertical: bool = True,
    prefer_mvp: bool = True,
    project_context: str | None = None,
    tech_stack: str | None = None,
    output_format: str = "text",
    generate_markdown: bool = False,
) -> int:
    """
    Run the AI smart splitting command.

    Args:
        console: Console for output.
        markdown_path: Path to markdown file containing stories.
        story_ids: Optional list of specific story IDs to analyze.
        max_points: Maximum story points before suggesting split.
        max_ac: Maximum acceptance criteria before suggesting split.
        prefer_vertical: Prefer vertical slices when splitting.
        prefer_mvp: Suggest MVP version first.
        project_context: Optional project context.
        tech_stack: Optional tech stack info.
        output_format: Output format (text, json, yaml).
        generate_markdown: Generate markdown for split stories.

    Returns:
        Exit code.
    """
    from spectryn.adapters import MarkdownParser
    from spectryn.application.ai_split import (
        AIStorySplitter,
        SplitOptions,
    )

    console.header(f"spectra Smart Splitting {Symbols.SPLIT}")

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

    console.success(f"Found {len(stories)} stories to analyze")

    # Show configuration
    console.section("Configuration")
    console.detail(f"Max story points before split: {max_points}")
    console.detail(f"Max acceptance criteria before split: {max_ac}")
    console.detail(f"Prefer vertical slices: {'yes' if prefer_vertical else 'no'}")
    console.detail(f"Suggest MVP first: {'yes' if prefer_mvp else 'no'}")

    # Create options
    options = SplitOptions(
        max_story_points=max_points,
        max_acceptance_criteria=max_ac,
        prefer_vertical_slices=prefer_vertical,
        prefer_mvp_first=prefer_mvp,
        project_context=project_context or "",
        tech_stack=tech_stack or "",
    )

    # Run analysis
    console.section("Analyzing Stories")
    console.info("Calling LLM provider for splitting suggestions...")

    splitter = AIStorySplitter(options)
    result = splitter.analyze(stories, options)

    if not result.success:
        console.error(f"Analysis failed: {result.error}")
        return ExitCode.ERROR

    if not result.suggestions:
        console.warning("No splitting suggestions returned")
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
        _format_text(result, console, splitter)

    # Generate markdown if requested
    if generate_markdown and result.stories_to_split > 0:
        console.section("Generated Markdown")
        md = _generate_markdown(result, splitter)
        print(md)

    return ExitCode.SUCCESS


def _format_text(result, console: Console, splitter) -> None:
    """Format splitting results as human-readable text."""
    console.section("Splitting Analysis")
    console.print()

    # Summary
    console.print(f"  Stories analyzed: {len(result.suggestions)}")
    console.print(f"  {Colors.YELLOW}Stories to split: {result.stories_to_split}{Colors.RESET}")
    console.print(f"  {Colors.GREEN}Stories OK: {result.stories_ok}{Colors.RESET}")
    if result.stories_to_split > 0:
        console.print(f"  Total new stories: {result.total_new_stories}")
    console.print()

    # Per-story suggestions
    for suggestion in result.suggestions:
        # Story header
        if suggestion.should_split:
            status_icon = f"{Colors.YELLOW}✂{Colors.RESET}"
            status_text = f"{Colors.YELLOW}SPLIT RECOMMENDED{Colors.RESET}"
        else:
            status_icon = f"{Colors.GREEN}✓{Colors.RESET}"
            status_text = f"{Colors.GREEN}OK{Colors.RESET}"

        console.print(
            f"  {status_icon} {Colors.BOLD}{suggestion.original_story_id}{Colors.RESET}: "
            f"{suggestion.original_title}"
        )
        console.print(f"     Status: {status_text}")
        console.print(f"     Current points: {suggestion.original_points}")
        console.print(f"     Confidence: {_format_confidence(suggestion.confidence)}")

        if suggestion.split_reasons:
            reasons = [_format_reason(r) for r in suggestion.split_reasons]
            console.print(f"     Reasons: {', '.join(reasons)}")

        if suggestion.explanation:
            console.print(f"     {Colors.DIM}{suggestion.explanation}{Colors.RESET}")

        # Show suggested splits
        if suggestion.should_split and suggestion.suggested_stories:
            console.print()
            console.print(f"     {Colors.CYAN}Suggested splits:{Colors.RESET}")

            # Generate IDs for display
            split_ids = splitter.generate_split_ids(
                suggestion.original_story_id, len(suggestion.suggested_stories)
            )

            for i, split_story in enumerate(suggestion.suggested_stories):
                split_id = split_ids[i] if i < len(split_ids) else f"#{i + 1}"
                console.print(
                    f"       {Colors.CYAN}→{Colors.RESET} {Colors.BOLD}{split_id}{Colors.RESET}: "
                    f"{split_story.title}"
                )
                console.print(
                    f"         Points: {split_story.suggested_points} | "
                    f"AC: {len(split_story.acceptance_criteria)}"
                )
                if split_story.rationale:
                    console.print(f"         {Colors.DIM}{split_story.rationale}{Colors.RESET}")

            # Point comparison
            if suggestion.point_change != 0:
                change_str = (
                    f"+{suggestion.point_change}"
                    if suggestion.point_change > 0
                    else str(suggestion.point_change)
                )
                console.print(
                    f"     Total after split: {suggestion.total_suggested_points} "
                    f"({change_str} points)"
                )

        console.print()

    # Next steps
    if result.stories_to_split > 0:
        console.section("Next Steps")
        console.item("Review the suggested splits")
        console.item("Generate markdown: spectra --split -f FILE --generate-markdown")
        console.item("Copy suggested stories to your epic file")
        console.item("Archive or remove the original large stories")


def _format_confidence(confidence: str) -> str:
    """Format confidence with color."""
    if confidence == "high":
        return f"{Colors.GREEN}high{Colors.RESET}"
    if confidence == "medium":
        return f"{Colors.YELLOW}medium{Colors.RESET}"
    return f"{Colors.RED}low{Colors.RESET}"


def _format_reason(reason) -> str:
    """Format split reason for display."""
    reason_map = {
        "too_large": "Too large",
        "too_many_ac": "Too many AC",
        "multiple_features": "Multiple features",
        "multiple_personas": "Multiple personas",
        "tech_complexity": "Technical complexity",
        "unclear_scope": "Unclear scope",
        "long_implementation": "Long implementation",
    }
    return reason_map.get(reason.value, reason.value)


def _format_json(result) -> str:
    """Format splitting results as JSON."""
    data = {
        "success": result.success,
        "stories_to_split": result.stories_to_split,
        "stories_ok": result.stories_ok,
        "total_new_stories": result.total_new_stories,
        "provider": result.provider_used,
        "model": result.model_used,
        "tokens_used": result.tokens_used,
        "suggestions": [
            {
                "original_story_id": s.original_story_id,
                "original_title": s.original_title,
                "original_points": s.original_points,
                "should_split": s.should_split,
                "split_reasons": [r.value for r in s.split_reasons],
                "confidence": s.confidence,
                "explanation": s.explanation,
                "total_suggested_points": s.total_suggested_points,
                "suggested_stories": [
                    {
                        "title": ss.title,
                        "description": {
                            "role": ss.description.role,
                            "want": ss.description.want,
                            "benefit": ss.description.benefit,
                        }
                        if ss.description
                        else None,
                        "acceptance_criteria": ss.acceptance_criteria,
                        "suggested_points": ss.suggested_points,
                        "rationale": ss.rationale,
                        "inherited_labels": ss.inherited_labels,
                        "technical_notes": ss.technical_notes,
                    }
                    for ss in s.suggested_stories
                ],
            }
            for s in result.suggestions
        ],
    }
    return json.dumps(data, indent=2)


def _format_yaml(result) -> str:
    """Format splitting results as YAML."""
    try:
        import yaml

        data = {
            "stories_to_split": result.stories_to_split,
            "stories_ok": result.stories_ok,
            "total_new_stories": result.total_new_stories,
            "suggestions": [
                {
                    "story_id": s.original_story_id,
                    "should_split": s.should_split,
                    "reasons": [r.value for r in s.split_reasons],
                    "splits": [
                        {
                            "title": ss.title,
                            "points": ss.suggested_points,
                            "ac_count": len(ss.acceptance_criteria),
                        }
                        for ss in s.suggested_stories
                    ],
                }
                for s in result.suggestions
                if s.should_split
            ],
        }
        return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    except ImportError:
        return _format_json(result)


def _generate_markdown(result, splitter) -> str:
    """Generate markdown for split stories."""
    lines = ["# Suggested Story Splits", ""]

    for suggestion in result.suggestions:
        if not suggestion.should_split or not suggestion.suggested_stories:
            continue

        lines.append(f"## From: {suggestion.original_story_id} - {suggestion.original_title}")
        lines.append("")
        lines.append(f"> Original: {suggestion.original_points} points")
        lines.append(f"> Reason: {suggestion.explanation}")
        lines.append("")

        # Generate IDs
        split_ids = splitter.generate_split_ids(
            suggestion.original_story_id, len(suggestion.suggested_stories)
        )

        for i, split_story in enumerate(suggestion.suggested_stories):
            split_id = split_ids[i] if i < len(split_ids) else f"NEW-{i + 1}"

            lines.append(f"### {split_id}: {split_story.title}")
            lines.append("")

            # Metadata table
            lines.append("| Field | Value |")
            lines.append("|-------|-------|")
            lines.append(f"| **Story Points** | {split_story.suggested_points} |")
            lines.append("| **Priority** | 🟢 Medium |")
            lines.append("| **Status** | 📋 Planned |")
            if split_story.inherited_labels:
                lines.append(f"| **Labels** | {', '.join(split_story.inherited_labels)} |")
            lines.append("")

            # Description
            if split_story.description:
                lines.append("#### Description")
                lines.append("")
                lines.append(f"**As a** {split_story.description.role}")
                lines.append(f"**I want** {split_story.description.want}")
                lines.append(f"**So that** {split_story.description.benefit}")
                lines.append("")

            # Acceptance criteria
            if split_story.acceptance_criteria:
                lines.append("#### Acceptance Criteria")
                lines.append("")
                for ac in split_story.acceptance_criteria:
                    lines.append(f"- [ ] {ac}")
                lines.append("")

            # Technical notes
            if split_story.technical_notes:
                lines.append("#### Technical Notes")
                lines.append("")
                lines.append(split_story.technical_notes)
                lines.append("")

            # Rationale
            if split_story.rationale:
                lines.append(f"> *Split rationale: {split_story.rationale}*")
                lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)
