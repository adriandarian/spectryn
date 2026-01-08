"""
Plugin Scaffold CLI - Commands for scaffolding new plugins.

Provides interactive and non-interactive ways to create new plugin projects
from templates.
"""

from pathlib import Path

from .exit_codes import ExitCode
from .output import Console, Symbols


def run_plugin_scaffold(
    console: Console,
    name: str | None = None,
    description: str | None = None,
    template_type: str | None = None,
    output_dir: str | None = None,
    author_name: str | None = None,
    author_email: str | None = None,
    include_tests: bool = True,
    include_docs: bool = True,
    include_ci: bool = True,
    interactive: bool = False,
) -> int:
    """
    Scaffold a new plugin project.

    Args:
        console: Console instance for output
        name: Plugin name
        description: Plugin description
        template_type: Type of plugin (parser, tracker, formatter, hook, command)
        output_dir: Output directory
        author_name: Author name
        author_email: Author email
        include_tests: Include test suite
        include_docs: Include documentation
        include_ci: Include CI configuration
        interactive: Run in interactive mode

    Returns:
        Exit code
    """
    from spectryn.plugins.templates import PluginScaffold, PluginTemplateType
    from spectryn.plugins.templates.scaffold import PluginScaffoldConfig

    console.info(f"{Symbols.WIZARD} Plugin Scaffold Generator\n")

    # Interactive mode
    if interactive or not all([name, description, template_type, author_name]):
        result = _run_interactive_scaffold(console)
        if result is None:
            console.print("Scaffold cancelled.")
            return ExitCode.SUCCESS
        name, description, template_type, output_dir, author_name, author_email = result

    # Validate required fields
    if not name:
        console.error("Plugin name is required. Use --name or run with --interactive.")
        return ExitCode.ERROR

    if not description:
        console.error(
            "Plugin description is required. Use --description or run with --interactive."
        )
        return ExitCode.ERROR

    if not template_type:
        console.error("Plugin type is required. Use --type or run with --interactive.")
        return ExitCode.ERROR

    if not author_name:
        console.error("Author name is required. Use --author or run with --interactive.")
        return ExitCode.ERROR

    # Parse template type
    try:
        plugin_type = PluginTemplateType[template_type.upper()]
    except KeyError:
        console.error(f"Invalid plugin type: {template_type}")
        console.print("Valid types: parser, tracker, formatter, hook, command")
        return ExitCode.ERROR

    # Set output directory
    out_path = Path(output_dir) if output_dir else Path.cwd()

    try:
        config = PluginScaffoldConfig(
            name=name,
            description=description,
            template_type=plugin_type,
            author_name=author_name,
            author_email=author_email,
            include_tests=include_tests,
            include_docs=include_docs,
            include_ci=include_ci,
        )

        scaffold = PluginScaffold(config)
        console.info(f"Creating plugin: spectra-{name}")
        console.info(f"Type: {plugin_type.name.lower()}")
        console.info(f"Output: {out_path}/spectra-{name}\n")

        created_files = scaffold.generate(out_path)

        console.success(f"\n{Symbols.SUCCESS} Plugin scaffolded successfully!")
        console.print(f"\nCreated {len(created_files)} files in spectra-{name}/")

        # Show next steps
        console.print(f"\n{Symbols.INFO} Next steps:")
        console.print(f"  1. cd spectra-{name}")
        console.print("  2. pip install -e '.[dev]'")
        console.print("  3. Implement your plugin logic")
        console.print("  4. Run tests: pytest")
        console.print("  5. Publish: spectra plugin publish .")

        return ExitCode.SUCCESS

    except ValueError as e:
        console.error(f"Configuration error: {e}")
        return ExitCode.ERROR
    except Exception as e:
        console.error(f"Scaffold failed: {e}")
        return ExitCode.ERROR


