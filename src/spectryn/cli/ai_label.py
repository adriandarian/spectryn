"""
AI Labeling CLI - Command handler for suggesting story labels.

Uses LLM providers to analyze story content and suggest appropriate
labels and categories.
"""

import json
from pathlib import Path

from .exit_codes import ExitCode
from .output import Colors, Console, Symbols


def run_ai_label(
    console: Console,
    markdown_path: str | None = None,
    story_ids: list[str] | None = None,
    existing_labels: list[str] | None = None,
    suggest_features: bool = True,
    suggest_components: bool = True,
    suggest_types: bool = True,
    suggest_nfr: bool = True,
    max_labels: int = 5,
    allow_new: bool = True,
    label_style: str = "kebab-case",
    project_context: str | None = None,
    tech_stack: str | None = None,
    output_format: str = "text",
    apply_changes: bool = False,
) -> int:
    """
    Run the AI labeling command.

    Args:
        console: Console for output.
        markdown_path: Path to markdown file containing stories.
        story_ids: Optional list of specific story IDs to label.
        existing_labels: List of existing labels to prefer.
        suggest_features: Suggest feature area labels.
        suggest_components: Suggest component labels.
        suggest_types: Suggest work type labels.
        suggest_nfr: Suggest non-functional requirement labels.
        max_labels: Maximum labels per story.
        allow_new: Allow suggesting new labels.
        label_style: Label formatting style.
        project_context: Optional project context.
        tech_stack: Optional tech stack info.
        output_format: Output format (text, json, yaml).
        apply_changes: Apply suggested labels to the file.

    Returns:
        Exit code.
    """
    from spectryn.adapters import MarkdownParser
    from spectryn.application.ai_label import (
        AILabeler,
        LabelingOptions,
    )

    console.header(f"spectra AI Labeling {Symbols.TAG}")

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

    console.success(f"Found {len(stories)} stories to label")

    # Collect existing labels from all stories
    all_existing = set(existing_labels or [])
    for story in epic.stories:  # Use all stories for existing labels
        if story.labels:
            all_existing.update(story.labels)

    if all_existing:
        console.detail(f"Existing labels: {len(all_existing)}")

    # Show configuration
    console.section("Configuration")
    categories = []
    if suggest_features:
        categories.append("features")
    if suggest_components:
        categories.append("components")
    if suggest_types:
        categories.append("types")
    if suggest_nfr:
        categories.append("NFR")
    console.detail(f"Categories: {', '.join(categories)}")
    console.detail(f"Max labels per story: {max_labels}")
    console.detail(f"Label style: {label_style}")
    console.detail(f"Allow new labels: {'yes' if allow_new else 'no'}")

    # Create options
    options = LabelingOptions(
        existing_labels=sorted(all_existing),
        suggest_features=suggest_features,
        suggest_components=suggest_components,
        suggest_types=suggest_types,
        suggest_nfr=suggest_nfr,
        max_labels_per_story=max_labels,
        allow_new_labels=allow_new,
        prefer_existing_labels=True,
        label_style=label_style,
        project_context=project_context or "",
        tech_stack=tech_stack or "",
    )

    # Run labeling
    console.section("Analyzing Stories")
    console.info("Calling LLM provider for label suggestions...")

    labeler = AILabeler(options)
    result = labeler.label(stories, options)

    if not result.success:
        console.error(f"Labeling failed: {result.error}")
        return ExitCode.ERROR

    if not result.suggestions:
        console.warning("No labeling suggestions returned")
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
        _format_text(result, console)

    # Apply changes if requested
    if apply_changes and result.stories_with_changes > 0:
        console.section("Applying Changes")
        applied = _apply_labels(markdown_path, result, console)
        if applied:
            console.success(f"Updated labels for {result.stories_with_changes} stories")
        else:
            console.error("Failed to apply label changes")
            return ExitCode.ERROR

    return ExitCode.SUCCESS


