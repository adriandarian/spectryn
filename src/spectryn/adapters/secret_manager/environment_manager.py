"""
Environment Variable Secret Manager.

Default fallback implementation that reads secrets from environment variables.
This is always available and requires no external dependencies.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from spectryn.core.ports.secret_manager import (
    Secret,
    SecretBackend,
    SecretManagerInfo,
    SecretManagerPort,
    SecretMetadata,
    SecretNotFoundError,
    SecretReference,
)


@dataclass
class EnvironmentConfig:
    """Configuration for environment variable secret manager."""

    # Prefix for environment variables (e.g., "SPECTRA_" -> "SPECTRA_JIRA_TOKEN")
    prefix: str = ""
    # Whether to look for .env file
    load_dotenv: bool = True
    # Path to .env file (None = auto-detect)
    dotenv_path: str | None = None


class EnvironmentSecretManager(SecretManagerPort):
    """
    Secret manager that reads from environment variables.

    This is the default fallback that's always available.

    Environment variable naming:
    - Simple: JIRA_API_TOKEN
    - With prefix: SPECTRA_JIRA_API_TOKEN
    - Structured: Not supported (use separate vars)

    Example:
        manager = EnvironmentSecretManager()

        # Get from environment
        token = manager.get_value("JIRA_API_TOKEN")

        # With prefix config
        manager = EnvironmentSecretManager(EnvironmentConfig(prefix="SPECTRA_"))
        token = manager.get_value("JIRA_API_TOKEN")  # Looks for SPECTRA_JIRA_API_TOKEN
    """

    def __init__(self, config: EnvironmentConfig | None = None) -> None:
        """
        Initialize the environment secret manager.

        Args:
            config: Optional configuration.
        """
        self._config = config or EnvironmentConfig()
        self._loaded_dotenv = False

        if self._config.load_dotenv:
            self._load_dotenv()

    def _load_dotenv(self) -> None:
        """Load .env file if available."""
        if self._loaded_dotenv:
            return

        try:
            from dotenv import load_dotenv

            if self._config.dotenv_path:
                load_dotenv(self._config.dotenv_path)
            else:
                load_dotenv()
            self._loaded_dotenv = True
        except ImportError:
            # python-dotenv not installed, skip
            pass

    def _get_env_name(self, path: str) -> str:
        """Convert a path to an environment variable name."""
        # Replace / and - with _
        name = path.replace("/", "_").replace("-", "_").upper()
        if self._config.prefix:
            prefix = self._config.prefix.rstrip("_").upper()
            if not name.startswith(prefix):
                name = f"{prefix}_{name}"
        return name

    @property
    def backend(self) -> SecretBackend:
        """Return the backend type."""
        return SecretBackend.ENVIRONMENT

    def get_secret(
        self,
        path: str,
        *,
        version: str | None = None,
    ) -> Secret:
        """
        Get a secret from environment variables.

        Args:
            path: Environment variable name or path.
            version: Ignored (env vars don't have versions).

        Returns:
            Secret with the value.

        Raises:
            SecretNotFoundError: If variable is not set.
        """
        env_name = self._get_env_name(path)
        value = os.environ.get(env_name)

        if value is None:
            # Also try the original path as-is
            value = os.environ.get(path)

        if value is None:
            raise SecretNotFoundError(path, "environment")

        return Secret(
            path=path,
            value=value,
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
        Get a secret value from environment variables.

        Args:
            path: Environment variable name or path.
            key: Ignored (env vars are single values).
            version: Ignored (env vars don't have versions).
            default: Default if not found.

        Returns:
            The value or default.
        """
        env_name = self._get_env_name(path)
        value = os.environ.get(env_name)

        if value is None:
            # Also try the original path as-is
            value = os.environ.get(path)

        if value is None:
            return default

        return value

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
        value = self.get_value(reference.path, default=None)
        if value is None:
            raise SecretNotFoundError(reference.path, "environment")
        return value

    def exists(self, path: str) -> bool:
        """Check if an environment variable exists."""
        env_name = self._get_env_name(path)
        return env_name in os.environ or path in os.environ

    def list_secrets(self, prefix: str = "") -> list[str]:
        """
        List environment variables matching a prefix.

        Args:
            prefix: Prefix to filter by.

        Returns:
            List of matching variable names.
        """
        full_prefix = self._get_env_name(prefix) if prefix else self._config.prefix
        return [
            name for name in os.environ if (full_prefix is None or name.startswith(full_prefix))
        ]

    def get_metadata(self, path: str) -> SecretMetadata:
        """
        Get metadata for an environment variable.

        Environment variables have minimal metadata.

        Args:
            path: Variable name.

        Returns:
            Basic metadata.

        Raises:
            SecretNotFoundError: If not found.
        """
        if not self.exists(path):
            raise SecretNotFoundError(path, "environment")

        return SecretMetadata(
            path=path,
            version="1",
            version_count=1,
        )

    def info(self) -> SecretManagerInfo:
        """Get information about this manager."""
        return SecretManagerInfo(
            backend=SecretBackend.ENVIRONMENT,
            connected=True,
            authenticated=True,
            version="1.0",
            features=["simple-values"],
            health_status="healthy",
        )

    def health_check(self) -> bool:
        """Environment manager is always healthy."""
        return True

    def close(self) -> None:
        """No resources to release."""
