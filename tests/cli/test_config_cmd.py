"""Tests for Config Command - Validate and manage configuration."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from spectryn.cli.config_cmd import (
    ConfigValidationResult,
    find_config_files,
    format_validation_result,
    run_config_validate,
    validate_config_file,
)
from spectryn.cli.exit_codes import ExitCode
from spectryn.cli.output import Console


class TestConfigValidationResult:
    """Tests for ConfigValidationResult dataclass."""

    def test_default_values(self):
        """Test default values."""
        result = ConfigValidationResult()
        assert result.valid is True
        assert result.config_file is None
        assert result.errors == []
        assert result.warnings == []
        assert result.info == []

    def test_with_errors(self):
        """Test result with errors."""
        result = ConfigValidationResult(
            valid=False,
            errors=["Missing field"],
        )
        assert result.valid is False
        assert len(result.errors) == 1


class TestFindConfigFiles:
    """Tests for find_config_files function."""

    def test_finds_yaml_config(self, tmp_path: Path, monkeypatch):
        """Test finding .spectra.yaml config."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".spectra.yaml").write_text("jira:\n  url: https://test.com")

        files = find_config_files()
        assert len(files) == 1
        assert files[0].name == ".spectra.yaml"

    def test_finds_multiple_configs(self, tmp_path: Path, monkeypatch):
        """Test finding multiple config files."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".spectra.yaml").write_text("jira: {}")
        (tmp_path / ".env").write_text("JIRA_URL=test")

        files = find_config_files()
        assert len(files) == 2

    def test_returns_empty_when_no_configs(self, tmp_path: Path, monkeypatch):
        """Test returns empty list when no configs."""
        monkeypatch.chdir(tmp_path)

        files = find_config_files()
        assert files == []

    def test_finds_pyproject_toml(self, tmp_path: Path, monkeypatch):
        """Test finding pyproject.toml."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pyproject.toml").write_text("[tool.spectra]\njira.url = 'https://test.com'")

        files = find_config_files()
        assert any(f.name == "pyproject.toml" for f in files)


class TestValidateConfigFile:
    """Tests for validate_config_file function."""

    def test_validate_nonexistent_file(self, tmp_path: Path):
        """Test validating nonexistent file."""
        result = validate_config_file(tmp_path / "nonexistent.yaml")
        assert result.valid is False
        assert any("not found" in e for e in result.errors)

    def test_validate_valid_yaml(self, tmp_path: Path):
        """Test validating valid YAML config."""
        config_file = tmp_path / ".spectra.yaml"
        config_file.write_text(
            """
jira:
  url: https://company.atlassian.net
  email: user@example.com
  api_token: secret123
  project: PROJ
"""
        )

        result = validate_config_file(config_file)
        assert result.valid is True
        assert len(result.errors) == 0

    def test_validate_yaml_missing_required(self, tmp_path: Path):
        """Test validating YAML with missing required fields."""
        config_file = tmp_path / ".spectra.yaml"
        config_file.write_text(
            """
jira:
  email: user@example.com
"""
        )

        result = validate_config_file(config_file)
        assert result.valid is False
        assert any("url" in e.lower() for e in result.errors)

    def test_validate_yaml_invalid_url(self, tmp_path: Path):
        """Test validating YAML with invalid URL."""
        config_file = tmp_path / ".spectra.yaml"
        config_file.write_text(
            """
jira:
  url: company.atlassian.net
  api_token: secret123
"""
        )

        result = validate_config_file(config_file)
        assert any("http" in w.lower() for w in result.warnings)

    def test_validate_empty_yaml(self, tmp_path: Path):
        """Test validating empty YAML config."""
        config_file = tmp_path / ".spectra.yaml"
        config_file.write_text("")

        result = validate_config_file(config_file)
        assert any("empty" in w.lower() for w in result.warnings)

    def test_validate_env_file(self, tmp_path: Path):
        """Test validating .env file."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            """
