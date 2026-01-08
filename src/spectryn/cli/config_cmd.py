"""
Config Command - Validate and manage configuration.

Features:
- Validate configuration files
- Show current configuration
- Test connections
- Check for common issues
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from .exit_codes import ExitCode
from .output import Colors, Console, Symbols


@dataclass
class ConfigValidationResult:
    """Result of configuration validation."""

    valid: bool = True
    config_file: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)


def find_config_files() -> list[Path]:
    """Find all configuration files in current directory."""
    config_files = []

    candidates = [
        ".spectra.yaml",
        ".spectra.yml",
        ".spectra.toml",
        ".env",
        "spectra.config.json",
        "pyproject.toml",  # Check for [tool.spectra] section
    ]

    for name in candidates:
        path = Path(name)
        if path.exists():
            config_files.append(path)

    return config_files


def validate_config_file(path: Path) -> ConfigValidationResult:
    """
    Validate a single configuration file.

    Args:
        path: Path to config file.

    Returns:
        ConfigValidationResult with issues found.
    """
    result = ConfigValidationResult(config_file=str(path))

    if not path.exists():
        result.valid = False
        result.errors.append(f"File not found: {path}")
        return result

    suffix = path.suffix.lower()
    content = path.read_text(encoding="utf-8")

    try:
        if suffix in (".yaml", ".yml"):
            import yaml

            config = yaml.safe_load(content)
            _validate_config_dict(config, result)

        elif suffix == ".toml":
            try:
                import tomllib
            except ImportError:
                import tomli as tomllib  # type: ignore

            config = tomllib.loads(content)

            # Check for [tool.spectra] in pyproject.toml
            if path.name == "pyproject.toml":
                config = config.get("tool", {}).get("spectra", {})
                if not config:
                    result.info.append("No [tool.spectra] section in pyproject.toml")
                    return result

            _validate_config_dict(config, result)

        elif suffix == ".json":
            import json

            config = json.loads(content)
            _validate_config_dict(config, result)

        elif path.name == ".env":
            _validate_env_file(content, result)

        else:
            result.warnings.append(f"Unknown config format: {suffix}")

    except Exception as e:
        result.valid = False
        result.errors.append(f"Parse error: {e}")

    return result


def _validate_config_dict(config: dict, result: ConfigValidationResult) -> None:
    """Validate a configuration dictionary."""
    if not config:
        result.warnings.append("Configuration is empty")
        return

    # Check for jira/tracker section
    jira_config = config.get("jira") or config.get("tracker") or {}

    if not jira_config:
        result.warnings.append("No tracker configuration found")
        result.info.append("Expected: jira.url, jira.email, jira.api_token")
        return

    # Required fields
    url = jira_config.get("url")
    email = jira_config.get("email")
    token = jira_config.get("api_token") or jira_config.get("token")

    if not url:
        result.errors.append("Missing: jira.url")
        result.valid = False
    elif not url.startswith(("http://", "https://")):
        result.warnings.append("jira.url should start with http:// or https://")

    if not email:
        result.warnings.append("Missing: jira.email")

    if not token:
        result.errors.append("Missing: jira.api_token")
        result.valid = False

    # Optional but recommended
    project = jira_config.get("project")
    if not project:
        result.info.append("Consider setting jira.project for default project")

    # Check sync config
    sync_config = config.get("sync") or {}
    if sync_config:
        if sync_config.get("dry_run") is True:
            result.info.append("dry_run is enabled by default")


def _validate_env_file(content: str, result: ConfigValidationResult) -> None:
    """Validate a .env file."""
    env_vars = {}

    for line in content.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if "=" in line:
            key, value = line.split("=", 1)
            env_vars[key.strip()] = value.strip()

    # Required variables
    required = ["JIRA_URL", "JIRA_API_TOKEN"]
    recommended = ["JIRA_EMAIL", "JIRA_PROJECT"]

    for var in required:
        if var not in env_vars:
            result.errors.append(f"Missing: {var}")
            result.valid = False

    for var in recommended:
        if var not in env_vars:
            result.warnings.append(f"Recommended: {var}")

    # Validate URL format
    jira_url = env_vars.get("JIRA_URL", "")
    if jira_url and not jira_url.startswith(("http://", "https://")):
        result.warnings.append("JIRA_URL should start with http:// or https://")


def format_validation_result(result: ConfigValidationResult, color: bool = True) -> str:
    """Format validation result for display."""
    lines = []

    # Header
    if result.valid:
        status = f"{Colors.GREEN}{Symbols.CHECK} Valid{Colors.RESET}" if color else "✓ Valid"
    else:
        status = f"{Colors.RED}{Symbols.CROSS} Invalid{Colors.RESET}" if color else "✗ Invalid"

    lines.append(f"  {result.config_file}: {status}")

    # Errors
    for error in result.errors:
        if color:
            lines.append(f"    {Colors.RED}✗ {error}{Colors.RESET}")
        else:
            lines.append(f"    ✗ {error}")

    # Warnings
    for warning in result.warnings:
        if color:
            lines.append(f"    {Colors.YELLOW}⚠ {warning}{Colors.RESET}")
        else:
            lines.append(f"    ⚠ {warning}")

    # Info
    for info in result.info:
        if color:
            lines.append(f"    {Colors.DIM}ℹ {info}{Colors.RESET}")
        else:
            lines.append(f"    ℹ {info}")

    return "\n".join(lines)


def run_config_validate(
    console: Console,
    config_file: str | None = None,
    test_connection: bool = False,
) -> int:
    """
    Run the config validate command.

    Args:
        console: Console for output.
        config_file: Specific config file to validate.
        test_connection: Whether to test tracker connection.

    Returns:
        Exit code.
    """
    console.header(f"spectra Config Validate {Symbols.GEAR}")
    console.print()

    # Find config files
    if config_file:
        files = [Path(config_file)]
        if not files[0].exists():
            console.error(f"Config file not found: {config_file}")
            return ExitCode.FILE_NOT_FOUND
    else:
        files = find_config_files()

    if not files:
        console.warning("No configuration files found")
        console.print()
        console.info("Create configuration with: spectra --init")
        console.info("Or set environment variables: JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN")

        # Check environment variables as fallback
        env_result = ConfigValidationResult(config_file="Environment")
        env_vars_found = False

        if os.environ.get("JIRA_URL"):
            env_vars_found = True
            env_result.info.append(f"JIRA_URL: {os.environ['JIRA_URL'][:30]}...")
        if os.environ.get("JIRA_API_TOKEN"):
            env_vars_found = True
            env_result.info.append("JIRA_API_TOKEN: ***")
        if os.environ.get("JIRA_EMAIL"):
            env_result.info.append(f"JIRA_EMAIL: {os.environ['JIRA_EMAIL']}")

        if env_vars_found:
            console.print()
            console.info("Environment variables detected:")
            for info in env_result.info:
                console.detail(f"  {info}")
            return ExitCode.SUCCESS

        return ExitCode.CONFIG_ERROR

    console.info(f"Found {len(files)} configuration file(s)")
    console.print()

    # Validate each file
    all_valid = True
    results = []

    for file_path in files:
        result = validate_config_file(file_path)
        results.append(result)

        formatted = format_validation_result(result, color=console.color)
        print(formatted)
        print()

        if not result.valid:
            all_valid = False

    # Test connection if requested
    if test_connection and all_valid:
        console.section("Testing Connection")

        try:
            from spectryn.adapters import ADFFormatter, EnvironmentConfigProvider, JiraAdapter

            config_provider = EnvironmentConfigProvider()
            if config_file:
                config_provider = EnvironmentConfigProvider(config_file=Path(config_file))

            config = config_provider.load()

            tracker = JiraAdapter(
                config=config.tracker,
                dry_run=True,
                formatter=ADFFormatter(),
            )

            if tracker.test_connection():
                user = tracker.get_current_user()
                console.success(f"Connected as: {user.get('displayName', 'Unknown')}")
            else:
                console.error("Connection failed")
                all_valid = False

        except Exception as e:
            console.error(f"Connection test failed: {e}")
            all_valid = False

    # Summary
    console.print()
    if all_valid:
        console.success("Configuration is valid")
    else:
        console.error("Configuration has errors")
        console.info("Fix the errors above and run again")

    return ExitCode.SUCCESS if all_valid else ExitCode.CONFIG_ERROR