def _format_text(result, console: Console) -> None:
    """Format labeling results as human-readable text."""
    console.section("Labeling Suggestions")
    console.print()

    # Summary
    console.print(f"  Stories analyzed: {len(result.suggestions)}")
    console.print(f"  Stories with changes: {result.stories_with_changes}")
    console.print(f"  Total unique labels: {len(result.all_labels_used)}")
    if result.new_labels_suggested:
        console.print(
            f"  {Colors.CYAN}New labels suggested: {len(result.new_labels_suggested)}{Colors.RESET}"
        )
    console.print()

    # Per-story suggestions
    for suggestion in result.suggestions:
        # Story header
        if suggestion.has_changes:
            status_icon = f"{Colors.YELLOW}●{Colors.RESET}"
        else:
            status_icon = f"{Colors.GREEN}✓{Colors.RESET}"

        console.print(
            f"  {status_icon} {Colors.BOLD}{suggestion.story_id}{Colors.RESET}: "
            f"{suggestion.story_title}"
        )

        # Current labels
        if suggestion.current_labels:
            current_str = ", ".join(f"`{l}`" for l in suggestion.current_labels)
            console.print(f"     Current: {current_str}")
        else:
            console.print(f"     Current: {Colors.DIM}(none){Colors.RESET}")

        # Labels to add
        if suggestion.labels_to_add:
            adds = []
            for label in suggestion.labels_to_add:
                is_new = any(sl.name == label and sl.is_new for sl in suggestion.suggested_labels)
                if is_new:
                    adds.append(f"{Colors.CYAN}`{label}`{Colors.RESET} (new)")
                else:
                    adds.append(f"{Colors.GREEN}`{label}`{Colors.RESET}")
            console.print(f"     {Colors.GREEN}+ Add:{Colors.RESET} {', '.join(adds)}")

        # Labels to remove
        if suggestion.labels_to_remove:
            removes = [f"{Colors.RED}`{l}`{Colors.RESET}" for l in suggestion.labels_to_remove]
            console.print(f"     {Colors.RED}- Remove:{Colors.RESET} {', '.join(removes)}")

        # Reasoning for top suggestions
        high_confidence = [sl for sl in suggestion.suggested_labels if sl.confidence == "high"]
        if high_confidence:
            console.print(f"     {Colors.DIM}Reasoning:{Colors.RESET}")
            for sl in high_confidence[:2]:
                console.print(f"       • {sl.name}: {sl.reasoning}")

        # Final labels
        if suggestion.has_changes:
            final = ", ".join(f"`{l}`" for l in suggestion.final_labels)
            console.print(f"     → Final: {final}")

        console.print()

    # New labels summary
    if result.new_labels_suggested:
        console.section("New Labels Suggested")
        for label in result.new_labels_suggested:
            console.print(f"  {Colors.CYAN}+ {label}{Colors.RESET}")
        console.print()

    # All labels
    console.section("All Labels")
    label_groups: dict[str, set[str]] = {}
    for s in result.suggestions:
        for sl in s.suggested_labels:
            cat = sl.category.value
            if cat not in label_groups:
                label_groups[cat] = set()
            label_groups[cat].add(sl.name)

    for cat, labels in sorted(label_groups.items()):
        console.print(f"  {Colors.BOLD}{cat}:{Colors.RESET} {', '.join(sorted(labels))}")
    console.print()

    # Next steps
    if result.stories_with_changes > 0:
        console.section("Next Steps")
        console.item("Review the suggested labels")
        console.item("Apply changes: spectra --label -f FILE --apply-labels")
        console.item("Or manually update labels in your markdown file")


def _format_json(result) -> str:
    """Format labeling results as JSON."""
    data = {
        "success": result.success,
        "stories_with_changes": result.stories_with_changes,
        "all_labels_used": result.all_labels_used,
        "new_labels_suggested": result.new_labels_suggested,
        "provider": result.provider_used,
        "model": result.model_used,
        "tokens_used": result.tokens_used,
        "suggestions": [
            {
                "story_id": s.story_id,
                "story_title": s.story_title,
                "current_labels": s.current_labels,
                "labels_to_add": s.labels_to_add,
                "labels_to_remove": s.labels_to_remove,
                "final_labels": s.final_labels,
                "has_changes": s.has_changes,
                "suggested_labels": [
                    {
                        "name": sl.name,
                        "category": sl.category.value,
                        "confidence": sl.confidence,
                        "reasoning": sl.reasoning,
                        "is_new": sl.is_new,
                    }
                    for sl in s.suggested_labels
                ],
            }
            for s in result.suggestions
        ],
    }
    return json.dumps(data, indent=2)


def _format_yaml(result) -> str:
    """Format labeling results as YAML."""
    try:
        import yaml

        data = {
            "stories_with_changes": result.stories_with_changes,
            "all_labels": result.all_labels_used,
            "new_labels": result.new_labels_suggested,
            "suggestions": [
                {
                    "story_id": s.story_id,
                    "current_labels": s.current_labels,
                    "labels_to_add": s.labels_to_add,
                    "labels_to_remove": s.labels_to_remove,
                    "final_labels": s.final_labels,
                }
                for s in result.suggestions
            ],
        }
        return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    except ImportError:
        return _format_json(result)


def _apply_labels(
    markdown_path: str,
    result,
    console: Console,
) -> bool:
    """Apply suggested labels to the markdown file."""
    import re

    try:
        content = Path(markdown_path).read_text(encoding="utf-8")
        updated_content = content

        for suggestion in result.suggestions:
            if not suggestion.has_changes:
                continue

            # Find the story section
            story_pattern = (
                rf"(###[^\n]*{re.escape(suggestion.story_id)}[^\n]*\n[\s\S]*?)(?=###|\Z)"
            )
            story_match = re.search(story_pattern, updated_content)

            if not story_match:
                continue

            story_section = story_match.group(0)

            # Check if Labels row exists in metadata table
            labels_pattern = r"(\|\s*\*\*Labels\*\*\s*\|\s*)([^|]*)(\s*\|)"
            labels_match = re.search(labels_pattern, story_section)

            final_labels_str = ", ".join(suggestion.final_labels)

            if labels_match:
                # Update existing Labels row
                updated_section = re.sub(
                    labels_pattern,
                    rf"\g<1>{final_labels_str}\g<3>",
                    story_section,
                    count=1,
                )
            else:
                # Try to add Labels row after Status or Priority row
                table_row_pattern = r"(\|\s*\*\*(?:Status|Priority)\*\*\s*\|[^|]*\|)"
                row_match = re.search(table_row_pattern, story_section)

                if row_match:
                    new_row = f"\n| **Labels** | {final_labels_str} |"
                    insert_pos = row_match.end()
                    updated_section = (
                        story_section[:insert_pos] + new_row + story_section[insert_pos:]
                    )
                else:
                    # Can't find where to insert, skip this story
                    continue

            updated_content = updated_content.replace(story_section, updated_section)

        Path(markdown_path).write_text(updated_content, encoding="utf-8")
        return True

    except Exception as e:
        console.error(f"Failed to update file: {e}")
        return False
