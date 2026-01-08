"""
Custom Field Mapping - Map custom fields between markdown and issue trackers.

This module provides comprehensive field mapping capabilities:
- Map markdown field names to tracker-specific field IDs
- Support different field types (text, number, dropdown, date, etc.)
- Transform values between markdown and tracker formats
- Handle tracker-specific field schemas
- Support per-project and per-tracker configurations
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


logger = logging.getLogger(__name__)


class FieldType(Enum):
    """Types of fields supported for mapping."""

    TEXT = "text"  # Plain text, string
    NUMBER = "number"  # Integer or float
    FLOAT = "float"  # Decimal number
    DROPDOWN = "dropdown"  # Single select from options
    MULTI_SELECT = "multi_select"  # Multiple selection
    DATE = "date"  # Date field
    DATETIME = "datetime"  # Date with time
    USER = "user"  # User/assignee reference
    URL = "url"  # URL/link field
    BOOLEAN = "boolean"  # True/false
    LABELS = "labels"  # Label array
    RICH_TEXT = "rich_text"  # Formatted text (markdown/HTML)


class FieldDirection(Enum):
    """Direction of field sync."""

    BIDIRECTIONAL = "bidirectional"  # Sync both ways
    PUSH_ONLY = "push_only"  # Only push to tracker
    PULL_ONLY = "pull_only"  # Only pull from tracker
    READ_ONLY = "read_only"  # Never sync, display only


@dataclass
class FieldValueMapping:
    """Maps values between markdown and tracker representations."""

    markdown_value: str
    tracker_value: str
    aliases: list[str] = field(default_factory=list)

    def matches_markdown(self, value: str) -> bool:
        """Check if a markdown value matches this mapping."""
        value_lower = value.lower().strip()
        return value_lower == self.markdown_value.lower() or value_lower in [
            a.lower() for a in self.aliases
        ]

    def matches_tracker(self, value: str) -> bool:
        """Check if a tracker value matches this mapping."""
        return value.lower().strip() == self.tracker_value.lower()


@dataclass
class FieldDefinition:
    """Definition of a custom field mapping."""

    # Basic identity
    name: str  # Internal name for reference
    markdown_name: str  # Name as it appears in markdown (e.g., "Story Points")
    tracker_field_id: str  # Tracker field ID (e.g., "customfield_10014")

    # Optional metadata
    tracker_field_name: str | None = None  # Human-readable tracker field name
    description: str = ""

    # Type and sync info
    field_type: FieldType = FieldType.TEXT
    direction: FieldDirection = FieldDirection.BIDIRECTIONAL
    required: bool = False
    default_value: Any = None

    # Value mappings (for dropdown/multi-select)
    value_mappings: list[FieldValueMapping] = field(default_factory=list)

    # Transformation rules
    transform_to_tracker: str | None = None  # Python expression or function name
    transform_from_tracker: str | None = None  # Python expression or function name

    # Validation
    pattern: str | None = None  # Regex pattern for validation
    min_value: float | None = None  # For number fields
    max_value: float | None = None  # For number fields
    allowed_values: list[str] = field(default_factory=list)  # For dropdowns

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "markdown_name": self.markdown_name,
            "tracker_field_id": self.tracker_field_id,
            "tracker_field_name": self.tracker_field_name,
            "description": self.description,
            "field_type": self.field_type.value,
            "direction": self.direction.value,
            "required": self.required,
            "default_value": self.default_value,
            "value_mappings": [
                {
                    "markdown": vm.markdown_value,
                    "tracker": vm.tracker_value,
                    "aliases": vm.aliases,
                }
                for vm in self.value_mappings
            ],
            "pattern": self.pattern,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "allowed_values": self.allowed_values,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FieldDefinition":
        """Create from dictionary."""
        value_mappings = []
        for vm in data.get("value_mappings", []):
            value_mappings.append(
                FieldValueMapping(
                    markdown_value=vm.get("markdown", ""),
                    tracker_value=vm.get("tracker", ""),
                    aliases=vm.get("aliases", []),
                )
            )

        return cls(
            name=data.get("name", ""),
            markdown_name=data.get("markdown_name", ""),
            tracker_field_id=data.get("tracker_field_id", ""),
            tracker_field_name=data.get("tracker_field_name"),
            description=data.get("description", ""),
            field_type=FieldType(data.get("field_type", "text")),
            direction=FieldDirection(data.get("direction", "bidirectional")),
            required=data.get("required", False),
            default_value=data.get("default_value"),
            value_mappings=value_mappings,
            pattern=data.get("pattern"),
            min_value=data.get("min_value"),
            max_value=data.get("max_value"),
            allowed_values=data.get("allowed_values", []),
        )


@dataclass
class TrackerFieldMappingConfig:
    """Configuration for a specific tracker's field mappings."""

    tracker_type: str  # e.g., "jira", "github", "linear"
    project_key: str | None = None  # Optional project-specific config

    # Standard field overrides (built-in fields)
    story_points_field: str | None = None
    priority_field: str | None = None
    status_field: str | None = None
    assignee_field: str | None = None
    labels_field: str | None = None
    due_date_field: str | None = None
    sprint_field: str | None = None

    # Custom field definitions
    custom_fields: list[FieldDefinition] = field(default_factory=list)

    # Global value transformations
    status_mapping: dict[str, str] = field(default_factory=dict)
    priority_mapping: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "tracker_type": self.tracker_type,
            "project_key": self.project_key,
            "story_points_field": self.story_points_field,
            "priority_field": self.priority_field,
            "status_field": self.status_field,
            "assignee_field": self.assignee_field,
            "labels_field": self.labels_field,
            "due_date_field": self.due_date_field,
            "sprint_field": self.sprint_field,
            "custom_fields": [cf.to_dict() for cf in self.custom_fields],
            "status_mapping": self.status_mapping,
            "priority_mapping": self.priority_mapping,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TrackerFieldMappingConfig":
        """Create from dictionary."""
        custom_fields = [FieldDefinition.from_dict(cf) for cf in data.get("custom_fields", [])]

        return cls(
            tracker_type=data.get("tracker_type", "jira"),
            project_key=data.get("project_key"),
            story_points_field=data.get("story_points_field"),
            priority_field=data.get("priority_field"),
            status_field=data.get("status_field"),
            assignee_field=data.get("assignee_field"),
            labels_field=data.get("labels_field"),
            due_date_field=data.get("due_date_field"),
            sprint_field=data.get("sprint_field"),
            custom_fields=custom_fields,
            status_mapping=data.get("status_mapping", {}),
            priority_mapping=data.get("priority_mapping", {}),
        )


