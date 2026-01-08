"""
AI Acceptance Criteria Generation CLI - Command handler for generating AC.

Uses LLM providers to analyze story descriptions and generate
comprehensive, testable acceptance criteria.
"""

import json
from pathlib import Path

from .exit_codes import ExitCode
from .output import Colors, Console, Symbols


def run_ai_acceptance(
    console: Console,
    markdown_path: str | None = None,
    story_ids: list[str] | None = None,
    use_gherkin: bool = False,
    include_validation: bool = True,
    include_error_handling: bool = True,
    include_edge_cases: bool = True,
    include_security: bool = False,
    min_ac: int = 3,
    max_ac: int = 8,
    project_context: str | None = None,
    tech_stack: str | None = None,
    output_format: str = "text",
    apply_changes: bool = False,
) -> int:
    """
    Run the AI AC generation command.

    Args:
        console: Console for output.
        markdown_path: Path to markdown file containing stories.
        story_ids: Optional list of specific story IDs to process.
        use_gherkin: Use Given/When/Then format.
        include_validation: Include validation AC.
        include_error_handling: Include error handling AC.
        include_edge_cases: Include edge case AC.
        include_security: Include security AC.
        min_ac: Minimum AC count per story.
        max_ac: Maximum AC count per story.
        project_context: Optional project context.
        tech_stack: Optional tech stack info.
        output_format: Output format (text, json, yaml, markdown).
        apply_changes: Apply generated AC to the file.

    Returns:
        Exit code.
    """
    from spectryn.adapters import MarkdownParser
    from spectryn.application.ai_acceptance import (
        ACGenerationOptions,
        AIAcceptanceCriteriaGenerator,
    )

    console.header(f"spectra AC Generation {Symbols.CHECKMARK}")

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

    # Filter to stories that need AC (none or few existing)
    if story_ids:
        filtered = [s for s in stories if str(s.id) in story_ids]
        if not filtered:
            console.error(f"No stories found matching IDs: {', '.join(story_ids)}")
            console.info(f"Available IDs: {', '.join(str(s.id) for s in stories)}")
            return ExitCode.ERROR
        stories = filtered
    else:
        # Default: filter to stories with few or no AC
        stories_needing_ac = [
            s for s in stories if not s.acceptance_criteria or len(s.acceptance_criteria) < min_ac
        ]
        if stories_needing_ac:
            console.info(
                f"Found {len(stories_needing_ac)} stories needing AC (out of {len(stories)} total)"
            )
            stories = stories_needing_ac
        else:
            console.info("All stories have sufficient AC, processing all")

    console.success(f"Processing {len(stories)} stories")

    # Show configuration
    console.section("Configuration")
    console.detail(f"Format: {'Gherkin (Given/When/Then)' if use_gherkin else 'Checklist'}")
    console.detail(f"AC per story: {min_ac}-{max_ac}")

    categories = ["functional"]
    if include_validation:
        categories.append("validation")
    if include_error_handling:
        categories.append("error handling")
    if include_edge_cases:
        categories.append("edge cases")
    if include_security:
        categories.append("security")
    console.detail(f"Categories: {', '.join(categories)}")

    # Create options
    options = ACGenerationOptions(
        use_gherkin=use_gherkin,
        include_validation=include_validation,
        include_error_handling=include_error_handling,
        include_edge_cases=include_edge_cases,
        include_security=include_security,
        min_ac_count=min_ac,
        max_ac_count=max_ac,
        project_context=project_context or "",
        tech_stack=tech_stack or "",
    )

    # Run generation
    console.section("Generating Acceptance Criteria")
    console.info("Calling LLM provider for AC generation...")

    generator = AIAcceptanceCriteriaGenerator(options)
    result = generator.generate(stories, options)

    if not result.success:
        console.error(f"Generation failed: {result.error}")
        return ExitCode.ERROR

    if not result.suggestions:
        console.warning("No AC suggestions returned")
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
    elif output_format == "markdown":
        output = _format_markdown(result)
        print(output)
    else:
        _format_text(result, console, use_gherkin)

    # Apply changes if requested
    if apply_changes and result.total_ac_generated > 0:
        console.section("Applying Changes")
        applied = _apply_ac(markdown_path, result, console)
        if applied:
            console.success(f"Added AC to {result.stories_with_new_ac} stories")
        else:
            console.error("Failed to apply AC changes")
            return ExitCode.ERROR

    return ExitCode.SUCCESS


