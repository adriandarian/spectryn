"""
Tests for backup sanitizer module.

Tests cover:
- Backup data sanitization
- Issue description redaction
- Metadata sanitization
- Embedded secret detection
"""

import pytest

from spectra.core.security.backup_sanitizer import (
    BACKUP_SENSITIVE_PATTERNS,
    BackupSanitizer,
    SanitizationResult,
    create_sanitizer,
    sanitize_backup_data,
)
from spectra.core.security.redactor import SecretRedactor


class TestSanitizationResult:
    """Tests for SanitizationResult."""

    def test_was_sanitized_true(self) -> None:
        """Should return True when fields were sanitized."""
        result = SanitizationResult(fields_sanitized=1)
        assert result.was_sanitized is True

    def test_was_sanitized_false(self) -> None:
        """Should return False when no fields were sanitized."""
        result = SanitizationResult()
        assert result.was_sanitized is False


class TestBackupSanitizer:
    """Tests for BackupSanitizer class."""

    def test_init_default(self) -> None:
        """Should initialize with global redactor."""
        sanitizer = BackupSanitizer()
        assert sanitizer.redactor is not None

    def test_init_custom_redactor(self) -> None:
        """Should use custom redactor."""
        redactor = SecretRedactor()
        sanitizer = BackupSanitizer(redactor)
        assert sanitizer.redactor is redactor


class TestSanitizeDict:
    """Tests for sanitize_dict method."""

    def test_sanitize_metadata_token(self) -> None:
        """Should sanitize tokens in metadata."""
        data = {
            "backup_id": "backup-123",
            "metadata": {
                "api_token": "secret-token-value",
                "user": "admin",
            },
            "issues": [],
        }
        sanitizer = BackupSanitizer()
        result = sanitizer.sanitize_dict(data)

        assert result.was_sanitized
        assert data["metadata"]["api_token"] == "[REDACTED]"
        assert data["metadata"]["user"] == "admin"

    def test_sanitize_nested_metadata(self) -> None:
        """Should sanitize deeply nested metadata."""
        data = {
            "metadata": {
                "config": {
                    "jira": {
                        "password": "secret123",
                        "url": "https://jira.example.com",
                    }
                }
            },
            "issues": [],
        }
        sanitizer = BackupSanitizer()
        result = sanitizer.sanitize_dict(data)

        assert result.was_sanitized
        assert data["metadata"]["config"]["jira"]["password"] == "[REDACTED]"
        assert data["metadata"]["config"]["jira"]["url"] == "https://jira.example.com"

    def test_sanitize_issue_description_with_secret(self) -> None:
        """Should sanitize secrets in issue descriptions."""
        redactor = SecretRedactor()
        redactor.register_secret("embedded-api-token-123")

        data = {
            "metadata": {},
            "issues": [
                {
                    "key": "PROJ-1",
                    "summary": "Test issue",
                    "description": "Configure with token: embedded-api-token-123",
                }
            ],
        }

        sanitizer = BackupSanitizer(redactor)
        result = sanitizer.sanitize_dict(data)

        assert result.was_sanitized
        assert "embedded-api-token-123" not in data["issues"][0]["description"]

    def test_sanitize_subtask_description(self) -> None:
        """Should sanitize secrets in subtask descriptions."""
        redactor = SecretRedactor()
        redactor.register_secret("subtask-secret-value")

        data = {
            "metadata": {},
            "issues": [
                {
                    "key": "PROJ-1",
                    "summary": "Parent",
                    "description": "Normal description",
                    "subtasks": [
                        {
                            "key": "PROJ-2",
                            "summary": "Subtask",
                            "description": "Uses subtask-secret-value",
                        }
                    ],
                }
            ],
        }

        sanitizer = BackupSanitizer(redactor)
        result = sanitizer.sanitize_dict(data)

        assert result.was_sanitized
        assert "subtask-secret-value" not in data["issues"][0]["subtasks"][0]["description"]

    def test_no_sanitization_needed(self) -> None:
        """Should not modify clean data."""
        data = {
            "backup_id": "backup-123",
            "metadata": {"trigger": "manual"},
            "issues": [
                {
                    "key": "PROJ-1",
                    "summary": "Normal issue",
                    "description": "Just a normal description",
                }
            ],
        }

        sanitizer = BackupSanitizer()
        sanitizer.sanitize_dict(data)

        # No sensitive keys or patterns in the data
        assert data["issues"][0]["description"] == "Just a normal description"

    def test_sanitize_adf_description(self) -> None:
        """Should sanitize ADF format descriptions."""
        data = {
            "metadata": {},
            "issues": [
                {
                    "key": "PROJ-1",
                    "summary": "Test",
                    "description": {
                        "type": "doc",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": "Token: secret123",
                                        "token": "actual-secret",
                                    }
                                ],
                            }
                        ],
                    },
                }
            ],
        }

        sanitizer = BackupSanitizer()
        sanitizer.sanitize_dict(data)

        # The token key in nested dict should be redacted
        desc = data["issues"][0]["description"]
        assert desc["content"][0]["content"][0].get("token") == "[REDACTED]"


