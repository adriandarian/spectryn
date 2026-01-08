"""
AI Story Generation CLI - Command handler for generating stories from descriptions.

Uses LLM providers to transform high-level feature descriptions into
properly formatted user stories.
"""

import json
from pathlib import Path

from .exit_codes import ExitCode
from .output import Console, Symbols


def run_ai_generate(
    console: Console,
    description: str | None = None,
    description_file: str | None = None,
    style: str = "standard",
    max_stories: int = 5,
    story_prefix: str = "US",
    project_context: str | None = None,
    tech_stack: str | None = None,
    output_file: str | None = None,
    output_format: str = "text",
    dry_run: bool = True,
) -> int:
    """
    Run the AI story generation command.

    Args:
        console: Console for output.
        description: High-level feature description text.
        description_file: Path to file containing description.
        style: Generation style (detailed, standard, minimal).
        max_stories: Maximum stories to generate.
        story_prefix: Story ID prefix (e.g., US, STORY).
        project_context: Optional project context.
        tech_stack: Optional tech stack info.
        output_file: Path to save generated stories.
        output_format: Output format (text, json, yaml, markdown).
        dry_run: If True, don't write to files.

    Returns:
        Exit code.
    """
    from spectryn.application.ai_generate import (
        AIStoryGenerator,
        GenerationOptions,
        GenerationStyle,
    )

    console.header(f"spectra AI Story Generation {Symbols.SPARKLES}")

    # Get description from file or argument
    if description_file:
        try:
            description_text = Path(description_file).read_text(encoding="utf-8")
            console.info(f"Reading description from: {description_file}")
        except FileNotFoundError:
            console.error(f"Description file not found: {description_file}")
            return ExitCode.CONFIG_ERROR
        except Exception as e:
            console.error(f"Failed to read description file: {e}")
            return ExitCode.ERROR
    elif description:
        description_text = description
    else:
        console.error("No description provided. Use --description or --description-file")
        console.info("Example: spectra --generate-stories --description 'Build a user dashboard'")
        return ExitCode.CONFIG_ERROR

    if not description_text.strip():
        console.error("Description is empty")
        return ExitCode.CONFIG_ERROR

    # Show configuration
    console.section("Configuration")
    console.detail(f"Style: {style}")
    console.detail(f"Max stories: {max_stories}")
    console.detail(f"Story prefix: {story_prefix}")
    if project_context:
        console.detail(f"Project context: {project_context[:50]}...")
    if tech_stack:
        console.detail(f"Tech stack: {tech_stack}")

    # Show description preview
    console.section("Description")
    preview = description_text[:200] + "..." if len(description_text) > 200 else description_text
    console.print(f"  {preview}")
    console.print()

    # Create options
    try:
        gen_style = GenerationStyle(style)
    except ValueError:
        console.error(f"Invalid generation style: {style}")
        console.info("Valid styles: detailed, standard, minimal")
        return ExitCode.CONFIG_ERROR

    options = GenerationOptions(
        style=gen_style,
        max_stories=max_stories,
        story_prefix=story_prefix,
        project_context=project_context or "",
        tech_stack=tech_stack or "",
        include_subtasks=style in ("detailed", "standard"),
        include_acceptance_criteria=True,
        include_technical_notes=style == "detailed",
        include_story_points=True,
    )

    # Generate stories
    console.section("Generating Stories")
    console.info("Calling LLM provider...")

    generator = AIStoryGenerator(options)
    result = generator.generate(description_text, options)

    if not result.success:
        console.error(f"Generation failed: {result.error}")
        return ExitCode.ERROR

    if not result.stories:
        console.warning("No stories were generated")
        return ExitCode.SUCCESS

    # Show generation info
    console.success(f"Generated {len(result.stories)} stories")
    console.detail(f"Provider: {result.provider_used}")
    console.detail(f"Model: {result.model_used}")
    if result.tokens_used > 0:
        console.detail(f"Tokens used: {result.tokens_used}")

    # Output based on format
    console.section("Generated Stories")

    if output_format == "json":
        output = _format_json(result.stories)
    elif output_format == "yaml":
        output = _format_yaml(result.stories)
    elif output_format == "markdown":
        output = _format_markdown(result.stories)
    else:
        output = _format_text(result.stories, console)

    # Handle output
    if output_file:
        if dry_run:
            console.dry_run_banner()
            console.info(f"Would write to: {output_file}")
            console.print()
            console.print(output)
        else:
            try:
                Path(output_file).write_text(output, encoding="utf-8")
                console.success(f"Written to: {output_file}")
            except Exception as e:
                console.error(f"Failed to write output file: {e}")
                return ExitCode.ERROR
    else:
        console.print()
        console.print(output)

    # Show next steps
    console.print()
    console.section("Next Steps")
    if output_file and not dry_run:
        console.item(f"Review and refine stories in {output_file}")
        console.item(f"Sync to tracker: spectra -f {output_file} -e YOUR-EPIC --execute")
    else:
        console.item("Copy the generated stories to your markdown file")
        console.item("Review and refine the stories")
        console.item("Sync to tracker: spectra -f EPIC.md -e YOUR-EPIC --execute")

    return ExitCode.SUCCESS


def _format_text(stories: list, console: Console) -> str:
    """Format stories as human-readable text."""
    lines = []

    for story in stories:
        lines.append(f"{Symbols.STORY} {story.id}: {story.title}")
        lines.append(f"   Priority: {story.priority.display_name} | Points: {story.story_points}")

        if story.description:
            lines.append(f"   As a {story.description.role}")
            lines.append(f"   I want {story.description.want}")
            lines.append(f"   So that {story.description.benefit}")

        if story.acceptance_criteria and len(story.acceptance_criteria) > 0:
            lines.append("   Acceptance Criteria:")
            for ac, _ in story.acceptance_criteria:
                lines.append(f"     - {ac}")

        if story.subtasks:
            lines.append("   Subtasks:")
            for subtask in story.subtasks:
                lines.append(f"     - {subtask.name} ({subtask.story_points} SP)")

        lines.append("")

    return "\n".join(lines)


def _format_json(stories: list) -> str:
    """Format stories as JSON."""
    data = {"stories": [story.to_dict() for story in stories]}
    return json.dumps(data, indent=2)


def _format_yaml(stories: list) -> str:
    """Format stories as YAML."""
    try:
        import yaml

        data = {"stories": [story.to_dict() for story in stories]}
        return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    except ImportError:
        # Fallback to simple YAML-like format
        lines = ["stories:"]
        for story in stories:
            lines.append(f"  - id: {story.id}")
            lines.append(f"    title: {story.title}")
            lines.append(f"    story_points: {story.story_points}")
            lines.append(f"    priority: {story.priority.name}")
            if story.description:
                lines.append("    description:")
                lines.append(f"      role: {story.description.role}")
                lines.append(f"      want: {story.description.want}")
                lines.append(f"      benefit: {story.description.benefit}")
            lines.append("")
        return "\n".join(lines)


def _format_markdown(stories: list) -> str:
    """Format stories as markdown."""
    from spectryn.adapters.formatters.markdown_writer import MarkdownWriter

    writer = MarkdownWriter(
        include_epic_header=False,
        include_metadata=True,
        include_subtasks=True,
        include_commits=False,
        include_technical_notes=True,
    )

    return writer.write_stories(stories)
