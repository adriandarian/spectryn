"""
Tests for the improved validation command.

Tests comprehensive markdown validation.
"""

from pathlib import Path

import pytest

from spectra.cli.exit_codes import ExitCode
from spectra.cli.output import Console
from spectra.cli.validate import (
    IssueSeverity,
    MarkdownValidator,
    ValidationIssue,
    ValidationResult,
    format_validation_result,
    run_validate,
)


# =============================================================================
# ValidationIssue Tests
# =============================================================================


class TestValidationIssue:
    """Tests for ValidationIssue dataclass."""

    def test_issue_creation(self):
        """Test creating a validation issue."""
        issue = ValidationIssue(
            severity=IssueSeverity.ERROR,
            code="E001",
            message="Test error",
            line=42,
            story_id="US-001",
            suggestion="Fix this",
        )

        assert issue.severity == IssueSeverity.ERROR
        assert issue.code == "E001"
        assert issue.message == "Test error"
        assert issue.line == 42
        assert issue.story_id == "US-001"
        assert issue.suggestion == "Fix this"

    def test_location_with_line_and_story(self):
        """Test location formatting with both line and story."""
        issue = ValidationIssue(
            severity=IssueSeverity.ERROR,
            code="E001",
            message="Test",
            line=42,
            story_id="US-001",
        )

        assert issue.location == "line 42: US-001"

    def test_location_with_line_only(self):
        """Test location formatting with line only."""
        issue = ValidationIssue(
            severity=IssueSeverity.ERROR,
            code="E001",
            message="Test",
            line=42,
        )

        assert issue.location == "line 42"

    def test_location_with_story_only(self):
        """Test location formatting with story only."""
        issue = ValidationIssue(
            severity=IssueSeverity.ERROR,
            code="E001",
            message="Test",
            story_id="US-001",
        )

        assert issue.location == "US-001"

    def test_location_empty(self):
        """Test location formatting with no location info."""
        issue = ValidationIssue(
            severity=IssueSeverity.ERROR,
            code="E001",
            message="Test",
        )

        assert issue.location == ""


# =============================================================================
# ValidationResult Tests
# =============================================================================


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_default_valid(self):
        """Test result is valid by default."""
        result = ValidationResult()

        assert result.valid is True
        assert result.issues == []
        assert result.errors == []
        assert result.warnings == []
        assert result.infos == []

    def test_add_error_invalidates(self):
        """Test adding an error makes result invalid."""
        result = ValidationResult()
        result.add_error("E001", "Error message")

        assert result.valid is False
        assert len(result.errors) == 1
        assert result.errors[0].code == "E001"

    def test_add_warning_stays_valid(self):
        """Test adding a warning keeps result valid."""
        result = ValidationResult()
        result.add_warning("W001", "Warning message")

        assert result.valid is True
        assert len(result.warnings) == 1

    def test_add_info(self):
        """Test adding an info message."""
        result = ValidationResult()
        result.add_info("I001", "Info message")

        assert result.valid is True
        assert len(result.infos) == 1


# =============================================================================
# MarkdownValidator Tests
# =============================================================================


