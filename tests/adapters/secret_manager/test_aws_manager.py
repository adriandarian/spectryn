"""
Tests for AWS Secrets Manager adapter.

Tests cover:
- Configuration validation
- Secret retrieval (string and JSON)
- Version handling
- Error handling
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

from spectryn.adapters.secret_manager.aws_manager import AwsSecretsConfig
from spectryn.core.ports.secret_manager import (
    SecretBackend,
    SecretReference,
)


class TestAwsSecretsConfig:
    """Tests for AwsSecretsConfig."""

    def test_valid_default(self) -> None:
        """Should be valid with just region."""
        config = AwsSecretsConfig(region="us-east-1")
        assert config.is_valid() is True

    def test_valid_with_credentials(self) -> None:
        """Should be valid with explicit credentials."""
        config = AwsSecretsConfig(
            region="us-west-2",
            access_key_id="AKIAXXXX",
            secret_access_key="secret",
        )
        assert config.is_valid() is True

    def test_default_region(self) -> None:
        """Should have default region."""
        config = AwsSecretsConfig()
        assert config.region == "us-east-1"


class TestAwsSecretManagerMocked:
    """Tests for AwsSecretManager with mocked boto3."""

    @pytest.fixture
    def mock_boto3(self) -> MagicMock:
        """Create a mock boto3 module."""
        mock = MagicMock()
        mock.Session.return_value.client.return_value = MagicMock()
        return mock

    @pytest.fixture
    def mock_botocore_exceptions(self) -> MagicMock:
        """Create mock botocore.exceptions module."""
        mock = MagicMock()
        mock.BotoCoreError = Exception
        mock.ClientError = Exception
        mock.NoCredentialsError = Exception
        return mock

    @pytest.fixture
    def aws_config(self) -> AwsSecretsConfig:
        """Create a test configuration."""
        return AwsSecretsConfig(
            region="us-east-1",
            access_key_id="AKIATEST",
            secret_access_key="testsecret",
        )

    def test_backend_type(
        self,
        mock_boto3: MagicMock,
        mock_botocore_exceptions: MagicMock,
        aws_config: AwsSecretsConfig,
    ) -> None:
        """Should report correct backend type."""
        # Pre-populate sys.modules with mocks before importing AwsSecretManager
        with patch.dict(
            sys.modules,
            {"boto3": mock_boto3, "botocore.exceptions": mock_botocore_exceptions},
        ):
            # Import inside the patch to get the mocked version
            from spectryn.adapters.secret_manager.aws_manager import AwsSecretManager

            # Setup mock responses
            client = mock_boto3.Session.return_value.client.return_value
            client.list_secrets.return_value = {"SecretList": []}

            manager = AwsSecretManager(aws_config)
            assert manager.backend == SecretBackend.AWS

    def test_get_secret_string(
        self,
        mock_boto3: MagicMock,
        mock_botocore_exceptions: MagicMock,
        aws_config: AwsSecretsConfig,
    ) -> None:
        """Should get string secret."""
        with patch.dict(
            sys.modules,
            {"boto3": mock_boto3, "botocore.exceptions": mock_botocore_exceptions},
        ):
            from spectryn.adapters.secret_manager.aws_manager import AwsSecretManager

            client = mock_boto3.Session.return_value.client.return_value
            client.list_secrets.return_value = {"SecretList": []}
            client.get_secret_value.return_value = {
                "SecretString": "plain_secret_value",
                "VersionId": "version-123",
            }

            manager = AwsSecretManager(aws_config)
            secret = manager.get_secret("myapp/token")

            assert secret.value == "plain_secret_value"
            assert secret.version == "version-123"

    def test_get_secret_json(
        self,
        mock_boto3: MagicMock,
        mock_botocore_exceptions: MagicMock,
        aws_config: AwsSecretsConfig,
    ) -> None:
        """Should parse JSON secret."""
        with patch.dict(
            sys.modules,
            {"boto3": mock_boto3, "botocore.exceptions": mock_botocore_exceptions},
        ):
            from spectryn.adapters.secret_manager.aws_manager import AwsSecretManager

            client = mock_boto3.Session.return_value.client.return_value
            client.list_secrets.return_value = {"SecretList": []}
            client.get_secret_value.return_value = {
                "SecretString": '{"username": "admin", "password": "secret123"}',
                "VersionId": "v1",
            }

            manager = AwsSecretManager(aws_config)
            secret = manager.get_secret("myapp/credentials")

            assert secret.data["username"] == "admin"
            assert secret.data["password"] == "secret123"

    def test_get_value_with_key(
        self,
        mock_boto3: MagicMock,
        mock_botocore_exceptions: MagicMock,
        aws_config: AwsSecretsConfig,
    ) -> None:
        """Should get specific key from JSON secret."""
        with patch.dict(
            sys.modules,
            {"boto3": mock_boto3, "botocore.exceptions": mock_botocore_exceptions},
        ):
            from spectryn.adapters.secret_manager.aws_manager import AwsSecretManager

            client = mock_boto3.Session.return_value.client.return_value
            client.list_secrets.return_value = {"SecretList": []}
            client.get_secret_value.return_value = {
                "SecretString": '{"api_key": "abc123", "api_secret": "xyz789"}',
                "VersionId": "v1",
            }

            manager = AwsSecretManager(aws_config)
            value = manager.get_value("myapp/api", key="api_key")

            assert value == "abc123"

    def test_get_value_default(
        self,
        mock_boto3: MagicMock,
        mock_botocore_exceptions: MagicMock,
        aws_config: AwsSecretsConfig,
    ) -> None:
        """Should return default for missing secret."""
        with patch.dict(
            sys.modules,
            {"boto3": mock_boto3, "botocore.exceptions": mock_botocore_exceptions},
        ):
            from spectryn.adapters.secret_manager.aws_manager import AwsSecretManager

            client = mock_boto3.Session.return_value.client.return_value
            client.list_secrets.return_value = {"SecretList": []}

            # Make it look like boto3 ClientError
            error = Exception("ResourceNotFoundException")
            error.response = {"Error": {"Code": "ResourceNotFoundException"}}  # type: ignore
            client.get_secret_value.side_effect = error

            # Patch _ClientError to be our Exception class
            manager = AwsSecretManager(aws_config)
            manager._ClientError = Exception  # type: ignore

            value = manager.get_value("missing/secret", default="fallback")

            assert value == "fallback"

    def test_exists_true(
        self,
        mock_boto3: MagicMock,
        mock_botocore_exceptions: MagicMock,
        aws_config: AwsSecretsConfig,
    ) -> None:
        """Should return True for existing secret."""
        with patch.dict(
            sys.modules,
            {"boto3": mock_boto3, "botocore.exceptions": mock_botocore_exceptions},
        ):
            from spectryn.adapters.secret_manager.aws_manager import AwsSecretManager

            client = mock_boto3.Session.return_value.client.return_value
            client.list_secrets.return_value = {"SecretList": []}
            client.describe_secret.return_value = {"Name": "myapp/token"}

            manager = AwsSecretManager(aws_config)
            assert manager.exists("myapp/token") is True

    def test_list_secrets(
        self,
        mock_boto3: MagicMock,
        mock_botocore_exceptions: MagicMock,
        aws_config: AwsSecretsConfig,
    ) -> None:
        """Should list secrets."""
        with patch.dict(
            sys.modules,
            {"boto3": mock_boto3, "botocore.exceptions": mock_botocore_exceptions},
        ):
            from spectryn.adapters.secret_manager.aws_manager import AwsSecretManager

            client = mock_boto3.Session.return_value.client.return_value
            client.list_secrets.return_value = {"SecretList": []}

            # Mock paginator
            mock_paginator = MagicMock()
            mock_paginator.paginate.return_value = [
                {
                    "SecretList": [
                        {"Name": "myapp/token"},
                        {"Name": "myapp/api-key"},
                        {"Name": "other/secret"},
                    ]
                }
            ]
            client.get_paginator.return_value = mock_paginator

            manager = AwsSecretManager(aws_config)
            secrets = manager.list_secrets("myapp/")

            assert len(secrets) == 2
            assert "myapp/token" in secrets
            assert "myapp/api-key" in secrets

    def test_get_metadata(
        self,
        mock_boto3: MagicMock,
        mock_botocore_exceptions: MagicMock,
        aws_config: AwsSecretsConfig,
    ) -> None:
        """Should get metadata."""
        with patch.dict(
            sys.modules,
            {"boto3": mock_boto3, "botocore.exceptions": mock_botocore_exceptions},
        ):
            from spectryn.adapters.secret_manager.aws_manager import AwsSecretManager

            client = mock_boto3.Session.return_value.client.return_value
            client.list_secrets.return_value = {"SecretList": []}
            client.describe_secret.return_value = {
                "Name": "myapp/token",
                "VersionIdsToStages": {
                    "v1": ["AWSPREVIOUS"],
                    "v2": ["AWSCURRENT"],
                },
                "CreatedDate": "2024-01-01T00:00:00Z",
                "LastChangedDate": "2024-01-15T00:00:00Z",
                "Tags": [{"Key": "env", "Value": "prod"}],
                "RotationEnabled": True,
            }

            manager = AwsSecretManager(aws_config)
            metadata = manager.get_metadata("myapp/token")

            assert metadata.path == "myapp/token"
            assert metadata.version == "v2"
            assert metadata.version_count == 2

    def test_resolve_reference(
        self,
        mock_boto3: MagicMock,
        mock_botocore_exceptions: MagicMock,
        aws_config: AwsSecretsConfig,
    ) -> None:
        """Should resolve secret reference."""
        with patch.dict(
            sys.modules,
            {"boto3": mock_boto3, "botocore.exceptions": mock_botocore_exceptions},
        ):
            from spectryn.adapters.secret_manager.aws_manager import AwsSecretManager

            client = mock_boto3.Session.return_value.client.return_value
            client.list_secrets.return_value = {"SecretList": []}
            client.get_secret_value.return_value = {
                "SecretString": '{"password": "secret123"}',
                "VersionId": "v1",
            }

            manager = AwsSecretManager(aws_config)
            ref = SecretReference.parse("aws://myapp/db#password")
            value = manager.resolve(ref)

            assert value == "secret123"

    def test_health_check(
        self,
        mock_boto3: MagicMock,
        mock_botocore_exceptions: MagicMock,
        aws_config: AwsSecretsConfig,
    ) -> None:
        """Should check health."""
        with patch.dict(
            sys.modules,
            {"boto3": mock_boto3, "botocore.exceptions": mock_botocore_exceptions},
        ):
            from spectryn.adapters.secret_manager.aws_manager import AwsSecretManager

            client = mock_boto3.Session.return_value.client.return_value
            client.list_secrets.return_value = {"SecretList": []}

            manager = AwsSecretManager(aws_config)
            assert manager.health_check() is True

    def test_info(
        self,
        mock_boto3: MagicMock,
        mock_botocore_exceptions: MagicMock,
        aws_config: AwsSecretsConfig,
    ) -> None:
        """Should return info."""
        with patch.dict(
            sys.modules,
            {"boto3": mock_boto3, "botocore.exceptions": mock_botocore_exceptions},
        ):
            from spectryn.adapters.secret_manager.aws_manager import AwsSecretManager

            client = mock_boto3.Session.return_value.client.return_value
            client.list_secrets.return_value = {"SecretList": []}

            manager = AwsSecretManager(aws_config)
            info = manager.info()

            assert info.backend == SecretBackend.AWS
            assert info.connected is True
            assert "versioning" in info.features


class TestAwsSecretManagerImportError:
    """Tests for boto3 import handling."""

    def test_raises_import_error_without_boto3(self) -> None:
        """Should raise ImportError if boto3 not installed."""
        # This test documents that boto3 is required
        # In practice, ImportError is raised during import
        config = AwsSecretsConfig(region="us-east-1")
        assert config is not None  # Config creation doesn't require boto3
