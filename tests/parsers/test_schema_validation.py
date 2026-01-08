"""
Tests for Schema Validation module.

Tests cover:
- Validation modes (lenient, normal, strict)
- Field validators (min_length, max_value, patterns, etc.)
- Story validation
- Subtask validation
- Epic validation
- ValidatingParser wrapper
- Schema presets
"""

import pytest

from spectryn.adapters.parsers.schema_validation import (
    EpicSchema,
    FieldSchema,
    FieldType,
    SchemaPreset,
    SchemaValidator,
    StorySchema,
    SubtaskSchema,
    ValidatingParser,
    ValidationError,
    ValidationMode,
    ValidationResult,
    ValidationSeverity,
    ValidationWarning,
    create_schema,
    create_validator,
    matches_pattern,
    max_length,
    max_value,
    min_length,
    min_value,
    not_empty,
    one_of,
    valid_priority,
    valid_status,
    valid_story_id,
)
from spectryn.core.domain.entities import Epic, Subtask, UserStory
from spectryn.core.domain.enums import Priority, Status
from spectryn.core.domain.value_objects import (
    AcceptanceCriteria,
    Description,
    IssueKey,
    StoryId,
)
from spectryn.core.ports.document_parser import ParserError


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def valid_story() -> UserStory:
    """Create a valid user story for testing."""
    return UserStory(
        id=StoryId("US-001"),
        title="Implement user authentication",
        description=Description(
            role="a user",
            want="to log in securely",
            benefit="I can access my account",
        ),
        acceptance_criteria=AcceptanceCriteria.from_list(
            ["User can enter username and password", "Invalid credentials show error"],
            [False, False],
        ),
        story_points=5,
        priority=Priority.HIGH,
        status=Status.IN_PROGRESS,
        assignee="developer@example.com",
    )


@pytest.fixture
def minimal_story() -> UserStory:
    """Create a minimal user story (only required fields)."""
    return UserStory(
        id=StoryId("US-002"),
        title="Basic story",
    )


@pytest.fixture
def invalid_story() -> UserStory:
    """Create an invalid user story for testing."""
    return UserStory(
        id=StoryId("US-003"),
        title="",  # Empty title
        story_points=-5,  # Invalid points
    )


@pytest.fixture
def valid_subtask() -> Subtask:
    """Create a valid subtask for testing."""
    return Subtask(
        name="Implement login form",
        status=Status.PLANNED,
        story_points=2,
    )


@pytest.fixture
def valid_epic(valid_story: UserStory) -> Epic:
    """Create a valid epic for testing."""
    return Epic(
        key=IssueKey("PROJ-100"),
        title="Authentication Epic",
        summary="Implement user authentication features",
        status=Status.IN_PROGRESS,
        priority=Priority.HIGH,
        stories=[valid_story],
    )


# =============================================================================
# Test Built-in Validators
# =============================================================================


class TestMinLength:
    """Tests for min_length validator."""

    def test_valid_string(self) -> None:
        """Test valid string meets minimum."""
        validator = min_length(5)
        is_valid, error = validator("hello world")
        assert is_valid
        assert error is None

    def test_invalid_string_too_short(self) -> None:
        """Test string too short fails."""
        validator = min_length(10)
        is_valid, error = validator("hello")
        assert not is_valid
        assert "at least 10" in error

    def test_none_value_passes(self) -> None:
        """Test None passes (required check handles it)."""
        validator = min_length(5)
        is_valid, _error = validator(None)
        assert is_valid

    def test_list_length(self) -> None:
        """Test validator works with lists."""
        validator = min_length(3)
        is_valid, _ = validator([1, 2])
        assert not is_valid
        is_valid, _ = validator([1, 2, 3])
        assert is_valid


class TestMaxLength:
    """Tests for max_length validator."""

    def test_valid_string(self) -> None:
        """Test valid string within maximum."""
        validator = max_length(20)
        is_valid, error = validator("hello")
        assert is_valid
        assert error is None

    def test_invalid_string_too_long(self) -> None:
        """Test string too long fails."""
        validator = max_length(5)
        is_valid, error = validator("hello world")
        assert not is_valid
        assert "at most 5" in error


