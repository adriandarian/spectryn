"""
Secret Manager Factory.

Creates appropriate secret manager based on configuration.
Provides convenience functions for resolving secrets in configs.
"""

from __future__ import annotations

import os
from typing import Any

from spectryn.core.ports.secret_manager import (
    CompositeSecretManager,
    SecretBackend,
    SecretManagerPort,
    SecretNotFoundError,
    SecretReference,
)

from .aws_manager import AwsSecretManager, AwsSecretsConfig
from .doppler_manager import DopplerConfig, DopplerSecretManager
from .environment_manager import EnvironmentConfig, EnvironmentSecretManager
from .onepassword_manager import OnePasswordConfig, OnePasswordSecretManager
from .vault_manager import VaultConfig, VaultSecretManager


def create_secret_manager(
    backend: SecretBackend | str | None = None,
    *,
    config: dict[str, Any] | None = None,
    fallback_to_env: bool = True,
) -> SecretManagerPort:
    """
    Create a secret manager for the specified backend.

    If no backend is specified, auto-detects based on environment variables:
    - VAULT_ADDR -> HashiCorp Vault
    - AWS_REGION + (secrets config) -> AWS Secrets Manager
    - OP_SERVICE_ACCOUNT_TOKEN -> 1Password
    - DOPPLER_TOKEN -> Doppler
    - Default: Environment variables

    Args:
        backend: Backend type (string or enum).
        config: Backend-specific configuration dictionary.
        fallback_to_env: If True, creates a composite manager with env fallback.

    Returns:
        Configured SecretManagerPort.

    Example:
        # Auto-detect from environment
        manager = create_secret_manager()

        # Explicit backend
        manager = create_secret_manager("vault", config={
            "address": "https://vault.example.com:8200",
            "token": "hvs.xxx",
        })

        # From environment with fallback
        manager = create_secret_manager(fallback_to_env=True)
    """
    config = config or {}

    # Convert string to enum
    if isinstance(backend, str):
        backend = SecretBackend(backend.lower())

    # Auto-detect if not specified
    if backend is None:
        backend = _detect_backend()

    # Create the primary manager
    primary = _create_manager(backend, config)

    # Optionally wrap with environment fallback
    if fallback_to_env and backend != SecretBackend.ENVIRONMENT:
        composite = CompositeSecretManager(default_backend=backend)
        composite.register(backend, primary)
        composite.register(SecretBackend.ENVIRONMENT, EnvironmentSecretManager())
        composite.set_fallback_order([backend, SecretBackend.ENVIRONMENT])
        return composite

    return primary


def _detect_backend() -> SecretBackend:
    """Detect the appropriate backend from environment."""
    # Check for Vault
    if os.environ.get("VAULT_ADDR"):
        return SecretBackend.VAULT

    # Check for Doppler (check first as it's more specific)
    if os.environ.get("DOPPLER_TOKEN"):
        return SecretBackend.DOPPLER

    # Check for 1Password
    if os.environ.get("OP_SERVICE_ACCOUNT_TOKEN"):
        return SecretBackend.ONEPASSWORD

    # Check for AWS (needs explicit configuration usually)
    if os.environ.get("SPECTRA_SECRET_BACKEND") == "aws":
        return SecretBackend.AWS

    # Default to environment
    return SecretBackend.ENVIRONMENT


