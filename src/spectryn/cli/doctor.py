"""
Doctor Command - Diagnose common setup issues.

Checks for:
- Configuration files and environment variables
- Jira/tracker connectivity
- File permissions
- Python dependencies
- Common misconfigurations
"""

import os
import shutil
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .exit_codes import ExitCode
from .output import Colors, Console, Symbols


class CheckStatus(Enum):
    """Status of a diagnostic check."""

    OK = "ok"
    WARNING = "warning"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass
class CheckResult:
    """Result of a diagnostic check."""

    name: str
    status: CheckStatus
    message: str
    details: list[str] = field(default_factory=list)
    suggestion: str | None = None


@dataclass
class DoctorReport:
    """Complete doctor report."""

    checks: list[CheckResult] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return any(c.status == CheckStatus.ERROR for c in self.checks)

    @property
    def has_warnings(self) -> bool:
        """Check if there are any warnings."""
        return any(c.status == CheckStatus.WARNING for c in self.checks)

    @property
    def ok_count(self) -> int:
        """Count of OK checks."""
        return sum(1 for c in self.checks if c.status == CheckStatus.OK)

    @property
    def error_count(self) -> int:
        """Count of error checks."""
        return sum(1 for c in self.checks if c.status == CheckStatus.ERROR)

    @property
    def warning_count(self) -> int:
        """Count of warning checks."""
        return sum(1 for c in self.checks if c.status == CheckStatus.WARNING)


