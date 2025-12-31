"""
AI Duplicate Detection CLI - Command handler for finding similar stories.

Uses LLM providers and text similarity to detect duplicate or
overlapping user stories.
"""

import json
from pathlib import Path

from .exit_codes import ExitCode
from .output import Colors, Console, Symbols


def run_ai_duplicate(
    console: Console,
    markdown_paths: list[str] | None = None,
    min_similarity: float = 0.40,
    use_llm: bool = True,
    project_context: str | None = None,
    output_format: str = "text",
) -> int:
    """
    Run the AI duplicate detection command.

    Args:
        console: Console for output.
        markdown_paths: Paths to markdown files to compare.
        min_similarity: Minimum similarity threshold (0.0-1.0).
        use_llm: Use LLM for semantic analysis.
        project_context: Optional project context.
        output_format: Output format (text, json, yaml).

    Returns:
        Exit code.
    """
    from spectra.adapters import MarkdownParser
    from spectra.application.ai_duplicate import (
        AIDuplicateDetector,
        DuplicateOptions,
    )

    console.header(f"spectra Duplicate Detection {Symbols.SEARCH}")

    # Validate input
    if not markdown_paths:
        console.error("No markdown files specified. Use --input/-i or --markdown/-f")
        return ExitCode.CONFIG_ERROR

    # Parse all markdown files
    console.section("Parsing Stories")
    parser = MarkdownParser()
    all_stories = []
    sources: dict[str, str] = {}  # Map story ID to source file

    for path in markdown_paths:
        if not Path(path).exists():
            console.warning(f"File not found: {path}")
            continue

        try:
            stories = parser.parse_stories(Path(path))
            for story in stories:
                all_stories.append(story)
                sources[str(story.id)] = Path(path).name
            console.info(f"  {Path(path).name}: {len(stories)} stories")
        except Exception as e:
            console.warning(f"Failed to parse {path}: {e}")
            continue

    if not all_stories:
        console.error("No stories found in the provided files")
        return ExitCode.ERROR

    if len(all_stories) < 2:
        console.error("At least 2 stories are required for duplicate detection")
        return ExitCode.ERROR

    console.success(f"Total: {len(all_stories)} stories from {len(markdown_paths)} files")

    # Show configuration
    console.section("Configuration")
    console.detail(f"Minimum similarity: {int(min_similarity * 100)}%")
    console.detail(f"LLM analysis: {'enabled' if use_llm else 'disabled'}")

    # Create options
    options = DuplicateOptions(
        min_threshold=min_similarity,
        use_llm=use_llm,
        use_text_similarity=True,
        project_context=project_context or "",
    )

    # Run detection
    console.section("Detecting Duplicates")
    if use_llm:
        console.info("Calling LLM provider for semantic analysis...")
    else:
        console.info("Using text-based similarity analysis...")

    detector = AIDuplicateDetector(options)
    result = detector.detect(all_stories, options)

    if not result.success:
        console.error(f"Detection failed: {result.error}")
        return ExitCode.ERROR

    # Show LLM info
    if result.provider_used:
        console.detail(f"Provider: {result.provider_used}")
        console.detail(f"Model: {result.model_used}")
        if result.tokens_used > 0:
            console.detail(f"Tokens used: {result.tokens_used}")

    # Output based on format
    if output_format == "json":
        output = _format_json(result, sources)
        print(output)
    elif output_format == "yaml":
        output = _format_yaml(result, sources)
        print(output)
    else:
        _format_text(result, console, sources)

    # Return warning if duplicates found
    if result.stories_with_duplicates > 0:
        return ExitCode.VALIDATION_ERROR

    return ExitCode.SUCCESS