class TestBackupSensitivePatterns:
    """Tests for backup-specific patterns."""

    def test_url_with_credentials_pattern(self) -> None:
        """Should match URLs with embedded credentials."""
        pattern = next(p for n, p in BACKUP_SENSITIVE_PATTERNS if "URL" in n)
        assert pattern.search("https://user:password@example.com/path")
        assert pattern.search("http://admin:secret123@internal.corp/api")
        assert not pattern.search("https://example.com/path")

    def test_env_assignment_pattern(self) -> None:
        """Should match environment variable assignments."""
        pattern = next(p for n, p in BACKUP_SENSITIVE_PATTERNS if "Env" in n)
        assert pattern.search("export TOKEN=abc123def456")
        assert pattern.search("API_KEY='secret-key-value'")
        assert pattern.search("PASSWORD=hunter2_password")


class TestSanitizeBackupData:
    """Tests for convenience function."""

    def test_sanitize_backup_data(self) -> None:
        """Should sanitize using convenience function."""
        data = {
            "metadata": {"api_token": "secret"},
            "issues": [],
        }
        result = sanitize_backup_data(data)
        assert result.was_sanitized
        assert data["metadata"]["api_token"] == "[REDACTED]"


class TestCreateSanitizer:
    """Tests for factory function."""

    def test_create_default_sanitizer(self) -> None:
        """Should create sanitizer with defaults."""
        sanitizer = create_sanitizer()
        assert isinstance(sanitizer, BackupSanitizer)

    def test_create_sanitizer_with_redactor(self) -> None:
        """Should create sanitizer with custom redactor."""
        redactor = SecretRedactor()
        sanitizer = create_sanitizer(redactor)
        assert sanitizer.redactor is redactor


class TestIntegrationWithBackup:
    """Integration tests simulating real backup data."""

    def test_full_backup_sanitization(self) -> None:
        """Should sanitize a realistic backup structure."""
        data = {
            "backup_id": "PROJ-1_20240115_123456_abc123",
            "epic_key": "PROJ-1",
            "markdown_path": "/path/to/file.md",
            "created_at": "2024-01-15T12:34:56",
            "metadata": {
                "trigger": "pre-sync",
                "config": {
                    "tracker_url": "https://jira.example.com",
                    "api_token": "super-secret-jira-token",
                },
            },
            "issues": [
                {
                    "key": "PROJ-100",
                    "summary": "Implement authentication",
                    "description": "Set up OAuth with token: ghp_1234567890abcdefghijklmnopqrstuvwxyz",
                    "status": "In Progress",
                    "issue_type": "Story",
                    "assignee": "developer@example.com",
                    "story_points": 5.0,
                    "subtasks": [
                        {
                            "key": "PROJ-101",
                            "summary": "Configure API keys",
                            "description": "Store api_key=secret-key-value in config",
                            "status": "Todo",
                        }
                    ],
                    "comments_count": 3,
                },
                {
                    "key": "PROJ-200",
                    "summary": "Normal story",
                    "description": "Just a regular description without secrets",
                    "status": "Done",
                    "issue_type": "Story",
                    "subtasks": [],
                },
            ],
        }

        sanitizer = BackupSanitizer()
        result = sanitizer.sanitize_dict(data)

        # Verify sanitization
        assert result.was_sanitized
        assert (
            result.fields_sanitized >= 2
        )  # At least metadata.config.api_token and issue description

        # API token in metadata should be redacted
        assert data["metadata"]["config"]["api_token"] == "[REDACTED]"

        # GitHub token in description should be redacted
        assert "ghp_" not in data["issues"][0]["description"]

        # Subtask with embedded secret should be redacted
        assert "secret-key-value" not in data["issues"][0]["subtasks"][0]["description"]

        # Non-sensitive data should be preserved
        assert data["epic_key"] == "PROJ-1"
        assert data["issues"][0]["status"] == "In Progress"
        assert data["issues"][1]["description"] == "Just a regular description without secrets"

    def test_preserves_structure(self) -> None:
        """Should preserve all structure while redacting."""
        data = {
            "metadata": {"password": "secret", "count": 42, "enabled": True},
            "issues": [
                {
                    "key": "PROJ-1",
                    "summary": "Test",
                    "description": None,
                    "story_points": 3.0,
                    "subtasks": [],
                }
            ],
        }

        sanitizer = BackupSanitizer()
        sanitizer.sanitize_dict(data)

        # Password redacted
        assert data["metadata"]["password"] == "[REDACTED]"
        # Other types preserved
        assert data["metadata"]["count"] == 42
        assert data["metadata"]["enabled"] is True
        # None description preserved
        assert data["issues"][0]["description"] is None
        assert data["issues"][0]["story_points"] == 3.0