class Doctor:
    """Diagnostic checker for spectra setup."""

    def __init__(self, console: Console, verbose: bool = False):
        """
        Initialize the doctor.

        Args:
            console: Console for output.
            verbose: Show verbose output.
        """
        self.console = console
        self.verbose = verbose
        self.report = DoctorReport()

    def run_all_checks(self) -> DoctorReport:
        """Run all diagnostic checks."""
        self.console.header(f"spectra Doctor {Symbols.GEAR}")
        self.console.print()
        self.console.info("Running diagnostic checks...")
        self.console.print()

        # Run checks in order
        self._check_python_version()
        self._check_dependencies()
        self._check_config_files()
        self._check_environment_variables()
        self._check_tracker_connection()
        self._check_workspace()
        self._check_git_integration()
        self._check_ai_tools()

        return self.report

    def _add_check(self, result: CheckResult) -> None:
        """Add a check result and display it."""
        self.report.checks.append(result)

        # Display the result
        if result.status == CheckStatus.OK:
            icon = f"{Colors.GREEN}{Symbols.CHECK}{Colors.RESET}" if self.console.color else "✓"
            color = Colors.GREEN if self.console.color else ""
        elif result.status == CheckStatus.WARNING:
            icon = f"{Colors.YELLOW}{Symbols.WARN}{Colors.RESET}" if self.console.color else "⚠"
            color = Colors.YELLOW if self.console.color else ""
        elif result.status == CheckStatus.ERROR:
            icon = f"{Colors.RED}{Symbols.CROSS}{Colors.RESET}" if self.console.color else "✗"
            color = Colors.RED if self.console.color else ""
        else:
            icon = f"{Colors.DIM}○{Colors.RESET}" if self.console.color else "○"
            color = Colors.DIM if self.console.color else ""

        reset = Colors.RESET if self.console.color else ""
        print(f"  {icon} {color}{result.name}{reset}: {result.message}")

        # Show details if verbose
        if self.verbose and result.details:
            for detail in result.details:
                print(f"      {detail}")

        # Show suggestion for errors/warnings
        if result.suggestion and result.status in (CheckStatus.ERROR, CheckStatus.WARNING):
            dim = Colors.DIM if self.console.color else ""
            print(f"      {dim}→ {result.suggestion}{reset}")

    # -------------------------------------------------------------------------
    # Individual Checks
    # -------------------------------------------------------------------------

    def _check_python_version(self) -> None:
        """Check Python version compatibility."""
        version = sys.version_info
        version_str = f"{version.major}.{version.minor}.{version.micro}"

        if version >= (3, 11):
            self._add_check(
                CheckResult(
                    name="Python Version",
                    status=CheckStatus.OK,
                    message=f"Python {version_str}",
                )
            )
        elif version >= (3, 9):
            self._add_check(
                CheckResult(
                    name="Python Version",
                    status=CheckStatus.WARNING,
                    message=f"Python {version_str} (3.11+ recommended)",
                    suggestion="Consider upgrading to Python 3.11+ for best performance",
                )
            )
        else:
            self._add_check(
                CheckResult(
                    name="Python Version",
                    status=CheckStatus.ERROR,
                    message=f"Python {version_str} (unsupported)",
                    suggestion="spectra requires Python 3.9 or higher",
                )
            )

    def _check_dependencies(self) -> None:
        """Check required dependencies."""
        required = {
            "requests": "HTTP requests for API calls",
            "pyyaml": "YAML parsing for config files",
        }

        optional = {
            "rich": "Enhanced terminal output",
            "opentelemetry-api": "OpenTelemetry tracing",
            "prometheus-client": "Prometheus metrics",
        }

        missing_required = []
        missing_optional = []

        for package, desc in required.items():
            try:
                __import__(package.replace("-", "_"))
            except ImportError:
                missing_required.append(f"{package}: {desc}")

        for package, desc in optional.items():
            try:
                __import__(package.replace("-", "_"))
            except ImportError:
                missing_optional.append(f"{package}: {desc}")

        if missing_required:
            self._add_check(
                CheckResult(
                    name="Dependencies",
                    status=CheckStatus.ERROR,
                    message=f"{len(missing_required)} required package(s) missing",
                    details=missing_required,
                    suggestion="Run: pip install "
                    + " ".join(p.split(":")[0] for p in missing_required),
                )
            )
        elif missing_optional:
            self._add_check(
                CheckResult(
                    name="Dependencies",
                    status=CheckStatus.OK,
                    message="Required packages installed",
                    details=[f"Optional: {p}" for p in missing_optional] if self.verbose else [],
                )
            )
        else:
            self._add_check(
                CheckResult(
                    name="Dependencies",
                    status=CheckStatus.OK,
                    message="All packages installed",
                )
            )

    def _check_config_files(self) -> None:
        """Check for configuration files."""
        config_files = [
            (".spectra.yaml", "YAML config"),
            (".spectra.yml", "YAML config"),
            (".spectra.toml", "TOML config"),
            (".env", "Environment file"),
            ("spectra.config.json", "JSON config"),
        ]

        found = []
        for filename, desc in config_files:
            path = Path(filename)
            if path.exists():
                found.append(f"{filename} ({desc})")

        if found:
            self._add_check(
                CheckResult(
                    name="Configuration",
                    status=CheckStatus.OK,
                    message=f"Found {len(found)} config file(s)",
                    details=found,
                )
            )
        else:
            self._add_check(
                CheckResult(
                    name="Configuration",
                    status=CheckStatus.WARNING,
                    message="No config file found",
                    suggestion="Run 'spectra --init' to create configuration",
                )
            )

    def _check_environment_variables(self) -> None:
        """Check required environment variables."""
        required_vars = {
            "JIRA_URL": "Jira instance URL",
            "JIRA_EMAIL": "Jira account email",
            "JIRA_API_TOKEN": "Jira API token",
        }

        # Also check for alternative tracker configs
        alternative_vars = {
            "GITHUB_TOKEN": "GitHub API token",
            "GITLAB_TOKEN": "GitLab API token",
            "LINEAR_API_KEY": "Linear API key",
            "AZURE_DEVOPS_PAT": "Azure DevOps PAT",
        }

        missing = []
        present = []
        alternatives_present = []

        for var, _desc in required_vars.items():
            value = os.environ.get(var)
            if value:
                # Mask sensitive values
                if "TOKEN" in var or "SECRET" in var or "KEY" in var:
                    masked = value[:4] + "..." + value[-4:] if len(value) > 10 else "***"
                    present.append(f"{var}: {masked}")
                else:
                    present.append(f"{var}: {value[:30]}...")
            else:
                missing.append(var)

        # Check alternatives
        for var, desc in alternative_vars.items():
            if os.environ.get(var):
                alternatives_present.append(f"{var} ({desc})")

        if not missing:
            self._add_check(
                CheckResult(
                    name="Environment",
                    status=CheckStatus.OK,
                    message="Jira credentials configured",
                    details=present if self.verbose else [],
                )
            )
        elif alternatives_present:
            self._add_check(
                CheckResult(
                    name="Environment",
                    status=CheckStatus.OK,
                    message="Alternative tracker configured",
                    details=alternatives_present,
                )
            )
        else:
            self._add_check(
                CheckResult(
                    name="Environment",
                    status=CheckStatus.ERROR,
                    message=f"Missing: {', '.join(missing)}",
                    suggestion="Set environment variables or run 'spectra --init'",
                )
            )

    def _check_tracker_connection(self) -> None:
        """Check connection to issue tracker."""
        # Check if we have credentials first
        jira_url = os.environ.get("JIRA_URL")
        jira_token = os.environ.get("JIRA_API_TOKEN")
        jira_email = os.environ.get("JIRA_EMAIL")

        if not all([jira_url, jira_token, jira_email]):
            self._add_check(
                CheckResult(
                    name="Tracker Connection",
                    status=CheckStatus.SKIPPED,
                    message="Skipped (no credentials)",
                )
            )
            return

        try:
            from spectryn.adapters import ADFFormatter, JiraAdapter
            from spectryn.core.ports.config_provider import TrackerConfig

            config = TrackerConfig(
                url=jira_url,
                email=jira_email,
                api_token=jira_token,
            )

            adapter = JiraAdapter(
                config=config,
                dry_run=True,
                formatter=ADFFormatter(),
            )

            if adapter.test_connection():
                user = adapter.get_current_user()
                display_name = user.get("displayName", user.get("emailAddress", "Unknown"))
                self._add_check(
                    CheckResult(
                        name="Tracker Connection",
                        status=CheckStatus.OK,
                        message=f"Connected as {display_name}",
                        details=[f"URL: {jira_url}"],
                    )
                )
            else:
                self._add_check(
                    CheckResult(
                        name="Tracker Connection",
                        status=CheckStatus.ERROR,
                        message="Connection failed",
                        suggestion="Check your Jira URL and credentials",
                    )
                )
        except ImportError:
            self._add_check(
                CheckResult(
                    name="Tracker Connection",
                    status=CheckStatus.SKIPPED,
                    message="Adapter not available",
                )
            )
        except Exception as e:
            self._add_check(
                CheckResult(
                    name="Tracker Connection",
                    status=CheckStatus.ERROR,
                    message=f"Error: {str(e)[:50]}",
                    suggestion="Check network connectivity and firewall settings",
                )
            )

    def _check_workspace(self) -> None:
        """Check workspace and file permissions."""
        cwd = Path.cwd()

        # Check if we can write to current directory
        test_file = cwd / ".spectra_doctor_test"
        can_write = False

        try:
            test_file.write_text("test")
            test_file.unlink()
            can_write = True
        except (PermissionError, OSError):
            pass

        # Look for markdown files
        md_files = list(cwd.glob("*.md"))[:10]
        yaml_files = list(cwd.glob("*.yaml")) + list(cwd.glob("*.yml"))

        details = []
        if md_files:
            details.append(f"Markdown files: {len(md_files)}")
        if yaml_files:
            details.append(f"YAML files: {len(yaml_files)}")

        if can_write:
            self._add_check(
                CheckResult(
                    name="Workspace",
                    status=CheckStatus.OK,
                    message=f"Writable ({cwd.name}/)",
                    details=details,
                )
            )
        else:
            self._add_check(
                CheckResult(
                    name="Workspace",
                    status=CheckStatus.ERROR,
                    message="Cannot write to current directory",
                    suggestion="Check file permissions or change to a writable directory",
                )
            )

    def _check_git_integration(self) -> None:
        """Check git integration."""
        git_dir = Path.cwd() / ".git"

        if not git_dir.is_dir():
            self._add_check(
                CheckResult(
                    name="Git Integration",
                    status=CheckStatus.SKIPPED,
                    message="Not a git repository",
                )
            )
            return

        # Check if git is available
        git_path = shutil.which("git")
        if not git_path:
            self._add_check(
                CheckResult(
                    name="Git Integration",
                    status=CheckStatus.WARNING,
                    message="git command not found",
                    suggestion="Install git for version control features",
                )
            )
            return

        # Check for pre-commit hooks
        hooks_dir = git_dir / "hooks"
        spectra_hook = hooks_dir / "pre-commit"

        details = []
        if spectra_hook.exists():
            content = spectra_hook.read_text()
            if "spectra" in content:
                details.append("Pre-commit hook: installed")

        # Check .gitignore for spectra files
        gitignore = Path.cwd() / ".gitignore"
        if gitignore.exists():
            content = gitignore.read_text()
            if ".spectra" in content or ".env" in content:
                details.append("Credentials in .gitignore: ✓")

        self._add_check(
            CheckResult(
                name="Git Integration",
                status=CheckStatus.OK,
                message="Git repository detected",
                details=details,
            )
        )

    def _check_ai_tools(self) -> None:
        """Check for available AI tools."""
        ai_tools = [
            ("claude", "Anthropic Claude CLI"),
            ("ollama", "Ollama local LLM"),
            ("aider", "Aider AI coding"),
            ("gh", "GitHub Copilot CLI"),
            ("llm", "LLM CLI tool"),
            ("sgpt", "Shell GPT"),
            ("mods", "Mods by Charm"),
        ]

        available = []
        for cmd, name in ai_tools:
            if shutil.which(cmd):
                available.append(name)

        if available:
            self._add_check(
                CheckResult(
                    name="AI Tools",
                    status=CheckStatus.OK,
                    message=f"{len(available)} AI tool(s) available",
                    details=available if self.verbose else available[:3],
                )
            )
        else:
            self._add_check(
                CheckResult(
                    name="AI Tools",
                    status=CheckStatus.SKIPPED,
                    message="No AI CLI tools detected (optional)",
                    suggestion="Install claude, ollama, or aider for AI-assisted features",
                )
            )