def _format_text(result, console: Console, sources: dict[str, str]) -> None:
    """Format duplicate results as human-readable text."""
    console.section("Duplicate Analysis")
    console.print()

    # Summary
    console.print(f"  Stories analyzed: {result.total_stories}")
    if result.stories_with_duplicates > 0:
        console.print(
            f"  {Colors.YELLOW}Stories with duplicates: "
            f"{result.stories_with_duplicates}{Colors.RESET}"
        )
    else:
        console.print(f"  {Colors.GREEN}No duplicates found!{Colors.RESET}")
    console.print(f"  Duplicate rate: {result.duplicate_rate:.1f}%")
    console.print(f"  Total matches: {len(result.all_matches)}")
    console.print()

    # Duplicate groups
    if result.duplicate_groups:
        console.section(f"{Colors.RED}Duplicate Groups{Colors.RESET}")
        for i, group in enumerate(result.duplicate_groups, 1):
            console.print(f"  Group {i}: {', '.join(group)}")
            for story_id in group:
                source = sources.get(story_id, "unknown")
                analysis = next((a for a in result.story_analyses if a.story_id == story_id), None)
                title = analysis.story_title if analysis else "Unknown"
                console.print(f"    • {story_id} ({source}): {title}")
        console.print()

    # Detailed matches
    if result.all_matches:
        console.section("Similarity Matches")

        # Sort by similarity score
        sorted_matches = sorted(result.all_matches, key=lambda m: m.similarity_score, reverse=True)

        for match in sorted_matches[:10]:  # Top 10
            level_color = _get_level_color(match.similarity_level.value)
            similarity_bar = _create_similarity_bar(match.similarity_score)

            console.print(
                f"  {similarity_bar} {level_color}{match.percentage}%{Colors.RESET} "
                f"{Colors.BOLD}{match.story_a_id}{Colors.RESET} ↔ "
                f"{Colors.BOLD}{match.story_b_id}{Colors.RESET}"
            )

            console.print(f"    {Colors.DIM}{match.story_a_title}{Colors.RESET}")
            console.print(f"    {Colors.DIM}{match.story_b_title}{Colors.RESET}")

            console.print(
                f"    Type: {level_color}{match.duplicate_type.value}{Colors.RESET} "
                f"| Confidence: {match.confidence}"
            )

            if match.matching_elements:
                console.print(
                    f"    {Colors.GREEN}Matching:{Colors.RESET} "
                    f"{', '.join(match.matching_elements[:3])}"
                )

            if match.differences:
                console.print(
                    f"    {Colors.YELLOW}Differences:{Colors.RESET} "
                    f"{', '.join(match.differences[:2])}"
                )

            if match.recommendation:
                console.print(f"    {Colors.CYAN}→ {match.recommendation}{Colors.RESET}")

            console.print()

        if len(result.all_matches) > 10:
            console.print(f"  ... and {len(result.all_matches) - 10} more matches")
            console.print()

    # Stories with most duplicates
    stories_with_matches = [a for a in result.story_analyses if a.matches]
    if stories_with_matches:
        console.section("Stories with Most Matches")
        sorted_analyses = sorted(stories_with_matches, key=lambda a: len(a.matches), reverse=True)

        for analysis in sorted_analyses[:5]:
            source = sources.get(analysis.story_id, "unknown")
            dup_icon = (
                f"{Colors.RED}⚠{Colors.RESET}"
                if analysis.has_duplicates
                else f"{Colors.YELLOW}~{Colors.RESET}"
            )
            console.print(
                f"  {dup_icon} {Colors.BOLD}{analysis.story_id}{Colors.RESET} "
                f"({source}): {len(analysis.matches)} matches"
            )
            if analysis.highest_match:
                console.print(
                    f"      Highest: {analysis.highest_match.percentage}% with "
                    f"{analysis.highest_match.story_b_id}"
                )
        console.print()

    # Next steps
    console.section("Next Steps")
    if result.stories_with_duplicates > 0:
        console.item(f"Review {result.stories_with_duplicates} stories with duplicates")
        console.item("Consider merging near-duplicate stories")
        console.item("Remove or archive exact duplicates")
    else:
        console.item("No action needed - no duplicates found")


def _create_similarity_bar(score: float) -> str:
    """Create a visual similarity bar."""
    filled = int(score * 10)
    empty = 10 - filled

    if score >= 0.80:
        color = Colors.RED
    elif score >= 0.60:
        color = Colors.YELLOW
    else:
        color = Colors.DIM

    return f"{color}{'█' * filled}{'░' * empty}{Colors.RESET}"


def _get_level_color(level: str) -> str:
    """Get color for similarity level."""
    colors = {
        "exact": Colors.RED,
        "high": Colors.RED,
        "medium": Colors.YELLOW,
        "low": Colors.DIM,
    }
    return colors.get(level, Colors.RESET)


def _format_json(result, sources: dict[str, str]) -> str:
    """Format duplicate results as JSON."""
    data = {
        "success": result.success,
        "total_stories": result.total_stories,
        "stories_with_duplicates": result.stories_with_duplicates,
        "duplicate_rate": result.duplicate_rate,
        "provider": result.provider_used,
        "model": result.model_used,
        "duplicate_groups": result.duplicate_groups,
        "matches": [
            {
                "story_a": m.story_a_id,
                "story_b": m.story_b_id,
                "story_a_source": sources.get(m.story_a_id, "unknown"),
                "story_b_source": sources.get(m.story_b_id, "unknown"),
                "similarity": m.percentage,
                "level": m.similarity_level.value,
                "type": m.duplicate_type.value,
                "matching_elements": m.matching_elements,
                "differences": m.differences,
                "recommendation": m.recommendation,
                "confidence": m.confidence,
            }
            for m in result.all_matches
        ],
    }
    return json.dumps(data, indent=2)


def _format_yaml(result, sources: dict[str, str]) -> str:
    """Format duplicate results as YAML."""
    try:
        import yaml

        data = {
            "stories_with_duplicates": result.stories_with_duplicates,
            "duplicate_rate": f"{result.duplicate_rate:.1f}%",
            "duplicate_groups": result.duplicate_groups,
            "matches": [
                {
                    "stories": [m.story_a_id, m.story_b_id],
                    "similarity": f"{m.percentage}%",
                    "type": m.duplicate_type.value,
                    "recommendation": m.recommendation,
                }
                for m in result.all_matches
                if m.is_likely_duplicate
            ],
        }
        return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    except ImportError:
        return _format_json(result, sources)
