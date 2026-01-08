"""
1Password Secret Manager.

Developer-friendly password manager with support for:
- CLI-based access (op command)
- Service accounts
- Vaults and items
- Secret references (op:// format)
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
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
class OnePasswordConfig:
    """
    Configuration for 1Password.

    Attributes:
        service_account_token: Service account token for automation.
        vault: Default vault to use.
        account: 1Password account (for CLI sign-in).
        op_path: Path to the op CLI binary.
        connect_host: 1Password Connect server host.
        connect_token: 1Password Connect server token.
    """

    service_account_token: str | None = None
    vault: str | None = None
    account: str | None = None
    op_path: str | None = None
    connect_host: str | None = None
    connect_token: str | None = None

    def is_valid(self) -> bool:
        """Check if configuration is valid."""
        return bool(self.service_account_token or self.connect_host or self.account)


class OnePasswordSecretManager(SecretManagerPort):
    """
    1Password secret manager using the op CLI.

    Supports:
    - Service account authentication
    - Vault and item access
    - Field-level retrieval
    - Secret references (op://vault/item/field)

    Requires the 1Password CLI (op) to be installed.

    Example:
        config = OnePasswordConfig(
            service_account_token="ops_xxx",
            vault="Private",
        )
        manager = OnePasswordSecretManager(config)

        # Get an item
        secret = manager.get_secret("Jira API Token")

        # Get a specific field
        token = manager.get_value("Jira", key="api-token")

        # Use op:// reference format
        ref = SecretReference.parse("1password://op://Private/Jira/api-token")
        token = manager.resolve(ref)
    """

    def __init__(self, config: OnePasswordConfig) -> None:
        """
        Initialize the 1Password secret manager.

        Args:
            config: 1Password configuration.

        Raises:
            ConnectionError: If op CLI is not found.
            AuthenticationError: If authentication fails.
        """
        self._config = config
        self._op_path = config.op_path or self._find_op_cli()
        self._env: dict[str, str] = {}

        if not self._op_path:
            raise ConnectionError(
                "1password",
                "1Password CLI (op) not found. Install from: "
                "https://developer.1password.com/docs/cli/get-started/",
            )

        # Setup environment for service account
        if config.service_account_token:
            self._env["OP_SERVICE_ACCOUNT_TOKEN"] = config.service_account_token

        # Verify authentication
        self._verify_auth()

    def _find_op_cli(self) -> str | None:
        """Find the op CLI binary."""
        # Check common locations
        op_path = shutil.which("op")
        if op_path:
            return op_path

        # Check common install locations
        common_paths = [
            "/usr/local/bin/op",
            "/opt/homebrew/bin/op",
            str(Path.home() / ".op" / "bin" / "op"),
            "C:\\Program Files\\1Password CLI\\op.exe",
        ]
        for path in common_paths:
            if Path(path).is_file():
                return path

        return None

    def _run_op(
        self,
        args: list[str],
        *,
        check: bool = True,
    ) -> dict[str, Any] | list[Any] | str:
        """
        Run an op CLI command.

        Args:
            args: Command arguments.
            check: Whether to check for errors.

        Returns:
            Parsed JSON output or raw output.

        Raises:
            SecretManagerError: If command fails.
        """
        assert self._op_path is not None  # Verified in __init__
        cmd: list[str] = [self._op_path, *args, "--format=json"]

        # Add account if specified
        if self._config.account and "--account" not in args:
            cmd.extend(["--account", self._config.account])

        env = {**os.environ, **self._env}

        try:
            result = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                env=env,
                timeout=30,
            )

            if check and result.returncode != 0:
                stderr = result.stderr.strip()
                if "not signed in" in stderr.lower():
                    raise AuthenticationError("1password", stderr)
                if "not found" in stderr.lower() or "doesn't exist" in stderr.lower():
                    raise SecretNotFoundError(str(args), "1password")
                if "permission" in stderr.lower() or "access" in stderr.lower():
                    raise AccessDeniedError(str(args), "1password")
                raise SecretManagerError(f"op command failed: {stderr}")

            if result.stdout:
                try:
                    data: dict[str, Any] | list[Any] = json.loads(result.stdout)
                    return data
                except json.JSONDecodeError:
                    return result.stdout.strip()
            return ""

        except subprocess.TimeoutExpired as e:
            raise ConnectionError("1password", "Command timed out") from e
        except FileNotFoundError as e:
            raise ConnectionError("1password", "op CLI not found") from e

    def _verify_auth(self) -> None:
        """Verify authentication is working."""
        try:
            # Try to get account info or list vaults
            self._run_op(["whoami"])
            logger.debug("Authenticated with 1Password")
        except (AuthenticationError, SecretManagerError) as e:
            # Try listing vaults as alternative check
            try:
                self._run_op(["vault", "list"])
            except Exception:
                raise AuthenticationError(
                    "1password",
                    f"Authentication failed: {e}",
                ) from e

    def _parse_item(self, item: dict[str, Any]) -> tuple[str | None, dict[str, str]]:
        """Parse a 1Password item into value and data."""
        data: dict[str, str] = {}
        primary_value: str | None = None

        # Extract fields
        for field in item.get("fields", []):
            field_id = field.get("id", "")
            field_label = field.get("label", "")
            field_value = field.get("value", "")

            if field_value:
                # Use label as key, fall back to id
                key = field_label or field_id
                data[key] = field_value

                # Common primary fields
                primary_ids = ("password", "credential", "api_token", "secret")
                primary_labels = ("password", "api token", "api-token", "secret")
                if field_id in primary_ids or field_label.lower() in primary_labels:
                    primary_value = field_value

        # If no primary found, use first value
        if not primary_value and data:
            primary_value = next(iter(data.values()))

        return primary_value, data

    def _parse_path(self, path: str) -> tuple[str | None, str, str | None]:
        """
        Parse a path into vault, item, and field.

        Supports formats:
        - item_name
        - vault/item_name
        - vault/item_name/field
        - op://vault/item/field (1Password reference format)

        Returns:
            Tuple of (vault, item, field).
        """
        # Handle op:// format
        if path.startswith("op://"):
            path = path[5:]

        parts = path.split("/")

        if len(parts) == 1:
            return self._config.vault, parts[0], None
        if len(parts) == 2:
            return parts[0], parts[1], None
        if len(parts) >= 3:
            return parts[0], parts[1], "/".join(parts[2:])

        return self._config.vault, path, None

    @property
    def backend(self) -> SecretBackend:
        """Return the backend type."""
        return SecretBackend.ONEPASSWORD

    def get_secret(
        self,
        path: str,
        *,
        version: str | None = None,
    ) -> Secret:
        """
        Get a secret from 1Password.

        Args:
            path: Item path (item, vault/item, or op://vault/item/field).
            version: Ignored (1Password doesn't expose version history via CLI).

        Returns:
            Secret with data and metadata.

        Raises:
            SecretNotFoundError: If item doesn't exist.
            AccessDeniedError: If access is denied.
        """
        vault, item_name, field = self._parse_path(path)

        args = ["item", "get", item_name]
        if vault:
            args.extend(["--vault", vault])

        result = self._run_op(args)
        if not isinstance(result, dict):
            raise SecretManagerError(f"Unexpected response from op: {result}")

        value, data = self._parse_item(result)

        # If a specific field was requested, extract it
        if field and field in data:
            value = data[field]

        # Parse metadata
        created_at = None
        updated_at = None
        if result.get("created_at"):
            with contextlib.suppress(ValueError):
                created_at = datetime.fromisoformat(result["created_at"].replace("Z", "+00:00"))
        if result.get("updated_at"):
            with contextlib.suppress(ValueError):
                updated_at = datetime.fromisoformat(result["updated_at"].replace("Z", "+00:00"))

        return Secret(
            path=path,
            value=value,
            data=data,
            version=result.get("version", "1"),
            metadata=SecretMetadata(
                path=path,
                created_at=created_at,
                updated_at=updated_at,
                version=str(result.get("version", 1)),
                tags=dict.fromkeys(result.get("tags", []), ""),
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
        Get a specific value from a 1Password item.

        Can use op read command for direct field access.

        Args:
            path: Item path.
            key: Field name within the item.
            version: Ignored.
            default: Default if not found.

        Returns:
            The value or default.
        """
        try:
            # If key is specified, try direct read first
            if key:
                vault, item_name, _ = self._parse_path(path)
                ref = f"op://{vault or 'Private'}/{item_name}/{key}"
                try:
                    result = self._run_op(["read", ref], check=False)
                    if isinstance(result, str) and result:
                        return result
                except SecretManagerError:
                    pass

            # Fall back to getting full item
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
        # Build op:// reference
        path = reference.path
        if reference.key:
            path = f"{path}/{reference.key}"

        value = self.get_value(path, default=None)
        if value is None:
            raise SecretNotFoundError(reference.path, "1password")
        return value

    def exists(self, path: str) -> bool:
        """Check if an item exists."""
        try:
            self.get_secret(path)
            return True
        except SecretNotFoundError:
            return False
        except SecretManagerError:
            return False

    def list_secrets(self, prefix: str = "") -> list[str]:
        """
        List items in a vault.

        Args:
            prefix: Vault name or prefix filter.

        Returns:
            List of item paths.
        """
        vault = prefix or self._config.vault

        args = ["item", "list"]
        if vault:
            args.extend(["--vault", vault])

        try:
            result = self._run_op(args)
            if not isinstance(result, list):
                return []

            items = []
            for item in result:
                item_id = item.get("id", "")
                item_title = item.get("title", item_id)
                item_vault = item.get("vault", {}).get("name", vault or "")
                if item_vault:
                    items.append(f"{item_vault}/{item_title}")
                else:
                    items.append(item_title)

            return items
        except SecretManagerError:
            return []

    def get_metadata(self, path: str) -> SecretMetadata:
        """
        Get metadata for an item.

        Args:
            path: Item path.

        Returns:
            Item metadata.

        Raises:
            SecretNotFoundError: If not found.
        """
        secret = self.get_secret(path)
        return secret.metadata or SecretMetadata(path=path)

    def info(self) -> SecretManagerInfo:
        """Get information about the 1Password connection."""
        features = ["vaults", "items", "fields"]
        if self._config.service_account_token:
            features.append("service-account")

        return SecretManagerInfo(
            backend=SecretBackend.ONEPASSWORD,
            connected=True,
            authenticated=True,
            features=features,
            health_status="healthy" if self.health_check() else "unhealthy",
        )

    def health_check(self) -> bool:
        """Check if 1Password is accessible."""
        try:
            self._run_op(["vault", "list"], check=False)
            return True
        except (ConnectionError, SecretManagerError):
            return False

    def close(self) -> None:
        """No resources to release."""