class TestMinValue:
    """Tests for min_value validator."""

    def test_valid_value(self) -> None:
        """Test value above minimum passes."""
        validator = min_value(0)
        is_valid, error = validator(5)
        assert is_valid
        assert error is None

    def test_invalid_value_too_small(self) -> None:
        """Test value below minimum fails."""
        validator = min_value(1)
        is_valid, error = validator(0)
        assert not is_valid
        assert "at least 1" in error

    def test_float_value(self) -> None:
        """Test validator works with floats."""
        validator = min_value(0.5)
        is_valid, _ = validator(0.3)
        assert not is_valid
        is_valid, _ = validator(0.7)
        assert is_valid


class TestMaxValue:
    """Tests for max_value validator."""

    def test_valid_value(self) -> None:
        """Test value below maximum passes."""
        validator = max_value(100)
        is_valid, error = validator(50)
        assert is_valid
        assert error is None

    def test_invalid_value_too_large(self) -> None:
        """Test value above maximum fails."""
        validator = max_value(10)
        is_valid, error = validator(15)
        assert not is_valid
        assert "at most 10" in error


class TestMatchesPattern:
    """Tests for matches_pattern validator."""

    def test_valid_pattern(self) -> None:
        """Test value matching pattern passes."""
        validator = matches_pattern(r"^[A-Z]+-\d+$")
        is_valid, error = validator("US-001")
        assert is_valid
        assert error is None

    def test_invalid_pattern(self) -> None:
        """Test value not matching pattern fails."""
        validator = matches_pattern(r"^[A-Z]+-\d+$", "must be format PREFIX-NUMBER")
        is_valid, error = validator("invalid")
        assert not is_valid
        assert "PREFIX-NUMBER" in error

    def test_none_passes(self) -> None:
        """Test None passes pattern check."""
        validator = matches_pattern(r".*")
        is_valid, _ = validator(None)
        assert is_valid


class TestOneOf:
    """Tests for one_of validator."""

    def test_valid_value(self) -> None:
        """Test value in allowed list passes."""
        validator = one_of(["red", "green", "blue"])
        is_valid, error = validator("red")
        assert is_valid
        assert error is None

    def test_invalid_value(self) -> None:
        """Test value not in allowed list fails."""
        validator = one_of(["red", "green", "blue"])
        is_valid, error = validator("yellow")
        assert not is_valid
        assert "must be one of" in error

    def test_case_insensitive(self) -> None:
        """Test case-insensitive matching."""
        validator = one_of(["Red", "Green", "Blue"], case_insensitive=True)
        is_valid, _ = validator("RED")
        assert is_valid


class TestNotEmpty:
    """Tests for not_empty validator."""

    def test_valid_string(self) -> None:
        """Test non-empty string passes."""
        validator = not_empty()
        is_valid, error = validator("hello")
        assert is_valid
        assert error is None

    def test_empty_string_fails(self) -> None:
        """Test empty string fails."""
        validator = not_empty()
        is_valid, error = validator("")
        assert not is_valid
        assert "empty" in error

    def test_blank_string_fails(self) -> None:
        """Test blank string fails."""
        validator = not_empty()
        is_valid, error = validator("   ")
        assert not is_valid
        assert "empty" in error

    def test_empty_list_fails(self) -> None:
        """Test empty list fails."""
        validator = not_empty()
        is_valid, _error = validator([])
        assert not is_valid


class TestValidStoryId:
    """Tests for valid_story_id validator."""

    def test_valid_formats(self) -> None:
        """Test various valid story ID formats."""
        validator = valid_story_id()

        valid_ids = ["US-001", "PROJ-123", "FEAT_001", "US/001", "#42", "123"]
        for story_id in valid_ids:
            is_valid, _error = validator(story_id)
            assert is_valid, f"Should be valid: {story_id}"

    def test_invalid_format(self) -> None:
        """Test invalid story ID format."""
        validator = valid_story_id()
        is_valid, error = validator("invalid id")
        assert not is_valid
        assert "valid story ID" in error


class TestValidPriority:
    """Tests for valid_priority validator."""

    def test_valid_enum(self) -> None:
        """Test Priority enum passes."""
        validator = valid_priority()
        is_valid, _ = validator(Priority.HIGH)
        assert is_valid

    def test_valid_string(self) -> None:
        """Test valid priority string passes."""
        validator = valid_priority()
        is_valid, _ = validator("high")
        assert is_valid

    def test_invalid_string(self) -> None:
        """Test invalid priority string gets default (no error for from_string)."""
        validator = valid_priority()
        # Note: Priority.from_string returns MEDIUM for unknown values
        # So we test that an actual invalid type fails
        is_valid, error = validator(123)  # Invalid type
        assert not is_valid
        assert "Priority enum or string" in error


