"""
Tests for Environment Secret Manager adapter.

Tests cover:
- Basic environment variable retrieval
- Prefix configuration
- Secret reference resolution
- List and exists operations
"""

import os

import pytest

from spectryn.adapters.secret_manager.environment_manager import (
    EnvironmentConfig,
    EnvironmentSecretManager,
)
from spectryn.core.ports.secret_manager import (
    SecretBackend,
    SecretNotFoundError,
    SecretReference,
)


class TestEnvironmentSecretManager:
    """Tests for EnvironmentSecretManager."""

    def test_backend_type(self) -> None:
        """Should report correct backend type."""
        manager = EnvironmentSecretManager()
        assert manager.backend == SecretBackend.ENVIRONMENT

    def test_get_value_existing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should get existing environment variable."""
        monkeypatch.setenv("TEST_SECRET_123", "secret_value")
        manager = EnvironmentSecretManager()
        assert manager.get_value("TEST_SECRET_123") == "secret_value"

    def test_get_value_missing_with_default(self) -> None:
        """Should return default for missing variable."""
        manager = EnvironmentSecretManager()
        assert manager.get_value("NONEXISTENT_VAR_XYZ") is None
        assert manager.get_value("NONEXISTENT_VAR_XYZ", default="fallback") == "fallback"

    def test_get_secret_existing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return Secret object for existing variable."""
        monkeypatch.setenv("MY_API_TOKEN", "token123")
        manager = EnvironmentSecretManager()
        secret = manager.get_secret("MY_API_TOKEN")
        assert secret.value == "token123"
        assert secret.path == "MY_API_TOKEN"

    def test_get_secret_missing_raises(self) -> None:
        """Should raise SecretNotFoundError for missing variable."""
        manager = EnvironmentSecretManager()
        with pytest.raises(SecretNotFoundError):
            manager.get_secret("DEFINITELY_NOT_SET_VAR")

    def test_exists_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return True for existing variable."""
        monkeypatch.setenv("EXISTS_TEST_VAR", "value")
        manager = EnvironmentSecretManager()
        assert manager.exists("EXISTS_TEST_VAR") is True

    def test_exists_false(self) -> None:
        """Should return False for missing variable."""
        manager = EnvironmentSecretManager()
        assert manager.exists("NOT_EXISTS_VAR_XYZ") is False

    def test_resolve_reference(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should resolve secret reference."""
        monkeypatch.setenv("REF_TEST_TOKEN", "resolved_value")
        manager = EnvironmentSecretManager()
        ref = SecretReference(
            backend=SecretBackend.ENVIRONMENT,
            path="REF_TEST_TOKEN",
        )
        assert manager.resolve(ref) == "resolved_value"

    def test_resolve_missing_raises(self) -> None:
        """Should raise for missing reference."""
        manager = EnvironmentSecretManager()
        ref = SecretReference(
            backend=SecretBackend.ENVIRONMENT,
            path="MISSING_REF_VAR",
        )
        with pytest.raises(SecretNotFoundError):
            manager.resolve(ref)

    def test_health_check(self) -> None:
        """Should always return True."""
        manager = EnvironmentSecretManager()
        assert manager.health_check() is True

    def test_info(self) -> None:
        """Should return correct info."""
        manager = EnvironmentSecretManager()
        info = manager.info()
        assert info.backend == SecretBackend.ENVIRONMENT
        assert info.connected is True
        assert info.authenticated is True

    def test_close_no_error(self) -> None:
        """Should close without error."""
        manager = EnvironmentSecretManager()
        manager.close()  # Should not raise


class TestEnvironmentConfigPrefix:
    """Tests for prefix configuration."""

    def test_prefix_applied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should apply prefix when looking up variables."""
        monkeypatch.setenv("SPECTRA_JIRA_TOKEN", "prefixed_value")
        config = EnvironmentConfig(prefix="SPECTRA_")
        manager = EnvironmentSecretManager(config)
        # Should find SPECTRA_JIRA_TOKEN when looking for JIRA_TOKEN
        assert manager.get_value("JIRA_TOKEN") == "prefixed_value"

    def test_prefix_uppercase(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should handle case conversion with prefix."""
        monkeypatch.setenv("APP_DATABASE_PASSWORD", "db_pass")
        config = EnvironmentConfig(prefix="APP_")
        manager = EnvironmentSecretManager(config)
        assert manager.get_value("database-password") == "db_pass"

    def test_original_path_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should fall back to original path if prefixed not found."""
        monkeypatch.setenv("DIRECT_VAR", "direct_value")
        config = EnvironmentConfig(prefix="PREFIX_")
        manager = EnvironmentSecretManager(config)
        # Should still find DIRECT_VAR even without prefix
        assert manager.get_value("DIRECT_VAR") == "direct_value"


class TestEnvironmentSecretManagerList:
    """Tests for listing secrets."""

    def test_list_secrets_empty_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should list variables with empty prefix."""
        monkeypatch.setenv("TEST_LIST_VAR_1", "value1")
        monkeypatch.setenv("TEST_LIST_VAR_2", "value2")
        manager = EnvironmentSecretManager()
        secrets = manager.list_secrets("")
        # Should include the test vars (and many others)
        assert "TEST_LIST_VAR_1" in secrets
        assert "TEST_LIST_VAR_2" in secrets

    def test_list_secrets_with_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should list variables matching prefix."""
        monkeypatch.setenv("UNIQUE_PREFIX_VAR1", "v1")
        monkeypatch.setenv("UNIQUE_PREFIX_VAR2", "v2")
        manager = EnvironmentSecretManager()
        secrets = manager.list_secrets("UNIQUE_PREFIX_")
        assert "UNIQUE_PREFIX_VAR1" in secrets
        assert "UNIQUE_PREFIX_VAR2" in secrets


class TestEnvironmentMetadata:
    """Tests for metadata operations."""

    def test_get_metadata_existing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return basic metadata for existing var."""
        monkeypatch.setenv("META_TEST_VAR", "value")
        manager = EnvironmentSecretManager()
        meta = manager.get_metadata("META_TEST_VAR")
        assert meta.path == "META_TEST_VAR"
        assert meta.version == "1"

    def test_get_metadata_missing_raises(self) -> None:
        """Should raise for missing variable."""
        manager = EnvironmentSecretManager()
        with pytest.raises(SecretNotFoundError):
            manager.get_metadata("NOT_EXISTING_META_VAR")


class TestContextManager:
    """Tests for context manager support."""

    def test_context_manager(self) -> None:
        """Should work as context manager."""
        with EnvironmentSecretManager() as manager:
            assert manager.health_check() is True
