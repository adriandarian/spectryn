"""
Field-related command handlers.

This module contains handlers for field-related commands:
- run_list_custom_fields: List available custom fields
- run_generate_field_mapping: Generate field mapping template
- run_list_sprints: List available sprints
"""

from pathlib import Path

from spectra.adapters import EnvironmentConfigProvider, JiraAdapter
from spectra.cli.exit_codes import ExitCode
from spectra.cli.output import Console, Symbols


__all__ = [
    "run_generate_field_mapping",
    "run_list_custom_fields",
    "run_list_sprints",
]


def run_list_custom_fields(args) -> int:
    """
    List available custom fields from the tracker.

    Connects to the tracker and retrieves all custom fields,
    displaying their IDs, names, and types.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code.
    """
    console = Console(verbose=args.verbose)

    console.header("Custom Fields Discovery")

    # Load config and create adapter
    config_provider = EnvironmentConfigProvider()
    try:
        tracker_config = config_provider.get_tracker_config()
    except Exception as e:
        console.error(f"Failed to load configuration: {e}")
        return ExitCode.CONFIG_ERROR

    adapter = JiraAdapter(tracker_config, dry_run=True)

    # Test connection
    if not adapter.test_connection():
        console.error("Failed to connect to Jira")
        return ExitCode.CONNECTION_ERROR

    console.info("Connected to Jira")
    console.print()

    # Get custom fields from Jira
    try:
        fields = adapter._client.get("field")
        if not isinstance(fields, list):
            console.error("Unexpected response from Jira")
            return ExitCode.ERROR

        # Filter to custom fields
        custom_fields = [f for f in fields if f.get("custom", False)]

        console.section(f"Custom Fields ({len(custom_fields)} found)")
        console.print()

        # Group by schema type
        by_type: dict[str, list] = {}
        for field in custom_fields:
            schema = field.get("schema", {})
            field_type = schema.get("type", "unknown")
            if field_type not in by_type:
                by_type[field_type] = []
            by_type[field_type].append(field)

        for field_type, type_fields in sorted(by_type.items()):
            console.info(f"{Symbols.BULLET} {field_type.upper()} fields:")
            for field in type_fields:
                field_id = field.get("id", "")
                field_name = field.get("name", "")
                console.print(f"    {field_id}: {field_name}")
            console.print()

        # Show common field mappings
        console.section("Common Field Usage")
        common = [
            ("Story Points", "customfield_10014", "story_points_field"),
            ("Sprint", "customfield_10020", "sprint_field"),
            ("Epic Link", "customfield_10008", "epic_link_field"),
        ]
        for name, default_id, cli_arg in common:
            matches = [f for f in custom_fields if name.lower() in f.get("name", "").lower()]
            if matches:
                field = matches[0]
                console.info(f"{name}: {field.get('id')} (--{cli_arg.replace('_', '-')})")
            else:
                console.warning(f"{name}: Not found (default: {default_id})")

    except Exception as e:
        console.error(f"Failed to retrieve fields: {e}")
        return ExitCode.ERROR

    return ExitCode.SUCCESS