JIRA_URL=https://company.atlassian.net
JIRA_API_TOKEN=secret123
JIRA_EMAIL=user@example.com
"""
        )

        result = validate_config_file(env_file)
        assert result.valid is True

    def test_validate_env_file_missing_required(self, tmp_path: Path):
        """Test validating .env with missing required vars."""
        env_file = tmp_path / ".env"
        env_file.write_text("JIRA_EMAIL=user@example.com")

        result = validate_config_file(env_file)
        assert result.valid is False
        assert any("JIRA_URL" in e for e in result.errors)
        assert any("JIRA_API_TOKEN" in e for e in result.errors)

    def test_validate_env_file_invalid_url(self, tmp_path: Path):
        """Test validating .env with invalid URL."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            """
JIRA_URL=company.atlassian.net
JIRA_API_TOKEN=secret
"""
        )

        result = validate_config_file(env_file)
        assert any("http" in w.lower() for w in result.warnings)

    def test_validate_json_config(self, tmp_path: Path):
        """Test validating JSON config."""
        config_file = tmp_path / "spectryn.config.json"
        config_file.write_text(
            """
{
  "jira": {
    "url": "https://company.atlassian.net",
    "api_token": "secret123"
  }
}
"""
        )

        result = validate_config_file(config_file)
        assert result.valid is True

    def test_validate_invalid_yaml_syntax(self, tmp_path: Path):
        """Test validating YAML with syntax error."""
        config_file = tmp_path / ".spectra.yaml"
        config_file.write_text("invalid: yaml: content: [")

        result = validate_config_file(config_file)
        assert result.valid is False
        assert any("parse" in e.lower() for e in result.errors)

    def test_validate_pyproject_toml_with_spectra_section(self, tmp_path: Path):
        """Test validating pyproject.toml with spectra section."""
        config_file = tmp_path / "pyproject.toml"
        config_file.write_text(
            """
[tool.spectra.jira]
url = "https://company.atlassian.net"
api_token = "secret123"
"""
        )

        result = validate_config_file(config_file)
        assert result.valid is True

    def test_validate_pyproject_toml_without_spectra_section(self, tmp_path: Path):
        """Test validating pyproject.toml without spectra section."""
        config_file = tmp_path / "pyproject.toml"
        config_file.write_text(
            """
[tool.pytest]
python_files = "test_*.py"
"""
        )

        result = validate_config_file(config_file)
        assert any("No [tool.spectra]" in i for i in result.info)

    def test_validate_with_dry_run_info(self, tmp_path: Path):
        """Test validation shows info about dry_run setting."""
        config_file = tmp_path / ".spectra.yaml"
        config_file.write_text(
            """
jira:
  url: https://company.atlassian.net
  api_token: secret123
sync:
  dry_run: true
"""
        )

        result = validate_config_file(config_file)
        assert any("dry_run" in i for i in result.info)


class TestFormatValidationResult:
    """Tests for format_validation_result function."""

    def test_format_valid_result(self):
        """Test formatting a valid result."""
        result = ConfigValidationResult(
            valid=True,
            config_file=".spectra.yaml",
        )

        formatted = format_validation_result(result, color=False)
        assert ".spectra.yaml" in formatted
        assert "Valid" in formatted

    def test_format_invalid_result(self):
        """Test formatting an invalid result."""
        result = ConfigValidationResult(
            valid=False,
            config_file=".spectra.yaml",
            errors=["Missing URL"],
        )

        formatted = format_validation_result(result, color=False)
        assert "Invalid" in formatted
        assert "Missing URL" in formatted

    def test_format_with_warnings(self):
        """Test formatting with warnings."""
        result = ConfigValidationResult(
            valid=True,
            config_file=".spectra.yaml",
            warnings=["Consider setting project"],
        )

        formatted = format_validation_result(result, color=False)
        assert "Consider setting project" in formatted
        assert "⚠" in formatted

    def test_format_with_info(self):
        """Test formatting with info messages."""
        result = ConfigValidationResult(
            valid=True,
            config_file=".spectra.yaml",
            info=["dry_run enabled"],
        )

        formatted = format_validation_result(result, color=False)
        assert "dry_run enabled" in formatted
        assert "ℹ" in formatted


class TestRunConfigValidate:
    """Tests for run_config_validate command."""

    def test_validate_specific_file(self, tmp_path: Path):
        """Test validating a specific file."""
        config_file = tmp_path / ".spectra.yaml"
        config_file.write_text(
            """
