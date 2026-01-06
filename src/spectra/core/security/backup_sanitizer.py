"""
Backup Sanitizer - Ensure backups don't contain sensitive data.

Provides pre-save sanitization of backup data to prevent accidental
storage of secrets, tokens, or other sensitive information.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from spectra.core.security.redactor import (
    SENSITIVE_KEY_PATTERNS,
    SecretRedactor,
    get_global_redactor,
)


if TYPE_CHECKING:
    from spectra.application.sync.backup import Backup, IssueSnapshot


# Additional patterns that might appear in issue descriptions or comments
BACKUP_SENSITIVE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Credentials in markdown code blocks
    (
        "Embedded Token",
        re.compile(
            r"```[^`]*(?:token|password|secret|key)\s*[=:]\s*['\"]?[A-Za-z0-9\-_\.=]{16,}['\"]?[^`]*```",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    # URLs with embedded credentials
    ("URL with Creds", re.compile(r"https?://[^:]+:[^@]+@[^\s]+")),
    # Environment variable assignments
    (
        "Env Assignment",
        re.compile(
            r"(?:export\s+)?(?:TOKEN|SECRET|PASSWORD|API_KEY|PAT)[=]['\"]?[A-Za-z0-9\-_\.=]{8,}['\"]?",
            re.IGNORECASE,
        ),
    ),
]


@dataclass
class SanitizationResult:
    """Result of backup sanitization."""

    # Number of fields sanitized
    fields_sanitized: int = 0

    # List of sanitized field paths (e.g., "issues[0].description")
    sanitized_paths: list[str] = field(default_factory=list)

    # Any warnings generated
    warnings: list[str] = field(default_factory=list)

    @property
    def was_sanitized(self) -> bool:
        """Check if any sanitization was performed."""
        return self.fields_sanitized > 0


class BackupSanitizer:
    """
    Sanitizes backup data to remove sensitive information.

    Used before saving backups to disk to ensure no secrets are
    accidentally persisted.

    Features:
    - Redacts sensitive key values
    - Scans descriptions and comments for embedded secrets
    - Preserves data structure while removing sensitive content
    """

    def __init__(self, redactor: SecretRedactor | None = None) -> None:
        """
        Initialize the sanitizer.

        Args:
            redactor: Optional SecretRedactor to use. Uses global if not specified.
        """
        self.redactor = redactor or get_global_redactor()

    def sanitize_backup(self, backup: Backup) -> SanitizationResult:
        """
        Sanitize a backup in place.

        Scans and redacts sensitive data from:
        - Issue descriptions
        - Issue summaries (unlikely but possible)
        - Metadata fields
        - Any string fields with sensitive content

        Args:
            backup: The backup to sanitize (modified in place).

        Returns:
            SanitizationResult with details of what was sanitized.
        """
        result = SanitizationResult()

        # Sanitize metadata
        self._sanitize_metadata(backup.metadata, "metadata", result)

        # Sanitize each issue
        for i, issue in enumerate(backup.issues):
            self._sanitize_issue(issue, f"issues[{i}]", result)

        return result

    def sanitize_dict(self, data: dict[str, Any]) -> SanitizationResult:
        """
        Sanitize a dictionary (e.g., backup.to_dict() output).

        Args:
            data: Dictionary to sanitize (modified in place).

        Returns:
            SanitizationResult with details.
        """
        result = SanitizationResult()

        # Sanitize metadata if present
        if "metadata" in data and isinstance(data["metadata"], dict):
            self._sanitize_metadata(data["metadata"], "metadata", result)

        # Sanitize issues if present
        if "issues" in data and isinstance(data["issues"], list):
            for i, issue in enumerate(data["issues"]):
                if isinstance(issue, dict):
                    self._sanitize_issue_dict(issue, f"issues[{i}]", result)

        return result

    def _sanitize_metadata(
        self,
        metadata: dict[str, Any],
        path: str,
        result: SanitizationResult,
    ) -> None:
        """Sanitize metadata dictionary."""
        for key in list(metadata.keys()):
            value = metadata[key]
            full_path = f"{path}.{key}"

            # Check if key is sensitive
            if self._is_sensitive_key(key):
                metadata[key] = "[REDACTED]"
                result.fields_sanitized += 1
                result.sanitized_paths.append(full_path)
            elif isinstance(value, str):
                # Check string value for embedded secrets
                sanitized = self._sanitize_string(value)
                if sanitized != value:
                    metadata[key] = sanitized
                    result.fields_sanitized += 1
                    result.sanitized_paths.append(full_path)
            elif isinstance(value, dict):
                self._sanitize_metadata(value, full_path, result)

    def _sanitize_issue(
        self,
        issue: IssueSnapshot,
        path: str,
        result: SanitizationResult,
    ) -> None:
        """Sanitize an issue snapshot."""
        # Sanitize description
        if issue.description:
            if isinstance(issue.description, str):
                sanitized = self._sanitize_string(issue.description)
                if sanitized != issue.description:
                    issue.description = sanitized
                    result.fields_sanitized += 1
                    result.sanitized_paths.append(f"{path}.description")
            elif isinstance(issue.description, dict):
                # ADF format - redact the entire structure
                sanitized_dict = self.redactor.redact_dict(issue.description)
                if sanitized_dict != issue.description:
                    issue.description = sanitized_dict
                    result.fields_sanitized += 1
                    result.sanitized_paths.append(f"{path}.description")

        # Sanitize summary (rare, but check anyway)
        if issue.summary:
            sanitized = self._sanitize_string(issue.summary)
            if sanitized != issue.summary:
                issue.summary = sanitized
                result.fields_sanitized += 1
                result.sanitized_paths.append(f"{path}.summary")

        # Sanitize subtasks
        for j, subtask in enumerate(issue.subtasks):
            self._sanitize_issue(subtask, f"{path}.subtasks[{j}]", result)

    def _sanitize_issue_dict(
        self,
        issue: dict[str, Any],
        path: str,
        result: SanitizationResult,
    ) -> None:
        """Sanitize an issue dictionary."""
        # Sanitize description
        if "description" in issue:
            desc = issue["description"]
            if isinstance(desc, str):
                sanitized = self._sanitize_string(desc)
                if sanitized != desc:
                    issue["description"] = sanitized
                    result.fields_sanitized += 1
                    result.sanitized_paths.append(f"{path}.description")
            elif isinstance(desc, dict):
                sanitized_dict = self.redactor.redact_dict(desc)
                if sanitized_dict != desc:
                    issue["description"] = sanitized_dict
                    result.fields_sanitized += 1
                    result.sanitized_paths.append(f"{path}.description")

        # Sanitize summary
        if "summary" in issue and isinstance(issue["summary"], str):
            sanitized = self._sanitize_string(issue["summary"])
            if sanitized != issue["summary"]:
                issue["summary"] = sanitized
                result.fields_sanitized += 1
                result.sanitized_paths.append(f"{path}.summary")

        # Sanitize subtasks
        if "subtasks" in issue and isinstance(issue["subtasks"], list):
            for j, subtask in enumerate(issue["subtasks"]):
                if isinstance(subtask, dict):
                    self._sanitize_issue_dict(subtask, f"{path}.subtasks[{j}]", result)

    def _sanitize_string(self, text: str) -> str:
        """Sanitize a string value for embedded secrets."""
        # First, use the main redactor
        result = self.redactor.redact_string(text)

        # Then apply backup-specific patterns
        for _name, pattern in BACKUP_SENSITIVE_PATTERNS:
            result = pattern.sub("[REDACTED]", result)

        return result

    def _is_sensitive_key(self, key: str) -> bool:
        """Check if a key name indicates sensitive data."""
        normalized = key.lower().replace("-", "_")
        return normalized in SENSITIVE_KEY_PATTERNS


def sanitize_backup_data(data: dict[str, Any]) -> SanitizationResult:
    """
    Convenience function to sanitize backup data before saving.

    Args:
        data: Backup dictionary (e.g., from backup.to_dict()).

    Returns:
        SanitizationResult with details of what was sanitized.
    """
    sanitizer = BackupSanitizer()
    return sanitizer.sanitize_dict(data)


def create_sanitizer(redactor: SecretRedactor | None = None) -> BackupSanitizer:
    """
    Create a BackupSanitizer instance.

    Args:
        redactor: Optional custom redactor.

    Returns:
        BackupSanitizer instance.
    """
    return BackupSanitizer(redactor)
