"""
Secret Redactor - Prevent sensitive data from leaking into logs and backups.

This module provides comprehensive secret redaction for:
- API tokens and keys
- Passwords and credentials
- Bearer tokens and auth headers
- Custom sensitive fields

Features:
- Pattern-based detection (regex)
- Key-based detection (dict key names)
- Context-aware redaction (preserves structure)
- Thread-safe global registration of secrets
- Configurable redaction placeholder
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from typing import Any


# -------------------------------------------------------------------------
# Sensitive Field Patterns
# -------------------------------------------------------------------------

# Keys that should always be redacted (case-insensitive matching)
SENSITIVE_KEY_PATTERNS: frozenset[str] = frozenset(
    {
        # Authentication tokens
        "api_token",
        "apitoken",
        "api_key",
        "apikey",
        "access_token",
        "accesstoken",
        "auth_token",
        "authtoken",
        "bearer_token",
        "bearertoken",
        "refresh_token",
        "refreshtoken",
        "token",
        "jwt",
        "jwt_token",
        # Passwords and secrets
        "password",
        "passwd",
        "pwd",
        "secret",
        "secret_key",
        "secretkey",
        "private_key",
        "privatekey",
        # API credentials
        "pat",  # Personal Access Token
        "personal_access_token",
        "client_secret",
        "clientsecret",
        "app_secret",
        "appsecret",
        # Service-specific
        "jira_api_token",
        "github_token",
        "gitlab_token",
        "azure_devops_pat",
        "linear_api_key",
        "asana_token",
        "trello_token",
        "trello_api_key",
        "shortcut_token",
        "clickup_token",
        "monday_api_key",
        "basecamp_access_token",
        "youtrack_token",
        "pivotal_api_token",
        "plane_api_token",
        "confluence_token",
        # LLM API keys
        "openai_api_key",
        "anthropic_api_key",
        "google_api_key",
        # Cloud credentials
        "aws_secret_access_key",
        "aws_session_token",
        "azure_key",
        "gcp_key",
        # Headers
        "authorization",
        "x-api-key",
        "x-auth-token",
        "x-tracker-token",
    }
)

# Regex patterns for detecting secrets in strings
SENSITIVE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Bearer tokens in headers
    ("Bearer Token", re.compile(r"Bearer\s+[A-Za-z0-9\-_\.=]+", re.IGNORECASE)),
    # Basic auth (base64 encoded)
    ("Basic Auth", re.compile(r"Basic\s+[A-Za-z0-9+/=]+", re.IGNORECASE)),
    # API keys (common formats)
    (
        "API Key",
        re.compile(
            r"(?:api[_-]?key|apikey)[=:]\s*['\"]?[A-Za-z0-9\-_\.=]{16,}['\"]?", re.IGNORECASE
        ),
    ),
    # JWT tokens (header.payload.signature format)
    ("JWT Token", re.compile(r"eyJ[A-Za-z0-9\-_]+\.eyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+")),
    # GitHub tokens (classic and fine-grained)
    ("GitHub Token", re.compile(r"gh[ps]_[A-Za-z0-9]{36,}")),
    ("GitHub Token", re.compile(r"github_pat_[A-Za-z0-9_]{22,}")),
    # GitLab tokens
    ("GitLab Token", re.compile(r"glpat-[A-Za-z0-9\-]{20,}")),
    # Slack tokens
    ("Slack Token", re.compile(r"xox[baprs]-[A-Za-z0-9\-]+")),
    # AWS credentials
    ("AWS Key", re.compile(r"AKIA[0-9A-Z]{16}")),
    (
        "AWS Secret",
        re.compile(
            r"(?:aws[_-]?secret[_-]?access[_-]?key)[=:]\s*['\"]?[A-Za-z0-9/+=]{40}['\"]?",
            re.IGNORECASE,
        ),
    ),
    # Azure
    ("Azure Key", re.compile(r"[A-Za-z0-9+/]{86}==", re.IGNORECASE)),
    # Generic long alphanumeric strings that look like secrets (32+ chars)
    (
        "Generic Secret",
        re.compile(
            r"(?:password|secret|token|key)[=:]\s*['\"]?[A-Za-z0-9\-_\.=]{32,}['\"]?", re.IGNORECASE
        ),
    ),
]

# Default redaction placeholder
DEFAULT_REDACTED = "[REDACTED]"


# -------------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------------


@dataclass
class RedactionConfig:
    """Configuration for secret redaction behavior."""

    # Placeholder text for redacted values
    placeholder: str = DEFAULT_REDACTED

    # Show partial value (e.g., "abc...xyz")
    show_partial: bool = False

    # Number of chars to show at start/end when show_partial is True
    partial_chars: int = 4

    # Additional sensitive key patterns (merged with defaults)
    extra_keys: frozenset[str] = field(default_factory=frozenset)

    # Keys to explicitly exclude from redaction (e.g., "token_count")
    exclude_keys: frozenset[str] = field(default_factory=frozenset)

    # Apply pattern matching to string values
    use_patterns: bool = True

    # Minimum length for a value to be considered for pattern matching
    min_pattern_length: int = 16


# -------------------------------------------------------------------------
# Secret Redactor
# -------------------------------------------------------------------------


class SecretRedactor:
    """
    Thread-safe secret redactor with pattern and key-based detection.

    Supports:
    - Registering known secrets for exact matching
    - Key-based redaction for dicts
    - Pattern-based redaction for strings
    - Partial value display for debugging

    Example:
        redactor = SecretRedactor()
        redactor.register_secret("super-secret-token-123")

        # Redact known secrets in strings
        text = "Using token: super-secret-token-123"
        safe_text = redactor.redact_string(text)
        # -> "Using token: [REDACTED]"

        # Redact sensitive keys in dicts
        config = {"api_token": "secret123", "url": "https://example.com"}
        safe_config = redactor.redact_dict(config)
        # -> {"api_token": "[REDACTED]", "url": "https://example.com"}
    """

    def __init__(self, config: RedactionConfig | None = None) -> None:
        """
        Initialize the redactor.

        Args:
            config: Optional configuration for redaction behavior.
        """
        self.config = config or RedactionConfig()
        self._registered_secrets: set[str] = set()
        self._lock = threading.RLock()

        # Compile sensitive key patterns
        self._sensitive_keys = SENSITIVE_KEY_PATTERNS | self.config.extra_keys
        self._sensitive_keys = self._sensitive_keys - self.config.exclude_keys

    def register_secret(self, secret: str) -> None:
        """
        Register a secret for exact matching redaction.

        Registered secrets are redacted from any string regardless of context.

        Args:
            secret: The secret value to redact.
        """
        if not secret or len(secret) < 4:
            return  # Don't register empty or very short values

        with self._lock:
            self._registered_secrets.add(secret)

    def register_secrets(self, *secrets: str) -> None:
        """Register multiple secrets at once."""
        for secret in secrets:
            self.register_secret(secret)

    def unregister_secret(self, secret: str) -> None:
        """Remove a secret from the registry."""
        with self._lock:
            self._registered_secrets.discard(secret)

    def clear_secrets(self) -> None:
        """Clear all registered secrets."""
        with self._lock:
            self._registered_secrets.clear()

    @property
    def registered_count(self) -> int:
        """Number of registered secrets."""
        with self._lock:
            return len(self._registered_secrets)

    def _format_redacted(self, original: str | None = None) -> str:
        """Format the redaction placeholder, optionally with partial value."""
        if not self.config.show_partial or not original:
            return self.config.placeholder

        if len(original) <= self.config.partial_chars * 2 + 3:
            return self.config.placeholder

        start = original[: self.config.partial_chars]
        end = original[-self.config.partial_chars :]
        return f"{start}...{end}"

    def _is_sensitive_key(self, key: str) -> bool:
        """Check if a key name indicates sensitive data."""
        normalized = key.lower().replace("-", "_")
        return normalized in self._sensitive_keys

    def redact_string(self, text: str) -> str:
        """
        Redact sensitive values from a string.

        Redacts:
        1. Registered secrets (exact match)
        2. Pattern-matched secrets (if enabled)

        Args:
            text: The text to redact.

        Returns:
            Text with sensitive values replaced.
        """
        if not text:
            return text

        result = text

        # 1. Redact registered secrets
        with self._lock:
            for secret in self._registered_secrets:
                if secret in result:
                    replacement = self._format_redacted(secret)
                    result = result.replace(secret, replacement)

        # 2. Redact pattern-matched secrets
        if self.config.use_patterns:
            for _name, pattern in SENSITIVE_PATTERNS:
                result = pattern.sub(self._format_redacted(), result)

        return result

    def redact_dict(
        self,
        data: dict[str, Any],
        *,
        recursive: bool = True,
        copy: bool = True,
    ) -> dict[str, Any]:
        """
        Redact sensitive values from a dictionary.

        Redacts:
        1. Values with sensitive key names
        2. Registered secrets in string values
        3. Pattern-matched secrets in string values

        Args:
            data: The dictionary to redact.
            recursive: Whether to recursively redact nested dicts/lists.
            copy: Whether to create a copy (True) or modify in place (False).

        Returns:
            Dictionary with sensitive values redacted.
        """
        result = {} if copy else data

        for key, value in data.items():
            if self._is_sensitive_key(key):
                # Sensitive key - redact entire value
                if isinstance(value, str):
                    result[key] = self._format_redacted(value)
                else:
                    result[key] = self.config.placeholder
            elif isinstance(value, str):
                # String value - check for secrets
                result[key] = self.redact_string(value)
            elif recursive and isinstance(value, dict):
                # Nested dict - recurse
                result[key] = self.redact_dict(value, recursive=True, copy=copy)
            elif recursive and isinstance(value, list):
                # List - check each item
                result[key] = self._redact_list(value, copy=copy)
            elif copy:
                # Copy non-string value
                result[key] = value

        return result

    def _redact_list(self, items: list[Any], *, copy: bool = True) -> list[Any]:
        """Redact sensitive values from a list."""
        result: list[Any] = []
        for item in items:
            if isinstance(item, str):
                result.append(self.redact_string(item))
            elif isinstance(item, dict):
                result.append(self.redact_dict(item, recursive=True, copy=copy))
            elif isinstance(item, list):
                result.append(self._redact_list(item, copy=copy))
            else:
                result.append(item)
        return result

    def redact_exception(self, exc: Exception) -> str:
        """
        Redact sensitive values from an exception message.

        Args:
            exc: The exception to redact.

        Returns:
            Redacted exception string.
        """
        return self.redact_string(str(exc))

    def make_safe_repr(self, obj: Any, max_depth: int = 3) -> str:
        """
        Create a safe string representation of an object.

        Useful for logging objects that may contain secrets.

        Args:
            obj: Object to represent.
            max_depth: Maximum recursion depth.

        Returns:
            Safe string representation.
        """
        if max_depth <= 0:
            return "..."

        if obj is None:
            return "None"
        if isinstance(obj, bool):
            return str(obj)
        if isinstance(obj, (int, float)):
            return str(obj)
        if isinstance(obj, str):
            return f'"{self.redact_string(obj)}"'
        if isinstance(obj, dict):
            redacted = self.redact_dict(obj)
            items = [f"{k!r}: {self.make_safe_repr(v, max_depth - 1)}" for k, v in redacted.items()]
            return "{" + ", ".join(items) + "}"
        if isinstance(obj, (list, tuple)):
            items = [self.make_safe_repr(item, max_depth - 1) for item in obj]
            if isinstance(obj, tuple):
                return "(" + ", ".join(items) + ")"
            return "[" + ", ".join(items) + "]"

        # For other objects, get string repr and redact
        try:
            return self.redact_string(repr(obj))
        except Exception:
            return f"<{type(obj).__name__}>"


# -------------------------------------------------------------------------
# Global Redactor Instance
# -------------------------------------------------------------------------

# Global redactor instance (thread-safe singleton)
_global_redactor: SecretRedactor | None = None
_global_lock = threading.Lock()


def get_global_redactor() -> SecretRedactor:
    """
    Get the global redactor instance.

    Creates one if it doesn't exist. The global redactor allows
    secrets to be registered once and redacted everywhere.

    Returns:
        The global SecretRedactor instance.
    """
    global _global_redactor
    if _global_redactor is None:
        with _global_lock:
            if _global_redactor is None:
                _global_redactor = SecretRedactor()
    return _global_redactor


def create_redactor(config: RedactionConfig | None = None) -> SecretRedactor:
    """
    Create a new SecretRedactor instance.

    Args:
        config: Optional configuration.

    Returns:
        New SecretRedactor instance.
    """
    return SecretRedactor(config)


# -------------------------------------------------------------------------
# Convenience Functions
# -------------------------------------------------------------------------


def redact_string(text: str) -> str:
    """
    Redact sensitive values from a string using the global redactor.

    Args:
        text: Text to redact.

    Returns:
        Redacted text.
    """
    return get_global_redactor().redact_string(text)


def redact_dict(
    data: dict[str, Any],
    *,
    recursive: bool = True,
) -> dict[str, Any]:
    """
    Redact sensitive values from a dictionary using the global redactor.

    Args:
        data: Dictionary to redact.
        recursive: Whether to recursively redact nested structures.

    Returns:
        Redacted dictionary.
    """
    return get_global_redactor().redact_dict(data, recursive=recursive)


def register_secret(secret: str) -> None:
    """
    Register a secret with the global redactor.

    Registered secrets are automatically redacted from all strings
    processed by the global redactor.

    Args:
        secret: The secret value to register.
    """
    get_global_redactor().register_secret(secret)


def register_secrets(*secrets: str) -> None:
    """Register multiple secrets with the global redactor."""
    get_global_redactor().register_secrets(*secrets)


# -------------------------------------------------------------------------
# Context Manager for Temporary Secret Registration
# -------------------------------------------------------------------------


class SecretScope:
    """
    Context manager for temporarily registering secrets.

    Useful for ensuring secrets are redacted during a specific operation
    and then cleaned up afterward.

    Example:
        with SecretScope("my-temp-secret"):
            # Secret is registered
            print(redact_string("Using my-temp-secret here"))
        # Secret is unregistered
    """

    def __init__(self, *secrets: str, redactor: SecretRedactor | None = None) -> None:
        """
        Initialize the scope.

        Args:
            *secrets: Secrets to register for this scope.
            redactor: Optional redactor (uses global if not specified).
        """
        self.secrets = secrets
        self.redactor = redactor or get_global_redactor()

    def __enter__(self) -> SecretScope:
        """Register secrets on entry."""
        for secret in self.secrets:
            self.redactor.register_secret(secret)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Unregister secrets on exit."""
        for secret in self.secrets:
            self.redactor.unregister_secret(secret)