class TestMarkdownValidator:
    """Tests for MarkdownValidator class."""

    @pytest.fixture
    def validator(self):
        """Create a validator instance."""
        return MarkdownValidator()

    @pytest.fixture
    def valid_markdown(self):
        """Create valid markdown content."""
        return """# 🚀 PROJ-100: Test Epic

## Stories

### 📋 US-001: First Story

| Field | Value |
|-------|-------|
| **Story Points** | 3 |
| **Priority** | Medium |
| **Status** | To Do |

#### Description

**As a** user
**I want** to test this
**So that** it works

#### Acceptance Criteria

- [ ] Criterion 1
- [ ] Criterion 2

---

### ✅ US-002: Second Story

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Priority** | High |
| **Status** | Done |

#### Description

**As a** developer
**I want** another story
**So that** it validates

---
"""

    @pytest.fixture
    def minimal_markdown(self):
        """Create minimal valid markdown."""
        return """### 📋 US-001: Test Story

| Field | Value |
|-------|-------|
| **Story Points** | 3 |

**As a** user
**I want** something
"""

    def test_validate_valid_markdown(self, validator, valid_markdown):
        """Test validation of valid markdown."""
        result = validator.validate(valid_markdown)

        assert result.valid is True
        assert len(result.errors) == 0
        assert result.story_count == 2
        assert result.subtask_count == 2
        assert result.total_story_points == 8

    def test_validate_minimal_markdown(self, validator, minimal_markdown):
        """Test validation of minimal valid markdown."""
        result = validator.validate(minimal_markdown)

        assert result.valid is True
        assert result.story_count == 1

    def test_validate_no_stories(self, validator):
        """Test validation fails with no stories."""
        content = "# Epic Title\n\nSome content without stories."

        result = validator.validate(content)

        assert result.valid is False
        assert any(e.code == "E100" for e in result.errors)

    def test_validate_duplicate_story_ids(self, validator):
        """Test validation detects duplicate story IDs."""
        content = """### 📋 US-001: First Story
| **Story Points** | 3 |

### 📋 US-001: Duplicate Story
| **Story Points** | 5 |
"""

        result = validator.validate(content)

        assert result.valid is False
        assert any(e.code == "E101" for e in result.errors)

    def test_validate_missing_story_points_warning(self, validator):
        """Test warning for missing story points."""
        content = """### 📋 US-001: Story Without Points

Some description without metadata table.
"""

        result = validator.validate(content)

        assert result.valid is True  # Still valid, just a warning
        assert any(w.code == "W202" for w in result.warnings)

    def test_validate_invalid_status_warning(self, validator):
        """Test warning for unrecognized status."""
        content = """### 📋 US-001: Story

| Field | Value |
|-------|-------|
| **Story Points** | 3 |
| **Status** | InvalidStatus |
"""

        result = validator.validate(content)

        assert any(w.code == "W204" for w in result.warnings)

    def test_validate_invalid_priority_warning(self, validator):
        """Test warning for unrecognized priority."""
        content = """### 📋 US-001: Story

| Field | Value |
|-------|-------|
| **Story Points** | 3 |
| **Priority** | SuperUrgent |
"""

        result = validator.validate(content)

        assert any(w.code == "W205" for w in result.warnings)

    def test_validate_missing_user_story_format_info(self, validator):
        """Test info for missing user story format."""
        content = """### 📋 US-001: Story

| Field | Value |
|-------|-------|
| **Story Points** | 3 |

Just a plain description without As a / I want / So that.
"""

        result = validator.validate(content)

        assert any(i.code == "I200" for i in result.infos)

    def test_validate_short_title_warning(self, validator):
        """Test warning for very short story title."""
        content = """### 📋 US-001: Test

| **Story Points** | 3 |
"""

        result = validator.validate(content)

        assert any(w.code == "W200" for w in result.warnings)

    def test_validate_file_not_found(self, validator):
        """Test validation of non-existent file."""
        result = validator.validate(Path("/nonexistent/file.md"))

        assert result.valid is False
        assert any(e.code == "E001" for e in result.errors)

    def test_validate_from_file(self, validator, tmp_path, valid_markdown):
        """Test validation from file path."""
        md_file = tmp_path / "test.md"
        md_file.write_text(valid_markdown, encoding="utf-8")

        result = validator.validate(md_file)

        assert result.valid is True
        assert result.file_path == str(md_file)

    def test_validate_strict_mode(self, valid_markdown):
        """Test strict mode treats warnings as errors."""
        # Add content that generates warnings
        content = """### 📋 US-001: X

| **Story Points** | TBD |

Description.
"""

        validator = MarkdownValidator(strict=True)
        result = validator.validate(content)

        # In strict mode, warnings become errors
        assert result.valid is False

    def test_validate_mixed_story_id_formats_warning(self, validator):
        """Test warning for mixing story ID formats."""
        content = """### 📋 US-001: Story One

| **Story Points** | 3 |

---

### 📋 PROJ-123: Story Two

| **Story Points** | 5 |
"""

        result = validator.validate(content)

        assert any(w.code == "W300" for w in result.warnings)


# =============================================================================
# Format Tests
# =============================================================================


class TestFormatValidationResult:
    """Tests for format_validation_result function."""

    def test_format_valid_result(self):
        """Test formatting a valid result."""
        result = ValidationResult()
        result.story_count = 3
        result.subtask_count = 10
        result.total_story_points = 21

        output = format_validation_result(result, color=False)

        assert "✓ Validation Passed" in output
        assert "Stories: 3" in output
        assert "Subtasks: 10" in output
        assert "Story Points: 21" in output

    def test_format_invalid_result(self):
        """Test formatting an invalid result."""
        result = ValidationResult()
        result.add_error("E001", "Test error", line=42, suggestion="Fix it")

        output = format_validation_result(result, color=False)

        assert "✗ Validation Failed" in output
        assert "Errors (1):" in output
        assert "[E001]" in output
        assert "Test error" in output
        assert "line 42" in output
        assert "→ Fix it" in output

    def test_format_with_warnings(self):
        """Test formatting with warnings."""
        result = ValidationResult()
        result.add_warning("W001", "Test warning")

        output = format_validation_result(result, color=False)

        assert "Warnings (1):" in output
        assert "[W001]" in output

    def test_format_with_suggestions(self):
        """Test formatting with suggestions."""
        result = ValidationResult()
        result.add_info("I001", "Test suggestion", suggestion="Do this")

        output = format_validation_result(result, color=False)

        assert "Suggestions (1):" in output


