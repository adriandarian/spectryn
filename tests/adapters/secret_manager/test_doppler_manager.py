"""
Tests for Doppler Secret Manager adapter.

Tests cover:
- Configuration validation
- Secret retrieval
- Project/config handling
- Error handling
"""

from unittest.mock import MagicMock, patch

import pytest

from spectryn.adapters.secret_manager.doppler_manager import (
    DopplerConfig,
    DopplerSecretManager,
)
from spectryn.core.ports.secret_manager import (
    AccessDeniedError,
    AuthenticationError,
    SecretBackend,
    SecretNotFoundError,
    SecretReference,
)


class TestDopplerConfig:
    """Tests for DopplerConfig."""

    def test_valid_with_token(self) -> None:
        """Should be valid with token."""
        config = DopplerConfig(token="dp.st.xxx")
        assert config.is_valid() is True

    def test_invalid_without_token(self) -> None:
        """Should be invalid without token."""
        config = DopplerConfig(token="")
        assert config.is_valid() is False

    def test_default_api_url(self) -> None:
        """Should have default API URL."""
        config = DopplerConfig(token="dp.st.xxx")
        assert config.api_url == "https://api.doppler.com/v3"


class TestDopplerSecretManagerMocked:
    """Tests for DopplerSecretManager with mocked HTTP."""

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Create a mock requests session."""
        session = MagicMock()
        session.auth = ("token", "")
        session.headers = {}
        return session

    @pytest.fixture
    def doppler_config(self) -> DopplerConfig:
        """Create a test configuration."""
        return DopplerConfig(
            token="dp.st.test",
            project="myapp",
            config="production",
        )

    def test_backend_type(
        self,
        mock_session: MagicMock,
        doppler_config: DopplerConfig,
    ) -> None:
        """Should report correct backend type."""
        with patch("requests.Session", return_value=mock_session):
            # Mock auth verification
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {}
            mock_response.raise_for_status = MagicMock()
            mock_session.get.return_value = mock_response

            manager = DopplerSecretManager(doppler_config)
            assert manager.backend == SecretBackend.DOPPLER

    def test_get_secret_single(
        self,
        mock_session: MagicMock,
        doppler_config: DopplerConfig,
    ) -> None:
        """Should get a single secret."""
        with patch("requests.Session", return_value=mock_session):
            auth_response = MagicMock()
            auth_response.status_code = 200
            auth_response.json.return_value = {}
            auth_response.raise_for_status = MagicMock()

            secrets_response = MagicMock()
            secrets_response.status_code = 200
            secrets_response.json.return_value = {
                "secrets": {
                    "API_KEY": {"computed": "key123", "raw": "key123"},
                    "DB_PASSWORD": {"computed": "pass456", "raw": "pass456"},
                }
            }
            secrets_response.raise_for_status = MagicMock()

            mock_session.get.return_value = auth_response
            mock_session.request.return_value = secrets_response

            manager = DopplerSecretManager(doppler_config)
            secret = manager.get_secret("API_KEY")

            assert secret.value == "key123"

    def test_get_secret_all(
        self,
        mock_session: MagicMock,
        doppler_config: DopplerConfig,
    ) -> None:
        """Should get all secrets for a config."""
        with patch("requests.Session", return_value=mock_session):
            auth_response = MagicMock()
            auth_response.status_code = 200
            auth_response.json.return_value = {}
            auth_response.raise_for_status = MagicMock()

            secrets_response = MagicMock()
            secrets_response.status_code = 200
            secrets_response.json.return_value = {
                "secrets": {
                    "API_KEY": {"computed": "key123"},
                    "DB_PASSWORD": {"computed": "pass456"},
                }
            }
            secrets_response.raise_for_status = MagicMock()

            mock_session.get.return_value = auth_response
            mock_session.request.return_value = secrets_response

            manager = DopplerSecretManager(doppler_config)
            secret = manager.get_secret("myapp/production")

            assert "API_KEY" in secret.data
            assert "DB_PASSWORD" in secret.data

    def test_get_value(
        self,
        mock_session: MagicMock,
        doppler_config: DopplerConfig,
    ) -> None:
        """Should get secret value directly."""
        with patch("requests.Session", return_value=mock_session):
            auth_response = MagicMock()
            auth_response.status_code = 200
            auth_response.json.return_value = {}
            auth_response.raise_for_status = MagicMock()

            secrets_response = MagicMock()
            secrets_response.status_code = 200
            secrets_response.json.return_value = {
                "secrets": {
                    "JIRA_TOKEN": {"computed": "jira_secret"},
                }
            }
            secrets_response.raise_for_status = MagicMock()

            mock_session.get.return_value = auth_response
            mock_session.request.return_value = secrets_response

            manager = DopplerSecretManager(doppler_config)
            value = manager.get_value("JIRA_TOKEN")

            assert value == "jira_secret"

    def test_get_value_default(
        self,
        mock_session: MagicMock,
        doppler_config: DopplerConfig,
    ) -> None:
        """Should return default for missing secret."""
        with patch("requests.Session", return_value=mock_session):
            auth_response = MagicMock()
            auth_response.status_code = 200
            auth_response.json.return_value = {}
            auth_response.raise_for_status = MagicMock()

            secrets_response = MagicMock()
            secrets_response.status_code = 200
            secrets_response.json.return_value = {"secrets": {}}
            secrets_response.raise_for_status = MagicMock()

            mock_session.get.return_value = auth_response
            mock_session.request.return_value = secrets_response

            manager = DopplerSecretManager(doppler_config)
            value = manager.get_value("MISSING_SECRET", default="fallback")

            assert value == "fallback"

    def test_exists_true(
        self,
        mock_session: MagicMock,
        doppler_config: DopplerConfig,
    ) -> None:
        """Should return True for existing secret."""
        with patch("requests.Session", return_value=mock_session):
            auth_response = MagicMock()
            auth_response.status_code = 200
            auth_response.json.return_value = {}
            auth_response.raise_for_status = MagicMock()

            secrets_response = MagicMock()
            secrets_response.status_code = 200
            secrets_response.json.return_value = {"secrets": {"API_KEY": {"computed": "value"}}}
            secrets_response.raise_for_status = MagicMock()

            mock_session.get.return_value = auth_response
            mock_session.request.return_value = secrets_response

            manager = DopplerSecretManager(doppler_config)
            assert manager.exists("API_KEY") is True

    def test_list_projects(
        self,
        mock_session: MagicMock,
        doppler_config: DopplerConfig,
    ) -> None:
        """Should list projects."""
        with patch("requests.Session", return_value=mock_session):
            auth_response = MagicMock()
            auth_response.status_code = 200
            auth_response.json.return_value = {}
            auth_response.raise_for_status = MagicMock()

            projects_response = MagicMock()
            projects_response.status_code = 200
            projects_response.json.return_value = {
                "projects": [{"name": "project1"}, {"name": "project2"}]
            }
            projects_response.raise_for_status = MagicMock()

            mock_session.get.return_value = auth_response
            mock_session.request.return_value = projects_response

            manager = DopplerSecretManager(doppler_config)
            projects = manager.list_secrets()

            assert "project1" in projects
            assert "project2" in projects

    def test_resolve_reference(
        self,
        mock_session: MagicMock,
        doppler_config: DopplerConfig,
    ) -> None:
        """Should resolve secret reference."""
        with patch("requests.Session", return_value=mock_session):
            auth_response = MagicMock()
            auth_response.status_code = 200
            auth_response.json.return_value = {}
            auth_response.raise_for_status = MagicMock()

            secrets_response = MagicMock()
            secrets_response.status_code = 200
            secrets_response.json.return_value = {
                "secrets": {"TOKEN": {"computed": "resolved_token"}}
            }
            secrets_response.raise_for_status = MagicMock()

            mock_session.get.return_value = auth_response
            mock_session.request.return_value = secrets_response

            manager = DopplerSecretManager(doppler_config)
            ref = SecretReference(
                backend=SecretBackend.DOPPLER,
                path="TOKEN",
            )
            value = manager.resolve(ref)

            assert value == "resolved_token"

    def test_health_check(
        self,
        mock_session: MagicMock,
        doppler_config: DopplerConfig,
    ) -> None:
        """Should check health."""
        with patch("requests.Session", return_value=mock_session):
            auth_response = MagicMock()
            auth_response.status_code = 200
            auth_response.json.return_value = {}
            auth_response.raise_for_status = MagicMock()

            mock_session.get.return_value = auth_response

            manager = DopplerSecretManager(doppler_config)
            assert manager.health_check() is True

    def test_info(
        self,
        mock_session: MagicMock,
        doppler_config: DopplerConfig,
    ) -> None:
        """Should return info."""
        with patch("requests.Session", return_value=mock_session):
            auth_response = MagicMock()
            auth_response.status_code = 200
            auth_response.json.return_value = {"workplace": {"name": "TestWorkplace"}}
            auth_response.raise_for_status = MagicMock()

            mock_session.get.return_value = auth_response
            mock_session.request.return_value = auth_response

            manager = DopplerSecretManager(doppler_config)
            info = manager.info()

            assert info.backend == SecretBackend.DOPPLER
            assert info.connected is True

    def test_close(
        self,
        mock_session: MagicMock,
        doppler_config: DopplerConfig,
    ) -> None:
        """Should close session."""
        with patch("requests.Session", return_value=mock_session):
            auth_response = MagicMock()
            auth_response.status_code = 200
            auth_response.json.return_value = {}
            auth_response.raise_for_status = MagicMock()
            mock_session.get.return_value = auth_response

            manager = DopplerSecretManager(doppler_config)
            manager.close()

            mock_session.close.assert_called_once()


class TestDopplerAuthenticationErrors:
    """Tests for authentication error handling."""

    def test_invalid_token(self) -> None:
        """Should raise AuthenticationError for invalid token."""
        config = DopplerConfig(token="invalid_token")

        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_session.get.return_value = mock_response

        with patch("requests.Session", return_value=mock_session):
            with pytest.raises(AuthenticationError, match="Invalid token"):
                DopplerSecretManager(config)