def format_doctor_report(report: DoctorReport, color: bool = True) -> str:
    """Format the doctor report summary."""
    lines = []
    lines.append("")

    # Summary
    if report.has_errors:
        status = f"{Colors.RED}{Colors.BOLD}Issues Found{Colors.RESET}" if color else "Issues Found"
    elif report.has_warnings:
        status = f"{Colors.YELLOW}{Colors.BOLD}Warnings{Colors.RESET}" if color else "Warnings"
    else:
        status = (
            f"{Colors.GREEN}{Colors.BOLD}All Checks Passed{Colors.RESET}"
            if color
            else "All Checks Passed"
        )

    lines.append(f"  Summary: {status}")
    lines.append(f"    ✓ OK: {report.ok_count}")

    if report.warning_count:
        lines.append(f"    ⚠ Warnings: {report.warning_count}")
    if report.error_count:
        lines.append(f"    ✗ Errors: {report.error_count}")

    lines.append("")

    return "\n".join(lines)


def run_doctor(
    console: Console,
    verbose: bool = False,
    fix: bool = False,
) -> int:
    """
    Run the doctor command.

    Args:
        console: Console for output.
        verbose: Show verbose output.
        fix: Attempt to fix issues automatically.

    Returns:
        Exit code.
    """
    doctor = Doctor(console, verbose=verbose)
    report = doctor.run_all_checks()

    # Print summary
    summary = format_doctor_report(report, color=console.color)
    print(summary)

    # Suggest next steps
    if report.has_errors:
        console.info("Next steps:")
        console.item("Fix the errors above, then run 'spectra doctor' again")
        console.item("Run 'spectra --init' to set up configuration")
        console.print()
        return ExitCode.ERROR

    if report.has_warnings:
        console.info("Your setup is working, but consider addressing the warnings above.")
        console.print()
        return ExitCode.SUCCESS

    console.success("spectra is ready to use!")
    console.info("Get started: spectra --validate --input EPIC.md")
    console.print()
    return ExitCode.SUCCESS