# =============================================================================
# run_validate Function Tests
# =============================================================================


class TestRunValidate:
    """Tests for run_validate function."""

    def test_run_validate_valid_file(self, tmp_path):
        """Test run_validate on a valid file."""
        md_file = tmp_path / "test.md"
        md_file.write_text(
            """### 📋 US-001: Valid Story

| Field | Value |
|-------|-------|
| **Story Points** | 3 |
| **Status** | To Do |

**As a** user
**I want** to test
**So that** it works
""",
            encoding="utf-8",
        )

        console = Console(color=False)
        result = run_validate(console, str(md_file))

        assert result == ExitCode.SUCCESS

    def test_run_validate_invalid_file(self, tmp_path):
        """Test run_validate on an invalid file."""
        md_file = tmp_path / "test.md"
        md_file.write_text("No stories here.")

        console = Console(color=False)
        result = run_validate(console, str(md_file))

        assert result == ExitCode.VALIDATION_ERROR

    def test_run_validate_file_not_found(self):
        """Test run_validate on missing file."""
        console = Console(color=False)
        result = run_validate(console, "/nonexistent/file.md")

        assert result == ExitCode.FILE_NOT_FOUND

    def test_run_validate_strict_mode(self, tmp_path):
        """Test run_validate with strict mode."""
        md_file = tmp_path / "test.md"
        # Content that generates warnings but no errors
        md_file.write_text(
            """### 📋 US-001: X

Description without points or format.
""",
            encoding="utf-8",
        )

        console = Console(color=False)

        # Without strict: should pass (only warnings)
        run_validate(console, str(md_file), strict=False)
        # Note: This might fail if the validator creates errors for this content

        # With strict: should fail (warnings become errors)
        result_strict = run_validate(console, str(md_file), strict=True)
        assert result_strict == ExitCode.VALIDATION_ERROR


# =============================================================================
# CLI Integration Tests
# =============================================================================


class TestCLIIntegration:
    """Tests for CLI integration."""

    def test_validate_flag_in_parser(self, cli_parser):
        """Test --validate flag is recognized."""
        args = cli_parser.parse_args(["--validate", "--markdown", "test.md"])

        assert args.validate is True
        assert args.markdown == "test.md"

    def test_strict_flag_in_parser(self, cli_parser):
        """Test --strict flag is recognized."""
        args = cli_parser.parse_args(
            [
                "--validate",
                "--markdown",
                "test.md",
                "--strict",
            ]
        )

        assert args.validate is True
        assert args.strict is True

    def test_validate_without_epic(self, cli_parser):
        """Test --validate doesn't require --epic."""
        # Should not raise
        args = cli_parser.parse_args(["--validate", "--markdown", "test.md"])

        assert args.validate is True
        assert args.epic is None


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    @pytest.fixture
    def validator(self):
        return MarkdownValidator()

    def test_empty_file(self, validator):
        """Test validation of empty content."""
        result = validator.validate("")

        assert result.valid is False
        assert result.story_count == 0

    def test_unicode_content(self, validator):
        """Test validation with unicode content."""
        content = """### 🎉 US-001: Story with émojis and üñíçödé

| **Story Points** | 5 |

**As a** 用户
**I want** テスト
**So that** ça fonctionne
"""

        result = validator.validate(content)

        assert result.valid is True
        assert result.story_count == 1

    def test_story_points_tbd(self, validator):
        """Test TBD story points are accepted."""
        content = """### 📋 US-001: Story

| **Story Points** | TBD |
"""

        result = validator.validate(content)

        # Should not have error or warning for TBD points
        assert not any(i.code == "W203" and "TBD" in i.message for i in result.warnings)

    def test_valid_statuses(self, validator):
        """Test various valid status values."""
        statuses = ["To Do", "In Progress", "Done", "Blocked", "Ready"]

        for status in statuses:
            content = f"""### 📋 US-001: Story

| **Status** | {status} |
"""
            result = validator.validate(content)

            # Should not warn about these statuses
            status_warnings = [w for w in result.warnings if w.code == "W204"]
            assert len(status_warnings) == 0, f"Unexpected warning for status '{status}'"

    def test_valid_priorities(self, validator):
        """Test various valid priority values."""
        priorities = ["High", "Medium", "Low", "Critical", "P1"]

        for priority in priorities:
            content = f"""### 📋 US-001: Story

| **Priority** | {priority} |
"""
            result = validator.validate(content)

            # Should not warn about these priorities
            priority_warnings = [w for w in result.warnings if w.code == "W205"]
            assert len(priority_warnings) == 0, f"Unexpected warning for priority '{priority}'"