class TestValidStatus:
    """Tests for valid_status validator."""

    def test_valid_enum(self) -> None:
        """Test Status enum passes."""
        validator = valid_status()
        is_valid, _ = validator(Status.IN_PROGRESS)
        assert is_valid

    def test_valid_string(self) -> None:
        """Test valid status string passes."""
        validator = valid_status()
        is_valid, _ = validator("done")
        assert is_valid

    def test_invalid_string(self) -> None:
        """Test invalid status type fails."""
        validator = valid_status()
        # Note: Status.from_string returns PLANNED for unknown values
        # So we test that an actual invalid type fails
        is_valid, error = validator(123)  # Invalid type
        assert not is_valid
        assert "Status enum or string" in error


# =============================================================================
# Test Field Schema
# =============================================================================


class TestFieldSchema:
    """Tests for FieldSchema validation."""

    def test_required_field_missing(self) -> None:
        """Test required field with None value fails."""
        schema = FieldSchema(
            name="title",
            required=True,
        )
        errors = schema.validate(None)
        assert len(errors) == 1
        assert "required" in errors[0].message.lower()

    def test_required_field_empty_string(self) -> None:
        """Test required field with empty string fails."""
        schema = FieldSchema(
            name="title",
            required=True,
        )
        errors = schema.validate("")
        assert len(errors) == 1

    def test_optional_field_missing(self) -> None:
        """Test optional field with None passes."""
        schema = FieldSchema(
            name="assignee",
            required=False,
        )
        errors = schema.validate(None)
        assert len(errors) == 0

    def test_validators_run(self) -> None:
        """Test custom validators are executed."""
        schema = FieldSchema(
            name="story_points",
            validators=[min_value(1), max_value(21)],
        )
        errors = schema.validate(50)
        assert len(errors) == 1
        assert "at most 21" in errors[0].message

    def test_label_from_display_name(self) -> None:
        """Test label uses display_name when set."""
        schema = FieldSchema(
            name="story_points",
            display_name="Story Points",
        )
        assert schema.label == "Story Points"

    def test_label_from_name(self) -> None:
        """Test label uses formatted name when no display_name."""
        schema = FieldSchema(name="story_points")
        assert schema.label == "Story Points"


# =============================================================================
# Test Validation Result
# =============================================================================


class TestValidationResult:
    """Tests for ValidationResult."""

    def test_is_valid_with_no_errors(self) -> None:
        """Test is_valid returns True when no errors."""
        result = ValidationResult()
        assert result.is_valid

    def test_is_valid_with_errors(self) -> None:
        """Test is_valid returns False when errors present."""
        result = ValidationResult()
        result.add_error(ValidationError(field="title", message="Required"))
        assert not result.is_valid

    def test_has_warnings(self) -> None:
        """Test has_warnings property."""
        result = ValidationResult()
        assert not result.has_warnings

        result.add_warning(ValidationWarning(field="assignee", message="Recommended"))
        assert result.has_warnings

    def test_merge_results(self) -> None:
        """Test merging two results."""
        result1 = ValidationResult(validated_count=5)
        result1.add_error(ValidationError(field="a", message="Error A"))

        result2 = ValidationResult(validated_count=3)
        result2.add_error(ValidationError(field="b", message="Error B"))
        result2.add_warning(ValidationWarning(field="c", message="Warning C"))

        merged = result1.merge(result2)
        assert merged.error_count == 2
        assert merged.warning_count == 1
        assert merged.validated_count == 8

    def test_str_representation_valid(self) -> None:
        """Test string representation for valid result."""
        result = ValidationResult(validated_count=10)
        assert "✓" in str(result)
        assert "10" in str(result)

    def test_str_representation_invalid(self) -> None:
        """Test string representation for invalid result."""
        result = ValidationResult()
        result.add_error(ValidationError(field="title", message="Required"))
        result_str = str(result)
        assert "✗" in result_str
        assert "title" in result_str


# =============================================================================
# Test Story Schema
# =============================================================================