class FieldMapper:
    """
    Maps fields between markdown and issue trackers.

    Provides:
    - Lookup of tracker field IDs from markdown field names
    - Value transformation between formats
    - Validation of field values
    - Support for multiple tracker configurations
    """

    # Default field mappings for common fields
    DEFAULT_MARKDOWN_TO_JIRA: dict[str, str] = {
        "story_points": "customfield_10014",
        "story points": "customfield_10014",
        "points": "customfield_10014",
        "sp": "customfield_10014",
        "priority": "priority",
        "status": "status",
        "assignee": "assignee",
        "labels": "labels",
        "due_date": "duedate",
        "due date": "duedate",
        "sprint": "customfield_10020",
        "epic_link": "customfield_10008",
        "epic link": "customfield_10008",
    }

    def __init__(
        self,
        config: TrackerFieldMappingConfig | None = None,
        configs: list[TrackerFieldMappingConfig] | None = None,
    ):
        """
        Initialize the field mapper.

        Args:
            config: Single tracker configuration
            configs: Multiple tracker configurations (for multi-tracker)
        """
        self.configs: list[TrackerFieldMappingConfig] = []
        if config:
            self.configs.append(config)
        if configs:
            self.configs.extend(configs)

        self.logger = logging.getLogger("FieldMapper")
        self._build_lookup_caches()

    def _build_lookup_caches(self) -> None:
        """Build lookup caches for fast field resolution."""
        # Cache: (tracker_type, project_key) -> {markdown_name -> FieldDefinition}
        self._field_cache: dict[tuple[str, str | None], dict[str, FieldDefinition]] = {}
        # Cache: (tracker_type, project_key) -> {tracker_field_id -> FieldDefinition}
        self._reverse_cache: dict[tuple[str, str | None], dict[str, FieldDefinition]] = {}

        for config in self.configs:
            key = (config.tracker_type, config.project_key)
            self._field_cache[key] = {}
            self._reverse_cache[key] = {}

            for field_def in config.custom_fields:
                # Index by markdown name (lowercase for case-insensitive lookup)
                self._field_cache[key][field_def.markdown_name.lower()] = field_def
                # Index by tracker field ID
                self._reverse_cache[key][field_def.tracker_field_id] = field_def

    def get_config(
        self, tracker_type: str, project_key: str | None = None
    ) -> TrackerFieldMappingConfig | None:
        """Get configuration for a specific tracker/project."""
        # First try exact match
        for config in self.configs:
            if config.tracker_type == tracker_type and config.project_key == project_key:
                return config

        # Fall back to tracker-type-only match
        for config in self.configs:
            if config.tracker_type == tracker_type and config.project_key is None:
                return config

        return None

    def get_tracker_field_id(
        self,
        markdown_name: str,
        tracker_type: str = "jira",
        project_key: str | None = None,
    ) -> str | None:
        """
        Get the tracker field ID for a markdown field name.

        Args:
            markdown_name: Field name as it appears in markdown
            tracker_type: Type of tracker (jira, github, etc.)
            project_key: Optional project key for project-specific mappings

        Returns:
            Tracker field ID, or None if not found
        """
        config = self.get_config(tracker_type, project_key)
        markdown_lower = markdown_name.lower().strip()

        # Check custom fields first
        if config:
            # Check custom_fields list
            for field_def in config.custom_fields:
                if field_def.markdown_name.lower() == markdown_lower:
                    return field_def.tracker_field_id

            # Check standard field overrides
            standard_mappings = {
                "story_points": config.story_points_field,
                "story points": config.story_points_field,
                "points": config.story_points_field,
                "priority": config.priority_field,
                "status": config.status_field,
                "assignee": config.assignee_field,
                "labels": config.labels_field,
                "due_date": config.due_date_field,
                "due date": config.due_date_field,
                "sprint": config.sprint_field,
            }
            if markdown_lower in standard_mappings:
                return standard_mappings[markdown_lower]

        # Fall back to defaults
        if tracker_type == "jira":
            return self.DEFAULT_MARKDOWN_TO_JIRA.get(markdown_lower)

        return None

    def get_markdown_field_name(
        self,
        tracker_field_id: str,
        tracker_type: str = "jira",
        project_key: str | None = None,
    ) -> str | None:
        """
        Get the markdown field name for a tracker field ID.

        Args:
            tracker_field_id: Tracker field ID
            tracker_type: Type of tracker
            project_key: Optional project key

        Returns:
            Markdown field name, or None if not found
        """
        key = (tracker_type, project_key)
        if key in self._reverse_cache:
            field_def = self._reverse_cache[key].get(tracker_field_id)
            if field_def:
                return field_def.markdown_name

        # Fall back to key without project
        key_no_project = (tracker_type, None)
        if key_no_project in self._reverse_cache:
            field_def = self._reverse_cache[key_no_project].get(tracker_field_id)
            if field_def:
                return field_def.markdown_name

        # Reverse lookup in defaults
        for md_name, field_id in self.DEFAULT_MARKDOWN_TO_JIRA.items():
            if field_id == tracker_field_id:
                return md_name

        return None

    def get_field_definition(
        self,
        markdown_name: str,
        tracker_type: str = "jira",
        project_key: str | None = None,
    ) -> FieldDefinition | None:
        """
        Get the full field definition for a markdown field.

        Args:
            markdown_name: Field name as it appears in markdown
            tracker_type: Type of tracker
            project_key: Optional project key

        Returns:
            FieldDefinition, or None if not found
        """
        key = (tracker_type, project_key)
        if key in self._field_cache:
            return self._field_cache[key].get(markdown_name.lower())

        key_no_project = (tracker_type, None)
        if key_no_project in self._field_cache:
            return self._field_cache[key_no_project].get(markdown_name.lower())

        return None

    def transform_value_to_tracker(
        self,
        markdown_name: str,
        value: Any,
        tracker_type: str = "jira",
        project_key: str | None = None,
    ) -> Any:
        """
        Transform a value from markdown format to tracker format.

        Args:
            markdown_name: Field name
            value: Value in markdown format
            tracker_type: Type of tracker
            project_key: Optional project key

        Returns:
            Transformed value for tracker
        """
        field_def = self.get_field_definition(markdown_name, tracker_type, project_key)

        if not field_def:
            return value  # No transformation defined

        # Apply value mappings for dropdown/multi-select
        if field_def.field_type in (FieldType.DROPDOWN, FieldType.MULTI_SELECT):
            for vm in field_def.value_mappings:
                if vm.matches_markdown(str(value)):
                    return vm.tracker_value
            # Return as-is if no mapping found
            return value

        # Apply type-specific transformations
        if field_def.field_type == FieldType.NUMBER:
            return int(value) if value else 0
        if field_def.field_type == FieldType.FLOAT:
            return float(value) if value else 0.0
        if field_def.field_type == FieldType.BOOLEAN:
            return str(value).lower() in ("true", "yes", "1", "✓", "✅")
        if field_def.field_type == FieldType.DATE:
            # Parse common date formats
            if isinstance(value, str):
                for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"]:
                    try:
                        return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
                    except ValueError:
                        continue
            return value
        if field_def.field_type == FieldType.LABELS:
            if isinstance(value, str):
                return [v.strip() for v in value.split(",")]
            return value

        return value

    def transform_value_from_tracker(
        self,
        tracker_field_id: str,
        value: Any,
        tracker_type: str = "jira",
        project_key: str | None = None,
    ) -> Any:
        """
        Transform a value from tracker format to markdown format.

        Args:
            tracker_field_id: Tracker field ID
            value: Value from tracker
            tracker_type: Type of tracker
            project_key: Optional project key

        Returns:
            Transformed value for markdown
        """
        key = (tracker_type, project_key)
        field_def = None

        if key in self._reverse_cache:
            field_def = self._reverse_cache[key].get(tracker_field_id)
        if not field_def:
            key_no_project = (tracker_type, None)
            if key_no_project in self._reverse_cache:
                field_def = self._reverse_cache[key_no_project].get(tracker_field_id)

        if not field_def:
            return value  # No transformation defined

        # Apply reverse value mappings for dropdown/multi-select
        if field_def.field_type in (FieldType.DROPDOWN, FieldType.MULTI_SELECT):
            for vm in field_def.value_mappings:
                if vm.matches_tracker(str(value)):
                    return vm.markdown_value
            return value

        # Apply type-specific transformations
        if field_def.field_type == FieldType.LABELS:
            if isinstance(value, list):
                return ", ".join(value)
            return value

        return value

    def validate_value(
        self,
        markdown_name: str,
        value: Any,
        tracker_type: str = "jira",
        project_key: str | None = None,
    ) -> tuple[bool, str | None]:
        """
        Validate a field value against its definition.

        Args:
            markdown_name: Field name
            value: Value to validate
            tracker_type: Type of tracker
            project_key: Optional project key

        Returns:
            Tuple of (is_valid, error_message)
        """
        field_def = self.get_field_definition(markdown_name, tracker_type, project_key)

        if not field_def:
            return True, None  # No validation rules

        # Check required
        if field_def.required and not value:
            return False, f"Field '{markdown_name}' is required"

        if not value:
            return True, None  # Empty non-required is OK

        # Check allowed values
        if field_def.allowed_values and str(value) not in field_def.allowed_values:
            return False, f"Value '{value}' not in allowed values for '{markdown_name}'"

        # Check pattern
        if field_def.pattern:
            if not re.match(field_def.pattern, str(value)):
                return False, f"Value '{value}' doesn't match pattern for '{markdown_name}'"

        # Check numeric bounds
        if field_def.field_type in (FieldType.NUMBER, FieldType.FLOAT):
            try:
                num_value = float(value)
                if field_def.min_value is not None and num_value < field_def.min_value:
                    return False, f"Value {num_value} below minimum {field_def.min_value}"
                if field_def.max_value is not None and num_value > field_def.max_value:
                    return False, f"Value {num_value} above maximum {field_def.max_value}"
            except ValueError:
                return False, f"Invalid number: {value}"

        return True, None

    def get_all_custom_fields(
        self,
        tracker_type: str = "jira",
        project_key: str | None = None,
    ) -> list[FieldDefinition]:
        """Get all custom field definitions for a tracker/project."""
        config = self.get_config(tracker_type, project_key)
        return config.custom_fields if config else []


