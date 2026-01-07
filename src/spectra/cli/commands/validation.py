"""
Validation command handler.

This module contains the markdown validation command handler.
"""

from spectra.cli.output import Console


__all__ = ["validate_markdown"]


def validate_markdown(
    console: Console,
    markdown_path: str,
    strict: bool = False,
    show_guide: bool = False,
    suggest_fix: bool = False,
    auto_fix: bool = False,
    ai_tool: str | None = None,
    input_dir: str | None = None,
) -> int:
    """
    Validate a markdown file's format and structure.

    Performs comprehensive validation including structure checks,
    story content validation, and best practice suggestions.

    Args:
        console: Console instance for output.
        markdown_path: Path to the markdown file to validate.
        strict: If True, treat warnings as errors.
        show_guide: If True, show the format guide.
        suggest_fix: If True, generate an AI prompt to fix issues.
        auto_fix: If True, automatically fix using an AI tool.
        ai_tool: Specific AI tool to use for auto-fix.
        input_dir: Path to directory containing US-*.md files.

    Returns:
        Exit code (0 for success, non-zero for errors).
    """
    from spectra.cli.validate import run_validate

    return run_validate(
        console,
        markdown_path,
        strict=strict,
        show_guide=show_guide,
        suggest_fix=suggest_fix,
        auto_fix=auto_fix,
        ai_tool=ai_tool,
        input_dir=input_dir,
    )