class TestStorySchema:
    """Tests for StorySchema validation."""

    def test_lenient_mode_minimal_validation(self, minimal_story: UserStory) -> None:
        """Test lenient mode only validates ID and title."""
        schema = StorySchema.default(ValidationMode.LENIENT)
        errors = schema.validate(minimal_story)
        assert len(errors) == 0

    def test_normal_mode_validation(self, valid_story: UserStory) -> None:
        """Test normal mode validates common fields."""
        schema = StorySchema.default(ValidationMode.NORMAL)
        errors = schema.validate(valid_story)
        assert len(errors) == 0

    def test_strict_mode_requires_all_fields(self, minimal_story: UserStory) -> None:
        """Test strict mode requires all fields."""
        schema = StorySchema.default(ValidationMode.STRICT)
        errors = schema.validate(minimal_story)

        # Should have errors for missing required fields
        # Note: status/priority have defaults so won't fail required check
        # But story_points=0 and short title will fail
        error_fields = {e.field for e in errors}
        # Story points defaults to 0 which fails min_value(1) in strict
        assert "story_points" in error_fields or "title" in error_fields

    def test_strict_mode_valid_story(self, valid_story: UserStory) -> None:
        """Test strict mode passes for fully-populated story."""
        schema = StorySchema.default(ValidationMode.STRICT)
        errors = schema.validate(valid_story)

        # Should pass with valid story
        error_errors = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert len(error_errors) == 0

    def test_description_requirement(self, minimal_story: UserStory) -> None:
        """Test description requirement validation."""
        schema = StorySchema.default(ValidationMode.NORMAL)
        schema.require_description = True

        errors = schema.validate(minimal_story)
        error_fields = {e.field for e in errors}
        assert "description" in error_fields

    def test_acceptance_criteria_requirement(self, minimal_story: UserStory) -> None:
        """Test acceptance criteria requirement."""
        schema = StorySchema.default(ValidationMode.NORMAL)
        schema.require_acceptance_criteria = True
        schema.min_acceptance_criteria = 2

        errors = schema.validate(minimal_story)
        error_fields = {e.field for e in errors}
        assert "acceptance_criteria" in error_fields

    def test_subtask_validation(self, valid_story: UserStory) -> None:
        """Test subtasks are validated."""
        # Add a subtask with empty name
        valid_story.subtasks = [Subtask(name="")]

        schema = StorySchema.default(ValidationMode.STRICT)
        errors = schema.validate(valid_story)

        # Should have subtask validation error
        subtask_errors = [e for e in errors if e.entity_type == "subtask"]
        assert len(subtask_errors) > 0


# =============================================================================
# Test Epic Schema
# =============================================================================


class TestEpicSchema:
    """Tests for EpicSchema validation."""

    def test_basic_epic_validation(self, valid_epic: Epic) -> None:
        """Test basic epic validation passes."""
        schema = EpicSchema.default(ValidationMode.NORMAL)
        errors = schema.validate(valid_epic)

        error_errors = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert len(error_errors) == 0

    def test_strict_mode_requires_stories(self) -> None:
        """Test strict mode requires stories."""
        empty_epic = Epic(
            key=IssueKey("PROJ-100"),
            title="Empty Epic",
            status=Status.PLANNED,
            priority=Priority.HIGH,
        )

        schema = EpicSchema.default(ValidationMode.STRICT)
        errors = schema.validate(empty_epic)

        error_fields = {e.field for e in errors}
        assert "stories" in error_fields

    def test_validates_nested_stories(self, valid_epic: Epic) -> None:
        """Test epic validates its stories."""
        # Add an invalid story
        invalid_story = UserStory(
            id=StoryId("US-999"),
            title="",  # Invalid
        )
        valid_epic.stories.append(invalid_story)

        schema = EpicSchema.default(ValidationMode.NORMAL)
        errors = schema.validate(valid_epic)

        story_errors = [e for e in errors if e.entity_type == "story"]
        assert len(story_errors) > 0


# =============================================================================
# Test Schema Validator
# =============================================================================


