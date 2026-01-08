"""
HashiCorp Vault Secret Manager.

Enterprise-grade secret management with support for:
- KV (Key-Value) secrets engine v1 and v2
- Token authentication
- AppRole authentication
- Kubernetes authentication
- Namespaces (Enterprise)
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import requests

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
class VaultConfig:
    """
    Configuration for HashiCorp Vault.

    Attributes:
        address: Vault server address (e.g., "https://vault.example.com:8200").
        token: Authentication token (if using token auth).
        namespace: Vault namespace (Enterprise feature).
        mount_point: KV secrets engine mount point.
        kv_version: KV engine version (1 or 2).
        role_id: AppRole role ID (if using AppRole auth).
        secret_id: AppRole secret ID (if using AppRole auth).
        kubernetes_role: Kubernetes auth role (if using K8s auth).
        kubernetes_jwt_path: Path to K8s service account JWT.
        timeout: Request timeout in seconds.
        verify_ssl: Whether to verify SSL certificates.
        ca_cert: Path to CA certificate bundle.
    """

    address: str
    token: str | None = None
    namespace: str | None = None
    mount_point: str = "secret"
    kv_version: int = 2
    role_id: str | None = None
    secret_id: str | None = None
    kubernetes_role: str | None = None
    kubernetes_jwt_path: str = "/var/run/secrets/kubernetes.io/serviceaccount/token"
    timeout: int = 30
    verify_ssl: bool = True
    ca_cert: str | None = None
    extra_headers: dict[str, str] = field(default_factory=dict)

    def is_valid(self) -> bool:
        """Check if configuration is valid."""
        if not self.address:
            return False
        # Need at least one auth method
        return bool(self.token or (self.role_id and self.secret_id) or self.kubernetes_role)


class VaultSecretManager(SecretManagerPort):
    """
    HashiCorp Vault secret manager.

    Supports:
    - KV secrets engine v1 and v2
    - Token, AppRole, and Kubernetes authentication
    - Namespaces (Enterprise)
    - Secret versioning (KV v2)

    Example:
        config = VaultConfig(
            address="https://vault.example.com:8200",
            token="hvs.xxxxx",
            mount_point="secret",
        )
        manager = VaultSecretManager(config)

        # Get a secret
        secret = manager.get_secret("myapp/database")

        # Get a specific version
        secret = manager.get_secret("myapp/database", version="3")

        # Get a specific key from a secret
        password = manager.get_value("myapp/database", key="password")
    """

    def __init__(self, config: VaultConfig) -> None:
        """
        Initialize the Vault secret manager.

        Args:
            config: Vault configuration.

        Raises:
            AuthenticationError: If authentication fails.
            ConnectionError: If connection fails.
        """
        self._config = config
        self._session = requests.Session()
        self._token: str | None = None

        # Setup SSL verification
        if config.ca_cert:
            self._session.verify = config.ca_cert
        else:
            self._session.verify = config.verify_ssl

        # Setup headers
        self._session.headers.update(
            {
                "X-Vault-Request": "true",
                **config.extra_headers,
            }
        )

        if config.namespace:
            self._session.headers["X-Vault-Namespace"] = config.namespace

        # Authenticate
        self._authenticate()

    def _authenticate(self) -> None:
        """Authenticate with Vault."""
        if self._config.token:
            self._token = self._config.token
            self._session.headers["X-Vault-Token"] = self._token
        elif self._config.role_id and self._config.secret_id:
            self._auth_approle()
        elif self._config.kubernetes_role:
            self._auth_kubernetes()
        else:
            raise AuthenticationError(
                "vault",
                "No authentication method configured",
            )

        # Verify token is valid
        self._verify_token()

    def _auth_approle(self) -> None:
        """Authenticate using AppRole."""
        url = f"{self._config.address}/v1/auth/approle/login"
        try:
            response = self._session.post(
                url,
                json={
                    "role_id": self._config.role_id,
                    "secret_id": self._config.secret_id,
                },
                timeout=self._config.timeout,
            )
            response.raise_for_status()
            data = response.json()
            self._token = data["auth"]["client_token"]
            self._session.headers["X-Vault-Token"] = self._token
            logger.debug("Authenticated with Vault using AppRole")
        except requests.exceptions.RequestException as e:
            raise AuthenticationError("vault", str(e)) from e

    def _auth_kubernetes(self) -> None:
        """Authenticate using Kubernetes service account."""
        try:
            with open(self._config.kubernetes_jwt_path) as f:
                jwt = f.read().strip()
        except OSError as e:
            raise AuthenticationError(
                "vault",
                f"Failed to read Kubernetes JWT: {e}",
            ) from e

        url = f"{self._config.address}/v1/auth/kubernetes/login"
        try:
            response = self._session.post(
                url,
                json={
                    "role": self._config.kubernetes_role,
                    "jwt": jwt,
                },
                timeout=self._config.timeout,
            )
            response.raise_for_status()
            data = response.json()
            self._token = data["auth"]["client_token"]
            self._session.headers["X-Vault-Token"] = self._token
            logger.debug("Authenticated with Vault using Kubernetes")
        except requests.exceptions.RequestException as e:
            raise AuthenticationError("vault", str(e)) from e

    def _verify_token(self) -> None:
        """Verify the current token is valid."""
        url = f"{self._config.address}/v1/auth/token/lookup-self"
        try:
            response = self._session.get(url, timeout=self._config.timeout)
            if response.status_code == 403:
                raise AuthenticationError("vault", "Token is invalid or expired")
            response.raise_for_status()
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError("vault", str(e)) from e
        except requests.exceptions.RequestException as e:
            if hasattr(e, "response") and e.response is not None:
                if e.response.status_code == 403:
                    raise AuthenticationError("vault", "Token is invalid or expired") from e
            raise SecretManagerError(f"Failed to verify Vault token: {e}") from e

    def _build_secret_path(self, path: str) -> str:
        """Build the full API path for a secret."""
        # For KV v2, data is stored at mount/data/path
        if self._config.kv_version == 2:
            return f"{self._config.address}/v1/{self._config.mount_point}/data/{path}"
        # For KV v1, data is stored at mount/path
        return f"{self._config.address}/v1/{self._config.mount_point}/{path}"

    def _build_metadata_path(self, path: str) -> str:
        """Build the full API path for secret metadata."""
        if self._config.kv_version == 2:
            return f"{self._config.address}/v1/{self._config.mount_point}/metadata/{path}"
        # KV v1 doesn't have separate metadata
        return self._build_secret_path(path)

    def _parse_response(
        self,
        response: requests.Response,
        path: str,
    ) -> dict[str, Any]:
        """Parse a Vault API response."""
        if response.status_code == 404:
            raise SecretNotFoundError(path, "vault")
        if response.status_code == 403:
            raise AccessDeniedError(path, "vault")

        try:
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            return data
        except requests.exceptions.RequestException as e:
            raise SecretManagerError(f"Vault API error: {e}") from e

    @property
    def backend(self) -> SecretBackend:
        """Return the backend type."""
        return SecretBackend.VAULT

    def get_secret(
        self,
        path: str,
        *,
        version: str | None = None,
    ) -> Secret:
        """
        Get a secret from Vault.

        Args:
            path: Secret path (relative to mount point).
            version: Specific version (KV v2 only).

        Returns:
            Secret with data and metadata.

        Raises:
            SecretNotFoundError: If secret doesn't exist.
            SecretVersionError: If version doesn't exist.
            AccessDeniedError: If access is denied.
        """
        url = self._build_secret_path(path)
        params = {}
        if version and self._config.kv_version == 2:
            params["version"] = version

        try:
            response = self._session.get(
                url,
                params=params,
                timeout=self._config.timeout,
            )
            data = self._parse_response(response, path)
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError("vault", str(e)) from e

        # Extract secret data based on KV version
        if self._config.kv_version == 2:
            secret_data = data.get("data", {}).get("data", {})
            metadata = data.get("data", {}).get("metadata", {})
            secret_version = str(metadata.get("version", "1"))
            created_time = metadata.get("created_time")
        else:
            secret_data = data.get("data", {})
            secret_version = "1"
            created_time = None

        # Parse timestamps
        created_at = None
        if created_time:
            with contextlib.suppress(ValueError):
                created_at = datetime.fromisoformat(created_time.replace("Z", "+00:00"))

        return Secret(
            path=path,
            value=secret_data.get("value") if len(secret_data) == 1 else None,
            data={k: str(v) for k, v in secret_data.items()},
            version=secret_version,
            metadata=SecretMetadata(
                path=path,
                version=secret_version,
                created_at=created_at,
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
        Get a specific value from a Vault secret.

        Args:
            path: Secret path.
            key: Key within the secret (default: first value).
            version: Specific version (KV v2 only).
            default: Default if not found.

        Returns:
            The value or default.
        """
        try:
            secret = self.get_secret(path, version=version)
            if key:
                return secret.data.get(key, default)
            # Return first value or the single value
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
            raise SecretNotFoundError(reference.path, "vault")
        return value

    def exists(self, path: str) -> bool:
        """Check if a secret exists."""
        try:
            self.get_secret(path)
            return True
        except SecretNotFoundError:
            return False
        except SecretManagerError:
            return False

    def list_secrets(self, prefix: str = "") -> list[str]:
        """
        List secrets under a path prefix.

        Args:
            prefix: Path prefix to list.

        Returns:
            List of secret paths.
        """
        # Use metadata endpoint for KV v2, or list endpoint
        if self._config.kv_version == 2:
            url = f"{self._config.address}/v1/{self._config.mount_point}/metadata/{prefix}"
        else:
            url = f"{self._config.address}/v1/{self._config.mount_point}/{prefix}"

        try:
            response = self._session.request(
                "LIST",
                url,
                timeout=self._config.timeout,
            )
            if response.status_code == 404:
                return []
            response.raise_for_status()
            data = response.json()
            keys = data.get("data", {}).get("keys", [])

            # Recursively list if keys end with /
            result = []
            for key in keys:
                full_path = f"{prefix}/{key}".lstrip("/")
                if key.endswith("/"):
                    # It's a directory, recurse
                    result.extend(self.list_secrets(full_path.rstrip("/")))
                else:
                    result.append(full_path)
            return result
        except requests.exceptions.RequestException:
            return []

    def get_metadata(self, path: str) -> SecretMetadata:
        """
        Get metadata for a secret.

        Args:
            path: Secret path.

        Returns:
            Secret metadata.

        Raises:
            SecretNotFoundError: If not found.
        """
        if self._config.kv_version == 1:
            # KV v1 doesn't have separate metadata
            secret = self.get_secret(path)
            return secret.metadata or SecretMetadata(path=path)

        url = self._build_metadata_path(path)
        try:
            response = self._session.get(url, timeout=self._config.timeout)
            data = self._parse_response(response, path)
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError("vault", str(e)) from e

        metadata = data.get("data", {})
        versions = metadata.get("versions", {})
        current_version = str(metadata.get("current_version", 1))
        version_info = versions.get(current_version, {})

        created_time = version_info.get("created_time")
        created_at = None
        if created_time:
            with contextlib.suppress(ValueError):
                created_at = datetime.fromisoformat(created_time.replace("Z", "+00:00"))

        return SecretMetadata(
            path=path,
            version=current_version,
            version_count=len(versions),
            created_at=created_at,
            tags=metadata.get("custom_metadata", {}),
        )

    def info(self) -> SecretManagerInfo:
        """Get information about the Vault connection."""
        features = [
            "versioning" if self._config.kv_version == 2 else "simple-kv",
            "namespaces" if self._config.namespace else "no-namespaces",
        ]

        return SecretManagerInfo(
            backend=SecretBackend.VAULT,
            connected=True,
            authenticated=bool(self._token),
            version=f"KV v{self._config.kv_version}",
            features=features,
            health_status="healthy" if self.health_check() else "unhealthy",
        )

    def health_check(self) -> bool:
        """Check if Vault is healthy and accessible."""
        url = f"{self._config.address}/v1/sys/health"
        try:
            response = self._session.get(url, timeout=self._config.timeout)
            # Vault returns various status codes for health
            # 200: initialized, unsealed, active
            # 429: unsealed, standby
            # 472: data recovery mode
            # 501: not initialized
            # 503: sealed
            return response.status_code in (200, 429)
        except requests.exceptions.RequestException:
            return False

    def close(self) -> None:
        """Close the session."""
        self._session.close()
