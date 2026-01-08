"""
Tenant-Aware Configuration - Configuration management with tenant isolation.

Extends the configuration system to support per-tenant configuration
with inheritance and overrides.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from spectryn.core.ports.config_provider import (
    AppConfig,
    ConfigProviderPort,
    SyncConfig,
    TrackerConfig,
    ValidationConfig,
)
from spectryn.core.tenant import (
    DEFAULT_TENANT_ID,
    Tenant,
    TenantManager,
    TenantPaths,
    get_current_tenant,
    get_tenant_manager,
)


if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


# =============================================================================
# Tenant Configuration Provider
# =============================================================================


class TenantConfigProvider(ConfigProviderPort):
    """
    Configuration provider with tenant awareness.

    Loads configuration with the following precedence (highest first):
    1. CLI overrides
    2. Environment variables
    3. Tenant-specific config file
    4. Base/default config file
    5. Default values

    This allows tenants to inherit common configuration while
    overriding specific values.
    """

    def __init__(
        self,
        tenant_id: str | None = None,
        tenant_manager: TenantManager | None = None,
        cli_overrides: dict[str, Any] | None = None,
        inherit_from_default: bool = True,
    ):
        """
        Initialize the tenant config provider.

        Args:
            tenant_id: Explicit tenant ID (overrides context)
            tenant_manager: Tenant manager instance
            cli_overrides: Command line argument overrides
            inherit_from_default: Inherit config from default tenant
        """
        self._explicit_tenant_id = tenant_id
        self._tenant_manager = tenant_manager
        self._cli_overrides = cli_overrides or {}
        self._inherit_from_default = inherit_from_default
        self._values: dict[str, Any] = {}
        self._config: AppConfig | None = None

        # Load configuration
        self._load_config()

    @property
    def name(self) -> str:
        """Get provider name."""
        tenant_id = self._resolve_tenant_id()
        return f"Tenant[{tenant_id}]"

    def _resolve_tenant_id(self) -> str:
        """Resolve the current tenant ID."""
        if self._explicit_tenant_id:
            return self._explicit_tenant_id

        # Check context
        current = get_current_tenant()
        if current:
            return current.id

        # Get from manager
        manager = self._tenant_manager or get_tenant_manager()
        return manager.current_tenant.id

    def _resolve_tenant(self) -> Tenant:
        """Resolve the current tenant."""
        tenant_id = self._resolve_tenant_id()
        manager = self._tenant_manager or get_tenant_manager()
        return manager.registry.get_or_default(tenant_id)

    def _get_paths(self) -> TenantPaths:
        """Get paths for current tenant."""
        tenant = self._resolve_tenant()
        manager = self._tenant_manager or get_tenant_manager()
        return manager.registry.get_paths(tenant)

    def _load_config(self) -> None:
        """Load configuration from all sources."""
        self._values = {}

        # 1. Load default tenant config (if inheriting and not default)
        tenant_id = self._resolve_tenant_id()
        if self._inherit_from_default and tenant_id != DEFAULT_TENANT_ID:
            self._load_tenant_config(DEFAULT_TENANT_ID)

        # 2. Load current tenant config
        self._load_tenant_config(tenant_id)

        # 3. Load environment variables
        self._load_environment()

        # 4. Apply CLI overrides
        self._apply_cli_overrides()

    def _load_tenant_config(self, tenant_id: str) -> None:
        """Load configuration from a specific tenant."""
        manager = self._tenant_manager or get_tenant_manager()
        tenant = manager.registry.get(tenant_id)

        if not tenant:
            return

        paths = manager.registry.get_paths(tenant)

        # Load from config file
        if paths.config_file.exists():
            self._load_yaml_config(paths.config_file)

        # Load from .env file
        if paths.env_file.exists():
            self._load_env_file(paths.env_file)

    def _load_yaml_config(self, config_path: Path) -> None:
        """Load configuration from YAML file."""
        try:
            import yaml

            with open(config_path) as f:
                data = yaml.safe_load(f) or {}

            # Flatten nested config into dot-notation
            self._merge_config(data)
            logger.debug(f"Loaded config from {config_path}")

        except ImportError:
            logger.warning("PyYAML not available, skipping YAML config")
        except Exception as e:
            logger.warning(f"Failed to load config from {config_path}: {e}")

    def _load_env_file(self, env_path: Path) -> None:
        """Load configuration from .env file."""
        try:
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip().strip("\"'")
                        # Map common env var names to config keys
                        config_key = self._env_var_to_config_key(key)
                        if config_key:
                            self._values[config_key] = value
                        else:
                            self._values[key.lower()] = value

            logger.debug(f"Loaded env from {env_path}")

        except Exception as e:
            logger.warning(f"Failed to load env from {env_path}: {e}")

    def _load_environment(self) -> None:
        """Load configuration from environment variables."""
        env_mappings = {
            "JIRA_URL": "tracker.url",
            "JIRA_EMAIL": "tracker.email",
            "JIRA_API_TOKEN": "tracker.api_token",
            "JIRA_PROJECT": "tracker.project_key",
            "SPECTRA_TENANT": "tenant_id",
            "SPECTRA_DRY_RUN": "sync.dry_run",
            "SPECTRA_VERBOSE": "sync.verbose",
            "SPECTRA_CACHE_ENABLED": "sync.cache_enabled",
            "SPECTRA_CACHE_TTL": "sync.cache_ttl",
        }

        for env_key, config_key in env_mappings.items():
            env_value = os.environ.get(env_key)
            if env_value is not None:
                # Handle boolean values
                parsed_value: str | bool | int
                if env_value.lower() in ("true", "1", "yes"):
                    parsed_value = True
                elif env_value.lower() in ("false", "0", "no"):
                    parsed_value = False
                elif env_value.isdigit():
                    parsed_value = int(env_value)
                else:
                    parsed_value = env_value
                self._values[config_key] = parsed_value

    def _env_var_to_config_key(self, env_var: str) -> str | None:
        """Map environment variable name to config key."""
        env_mappings = {
            "JIRA_URL": "tracker.url",
            "JIRA_EMAIL": "tracker.email",
            "JIRA_API_TOKEN": "tracker.api_token",
            "JIRA_PROJECT": "tracker.project_key",
            "SPECTRA_TENANT": "tenant_id",
            "SPECTRA_DRY_RUN": "sync.dry_run",
            "SPECTRA_VERBOSE": "sync.verbose",
            "SPECTRA_CACHE_ENABLED": "sync.cache_enabled",
            "SPECTRA_CACHE_TTL": "sync.cache_ttl",
        }
        return env_mappings.get(env_var.upper())

    def _apply_cli_overrides(self) -> None:
        """Apply CLI argument overrides."""
        for key, value in self._cli_overrides.items():
            if value is not None:
                self._values[key] = value

    def _merge_config(self, data: dict[str, Any], prefix: str = "") -> None:
        """Merge nested config dictionary into flat values."""
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                self._merge_config(value, full_key)
            else:
                self._values[full_key] = value

    def load(self) -> AppConfig:
        """Load complete configuration."""
        if self._config:
            return self._config

        # Build TrackerConfig
        tracker = TrackerConfig(
            url=self.get("tracker.url", ""),
            email=self.get("tracker.email", ""),
            api_token=self.get("tracker.api_token", ""),
            project_key=self.get("tracker.project_key"),
            story_points_field=self.get("tracker.story_points_field", "customfield_10014"),
        )

        # Build SyncConfig
        sync = SyncConfig(
            dry_run=self.get("sync.dry_run", True),
            confirm_changes=self.get("sync.confirm_changes", True),
            verbose=self.get("sync.verbose", False),
            sync_epic=self.get("sync.sync_epic", True),
            create_stories=self.get("sync.create_stories", True),
            sync_descriptions=self.get("sync.sync_descriptions", True),
            sync_subtasks=self.get("sync.sync_subtasks", True),
            sync_comments=self.get("sync.sync_comments", True),
            sync_statuses=self.get("sync.sync_statuses", True),
            story_filter=self.get("sync.story_filter"),
            export_path=self.get("sync.export_path"),
            backup_enabled=self.get("sync.backup_enabled", True),
            backup_dir=self.get("sync.backup_dir"),
            cache_enabled=self.get("sync.cache_enabled", True),
            cache_ttl=self.get("sync.cache_ttl", 300.0),
            cache_max_size=self.get("sync.cache_max_size", 1000),
            cache_dir=self.get("sync.cache_dir"),
        )

        # Build ValidationConfig
        validation = ValidationConfig()

        self._config = AppConfig(
            tracker=tracker,
            sync=sync,
            validation=validation,
            markdown_path=self.get("markdown_path"),
            epic_key=self.get("epic_key"),
        )

        return self._config

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        return self._values.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value."""
        self._values[key] = value
        # Invalidate cached config
        self._config = None

    def validate(self) -> list[str]:
        """Validate configuration."""
        errors = []

        config = self.load()
        if not config.tracker.url:
            errors.append("Missing tracker URL (JIRA_URL)")
        if not config.tracker.email:
            errors.append("Missing tracker email (JIRA_EMAIL)")
        if not config.tracker.api_token:
            errors.append("Missing API token (JIRA_API_TOKEN)")

        return errors


