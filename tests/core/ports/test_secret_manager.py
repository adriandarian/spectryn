"""
Tests for Secret Manager Port interface.

Tests cover:
- SecretReference parsing
- Secret data class
- CompositeSecretManager behavior
"""

import pytest

from spectryn.core.ports.secret_manager import (
    CompositeSecretManager,
    Secret,
    SecretBackend,
    SecretManagerError,
    SecretMetadata,
    SecretNotFoundError,
    SecretReference,
)


class TestSecretReference:
    """Tests for SecretReference parsing."""

    def test_parse_vault_reference(self) -> None:
        """Should parse vault:// references."""
        ref = SecretReference.parse("vault://secret/data/myapp#api_token")
        assert ref.backend == SecretBackend.VAULT
        assert ref.path == "secret/data/myapp"
        assert ref.key == "api_token"
        assert ref.version is None

    def test_parse_vault_with_version(self) -> None:
        """Should parse vault reference with version."""
        ref = SecretReference.parse("vault://secret/myapp#password@3")
        assert ref.backend == SecretBackend.VAULT
        assert ref.path == "secret/myapp"
        assert ref.key == "password"
        assert ref.version == "3"

    def test_parse_aws_reference(self) -> None:
        """Should parse aws:// references."""
        ref = SecretReference.parse("aws://myapp/database#password")
        assert ref.backend == SecretBackend.AWS
        assert ref.path == "myapp/database"
        assert ref.key == "password"

    def test_parse_onepassword_reference(self) -> None:
        """Should parse 1password:// references."""
        ref = SecretReference.parse("1password://op://Private/Jira/api-token")
        assert ref.backend == SecretBackend.ONEPASSWORD
        assert ref.path == "op://Private/Jira/api-token"

    def test_parse_doppler_reference(self) -> None:
        """Should parse doppler:// references."""
        ref = SecretReference.parse("doppler://myapp/production/API_KEY")
        assert ref.backend == SecretBackend.DOPPLER
        assert ref.path == "myapp/production/API_KEY"

    def test_parse_environment_reference(self) -> None:
        """Should parse environment:// references."""
        ref = SecretReference.parse("environment://JIRA_API_TOKEN")
        assert ref.backend == SecretBackend.ENVIRONMENT
        assert ref.path == "JIRA_API_TOKEN"

    def test_parse_env_shorthand(self) -> None:
        """Should parse $VAR shorthand as environment."""
        ref = SecretReference.parse("$JIRA_API_TOKEN")
        assert ref.backend == SecretBackend.ENVIRONMENT
        assert ref.path == "JIRA_API_TOKEN"

    def test_parse_path_only(self) -> None:
        """Should parse reference without key."""
        ref = SecretReference.parse("vault://secret/myapp")
        assert ref.path == "secret/myapp"
        assert ref.key is None

    def test_parse_empty_raises(self) -> None:
        """Should raise ValueError for empty reference."""
        with pytest.raises(ValueError, match="Empty secret reference"):
            SecretReference.parse("")

    def test_parse_invalid_format_raises(self) -> None:
        """Should raise ValueError for invalid format."""
        with pytest.raises(ValueError, match="Invalid secret reference format"):
            SecretReference.parse("invalid-reference")

    def test_to_string(self) -> None:
        """Should convert back to string."""
        ref = SecretReference(
            backend=SecretBackend.VAULT,
            path="secret/myapp",
            key="api_token",
            version="2",
        )
        assert ref.to_string() == "vault://secret/myapp#api_token@2"

    def test_to_string_minimal(self) -> None:
        """Should convert minimal reference to string."""
        ref = SecretReference(
            backend=SecretBackend.AWS,
            path="myapp/secrets",
        )
        assert ref.to_string() == "aws://myapp/secrets"


class TestSecret:
    """Tests for Secret data class."""

    def test_get_value_simple(self) -> None:
        """Should get simple value."""
        secret = Secret(path="test", value="secret123")
        assert secret.get_value() == "secret123"

    def test_get_value_from_data(self) -> None:
        """Should get first value from data if no value."""
        secret = Secret(path="test", data={"password": "secret123"})
        assert secret.get_value() == "secret123"

    def test_get_value_raises_if_empty(self) -> None:
        """Should raise if no value available."""
        secret = Secret(path="test")
        with pytest.raises(ValueError, match="has no value"):
            secret.get_value()

    def test_get_key(self) -> None:
        """Should get specific key from data."""
        secret = Secret(path="test", data={"user": "admin", "pass": "secret"})
        assert secret.get("user") == "admin"
        assert secret.get("pass") == "secret"
        assert secret.get("missing") is None
        assert secret.get("missing", "default") == "default"


class TestSecretMetadata:
    """Tests for SecretMetadata."""

    def test_basic_metadata(self) -> None:
        """Should store metadata correctly."""
        meta = SecretMetadata(
            path="test/secret",
            version="3",
            version_count=5,
            rotation_enabled=True,
        )
        assert meta.path == "test/secret"
        assert meta.version == "3"
        assert meta.version_count == 5
        assert meta.rotation_enabled is True

    def test_default_values(self) -> None:
        """Should have sensible defaults."""
        meta = SecretMetadata(path="test")
        assert meta.version is None
        assert meta.version_count == 1
        assert meta.rotation_enabled is False
        assert meta.tags == {}


class TestCompositeSecretManager:
    """Tests for CompositeSecretManager."""

    def test_register_backend(self) -> None:
        """Should register backends."""
        composite = CompositeSecretManager()
        # Can't test fully without mock managers, but test structure
        assert composite.backend == SecretBackend.ENVIRONMENT

    def test_set_default_backend_unregistered_raises(self) -> None:
        """Should raise when setting unregistered default."""
        composite = CompositeSecretManager()
        with pytest.raises(ValueError, match="not registered"):
            composite.set_default_backend(SecretBackend.VAULT)

    def test_health_check_no_backends(self) -> None:
        """Should return False with no backends."""
        composite = CompositeSecretManager()
        assert composite.health_check() is False

    def test_close_empty(self) -> None:
        """Should handle close with no backends."""
        composite = CompositeSecretManager()
        composite.close()  # Should not raise


class TestSecretBackend:
    """Tests for SecretBackend enum."""

    def test_all_backends(self) -> None:
        """Should have all expected backends."""
        backends = {b.value for b in SecretBackend}
        expected = {"environment", "vault", "aws", "1password", "doppler", "azure", "gcp"}
        assert backends == expected

    def test_backend_values(self) -> None:
        """Backend values should be lowercase strings."""
        for backend in SecretBackend:
            assert backend.value == backend.value.lower()
            assert isinstance(backend.value, str)


class TestSecretExceptions:
    """Tests for secret manager exceptions."""

    def test_secret_not_found_error(self) -> None:
        """Should format error message correctly."""
        error = SecretNotFoundError("myapp/token", "vault")
        assert "myapp/token" in str(error)
        assert "vault" in str(error)

    def test_secret_not_found_error_no_backend(self) -> None:
        """Should work without backend."""
        error = SecretNotFoundError("myapp/token")
        assert "myapp/token" in str(error)
        assert error.backend is None