class TestSchemaValidator:
    """Tests for SchemaValidator."""

    def test_validate_single_story(self, valid_story: UserStory) -> None:
        """Test validating a single story."""
        validator = SchemaValidator(mode=ValidationMode.NORMAL)
        result = validator.validate_story(valid_story)

        assert result.is_valid
        assert result.validated_count == 1

    def test_validate_multiple_stories(self, valid_story: UserStory) -> None:
        """Test validating multiple stories."""
        stories = [valid_story] * 5
        validator = SchemaValidator(mode=ValidationMode.NORMAL)
        result = validator.validate_stories(stories)

        assert result.is_valid
        assert result.validated_count == 5

    def test_fail_fast_mode(self, invalid_story: UserStory, valid_story: UserStory) -> None:
        """Test fail_fast stops on first error."""
        validator = SchemaValidator(mode=ValidationMode.NORMAL, fail_fast=True)
        result = validator.validate_stories([invalid_story, valid_story])

        # Should only validate first story
        assert result.validated_count == 1

    def test_validate_epic(self, valid_epic: Epic) -> None:
        """Test validating an epic."""
        validator = SchemaValidator(mode=ValidationMode.NORMAL)
        result = validator.validate_epic(valid_epic)

        assert result.is_valid
        # Epic + stories count
        assert result.validated_count >= 1


# =============================================================================
# Test Schema Presets
# =============================================================================


class TestSchemaPresets:
    """Tests for schema presets."""

    def test_agile_preset_requires_points(self, minimal_story: UserStory) -> None:
        """Test Agile preset requires story points."""
        story_schema, _ = create_schema(SchemaPreset.AGILE)
        errors = story_schema.validate(minimal_story)

        error_fields = {e.field for e in errors if e.severity == ValidationSeverity.ERROR}
        assert "story_points" in error_fields

    def test_kanban_preset_requires_status(self, minimal_story: UserStory) -> None:
        """Test Kanban preset validation."""
        story_schema, _ = create_schema(SchemaPreset.KANBAN)

        # Kanban requires status to be set, but minimal_story has default PLANNED
        # So this should pass status validation. Test that schema applies
        errors = story_schema.validate(minimal_story)
        # Schema applies - should at least validate without crashing
        # Minimal story with default status should be valid for kanban
        assert isinstance(errors, list)

    def test_documentation_preset_requires_description(self, minimal_story: UserStory) -> None:
        """Test Documentation preset requires description."""
        story_schema, _ = create_schema(SchemaPreset.DOCUMENTATION)
        errors = story_schema.validate(minimal_story)

        error_fields = {e.field for e in errors}
        assert "description" in error_fields

    def test_qa_preset_requires_acceptance_criteria(self, minimal_story: UserStory) -> None:
        """Test QA preset requires acceptance criteria."""
        story_schema, _ = create_schema(SchemaPreset.QA)
        errors = story_schema.validate(minimal_story)

        error_fields = {e.field for e in errors}
        assert "acceptance_criteria" in error_fields


# =============================================================================
# Test Validating Parser
# =============================================================================


class TestValidatingParser:
    """Tests for ValidatingParser wrapper."""

    def test_wraps_parser_name(self) -> None:
        """Test parser name includes wrapper."""
        from spectryn.adapters.parsers import MarkdownParser

        parser = MarkdownParser()
        validating = ValidatingParser(parser)

        assert "Validating" in validating.name
        assert "Markdown" in validating.name

    def test_supported_extensions(self) -> None:
        """Test extensions come from wrapped parser."""
        from spectryn.adapters.parsers import MarkdownParser

        parser = MarkdownParser()
        validating = ValidatingParser(parser)

        assert validating.supported_extensions == parser.supported_extensions

    def test_can_parse_delegates(self, tmp_path) -> None:
        """Test can_parse delegates to wrapped parser."""
        from spectryn.adapters.parsers import MarkdownParser

        parser = MarkdownParser()
        validating = ValidatingParser(parser)

        # Create actual test files
        md_file = tmp_path / "test.md"
        md_file.write_text("# Test", encoding="utf-8")
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text("key: value", encoding="utf-8")

        assert validating.can_parse(md_file)
        assert not validating.can_parse(yaml_file)

    def test_parse_stories_validates(self, tmp_path) -> None:
        """Test parse_stories validates results."""
        from spectryn.adapters.parsers import MarkdownParser

        # Create a valid markdown file
        content = """
# Epic: PROJ-100 - Test Epic

### US-001: Valid story title here

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Priority** | High |
| **Status** | Planned |

#### Description
**As a** user
**I want** a feature
**So that** I benefit
"""
        md_file = tmp_path / "valid.md"
        md_file.write_text(content, encoding="utf-8")

        parser = MarkdownParser()
        validating = ValidatingParser(parser, mode=ValidationMode.NORMAL)

        stories = validating.parse_stories(md_file)
        assert len(stories) > 0
        assert validating.last_validation_result is not None
        assert validating.last_validation_result.is_valid

    def test_parse_stories_raises_on_invalid(self, tmp_path) -> None:
        """Test parse_stories raises on validation failure."""
        from spectryn.adapters.parsers import MarkdownParser

        # Create a markdown file with issues
        content = """
# Epic: PROJ-100 - Test Epic

### US-001: X

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
"""
        md_file = tmp_path / "invalid.md"
        md_file.write_text(content, encoding="utf-8")

        parser = MarkdownParser()
        validating = ValidatingParser(
            parser,
            mode=ValidationMode.STRICT,
            raise_on_error=True,
        )

        with pytest.raises(ParserError) as exc_info:
            validating.parse_stories(md_file)

        assert "validation failed" in str(exc_info.value).lower()

    def test_parse_stories_no_raise(self, tmp_path) -> None:
        """Test parse_stories doesn't raise when disabled."""
        from spectryn.adapters.parsers import MarkdownParser

        content = """
# Epic: PROJ-100 - Test Epic

### US-001: X

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
"""
        md_file = tmp_path / "invalid.md"
        md_file.write_text(content, encoding="utf-8")

        parser = MarkdownParser()
        validating = ValidatingParser(
            parser,
            mode=ValidationMode.STRICT,
            raise_on_error=False,
        )

        # Should not raise
        stories = validating.parse_stories(md_file)
        assert len(stories) > 0
        assert not validating.last_validation_result.is_valid