# =============================================================================
# Tenant Configuration Manager
# =============================================================================


class TenantConfigManager:
    """
    Manage configuration across tenants.

    Provides methods for:
    - Creating tenant configurations
    - Copying configurations between tenants
    - Listing tenant configurations
    """

    def __init__(self, tenant_manager: TenantManager | None = None):
        """
        Initialize the config manager.

        Args:
            tenant_manager: Tenant manager instance
        """
        self.manager = tenant_manager or get_tenant_manager()

    def create_config(
        self,
        tenant_id: str,
        config_data: dict[str, Any],
        format: str = "yaml",
    ) -> Path:
        """
        Create a configuration file for a tenant.

        Args:
            tenant_id: Tenant ID
            config_data: Configuration data
            format: Config format ("yaml", "toml", "env")

        Returns:
            Path to created config file
        """
        paths = self.manager.registry.get_paths(tenant_id)
        paths.ensure_dirs()

        if format == "yaml":
            return self._write_yaml_config(paths.config_file, config_data)
        if format == "toml":
            return self._write_toml_config(paths.config_dir / "spectra.toml", config_data)
        if format == "env":
            return self._write_env_config(paths.env_file, config_data)
        raise ValueError(f"Unsupported config format: {format}")

    def _write_yaml_config(self, path: Path, data: dict[str, Any]) -> Path:
        """Write YAML configuration."""
        try:
            import yaml

            with open(path, "w") as f:
                yaml.safe_dump(data, f, default_flow_style=False)

            logger.info(f"Created YAML config: {path}")
            return path

        except ImportError:
            raise RuntimeError("PyYAML not available")

    def _write_toml_config(self, path: Path, data: dict[str, Any]) -> Path:
        """Write TOML configuration."""
        try:
            import tomli_w

            with open(path, "wb") as f:
                tomli_w.dump(data, f)

            logger.info(f"Created TOML config: {path}")
            return path

        except ImportError:
            # Fall back to manual TOML writing
            lines: list[str] = []
            self._dict_to_toml_lines(data, lines)
            path.write_text("\n".join(lines))
            logger.info(f"Created TOML config: {path}")
            return path

    def _dict_to_toml_lines(
        self,
        data: dict[str, Any],
        lines: list[str],
        prefix: str = "",
    ) -> None:
        """Convert dict to TOML lines."""
        for key, value in data.items():
            if isinstance(value, dict):
                section = f"{prefix}.{key}" if prefix else key
                lines.append(f"[{section}]")
                self._dict_to_toml_lines(value, lines, section)
            elif isinstance(value, str):
                lines.append(f'{key} = "{value}"')
            elif isinstance(value, bool):
                lines.append(f"{key} = {str(value).lower()}")
            else:
                lines.append(f"{key} = {value}")

    def _write_env_config(self, path: Path, data: dict[str, Any]) -> Path:
        """Write .env configuration."""
        lines: list[str] = []

        # Flatten nested config
        flat: dict[str, Any] = {}
        self._flatten_dict(data, flat)

        # Convert to env format
        for key, value in flat.items():
            env_key = key.upper().replace(".", "_").replace("-", "_")
            if isinstance(value, bool):
                value = "true" if value else "false"
            lines.append(f"{env_key}={value}")

        path.write_text("\n".join(lines) + "\n")
        logger.info(f"Created .env config: {path}")
        return path

    def _flatten_dict(
        self,
        data: dict[str, Any],
        result: dict[str, Any],
        prefix: str = "",
    ) -> None:
        """Flatten nested dict."""
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                self._flatten_dict(value, result, full_key)
            else:
                result[full_key] = value

    def copy_config(
        self,
        source_tenant_id: str,
        target_tenant_id: str,
        exclude_credentials: bool = True,
    ) -> dict[str, Path]:
        """
        Copy configuration from one tenant to another.

        Args:
            source_tenant_id: Source tenant
            target_tenant_id: Target tenant
            exclude_credentials: Exclude sensitive credentials

        Returns:
            Dictionary of copied file paths
        """
        import shutil

        source_paths = self.manager.registry.get_paths(source_tenant_id)
        target_paths = self.manager.registry.get_paths(target_tenant_id)

        target_paths.ensure_dirs()
        copied = {}

        # Copy config file
        if source_paths.config_file.exists():
            if exclude_credentials:
                # Load, sanitize, and save
                config_data = self._load_and_sanitize_config(source_paths.config_file)
                target_file = self.create_config(target_tenant_id, config_data, "yaml")
                copied["config"] = target_file
            else:
                shutil.copy2(source_paths.config_file, target_paths.config_file)
                copied["config"] = target_paths.config_file

        return copied

    def _load_and_sanitize_config(self, path: Path) -> dict[str, Any]:
        """Load config and remove sensitive values."""
        try:
            import yaml

            with open(path) as f:
                data = yaml.safe_load(f) or {}

            # Remove sensitive fields
            sensitive_fields = ["api_token", "api_key", "password", "secret", "pat"]

            def sanitize(obj: Any) -> Any:
                if isinstance(obj, dict):
                    return {
                        k: (
                            "***REDACTED***"
                            if any(s in k.lower() for s in sensitive_fields)
                            else sanitize(v)
                        )
                        for k, v in obj.items()
                    }
                return obj

            result = sanitize(data)
            return result if isinstance(result, dict) else {}

        except ImportError:
            return {}

    def list_tenant_configs(self) -> list[dict[str, Any]]:
        """
        List configuration status for all tenants.

        Returns:
            List of tenant config status dicts
        """
        results = []

        for tenant in self.manager.list_tenants():
            paths = self.manager.registry.get_paths(tenant)

            status = {
                "tenant_id": tenant.id,
                "tenant_name": tenant.name,
                "has_config_file": paths.config_file.exists(),
                "has_env_file": paths.env_file.exists(),
                "config_file_path": str(paths.config_file),
                "env_file_path": str(paths.env_file),
            }

            # Get validation status
            try:
                provider = TenantConfigProvider(tenant_id=tenant.id)
                errors = provider.validate()
                status["is_valid"] = len(errors) == 0
                status["validation_errors"] = errors
            except Exception as e:
                status["is_valid"] = False
                status["validation_errors"] = [str(e)]

            results.append(status)

        return results


# =============================================================================
# Factory Functions
# =============================================================================


def create_tenant_config_provider(
    tenant_id: str | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> TenantConfigProvider:
    """
    Create a tenant-aware configuration provider.

    Args:
        tenant_id: Explicit tenant ID
        cli_overrides: CLI argument overrides

    Returns:
        Configured TenantConfigProvider
    """
    return TenantConfigProvider(
        tenant_id=tenant_id,
        cli_overrides=cli_overrides,
    )


def get_tenant_config_path(
    tenant_id: str | None = None,
    config_type: str = "config",
) -> Path:
    """
    Get the configuration file path for a tenant.

    Args:
        tenant_id: Tenant ID (None for current)
        config_type: "config" or "env"

    Returns:
        Path to configuration file
    """
    manager = get_tenant_manager()
    paths = manager.registry.get_paths(tenant_id) if tenant_id else manager.current_paths

    if config_type == "env":
        return paths.env_file
    return paths.config_file


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "TenantConfigManager",
    "TenantConfigProvider",
    "create_tenant_config_provider",
    "get_tenant_config_path",
]
