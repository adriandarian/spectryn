"""
AWS Secrets Manager Secret Manager.

AWS native secret storage with support for:
- Secret versioning
- Automatic rotation
- Cross-region replication
- IAM-based access control
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from spectryn.core.ports.secret_manager import (
    AccessDeniedError,
    AuthenticationError,
    ConnectionError,
    Secret,
    SecretBackend,
    SecretManagerError,
    SecretManagerInfo,
    SecretManagerPort,
    SecretMetadata,
    SecretNotFoundError,
    SecretReference,
)


logger = logging.getLogger(__name__)


@dataclass
class AwsSecretsConfig:
    """
    Configuration for AWS Secrets Manager.

    Attributes:
        region: AWS region (e.g., "us-east-1").
        access_key_id: AWS access key ID (optional, uses default chain if not set).
        secret_access_key: AWS secret access key.
        session_token: AWS session token (for temporary credentials).
        profile: AWS profile name to use.
        endpoint_url: Custom endpoint URL (for LocalStack/testing).
        prefix: Prefix for all secret names.
    """

    region: str = "us-east-1"
    access_key_id: str | None = None
    secret_access_key: str | None = None
    session_token: str | None = None
    profile: str | None = None
    endpoint_url: str | None = None
    prefix: str = ""

    def is_valid(self) -> bool:
        """Check if configuration is valid."""
        # Either explicit credentials or default chain (profile/env/IAM role)
        return bool(self.region)


class AwsSecretManager(SecretManagerPort):
    """
    AWS Secrets Manager implementation.

    Supports:
    - String and JSON secrets
    - Secret versioning (AWSCURRENT, AWSPREVIOUS, custom labels)
    - Automatic rotation status
    - IAM-based authentication

    Requires boto3 to be installed.

    Example:
        config = AwsSecretsConfig(region="us-east-1")
        manager = AwsSecretManager(config)

        # Get a secret
        secret = manager.get_secret("myapp/database")

        # Get a specific version
        secret = manager.get_secret("myapp/database", version="AWSPREVIOUS")

        # Get a specific key from a JSON secret
        password = manager.get_value("myapp/database", key="password")
    """

    def __init__(self, config: AwsSecretsConfig) -> None:
        """
        Initialize the AWS Secrets Manager.

        Args:
            config: AWS configuration.

        Raises:
            ImportError: If boto3 is not installed.
            AuthenticationError: If authentication fails.
        """
        self._config = config
        self._client: Any = None

        try:
            import boto3
            from botocore.exceptions import (
                BotoCoreError,
                ClientError,
                NoCredentialsError,
            )

            self._boto3 = boto3
            self._BotoCoreError = BotoCoreError
            self._ClientError = ClientError
            self._NoCredentialsError = NoCredentialsError
        except ImportError as e:
            raise ImportError(
                "boto3 is required for AWS Secrets Manager. Install with: pip install boto3"
            ) from e

        self._connect()

    def _connect(self) -> None:
        """Connect to AWS Secrets Manager."""
        try:
            session_kwargs: dict[str, Any] = {}
            if self._config.profile:
                session_kwargs["profile_name"] = self._config.profile
            if self._config.region:
                session_kwargs["region_name"] = self._config.region

            session = self._boto3.Session(**session_kwargs)

            client_kwargs: dict[str, Any] = {}
            if self._config.access_key_id and self._config.secret_access_key:
                client_kwargs["aws_access_key_id"] = self._config.access_key_id
                client_kwargs["aws_secret_access_key"] = self._config.secret_access_key
                if self._config.session_token:
                    client_kwargs["aws_session_token"] = self._config.session_token
            if self._config.endpoint_url:
                client_kwargs["endpoint_url"] = self._config.endpoint_url

            self._client = session.client("secretsmanager", **client_kwargs)

            # Verify connection by listing secrets (limited to 1)
            self._client.list_secrets(MaxResults=1)
            logger.debug("Connected to AWS Secrets Manager in %s", self._config.region)

        except self._NoCredentialsError as e:
            raise AuthenticationError("aws", "No AWS credentials found") from e
        except self._ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code in ("AccessDeniedException", "UnauthorizedAccess"):
                raise AuthenticationError("aws", str(e)) from e
            raise ConnectionError("aws", str(e)) from e
        except self._BotoCoreError as e:
            raise ConnectionError("aws", str(e)) from e

    def _get_secret_name(self, path: str) -> str:
        """Get the full secret name with prefix."""
        if self._config.prefix:
            prefix = self._config.prefix.rstrip("/")
            if not path.startswith(prefix):
                return f"{prefix}/{path}"
        return path

    def _parse_secret_value(self, response: dict[str, Any]) -> tuple[str | None, dict[str, str]]:
        """Parse the secret value from AWS response."""
        # AWS can return SecretString (for text) or SecretBinary (for binary)
        if "SecretString" in response:
            secret_string = response["SecretString"]
            # Try to parse as JSON
            try:
                data = json.loads(secret_string)
                if isinstance(data, dict):
                    return None, {k: str(v) for k, v in data.items()}
                # Single value JSON
                return str(data), {}
            except json.JSONDecodeError:
                # Plain string
                return secret_string, {}
        elif "SecretBinary" in response:
            # Binary secret - return as base64 or decoded string
            import base64

            binary = response["SecretBinary"]
            try:
                return binary.decode("utf-8"), {}
            except UnicodeDecodeError:
                return base64.b64encode(binary).decode("ascii"), {}
        return None, {}

    @property
    def backend(self) -> SecretBackend:
        """Return the backend type."""
        return SecretBackend.AWS

    def get_secret(
        self,
        path: str,
        *,
        version: str | None = None,
    ) -> Secret:
        """
        Get a secret from AWS Secrets Manager.

        Args:
            path: Secret name.
            version: Version stage (e.g., "AWSCURRENT", "AWSPREVIOUS") or version ID.

        Returns:
            Secret with data and metadata.

        Raises:
            SecretNotFoundError: If secret doesn't exist.
            AccessDeniedError: If access is denied.
        """
        secret_name = self._get_secret_name(path)
        kwargs: dict[str, Any] = {"SecretId": secret_name}

        if version:
            # Check if it looks like a version ID (UUID format) or stage
            if "-" in version and len(version) > 20:
                kwargs["VersionId"] = version
            else:
                kwargs["VersionStage"] = version

        try:
            response = self._client.get_secret_value(**kwargs)
        except self._ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "ResourceNotFoundException":
                raise SecretNotFoundError(path, "aws") from e
            if error_code in ("AccessDeniedException", "UnauthorizedAccess"):
                raise AccessDeniedError(path, "aws") from e
            raise SecretManagerError(f"AWS error: {e}") from e

        value, data = self._parse_secret_value(response)
        version_id = response.get("VersionId", "")
        created_date = response.get("CreatedDate")

        return Secret(
            path=path,
            value=value,
            data=data,
            version=version_id,
            metadata=SecretMetadata(
                path=path,
                version=version_id,
                created_at=created_date,
                rotation_enabled=False,  # Will be updated from describe
            ),
        )

    def get_value(
        self,
        path: str,
        *,
        key: str | None = None,
        version: str | None = None,
        default: str | None = None,
    ) -> str | None:
        """
        Get a specific value from an AWS secret.

        Args:
            path: Secret name.
            key: Key within JSON secret.
            version: Version stage or ID.
            default: Default if not found.

        Returns:
            The value or default.
        """
        try:
            secret = self.get_secret(path, version=version)
            if key:
                return secret.data.get(key, default)
            if secret.value:
                return secret.value
            if secret.data:
                return next(iter(secret.data.values()), default)
            return default
        except SecretNotFoundError:
            return default

    def resolve(self, reference: SecretReference) -> str:
        """
        Resolve a secret reference.

        Args:
            reference: The secret reference.

        Returns:
            The secret value.

        Raises:
            SecretNotFoundError: If not found.
        """
        value = self.get_value(
            reference.path,
            key=reference.key,
            version=reference.version,
        )
        if value is None:
            raise SecretNotFoundError(reference.path, "aws")
        return value

    def exists(self, path: str) -> bool:
        """Check if a secret exists."""
        secret_name = self._get_secret_name(path)
        try:
            self._client.describe_secret(SecretId=secret_name)
            return True
        except self._ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "ResourceNotFoundException":
                return False
            return False

    def list_secrets(self, prefix: str = "") -> list[str]:
        """
        List secrets matching a prefix.

        Args:
            prefix: Prefix to filter by.

        Returns:
            List of secret names.
        """
        full_prefix = self._get_secret_name(prefix) if prefix else self._config.prefix
        secrets = []
        paginator = self._client.get_paginator("list_secrets")

        try:
            for page in paginator.paginate():
                for secret in page.get("SecretList", []):
                    name = secret.get("Name", "")
                    if full_prefix:
                        if name.startswith(full_prefix):
                            # Remove prefix from result
                            if self._config.prefix:
                                name = name[len(self._config.prefix) :].lstrip("/")
                            secrets.append(name)
                    else:
                        secrets.append(name)
        except self._ClientError:
            pass

        return secrets

    def get_metadata(self, path: str) -> SecretMetadata:
        """
        Get metadata for a secret.

        Args:
            path: Secret name.

        Returns:
            Secret metadata.

        Raises:
            SecretNotFoundError: If not found.
        """
        secret_name = self._get_secret_name(path)
        try:
            response = self._client.describe_secret(SecretId=secret_name)
        except self._ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "ResourceNotFoundException":
                raise SecretNotFoundError(path, "aws") from e
            raise SecretManagerError(f"AWS error: {e}") from e

        # Count versions
        versions = response.get("VersionIdsToStages", {})
        version_count = len(versions)

        # Get current version
        current_version = None
        for version_id, stages in versions.items():
            if "AWSCURRENT" in stages:
                current_version = version_id
                break

        return SecretMetadata(
            path=path,
            created_at=response.get("CreatedDate"),
            updated_at=response.get("LastChangedDate"),
            version=current_version,
            version_count=version_count,
            tags={t["Key"]: t["Value"] for t in response.get("Tags", [])},
            rotation_enabled=response.get("RotationEnabled", False),
            description=response.get("Description"),
        )

    def info(self) -> SecretManagerInfo:
        """Get information about the AWS connection."""
        return SecretManagerInfo(
            backend=SecretBackend.AWS,
            connected=self._client is not None,
            authenticated=True,
            version="2017-10-17",  # AWS Secrets Manager API version
            features=["versioning", "rotation", "tags", "binary-secrets"],
            health_status="healthy" if self.health_check() else "unhealthy",
        )

    def health_check(self) -> bool:
        """Check if AWS Secrets Manager is accessible."""
        try:
            self._client.list_secrets(MaxResults=1)
            return True
        except (self._ClientError, self._BotoCoreError):
            return False

    def close(self) -> None:
        """Close the client (no-op for boto3)."""
        # boto3 clients don't need explicit closing