jira:
  url: https://company.atlassian.net
  api_token: secret123
"""
        )

        console = MagicMock(spec=Console)
        console.color = False

        result = run_config_validate(console, config_file=str(config_file))
        assert result == ExitCode.SUCCESS

    def test_validate_file_not_found(self):
        """Test error when file not found."""
        console = MagicMock(spec=Console)

        result = run_config_validate(console, config_file="/nonexistent/file.yaml")

        assert result == ExitCode.FILE_NOT_FOUND
        console.error.assert_called()

    def test_validate_no_config_files_no_env(self, tmp_path: Path, monkeypatch):
        """Test when no config files and no environment vars."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("JIRA_URL", raising=False)
        monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
        monkeypatch.delenv("JIRA_EMAIL", raising=False)

        console = MagicMock(spec=Console)

        result = run_config_validate(console)

        assert result == ExitCode.CONFIG_ERROR
        console.warning.assert_called()

    def test_validate_no_config_files_with_env(self, tmp_path: Path, monkeypatch):
        """Test when no config files but environment vars exist."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("JIRA_URL", "https://test.atlassian.net")
        monkeypatch.setenv("JIRA_API_TOKEN", "secret")

        console = MagicMock(spec=Console)

        result = run_config_validate(console)

        assert result == ExitCode.SUCCESS

    def test_validate_multiple_files(self, tmp_path: Path, monkeypatch):
        """Test validating multiple config files."""
        monkeypatch.chdir(tmp_path)

        (tmp_path / ".spectra.yaml").write_text(
            """
jira:
  url: https://company.atlassian.net
  api_token: secret123
"""
        )
        (tmp_path / ".env").write_text(
            """
JIRA_URL=https://company.atlassian.net
JIRA_API_TOKEN=secret123
"""
        )

        console = MagicMock(spec=Console)
        console.color = False

        result = run_config_validate(console)
        assert result == ExitCode.SUCCESS

    def test_validate_with_invalid_config(self, tmp_path: Path, monkeypatch):
        """Test validation fails with invalid config."""
        monkeypatch.chdir(tmp_path)

        (tmp_path / ".spectra.yaml").write_text(
            """
jira:
  email: user@example.com
"""
        )

        console = MagicMock(spec=Console)
        console.color = False

        result = run_config_validate(console)
        assert result == ExitCode.CONFIG_ERROR

    def test_validate_with_test_connection(self, tmp_path: Path):
        """Test validation with connection test."""
        config_file = tmp_path / ".spectra.yaml"
        config_file.write_text(
            """
jira:
  url: https://company.atlassian.net
  api_token: secret123
"""
        )

        console = MagicMock(spec=Console)
        console.color = False

        with patch("spectryn.adapters.EnvironmentConfigProvider") as mock_provider:
            with patch("spectryn.adapters.JiraAdapter") as mock_adapter:
                mock_instance = MagicMock()
                mock_instance.test_connection.return_value = True
                mock_instance.get_current_user.return_value = {"displayName": "Test User"}
                mock_adapter.return_value = mock_instance

                mock_config = MagicMock()
                mock_provider.return_value.load.return_value = mock_config

                result = run_config_validate(
                    console,
                    config_file=str(config_file),
                    test_connection=True,
                )

        assert result == ExitCode.SUCCESS
        console.success.assert_called()

    def test_validate_connection_test_fails(self, tmp_path: Path):
        """Test when connection test fails."""
        config_file = tmp_path / ".spectra.yaml"
        config_file.write_text(
            """
jira:
  url: https://company.atlassian.net
  api_token: secret123
"""
        )

        console = MagicMock(spec=Console)
        console.color = False

        with patch("spectryn.adapters.EnvironmentConfigProvider") as mock_provider:
            with patch("spectryn.adapters.JiraAdapter") as mock_adapter:
                mock_adapter.side_effect = Exception("Connection failed")
                mock_provider.return_value.load.return_value = MagicMock()

                result = run_config_validate(
                    console,
                    config_file=str(config_file),
                    test_connection=True,
                )

        assert result == ExitCode.CONFIG_ERROR
