"""
Secret Manager Port - Abstract interface for secret management.

Provides a pluggable backend for retrieving secrets from external secret
management systems. This enables centralized secret management and
avoids storing secrets in configuration files.

Supported backends:
- HashiCorp Vault: Enterprise-grade secret management
- AWS Secrets Manager: AWS native secret storage
- 1Password: Developer-friendly password manager
- Doppler: SecretOps platform for teams
- Environment Variables: Default fallback

Benefits:
- Centralized secret management
- Audit logging and access control
- Secret rotation without config changes
- Team-wide secret sharing
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


# -------------------------------------------------------------------------
# Exceptions
# -------------------------------------------------------------------------


class SecretManagerError(Exception):
    """Base exception for secret manager errors."""


class SecretNotFoundError(SecretManagerError):
    """The requested secret was not found."""

    def __init__(self, secret_path: str, backend: str | None = None) -> None:
        self.secret_path = secret_path
        self.backend = backend
        msg = f"Secret not found: {secret_path}"
        if backend:
            msg += f" (backend: {backend})"
        super().__init__(msg)


class AuthenticationError(SecretManagerError):
    """Failed to authenticate with the secret manager."""

    def __init__(self, backend: str, message: str | None = None) -> None:
        self.backend = backend
        msg = f"Authentication failed for {backend}"
        if message:
            msg += f": {message}"
        super().__init__(msg)


class ConnectionError(SecretManagerError):
    """Failed to connect to the secret manager."""

    def __init__(self, backend: str, message: str | None = None) -> None:
        self.backend = backend
        msg = f"Connection failed to {backend}"
        if message:
            msg += f": {message}"
        super().__init__(msg)


class AccessDeniedError(SecretManagerError):
    """Access to the secret was denied."""

    def __init__(self, secret_path: str, backend: str | None = None) -> None:
        self.secret_path = secret_path
        self.backend = backend
        msg = f"Access denied to secret: {secret_path}"
        if backend:
            msg += f" (backend: {backend})"
        super().__init__(msg)


class SecretVersionError(SecretManagerError):
    """Invalid or missing secret version."""

    def __init__(self, secret_path: str, version: str) -> None:
        self.secret_path = secret_path
        self.version = version
        super().__init__(f"Version '{version}' not found for secret: {secret_path}")


# -------------------------------------------------------------------------
# Enums
# -------------------------------------------------------------------------


class SecretBackend(Enum):
    """Supported secret management backends."""

    ENVIRONMENT = "environment"
    VAULT = "vault"  # HashiCorp Vault
    AWS = "aws"  # AWS Secrets Manager
    ONEPASSWORD = "1password"  # 1Password
    DOPPLER = "doppler"  # Doppler
    AZURE = "azure"  # Azure Key Vault (future)
    GCP = "gcp"  # Google Secret Manager (future)


# -------------------------------------------------------------------------
# Data Classes
# -------------------------------------------------------------------------


@dataclass
class SecretMetadata:
    """
    Metadata about a secret.

    Attributes:
        path: Full path/name of the secret.
        created_at: When the secret was created.
        updated_at: When the secret was last updated.
        version: Current version identifier.
        version_count: Total number of versions.
        tags: Key-value tags/labels on the secret.
        expires_at: When the secret expires (if applicable).
        rotation_enabled: Whether automatic rotation is enabled.
        description: Human-readable description.
    """

    path: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    version: str | None = None
    version_count: int = 1
    tags: dict[str, str] = field(default_factory=dict)
    expires_at: datetime | None = None
    rotation_enabled: bool = False
    description: str | None = None


@dataclass
class Secret:
    """
    A secret value with metadata.

    Attributes:
        path: Full path/name of the secret.
        value: The secret value (string for simple secrets).
        data: Dictionary of key-value pairs (for structured secrets).
        version: Version identifier.
        metadata: Full metadata about the secret.
    """

    path: str
    value: str | None = None
    data: dict[str, str] = field(default_factory=dict)
    version: str | None = None
    metadata: SecretMetadata | None = None

    def get(self, key: str, default: str | None = None) -> str | None:
        """
        Get a value from structured secret data.

        Args:
            key: Key to look up.
            default: Default if key not found.

        Returns:
            The value or default.
        """
        return self.data.get(key, default)

    def get_value(self) -> str:
        """
        Get the primary value.

        For simple secrets, returns the value.
        For structured secrets, returns the first value or JSON.

        Returns:
            The secret value as a string.

        Raises:
            ValueError: If no value is available.
        """
        if self.value:
            return self.value
        if self.data:
            # Return first value for convenience
            return next(iter(self.data.values()))
        raise ValueError(f"Secret '{self.path}' has no value")


@dataclass
class SecretReference:
    """
    Reference to a secret in external storage.

    Used in configuration to indicate a value should be fetched
    from a secret manager.

    Format patterns:
    - vault://secret/data/spectra/jira#api_token
    - aws://spectra/jira-credentials#api_token
    - 1password://op://Private/Jira/api-token
    - doppler://JIRA_API_TOKEN
    - env://JIRA_API_TOKEN

    Attributes:
        backend: The secret backend to use.
        path: The secret path/name.
        key: Optional key within structured secret.
        version: Optional version to retrieve.
    """

    backend: SecretBackend
    path: str
    key: str | None = None
    version: str | None = None

    @classmethod
    def parse(cls, reference: str) -> SecretReference:
        """
        Parse a secret reference string.

        Args:
            reference: Reference string like "vault://path/to/secret#key"

        Returns:
            Parsed SecretReference.

        Raises:
            ValueError: If reference format is invalid.
        """
        if not reference:
            raise ValueError("Empty secret reference")

        # Check for supported prefixes
        for backend in SecretBackend:
            prefix = f"{backend.value}://"
            if reference.startswith(prefix):
                remaining = reference[len(prefix) :]
                return cls._parse_path_and_key(backend, remaining)

        # Default to environment variable
        if reference.startswith("$"):
            return cls(
                backend=SecretBackend.ENVIRONMENT,
                path=reference[1:],
            )

        raise ValueError(
            f"Invalid secret reference format: {reference}. "
            f"Expected format: <backend>://path[#key] or $ENV_VAR"
        )

    @classmethod
    def _parse_path_and_key(
        cls,
        backend: SecretBackend,
        path_str: str,
    ) -> SecretReference:
        """Parse path and optional key/version from string."""
        version = None
        key = None

        # Extract version if present (path@version)
        if "@" in path_str:
            path_str, version = path_str.rsplit("@", 1)

        # Extract key if present (path#key)
        if "#" in path_str:
            path, key = path_str.rsplit("#", 1)
        else:
            path = path_str

        return cls(
            backend=backend,
            path=path,
            key=key,
            version=version,
        )

    def to_string(self) -> str:
        """Convert to reference string."""
        result = f"{self.backend.value}://{self.path}"
        if self.key:
            result += f"#{self.key}"
        if self.version:
            result += f"@{self.version}"
        return result


@dataclass
class SecretManagerInfo:
    """
    Information about a secret manager backend.

    Attributes:
        backend: Backend type.
        connected: Whether connection is established.
        authenticated: Whether authentication succeeded.
        version: Backend version if available.
        features: Supported features (e.g., versioning, rotation).
        health_status: Health check status.
    """

    backend: SecretBackend
    connected: bool = False
    authenticated: bool = False
    version: str | None = None
    features: list[str] = field(default_factory=list)
    health_status: str = "unknown"


# -------------------------------------------------------------------------
# Port Interface
# -------------------------------------------------------------------------


class SecretManagerPort(ABC):
    """
    Abstract interface for secret management.

    Implementations can use different backends:
    - Environment variables (default fallback)
    - HashiCorp Vault
    - AWS Secrets Manager
    - 1Password
    - Doppler

    Example usage:
        # Get a simple secret
        api_token = manager.get_secret("jira/api-token")

        # Get a specific key from a structured secret
        password = manager.get_value("database/credentials", key="password")

        # Resolve a reference from config
        ref = SecretReference.parse("vault://secret/data/jira#api_token")
        value = manager.resolve(ref)

        # List available secrets
        for path in manager.list_secrets("jira/"):
            print(path)
    """

    @property
    @abstractmethod
    def backend(self) -> SecretBackend:
        """
        The backend type for this manager.

        Returns:
            The SecretBackend enum value.
        """

    @abstractmethod
    def get_secret(
        self,
        path: str,
        *,
        version: str | None = None,
    ) -> Secret:
        """
        Get a secret by path.

        Args:
            path: The secret path/name.
            version: Optional specific version.

        Returns:
            The Secret with value and metadata.

        Raises:
            SecretNotFoundError: If secret doesn't exist.
            AuthenticationError: If authentication fails.
            AccessDeniedError: If access is denied.
            SecretManagerError: For other errors.
        """

    @abstractmethod
    def get_value(
        self,
        path: str,
        *,
        key: str | None = None,
        version: str | None = None,
        default: str | None = None,
    ) -> str | None:
        """
        Get a secret value directly.

        Convenience method for getting just the value.

        Args:
            path: The secret path/name.
            key: Optional key for structured secrets.
            version: Optional specific version.
            default: Default value if not found (instead of raising).

        Returns:
            The secret value, or default if not found and default provided.

        Raises:
            SecretNotFoundError: If secret doesn't exist and no default.
            AuthenticationError: If authentication fails.
            AccessDeniedError: If access is denied.
        """

    @abstractmethod
    def resolve(self, reference: SecretReference) -> str:
        """
        Resolve a secret reference to its value.

        Args:
            reference: The secret reference to resolve.

        Returns:
            The secret value.

        Raises:
            SecretNotFoundError: If secret doesn't exist.
            AuthenticationError: If authentication fails.
            AccessDeniedError: If access is denied.
        """

    @abstractmethod
    def exists(self, path: str) -> bool:
        """
        Check if a secret exists.

        Args:
            path: The secret path/name.

        Returns:
            True if secret exists, False otherwise.
        """

    @abstractmethod
    def list_secrets(self, prefix: str = "") -> list[str]:
        """
        List secret paths matching a prefix.

        Args:
            prefix: Optional prefix to filter by.

        Returns:
            List of secret paths.

        Raises:
            AuthenticationError: If authentication fails.
            AccessDeniedError: If access is denied.
        """

    @abstractmethod
    def get_metadata(self, path: str) -> SecretMetadata:
        """
        Get metadata about a secret without retrieving its value.

        Args:
            path: The secret path/name.

        Returns:
            Secret metadata.

        Raises:
            SecretNotFoundError: If secret doesn't exist.
            AuthenticationError: If authentication fails.
        """

    @abstractmethod
    def info(self) -> SecretManagerInfo:
        """
        Get information about the secret manager.

        Returns:
            SecretManagerInfo with backend details.
        """

    @abstractmethod
    def health_check(self) -> bool:
        """
        Check if the secret manager is healthy and accessible.

        Returns:
            True if healthy, False otherwise.
        """

    @abstractmethod
    def close(self) -> None:
        """
        Close the secret manager and release resources.

        Should be called when done with the manager.
        """

    # Convenience methods with default implementations

    def resolve_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """
        Resolve all secret references in a configuration dict.

        Recursively scans the config for SecretReference patterns
        and replaces them with actual values.

        Args:
            config: Configuration dictionary.

        Returns:
            New dictionary with secrets resolved.
        """
        return self._resolve_dict(config)

    def _resolve_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Recursively resolve secrets in a dictionary."""
        result: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, dict):
                result[key] = self._resolve_dict(value)
            elif isinstance(value, list):
                result[key] = self._resolve_list(value)
            elif isinstance(value, str):
                result[key] = self._resolve_string(value)
            else:
                result[key] = value
        return result

    def _resolve_list(self, data: list[Any]) -> list[Any]:
        """Recursively resolve secrets in a list."""
        result: list[Any] = []
        for item in data:
            if isinstance(item, dict):
                result.append(self._resolve_dict(item))
            elif isinstance(item, list):
                result.append(self._resolve_list(item))
            elif isinstance(item, str):
                result.append(self._resolve_string(item))
            else:
                result.append(item)
        return result

    def _resolve_string(self, value: str) -> str:
        """Resolve a string if it's a secret reference."""
        # Check if it looks like a secret reference
        for backend in SecretBackend:
            if value.startswith(f"{backend.value}://"):
                try:
                    ref = SecretReference.parse(value)
                    return self.resolve(ref)
                except (SecretNotFoundError, ValueError):
                    # Return original if resolution fails
                    return value
        # Check for $ENV_VAR pattern
        if value.startswith("$") and not value.startswith("${"):
            try:
                ref = SecretReference.parse(value)
                return self.resolve(ref)
            except (SecretNotFoundError, ValueError):
                return value
        return value

    def __enter__(self) -> SecretManagerPort:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()


