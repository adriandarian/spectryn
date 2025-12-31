"""
AI Dependency Detection CLI - Command handler for detecting story dependencies.

Uses LLM providers to analyze stories and identify blocking relationships.
"""

import json
from pathlib import Path

from .exit_codes import ExitCode
from .output import Colors, Console, Symbols


def run_ai_dependency(
    console: Console,
    markdown_path: str | None = None,
    detect_technical: bool = True,
    detect_data: bool = True,
    detect_feature: bool = True,
    detect_related: bool = True,
    check_circular: bool = True,
    project_context: str | None = None,
    tech_stack: str | None = None,
    architecture: str | None = None,
    output_format: str = "text",
    show_graph: bool = False,
) -> int:
    """
    Run the AI dependency detection command.

    Args:
        console: Console for output.
        markdown_path: Path to markdown file containing stories.
        detect_technical: Detect technical dependencies.
        detect_data: Detect data dependencies.
        detect_feature: Detect feature dependencies.
        detect_related: Detect related (non-blocking) relationships.
        check_circular: Check for circular dependencies.
        project_context: Optional project context.
        tech_stack: Optional tech stack info.
        architecture: Optional architecture description.
        output_format: Output format (text, json, yaml, mermaid).
        show_graph: Show ASCII dependency graph.

    Returns:
        Exit code.
    """
    from spectra.adapters import MarkdownParser
    from spectra.application.ai_dependency import (
        AIDependencyDetector,
        DependencyOptions,
    )

    console.header(f"spectra Dependency Detection {Symbols.ARROW_RIGHT}")

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

    if len(stories) < 2:
        console.error("At least 2 stories are required for dependency detection")
        return ExitCode.ERROR

    console.success(f"Found {len(stories)} stories to analyze")

    # Show configuration
    console.section("Configuration")
    categories = []
    if detect_technical:
        categories.append("technical")
    if detect_data:
        categories.append("data")
    if detect_feature:
        categories.append("feature")
    if detect_related:
        categories.append("related")
    console.detail(f"Detection categories: {', '.join(categories)}")
    console.detail(f"Check circular: {'yes' if check_circular else 'no'}")

    # Create options
    options = DependencyOptions(
        detect_technical=detect_technical,
        detect_data=detect_data,
        detect_feature=detect_feature,
        detect_related=detect_related,
        check_circular=check_circular,
        project_context=project_context or "",
        tech_stack=tech_stack or "",
        architecture=architecture or "",
    )

    # Run detection
    console.section("Analyzing Dependencies")
    console.info("Calling LLM provider for dependency analysis...")

    detector = AIDependencyDetector(options)
    result = detector.detect(stories, options)

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
        output = _format_json(result)
        print(output)
    elif output_format == "yaml":
        output = _format_yaml(result)
        print(output)
    elif output_format == "mermaid":
        output = _format_mermaid(result)
        print(output)
    else:
        _format_text(result, console, show_graph)

    return ExitCode.SUCCESS


def _format_text(result, console: Console, show_graph: bool) -> None:
    """Format dependency results as human-readable text."""
    console.section("Dependency Analysis")
    console.print()

    # Summary
    console.print(f"  Stories analyzed: {len(result.story_dependencies)}")
    console.print(f"  {Colors.CYAN}Dependencies found: {result.total_dependencies}{Colors.RESET}")
    console.print(f"  Stories with blockers: {result.stories_with_blockers}")

    if result.has_circular:
        console.print(
            f"  {Colors.RED}{Symbols.CROSS} Circular dependencies: "
            f"{len(result.circular_dependencies)}{Colors.RESET}"
        )
    console.print()

    # Circular dependency warnings
    if result.circular_dependencies:
        console.section(f"{Colors.RED}Circular Dependencies Detected{Colors.RESET}")
        for cycle in result.circular_dependencies:
            console.print(f"  {Colors.RED}⚠{Colors.RESET} {' → '.join(cycle)}")
        console.print()

    # Per-story dependencies
    console.section("Story Dependencies")

    for story_dep in result.story_dependencies:
        # Story header
        if story_dep.has_blockers:
            status_icon = f"{Colors.YELLOW}⏸{Colors.RESET}"
        elif story_dep.is_blocker:
            status_icon = f"{Colors.RED}🔒{Colors.RESET}"
        else:
            status_icon = f"{Colors.GREEN}✓{Colors.RESET}"

        console.print(
            f"  {status_icon} {Colors.BOLD}{story_dep.story_id}{Colors.RESET}: "
            f"{story_dep.story_title}"
        )

        # Blocked by
        if story_dep.blocked_by:
            console.print(
                f"     {Colors.YELLOW}Blocked by:{Colors.RESET} {', '.join(story_dep.blocked_by)}"
            )

        # Blocks
        if story_dep.blocks:
            console.print(f"     {Colors.RED}Blocks:{Colors.RESET} {', '.join(story_dep.blocks)}")

        # Related
        if story_dep.related_to:
            console.print(
                f"     {Colors.DIM}Related to:{Colors.RESET} {', '.join(story_dep.related_to)}"
            )

        # Dependency details
        for dep in story_dep.dependencies:
            strength_color = (
                Colors.RED
                if dep.strength.value == "hard"
                else Colors.YELLOW
                if dep.strength.value == "soft"
                else Colors.DIM
            )
            console.print(
                f"       {Colors.DIM}→ {dep.to_story_id} "
                f"[{strength_color}{dep.strength.value}{Colors.RESET}] "
                f"{dep.reason}{Colors.RESET}"
            )

        console.print()

    # Suggested order
    if result.suggested_order:
        console.section("Suggested Execution Order")
        for i, story_id in enumerate(result.suggested_order, 1):
            console.print(f"  {i}. {story_id}")
        console.print()

    # ASCII Graph
    if show_graph and result.all_dependencies:
        console.section("Dependency Graph")
        _print_ascii_graph(result, console)

    # Next steps
    console.section("Next Steps")
    console.item("Review detected dependencies")
    console.item("Update blocked stories with dependency links")
    console.item("Export as Mermaid: spectra --dependencies -f FILE -o mermaid")