def _create_manager(
    backend: SecretBackend,
    config: dict[str, Any],
) -> SecretManagerPort:
    """Create a manager for a specific backend."""
    if backend == SecretBackend.ENVIRONMENT:
        return EnvironmentSecretManager(
            EnvironmentConfig(
                prefix=config.get("prefix", os.environ.get("SPECTRA_SECRET_PREFIX", "")),
                load_dotenv=config.get("load_dotenv", True),
                dotenv_path=config.get("dotenv_path"),
            )
        )

    if backend == SecretBackend.VAULT:
        return VaultSecretManager(
            VaultConfig(
                address=config.get("address", os.environ.get("VAULT_ADDR", "")),
                token=config.get("token", os.environ.get("VAULT_TOKEN")),
                namespace=config.get("namespace", os.environ.get("VAULT_NAMESPACE")),
                mount_point=config.get("mount_point", os.environ.get("VAULT_MOUNT", "secret")),
                kv_version=config.get("kv_version", int(os.environ.get("VAULT_KV_VERSION", "2"))),
                role_id=config.get("role_id", os.environ.get("VAULT_ROLE_ID")),
                secret_id=config.get("secret_id", os.environ.get("VAULT_SECRET_ID")),
                kubernetes_role=config.get("kubernetes_role", os.environ.get("VAULT_K8S_ROLE")),
                timeout=config.get("timeout", 30),
                verify_ssl=config.get("verify_ssl", True),
                ca_cert=config.get("ca_cert", os.environ.get("VAULT_CACERT")),
            )
        )

    if backend == SecretBackend.AWS:
        return AwsSecretManager(
            AwsSecretsConfig(
                region=config.get("region", os.environ.get("AWS_REGION", "us-east-1")),
                access_key_id=config.get("access_key_id", os.environ.get("AWS_ACCESS_KEY_ID")),
                secret_access_key=config.get(
                    "secret_access_key", os.environ.get("AWS_SECRET_ACCESS_KEY")
                ),
                session_token=config.get("session_token", os.environ.get("AWS_SESSION_TOKEN")),
                profile=config.get("profile", os.environ.get("AWS_PROFILE")),
                endpoint_url=config.get("endpoint_url"),
                prefix=config.get("prefix", os.environ.get("SPECTRA_SECRET_PREFIX", "")),
            )
        )

    if backend == SecretBackend.ONEPASSWORD:
        return OnePasswordSecretManager(
            OnePasswordConfig(
                service_account_token=config.get(
                    "service_account_token",
                    os.environ.get("OP_SERVICE_ACCOUNT_TOKEN"),
                ),
                vault=config.get("vault", os.environ.get("OP_VAULT")),
                account=config.get("account", os.environ.get("OP_ACCOUNT")),
                op_path=config.get("op_path"),
                connect_host=config.get("connect_host", os.environ.get("OP_CONNECT_HOST")),
                connect_token=config.get("connect_token", os.environ.get("OP_CONNECT_TOKEN")),
            )
        )

    if backend == SecretBackend.DOPPLER:
        return DopplerSecretManager(
            DopplerConfig(
                token=config.get("token", os.environ.get("DOPPLER_TOKEN", "")),
                project=config.get("project", os.environ.get("DOPPLER_PROJECT")),
                config=config.get("config", os.environ.get("DOPPLER_CONFIG")),
                api_url=config.get(
                    "api_url",
                    os.environ.get("DOPPLER_API_URL", "https://api.doppler.com/v3"),
                ),
                timeout=config.get("timeout", 30),
            )
        )

    raise ValueError(f"Unsupported backend: {backend}")


def get_config_secret(
    reference: str,
    *,
    default: str | None = None,
    manager: SecretManagerPort | None = None,
) -> str | None:
    """
    Resolve a secret reference string to its value.

    Convenience function for use in configuration loading.

    Args:
        reference: Secret reference string (e.g., "vault://path#key" or "$ENV_VAR").
        default: Default value if secret not found.
        manager: Optional pre-configured manager (creates one if not provided).

    Returns:
        The secret value or default.

    Example:
        # In configuration loading
        config = {
            "jira_token": get_config_secret("vault://jira/api#token"),
            "github_token": get_config_secret("$GITHUB_TOKEN"),
            "api_key": get_config_secret("doppler://myapp/prod/API_KEY"),
        }
    """
    # Handle plain environment variable references
    if reference.startswith("$") and not reference.startswith("${"):
        env_name = reference[1:]
        return os.environ.get(env_name, default)

    # Check if it looks like a secret reference
    is_reference = False
    for backend in SecretBackend:
        if reference.startswith(f"{backend.value}://"):
            is_reference = True
            break

    if not is_reference:
        # Not a reference, return as-is (might be a literal value)
        return reference

    # Parse and resolve
    try:
        ref = SecretReference.parse(reference)
    except ValueError:
        return default

    # Create manager if not provided
    if manager is None:
        try:
            manager = create_secret_manager(ref.backend, fallback_to_env=False)
        except Exception:
            return default

    try:
        return manager.resolve(ref)
    except SecretNotFoundError:
        return default
    except Exception:
        return default


def resolve_config_secrets(
    config: dict[str, Any],
    *,
    manager: SecretManagerPort | None = None,
) -> dict[str, Any]:
    """
    Resolve all secret references in a configuration dictionary.

    Recursively processes the config and replaces any values that
    look like secret references with their resolved values.

    Args:
        config: Configuration dictionary.
        manager: Optional pre-configured manager.

    Returns:
        New dictionary with secrets resolved.

    Example:
        raw_config = {
            "tracker": {
                "type": "jira",
                "api_token": "vault://jira/credentials#api_token",
                "url": "https://jira.example.com",
            }
        }
        resolved = resolve_config_secrets(raw_config)
        # resolved["tracker"]["api_token"] is now the actual token
    """
    if manager is None:
        manager = create_secret_manager()

    return manager.resolve_config(config)


# Global manager instance (lazy-initialized)
_global_manager: SecretManagerPort | None = None


def get_global_secret_manager() -> SecretManagerPort:
    """
    Get the global secret manager instance.

    Creates one if it doesn't exist.

    Returns:
        The global SecretManagerPort instance.
    """
    global _global_manager
    if _global_manager is None:
        _global_manager = create_secret_manager()
    return _global_manager


def set_global_secret_manager(manager: SecretManagerPort) -> None:
    """
    Set the global secret manager instance.

    Args:
        manager: The manager to use globally.
    """
    global _global_manager
    _global_manager = manager
