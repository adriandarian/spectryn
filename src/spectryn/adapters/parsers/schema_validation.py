"""
Schema Validation - Optional strict mode for validating required fields.

This module provides configurable schema validation for parsed entities:
- Define which fields are required vs optional
- Add custom validation rules (min/max values, patterns, etc.)
- Collect validation errors with precise locations
- Support multiple strictness levels (lenient, normal, strict)

Usage:
    from spectryn.adapters.parsers.schema_validation import (
        SchemaValidator,
        StorySchema,
        ValidationMode,
    )

    # Create validator with strict mode
    validator = SchemaValidator(mode=ValidationMode.STRICT)

    # Validate parsed stories
    result = validator.validate_stories(stories)

    if not result.is_valid:
        for error in result.errors:
            print(f"{error.severity}: {error.field} - {error.message}")

    # Or wrap a parser to auto-validate
    from spectryn.adapters.parsers import MarkdownParser
    validating_parser = ValidatingParser(MarkdownParser(), mode=ValidationMode.STRICT)
    stories = validating_parser.parse_stories("epics.md")  # Raises on validation failure
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from spectryn.core.domain.entities import Epic, Subtask, UserStory
from spectryn.core.domain.enums import Priority, Status
from spectryn.core.domain.value_objects import StoryId
from spectryn.core.ports.document_parser import DocumentParserPort, ParserError

from .tolerant_markdown import ParseLocation


__all__ = [
    "EpicSchema",
    "FieldSchema",
    "FieldType",
    "SchemaPreset",
    "SchemaValidator",
    "StorySchema",
    "SubtaskSchema",
    "ValidatingParser",
    "ValidationError",
    "ValidationMode",
    "ValidationResult",
    "ValidationSeverity",
    "ValidationWarning",
    "create_schema",
    "create_validator",
    "matches_pattern",
    "max_length",
    "max_value",
    "min_length",
    "min_value",
    "not_empty",
    "one_of",
    "valid_priority",
    "valid_status",
    "valid_story_id",
]


# =============================================================================
# Enums
# =============================================================================


class ValidationMode(Enum):
    """
    Validation strictness level.

    LENIENT: Only validate critical fields, ignore most issues
    NORMAL: Standard validation with sensible defaults
    STRICT: Validate all fields, fail on any issue
    CUSTOM: Use custom schema configuration
    """

    LENIENT = "lenient"
    NORMAL = "normal"
    STRICT = "strict"
    CUSTOM = "custom"


class ValidationSeverity(Enum):
    """Severity level for validation issues."""

    ERROR = "error"  # Validation fails, data is invalid
    WARNING = "warning"  # Data is questionable but usable
    INFO = "info"  # Informational suggestion


class FieldType(Enum):
    """Types of fields that can be validated."""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    ENUM = "enum"
    LIST = "list"
    STORY_ID = "story_id"
    ISSUE_KEY = "issue_key"
    DATE = "date"
    DATETIME = "datetime"
    ANY = "any"


# =============================================================================
# Validation Result Types
# =============================================================================


@dataclass(frozen=True)
class ValidationError:
    """
    A validation error for a specific field.

    Attributes:
        field: Name of the field that failed validation
        message: Human-readable error description
        severity: Error severity level
        value: The invalid value (if available)
        location: Source location (if available from parsing)
        entity_id: ID of the entity (story/subtask/epic)
        entity_type: Type of entity being validated
        rule: Name of the validation rule that failed
        suggestion: How to fix the issue
    """

    field: str
    message: str
    severity: ValidationSeverity = ValidationSeverity.ERROR
    value: Any = None
    location: ParseLocation | None = None
    entity_id: str | None = None
    entity_type: str = "story"
    rule: str | None = None
    suggestion: str | None = None

    def __str__(self) -> str:
        """Format error for display."""
        parts = []

        # Location prefix
        if self.location:
            parts.append(f"[{self.location}]")
        elif self.entity_id:
            parts.append(f"[{self.entity_type}:{self.entity_id}]")

        # Severity and field
        parts.append(f"{self.severity.value.upper()}: {self.field}")

        # Message
        parts.append(f"- {self.message}")

        result = " ".join(parts)

        # Add suggestion on new line
        if self.suggestion:
            result += f"\n  Suggestion: {self.suggestion}"

        return result


@dataclass(frozen=True)
class ValidationWarning(ValidationError):  # noqa: N818
    """A validation warning (non-critical issue).

    Note: Named ValidationWarning (not ValidationWarningError) because this
    is a dataclass representing a validation issue, not an exception class.
    """

    severity: ValidationSeverity = field(default=ValidationSeverity.WARNING, init=False, repr=False)


@dataclass
class ValidationResult:
    """
    Result of schema validation.

    Attributes:
        errors: List of validation errors
        warnings: List of validation warnings
        validated_count: Number of entities validated
        source: Source identifier (file path, etc.)
    """

    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationWarning] = field(default_factory=list)
    validated_count: int = 0
    source: str | None = None

    @property
    def is_valid(self) -> bool:
        """Check if validation passed (no errors)."""
        return len(self.errors) == 0

    @property
    def has_warnings(self) -> bool:
        """Check if there are any warnings."""
        return len(self.warnings) > 0

    @property
    def error_count(self) -> int:
        """Get total error count."""
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        """Get total warning count."""
        return len(self.warnings)

    def add_error(self, error: ValidationError) -> None:
        """Add a validation error."""
        self.errors.append(error)

    def add_warning(self, warning: ValidationWarning) -> None:
        """Add a validation warning."""
        self.warnings.append(warning)

    def merge(self, other: ValidationResult) -> ValidationResult:
        """Merge another result into this one."""
        return ValidationResult(
            errors=self.errors + other.errors,
            warnings=self.warnings + other.warnings,
            validated_count=self.validated_count + other.validated_count,
            source=self.source or other.source,
        )

    def __str__(self) -> str:
        """Format result for display."""
        if self.is_valid and not self.has_warnings:
            return f"✓ Validation passed ({self.validated_count} entities)"

        lines = []
        if not self.is_valid:
            lines.append(f"✗ Validation failed: {self.error_count} error(s)")
            for error in self.errors:
                lines.append(f"  {error}")

        if self.has_warnings:
            lines.append(f"⚠ {self.warning_count} warning(s)")
            for warning in self.warnings:
                lines.append(f"  {warning}")

        return "\n".join(lines)


# =============================================================================
# Built-in Validators
# =============================================================================

# Type alias for validator functions
ValidatorFunc = Callable[[Any], tuple[bool, str | None]]


def min_length(length: int) -> ValidatorFunc:
    """Validate minimum string/list length."""

    def validator(value: Any) -> tuple[bool, str | None]:
        if value is None:
            return True, None  # Let required check handle None
        if hasattr(value, "__len__"):
            if len(value) < length:
                return False, f"must have at least {length} character(s)"
        return True, None

    return validator


def max_length(length: int) -> ValidatorFunc:
    """Validate maximum string/list length."""

    def validator(value: Any) -> tuple[bool, str | None]:
        if value is None:
            return True, None
        if hasattr(value, "__len__"):
            if len(value) > length:
                return False, f"must have at most {length} character(s)"
        return True, None

    return validator


def min_value(minimum: int | float) -> ValidatorFunc:
    """Validate minimum numeric value."""

    def validator(value: Any) -> tuple[bool, str | None]:
        if value is None:
            return True, None
        if isinstance(value, (int, float)):
            if value < minimum:
                return False, f"must be at least {minimum}"
        return True, None

    return validator


def max_value(maximum: int | float) -> ValidatorFunc:
    """Validate maximum numeric value."""

    def validator(value: Any) -> tuple[bool, str | None]:
        if value is None:
            return True, None
        if isinstance(value, (int, float)):
            if value > maximum:
                return False, f"must be at most {maximum}"
        return True, None

    return validator


def matches_pattern(pattern: str, description: str | None = None) -> ValidatorFunc:
    """Validate string matches regex pattern."""
    compiled = re.compile(pattern)

    def validator(value: Any) -> tuple[bool, str | None]:
        if value is None:
            return True, None
        if isinstance(value, str):
            if not compiled.match(value):
                msg = description or f"must match pattern '{pattern}'"
                return False, msg
        return True, None

    return validator


def one_of(allowed: list[Any], case_insensitive: bool = False) -> ValidatorFunc:
    """Validate value is one of allowed values."""

    def validator(value: Any) -> tuple[bool, str | None]:
        if value is None:
            return True, None
        check_value = value.lower() if case_insensitive and isinstance(value, str) else value
        allowed_check = (
            [v.lower() if isinstance(v, str) else v for v in allowed]
            if case_insensitive
            else allowed
        )
        if check_value not in allowed_check:
            return False, f"must be one of: {', '.join(str(v) for v in allowed)}"
        return True, None

    return validator


def not_empty() -> ValidatorFunc:
    """Validate value is not empty (non-blank string, non-empty list)."""

    def validator(value: Any) -> tuple[bool, str | None]:
        if value is None:
            return True, None  # Let required check handle None
        if isinstance(value, str) and not value.strip():
            return False, "must not be empty or blank"
        if hasattr(value, "__len__") and len(value) == 0:
            return False, "must not be empty"
        return True, None

    return validator


def valid_story_id() -> ValidatorFunc:
    """Validate value is a valid story ID format."""

    def validator(value: Any) -> tuple[bool, str | None]:
        if value is None:
            return True, None
        str_val = str(value)
        if not StoryId.PATTERN.match(str_val):
            return False, "must be a valid story ID (e.g., US-001, PROJ-123, #42)"
        return True, None

    return validator


def valid_priority() -> ValidatorFunc:
    """Validate value is a valid priority."""

    def validator(value: Any) -> tuple[bool, str | None]:
        if value is None:
            return True, None
        if isinstance(value, Priority):
            return True, None
        if isinstance(value, str):
            # Priority.from_string always returns a valid Priority (defaults to MEDIUM)
            # So string values are always valid
            return True, None
        return False, "must be a Priority enum or string"

    return validator


def valid_status() -> ValidatorFunc:
    """Validate value is a valid status."""

    def validator(value: Any) -> tuple[bool, str | None]:
        if value is None:
            return True, None
        if isinstance(value, Status):
            return True, None
        if isinstance(value, str):
            # Status.from_string always returns a valid Status (defaults to PLANNED)
            # So string values are always valid
            return True, None
        return False, "must be a Status enum or string"

    return validator


# =============================================================================
# Schema Definitions
# =============================================================================


@dataclass
class FieldSchema:
    """
    Schema definition for a single field.

    Attributes:
        name: Field name (attribute name on entity)
        display_name: Human-readable field name
        field_type: Expected type of the field
        required: Whether the field is required
        validators: List of validation functions
        default: Default value if not provided
        description: Field description for documentation
        severity: Severity if validation fails (error vs warning)
    """

    name: str
    display_name: str | None = None
    field_type: FieldType = FieldType.ANY
    required: bool = False
    validators: list[ValidatorFunc] = field(default_factory=list)
    default: Any = None
    description: str | None = None
    severity: ValidationSeverity = ValidationSeverity.ERROR

    @property
    def label(self) -> str:
        """Get display name or formatted field name."""
        return self.display_name or self.name.replace("_", " ").title()

    def validate(
        self,
        value: Any,
        entity_id: str | None = None,
        entity_type: str = "story",
        location: ParseLocation | None = None,
    ) -> list[ValidationError]:
        """
        Validate a value against this field schema.

        Args:
            value: The value to validate
            entity_id: ID of the entity being validated
            entity_type: Type of entity
            location: Source location

        Returns:
            List of validation errors (empty if valid)
        """
        errors: list[ValidationError] = []

        # Check required
        is_missing = value is None or (isinstance(value, (str, list)) and len(value) == 0)
        if self.required and is_missing:
            errors.append(
                ValidationError(
                    field=self.name,
                    message=f"{self.label} is required",
                    severity=self.severity,
                    value=value,
                    location=location,
                    entity_id=entity_id,
                    entity_type=entity_type,
                    rule="required",
                    suggestion=f"Add a value for {self.label}",
                )
            )
            return errors  # Skip other validators if missing

        # Run custom validators
        for validator in self.validators:
            is_valid, error_msg = validator(value)
            if not is_valid and error_msg:
                errors.append(
                    ValidationError(
                        field=self.name,
                        message=f"{self.label} {error_msg}",
                        severity=self.severity,
                        value=value,
                        location=location,
                        entity_id=entity_id,
                        entity_type=entity_type,
                        rule=validator.__name__ if hasattr(validator, "__name__") else "custom",
                    )
                )

        return errors


@dataclass
class SubtaskSchema:
    """Schema for subtask validation."""

    fields: dict[str, FieldSchema] = field(default_factory=dict)

    @classmethod
    def default(cls, mode: ValidationMode = ValidationMode.NORMAL) -> SubtaskSchema:
        """Create default subtask schema based on mode."""
        schema = cls()

        if mode == ValidationMode.LENIENT:
            # Only require name in lenient mode
            schema.fields["name"] = FieldSchema(
                name="name",
                display_name="Subtask Name",
                field_type=FieldType.STRING,
                required=True,
                validators=[not_empty()],
            )
        elif mode == ValidationMode.NORMAL:
            schema.fields["name"] = FieldSchema(
                name="name",
                display_name="Subtask Name",
                field_type=FieldType.STRING,
                required=True,
                validators=[not_empty(), min_length(3)],
            )
            schema.fields["status"] = FieldSchema(
                name="status",
                display_name="Status",
                field_type=FieldType.ENUM,
                required=False,
                validators=[valid_status()],
            )
        elif mode == ValidationMode.STRICT:
            schema.fields["name"] = FieldSchema(
                name="name",
                display_name="Subtask Name",
                field_type=FieldType.STRING,
                required=True,
                validators=[not_empty(), min_length(5), max_length(200)],
            )
            schema.fields["status"] = FieldSchema(
                name="status",
                display_name="Status",
                field_type=FieldType.ENUM,
                required=True,
                validators=[valid_status()],
            )
            schema.fields["story_points"] = FieldSchema(
                name="story_points",
                display_name="Story Points",
                field_type=FieldType.INTEGER,
                required=False,
                validators=[min_value(0), max_value(100)],
                severity=ValidationSeverity.WARNING,
            )

        return schema

    def validate(
        self,
        subtask: Subtask,
        parent_id: str | None = None,
        location: ParseLocation | None = None,
    ) -> list[ValidationError]:
        """Validate a subtask against this schema."""
        errors: list[ValidationError] = []
        entity_id = f"{parent_id}/{subtask.name[:20]}" if parent_id else subtask.name[:20]

        for field_schema in self.fields.values():
            value = getattr(subtask, field_schema.name, None)
            errors.extend(
                field_schema.validate(
                    value,
                    entity_id=entity_id,
                    entity_type="subtask",
                    location=location,
                )
            )

        return errors


@dataclass
class StorySchema:
    """
    Schema for user story validation.

    Defines required fields, validation rules, and nested schemas.
    """

    fields: dict[str, FieldSchema] = field(default_factory=dict)
    subtask_schema: SubtaskSchema | None = None
    require_acceptance_criteria: bool = False
    min_acceptance_criteria: int = 0
    require_description: bool = False

    @classmethod
    def default(cls, mode: ValidationMode = ValidationMode.NORMAL) -> StorySchema:
        """Create default story schema based on mode."""
        schema = cls()

        if mode == ValidationMode.LENIENT:
            # Minimal validation - only ID and title
            schema.fields["id"] = FieldSchema(
                name="id",
                display_name="Story ID",
                field_type=FieldType.STORY_ID,
                required=True,
                validators=[valid_story_id()],
            )
            schema.fields["title"] = FieldSchema(
                name="title",
                display_name="Title",
                field_type=FieldType.STRING,
                required=True,
                validators=[not_empty()],
            )
            schema.subtask_schema = SubtaskSchema.default(mode)

        elif mode == ValidationMode.NORMAL:
            # Standard validation
            schema.fields["id"] = FieldSchema(
                name="id",
                display_name="Story ID",
                field_type=FieldType.STORY_ID,
                required=True,
                validators=[valid_story_id()],
            )
            schema.fields["title"] = FieldSchema(
                name="title",
                display_name="Title",
                field_type=FieldType.STRING,
                required=True,
                validators=[not_empty(), min_length(5)],
            )
            schema.fields["status"] = FieldSchema(
                name="status",
                display_name="Status",
                field_type=FieldType.ENUM,
                required=False,
                validators=[valid_status()],
            )
            schema.fields["priority"] = FieldSchema(
                name="priority",
                display_name="Priority",
                field_type=FieldType.ENUM,
                required=False,
                validators=[valid_priority()],
            )
            schema.fields["story_points"] = FieldSchema(
                name="story_points",
                display_name="Story Points",
                field_type=FieldType.INTEGER,
                required=False,
                validators=[min_value(0), max_value(100)],
                severity=ValidationSeverity.WARNING,
            )
            schema.subtask_schema = SubtaskSchema.default(mode)

        elif mode == ValidationMode.STRICT:
            # Strict validation - all fields required with constraints
            schema.fields["id"] = FieldSchema(
                name="id",
                display_name="Story ID",
                field_type=FieldType.STORY_ID,
                required=True,
                validators=[valid_story_id()],
            )
            schema.fields["title"] = FieldSchema(
                name="title",
                display_name="Title",
                field_type=FieldType.STRING,
                required=True,
                validators=[not_empty(), min_length(10), max_length(200)],
            )
            schema.fields["status"] = FieldSchema(
                name="status",
                display_name="Status",
                field_type=FieldType.ENUM,
                required=True,
                validators=[valid_status()],
            )
            schema.fields["priority"] = FieldSchema(
                name="priority",
                display_name="Priority",
                field_type=FieldType.ENUM,
                required=True,
                validators=[valid_priority()],
            )
            schema.fields["story_points"] = FieldSchema(
                name="story_points",
                display_name="Story Points",
                field_type=FieldType.INTEGER,
                required=True,
                validators=[min_value(1), max_value(21)],  # Fibonacci-ish
            )
            schema.fields["assignee"] = FieldSchema(
                name="assignee",
                display_name="Assignee",
                field_type=FieldType.STRING,
                required=False,
                validators=[],
                severity=ValidationSeverity.WARNING,
            )
            schema.require_description = True
            schema.require_acceptance_criteria = True
            schema.min_acceptance_criteria = 1
            schema.subtask_schema = SubtaskSchema.default(mode)

        return schema

    def validate(
        self,
        story: UserStory,
        location: ParseLocation | None = None,
    ) -> list[ValidationError]:
        """Validate a user story against this schema."""
        errors: list[ValidationError] = []
        entity_id = str(story.id)

        # Validate defined fields
        for field_schema in self.fields.values():
            value = getattr(story, field_schema.name, None)
            errors.extend(
                field_schema.validate(
                    value,
                    entity_id=entity_id,
                    entity_type="story",
                    location=location,
                )
            )

        # Validate description requirement
        if self.require_description:
            if story.description is None or not story.description.to_markdown().strip():
                errors.append(
                    ValidationError(
                        field="description",
                        message="Description is required",
                        severity=ValidationSeverity.ERROR,
                        entity_id=entity_id,
                        entity_type="story",
                        rule="required",
                        suggestion="Add a description with As a/I want/So that format",
                    )
                )

        # Validate acceptance criteria requirement
        if self.require_acceptance_criteria:
            ac_count = len(story.acceptance_criteria.items) if story.acceptance_criteria else 0
            if ac_count < self.min_acceptance_criteria:
                errors.append(
                    ValidationError(
                        field="acceptance_criteria",
                        message=f"At least {self.min_acceptance_criteria} acceptance criteria required, found {ac_count}",
                        severity=ValidationSeverity.ERROR,
                        entity_id=entity_id,
                        entity_type="story",
                        rule="min_acceptance_criteria",
                        suggestion="Add acceptance criteria using checkbox format: - [ ] Criteria",
                    )
                )

        # Validate subtasks
        if self.subtask_schema and story.subtasks:
            for subtask in story.subtasks:
                errors.extend(
                    self.subtask_schema.validate(
                        subtask,
                        parent_id=entity_id,
                        location=location,
                    )
                )

        return errors


@dataclass
class EpicSchema:
    """Schema for epic validation."""

    fields: dict[str, FieldSchema] = field(default_factory=dict)
    story_schema: StorySchema | None = None
    require_stories: bool = False
    min_stories: int = 0

    @classmethod
    def default(cls, mode: ValidationMode = ValidationMode.NORMAL) -> EpicSchema:
        """Create default epic schema based on mode."""
        schema = cls()
        schema.story_schema = StorySchema.default(mode)

        if mode == ValidationMode.LENIENT:
            schema.fields["key"] = FieldSchema(
                name="key",
                display_name="Epic Key",
                field_type=FieldType.ISSUE_KEY,
                required=True,
            )
            schema.fields["title"] = FieldSchema(
                name="title",
                display_name="Title",
                field_type=FieldType.STRING,
                required=True,
                validators=[not_empty()],
            )

        elif mode == ValidationMode.NORMAL:
            schema.fields["key"] = FieldSchema(
                name="key",
                display_name="Epic Key",
                field_type=FieldType.ISSUE_KEY,
                required=True,
            )
            schema.fields["title"] = FieldSchema(
                name="title",
                display_name="Title",
                field_type=FieldType.STRING,
                required=True,
                validators=[not_empty(), min_length(5)],
            )
            schema.fields["status"] = FieldSchema(
                name="status",
                display_name="Status",
                field_type=FieldType.ENUM,
                required=False,
                validators=[valid_status()],
            )

        elif mode == ValidationMode.STRICT:
            schema.fields["key"] = FieldSchema(
                name="key",
                display_name="Epic Key",
                field_type=FieldType.ISSUE_KEY,
                required=True,
            )
            schema.fields["title"] = FieldSchema(
                name="title",
                display_name="Title",
                field_type=FieldType.STRING,
                required=True,
                validators=[not_empty(), min_length(10), max_length(200)],
            )
            schema.fields["summary"] = FieldSchema(
                name="summary",
                display_name="Summary",
                field_type=FieldType.STRING,
                required=False,
                severity=ValidationSeverity.WARNING,
            )
            schema.fields["status"] = FieldSchema(
                name="status",
                display_name="Status",
                field_type=FieldType.ENUM,
                required=True,
                validators=[valid_status()],
            )
            schema.fields["priority"] = FieldSchema(
                name="priority",
                display_name="Priority",
                field_type=FieldType.ENUM,
                required=True,
                validators=[valid_priority()],
            )
            schema.require_stories = True
            schema.min_stories = 1

        return schema

    def validate(
        self,
        epic: Epic,
        location: ParseLocation | None = None,
    ) -> list[ValidationError]:
        """Validate an epic against this schema."""
        errors: list[ValidationError] = []
        entity_id = str(epic.key)

        # Validate epic fields
        for field_schema in self.fields.values():
            value = getattr(epic, field_schema.name, None)
            errors.extend(
                field_schema.validate(
                    value,
                    entity_id=entity_id,
                    entity_type="epic",
                    location=location,
                )
            )

        # Validate stories requirement
        if self.require_stories:
            story_count = len(epic.stories)
            if story_count < self.min_stories:
                errors.append(
                    ValidationError(
                        field="stories",
                        message=f"At least {self.min_stories} story(ies) required, found {story_count}",
                        severity=ValidationSeverity.ERROR,
                        entity_id=entity_id,
                        entity_type="epic",
                        rule="min_stories",
                    )
                )

        # Validate each story
        if self.story_schema:
            for story in epic.stories:
                errors.extend(self.story_schema.validate(story, location=location))

        # Validate child epics recursively
        for child_epic in epic.child_epics:
            errors.extend(self.validate(child_epic, location=location))

        return errors


# =============================================================================
# Schema Presets
# =============================================================================


class SchemaPreset(Enum):
    """Predefined schema configurations for common use cases."""

    # Basic presets based on mode
    LENIENT = "lenient"
    NORMAL = "normal"
    STRICT = "strict"

    # Domain-specific presets
    AGILE = "agile"  # Agile/Scrum focused (story points, sprints)
    KANBAN = "kanban"  # Kanban focused (status important, points optional)
    DOCUMENTATION = "documentation"  # Documentation focused (descriptions required)
    QA = "qa"  # QA focused (acceptance criteria required)


def create_schema(
    preset: SchemaPreset | ValidationMode = ValidationMode.NORMAL,
) -> tuple[StorySchema, EpicSchema]:
    """
    Create story and epic schemas from a preset.

    Args:
        preset: Schema preset or validation mode

    Returns:
        Tuple of (StorySchema, EpicSchema)
    """
    # Convert preset to mode
    if isinstance(preset, ValidationMode):
        mode = preset
    elif preset == SchemaPreset.LENIENT:
        mode = ValidationMode.LENIENT
    elif preset == SchemaPreset.STRICT:
        mode = ValidationMode.STRICT
    else:
        mode = ValidationMode.NORMAL

    story_schema = StorySchema.default(mode)
    epic_schema = EpicSchema.default(mode)

    # Apply preset-specific modifications
    if preset == SchemaPreset.AGILE:
        # Agile: story points required, sprint tracking
        story_schema.fields["story_points"] = FieldSchema(
            name="story_points",
            display_name="Story Points",
            field_type=FieldType.INTEGER,
            required=True,
            validators=[min_value(1), max_value(21)],
        )
        story_schema.fields["sprint"] = FieldSchema(
            name="sprint",
            display_name="Sprint",
            field_type=FieldType.STRING,
            required=False,
            severity=ValidationSeverity.WARNING,
        )

    elif preset == SchemaPreset.KANBAN:
        # Kanban: status required, points optional
        story_schema.fields["status"] = FieldSchema(
            name="status",
            display_name="Status",
            field_type=FieldType.ENUM,
            required=True,
            validators=[valid_status()],
        )
        story_schema.fields["story_points"].required = False

    elif preset == SchemaPreset.DOCUMENTATION:
        # Documentation: descriptions required
        story_schema.require_description = True

    elif preset == SchemaPreset.QA:
        # QA: acceptance criteria required
        story_schema.require_acceptance_criteria = True
        story_schema.min_acceptance_criteria = 2

    return story_schema, epic_schema


# =============================================================================
# Main Validator
# =============================================================================


class SchemaValidator:
    """
    Main schema validator for stories, subtasks, and epics.

    Can be used standalone or integrated with parsers.

    Example:
        validator = SchemaValidator(mode=ValidationMode.STRICT)
        result = validator.validate_stories(stories)
        if not result.is_valid:
            raise ValidationError(str(result))
    """

    def __init__(
        self,
        mode: ValidationMode = ValidationMode.NORMAL,
        story_schema: StorySchema | None = None,
        epic_schema: EpicSchema | None = None,
        fail_fast: bool = False,
    ) -> None:
        """
        Initialize validator.

        Args:
            mode: Validation mode (lenient, normal, strict)
            story_schema: Custom story schema (overrides mode)
            epic_schema: Custom epic schema (overrides mode)
            fail_fast: Stop on first error
        """
        self.mode = mode
        self.fail_fast = fail_fast

        if story_schema and epic_schema:
            self.story_schema = story_schema
            self.epic_schema = epic_schema
        else:
            self.story_schema, self.epic_schema = create_schema(mode)

    def validate_story(
        self,
        story: UserStory,
        location: ParseLocation | None = None,
    ) -> ValidationResult:
        """Validate a single story."""
        errors = self.story_schema.validate(story, location=location)

        # Split errors and warnings
        validation_errors = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        validation_warnings = [
            ValidationWarning(
                field=e.field,
                message=e.message,
                value=e.value,
                location=e.location,
                entity_id=e.entity_id,
                entity_type=e.entity_type,
                rule=e.rule,
                suggestion=e.suggestion,
            )
            for e in errors
            if e.severity == ValidationSeverity.WARNING
        ]

        return ValidationResult(
            errors=validation_errors,
            warnings=validation_warnings,
            validated_count=1,
        )

    def validate_stories(
        self,
        stories: list[UserStory],
        source: str | None = None,
    ) -> ValidationResult:
        """Validate a list of stories."""
        result = ValidationResult(source=source)

        for story in stories:
            story_result = self.validate_story(story)
            result = result.merge(story_result)

            if self.fail_fast and not result.is_valid:
                break

        return result

    def validate_epic(
        self,
        epic: Epic,
        location: ParseLocation | None = None,
    ) -> ValidationResult:
        """Validate an epic and its stories."""
        errors = self.epic_schema.validate(epic, location=location)

        # Split errors and warnings
        validation_errors = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        validation_warnings = [
            ValidationWarning(
                field=e.field,
                message=e.message,
                value=e.value,
                location=e.location,
                entity_id=e.entity_id,
                entity_type=e.entity_type,
                rule=e.rule,
                suggestion=e.suggestion,
            )
            for e in errors
            if e.severity == ValidationSeverity.WARNING
        ]

        return ValidationResult(
            errors=validation_errors,
            warnings=validation_warnings,
            validated_count=1 + len(epic.stories),
        )

    def validate_epics(
        self,
        epics: list[Epic],
        source: str | None = None,
    ) -> ValidationResult:
        """Validate a list of epics."""
        result = ValidationResult(source=source)

        for epic in epics:
            epic_result = self.validate_epic(epic)
            result = result.merge(epic_result)

            if self.fail_fast and not result.is_valid:
                break

        return result


# =============================================================================
# Validating Parser Wrapper
# =============================================================================


class ValidatingParser(DocumentParserPort):
    """
    Parser wrapper that adds schema validation.

    Wraps any DocumentParserPort implementation and validates
    the parsed results before returning them.

    Example:
        parser = MarkdownParser()
        validating = ValidatingParser(parser, mode=ValidationMode.STRICT)
        stories = validating.parse_stories("epics.md")  # Validates automatically
    """

    def __init__(
        self,
        parser: DocumentParserPort,
        mode: ValidationMode = ValidationMode.NORMAL,
        validator: SchemaValidator | None = None,
        raise_on_error: bool = True,
        collect_warnings: bool = True,
    ) -> None:
        """
        Initialize validating parser.

        Args:
            parser: The underlying parser to wrap
            mode: Validation mode
            validator: Custom validator (overrides mode)
            raise_on_error: Raise ParserError on validation failure
            collect_warnings: Include warnings in error message
        """
        self._parser = parser
        self._validator = validator or SchemaValidator(mode=mode)
        self._raise_on_error = raise_on_error
        self._collect_warnings = collect_warnings
        self._last_result: ValidationResult | None = None

    @property
    def name(self) -> str:
        """Get the parser name."""
        return f"Validating({self._parser.name})"

    @property
    def supported_extensions(self) -> list[str]:
        """Get list of supported file extensions."""
        return self._parser.supported_extensions

    @property
    def last_validation_result(self) -> ValidationResult | None:
        """Get the result of the last validation."""
        return self._last_result

    def can_parse(self, source: str | Path) -> bool:
        """Check if this parser can handle the given source."""
        return self._parser.can_parse(source)

    def parse_stories(self, source: str | Path) -> list[UserStory]:
        """Parse and validate stories."""
        stories = self._parser.parse_stories(source)
        source_str = str(source) if isinstance(source, Path) else source[:50]

        self._last_result = self._validator.validate_stories(stories, source=source_str)

        if not self._last_result.is_valid and self._raise_on_error:
            error_msg = f"Schema validation failed for {source_str}:\n{self._last_result}"
            raise ParserError(error_msg)

        return stories

    def parse_epic(self, source: str | Path) -> Epic | None:
        """Parse and validate an epic."""
        epic = self._parser.parse_epic(source)
        if epic is None:
            return None

        source_str = str(source) if isinstance(source, Path) else source[:50]
        self._last_result = self._validator.validate_epic(epic)
        self._last_result.source = source_str

        if not self._last_result.is_valid and self._raise_on_error:
            error_msg = f"Schema validation failed for {source_str}:\n{self._last_result}"
            raise ParserError(error_msg)

        return epic

    def validate(self, source: str | Path) -> list[str]:
        """Validate source document with schema validation."""
        # First run parser's own validation
        parser_errors = self._parser.validate(source)

        # Then add schema validation
        try:
            stories = self._parser.parse_stories(source)
            result = self._validator.validate_stories(stories)

            schema_errors = [str(e) for e in result.errors]
            if self._collect_warnings:
                schema_errors.extend([str(w) for w in result.warnings])

            return [*parser_errors, *schema_errors]
        except ParserError as e:
            return [*parser_errors, str(e)]


# =============================================================================
# Factory Functions
# =============================================================================


def create_validator(
    mode: ValidationMode = ValidationMode.NORMAL,
    preset: SchemaPreset | None = None,
    **kwargs: Any,
) -> SchemaValidator:
    """
    Create a schema validator with the specified configuration.

    Args:
        mode: Validation mode
        preset: Optional preset that overrides mode
        **kwargs: Additional arguments passed to SchemaValidator

    Returns:
        Configured SchemaValidator instance
    """
    if preset:
        story_schema, epic_schema = create_schema(preset)
        return SchemaValidator(
            mode=ValidationMode.CUSTOM,
            story_schema=story_schema,
            epic_schema=epic_schema,
            **kwargs,
        )
    return SchemaValidator(mode=mode, **kwargs)