def _format_text(result, console: Console, use_gherkin: bool) -> None:
    """Format AC generation results as human-readable text."""
    console.section("Generated Acceptance Criteria")
    console.print()

    # Summary
    console.print(f"  Stories processed: {len(result.suggestions)}")
    console.print(f"  {Colors.GREEN}Total AC generated: {result.total_ac_generated}{Colors.RESET}")
    console.print()

    # Per-story suggestions
    for suggestion in result.suggestions:
        # Story header
        console.print(
            f"  {Colors.BOLD}{suggestion.story_id}{Colors.RESET}: {suggestion.story_title}"
        )
        console.print(
            f"     Existing AC: {suggestion.current_ac_count} | "
            f"New AC: {Colors.GREEN}{suggestion.num_generated}{Colors.RESET}"
        )

        if suggestion.explanation:
            console.print(f"     {Colors.DIM}{suggestion.explanation}{Colors.RESET}")

        console.print()

        # Show generated AC
        for i, ac in enumerate(suggestion.generated_ac, 1):
            category_color = _get_category_color(ac.category.value)

            if use_gherkin and ac.is_gherkin:
                console.print(f"     {Colors.CYAN}{i}.{Colors.RESET} [{category_color}]")
                console.print(f"        {Colors.DIM}Given{Colors.RESET} {ac.given}")
                console.print(f"        {Colors.DIM}When{Colors.RESET} {ac.when}")
                console.print(f"        {Colors.DIM}Then{Colors.RESET} {ac.then}")
            else:
                console.print(f"     {Colors.CYAN}{i}.{Colors.RESET} [{category_color}] {ac.text}")

        # Missing categories
        if suggestion.has_missing_categories:
            missing = [c.value for c in suggestion.has_missing_categories]
            console.print(
                f"     {Colors.YELLOW}Note: Consider adding {', '.join(missing)} AC{Colors.RESET}"
            )

        console.print()

    # Next steps
    console.section("Next Steps")
    console.item("Review the generated acceptance criteria")
    console.item("Apply changes: spectra --generate-ac -f FILE --apply-ac")
    console.item("Or copy the AC to your story files manually")


def _get_category_color(category: str) -> str:
    """Get colored category label."""
    colors = {
        "functional": f"{Colors.GREEN}functional{Colors.RESET}",
        "validation": f"{Colors.YELLOW}validation{Colors.RESET}",
        "error_handling": f"{Colors.RED}error{Colors.RESET}",
        "edge_case": f"{Colors.MAGENTA}edge{Colors.RESET}",
        "security": f"{Colors.RED}security{Colors.RESET}",
        "performance": f"{Colors.CYAN}perf{Colors.RESET}",
        "accessibility": f"{Colors.BLUE}a11y{Colors.RESET}",
        "ux": f"{Colors.BLUE}ux{Colors.RESET}",
    }
    return colors.get(category, category)


def _format_json(result) -> str:
    """Format AC generation results as JSON."""
    data = {
        "success": result.success,
        "total_ac_generated": result.total_ac_generated,
        "stories_with_new_ac": result.stories_with_new_ac,
        "provider": result.provider_used,
        "model": result.model_used,
        "tokens_used": result.tokens_used,
        "suggestions": [
            {
                "story_id": s.story_id,
                "story_title": s.story_title,
                "current_ac_count": s.current_ac_count,
                "num_generated": s.num_generated,
                "explanation": s.explanation,
                "generated_ac": [
                    {
                        "text": ac.text,
                        "category": ac.category.value,
                        "is_gherkin": ac.is_gherkin,
                        "given": ac.given if ac.is_gherkin else None,
                        "when": ac.when if ac.is_gherkin else None,
                        "then": ac.then if ac.is_gherkin else None,
                    }
                    for ac in s.generated_ac
                ],
                "missing_categories": [c.value for c in s.has_missing_categories],
            }
            for s in result.suggestions
        ],
    }
    return json.dumps(data, indent=2)


