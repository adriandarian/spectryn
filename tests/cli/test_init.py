"""
Tests for the init wizard.

Tests the first-time setup wizard functionality.
"""

from unittest.mock import patch

import pytest

from spectryn.cli.exit_codes import ExitCode
from spectryn.cli.init import (
    ConfigFormat,
    InitConfig,
    InitWizard,
    run_init,
)
from spectryn.cli.output import Console


# =============================================================================
# InitConfig Tests
# =============================================================================


class TestInitConfig:
    """Tests for InitConfig dataclass."""

    def test_default_values(self):
        """Test InitConfig has sensible defaults."""
        config = InitConfig()

        assert config.jira_url == ""
        assert config.jira_email == ""
        assert config.jira_api_token == ""
        assert config.project_key == ""
        assert config.config_format == ConfigFormat.ENV
        assert config.create_sample is False
        assert config.sample_path == "EPIC.md"

    def test_custom_values(self):
        """Test InitConfig with custom values."""
        config = InitConfig(
            jira_url="https://example.atlassian.net",
            jira_email="test@example.com",
            jira_api_token="secret",
            project_key="PROJ",
            config_format=ConfigFormat.YAML,
            create_sample=True,
            sample_path="custom.md",
        )

        assert config.jira_url == "https://example.atlassian.net"
        assert config.jira_email == "test@example.com"
        assert config.project_key == "PROJ"
        assert config.config_format == ConfigFormat.YAML


# =============================================================================
# InitWizard Tests
# =============================================================================


