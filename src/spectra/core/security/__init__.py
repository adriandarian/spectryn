"""
Security - Core security utilities for secrets hygiene.

Provides:
- SecretRedactor: Redact sensitive values from strings/dicts
- RedactingFormatter: Logging formatter that auto-redacts secrets
- BackupSanitizer: Sanitize backups before saving
- SENSITIVE_PATTERNS: Known patterns for secret detection
"""

from .backup_sanitizer import (
    BACKUP_SENSITIVE_PATTERNS,
    BackupSanitizer,
    SanitizationResult,
    create_sanitizer,
    sanitize_backup_data,
)
from .redactor import (
    SENSITIVE_PATTERNS,
    RedactionConfig,
    SecretRedactor,
    SecretScope,
    create_redactor,
    get_global_redactor,
    redact_dict,
    redact_string,
    register_secret,
    register_secrets,
)


__all__ = [
    # Redactor
    "SENSITIVE_PATTERNS",
    "RedactionConfig",
    "SecretRedactor",
    "SecretScope",
    "create_redactor",
    "get_global_redactor",
    "redact_dict",
    "redact_string",
    "register_secret",
    "register_secrets",
    # Backup Sanitizer
    "BACKUP_SENSITIVE_PATTERNS",
    "BackupSanitizer",
    "SanitizationResult",
    "create_sanitizer",
    "sanitize_backup_data",
]
