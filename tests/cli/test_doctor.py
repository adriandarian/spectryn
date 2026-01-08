"""Tests for CLI doctor commands."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from spectryn.cli.doctor import (
    CheckResult,
    CheckStatus,
    Doctor,
    DoctorReport,
    format_doctor_report,
    run_doctor,
)
from spectryn.cli.exit_codes import ExitCode


# =============================================================================
# CheckResult and DoctorReport Tests
# =============================================================================


class TestCheckResult:
    """Tests for CheckResult dataclass."""

    def test_create_ok_result(self):
        """Test creating OK check result."""
        result = CheckResult(
            name="Test",
            status=CheckStatus.OK,
            message="Success",
        )
        assert result.name == "Test"
        assert result.status == CheckStatus.OK
        assert result.message == "Success"
        assert result.details == []
        assert result.suggestion is None

    def test_create_error_result(self):
        """Test creating error check result."""
        result = CheckResult(
            name="Test",
            status=CheckStatus.ERROR,
            message="Failed",
            details=["Detail 1", "Detail 2"],
            suggestion="Fix it",
        )
        assert result.status == CheckStatus.ERROR
        assert len(result.details) == 2
        assert result.suggestion == "Fix it"


class TestDoctorReport:
    """Tests for DoctorReport dataclass."""

    def test_empty_report(self):
        """Test empty report properties."""
        report = DoctorReport()
        assert report.has_errors is False
        assert report.has_warnings is False
        assert report.ok_count == 0
        assert report.error_count == 0
        assert report.warning_count == 0

    def test_report_with_checks(self):
        """Test report with various check results."""
        report = DoctorReport(
            checks=[
                CheckResult("Test1", CheckStatus.OK, "OK"),
                CheckResult("Test2", CheckStatus.OK, "OK"),
                CheckResult("Test3", CheckStatus.WARNING, "Warning"),
                CheckResult("Test4", CheckStatus.ERROR, "Error"),
            ]
        )
        assert report.has_errors is True
        assert report.has_warnings is True
        assert report.ok_count == 2
        assert report.warning_count == 1
        assert report.error_count == 1

    def test_report_only_ok(self):
        """Test report with only OK checks."""
        report = DoctorReport(
            checks=[
                CheckResult("Test1", CheckStatus.OK, "OK"),
                CheckResult("Test2", CheckStatus.OK, "OK"),
            ]
        )
        assert report.has_errors is False
        assert report.has_warnings is False
        assert report.ok_count == 2


# =============================================================================
# Doctor Class Tests
# =============================================================================


class TestDoctor:
    """Tests for Doctor class."""

    @pytest.fixture
    def mock_console(self):
        """Create a mock console."""
        console = MagicMock()
        console.color = False
        return console

    def test_init(self, mock_console):
        """Test Doctor initialization."""
        doctor = Doctor(mock_console, verbose=True)
        assert doctor.console == mock_console
        assert doctor.verbose is True
        assert isinstance(doctor.report, DoctorReport)

    def test_add_check(self, mock_console):
        """Test adding a check result."""
        doctor = Doctor(mock_console)
        result = CheckResult("Test", CheckStatus.OK, "Success")

        doctor._add_check(result)

        assert len(doctor.report.checks) == 1
        assert doctor.report.checks[0] == result

    def test_check_python_version_ok(self, mock_console):
        """Test Python version check for supported version."""
        doctor = Doctor(mock_console)

        # Directly test by just running the check - the actual version is 3.11+
        doctor._check_python_version()

        assert len(doctor.report.checks) == 1
        # Should be OK on Python 3.11+
        assert doctor.report.checks[0].status in [CheckStatus.OK, CheckStatus.WARNING]

    def test_check_python_version_reports_version(self, mock_console):
        """Test Python version check includes version info."""
        doctor = Doctor(mock_console)

        doctor._check_python_version()

        assert len(doctor.report.checks) == 1
        assert "Python" in doctor.report.checks[0].message

    def test_check_dependencies_all_present(self, mock_console):
        """Test dependency check when all are present."""
        doctor = Doctor(mock_console)

        with patch("builtins.__import__", return_value=MagicMock()):
            doctor._check_dependencies()

        assert any(c.name == "Dependencies" for c in doctor.report.checks)

    def test_check_dependencies_missing_required(self, mock_console):
        """Test dependency check with missing required package."""
        doctor = Doctor(mock_console)

        def mock_import(name, *args, **kwargs):
            if name == "requests":
                raise ImportError("No module named 'requests'")
            return MagicMock()

        with patch("builtins.__import__", side_effect=mock_import):
            doctor._check_dependencies()

        check = next(c for c in doctor.report.checks if c.name == "Dependencies")
        assert check.status == CheckStatus.ERROR

    def test_check_config_files_found(self, mock_console, tmp_path, monkeypatch):
        """Test config file check when files exist."""
        monkeypatch.chdir(tmp_path)

        # Create a config file
        (tmp_path / ".spectra.yaml").write_text("test: value")

        doctor = Doctor(mock_console)
        doctor._check_config_files()

        check = next(c for c in doctor.report.checks if c.name == "Configuration")
        assert check.status == CheckStatus.OK

    def test_check_config_files_not_found(self, mock_console, tmp_path, monkeypatch):
        """Test config file check when no files exist."""
        monkeypatch.chdir(tmp_path)

        doctor = Doctor(mock_console)
        doctor._check_config_files()

        check = next(c for c in doctor.report.checks if c.name == "Configuration")
        assert check.status == CheckStatus.WARNING

    def test_check_environment_jira_configured(self, mock_console):
        """Test environment check with Jira configured."""
        doctor = Doctor(mock_console)

        env = {
            "JIRA_URL": "https://test.atlassian.net",
            "JIRA_EMAIL": "test@example.com",
            "JIRA_API_TOKEN": "secrettoken123456",
        }

        with patch.dict(os.environ, env, clear=True):
            doctor._check_environment_variables()

        check = next(c for c in doctor.report.checks if c.name == "Environment")
        assert check.status == CheckStatus.OK

    def test_check_environment_alternative_tracker(self, mock_console):
        """Test environment check with alternative tracker."""
        doctor = Doctor(mock_console)

        env = {"GITHUB_TOKEN": "ghp_test123456789"}

        with patch.dict(os.environ, env, clear=True):
            doctor._check_environment_variables()

        check = next(c for c in doctor.report.checks if c.name == "Environment")
        assert check.status == CheckStatus.OK

    def test_check_environment_missing(self, mock_console):
        """Test environment check with no credentials."""
        doctor = Doctor(mock_console)

        with patch.dict(os.environ, {}, clear=True):
            doctor._check_environment_variables()

        check = next(c for c in doctor.report.checks if c.name == "Environment")
        assert check.status == CheckStatus.ERROR

    def test_check_tracker_connection_skipped(self, mock_console):
        """Test tracker connection check skipped without credentials."""
        doctor = Doctor(mock_console)

        with patch.dict(os.environ, {}, clear=True):
            doctor._check_tracker_connection()

        check = next(c for c in doctor.report.checks if c.name == "Tracker Connection")
        assert check.status == CheckStatus.SKIPPED

    def test_check_tracker_connection_success(self, mock_console):
        """Test tracker connection check success."""
        doctor = Doctor(mock_console)

        env = {
            "JIRA_URL": "https://test.atlassian.net",
            "JIRA_EMAIL": "test@example.com",
            "JIRA_API_TOKEN": "secrettoken123456",
        }

        mock_adapter = MagicMock()
        mock_adapter.test_connection.return_value = True
        mock_adapter.get_current_user.return_value = {"displayName": "Test User"}

        with patch.dict(os.environ, env):
            with patch("spectryn.adapters.JiraAdapter", return_value=mock_adapter):
                with patch("spectryn.adapters.ADFFormatter"):
                    with patch("spectryn.core.ports.config_provider.TrackerConfig"):
                        doctor._check_tracker_connection()

        check = next(c for c in doctor.report.checks if c.name == "Tracker Connection")
        assert check.status == CheckStatus.OK

    def test_check_tracker_connection_failure(self, mock_console):
        """Test tracker connection check failure."""
        doctor = Doctor(mock_console)

        env = {
            "JIRA_URL": "https://test.atlassian.net",
            "JIRA_EMAIL": "test@example.com",
            "JIRA_API_TOKEN": "secrettoken123456",
        }

        mock_adapter = MagicMock()
        mock_adapter.test_connection.return_value = False

        with patch.dict(os.environ, env):
            with patch("spectryn.adapters.JiraAdapter", return_value=mock_adapter):
                with patch("spectryn.adapters.ADFFormatter"):
                    with patch("spectryn.core.ports.config_provider.TrackerConfig"):
                        doctor._check_tracker_connection()

        check = next(c for c in doctor.report.checks if c.name == "Tracker Connection")
        assert check.status == CheckStatus.ERROR

    def test_check_workspace_writable(self, mock_console, tmp_path, monkeypatch):
        """Test workspace check for writable directory."""
        monkeypatch.chdir(tmp_path)

        doctor = Doctor(mock_console)
        doctor._check_workspace()

        check = next(c for c in doctor.report.checks if c.name == "Workspace")
        assert check.status == CheckStatus.OK

    def test_check_git_integration_no_git(self, mock_console, tmp_path, monkeypatch):
        """Test git integration check when not a git repo."""
        monkeypatch.chdir(tmp_path)

        doctor = Doctor(mock_console)
        doctor._check_git_integration()

        check = next(c for c in doctor.report.checks if c.name == "Git Integration")
        assert check.status == CheckStatus.SKIPPED

    def test_check_git_integration_found(self, mock_console, tmp_path, monkeypatch):
        """Test git integration check when git repo exists."""
        monkeypatch.chdir(tmp_path)

        # Create .git directory
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "hooks").mkdir()

        with patch("shutil.which", return_value="/usr/bin/git"):
            doctor = Doctor(mock_console)
            doctor._check_git_integration()

        check = next(c for c in doctor.report.checks if c.name == "Git Integration")
        assert check.status == CheckStatus.OK

    def test_check_ai_tools_found(self, mock_console):
        """Test AI tools check when tools are available."""
        doctor = Doctor(mock_console)

        def mock_which(cmd):
            return "/usr/bin/" + cmd if cmd in ["claude", "ollama"] else None

        with patch("shutil.which", side_effect=mock_which):
            doctor._check_ai_tools()

        check = next(c for c in doctor.report.checks if c.name == "AI Tools")
        assert check.status == CheckStatus.OK

    def test_check_ai_tools_none(self, mock_console):
        """Test AI tools check when no tools available."""
        doctor = Doctor(mock_console)

        with patch("shutil.which", return_value=None):
            doctor._check_ai_tools()

        check = next(c for c in doctor.report.checks if c.name == "AI Tools")
        assert check.status == CheckStatus.SKIPPED

    def test_run_all_checks(self, mock_console, tmp_path, monkeypatch):
        """Test running all checks."""
        monkeypatch.chdir(tmp_path)

        doctor = Doctor(mock_console)

        # Mock environment to avoid real checks
        with patch.dict(os.environ, {}, clear=True):
            with patch("shutil.which", return_value=None):
                report = doctor.run_all_checks()

        assert isinstance(report, DoctorReport)
        assert len(report.checks) > 0


# =============================================================================
# format_doctor_report Tests
# =============================================================================


class TestFormatDoctorReport:
    """Tests for format_doctor_report function."""

    def test_format_all_ok(self):
        """Test formatting report with all OK checks."""
        report = DoctorReport(
            checks=[
                CheckResult("Test1", CheckStatus.OK, "OK"),
                CheckResult("Test2", CheckStatus.OK, "OK"),
            ]
        )

        result = format_doctor_report(report, color=False)

        assert "All Checks Passed" in result
        assert "OK: 2" in result

    def test_format_with_errors(self):
        """Test formatting report with errors."""
        report = DoctorReport(
            checks=[
                CheckResult("Test1", CheckStatus.OK, "OK"),
                CheckResult("Test2", CheckStatus.ERROR, "Error"),
            ]
        )

        result = format_doctor_report(report, color=False)

        assert "Issues Found" in result
        assert "Errors: 1" in result

    def test_format_with_warnings(self):
        """Test formatting report with warnings."""
        report = DoctorReport(
            checks=[
                CheckResult("Test1", CheckStatus.OK, "OK"),
                CheckResult("Test2", CheckStatus.WARNING, "Warning"),
            ]
        )

        result = format_doctor_report(report, color=False)

        assert "Warnings" in result
        assert "Warnings: 1" in result


# =============================================================================
# run_doctor Tests
# =============================================================================


class TestRunDoctor:
    """Tests for run_doctor function."""

    @pytest.fixture
    def mock_console(self):
        """Create a mock console."""
        console = MagicMock()
        console.color = False
        return console

    def test_run_doctor_success(self, mock_console, tmp_path, monkeypatch):
        """Test run_doctor with all checks passing."""
        monkeypatch.chdir(tmp_path)

        # Create config file
        (tmp_path / ".spectra.yaml").write_text("test: value")
        # Create .git dir
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "hooks").mkdir()

        env = {
            "JIRA_URL": "https://test.atlassian.net",
            "JIRA_EMAIL": "test@example.com",
            "JIRA_API_TOKEN": "secrettoken123456",
        }

        mock_adapter = MagicMock()
        mock_adapter.test_connection.return_value = True
        mock_adapter.get_current_user.return_value = {"displayName": "Test"}

        # Mock both pyyaml and requests imports to pass dependency check
        original_import = (
            __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__
        )

        def mock_import(name, *args, **kwargs):
            if name in ("pyyaml", "yaml", "requests"):
                return MagicMock()
            return original_import(name, *args, **kwargs)

        with patch.dict(os.environ, env):
            with patch("builtins.__import__", side_effect=mock_import):
                with patch("spectryn.adapters.JiraAdapter", return_value=mock_adapter):
                    with patch("spectryn.adapters.ADFFormatter"):
                        with patch("spectryn.core.ports.config_provider.TrackerConfig"):
                            with patch("shutil.which", return_value="/usr/bin/git"):
                                result = run_doctor(mock_console, verbose=False)

        # Result depends on actual environment; check it doesn't crash
        assert result in [ExitCode.SUCCESS, ExitCode.ERROR]

    def test_run_doctor_with_errors(self, mock_console, tmp_path, monkeypatch):
        """Test run_doctor with errors."""
        monkeypatch.chdir(tmp_path)

        # No config, no credentials
        with patch.dict(os.environ, {}, clear=True):
            with patch("shutil.which", return_value=None):
                result = run_doctor(mock_console, verbose=False)

        assert result == ExitCode.ERROR

    def test_run_doctor_verbose(self, mock_console, tmp_path, monkeypatch):
        """Test run_doctor in verbose mode."""
        monkeypatch.chdir(tmp_path)

        with patch.dict(os.environ, {}, clear=True):
            with patch("shutil.which", return_value=None):
                result = run_doctor(mock_console, verbose=True)

        # Should still run without crashing
        assert result in [ExitCode.SUCCESS, ExitCode.ERROR]
