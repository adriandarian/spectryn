"""AI-powered story splitting command for spectra.

Suggests how to break down large stories into smaller, more manageable pieces.
"""

from dataclasses import dataclass, field
from pathlib import Path

from .exit_codes import ExitCode
from .output import Colors, Console, Symbols


@dataclass
class SplitSuggestion:
    """A suggestion for splitting a story."""

    title: str
    description: str
    story_points: int | None = None
    acceptance_criteria: list[str] = field(default_factory=list)
    rationale: str = ""


@dataclass
class StorySplitAnalysis:
    """Analysis of a story with splitting suggestions."""

    original_id: str
    original_title: str
    original_points: int | None
    complexity_score: int  # 1-10
    split_recommended: bool
    reasons: list[str] = field(default_factory=list)
    suggestions: list[SplitSuggestion] = field(default_factory=list)


def analyze_story_complexity(story: dict | object) -> StorySplitAnalysis:
    """Analyze a story to determine if splitting is recommended.

    Factors considered:
    - Story points (>8 suggests splitting)
    - Number of acceptance criteria (>5 suggests splitting)
    - Multiple "and" in title (suggests multiple concerns)
    - Multiple user types in description

    Args:
        story: Story to analyze (dict or UserStory)

    Returns:
        Analysis with splitting recommendations
    """
    # Extract fields from story
    if hasattr(story, "id"):
        story_id = str(story.id)
        title = story.title or ""
        points = story.story_points
        ac_list = story.acceptance_criteria or []
        description = ""
        if story.description:
            if hasattr(story.description, "as_a"):
                description = f"{story.description.as_a} {story.description.i_want} {story.description.so_that}"
            else:
                description = str(story.description)
    else:
        story_id = str(story.get("id", ""))
        title = story.get("title", "")
        points = story.get("story_points")
        ac_list = story.get("acceptance_criteria", [])
        description = story.get("description", "")

    analysis = StorySplitAnalysis(
        original_id=story_id,
        original_title=title,
        original_points=points,
        complexity_score=0,
        split_recommended=False,
    )

    # Analyze complexity factors
    complexity = 0

    # Factor 1: Story points
    if points:
        if points >= 13:
            complexity += 4
            analysis.reasons.append(
                f"High story points ({points}) - typically too large for a sprint"
            )
        elif points >= 8:
            complexity += 2
            analysis.reasons.append(f"Story points ({points}) suggest moderate complexity")

    # Factor 2: Acceptance criteria count
    ac_count = len(ac_list) if isinstance(ac_list, list) else 0
    if ac_count > 8:
        complexity += 3
        analysis.reasons.append(f"Many acceptance criteria ({ac_count}) - may be doing too much")
    elif ac_count > 5:
        complexity += 1
        analysis.reasons.append(f"Moderate acceptance criteria count ({ac_count})")

    # Factor 3: Multiple concerns in title (detected by "and", "&", ",")
    title_lower = title.lower()
    if " and " in title_lower or " & " in title_lower:
        complexity += 2
        analysis.reasons.append("Title suggests multiple concerns (contains 'and')")

    # Factor 4: Multiple user types
    user_types = ["user", "admin", "manager", "developer", "customer", "guest", "member"]
    found_users = [u for u in user_types if u in description.lower()]
    if len(found_users) > 1:
        complexity += 2
        analysis.reasons.append(f"Multiple user types mentioned: {', '.join(found_users)}")

    # Factor 5: Technical breadth
    tech_keywords = [
        "frontend",
        "backend",
        "database",
        "api",
        "ui",
        "ux",
        "integration",
        "migration",
    ]
    found_tech = [t for t in tech_keywords if t in title_lower or t in description.lower()]
    if len(found_tech) > 2:
        complexity += 2
        analysis.reasons.append(f"Spans multiple technical areas: {', '.join(found_tech)}")

    analysis.complexity_score = min(complexity, 10)
    analysis.split_recommended = complexity >= 4

    # Generate split suggestions if recommended
    if analysis.split_recommended:
        analysis.suggestions = generate_split_suggestions(title, description, ac_list, points)

    return analysis