# -------------------------------------------------------------------------
# Composite Manager (supports multiple backends)
# -------------------------------------------------------------------------


class CompositeSecretManager(SecretManagerPort):
    """
    A secret manager that delegates to multiple backends.

    Routes requests based on the secret reference backend.
    Falls back through backends if a secret is not found.

    Example:
        manager = CompositeSecretManager()
        manager.register(SecretBackend.VAULT, vault_manager)
        manager.register(SecretBackend.AWS, aws_manager)
        manager.register(SecretBackend.ENVIRONMENT, env_manager)

        # Routes to appropriate backend based on reference
        vault_secret = manager.resolve(SecretReference.parse("vault://..."))
        aws_secret = manager.resolve(SecretReference.parse("aws://..."))
    """

    def __init__(
        self,
        default_backend: SecretBackend = SecretBackend.ENVIRONMENT,
    ) -> None:
        """
        Initialize the composite manager.

        Args:
            default_backend: Default backend for non-referenced lookups.
        """
        self._managers: dict[SecretBackend, SecretManagerPort] = {}
        self._default_backend = default_backend
        self._fallback_order: list[SecretBackend] = []

    def register(
        self,
        backend: SecretBackend,
        manager: SecretManagerPort,
        *,
        fallback: bool = False,
    ) -> None:
        """
        Register a backend manager.

        Args:
            backend: The backend type.
            manager: The manager implementation.
            fallback: If True, add to fallback chain.
        """
        self._managers[backend] = manager
        if fallback and backend not in self._fallback_order:
            self._fallback_order.append(backend)

    def unregister(self, backend: SecretBackend) -> None:
        """Remove a backend manager."""
        self._managers.pop(backend, None)
        if backend in self._fallback_order:
            self._fallback_order.remove(backend)

    def set_default_backend(self, backend: SecretBackend) -> None:
        """Set the default backend for non-referenced lookups."""
        if backend not in self._managers:
            raise ValueError(f"Backend {backend.value} is not registered")
        self._default_backend = backend

    def set_fallback_order(self, order: list[SecretBackend]) -> None:
        """Set the fallback order for lookups."""
        self._fallback_order = [b for b in order if b in self._managers]

    def _get_manager(self, backend: SecretBackend) -> SecretManagerPort:
        """Get the manager for a backend."""
        if backend not in self._managers:
            raise SecretManagerError(f"No manager registered for backend: {backend.value}")
        return self._managers[backend]

    def _get_default_manager(self) -> SecretManagerPort:
        """Get the default backend manager."""
        return self._get_manager(self._default_backend)

    @property
    def backend(self) -> SecretBackend:
        """Returns the default backend."""
        return self._default_backend

    def get_secret(
        self,
        path: str,
        *,
        version: str | None = None,
    ) -> Secret:
        """Get secret from default backend with fallback."""
        managers_to_try = [self._default_backend] + [
            b for b in self._fallback_order if b != self._default_backend
        ]

        last_error: SecretManagerError | None = None
        for backend in managers_to_try:
            if backend not in self._managers:
                continue
            try:
                return self._managers[backend].get_secret(path, version=version)
            except SecretNotFoundError as e:
                last_error = e
                continue

        if last_error:
            raise last_error
        raise SecretNotFoundError(path, self._default_backend.value)

    def get_value(
        self,
        path: str,
        *,
        key: str | None = None,
        version: str | None = None,
        default: str | None = None,
    ) -> str | None:
        """Get value from default backend with fallback."""
        managers_to_try = [self._default_backend] + [
            b for b in self._fallback_order if b != self._default_backend
        ]

        for backend in managers_to_try:
            if backend not in self._managers:
                continue
            try:
                value = self._managers[backend].get_value(
                    path, key=key, version=version, default=None
                )
                if value is not None:
                    return value
            except SecretNotFoundError:
                continue

        return default

    def resolve(self, reference: SecretReference) -> str:
        """Resolve from the backend specified in the reference."""
        manager = self._get_manager(reference.backend)
        return (
            manager.get_value(
                reference.path,
                key=reference.key,
                version=reference.version,
            )
            or ""
        )

    def exists(self, path: str) -> bool:
        """Check if secret exists in any backend."""
        return any(manager.exists(path) for manager in self._managers.values())

    def list_secrets(self, prefix: str = "") -> list[str]:
        """List secrets from default backend."""
        return self._get_default_manager().list_secrets(prefix)

    def get_metadata(self, path: str) -> SecretMetadata:
        """Get metadata from default backend with fallback."""
        managers_to_try = [self._default_backend] + [
            b for b in self._fallback_order if b != self._default_backend
        ]

        last_error: SecretManagerError | None = None
        for backend in managers_to_try:
            if backend not in self._managers:
                continue
            try:
                return self._managers[backend].get_metadata(path)
            except SecretNotFoundError as e:
                last_error = e
                continue

        if last_error:
            raise last_error
        raise SecretNotFoundError(path, self._default_backend.value)

    def info(self) -> SecretManagerInfo:
        """Aggregate info from all backends."""
        features: list[str] = []
        for manager in self._managers.values():
            features.extend(manager.info().features)

        return SecretManagerInfo(
            backend=self._default_backend,
            connected=all(m.health_check() for m in self._managers.values()),
            authenticated=True,  # Assumed if we got here
            features=list(set(features)),
            health_status="healthy" if self._managers else "no backends",
        )

    def health_check(self) -> bool:
        """Check if all backends are healthy."""
        if not self._managers:
            return False
        return all(m.health_check() for m in self._managers.values())

    def close(self) -> None:
        """Close all backend managers."""
        for manager in self._managers.values():
            manager.close()
        self._managers.clear()
