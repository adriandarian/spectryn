"""
Tests for secrets redactor module.

Tests cover:
- Key-based redaction
- Pattern-based redaction
- String redaction
- Dict redaction
- Secret registration
- Partial value display
- Thread safety
"""

import pytest

from spectra.core.security.redactor import (
    DEFAULT_REDACTED,
    SENSITIVE_KEY_PATTERNS,
    SENSITIVE_PATTERNS,
    RedactionConfig,
    SecretRedactor,
    SecretScope,
    create_redactor,
    get_global_redactor,
    redact_dict,
    redact_string,
    register_secret,
)


class TestSecretRedactor:
    """Tests for SecretRedactor class."""

    def test_init_default_config(self) -> None:
        """Should initialize with default configuration."""
        redactor = SecretRedactor()
        assert redactor.config.placeholder == DEFAULT_REDACTED
        assert redactor.config.show_partial is False
        assert redactor.registered_count == 0

    def test_init_custom_config(self) -> None:
        """Should initialize with custom configuration."""
        config = RedactionConfig(
            placeholder="***HIDDEN***",
            show_partial=True,
            partial_chars=3,
        )
        redactor = SecretRedactor(config)
        assert redactor.config.placeholder == "***HIDDEN***"
        assert redactor.config.show_partial is True

    def test_register_secret(self) -> None:
        """Should register secrets for redaction."""
        redactor = SecretRedactor()
        redactor.register_secret("my-secret-token")
        assert redactor.registered_count == 1

    def test_register_secret_ignores_short(self) -> None:
        """Should ignore very short values."""
        redactor = SecretRedactor()
        redactor.register_secret("abc")
        assert redactor.registered_count == 0

    def test_register_secrets_multiple(self) -> None:
        """Should register multiple secrets at once."""
        redactor = SecretRedactor()
        redactor.register_secrets("secret1-token", "secret2-password", "secret3-key")
        assert redactor.registered_count == 3

    def test_unregister_secret(self) -> None:
        """Should unregister secrets."""
        redactor = SecretRedactor()
        redactor.register_secret("my-secret-token")
        assert redactor.registered_count == 1
        redactor.unregister_secret("my-secret-token")
        assert redactor.registered_count == 0

    def test_clear_secrets(self) -> None:
        """Should clear all registered secrets."""
        redactor = SecretRedactor()
        redactor.register_secrets("secret1-abcd", "secret2-efgh")
        assert redactor.registered_count == 2
        redactor.clear_secrets()
        assert redactor.registered_count == 0


class TestStringRedaction:
    """Tests for string redaction."""

    def test_redact_registered_secret(self) -> None:
        """Should redact registered secrets."""
        redactor = SecretRedactor()
        redactor.register_secret("super-secret-123")
        text = "Using token: super-secret-123"
        result = redactor.redact_string(text)
        assert result == f"Using token: {DEFAULT_REDACTED}"

    def test_redact_multiple_occurrences(self) -> None:
        """Should redact multiple occurrences."""
        redactor = SecretRedactor()
        redactor.register_secret("token-abc123")
        text = "token-abc123 and again token-abc123"
        result = redactor.redact_string(text)
        assert result == f"{DEFAULT_REDACTED} and again {DEFAULT_REDACTED}"

    def test_redact_bearer_token_pattern(self) -> None:
        """Should redact Bearer tokens."""
        redactor = SecretRedactor()
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"
        result = redactor.redact_string(text)
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result
        assert DEFAULT_REDACTED in result

    def test_redact_github_token_pattern(self) -> None:
        """Should redact GitHub tokens."""
        redactor = SecretRedactor()
        text = "token=ghp_1234567890abcdefghijklmnopqrstuvwxyz"
        result = redactor.redact_string(text)
        assert "ghp_" not in result

    def test_redact_jwt_pattern(self) -> None:
        """Should redact JWT tokens."""
        redactor = SecretRedactor()
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        text = f"Using JWT: {jwt}"
        result = redactor.redact_string(text)
        assert jwt not in result

    def test_no_redact_safe_text(self) -> None:
        """Should not modify safe text."""
        redactor = SecretRedactor()
        text = "This is a normal message with no secrets"
        result = redactor.redact_string(text)
        assert result == text

    def test_redact_empty_string(self) -> None:
        """Should handle empty strings."""
        redactor = SecretRedactor()
        assert redactor.redact_string("") == ""

    def test_partial_value_display(self) -> None:
        """Should show partial value when configured."""
        config = RedactionConfig(show_partial=True, partial_chars=4)
        redactor = SecretRedactor(config)
        redactor.register_secret("abcdefghijklmnop")
        text = "secret: abcdefghijklmnop"
        result = redactor.redact_string(text)
        assert "abcd...mnop" in result