def run_generate_field_mapping(args) -> int:
    """
    Generate a field mapping template YAML file.

    Creates a sample field mapping configuration that can be customized.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code.
    """
    from spectra.application.sync.field_mapping import (
        FieldDefinition,
        FieldMappingLoader,
        FieldType,
        FieldValueMapping,
        TrackerFieldMappingConfig,
    )

    console = Console(verbose=args.verbose)

    output_path = Path(args.generate_field_mapping)

    console.header("Generate Field Mapping Template")

    # Create sample configuration
    config = TrackerFieldMappingConfig(
        tracker_type="jira",
        project_key="PROJ",
        story_points_field="customfield_10014",
        priority_field="priority",
        status_field="status",
        assignee_field="assignee",
        labels_field="labels",
        due_date_field="duedate",
        sprint_field="customfield_10020",
        status_mapping={
            "Planned": "To Do",
            "Open": "To Do",
            "In Progress": "In Progress",
            "Done": "Done",
            "Blocked": "On Hold",
        },
        priority_mapping={
            "Critical": "Highest",
            "High": "High",
            "Medium": "Medium",
            "Low": "Low",
        },
        custom_fields=[
            FieldDefinition(
                name="team",
                markdown_name="Team",
                tracker_field_id="customfield_10050",
                tracker_field_name="Team",
                description="Development team assignment",
                field_type=FieldType.DROPDOWN,
                value_mappings=[
                    FieldValueMapping(
                        markdown_value="Backend",
                        tracker_value="10001",
                        aliases=["BE", "Server"],
                    ),
                    FieldValueMapping(
                        markdown_value="Frontend",
                        tracker_value="10002",
                        aliases=["FE", "UI"],
                    ),
                ],
            ),
            FieldDefinition(
                name="target_release",
                markdown_name="Target Release",
                tracker_field_id="customfield_10060",
                tracker_field_name="Target Release",
                description="Target release version",
                field_type=FieldType.TEXT,
                required=True,
                pattern=r"^v\d+\.\d+\.\d+$",
            ),
            FieldDefinition(
                name="business_value",
                markdown_name="Business Value",
                tracker_field_id="customfield_10070",
                tracker_field_name="Business Value",
                description="Business value score",
                field_type=FieldType.NUMBER,
                min_value=1,
                max_value=100,
            ),
        ],
    )

    try:
        FieldMappingLoader.save_to_yaml(config, output_path)
        console.success(f"Generated field mapping template: {output_path}")
        console.print()
        console.info("Edit this file to customize field mappings for your project.")
        console.info("Use with: spectra --field-mapping field_mapping.yaml ...")
    except Exception as e:
        console.error(f"Failed to write file: {e}")
        return ExitCode.ERROR

    return ExitCode.SUCCESS


def run_list_sprints(args) -> int:
    """
    List available sprints from the tracker.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code.
    """
    from spectra.application.sync.sprint_sync import Sprint, SprintState

    console = Console(verbose=args.verbose)

    console.header("Available Sprints")

    # Load config and create adapter
    config_provider = EnvironmentConfigProvider()
    try:
        tracker_config = config_provider.get_tracker_config()
    except Exception as e:
        console.error(f"Failed to load configuration: {e}")
        return ExitCode.CONFIG_ERROR

    adapter = JiraAdapter(tracker_config, dry_run=True)

    # Test connection
    if not adapter.test_connection():
        console.error("Failed to connect to Jira")
        return ExitCode.CONNECTION_ERROR

    console.info("Connected to Jira")
    console.print()

    # Get sprints
    board_id = args.sprint_board if hasattr(args, "sprint_board") else None

    try:
        raw_sprints = adapter.get_sprints(board_id=board_id)

        if not raw_sprints:
            console.warning("No sprints found")
            return ExitCode.SUCCESS

        sprints = [Sprint.from_jira_sprint(s) for s in raw_sprints]

        # Group by state
        by_state: dict[SprintState, list[Sprint]] = {}
        for sprint in sprints:
            if sprint.state not in by_state:
                by_state[sprint.state] = []
            by_state[sprint.state].append(sprint)

        # Display sprints
        state_order = [
            SprintState.ACTIVE,
            SprintState.FUTURE,
            SprintState.CLOSED,
            SprintState.UNKNOWN,
        ]

        for state in state_order:
            if state not in by_state:
                continue

            state_sprints = by_state[state]
            state_name = state.value.upper()
            state_emoji = {
                SprintState.ACTIVE: Symbols.IN_PROGRESS,
                SprintState.FUTURE: Symbols.PLANNED,
                SprintState.CLOSED: Symbols.DONE,
                SprintState.UNKNOWN: Symbols.BULLET,
            }.get(state, Symbols.BULLET)

            console.section(f"{state_emoji} {state_name} ({len(state_sprints)})")
            console.print()

            for sprint in state_sprints:
                # Format dates
                date_info = ""
                if sprint.start_date and sprint.end_date:
                    start = sprint.start_date.strftime("%Y-%m-%d")
                    end = sprint.end_date.strftime("%Y-%m-%d")
                    date_info = f" ({start} - {end})"

                    if sprint.is_active():
                        days = sprint.days_remaining()
                        if days is not None:
                            date_info += f" - {days} days remaining"

                console.print(f"    {sprint.id}: {sprint.name}{date_info}")

                if sprint.goal:
                    console.print(f"        Goal: {sprint.goal[:60]}...")

            console.print()

        console.info(f"Total: {len(sprints)} sprints")

    except Exception as e:
        console.error(f"Failed to get sprints: {e}")
        return ExitCode.ERROR

    return ExitCode.SUCCESS
