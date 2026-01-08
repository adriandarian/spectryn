"""
Environment Config Provider - Load configuration from environment variables.

Supports (in order of precedence, highest first):
1. Command line argument overrides
2. Environment variables (JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN)
3. .env files
4. Config files (.spectra.yaml, .spectra.toml, pyproject.toml)
"""

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


if TYPE_CHECKING:
    from .file_config import FileConfigProvider


class EnvironmentConfigProvider(ConfigProviderPort):
    """
    Configuration provider that loads from environment variables and .env files.

    Optionally loads base configuration from a config file (.spectra.yaml,
    .spectra.toml, or pyproject.toml), then overlays environment variables,
    and finally applies CLI overrides.
    """

    ENV_PREFIX = "JIRA_"

    def __init__(
        self,
        env_file: Path | None = None,
        config_file: Path | None = None,
        cli_overrides: dict[str, Any] | None = None,
    ) -> None:
        """
        Initialize the config provider.

        Args:
            env_file: Path to .env file (auto-detected if not specified)
            config_file: Path to config file (.spectra.yaml, .spectra.toml)
            cli_overrides: Command line argument overrides
        """
        self._values: dict[str, Any] = {}
        self._env_file = env_file
        self._config_file = config_file
        self._cli_overrides = cli_overrides or {}
        self._file_config: FileConfigProvider | None = None
        self._config_file_path: Path | None = None

        # Load configuration (order matters - later sources override earlier)
        self._load_file_config()  # 4. Config files (lowest priority)
        self._load_env_file()  # 3. .env files
        self._load_environment()  # 2. Environment variables
        self._apply_cli_overrides()  # 1. CLI args (highest priority)

    # -------------------------------------------------------------------------
    # ConfigProviderPort Implementation
    # -------------------------------------------------------------------------

    @property
    def name(self) -> str:
        if self._config_file_path:
            return f"Environment + {self._config_file_path.name}"
        return "Environment"

    @property
    def config_file_path(self) -> Path | None:
        """Get the path to the loaded config file, if any."""
        return self._config_file_path

    def load(self) -> AppConfig:
        """Load complete configuration."""
        tracker = TrackerConfig(
            url=self.get("jira_url", ""),
            email=self.get("jira_email", ""),
            api_token=self.get("jira_api_token", ""),
            project_key=self.get("project_key"),
            story_points_field=self.get("story_points_field", "customfield_10014"),
        )

        sync = SyncConfig(
            dry_run=not self.get("execute", False),
            confirm_changes=not self.get("no_confirm", False),
            verbose=self.get("verbose", False),
            sync_descriptions=self.get("sync_descriptions", True),
            sync_subtasks=self.get("sync_subtasks", True),
            sync_comments=self.get("sync_comments", True),
            sync_statuses=self.get("sync_statuses", True),
            story_filter=self.get("story_filter"),
            export_path=self.get("export_path"),
        )

        # Get validation config from file config if available, otherwise use defaults
        # The FileConfigProvider loads the complete nested validation configuration
        validation = self.get("_validation_config", ValidationConfig())

        return AppConfig(
            tracker=tracker,
            sync=sync,
            validation=validation,
            markdown_path=self.get("markdown_path"),
            epic_key=self.get("epic_key"),
        )

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        # Normalize key
        key = key.lower().replace("-", "_")

        # Check CLI overrides first (only if value is not None)
        if key in self._cli_overrides and self._cli_overrides[key] is not None:
            return self._cli_overrides[key]

        # Check loaded values
        return self._values.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value."""
        key = key.lower().replace("-", "_")
        self._values[key] = value

    def validate(self) -> list[str]:
        """Validate configuration with clear, actionable error messages."""
        errors = []

        # Check for file config errors first
        if self._file_config:
            file_errors = self._file_config.validate()
            # Only add errors that aren't about missing values (we may have them from env)
            for err in file_errors:
                if "syntax" in err.lower() or "unexpected" in err.lower():
                    errors.append(err)

        config_sources = "Set via:\n" + (
            "  • Config file: jira.url, jira.email, jira.api_token\n"
            "  • Environment: JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN\n"
            "  • .env file: JIRA_URL=..., JIRA_EMAIL=..., JIRA_API_TOKEN=..."
        )

        if not self.get("jira_url"):
            errors.append(f"Missing Jira URL.\n{config_sources}")
        if not self.get("jira_email"):
            errors.append(f"Missing Jira email.\n{config_sources}")
        if not self.get("jira_api_token"):
            errors.append(f"Missing Jira API token.\n{config_sources}")

        return errors

    # -------------------------------------------------------------------------
    # Private Methods
    # -------------------------------------------------------------------------

    def _load_file_config(self) -> None:
        """Load values from config file (.spectra.yaml, .spectra.toml, etc.)."""
        from .file_config import FileConfigProvider

        try:
            self._file_config = FileConfigProvider(
                config_path=self._config_file,
                cli_overrides={},  # Don't pass CLI overrides - we handle them
            )
            self._config_file_path = self._file_config.config_file_path

            # Merge file config values into our values
            if self._config_file_path:
                file_app_config = self._file_config.load()

                # Map file config to flat keys
                if file_app_config.tracker.url:
                    self._values["jira_url"] = file_app_config.tracker.url
                if file_app_config.tracker.email:
                    self._values["jira_email"] = file_app_config.tracker.email
                if file_app_config.tracker.api_token:
                    self._values["jira_api_token"] = file_app_config.tracker.api_token
                if file_app_config.tracker.project_key:
                    self._values["project_key"] = file_app_config.tracker.project_key
                if file_app_config.tracker.story_points_field:
                    self._values["story_points_field"] = file_app_config.tracker.story_points_field
                if file_app_config.markdown_path:
                    self._values["markdown_path"] = file_app_config.markdown_path
                if file_app_config.epic_key:
                    self._values["epic_key"] = file_app_config.epic_key

                # Sync config
                self._values["execute"] = not file_app_config.sync.dry_run
                self._values["no_confirm"] = not file_app_config.sync.confirm_changes
                self._values["verbose"] = file_app_config.sync.verbose
                self._values["sync_descriptions"] = file_app_config.sync.sync_descriptions
                self._values["sync_subtasks"] = file_app_config.sync.sync_subtasks
                self._values["sync_comments"] = file_app_config.sync.sync_comments
                self._values["sync_statuses"] = file_app_config.sync.sync_statuses
                if file_app_config.sync.story_filter:
                    self._values["story_filter"] = file_app_config.sync.story_filter
                if file_app_config.sync.export_path:
                    self._values["export_path"] = file_app_config.sync.export_path

                # Store complete validation config object
                # This preserves all nested configuration from the file
                self._values["_validation_config"] = file_app_config.validation

        except Exception:
            # File config is optional, don't fail if it can't load
            pass

    def _load_env_file(self) -> None:
        """Load values from .env file."""
        env_file = self._find_env_file()
        if not env_file:
            return

        for line in env_file.read_text().splitlines():
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            # Parse key=value
            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip().lower()
            value = value.strip().strip('"').strip("'")

            self._values[key] = value

    def _find_env_file(self) -> Path | None:
        """Find .env file."""
        if self._env_file and self._env_file.exists():
            return self._env_file

        # Check current directory
        cwd_env = Path.cwd() / ".env"
        if cwd_env.exists():
            return cwd_env

        # Check package directory
        pkg_env = Path(__file__).parent.parent.parent.parent / ".env"
        if pkg_env.exists():
            return pkg_env

        return None

    def _load_environment(self) -> None:
        """Load values from environment variables."""
        env_mapping = {
            "JIRA_URL": "jira_url",
            "JIRA_EMAIL": "jira_email",
            "JIRA_API_TOKEN": "jira_api_token",
            "JIRA_PROJECT": "project_key",
            "SPECTRA_VERBOSE": "verbose",
            "SPECTRA_LOG_FORMAT": "log_format",
        }

        for env_key, config_key in env_mapping.items():
            raw_value = os.environ.get(env_key)
            if raw_value is not None:
                # Convert boolean-ish values
                final_value: Any
                if raw_value.lower() in ("true", "1", "yes"):
                    final_value = True
                elif raw_value.lower() in ("false", "0", "no"):
                    final_value = False
                else:
                    final_value = raw_value

                self._values[config_key] = final_value

    def _apply_cli_overrides(self) -> None:
        """Apply CLI argument overrides."""
        # Map CLI args to config keys
        cli_mapping = {
            "markdown": "markdown_path",
            "epic": "epic_key",
            "project": "project_key",
            "jira_url": "jira_url",
            "story": "story_filter",
            "execute": "execute",
            "no_confirm": "no_confirm",
            "verbose": "verbose",
        }

        for cli_key, config_key in cli_mapping.items():
            if cli_key in self._cli_overrides and self._cli_overrides[cli_key] is not None:
                self._values[config_key] = self._cli_overrides[cli_key]