class TestDictRedaction:
    """Tests for dictionary redaction."""

    def test_redact_sensitive_key(self) -> None:
        """Should redact values with sensitive keys."""
        redactor = SecretRedactor()
        data = {"api_token": "secret123", "url": "https://example.com"}
        result = redactor.redact_dict(data)
        assert result["api_token"] == DEFAULT_REDACTED
        assert result["url"] == "https://example.com"

    def test_redact_password_key(self) -> None:
        """Should redact password values."""
        redactor = SecretRedactor()
        data = {"password": "hunter2", "username": "admin"}
        result = redactor.redact_dict(data)
        assert result["password"] == DEFAULT_REDACTED
        assert result["username"] == "admin"

    def test_redact_nested_dict(self) -> None:
        """Should redact nested dictionaries."""
        redactor = SecretRedactor()
        data = {
            "config": {
                "jira": {
                    "api_token": "secret-token",
                    "url": "https://jira.example.com",
                }
            }
        }
        result = redactor.redact_dict(data)
        assert result["config"]["jira"]["api_token"] == DEFAULT_REDACTED
        assert result["config"]["jira"]["url"] == "https://jira.example.com"

    def test_redact_list_in_dict(self) -> None:
        """Should redact lists containing dicts."""
        redactor = SecretRedactor()
        data = {
            "adapters": [
                {"name": "jira", "token": "secret1"},
                {"name": "github", "token": "secret2"},
            ]
        }
        result = redactor.redact_dict(data)
        assert result["adapters"][0]["token"] == DEFAULT_REDACTED
        assert result["adapters"][1]["token"] == DEFAULT_REDACTED
        assert result["adapters"][0]["name"] == "jira"

    def test_redact_embedded_secrets_in_values(self) -> None:
        """Should redact secrets embedded in string values."""
        redactor = SecretRedactor()
        redactor.register_secret("embedded-secret-123")
        data = {"message": "Using token embedded-secret-123 here"}
        result = redactor.redact_dict(data)
        assert "embedded-secret-123" not in result["message"]

    def test_does_not_modify_original(self) -> None:
        """Should not modify original dict when copy=True."""
        redactor = SecretRedactor()
        original = {"api_token": "secret123"}
        result = redactor.redact_dict(original, copy=True)
        assert original["api_token"] == "secret123"
        assert result["api_token"] == DEFAULT_REDACTED

    def test_redact_various_key_formats(self) -> None:
        """Should redact keys regardless of case/separator."""
        redactor = SecretRedactor()
        data = {
            "api_token": "secret1",
            "API_TOKEN": "secret2",
            "apitoken": "secret3",
            "api-token": "secret4",
        }
        result = redactor.redact_dict(data)
        # All should be redacted (key matching is case-insensitive)
        for key in data:
            assert result[key] == DEFAULT_REDACTED


class TestSensitiveKeyPatterns:
    """Tests for sensitive key patterns."""

    def test_common_token_keys(self) -> None:
        """Should include common token key patterns."""
        assert "api_token" in SENSITIVE_KEY_PATTERNS
        assert "access_token" in SENSITIVE_KEY_PATTERNS
        assert "bearer_token" in SENSITIVE_KEY_PATTERNS
        assert "refresh_token" in SENSITIVE_KEY_PATTERNS

    def test_password_keys(self) -> None:
        """Should include password key patterns."""
        assert "password" in SENSITIVE_KEY_PATTERNS
        assert "passwd" in SENSITIVE_KEY_PATTERNS
        assert "secret" in SENSITIVE_KEY_PATTERNS

    def test_service_specific_keys(self) -> None:
        """Should include service-specific key patterns."""
        assert "jira_api_token" in SENSITIVE_KEY_PATTERNS
        assert "github_token" in SENSITIVE_KEY_PATTERNS
        assert "azure_devops_pat" in SENSITIVE_KEY_PATTERNS


class TestSensitivePatterns:
    """Tests for regex patterns."""

    def test_bearer_pattern_matches(self) -> None:
        """Should match Bearer tokens."""
        bearer_pattern = next(p for n, p in SENSITIVE_PATTERNS if "Bearer" in n)
        assert bearer_pattern.search("Bearer abc123def456")
        assert bearer_pattern.search("bearer ABC123")

    def test_jwt_pattern_matches(self) -> None:
        """Should match JWT tokens."""
        jwt_pattern = next(p for n, p in SENSITIVE_PATTERNS if "JWT" in n)
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.Rq8IjqH"
        assert jwt_pattern.search(jwt)

    def test_github_pattern_matches(self) -> None:
        """Should match GitHub tokens."""
        gh_patterns = [p for n, p in SENSITIVE_PATTERNS if "GitHub" in n]
        assert any(p.search("ghp_1234567890abcdefghijklmnopqrstuvwxyz") for p in gh_patterns)


