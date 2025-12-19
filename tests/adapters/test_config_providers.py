"""
Tests for configuration providers.
"""

from pathlib import Path
from textwrap import dedent

import pytest

from spectra.adapters.config import (
    EnvironmentConfigProvider,
    FileConfigProvider,
)


class TestFileConfigProvider:
    """Tests for FileConfigProvider."""

    def test_load_yaml_config(self, tmp_path: Path) -> None:
        """Test loading YAML config file."""
        config_file = tmp_path / ".spectra.yaml"
        config_file.write_text(
            dedent(
                """
            jira:
              url: https://example.atlassian.net
              email: user@example.com
              api_token: secret-token
              project: PROJ

            sync:
              verbose: true
              descriptions: true
              subtasks: false

            markdown: /path/to/epic.md
            epic: PROJ-123
        """
            )
        )

        provider = FileConfigProvider(config_path=config_file)
        config = provider.load()

        assert config.tracker.url == "https://example.atlassian.net"
        assert config.tracker.email == "user@example.com"
        assert config.tracker.api_token == "secret-token"
        assert config.tracker.project_key == "PROJ"
        assert config.sync.verbose is True
        assert config.sync.sync_descriptions is True
        assert config.sync.sync_subtasks is False
        assert config.markdown_path == "/path/to/epic.md"
        assert config.epic_key == "PROJ-123"

    def test_load_toml_config(self, tmp_path: Path) -> None:
        """Test loading TOML config file."""
        config_file = tmp_path / ".spectra.toml"
        config_file.write_text(
            dedent(
                """
            markdown = "/path/to/epic.md"
            epic = "PROJ-456"

            [jira]
            url = "https://company.atlassian.net"
            email = "dev@company.com"
            api_token = "api-token-123"

            [sync]
            verbose = false
            execute = true
        """
            )
        )

        provider = FileConfigProvider(config_path=config_file)
        config = provider.load()

        assert config.tracker.url == "https://company.atlassian.net"
        assert config.tracker.email == "dev@company.com"
        assert config.tracker.api_token == "api-token-123"
        assert config.markdown_path == "/path/to/epic.md"
        assert config.epic_key == "PROJ-456"
        assert config.sync.verbose is False
        assert config.sync.dry_run is False  # execute = true

    def test_load_pyproject_toml(self, tmp_path: Path) -> None:
        """Test loading from pyproject.toml [tool.spectra] section."""
        config_file = tmp_path / "pyproject.toml"
        config_file.write_text(
            dedent(
                """
            [project]
            name = "my-project"

            [tool.spectra]
            epic = "PROJ-789"

            [tool.spectra.jira]
            url = "https://test.atlassian.net"
            email = "test@test.com"
            api_token = "test-token"
        """
            )
        )

        provider = FileConfigProvider(config_path=config_file)
        config = provider.load()

        assert config.tracker.url == "https://test.atlassian.net"
        assert config.tracker.email == "test@test.com"
        assert config.epic_key == "PROJ-789"

    def test_config_file_not_found(self, tmp_path: Path) -> None:
        """Test error when specified config file doesn't exist."""
        config_file = tmp_path / "nonexistent.yaml"

        provider = FileConfigProvider(config_path=config_file)
        errors = provider.validate()

        assert any("not found" in err.lower() for err in errors)

    def test_invalid_yaml_syntax(self, tmp_path: Path) -> None:
        """Test error on invalid YAML syntax."""
        config_file = tmp_path / ".spectra.yaml"
        config_file.write_text(
            dedent(
                """
            jira:
              url: "unclosed string
              invalid:: yaml
        """
            )
        )

        provider = FileConfigProvider(config_path=config_file)
        errors = provider.validate()

        assert len(errors) > 0
        assert any("yaml" in err.lower() or "syntax" in err.lower() for err in errors)

    def test_invalid_toml_syntax(self, tmp_path: Path) -> None:
        """Test error on invalid TOML syntax."""
        config_file = tmp_path / ".spectra.toml"
        config_file.write_text(
            dedent(
                """
            [jira
            url = invalid
        """
            )
        )

        provider = FileConfigProvider(config_path=config_file)
        errors = provider.validate()

        assert len(errors) > 0

    def test_cli_overrides_take_precedence(self, tmp_path: Path) -> None:
        """Test that CLI overrides take precedence over file config."""
        config_file = tmp_path / ".spectra.yaml"
        config_file.write_text(
            dedent(
                """
            jira:
              url: https://file.atlassian.net
              email: file@example.com
              api_token: file-token

            sync:
              verbose: false
        """
            )
        )

        provider = FileConfigProvider(
            config_path=config_file,
            cli_overrides={"verbose": True, "jira_url": "https://cli.atlassian.net"},
        )

        # CLI override should win
        assert provider.get("sync.verbose") is True

    def test_auto_detect_yaml_in_cwd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test auto-detection of .spectra.yaml in current directory."""
        monkeypatch.chdir(tmp_path)

        config_file = tmp_path / ".spectra.yaml"
        config_file.write_text(
            dedent(
                """
            jira:
              url: https://auto.atlassian.net
              email: auto@example.com
              api_token: auto-token
        """
            )
        )

        provider = FileConfigProvider()
        config = provider.load()

        assert config.tracker.url == "https://auto.atlassian.net"
        assert provider.config_file_path == config_file

    def test_validate_missing_required_fields(self, tmp_path: Path) -> None:
        """Test validation reports missing required fields."""
        config_file = tmp_path / ".spectra.yaml"
        config_file.write_text(
            dedent(
                """
            jira:
              url: https://example.atlassian.net
            # Missing email and api_token
        """
            )
        )

        provider = FileConfigProvider(config_path=config_file)
        errors = provider.validate()

        assert any("email" in err.lower() for err in errors)
        assert any("api_token" in err.lower() or "token" in err.lower() for err in errors)


class TestEnvironmentConfigProvider:
    """Tests for EnvironmentConfigProvider with file config integration."""

    def test_load_from_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading configuration from environment variables."""
        monkeypatch.setenv("JIRA_URL", "https://env.atlassian.net")
        monkeypatch.setenv("JIRA_EMAIL", "env@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "env-token")

        provider = EnvironmentConfigProvider()
        config = provider.load()

        assert config.tracker.url == "https://env.atlassian.net"
        assert config.tracker.email == "env@example.com"
        assert config.tracker.api_token == "env-token"

    def test_env_overrides_file_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that environment variables override file config."""
        config_file = tmp_path / ".spectra.yaml"
        config_file.write_text(
            dedent(
                """
            jira:
              url: https://file.atlassian.net
              email: file@example.com
              api_token: file-token
        """
            )
        )

        monkeypatch.setenv("JIRA_URL", "https://env.atlassian.net")
        monkeypatch.setenv("JIRA_EMAIL", "env@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "env-token")

        provider = EnvironmentConfigProvider(config_file=config_file)
        config = provider.load()

        # Environment should override file
        assert config.tracker.url == "https://env.atlassian.net"
        assert config.tracker.email == "env@example.com"
        assert config.tracker.api_token == "env-token"

    def test_cli_overrides_env_and_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that CLI args override both env and file config."""
        config_file = tmp_path / ".spectra.yaml"
        config_file.write_text(
            dedent(
                """
            jira:
              url: https://file.atlassian.net
              email: file@example.com
              api_token: file-token

            sync:
              verbose: false
        """
            )
        )

        monkeypatch.setenv("JIRA_URL", "https://env.atlassian.net")
        monkeypatch.setenv("MD2JIRA_VERBOSE", "false")

        provider = EnvironmentConfigProvider(
            config_file=config_file,
            cli_overrides={"jira_url": "https://cli.atlassian.net", "verbose": True},
        )
        config = provider.load()

        # CLI should override both env and file
        assert config.tracker.url == "https://cli.atlassian.net"
        assert config.sync.verbose is True

    def test_load_from_env_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading from .env file."""
        monkeypatch.chdir(tmp_path)

        env_file = tmp_path / ".env"
        env_file.write_text(
            dedent(
                """
            JIRA_URL=https://dotenv.atlassian.net
            JIRA_EMAIL=dotenv@example.com
            JIRA_API_TOKEN=dotenv-token
        """
            )
        )

        provider = EnvironmentConfigProvider()
        config = provider.load()

        assert config.tracker.url == "https://dotenv.atlassian.net"
        assert config.tracker.email == "dotenv@example.com"

    def test_shows_config_file_in_name(self, tmp_path: Path) -> None:
        """Test that provider name includes config file when loaded."""
        config_file = tmp_path / ".spectra.yaml"
        config_file.write_text(
            dedent(
                """
            jira:
              url: https://example.atlassian.net
              email: test@example.com
              api_token: token
        """
            )
        )

        provider = EnvironmentConfigProvider(config_file=config_file)

        assert ".spectra.yaml" in provider.name

    def test_validation_error_messages_are_actionable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that validation errors include helpful guidance."""
        # Clear any existing env vars
        monkeypatch.delenv("JIRA_URL", raising=False)
        monkeypatch.delenv("JIRA_EMAIL", raising=False)
        monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
        monkeypatch.chdir(tmp_path)  # Ensure no .env file is found

        provider = EnvironmentConfigProvider()
        errors = provider.validate()

        # Errors should mention multiple config sources
        error_text = " ".join(errors)
        assert "config file" in error_text.lower() or "jira.url" in error_text.lower()
        assert "environment" in error_text.lower() or "JIRA_URL" in error_text


class TestConfigPrecedence:
    """Test configuration precedence: CLI > env > .env > config file."""

    def test_full_precedence_chain(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test the full configuration precedence chain."""
        # 1. Config file (lowest priority)
        config_file = tmp_path / ".spectra.yaml"
        config_file.write_text(
            dedent(
                """
            jira:
              url: https://file.atlassian.net
              email: file@example.com
              api_token: file-token
              project: FILE-PROJ

            sync:
              verbose: false
        """
            )
        )

        monkeypatch.chdir(tmp_path)

        # 2. .env file
        env_file = tmp_path / ".env"
        env_file.write_text(
            dedent(
                """
            JIRA_URL=https://dotenv.atlassian.net
            JIRA_EMAIL=dotenv@example.com
        """
            )
        )

        # 3. Environment variables
        monkeypatch.setenv("JIRA_URL", "https://env.atlassian.net")

        # 4. CLI overrides (highest priority)
        provider = EnvironmentConfigProvider(
            config_file=config_file,
            cli_overrides={"verbose": True},
        )
        config = provider.load()

        # Verify precedence:
        # - URL: env var wins over .env and file
        assert config.tracker.url == "https://env.atlassian.net"
        # - Email: .env wins over file (no env var or CLI)
        assert config.tracker.email == "dotenv@example.com"
        # - Token: file wins (no higher-priority source)
        assert config.tracker.api_token == "file-token"
        # - Project: file wins (no higher-priority source)
        assert config.tracker.project_key == "FILE-PROJ"
        # - Verbose: CLI wins
        assert config.sync.verbose is True


class TestValidationConfig:
    """Tests for ValidationConfig loading and defaults with nested structure."""

    def test_default_validation_config(self, tmp_path: Path) -> None:
        """Test default validation config values."""
        config_file = tmp_path / ".spectra.yaml"
        config_file.write_text(
            dedent(
                """
            jira:
              url: https://example.atlassian.net
              email: user@example.com
              api_token: secret-token
        """
            )
        )

        provider = FileConfigProvider(config_path=config_file)
        config = provider.load()

        # Check defaults using new nested structure
        assert config.validation.issue_types.allowed == ["Story", "User Story"]
        assert config.validation.issue_types.default == "User Story"
        assert config.validation.naming.allowed_id_prefixes == []
        assert config.validation.behavior.strict is False
        assert config.validation.estimation.min_story_points == 0
        assert config.validation.estimation.max_story_points == 0
        assert config.validation.content.require_description is False
        assert config.validation.subtasks.require_subtasks is False

        # Check backward compatible accessors
        assert config.validation.allowed_issue_types == ["Story", "User Story"]
        assert config.validation.default_issue_type == "User Story"
        assert config.validation.strict is False

    def test_load_validation_config_yaml(self, tmp_path: Path) -> None:
        """Test loading validation config from YAML with nested structure."""
        config_file = tmp_path / ".spectra.yaml"
        config_file.write_text(
            dedent(
                """
            jira:
              url: https://example.atlassian.net
              email: user@example.com
              api_token: secret-token

            validation:
              issue_types:
                allowed:
                  - "User Story"
                  - "Bug"
                default: "User Story"
              naming:
                allowed_id_prefixes:
                  - "US"
                  - "BUG"
              estimation:
                require_story_points: true
                min_story_points: 1
                max_story_points: 21
                fibonacci_only: true
              content:
                require_description: true
                require_acceptance_criteria: true
              behavior:
                strict: true
        """
            )
        )

        provider = FileConfigProvider(config_path=config_file)
        config = provider.load()

        # Check nested structure
        assert config.validation.issue_types.allowed == ["User Story", "Bug"]
        assert config.validation.issue_types.default == "User Story"
        assert config.validation.naming.allowed_id_prefixes == ["US", "BUG"]
        assert config.validation.behavior.strict is True
        assert config.validation.estimation.require_story_points is True
        assert config.validation.estimation.min_story_points == 1
        assert config.validation.estimation.max_story_points == 21
        assert config.validation.estimation.fibonacci_only is True
        assert config.validation.content.require_description is True
        assert config.validation.content.require_acceptance_criteria is True

    def test_load_validation_config_toml(self, tmp_path: Path) -> None:
        """Test loading validation config from TOML with nested structure."""
        config_file = tmp_path / ".spectra.toml"
        config_file.write_text(
            dedent(
                """
            [jira]
            url = "https://example.atlassian.net"
            email = "user@example.com"
            api_token = "secret-token"

            [validation.issue_types]
            allowed = ["Story"]
            default = "Story"

            [validation.naming]
            allowed_id_prefixes = ["PROJ"]

            [validation.estimation]
            max_story_points = 13

            [validation.behavior]
            strict = false
        """
            )
        )

        provider = FileConfigProvider(config_path=config_file)
        config = provider.load()

        assert config.validation.issue_types.allowed == ["Story"]
        assert config.validation.issue_types.default == "Story"
        assert config.validation.naming.allowed_id_prefixes == ["PROJ"]
        assert config.validation.behavior.strict is False
        assert config.validation.estimation.max_story_points == 13

    def test_validation_config_single_issue_type(self, tmp_path: Path) -> None:
        """Test validation config with single allowed issue type (guards against 'Story' vs 'User Story')."""
        config_file = tmp_path / ".spectra.yaml"
        config_file.write_text(
            dedent(
                """
            jira:
              url: https://example.atlassian.net
              email: user@example.com
              api_token: secret-token

            validation:
              issue_types:
                # Guard: Only allow "User Story", reject "Story"
                allowed:
                  - "User Story"
                default: "User Story"
        """
            )
        )

        provider = FileConfigProvider(config_path=config_file)
        config = provider.load()

        assert config.validation.issue_types.allowed == ["User Story"]
        assert "Story" not in config.validation.issue_types.allowed
        assert "User Story" in config.validation.issue_types.allowed

    def test_validation_config_via_environment_provider(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test validation config loads through EnvironmentConfigProvider."""
        config_file = tmp_path / ".spectra.yaml"
        config_file.write_text(
            dedent(
                """
            jira:
              url: https://example.atlassian.net
              email: user@example.com
              api_token: secret-token

            validation:
              issue_types:
                allowed:
                  - "Task"
                  - "Bug"
                default: "Task"
              behavior:
                strict: true
        """
            )
        )

        monkeypatch.setenv("JIRA_URL", "https://env.atlassian.net")
        monkeypatch.setenv("JIRA_EMAIL", "env@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "env-token")

        provider = EnvironmentConfigProvider(config_file=config_file)
        config = provider.load()

        # Validation config should be loaded from file
        assert config.validation.issue_types.allowed == ["Task", "Bug"]
        assert config.validation.issue_types.default == "Task"
        assert config.validation.behavior.strict is True

    def test_validation_config_labels_and_components(self, tmp_path: Path) -> None:
        """Test loading labels and components config."""
        config_file = tmp_path / ".spectra.yaml"
        config_file.write_text(
            dedent(
                """
            jira:
              url: https://example.atlassian.net
              email: user@example.com
              api_token: secret-token

            validation:
              labels:
                required:
                  - "team:backend"
                allowed:
                  - "team:backend"
                  - "team:frontend"
                  - "priority:high"
                max_labels: 5
              components:
                required:
                  - "API"
                require_component: true
        """
            )
        )

        provider = FileConfigProvider(config_path=config_file)
        config = provider.load()

        assert config.validation.labels.required == ["team:backend"]
        assert "team:frontend" in config.validation.labels.allowed
        assert config.validation.labels.max_labels == 5
        assert config.validation.components.required == ["API"]
        assert config.validation.components.require_component is True

    def test_validation_config_epic_constraints(self, tmp_path: Path) -> None:
        """Test loading epic-level constraints."""
        config_file = tmp_path / ".spectra.yaml"
        config_file.write_text(
            dedent(
                """
            jira:
              url: https://example.atlassian.net
              email: user@example.com
              api_token: secret-token

            validation:
              epic:
                max_stories: 50
                min_stories: 1
                require_summary: true
                max_total_story_points: 200
        """
            )
        )

        provider = FileConfigProvider(config_path=config_file)
        config = provider.load()

        assert config.validation.epic.max_stories == 50
        assert config.validation.epic.min_stories == 1
        assert config.validation.epic.require_summary is True
        assert config.validation.epic.max_total_story_points == 200

    def test_validation_config_subtasks(self, tmp_path: Path) -> None:
        """Test loading subtask constraints."""
        config_file = tmp_path / ".spectra.yaml"
        config_file.write_text(
            dedent(
                """
            jira:
              url: https://example.atlassian.net
              email: user@example.com
              api_token: secret-token

            validation:
              subtasks:
                require_subtasks: true
                min_subtasks: 1
                max_subtasks: 10
                require_subtask_estimates: true
        """
            )
        )

        provider = FileConfigProvider(config_path=config_file)
        config = provider.load()

        assert config.validation.subtasks.require_subtasks is True
        assert config.validation.subtasks.min_subtasks == 1
        assert config.validation.subtasks.max_subtasks == 10
        assert config.validation.subtasks.require_subtask_estimates is True

    def test_validation_config_workflow(self, tmp_path: Path) -> None:
        """Test loading workflow configuration."""
        config_file = tmp_path / ".spectra.yaml"
        config_file.write_text(
            dedent(
                """
            jira:
              url: https://example.atlassian.net
              email: user@example.com
              api_token: secret-token

            validation:
              workflow:
                definition_of_done:
                  - "Code reviewed"
                  - "Tests passing"
                require_review: true
                require_epic_link: true
                max_blocked_days: 7
        """
            )
        )

        provider = FileConfigProvider(config_path=config_file)
        config = provider.load()

        assert config.validation.workflow.definition_of_done == ["Code reviewed", "Tests passing"]
        assert config.validation.workflow.require_review is True
        assert config.validation.workflow.require_epic_link is True
        assert config.validation.workflow.max_blocked_days == 7

    def test_validation_config_scheduling(self, tmp_path: Path) -> None:
        """Test loading scheduling configuration."""
        config_file = tmp_path / ".spectra.yaml"
        config_file.write_text(
            dedent(
                """
            jira:
              url: https://example.atlassian.net
              email: user@example.com
              api_token: secret-token

            validation:
              scheduling:
                stale_after_days: 14
                sla_days: 30
                warn_approaching_sla_days: 7
                work_days_only: true
        """
            )
        )

        provider = FileConfigProvider(config_path=config_file)
        config = provider.load()

        assert config.validation.scheduling.stale_after_days == 14
        assert config.validation.scheduling.sla_days == 30
        assert config.validation.scheduling.warn_approaching_sla_days == 7
        assert config.validation.scheduling.work_days_only is True

    def test_validation_config_development(self, tmp_path: Path) -> None:
        """Test loading development workflow configuration."""
        config_file = tmp_path / ".spectra.yaml"
        config_file.write_text(
            dedent(
                """
            jira:
              url: https://example.atlassian.net
              email: user@example.com
              api_token: secret-token

            validation:
              development:
                branch_naming_pattern: "feature|bugfix"
                require_pr_link: true
                allowed_branch_prefixes:
                  - "feature/"
                  - "bugfix/"
                require_merge_before_done: true
        """
            )
        )

        provider = FileConfigProvider(config_path=config_file)
        config = provider.load()

        assert "feature" in config.validation.development.branch_naming_pattern
        assert config.validation.development.require_pr_link is True
        assert "feature/" in config.validation.development.allowed_branch_prefixes
        assert config.validation.development.require_merge_before_done is True

    def test_validation_config_quality(self, tmp_path: Path) -> None:
        """Test loading quality requirements configuration."""
        config_file = tmp_path / ".spectra.yaml"
        config_file.write_text(
            dedent(
                """
            jira:
              url: https://example.atlassian.net
              email: user@example.com
              api_token: secret-token

            validation:
              quality:
                require_test_cases: true
                min_test_cases: 2
                require_reproduction_steps: true
                bug_severity_levels:
                  - "Critical"
                  - "Major"
                  - "Minor"
        """
            )
        )

        provider = FileConfigProvider(config_path=config_file)
        config = provider.load()

        assert config.validation.quality.require_test_cases is True
        assert config.validation.quality.min_test_cases == 2
        assert config.validation.quality.require_reproduction_steps is True
        assert "Critical" in config.validation.quality.bug_severity_levels

    def test_validation_config_security(self, tmp_path: Path) -> None:
        """Test loading security configuration."""
        config_file = tmp_path / ".spectra.yaml"
        config_file.write_text(
            dedent(
                """
            jira:
              url: https://example.atlassian.net
              email: user@example.com
              api_token: secret-token

            validation:
              security:
                require_security_review: true
                confidentiality_levels:
                  - "public"
                  - "internal"
                  - "confidential"
                compliance_tags:
                  - "GDPR"
                  - "SOC2"
        """
            )
        )

        provider = FileConfigProvider(config_path=config_file)
        config = provider.load()

        assert config.validation.security.require_security_review is True
        assert "internal" in config.validation.security.confidentiality_levels
        assert "GDPR" in config.validation.security.compliance_tags

    def test_validation_config_capacity(self, tmp_path: Path) -> None:
        """Test loading capacity management configuration."""
        config_file = tmp_path / ".spectra.yaml"
        config_file.write_text(
            dedent(
                """
            jira:
              url: https://example.atlassian.net
              email: user@example.com
              api_token: secret-token

            validation:
              capacity:
                max_stories_per_assignee: 5
                max_points_per_sprint: 40
                max_parallel_stories: 3
                points_per_day: 2.5
        """
            )
        )

        provider = FileConfigProvider(config_path=config_file)
        config = provider.load()

        assert config.validation.capacity.max_stories_per_assignee == 5
        assert config.validation.capacity.max_points_per_sprint == 40
        assert config.validation.capacity.max_parallel_stories == 3
        assert config.validation.capacity.points_per_day == 2.5

    def test_validation_config_environments(self, tmp_path: Path) -> None:
        """Test loading environments configuration."""
        config_file = tmp_path / ".spectra.yaml"
        config_file.write_text(
            dedent(
                """
            jira:
              url: https://example.atlassian.net
              email: user@example.com
              api_token: secret-token

            validation:
              environments:
                allowed_environments:
                  - "development"
                  - "staging"
                  - "production"
                environment_order:
                  - "development"
                  - "staging"
                  - "production"
                production_approval_required: true
        """
            )
        )

        provider = FileConfigProvider(config_path=config_file)
        config = provider.load()

        assert "staging" in config.validation.environments.allowed_environments
        assert config.validation.environments.environment_order == [
            "development",
            "staging",
            "production",
        ]
        assert config.validation.environments.production_approval_required is True

    def test_validation_config_defaults_for_extended_sections(self, tmp_path: Path) -> None:
        """Test that extended validation sections have sensible defaults."""
        config_file = tmp_path / ".spectra.yaml"
        config_file.write_text(
            dedent(
                """
            jira:
              url: https://example.atlassian.net
              email: user@example.com
              api_token: secret-token
        """
            )
        )

        provider = FileConfigProvider(config_path=config_file)
        config = provider.load()

        # Workflow defaults
        assert config.validation.workflow.definition_of_done == []
        assert config.validation.workflow.require_review is False

        # Scheduling defaults
        assert config.validation.scheduling.stale_after_days == 0
        assert config.validation.scheduling.sla_days == 0

        # Development defaults
        assert config.validation.development.branch_naming_pattern == ""
        assert config.validation.development.require_pr_link is False

        # Quality defaults
        assert config.validation.quality.require_test_cases is False
        assert config.validation.quality.min_test_cases == 0

        # Security defaults
        assert config.validation.security.require_security_review is False
        assert config.validation.security.compliance_tags == []

        # Capacity defaults
        assert config.validation.capacity.max_stories_per_assignee == 0
        assert config.validation.capacity.points_per_day == 0.0

        # Environments defaults
        assert config.validation.environments.allowed_environments == []
        assert config.validation.environments.production_approval_required is False