def _format_yaml(result) -> str:
    """Format AC generation results as YAML."""
    try:
        import yaml

        data = {
            "total_ac_generated": result.total_ac_generated,
            "suggestions": [
                {
                    "story_id": s.story_id,
                    "acceptance_criteria": [ac.text for ac in s.generated_ac],
                }
                for s in result.suggestions
            ],
        }
        return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    except ImportError:
        return _format_json(result)


def _format_markdown(result) -> str:
    """Format AC generation results as markdown."""
    lines = ["# Generated Acceptance Criteria", ""]

    for suggestion in result.suggestions:
        lines.append(f"## {suggestion.story_id}: {suggestion.story_title}")
        lines.append("")

        if suggestion.explanation:
            lines.append(f"> {suggestion.explanation}")
            lines.append("")

        lines.append("### Acceptance Criteria")
        lines.append("")

        for ac in suggestion.generated_ac:
            if ac.is_gherkin and ac.given and ac.when and ac.then:
                lines.append(f"- [ ] **{ac.category.value.title()}**")
                lines.append(f"  - Given {ac.given}")
                lines.append(f"  - When {ac.when}")
                lines.append(f"  - Then {ac.then}")
            else:
                lines.append(f"- [ ] {ac.text}")

        lines.append("")

    return "\n".join(lines)


def _apply_ac(
    markdown_path: str,
    result,
    console: Console,
) -> bool:
    """Apply generated AC to the markdown file."""
    import re as regex

    try:
        content = Path(markdown_path).read_text(encoding="utf-8")
        updated_content = content

        for suggestion in result.suggestions:
            if not suggestion.generated_ac:
                continue

            # Find the story section
            story_pattern = (
                rf"(###[^\n]*{regex.escape(suggestion.story_id)}[^\n]*\n[\s\S]*?)(?=###|\Z)"
            )
            story_match = regex.search(story_pattern, updated_content)

            if not story_match:
                continue

            story_section = story_match.group(0)

            # Check if AC section exists
            ac_section_pattern = r"(####\s*Acceptance Criteria[^\n]*\n)([\s\S]*?)(?=####|\Z)"
            ac_match = regex.search(ac_section_pattern, story_section)

            # Generate new AC text
            new_ac_lines = []
            for ac in suggestion.generated_ac:
                new_ac_lines.append(f"- [ ] {ac.text}")
            new_ac_text = "\n".join(new_ac_lines)

            if ac_match:
                # Append to existing AC section
                existing_ac = ac_match.group(2).rstrip()
                if existing_ac:
                    new_section = ac_match.group(1) + existing_ac + "\n" + new_ac_text + "\n\n"
                else:
                    new_section = ac_match.group(1) + "\n" + new_ac_text + "\n\n"

                updated_story = story_section.replace(ac_match.group(0), new_section)
            else:
                # Add new AC section before Technical Notes or at end
                tech_notes_pattern = r"(####\s*Technical Notes)"
                tech_match = regex.search(tech_notes_pattern, story_section)

                ac_section = f"\n#### Acceptance Criteria\n\n{new_ac_text}\n\n"

                if tech_match:
                    insert_pos = tech_match.start()
                    updated_story = (
                        story_section[:insert_pos] + ac_section + story_section[insert_pos:]
                    )
                else:
                    updated_story = story_section.rstrip() + "\n" + ac_section

            updated_content = updated_content.replace(story_section, updated_story)

        Path(markdown_path).write_text(updated_content, encoding="utf-8")
        return True

    except Exception as e:
        console.error(f"Failed to update file: {e}")
        return False