class TestSecretScope:
    """Tests for SecretScope context manager."""

    def test_scope_registers_secrets(self) -> None:
        """Should register secrets on entry."""
        redactor = SecretRedactor()
        with SecretScope("temp-secret-123", redactor=redactor):
            assert redactor.registered_count == 1
            text = "using temp-secret-123"
            assert DEFAULT_REDACTED in redactor.redact_string(text)

    def test_scope_unregisters_on_exit(self) -> None:
        """Should unregister secrets on exit."""
        redactor = SecretRedactor()
        with SecretScope("temp-secret-123", redactor=redactor):
            pass
        assert redactor.registered_count == 0

    def test_scope_unregisters_on_exception(self) -> None:
        """Should unregister secrets even on exception."""
        redactor = SecretRedactor()
        try:
            with SecretScope("temp-secret-123", redactor=redactor):
                raise ValueError("Test error")
        except ValueError:
            pass
        assert redactor.registered_count == 0


class TestGlobalRedactor:
    """Tests for global redactor functions."""

    def test_get_global_redactor(self) -> None:
        """Should return singleton instance."""
        r1 = get_global_redactor()
        r2 = get_global_redactor()
        assert r1 is r2

    def test_register_secret_global(self) -> None:
        """Should register with global redactor."""
        # Clear any previous state
        get_global_redactor().clear_secrets()
        register_secret("global-test-secret")
        assert get_global_redactor().registered_count >= 1
        # Cleanup
        get_global_redactor().clear_secrets()

    def test_redact_string_global(self) -> None:
        """Should use global redactor for string redaction."""
        get_global_redactor().clear_secrets()
        register_secret("global-secret-abc")
        result = redact_string("using global-secret-abc here")
        assert "global-secret-abc" not in result
        get_global_redactor().clear_secrets()

    def test_redact_dict_global(self) -> None:
        """Should use global redactor for dict redaction."""
        data = {"api_token": "secret"}
        result = redact_dict(data)
        assert result["api_token"] == DEFAULT_REDACTED


class TestCreateRedactor:
    """Tests for create_redactor factory function."""

    def test_create_with_defaults(self) -> None:
        """Should create redactor with default config."""
        redactor = create_redactor()
        assert redactor.config.placeholder == DEFAULT_REDACTED

    def test_create_with_custom_config(self) -> None:
        """Should create redactor with custom config."""
        config = RedactionConfig(placeholder="[HIDDEN]")
        redactor = create_redactor(config)
        assert redactor.config.placeholder == "[HIDDEN]"


class TestExcludeKeys:
    """Tests for excluding keys from redaction."""

    def test_exclude_specific_key(self) -> None:
        """Should not redact excluded keys."""
        config = RedactionConfig(exclude_keys=frozenset({"token_count"}))
        redactor = SecretRedactor(config)
        data = {"token": "secret", "token_count": 100}
        result = redactor.redact_dict(data)
        assert result["token"] == DEFAULT_REDACTED
        assert result["token_count"] == 100


class TestMakeSafeRepr:
    """Tests for make_safe_repr method."""

    def test_safe_repr_dict(self) -> None:
        """Should create safe repr of dict."""
        redactor = SecretRedactor()
        obj = {"api_token": "secret123", "url": "https://example.com"}
        result = redactor.make_safe_repr(obj)
        assert "secret123" not in result
        assert DEFAULT_REDACTED in result
        assert "example.com" in result

    def test_safe_repr_string(self) -> None:
        """Should create safe repr of string with secret."""
        redactor = SecretRedactor()
        redactor.register_secret("embedded-secret")
        result = redactor.make_safe_repr("has embedded-secret value")
        assert "embedded-secret" not in result

    def test_safe_repr_primitives(self) -> None:
        """Should handle primitive types."""
        redactor = SecretRedactor()
        assert redactor.make_safe_repr(None) == "None"
        assert redactor.make_safe_repr(True) == "True"
        assert redactor.make_safe_repr(42) == "42"
        assert redactor.make_safe_repr(3.14) == "3.14"


class TestRedactException:
    """Tests for exception redaction."""

    def test_redact_exception_message(self) -> None:
        """Should redact secrets from exception messages."""
        redactor = SecretRedactor()
        redactor.register_secret("secret-in-error")
        exc = ValueError("Failed with secret-in-error")
        result = redactor.redact_exception(exc)
        assert "secret-in-error" not in result
        assert DEFAULT_REDACTED in result
