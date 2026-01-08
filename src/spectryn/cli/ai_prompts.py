"""
AI Prompts CLI - Command handler for managing custom prompts.

Provides commands to list, view, create, and export AI prompts.
"""

import json
from pathlib import Path

from .exit_codes import ExitCode
from .output import Colors, Console, Symbols


def run_ai_prompts(
    console: Console,
    action: str = "list",
    prompt_name: str | None = None,
    prompt_type: str | None = None,
    config_path: str | None = None,
    export_path: str | None = None,
    output_format: str = "text",
) -> int:
    """
    Run the AI prompts management command.

    Args:
        console: Console for output.
        action: Action to perform (list, view, export, init).
        prompt_name: Name of specific prompt.
        prompt_type: Type of prompt to filter by.
        config_path: Path to prompts config file.
        export_path: Path to export prompts to.
        output_format: Output format (text, json, yaml).

    Returns:
        Exit code.
    """
    from spectryn.application.ai_prompts import (
        PromptManager,
        get_prompt_manager,
        set_prompt_manager,
    )

    console.header(f"spectra Prompt Manager {Symbols.GEAR}")

    # Initialize manager with config if provided
    if config_path:
        manager = PromptManager(config_path=config_path)
        set_prompt_manager(manager)
    else:
        manager = get_prompt_manager()

    # Handle actions
    if action == "list":
        return _list_prompts(console, manager, prompt_type, output_format)
    if action == "view":
        return _view_prompt(console, manager, prompt_name, prompt_type, output_format)
    if action == "export":
        return _export_prompts(console, manager, export_path or "spectra-prompts.json")
    if action == "init":
        return _init_prompts(console, manager, export_path or ".spectra-prompts.json")
    if action == "types":
        return _list_types(console, output_format)
    console.error(f"Unknown action: {action}")
    return ExitCode.CONFIG_ERROR


def _list_prompts(
    console: Console,
    manager,
    prompt_type: str | None,
    output_format: str,
) -> int:
    """List available prompts."""
    from spectryn.application.ai_prompts import PromptType

    # Filter by type if specified
    ptype = None
    if prompt_type:
        try:
            ptype = PromptType(prompt_type)
        except ValueError:
            console.error(f"Unknown prompt type: {prompt_type}")
            return ExitCode.CONFIG_ERROR

    prompts = manager.list_prompts(ptype, include_defaults=True)

    if output_format == "json":
        data = [p.to_dict() for p in prompts]
        print(json.dumps(data, indent=2))
        return ExitCode.SUCCESS

    console.section("Available Prompts")
    console.print()

    if not prompts:
        console.info("No prompts found")
        return ExitCode.SUCCESS

    # Group by type
    by_type: dict[str, list] = {}
    for prompt in prompts:
        type_name = prompt.prompt_type.value
        if type_name not in by_type:
            by_type[type_name] = []
        by_type[type_name].append(prompt)

    for type_name, type_prompts in sorted(by_type.items()):
        console.print(f"  {Colors.BOLD}{type_name}{Colors.RESET}")
        for prompt in type_prompts:
            is_default = prompt.name.startswith("default_")
            tag = (
                f"{Colors.DIM}(default){Colors.RESET}"
                if is_default
                else f"{Colors.GREEN}(custom){Colors.RESET}"
            )
            console.print(f"    • {prompt.name} {tag}")
            if prompt.description:
                console.print(f"      {Colors.DIM}{prompt.description}{Colors.RESET}")
        console.print()

    console.detail(f"Total: {len(prompts)} prompts")

    return ExitCode.SUCCESS