def generate_split_suggestions(
    title: str,
    description: str,
    acceptance_criteria: list,
    original_points: int | None,
) -> list[SplitSuggestion]:
    """Generate suggestions for splitting a story.

    Args:
        title: Original story title
        description: Original story description
        acceptance_criteria: List of acceptance criteria
        original_points: Original story points

    Returns:
        List of split suggestions
    """
    suggestions: list[SplitSuggestion] = []

    # Strategy 1: Split by acceptance criteria groups
    if len(acceptance_criteria) >= 4:
        # Group AC into chunks
        mid = len(acceptance_criteria) // 2
        ac_list = list(acceptance_criteria)

        suggestions.append(
            SplitSuggestion(
                title=f"{title} - Part 1 (Core Functionality)",
                description="First part focusing on core functionality",
                story_points=(original_points // 2) if original_points else None,
                acceptance_criteria=[str(ac) for ac in ac_list[:mid]],
                rationale="Split acceptance criteria into manageable chunks",
            )
        )
        suggestions.append(
            SplitSuggestion(
                title=f"{title} - Part 2 (Extended Functionality)",
                description="Second part with extended functionality",
                story_points=(original_points - original_points // 2) if original_points else None,
                acceptance_criteria=[str(ac) for ac in ac_list[mid:]],
                rationale="Split acceptance criteria into manageable chunks",
            )
        )

    # Strategy 2: Split by technical layer
    title_lower = title.lower()
    if any(word in title_lower for word in ["full", "complete", "end-to-end", "e2e"]):
        base_points = (original_points // 3) if original_points else None

        suggestions.append(
            SplitSuggestion(
                title=f"{title} - Backend/API",
                description="Backend implementation and API endpoints",
                story_points=base_points,
                rationale="Vertical slice: Backend layer",
            )
        )
        suggestions.append(
            SplitSuggestion(
                title=f"{title} - Frontend/UI",
                description="Frontend implementation and user interface",
                story_points=base_points,
                rationale="Vertical slice: Frontend layer",
            )
        )
        suggestions.append(
            SplitSuggestion(
                title=f"{title} - Integration & Testing",
                description="Integration between layers and end-to-end testing",
                story_points=base_points,
                rationale="Vertical slice: Integration layer",
            )
        )

    # Strategy 3: Split by user journey phases
    if " and " in title.lower():
        parts = title.lower().split(" and ")
        base_title = title.split(" and ")[0].split(" And ")[0]

        for part in parts[:3]:
            suggestions.append(
                SplitSuggestion(
                    title=f"{base_title.strip().title()} - {part.strip().title()}",
                    description=f"Focused on: {part.strip()}",
                    story_points=(original_points // len(parts)) if original_points else None,
                    rationale="Split by distinct concerns in title",
                )
            )

    # If no specific strategies matched, provide generic suggestions
    if not suggestions and original_points and original_points >= 8:
        half_points = original_points // 2
        suggestions.append(
            SplitSuggestion(
                title=f"{title} - MVP/Core",
                description="Minimum viable implementation of core feature",
                story_points=half_points,
                rationale="Deliver core value first",
            )
        )
        suggestions.append(
            SplitSuggestion(
                title=f"{title} - Enhancements",
                description="Additional features and polish",
                story_points=original_points - half_points,
                rationale="Follow-up with enhancements",
            )
        )

    return suggestions


def format_analysis(
    analysis: StorySplitAnalysis,
    color: bool = True,
) -> list[str]:
    """Format analysis for display.

    Args:
        analysis: Analysis to format
        color: Whether to use colors

    Returns:
        Formatted lines
    """
    lines: list[str] = []

    # Header
    if color:
        lines.append(
            f"{Colors.BOLD}{analysis.original_id}: {analysis.original_title}{Colors.RESET}"
        )
    else:
        lines.append(f"{analysis.original_id}: {analysis.original_title}")
    lines.append("")

    # Complexity score
    complexity_bar = "█" * analysis.complexity_score + "░" * (10 - analysis.complexity_score)
    if color:
        if analysis.complexity_score >= 7:
            score_color = Colors.RED
        elif analysis.complexity_score >= 4:
            score_color = Colors.YELLOW
        else:
            score_color = Colors.GREEN
        lines.append(
            f"  Complexity: {score_color}{complexity_bar}{Colors.RESET} {analysis.complexity_score}/10"
        )
    else:
        lines.append(f"  Complexity: [{complexity_bar}] {analysis.complexity_score}/10")

    # Points
    if analysis.original_points:
        lines.append(f"  Story Points: {analysis.original_points}")
    lines.append("")

    # Recommendation
    if analysis.split_recommended:
        if color:
            lines.append(f"  {Colors.YELLOW}{Symbols.WARNING} Split Recommended{Colors.RESET}")
        else:
            lines.append("  ⚠ Split Recommended")
    elif color:
        lines.append(f"  {Colors.GREEN}{Symbols.CHECK} Size looks good{Colors.RESET}")
    else:
        lines.append("  ✓ Size looks good")
    lines.append("")

    # Reasons
    if analysis.reasons:
        lines.append("  Analysis:")
        for reason in analysis.reasons:
            lines.append(f"    • {reason}")
        lines.append("")

    # Suggestions
    if analysis.suggestions:
        if color:
            lines.append(f"  {Colors.CYAN}Suggested Split:{Colors.RESET}")
        else:
            lines.append("  Suggested Split:")
        lines.append("")

        for i, suggestion in enumerate(analysis.suggestions, 1):
            if color:
                lines.append(f"    {Colors.BOLD}{i}. {suggestion.title}{Colors.RESET}")
            else:
                lines.append(f"    {i}. {suggestion.title}")

            if suggestion.story_points:
                lines.append(f"       Points: {suggestion.story_points}")
            if suggestion.rationale:
                lines.append(f"       Rationale: {suggestion.rationale}")
            if suggestion.acceptance_criteria:
                lines.append("       Acceptance Criteria:")
                for ac in suggestion.acceptance_criteria[:3]:
                    lines.append(f"         - {ac[:60]}...")
                if len(suggestion.acceptance_criteria) > 3:
                    lines.append(f"         ... and {len(suggestion.acceptance_criteria) - 3} more")
            lines.append("")

    return lines


def run_split(
    console: Console | None = None,
    input_path: Path | None = None,
    story_id: str | None = None,
    threshold: int = 4,
    output_format: str = "text",
    color: bool = True,
) -> ExitCode:
    """Run story splitting analysis.

    Args:
        console: Console for output
        input_path: Path to markdown file
        story_id: Specific story to analyze (or all if None)
        threshold: Complexity threshold for recommendations (1-10)
        output_format: Output format (text, json, markdown)
        color: Whether to use colors

    Returns:
        Exit code
    """
    console = console or Console(color=color)

    if not input_path:
        console.error("Input file required: --markdown EPIC.md")
        return ExitCode.ERROR

    console.header("Story Split Analysis")

    # Parse stories from file
    if not input_path.exists():
        console.error(f"File not found: {input_path}")
        return ExitCode.ERROR

    try:
        from spectryn.adapters.parsers.markdown import MarkdownParser

        parser = MarkdownParser()
        stories = parser.parse_stories(input_path)
    except Exception as e:
        console.error(f"Failed to parse file: {e}")
        return ExitCode.ERROR

    if not stories:
        console.warning("No stories found in file")
        return ExitCode.SUCCESS

    # Filter to specific story if requested
    if story_id:
        stories = [s for s in stories if str(s.id) == story_id]
        if not stories:
            console.error(f"Story not found: {story_id}")
            return ExitCode.ERROR

    console.info(f"Analyzing {len(stories)} stories...")
    console.print("")

    # Analyze each story
    analyses: list[StorySplitAnalysis] = []
    split_recommended_count = 0

    for story in stories:
        analysis = analyze_story_complexity(story)
        analyses.append(analysis)
        if analysis.split_recommended:
            split_recommended_count += 1

    # Output based on format
    if output_format == "json":
        import json

        output = {
            "total_stories": len(analyses),
            "split_recommended": split_recommended_count,
            "analyses": [
                {
                    "id": a.original_id,
                    "title": a.original_title,
                    "points": a.original_points,
                    "complexity": a.complexity_score,
                    "split_recommended": a.split_recommended,
                    "reasons": a.reasons,
                    "suggestions": [
                        {
                            "title": s.title,
                            "points": s.story_points,
                            "rationale": s.rationale,
                        }
                        for s in a.suggestions
                    ],
                }
                for a in analyses
            ],
        }
        print(json.dumps(output, indent=2))

    elif output_format == "markdown":
        print("# Story Split Analysis\n")
        print(f"**Total Stories:** {len(analyses)}")
        print(f"**Split Recommended:** {split_recommended_count}\n")

        for analysis in analyses:
            if analysis.split_recommended or not story_id:
                print(f"## {analysis.original_id}: {analysis.original_title}\n")
                print(f"- **Complexity:** {analysis.complexity_score}/10")
                print(f"- **Points:** {analysis.original_points or 'N/A'}")
                print(f"- **Split Recommended:** {'Yes' if analysis.split_recommended else 'No'}\n")

                if analysis.reasons:
                    print("### Analysis\n")
                    for reason in analysis.reasons:
                        print(f"- {reason}")
                    print("")

                if analysis.suggestions:
                    print("### Suggested Split\n")
                    for i, s in enumerate(analysis.suggestions, 1):
                        print(f"{i}. **{s.title}** ({s.story_points or '?'} pts)")
                        if s.rationale:
                            print(f"   - {s.rationale}")
                    print("")

    else:  # text format
        # Summary
        if color:
            console.print(f"  {Colors.BOLD}Summary:{Colors.RESET}")
        else:
            console.print("  Summary:")
        console.print(f"    Total stories: {len(analyses)}")

        if split_recommended_count > 0:
            if color:
                console.print(
                    f"    Split recommended: {Colors.YELLOW}{split_recommended_count}{Colors.RESET}"
                )
            else:
                console.print(f"    Split recommended: {split_recommended_count}")
        elif color:
            console.print(f"    Split recommended: {Colors.GREEN}0{Colors.RESET}")
        else:
            console.print("    Split recommended: 0")
        console.print("")

        # Details for stories needing splits (or all if specific story requested)
        for analysis in analyses:
            if analysis.split_recommended or story_id:
                lines = format_analysis(analysis, color)
                for line in lines:
                    console.print(line)
                console.print("-" * 50)
                console.print("")

    return ExitCode.SUCCESS