class FieldMappingLoader:
    """Load field mappings from configuration files."""

    @staticmethod
    def load_from_yaml(path: Path) -> TrackerFieldMappingConfig:
        """
        Load field mapping configuration from YAML file.

        Expected format:
        ```yaml
        tracker_type: jira
        project_key: PROJ  # optional

        # Standard field overrides
        story_points_field: customfield_10014
        priority_field: priority
        status_field: status

        # Status value mappings
        status_mapping:
          "Done": "Closed"
          "In Progress": "In Development"

        # Priority value mappings
        priority_mapping:
          "Critical": "Highest"
          "High": "High"

        # Custom field definitions
        custom_fields:
          - name: team
            markdown_name: "Team"
            tracker_field_id: customfield_10050
            field_type: dropdown
            value_mappings:
              - markdown: "Backend"
                tracker: "10001"
              - markdown: "Frontend"
                tracker: "10002"

          - name: target_release
            markdown_name: "Target Release"
            tracker_field_id: customfield_10060
            field_type: text
            required: true
        ```
        """
        with open(path) as f:
            data = yaml.safe_load(f)

        return TrackerFieldMappingConfig.from_dict(data)

    @staticmethod
    def load_from_dict(data: dict[str, Any]) -> TrackerFieldMappingConfig:
        """Load field mapping configuration from dictionary."""
        return TrackerFieldMappingConfig.from_dict(data)

    @staticmethod
    def save_to_yaml(config: TrackerFieldMappingConfig, path: Path) -> None:
        """Save field mapping configuration to YAML file."""
        with open(path, "w") as f:
            yaml.dump(config.to_dict(), f, default_flow_style=False, sort_keys=False)


def create_default_jira_mapping() -> TrackerFieldMappingConfig:
    """Create default Jira field mapping configuration."""
    return TrackerFieldMappingConfig(
        tracker_type="jira",
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
    )


def create_field_mapper_from_config(
    config_path: Path | None = None,
    config_dict: dict[str, Any] | None = None,
) -> FieldMapper:
    """
    Create a FieldMapper from configuration.

    Args:
        config_path: Path to YAML configuration file
        config_dict: Configuration dictionary

    Returns:
        Configured FieldMapper
    """
    configs = []

    if config_path and config_path.exists():
        configs.append(FieldMappingLoader.load_from_yaml(config_path))

    if config_dict:
        configs.append(FieldMappingLoader.load_from_dict(config_dict))

    if not configs:
        # Use default Jira mapping
        configs.append(create_default_jira_mapping())

    return FieldMapper(configs=configs)