def _view_prompt(
    console: Console,
    manager,
    prompt_name: str | None,
    prompt_type: str | None,
    output_format: str,
) -> int:
    """View a specific prompt."""
    from spectryn.application.ai_prompts import PromptType

    ptype = None
    if prompt_type:
        try:
            ptype = PromptType(prompt_type)
        except ValueError:
            console.error(f"Unknown prompt type: {prompt_type}")
            return ExitCode.CONFIG_ERROR

    if not prompt_name and not ptype:
        console.error("Specify --prompt-name or --prompt-type to view a prompt")
        return ExitCode.CONFIG_ERROR

    prompt = manager.get_prompt(ptype or PromptType.CUSTOM, prompt_name)

    if not prompt or not prompt.system_prompt:
        console.error(f"Prompt not found: {prompt_name or prompt_type}")
        return ExitCode.ERROR

    if output_format == "json":
        print(json.dumps(prompt.to_dict(), indent=2))
        return ExitCode.SUCCESS

    console.section(f"Prompt: {prompt.name}")
    console.print()

    console.print(f"  {Colors.BOLD}Type:{Colors.RESET} {prompt.prompt_type.value}")
    console.print(f"  {Colors.BOLD}Version:{Colors.RESET} {prompt.version}")
    if prompt.description:
        console.print(f"  {Colors.BOLD}Description:{Colors.RESET} {prompt.description}")
    if prompt.tags:
        console.print(f"  {Colors.BOLD}Tags:{Colors.RESET} {', '.join(prompt.tags)}")
    console.print()

    # Variables
    if prompt.variables:
        console.section("Variables")
        for var in prompt.variables:
            req = f"{Colors.RED}*{Colors.RESET}" if var.required else ""
            console.print(f"  ${var.name}{req}: {var.description}")
            if var.default:
                console.print(f"    Default: {Colors.DIM}{var.default}{Colors.RESET}")
            if var.example:
                console.print(f"    Example: {Colors.DIM}{var.example}{Colors.RESET}")
        console.print()

    # System prompt
    console.section("System Prompt")
    console.print()
    for line in prompt.system_prompt.split("\n"):
        console.print(f"  {Colors.DIM}{line}{Colors.RESET}")
    console.print()

    # User prompt
    console.section("User Prompt")
    console.print()
    for line in prompt.user_prompt.split("\n")[:20]:  # Limit to 20 lines
        console.print(f"  {Colors.DIM}{line}{Colors.RESET}")
    if len(prompt.user_prompt.split("\n")) > 20:
        console.print(f"  {Colors.DIM}... (truncated){Colors.RESET}")
    console.print()

    return ExitCode.SUCCESS


def _export_prompts(console: Console, manager, path: str) -> int:
    """Export default prompts for customization."""
    console.section("Exporting Prompts")

    if manager.export_defaults(path):
        console.success(f"Exported default prompts to {path}")
        console.print()
        console.info("Edit this file to customize prompts, then use:")
        console.print(f"  spectra --prompts-config {path} <command>")
        return ExitCode.SUCCESS
    console.error("Failed to export prompts")
    return ExitCode.ERROR


def _init_prompts(console: Console, manager, path: str) -> int:
    """Initialize a prompts config file."""

    console.section("Initializing Prompts Config")

    if Path(path).exists():
        console.warning(f"File already exists: {path}")
        console.info("Use --export to overwrite with defaults")
        return ExitCode.CONFIG_ERROR

    # Create minimal config
    data = {
        "use_defaults": True,
        "prompts": {
            "my_custom_prompt": {
                "name": "my_custom_prompt",
                "prompt_type": "custom",
                "description": "Example custom prompt",
                "system_prompt": "You are an AI assistant.",
                "user_prompt": "Help with: $task",
                "variables": [
                    {
                        "name": "task",
                        "description": "The task to help with",
                        "required": True,
                    }
                ],
                "version": "1.0",
            }
        },
    }

    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        console.success(f"Created prompts config: {path}")
        console.print()
        console.info("Next steps:")
        console.item("Edit the file to add your custom prompts")
        console.item(f"Use: spectra --prompts-config {path} <command>")
        return ExitCode.SUCCESS
    except Exception as e:
        console.error(f"Failed to create config: {e}")
        return ExitCode.ERROR


def _list_types(console: Console, output_format: str) -> int:
    """List available prompt types."""
    from spectryn.application.ai_prompts import PromptType

    types = [{"value": t.value, "name": t.name} for t in PromptType]

    if output_format == "json":
        print(json.dumps(types, indent=2))
        return ExitCode.SUCCESS

    console.section("Available Prompt Types")
    console.print()

    for t in PromptType:
        console.print(f"  • {Colors.BOLD}{t.value}{Colors.RESET}")

    console.print()
    return ExitCode.SUCCESS