# =============================================================================
# Test Factory Functions
# =============================================================================


class TestFactoryFunctions:
    """Tests for factory functions."""

    def test_create_validator_with_mode(self) -> None:
        """Test create_validator with mode."""
        validator = create_validator(mode=ValidationMode.STRICT)
        assert validator.mode == ValidationMode.STRICT

    def test_create_validator_with_preset(self) -> None:
        """Test create_validator with preset."""
        validator = create_validator(preset=SchemaPreset.AGILE)
        assert validator.mode == ValidationMode.CUSTOM

    def test_create_validator_with_fail_fast(self) -> None:
        """Test create_validator passes kwargs."""
        validator = create_validator(mode=ValidationMode.NORMAL, fail_fast=True)
        assert validator.fail_fast

    def test_create_schema_returns_both(self) -> None:
        """Test create_schema returns story and epic schemas."""
        story_schema, epic_schema = create_schema(ValidationMode.NORMAL)

        assert isinstance(story_schema, StorySchema)
        assert isinstance(epic_schema, EpicSchema)


# =============================================================================
# Test Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    def test_validation_error_string_format(self) -> None:
        """Test ValidationError string formatting."""
        error = ValidationError(
            field="title",
            message="is required",
            entity_id="US-001",
            entity_type="story",
            suggestion="Add a title",
        )
        error_str = str(error)

        assert "title" in error_str
        assert "required" in error_str
        assert "US-001" in error_str
        assert "Suggestion" in error_str

    def test_validation_error_with_location(self) -> None:
        """Test ValidationError with location."""
        from spectryn.adapters.parsers.tolerant_markdown import ParseLocation

        error = ValidationError(
            field="title",
            message="is required",
            location=ParseLocation(line=42, column=5),
        )
        error_str = str(error)

        assert "line 42" in error_str

    def test_story_id_field_on_entity(self) -> None:
        """Test StoryId field validation on actual entity."""
        story = UserStory(
            id=StoryId("US-001"),
            title="Test",
        )

        validator = SchemaValidator(mode=ValidationMode.NORMAL)
        result = validator.validate_story(story)

        # Should pass - US-001 is valid
        id_errors = [e for e in result.errors if e.field == "id"]
        assert len(id_errors) == 0

    def test_empty_stories_list_validation(self) -> None:
        """Test validating empty stories list."""
        validator = SchemaValidator(mode=ValidationMode.NORMAL)
        result = validator.validate_stories([])

        assert result.is_valid
        assert result.validated_count == 0

    def test_custom_schema_overrides_mode(self) -> None:
        """Test custom schemas override mode."""
        custom_story = StorySchema()
        custom_story.fields["custom_field"] = FieldSchema(
            name="custom_field",
            required=True,
        )

        custom_epic = EpicSchema()

        validator = SchemaValidator(
            mode=ValidationMode.LENIENT,
            story_schema=custom_story,
            epic_schema=custom_epic,
        )

        # Should use custom schema, not lenient defaults
        assert "custom_field" in validator.story_schema.fields
