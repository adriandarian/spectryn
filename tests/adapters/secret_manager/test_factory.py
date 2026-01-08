"""
Tests for Secret Manager Factory.

Tests cover:
- Auto-detection of backends
- Factory creation
- Config secret resolution
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from spectryn.adapters.secret_manager.environment_manager import EnvironmentSecretManager
from spectryn.adapters.secret_manager.factory import (
    create_secret_manager,
    get_config_secret,
    get_global_secret_manager,
    resolve_config_secrets,
    set_global_secret_manager,
)
from spectryn.core.ports.secret_manager import SecretBackend


class TestCreateSecretManager:
    """Tests for create_secret_manager factory."""

    def test_create_environment_manager(self) -> None:
        """Should create environment manager by default."""
        manager = create_secret_manager(
            SecretBackend.ENVIRONMENT,
            fallback_to_env=False,
        )
        assert isinstance(manager, EnvironmentSecretManager)

    def test_create_from_string(self) -> None:
        """Should accept string backend name."""
        manager = create_secret_manager(
            "environment",
            fallback_to_env=False,
        )
        assert isinstance(manager, EnvironmentSecretManager)

    def test_auto_detect_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should default to environment when nothing else configured."""
        # Clear any vault/doppler/etc env vars
        for var in ["VAULT_ADDR", "DOPPLER_TOKEN", "OP_SERVICE_ACCOUNT_TOKEN"]:
            monkeypatch.delenv(var, raising=False)

        manager = create_secret_manager(fallback_to_env=False)
        assert isinstance(manager, EnvironmentSecretManager)

    def test_auto_detect_vault(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should detect Vault from VAULT_ADDR."""
        monkeypatch.setenv("VAULT_ADDR", "https://vault.example.com:8200")
        monkeypatch.setenv("VAULT_TOKEN", "hvs.test")

        # This would try to connect, so we just test detection
        from spectryn.adapters.secret_manager.factory import _detect_backend

        assert _detect_backend() == SecretBackend.VAULT

    def test_auto_detect_doppler(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should detect Doppler from DOPPLER_TOKEN."""
        monkeypatch.delenv("VAULT_ADDR", raising=False)
        monkeypatch.setenv("DOPPLER_TOKEN", "dp.st.xxx")

        from spectryn.adapters.secret_manager.factory import _detect_backend

        assert _detect_backend() == SecretBackend.DOPPLER

    def test_auto_detect_onepassword(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should detect 1Password from OP_SERVICE_ACCOUNT_TOKEN."""
        monkeypatch.delenv("VAULT_ADDR", raising=False)
        monkeypatch.delenv("DOPPLER_TOKEN", raising=False)
        monkeypatch.setenv("OP_SERVICE_ACCOUNT_TOKEN", "ops_xxx")

        from spectryn.adapters.secret_manager.factory import _detect_backend

        assert _detect_backend() == SecretBackend.ONEPASSWORD

    def test_fallback_creates_composite(self) -> None:
        """Should create composite manager with fallback."""
        manager = create_secret_manager(
            SecretBackend.ENVIRONMENT,
            fallback_to_env=True,
        )
        # Composite wraps the environment manager
        assert manager.backend == SecretBackend.ENVIRONMENT


class TestGetConfigSecret:
    """Tests for get_config_secret convenience function."""

    def test_resolve_env_shorthand(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should resolve $VAR shorthand."""
        monkeypatch.setenv("MY_TEST_TOKEN", "token_value")
        value = get_config_secret("$MY_TEST_TOKEN")
        assert value == "token_value"

    def test_resolve_env_shorthand_default(self) -> None:
        """Should return default for missing $VAR."""
        value = get_config_secret("$MISSING_VAR_XYZ", default="fallback")
        assert value == "fallback"

    def test_literal_value(self) -> None:
        """Should return literal values as-is."""
        value = get_config_secret("not-a-reference")
        assert value == "not-a-reference"

    def test_resolve_environment_reference(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Should resolve environment:// references."""
        monkeypatch.setenv("TEST_ENV_REF", "env_ref_value")
        value = get_config_secret("environment://TEST_ENV_REF")
        assert value == "env_ref_value"


class TestResolveConfigSecrets:
    """Tests for resolve_config_secrets function."""

    def test_resolve_nested_dict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should resolve nested references."""
        monkeypatch.setenv("NESTED_TOKEN", "nested_value")

        config = {
            "tracker": {
                "type": "jira",
                "token": "$NESTED_TOKEN",
                "url": "https://jira.example.com",
            }
        }

        resolved = resolve_config_secrets(config)
        assert resolved["tracker"]["token"] == "nested_value"
        assert resolved["tracker"]["url"] == "https://jira.example.com"

    def test_resolve_list_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should resolve references in lists."""
        monkeypatch.setenv("LIST_TOKEN", "list_value")

        config = {"tokens": ["literal", "$LIST_TOKEN"]}

        resolved = resolve_config_secrets(config)
        assert resolved["tokens"][0] == "literal"
        assert resolved["tokens"][1] == "list_value"

    def test_preserve_non_strings(self) -> None:
        """Should preserve non-string values."""
        config = {
            "port": 8080,
            "enabled": True,
            "tags": ["a", "b"],
        }

        resolved = resolve_config_secrets(config)
        assert resolved["port"] == 8080
        assert resolved["enabled"] is True


class TestGlobalSecretManager:
    """Tests for global manager functions."""

    def test_get_global_creates(self) -> None:
        """Should create global manager on first access."""
        # Reset global state
        from spectryn.adapters.secret_manager import factory

        factory._global_manager = None

        manager = get_global_secret_manager()
        assert manager is not None

    def test_get_global_singleton(self) -> None:
        """Should return same instance."""
        m1 = get_global_secret_manager()
        m2 = get_global_secret_manager()
        assert m1 is m2

    def test_set_global(self) -> None:
        """Should allow setting global manager."""
        custom = EnvironmentSecretManager()
        set_global_secret_manager(custom)
        assert get_global_secret_manager() is custom
