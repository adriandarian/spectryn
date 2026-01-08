"""
Secret Manager Adapters - Implementations of SecretManagerPort.

Available backends:
- EnvironmentSecretManager: Environment variables (default fallback)
- VaultSecretManager: HashiCorp Vault
- AwsSecretManager: AWS Secrets Manager
- OnePasswordSecretManager: 1Password
- DopplerSecretManager: Doppler
"""

from .aws_manager import AwsSecretManager
from .doppler_manager import DopplerSecretManager
from .environment_manager import EnvironmentSecretManager
from .factory import create_secret_manager, get_config_secret
from .onepassword_manager import OnePasswordSecretManager
from .vault_manager import VaultSecretManager


__all__ = [
    "AwsSecretManager",
    "DopplerSecretManager",
    "EnvironmentSecretManager",
    "OnePasswordSecretManager",
    "VaultSecretManager",
    "create_secret_manager",
    "get_config_secret",
]
