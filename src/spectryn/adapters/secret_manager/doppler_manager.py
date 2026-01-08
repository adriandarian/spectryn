"""
Doppler Secret Manager.

SecretOps platform for teams with support for:
- Projects and environments
- Secret versioning
- Change logs
- Service tokens
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
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
class DopplerConfig:
    """
    Configuration for Doppler.

    Attributes:
        token: Doppler service token or personal token.
        project: Default project name.
        config: Default config/environment (e.g., "dev", "stg", "prd").
        api_url: Doppler API URL (for self-hosted).
        timeout: Request timeout in seconds.
    """

    token: str
    project: str | None = None
    config: str | None = None
    api_url: str = "https://api.doppler.com/v3"
    timeout: int = 30

    def is_valid(self) -> bool:
        """Check if configuration is valid."""
        return bool(self.token)


class DopplerSecretManager(SecretManagerPort):
    """
    Doppler secret manager.

    Supports:
    - Project and environment-based secrets
    - Service token authentication
    - Secret versioning and change logs
    - Multiple environments (dev, staging, production)

    Example:
        config = DopplerConfig(
            token="dp.st.xxx",
            project="myapp",
            config="production",
        )
        manager = DopplerSecretManager(config)

        # Get a secret
        api_token = manager.get_value("JIRA_API_TOKEN")

        # Get all secrets for a config
        secret = manager.get_secret("myapp/production")

        # List projects
        projects = manager.list_secrets()
    """

    def __init__(self, config: DopplerConfig) -> None:
        """
        Initialize the Doppler secret manager.

        Args:
            config: Doppler configuration.

        Raises:
            AuthenticationError: If authentication fails.
            ConnectionError: If connection fails.
        """
        self._config = config
        self._session = requests.Session()
        self._session.auth = (config.token, "")
        self._session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

        # Verify authentication
        self._verify_auth()

    def _verify_auth(self) -> None:
        """Verify authentication is working."""
        url = f"{self._config.api_url}/me"
        try:
            response = self._session.get(url, timeout=self._config.timeout)
            if response.status_code == 401:
                raise AuthenticationError("doppler", "Invalid token")
            response.raise_for_status()
            logger.debug("Authenticated with Doppler")
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError("doppler", str(e)) from e
        except requests.exceptions.RequestException as e:
            if hasattr(e, "response") and e.response is not None:
                if e.response.status_code == 401:
                    raise AuthenticationError("doppler", "Invalid token") from e
            raise ConnectionError("doppler", str(e)) from e

    def _get_secrets_url(
        self,
        project: str | None = None,
        config: str | None = None,
    ) -> str:
        """Build the secrets endpoint URL."""
        proj = project or self._config.project
        conf = config or self._config.config

        if not proj or not conf:
            raise SecretManagerError(
                "Project and config must be specified either in config or path"
            )

        return f"{self._config.api_url}/configs/config/secrets"

    def _parse_path(self, path: str) -> tuple[str | None, str | None, str | None]:
        """
        Parse a path into project, config, and secret name.

        Formats:
        - SECRET_NAME (uses default project/config)
        - project/config/SECRET_NAME
        - project/config (all secrets)

        Returns:
            Tuple of (project, config, secret_name).
        """
        parts = path.split("/")

        if len(parts) == 1:
            # Just a secret name
            return self._config.project, self._config.config, parts[0]
        if len(parts) == 2:
            # project/config (get all secrets)
            return parts[0], parts[1], None
        if len(parts) >= 3:
            # project/config/secret_name
            return parts[0], parts[1], "/".join(parts[2:])

        return self._config.project, self._config.config, path

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an API request."""
        try:
            response = self._session.request(
                method,
                url,
                params=params,
                json=json_data,
                timeout=self._config.timeout,
            )

            if response.status_code == 401:
                raise AuthenticationError("doppler", "Invalid or expired token")
            if response.status_code == 403:
                raise AccessDeniedError(url, "doppler")
            if response.status_code == 404:
                raise SecretNotFoundError(url, "doppler")

            response.raise_for_status()
            data: dict[str, Any] = response.json()
            return data

        except requests.exceptions.ConnectionError as e:
            raise ConnectionError("doppler", str(e)) from e
        except requests.exceptions.RequestException as e:
            if hasattr(e, "response") and e.response is not None:
                if e.response.status_code == 401:
                    raise AuthenticationError("doppler", str(e)) from e
                if e.response.status_code == 403:
                    raise AccessDeniedError(str(params), "doppler") from e
                if e.response.status_code == 404:
                    raise SecretNotFoundError(str(params), "doppler") from e
            raise SecretManagerError(f"Doppler API error: {e}") from e

    @property
    def backend(self) -> SecretBackend:
        """Return the backend type."""
        return SecretBackend.DOPPLER

    def get_secret(
        self,
        path: str,
        *,
        version: str | None = None,
    ) -> Secret:
        """
        Get secrets from Doppler.

        If path is a secret name, returns that single secret.
        If path is project/config, returns all secrets for that config.

        Args:
            path: Secret name or project/config path.
            version: Ignored (Doppler doesn't support version retrieval via API).

        Returns:
            Secret with data.

        Raises:
            SecretNotFoundError: If not found.
            AccessDeniedError: If access is denied.
        """
        project, config, secret_name = self._parse_path(path)

        if not project or not config:
            raise SecretManagerError(
                "Project and config must be specified. "
                "Use format: project/config/SECRET_NAME or set defaults in config."
            )

        url = f"{self._config.api_url}/configs/config/secrets"
        params = {"project": project, "config": config}

        data = self._request("GET", url, params=params)
        secrets = data.get("secrets", {})

        if secret_name:
            # Get specific secret
            if secret_name not in secrets:
                raise SecretNotFoundError(path, "doppler")

            secret_data = secrets[secret_name]
            return Secret(
                path=path,
                value=secret_data.get("computed", secret_data.get("raw", "")),
                data={secret_name: secret_data.get("computed", secret_data.get("raw", ""))},
                metadata=SecretMetadata(
                    path=path,
                    description=secret_data.get("note"),
                ),
            )
        # Get all secrets
        all_data = {k: v.get("computed", v.get("raw", "")) for k, v in secrets.items()}
        return Secret(
            path=path,
            data=all_data,
            metadata=SecretMetadata(path=path),
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
        Get a specific secret value from Doppler.

        Args:
            path: Secret name or path.
            key: Additional key (for structured paths).
            version: Ignored.
            default: Default if not found.

        Returns:
            The value or default.
        """
        try:
            # If key is provided, append it to path
            if key:
                path = f"{path}/{key}"

            _project, _config, secret_name = self._parse_path(path)

            if not secret_name:
                # Path was just project/config, need a secret name
                return default

            secret = self.get_secret(path, version=version)
            return secret.value or default

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
        path = reference.path
        if reference.key:
            path = f"{path}/{reference.key}"

        value = self.get_value(path, default=None)
        if value is None:
            raise SecretNotFoundError(reference.path, "doppler")
        return value

    def exists(self, path: str) -> bool:
        """Check if a secret exists."""
        try:
            project, config, secret_name = self._parse_path(path)
            if not secret_name:
                # Check if project/config exists
                url = f"{self._config.api_url}/configs/config"
                params = {"project": project, "config": config}
                self._request("GET", url, params=params)
                return True

            self.get_secret(path)
            return True
        except SecretNotFoundError:
            return False
        except SecretManagerError:
            return False

    def list_secrets(self, prefix: str = "") -> list[str]:
        """
        List secrets or projects.

        Args:
            prefix: If empty, lists projects. If project name, lists configs.
                   If project/config, lists secret names.

        Returns:
            List of names.
        """
        if not prefix:
            # List projects
            url = f"{self._config.api_url}/projects"
            try:
                data = self._request("GET", url)
                return [p["name"] for p in data.get("projects", [])]
            except SecretManagerError:
                return []

        parts = prefix.split("/")
        if len(parts) == 1:
            # List configs for project
            url = f"{self._config.api_url}/configs"
            try:
                data = self._request("GET", url, params={"project": prefix})
                return [c["name"] for c in data.get("configs", [])]
            except SecretManagerError:
                return []
        else:
            # List secrets for project/config
            project, config = parts[0], parts[1]
            try:
                secret = self.get_secret(f"{project}/{config}")
                return list(secret.data.keys())
            except SecretManagerError:
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
        project, config, secret_name = self._parse_path(path)

        if not secret_name:
            # Get config metadata
            url = f"{self._config.api_url}/configs/config"
            params = {"project": project, "config": config}
            data = self._request("GET", url, params=params)
            config_data = data.get("config", {})

            created_at = None
            if config_data.get("created_at"):
                with contextlib.suppress(ValueError):
                    created_at = datetime.fromisoformat(
                        config_data["created_at"].replace("Z", "+00:00")
                    )

            return SecretMetadata(
                path=path,
                created_at=created_at,
            )

        # Get secret metadata via the secrets endpoint
        secret = self.get_secret(path)
        return secret.metadata or SecretMetadata(path=path)

    def info(self) -> SecretManagerInfo:
        """Get information about the Doppler connection."""
        # Get current user info
        url = f"{self._config.api_url}/me"
        try:
            data = self._request("GET", url)
            workplace = data.get("workplace", {}).get("name", "")
        except SecretManagerError:
            workplace = ""

        return SecretManagerInfo(
            backend=SecretBackend.DOPPLER,
            connected=True,
            authenticated=True,
            version=workplace,
            features=["projects", "configs", "secrets", "audit-log"],
            health_status="healthy" if self.health_check() else "unhealthy",
        )

    def health_check(self) -> bool:
        """Check if Doppler is accessible."""
        url = f"{self._config.api_url}/me"
        try:
            response = self._session.get(url, timeout=self._config.timeout)
            return bool(response.status_code == 200)
        except requests.exceptions.RequestException:
            return False

    def close(self) -> None:
        """Close the session."""
        self._session.close()
