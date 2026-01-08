"""
Tests for Vault Secret Manager adapter.

Tests cover:
- Configuration validation
- KV v1 and v2 secret retrieval
- Authentication methods
- Error handling
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from spectryn.adapters.secret_manager.vault_manager import (
    VaultConfig,
    VaultSecretManager,
)
from spectryn.core.ports.secret_manager import (
    AccessDeniedError,
    AuthenticationError,
    ConnectionError,
    SecretBackend,
    SecretNotFoundError,
    SecretReference,
)


class TestVaultConfig:
    """Tests for VaultConfig."""

    def test_valid_with_token(self) -> None:
        """Should be valid with address and token."""
        config = VaultConfig(
            address="https://vault.example.com:8200",
            token="hvs.xxx",
        )
        assert config.is_valid() is True

    def test_valid_with_approle(self) -> None:
        """Should be valid with AppRole credentials."""
        config = VaultConfig(
            address="https://vault.example.com:8200",
            role_id="role-123",
            secret_id="secret-456",
        )
        assert config.is_valid() is True

    def test_valid_with_kubernetes(self) -> None:
        """Should be valid with Kubernetes auth."""
        config = VaultConfig(
            address="https://vault.example.com:8200",
            kubernetes_role="my-role",
        )
        assert config.is_valid() is True

    def test_invalid_no_auth(self) -> None:
        """Should be invalid without auth method."""
        config = VaultConfig(address="https://vault.example.com:8200")
        assert config.is_valid() is False

    def test_invalid_no_address(self) -> None:
        """Should be invalid without address."""
        config = VaultConfig(address="", token="hvs.xxx")
        assert config.is_valid() is False

    def test_default_values(self) -> None:
        """Should have correct defaults."""
        config = VaultConfig(
            address="https://vault.example.com",
            token="hvs.xxx",
        )
        assert config.mount_point == "secret"
        assert config.kv_version == 2
        assert config.timeout == 30
        assert config.verify_ssl is True


class TestVaultSecretManagerMocked:
    """Tests for VaultSecretManager with mocked HTTP."""

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Create a mock requests session."""
        session = MagicMock()
        session.headers = {}
        return session

    @pytest.fixture
    def vault_config(self) -> VaultConfig:
        """Create a test configuration."""
        return VaultConfig(
            address="https://vault.example.com:8200",
            token="hvs.test_token",
            mount_point="secret",
            kv_version=2,
        )

    def test_backend_type(
        self,
        mock_session: MagicMock,
        vault_config: VaultConfig,
    ) -> None:
        """Should report correct backend type."""
        with patch("requests.Session", return_value=mock_session):
            # Mock successful auth verification
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"data": {}}
            mock_session.get.return_value = mock_response

            manager = VaultSecretManager(vault_config)
            assert manager.backend == SecretBackend.VAULT

    def test_get_secret_kv2(
        self,
        mock_session: MagicMock,
        vault_config: VaultConfig,
    ) -> None:
        """Should get secret from KV v2."""
        with patch("requests.Session", return_value=mock_session):
            # Mock auth verification
            auth_response = MagicMock()
            auth_response.status_code = 200
            auth_response.json.return_value = {}

            # Mock secret retrieval
            secret_response = MagicMock()
            secret_response.status_code = 200
            secret_response.json.return_value = {
                "data": {
                    "data": {"api_token": "secret123", "user": "admin"},
                    "metadata": {"version": 1},
                }
            }
            secret_response.raise_for_status = MagicMock()

            mock_session.get.side_effect = [auth_response, secret_response]

            manager = VaultSecretManager(vault_config)
            secret = manager.get_secret("myapp/config")

            assert secret.data["api_token"] == "secret123"
            assert secret.data["user"] == "admin"

    def test_get_value_with_key(
        self,
        mock_session: MagicMock,
        vault_config: VaultConfig,
    ) -> None:
        """Should get specific key from secret."""
        with patch("requests.Session", return_value=mock_session):
            auth_response = MagicMock()
            auth_response.status_code = 200
            auth_response.json.return_value = {}

            secret_response = MagicMock()
            secret_response.status_code = 200
            secret_response.json.return_value = {
                "data": {
                    "data": {"password": "hunter2", "username": "admin"},
                    "metadata": {"version": 1},
                }
            }
            secret_response.raise_for_status = MagicMock()

            mock_session.get.side_effect = [auth_response, secret_response]

            manager = VaultSecretManager(vault_config)
            value = manager.get_value("myapp/db", key="password")

            assert value == "hunter2"

    def test_get_value_default(
        self,
        mock_session: MagicMock,
        vault_config: VaultConfig,
    ) -> None:
        """Should return default for missing secret."""
        with patch("requests.Session", return_value=mock_session):
            auth_response = MagicMock()
            auth_response.status_code = 200
            auth_response.json.return_value = {}

            secret_response = MagicMock()
            secret_response.status_code = 404

            mock_session.get.side_effect = [auth_response, secret_response]

            manager = VaultSecretManager(vault_config)
            value = manager.get_value("missing/secret", default="fallback")

            assert value == "fallback"

    def test_secret_not_found(
        self,
        mock_session: MagicMock,
        vault_config: VaultConfig,
    ) -> None:
        """Should raise SecretNotFoundError for 404."""
        with patch("requests.Session", return_value=mock_session):
            auth_response = MagicMock()
            auth_response.status_code = 200
            auth_response.json.return_value = {}

            secret_response = MagicMock()
            secret_response.status_code = 404

            mock_session.get.side_effect = [auth_response, secret_response]

            manager = VaultSecretManager(vault_config)

            with pytest.raises(SecretNotFoundError):
                manager.get_secret("missing/secret")

    def test_access_denied(
        self,
        mock_session: MagicMock,
        vault_config: VaultConfig,
    ) -> None:
        """Should raise AccessDeniedError for 403."""
        with patch("requests.Session", return_value=mock_session):
            auth_response = MagicMock()
            auth_response.status_code = 200
            auth_response.json.return_value = {}

            secret_response = MagicMock()
            secret_response.status_code = 403

            mock_session.get.side_effect = [auth_response, secret_response]

            manager = VaultSecretManager(vault_config)

            with pytest.raises(AccessDeniedError):
                manager.get_secret("forbidden/secret")

    def test_health_check_healthy(
        self,
        mock_session: MagicMock,
        vault_config: VaultConfig,
    ) -> None:
        """Should return True for healthy vault."""
        with patch("requests.Session", return_value=mock_session):
            auth_response = MagicMock()
            auth_response.status_code = 200
            auth_response.json.return_value = {}

            health_response = MagicMock()
            health_response.status_code = 200

            mock_session.get.side_effect = [auth_response, health_response]

            manager = VaultSecretManager(vault_config)
            assert manager.health_check() is True

    def test_health_check_sealed(
        self,
        mock_session: MagicMock,
        vault_config: VaultConfig,
    ) -> None:
        """Should return False for sealed vault."""
        with patch("requests.Session", return_value=mock_session):
            auth_response = MagicMock()
            auth_response.status_code = 200
            auth_response.json.return_value = {}

            health_response = MagicMock()
            health_response.status_code = 503

            mock_session.get.side_effect = [auth_response, health_response]

            manager = VaultSecretManager(vault_config)
            assert manager.health_check() is False

    def test_list_secrets(
        self,
        mock_session: MagicMock,
        vault_config: VaultConfig,
    ) -> None:
        """Should list secrets."""
        with patch("requests.Session", return_value=mock_session):
            auth_response = MagicMock()
            auth_response.status_code = 200
            auth_response.json.return_value = {}

            list_response = MagicMock()
            list_response.status_code = 200
            list_response.json.return_value = {"data": {"keys": ["secret1", "secret2"]}}
            list_response.raise_for_status = MagicMock()

            mock_session.get.return_value = auth_response
            mock_session.request.return_value = list_response

            manager = VaultSecretManager(vault_config)
            secrets = manager.list_secrets("myapp")

            assert "myapp/secret1" in secrets
            assert "myapp/secret2" in secrets

    def test_exists_true(
        self,
        mock_session: MagicMock,
        vault_config: VaultConfig,
    ) -> None:
        """Should return True for existing secret."""
        with patch("requests.Session", return_value=mock_session):
            auth_response = MagicMock()
            auth_response.status_code = 200
            auth_response.json.return_value = {}

            secret_response = MagicMock()
            secret_response.status_code = 200
            secret_response.json.return_value = {
                "data": {"data": {"value": "test"}, "metadata": {}}
            }
            secret_response.raise_for_status = MagicMock()

            mock_session.get.side_effect = [auth_response, secret_response]

            manager = VaultSecretManager(vault_config)
            assert manager.exists("myapp/token") is True

    def test_exists_false(
        self,
        mock_session: MagicMock,
        vault_config: VaultConfig,
    ) -> None:
        """Should return False for missing secret."""
        with patch("requests.Session", return_value=mock_session):
            auth_response = MagicMock()
            auth_response.status_code = 200
            auth_response.json.return_value = {}

            secret_response = MagicMock()
            secret_response.status_code = 404

            mock_session.get.side_effect = [auth_response, secret_response]

            manager = VaultSecretManager(vault_config)
            assert manager.exists("missing/secret") is False

    def test_resolve_reference(
        self,
        mock_session: MagicMock,
        vault_config: VaultConfig,
    ) -> None:
        """Should resolve secret reference."""
        with patch("requests.Session", return_value=mock_session):
            auth_response = MagicMock()
            auth_response.status_code = 200
            auth_response.json.return_value = {}

            secret_response = MagicMock()
            secret_response.status_code = 200
            secret_response.json.return_value = {
                "data": {"data": {"api_token": "resolved123"}, "metadata": {}}
            }
            secret_response.raise_for_status = MagicMock()

            mock_session.get.side_effect = [auth_response, secret_response]

            manager = VaultSecretManager(vault_config)
            ref = SecretReference(
                backend=SecretBackend.VAULT,
                path="myapp/config",
                key="api_token",
            )
            value = manager.resolve(ref)
            assert value == "resolved123"

    def test_info(
        self,
        mock_session: MagicMock,
        vault_config: VaultConfig,
    ) -> None:
        """Should return correct info."""
        with patch("requests.Session", return_value=mock_session):
            auth_response = MagicMock()
            auth_response.status_code = 200
            auth_response.json.return_value = {}

            health_response = MagicMock()
            health_response.status_code = 200

            mock_session.get.side_effect = [auth_response, health_response]

            manager = VaultSecretManager(vault_config)
            info = manager.info()

            assert info.backend == SecretBackend.VAULT
            assert info.connected is True
            assert info.authenticated is True
            assert "versioning" in info.features

    def test_close(
        self,
        mock_session: MagicMock,
        vault_config: VaultConfig,
    ) -> None:
        """Should close session."""
        with patch("requests.Session", return_value=mock_session):
            auth_response = MagicMock()
            auth_response.status_code = 200
            auth_response.json.return_value = {}
            mock_session.get.return_value = auth_response

            manager = VaultSecretManager(vault_config)
            manager.close()

            mock_session.close.assert_called_once()


class TestVaultAuthenticationErrors:
    """Tests for authentication error handling."""

    def test_invalid_token(self) -> None:
        """Should raise AuthenticationError for invalid token."""
        config = VaultConfig(
            address="https://vault.example.com:8200",
            token="invalid",
        )

        mock_session = MagicMock()
        mock_session.headers = {}
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_session.get.return_value = mock_response

        with patch("requests.Session", return_value=mock_session):
            with pytest.raises(AuthenticationError, match="invalid or expired"):
                VaultSecretManager(config)

    def test_connection_error(self) -> None:
        """Should raise ConnectionError for network issues."""
        config = VaultConfig(
            address="https://unreachable.example.com:8200",
            token="hvs.xxx",
        )

        mock_session = MagicMock()
        mock_session.headers = {}
        mock_session.get.side_effect = requests.exceptions.ConnectionError("timeout")

        with patch("requests.Session", return_value=mock_session):
            with pytest.raises(ConnectionError):
                VaultSecretManager(config)