class TestInitWizard:
    """Tests for InitWizard class."""

    @pytest.fixture
    def console(self):
        """Create a mock console."""
        return Console(color=False, json_mode=False)

    @pytest.fixture
    def wizard(self, console):
        """Create a wizard instance."""
        return InitWizard(console)

    def test_wizard_initialization(self, wizard):
        """Test wizard initializes with empty config."""
        assert wizard.config.jira_url == ""
        assert wizard.config.jira_email == ""
        assert wizard.config.jira_api_token == ""

    def test_check_existing_config_env_file(self, wizard, tmp_path, monkeypatch):
        """Test detection of existing .env file."""
        # Clear any pre-existing environment variables that might interfere
        monkeypatch.delenv("JIRA_URL", raising=False)
        monkeypatch.delenv("JIRA_EMAIL", raising=False)
        monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
        monkeypatch.chdir(tmp_path)

        # No config file
        assert wizard._check_existing_config() is False

        # Create .env file
        (tmp_path / ".env").write_text("JIRA_URL=https://example.com")
        assert wizard._check_existing_config() is True

    def test_check_existing_config_yaml_file(self, wizard, tmp_path, monkeypatch):
        """Test detection of existing .spectra.yaml file."""
        monkeypatch.chdir(tmp_path)

        # Create yaml config
        (tmp_path / ".spectra.yaml").write_text("jira:\n  url: https://example.com")
        assert wizard._check_existing_config() is True

    def test_check_existing_config_env_vars(self, wizard, tmp_path, monkeypatch):
        """Test detection of environment variables."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("JIRA_URL", "https://example.atlassian.net")

        assert wizard._check_existing_config() is True

    @patch("builtins.input")
    def test_prompt_input(self, mock_input, wizard):
        """Test text input prompt."""
        mock_input.return_value = "https://example.atlassian.net"

        result = wizard._prompt_input("Jira URL: ")

        assert result == "https://example.atlassian.net"

    @patch("builtins.input")
    def test_prompt_input_default(self, mock_input, wizard):
        """Test text input prompt with default."""
        mock_input.return_value = ""

        result = wizard._prompt_input("Value: ", default="default_value")

        assert result == "default_value"

    @patch("builtins.input")
    def test_prompt_yes_no_yes(self, mock_input, wizard):
        """Test yes/no prompt with 'y' response."""
        mock_input.return_value = "y"

        result = wizard._prompt_yes_no("Continue?")

        assert result is True

    @patch("builtins.input")
    def test_prompt_yes_no_no(self, mock_input, wizard):
        """Test yes/no prompt with 'n' response."""
        mock_input.return_value = "n"

        result = wizard._prompt_yes_no("Continue?")

        assert result is False

    @patch("builtins.input")
    def test_prompt_yes_no_default(self, mock_input, wizard):
        """Test yes/no prompt with empty response uses default."""
        mock_input.return_value = ""

        # Default True
        result = wizard._prompt_yes_no("Continue?", default=True)
        assert result is True

        # Default False
        result = wizard._prompt_yes_no("Continue?", default=False)
        assert result is False


# =============================================================================
# Config File Creation Tests
# =============================================================================


class TestConfigFileCreation:
    """Tests for config file creation."""

    @pytest.fixture
    def wizard(self):
        """Create a wizard instance."""
        console = Console(color=False)
        wizard = InitWizard(console)
        wizard.config = InitConfig(
            jira_url="https://example.atlassian.net",
            jira_email="test@example.com",
            jira_api_token="secret_token",
            project_key="PROJ",
        )
        return wizard

    def test_create_env_file(self, wizard, tmp_path, monkeypatch):
        """Test .env file creation."""
        monkeypatch.chdir(tmp_path)
        wizard.config.config_format = ConfigFormat.ENV

        wizard._create_env_file()

        env_file = tmp_path / ".env"
        assert env_file.exists()

        content = env_file.read_text()
        assert "JIRA_URL=https://example.atlassian.net" in content
        assert "JIRA_EMAIL=test@example.com" in content
        assert "JIRA_API_TOKEN=secret_token" in content
        assert "JIRA_PROJECT=PROJ" in content

    def test_create_yaml_file(self, wizard, tmp_path, monkeypatch):
        """Test .spectra.yaml file creation."""
        monkeypatch.chdir(tmp_path)
        wizard.config.config_format = ConfigFormat.YAML

        wizard._create_yaml_file()

        yaml_file = tmp_path / ".spectra.yaml"
        assert yaml_file.exists()

        content = yaml_file.read_text()
        assert "url: https://example.atlassian.net" in content
        assert "email: test@example.com" in content
        assert "api_token: secret_token" in content
        assert "project: PROJ" in content

    def test_create_toml_file(self, wizard, tmp_path, monkeypatch):
        """Test .spectra.toml file creation."""
        monkeypatch.chdir(tmp_path)
        wizard.config.config_format = ConfigFormat.TOML

        wizard._create_toml_file()

        toml_file = tmp_path / ".spectra.toml"
        assert toml_file.exists()

        content = toml_file.read_text()
        assert 'url = "https://example.atlassian.net"' in content
        assert 'email = "test@example.com"' in content
        assert 'api_token = "secret_token"' in content
        assert 'project = "PROJ"' in content

    def test_add_to_gitignore(self, wizard, tmp_path, monkeypatch):
        """Test adding config file to .gitignore."""
        monkeypatch.chdir(tmp_path)

        # Create .gitignore
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("node_modules/\n")

        wizard._add_to_gitignore(".env")

        content = gitignore.read_text()
        assert ".env" in content
        assert "spectra configuration" in content

    def test_add_to_gitignore_already_exists(self, wizard, tmp_path, monkeypatch):
        """Test not duplicating entry in .gitignore."""
        monkeypatch.chdir(tmp_path)

        # Create .gitignore with .env already present
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text(".env\n")

        wizard._add_to_gitignore(".env")

        content = gitignore.read_text()
        # Should only appear once
        assert content.count(".env") == 1


# =============================================================================
# Sample Markdown Tests
# =============================================================================


class TestSampleMarkdown:
    """Tests for sample markdown creation."""

    @pytest.fixture
    def wizard(self):
        """Create a wizard instance."""
        console = Console(color=False)
        wizard = InitWizard(console)
        wizard.config = InitConfig(project_key="PROJ")
        return wizard

    def test_sample_markdown_content(self, wizard):
        """Test sample markdown has expected content."""
        sample = wizard.SAMPLE_MARKDOWN.format(project_key="PROJ")

        assert "# Epic: PROJ-XXX" in sample
        assert "## Stories" in sample
        assert "### STORY-001:" in sample
        assert "#### Subtasks" in sample
        assert "- [ ]" in sample

    @patch("builtins.input")
    def test_create_sample_markdown(self, mock_input, wizard, tmp_path, monkeypatch):
        """Test sample markdown file creation."""
        monkeypatch.chdir(tmp_path)
        mock_input.return_value = "EPIC.md"

        wizard._create_sample_markdown()

        sample_file = tmp_path / "EPIC.md"
        assert sample_file.exists()

        content = sample_file.read_text()
        assert "# Epic: PROJ-XXX" in content


# =============================================================================
# Full Wizard Flow Tests
# =============================================================================


class TestWizardFlow:
    """Tests for complete wizard flow."""

    @patch("builtins.input")
    @patch("getpass.getpass")
    @patch.object(InitWizard, "_test_connection")
    def test_full_wizard_flow(
        self,
        mock_test_conn,
        mock_getpass,
        mock_input,
        tmp_path,
        monkeypatch,
    ):
        """Test complete wizard flow."""
        # Clear any pre-existing environment variables that might interfere
        monkeypatch.delenv("JIRA_URL", raising=False)
        monkeypatch.delenv("JIRA_EMAIL", raising=False)
        monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
        monkeypatch.chdir(tmp_path)

        # Mock connection test to succeed
        mock_test_conn.return_value = True

        # Mock user inputs
        mock_input.side_effect = [
            "https://example.atlassian.net",  # URL
            "test@example.com",  # Email
            "1",  # Config format (env)
            "PROJ",  # Project key
            "n",  # Don't create sample
        ]
        mock_getpass.return_value = "secret_token"

        console = Console(color=False)
        wizard = InitWizard(console)

        result = wizard.run()

        assert result is True
        assert (tmp_path / ".env").exists()

    @patch("builtins.input")
    @patch("getpass.getpass")
    def test_wizard_cancelled_on_overwrite_decline(
        self,
        mock_getpass,
        mock_input,
        tmp_path,
        monkeypatch,
    ):
        """Test wizard exits if user declines overwrite."""
        monkeypatch.chdir(tmp_path)

        # Create existing config
        (tmp_path / ".env").write_text("JIRA_URL=existing")

        # Decline overwrite
        mock_input.return_value = "n"

        console = Console(color=False)
        wizard = InitWizard(console)

        result = wizard.run()

        assert result is False


# =============================================================================
# run_init Function Tests
# =============================================================================


class TestRunInit:
    """Tests for run_init function."""

    @patch.object(InitWizard, "run")
    def test_run_init_success(self, mock_run):
        """Test run_init returns success on wizard success."""
        mock_run.return_value = True
        console = Console(color=False)

        result = run_init(console)

        assert result == ExitCode.SUCCESS

    @patch.object(InitWizard, "run")
    def test_run_init_cancelled(self, mock_run):
        """Test run_init returns cancelled on wizard failure."""
        mock_run.return_value = False
        console = Console(color=False)

        result = run_init(console)

        assert result == ExitCode.CANCELLED

    @patch.object(InitWizard, "run")
    def test_run_init_keyboard_interrupt(self, mock_run, capsys):
        """Test run_init handles keyboard interrupt."""
        mock_run.side_effect = KeyboardInterrupt()
        console = Console(color=False)

        result = run_init(console)

        assert result == ExitCode.SIGINT


# =============================================================================
# CLI Integration Tests
# =============================================================================


class TestCLIIntegration:
    """Tests for CLI integration."""

    def test_init_flag_in_parser(self, cli_parser):
        """Test --init flag is recognized by parser."""
        args = cli_parser.parse_args(["--init"])

        assert args.init is True

    def test_init_flag_standalone(self, cli_parser):
        """Test --init can be used without other arguments."""
        # Should not raise - init doesn't require markdown/epic
        args = cli_parser.parse_args(["--init"])

        assert args.init is True
        assert args.input is None
        assert args.epic is None