def _print_ascii_graph(result, console: Console) -> None:
    """Print a simple ASCII representation of the dependency graph."""
    # Find root nodes (no blockers)
    all_story_ids = {s.story_id for s in result.story_dependencies}
    blocked_ids = {s.story_id for s in result.story_dependencies if s.has_blockers}
    root_ids = all_story_ids - blocked_ids

    if not root_ids:
        root_ids = all_story_ids  # All are blocked, just show all

    visited = set()

    def print_tree(story_id: str, indent: int = 0) -> None:
        if story_id in visited:
            console.print(f"{'  ' * indent}├── {story_id} (circular)")
            return

        visited.add(story_id)
        prefix = "├── " if indent > 0 else ""
        console.print(f"{'  ' * indent}{prefix}{story_id}")

        # Find stories this blocks
        story_dep = next((s for s in result.story_dependencies if s.story_id == story_id), None)
        if story_dep:
            for blocked_id in story_dep.blocks:
                print_tree(blocked_id, indent + 1)

    for root_id in sorted(root_ids):
        print_tree(root_id)

    console.print()


def _format_json(result) -> str:
    """Format dependency results as JSON."""
    data = {
        "success": result.success,
        "total_dependencies": result.total_dependencies,
        "stories_with_blockers": result.stories_with_blockers,
        "has_circular": result.has_circular,
        "circular_dependencies": result.circular_dependencies,
        "suggested_order": result.suggested_order,
        "provider": result.provider_used,
        "model": result.model_used,
        "dependencies": [
            {
                "from": d.from_story_id,
                "to": d.to_story_id,
                "type": d.dependency_type.value,
                "strength": d.strength.value,
                "reason": d.reason,
                "confidence": d.confidence,
            }
            for d in result.all_dependencies
        ],
        "stories": [
            {
                "id": s.story_id,
                "title": s.story_title,
                "blocked_by": s.blocked_by,
                "blocks": s.blocks,
                "related_to": s.related_to,
            }
            for s in result.story_dependencies
        ],
    }
    return json.dumps(data, indent=2)


def _format_yaml(result) -> str:
    """Format dependency results as YAML."""
    try:
        import yaml

        data = {
            "total_dependencies": result.total_dependencies,
            "circular_dependencies": result.circular_dependencies,
            "suggested_order": result.suggested_order,
            "stories": [
                {
                    "id": s.story_id,
                    "blocked_by": s.blocked_by,
                    "blocks": s.blocks,
                }
                for s in result.story_dependencies
                if s.blocked_by or s.blocks
            ],
        }
        return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    except ImportError:
        return _format_json(result)


def _format_mermaid(result) -> str:
    """Format dependency graph as Mermaid diagram."""
    lines = ["```mermaid", "graph TD"]

    # Add nodes
    for story_dep in result.story_dependencies:
        # Escape special characters in title
        title = story_dep.story_title.replace('"', "'")[:30]
        lines.append(f'    {story_dep.story_id}["{story_dep.story_id}: {title}"]')

    lines.append("")

    # Add edges
    for dep in result.all_dependencies:
        if dep.dependency_type.value == "blocked_by":
            # from_story is blocked by to_story, so to → from
            arrow = "==>" if dep.strength.value == "hard" else "-->"
            lines.append(f"    {dep.to_story_id} {arrow} {dep.from_story_id}")
        elif dep.dependency_type.value == "blocks":
            arrow = "==>" if dep.strength.value == "hard" else "-->"
            lines.append(f"    {dep.from_story_id} {arrow} {dep.to_story_id}")
        elif dep.dependency_type.value == "related":
            lines.append(f"    {dep.from_story_id} -.- {dep.to_story_id}")

    # Style circular dependencies
    if result.circular_dependencies:
        lines.append("")
        lines.append("    %% Circular dependencies highlighted")
        for cycle in result.circular_dependencies:
            for story_id in cycle[:-1]:  # Last is duplicate of first
                lines.append(f"    style {story_id} fill:#ff6b6b")

    lines.append("```")
    return "\n".join(lines)