def _run_interactive_scaffold(
    console: Console,
) -> tuple[str, str, str, str, str, str | None] | None:
    """
    Run interactive scaffold wizard.

    Returns:
        Tuple of (name, description, type, output_dir, author_name, author_email)
        or None if cancelled
    """
    console.print("This wizard will help you create a new spectra plugin.\n")

    # Plugin name
    console.print(f"{Symbols.BULLET} Plugin name (lowercase, e.g., 'my_tracker'):")
    try:
        name = input("  > ").strip().lower().replace("-", "_")
        if not name:
            return None
    except (EOFError, KeyboardInterrupt):
        return None

    # Description
    console.print(f"\n{Symbols.BULLET} Description:")
    try:
        description = input("  > ").strip()
        if not description:
            description = f"A spectra plugin for {name}"
    except (EOFError, KeyboardInterrupt):
        return None

    # Plugin type
    console.print(f"\n{Symbols.BULLET} Plugin type:")
    console.print("  1. parser    - Parse new document formats")
    console.print("  2. tracker   - Integrate with issue trackers")
    console.print("  3. formatter - Format output documents")
    console.print("  4. hook      - Add processing hooks")
    console.print("  5. command   - Add CLI commands")

    try:
        type_input = input("  > ").strip()
        type_map = {
            "1": "parser",
            "parser": "parser",
            "2": "tracker",
            "tracker": "tracker",
            "3": "formatter",
            "formatter": "formatter",
            "4": "hook",
            "hook": "hook",
            "5": "command",
            "command": "command",
        }
        plugin_type = type_map.get(type_input, "hook")
    except (EOFError, KeyboardInterrupt):
        return None

    # Output directory
    console.print(f"\n{Symbols.BULLET} Output directory (default: current directory):")
    try:
        output_dir = input("  > ").strip() or "."
    except (EOFError, KeyboardInterrupt):
        return None

    # Author name
    console.print(f"\n{Symbols.BULLET} Author name:")
    try:
        author_name = input("  > ").strip()
        if not author_name:
            author_name = "Anonymous"
    except (EOFError, KeyboardInterrupt):
        return None

    # Author email (optional)
    console.print(f"\n{Symbols.BULLET} Author email (optional):")
    try:
        author_email = input("  > ").strip() or None
    except (EOFError, KeyboardInterrupt):
        return None

    # Confirm
    console.print(f"\n{Symbols.INFO} Summary:")
    console.print(f"  Name:        spectra-{name}")
    console.print(f"  Description: {description}")
    console.print(f"  Type:        {plugin_type}")
    console.print(f"  Output:      {output_dir}/spectra-{name}")
    console.print(f"  Author:      {author_name}")

    console.print(f"\n{Symbols.BULLET} Create plugin? [Y/n]")
    try:
        confirm = input("  > ").strip().lower()
        if confirm and confirm not in ("y", "yes"):
            return None
    except (EOFError, KeyboardInterrupt):
        return None

    return (name, description, plugin_type, output_dir, author_name, author_email)


def run_list_templates(console: Console) -> int:
    """
    List available plugin templates.

    Args:
        console: Console instance

    Returns:
        Exit code
    """
    from spectryn.plugins.templates import PluginTemplateType

    console.info(f"{Symbols.PACKAGE} Available Plugin Templates\n")

    templates = [
        (PluginTemplateType.PARSER, "Document Parser", "Parse new input formats (JSON, XML, etc.)"),
        (PluginTemplateType.TRACKER, "Issue Tracker", "Integrate with issue tracking systems"),
        (PluginTemplateType.FORMATTER, "Output Formatter", "Format output for different targets"),
        (PluginTemplateType.HOOK, "Processing Hook", "Add pre/post processing hooks"),
        (PluginTemplateType.COMMAND, "CLI Command", "Add custom CLI commands"),
    ]

    for template_type, name, description in templates:
        console.print(f"  {Symbols.BULLET} {template_type.name.lower()}")
        console.print(f"    {name}")
        console.print(f"    {description}")
        console.print("")

    console.print("Use `spectra plugin new --type <template>` to create a new plugin.")

    return ExitCode.SUCCESS
