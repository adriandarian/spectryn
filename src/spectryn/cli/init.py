"""
Init Wizard - First-time setup assistant for spectra.

Provides an interactive setup experience that:
1. Collects Jira credentials
2. Tests the connection
3. Creates configuration files
4. Optionally creates a sample markdown file
"""

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .output import Colors, Console, Symbols


class ConfigFormat(Enum):
    """Configuration file format options."""

    ENV = ".env"
    YAML = ".spectra.yaml"
    TOML = ".spectra.toml"


@dataclass
class InitConfig:
    """
    Configuration collected during init wizard.

    Attributes:
        jira_url: Jira instance URL.
        jira_email: Jira account email.
        jira_api_token: Jira API token.
        project_key: Default project key (optional).
        config_format: Chosen configuration file format.
        create_sample: Whether to create a sample markdown file.
        sample_path: Path for sample markdown file.
    """

    jira_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""
    project_key: str = ""
    config_format: ConfigFormat = ConfigFormat.ENV
    create_sample: bool = False
    sample_path: str = "EPIC.md"


class InitWizard:
    """
    Interactive setup wizard for first-time spectra configuration.

    Guides users through setting up their Jira credentials and
    creating the necessary configuration files.
    """

    SAMPLE_MARKDOWN = """# Epic: {project_key}-XXX
<!-- Replace XXX with your actual epic number -->

## Description
This is a sample epic document. Replace this description with your epic's details.

## Stories

### STORY-001: Sample Story Title
**Status:** To Do
**Points:** 3

As a user, I want to have a sample story so that I can see the expected format.

#### Acceptance Criteria
- [ ] First acceptance criterion
- [ ] Second acceptance criterion
- [ ] Third acceptance criterion

#### Subtasks
- [ ] Implement the feature
- [ ] Write unit tests
- [ ] Update documentation

---

### STORY-002: Another Sample Story
**Status:** To Do
**Points:** 5

As a developer, I want to understand the markdown format so that I can create my own epics.

#### Acceptance Criteria
- [ ] Story has a clear title with ID
- [ ] Story includes status and points
- [ ] Story has acceptance criteria as subtasks

#### Subtasks
- [ ] Design the solution
- [ ] Implement the solution
- [ ] Review and test

---

## Notes
- Stories are separated by `---` (horizontal rule)
- Story IDs use PREFIX-NUMBER format (e.g., STORY-001, US-001, PROJ-123)
- Status should match a valid Jira status in your workflow
- Points are optional but recommended for sprint planning
"""

    def __init__(self, console: Console):
        """
        Initialize the wizard.

        Args:
            console: Console instance for output.
        """
        self.console = console
        self.config = InitConfig()

    def run(self) -> bool:
        """
        Run the complete setup wizard.

        Returns:
            True if setup completed successfully, False otherwise.
        """
        self._show_welcome()

        # Step 1: Check for existing configuration
        if self._check_existing_config() and not self._prompt_overwrite():
            self.console.info("Setup cancelled. Existing configuration preserved.")
            return False

        # Step 2: Collect Jira credentials
        if not self._collect_credentials():
            return False

        # Step 3: Test connection
        if not self._test_connection() and not self._prompt_continue_anyway():
            return False

        # Step 4: Choose config format
        self._choose_config_format()

        # Step 5: Optionally collect project key
        self._collect_project_key()

        # Step 6: Create configuration file
        if not self._create_config_file():
            return False

        # Step 7: Optionally create sample markdown
        if self._prompt_create_sample():
            self._create_sample_markdown()

        # Show completion message
        self._show_completion()

        return True

    # -------------------------------------------------------------------------
    # Welcome and Check
    # -------------------------------------------------------------------------

    def _show_welcome(self) -> None:
        """Show welcome banner."""
        self.console.header(f"spectra Setup Wizard {Symbols.GEAR}")
        self.console.print()
        self.console.info("Welcome! This wizard will help you set up spectra.")
        self.console.info("You'll need:")
        self.console.item("Your Jira instance URL")
        self.console.item("Your Jira account email")
        self.console.item("A Jira API token")
        self.console.print()
        self.console.detail("API tokens can be created at:")
        self.console.detail("https://id.atlassian.com/manage-profile/security/api-tokens")
        self.console.print()

    def _check_existing_config(self) -> bool:
        """Check if configuration already exists."""
        config_files = [
            Path(".env"),
            Path(".spectra.yaml"),
            Path(".spectra.yml"),
            Path(".spectra.toml"),
        ]

        for config_file in config_files:
            if config_file.exists():
                return True

        # Check environment variables
        return bool(os.environ.get("JIRA_URL") or os.environ.get("JIRA_API_TOKEN"))

    def _prompt_overwrite(self) -> bool:
        """Prompt user about overwriting existing config."""
        self.console.warning("Existing configuration detected!")
        return self._prompt_yes_no(
            "Do you want to create a new configuration? (existing files won't be deleted)",
            default=False,
        )

    # -------------------------------------------------------------------------
    # Credential Collection
    # -------------------------------------------------------------------------

    def _collect_credentials(self) -> bool:
        """Collect Jira credentials from user."""
        self.console.section("Jira Credentials")
        self.console.print()

        # Jira URL
        self.console.info("Enter your Jira instance URL")
        self.console.detail("Example: https://your-company.atlassian.net")
        url = self._prompt_input("Jira URL: ")
        if not url:
            self.console.error("Jira URL is required")
            return False

        # Validate and clean URL
        url = url.strip().rstrip("/")
        if not url.startswith("http"):
            url = f"https://{url}"
        self.config.jira_url = url

        self.console.print()

        # Jira Email
        self.console.info("Enter your Jira account email")
        email = self._prompt_input("Email: ")
        if not email:
            self.console.error("Email is required")
            return False
        self.config.jira_email = email.strip()

        self.console.print()

        # API Token
        self.console.info("Enter your Jira API token")
        self.console.detail("The token will be hidden as you type")
        token = self._prompt_password("API Token: ")
        if not token:
            self.console.error("API token is required")
            return False
        self.config.jira_api_token = token.strip()

        self.console.print()
        self.console.success("Credentials collected!")

        return True

    # -------------------------------------------------------------------------
    # Connection Test
    # -------------------------------------------------------------------------

    def _test_connection(self) -> bool:
        """Test connection to Jira."""
        self.console.section("Testing Connection")
        self.console.print()
        self.console.info("Connecting to Jira...")

        try:
            from spectryn.adapters import ADFFormatter, JiraAdapter
            from spectryn.core.ports.config_provider import TrackerConfig

            config = TrackerConfig(
                url=self.config.jira_url,
                email=self.config.jira_email,
                api_token=self.config.jira_api_token,
            )

            adapter = JiraAdapter(
                config=config,
                dry_run=True,
                formatter=ADFFormatter(),
            )

            if adapter.test_connection():
                user = adapter.get_current_user()
                display_name = user.get("displayName", user.get("emailAddress", "Unknown"))
                self.console.success(f"Connected successfully as: {display_name}")
                return True
            self.console.error("Connection failed")
            return False

        except Exception as e:
            self.console.error(f"Connection failed: {e}")
            return False

    def _prompt_continue_anyway(self) -> bool:
        """Prompt user to continue despite connection failure."""
        self.console.print()
        self.console.warning("Connection test failed.")
        self.console.info("This could be due to:")
        self.console.item("Network issues")
        self.console.item("Incorrect URL or credentials")
        self.console.item("Firewall/proxy restrictions")
        self.console.print()

        return self._prompt_yes_no(
            "Continue with setup anyway? (you can fix credentials later)",
            default=False,
        )

    # -------------------------------------------------------------------------
    # Config Format Selection
    # -------------------------------------------------------------------------

    def _choose_config_format(self) -> None:
        """Let user choose configuration file format."""
        self.console.section("Configuration Format")
        self.console.print()
        self.console.info("Choose where to store your configuration:")
        self.console.print()

        options = [
            (ConfigFormat.ENV, ".env file", "Simple key=value format, easy to manage"),
            (ConfigFormat.YAML, ".spectra.yaml", "Human-readable YAML format"),
            (ConfigFormat.TOML, ".spectra.toml", "Modern TOML format"),
        ]

        for i, (_fmt, name, desc) in enumerate(options, 1):
            self.console.item(f"{i}. {name} - {desc}")

        self.console.print()
        choice = self._prompt_input("Enter choice [1]: ", default="1")

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                self.config.config_format = options[idx][0]
            else:
                self.config.config_format = ConfigFormat.ENV
        except ValueError:
            self.config.config_format = ConfigFormat.ENV

        self.console.success(f"Using {self.config.config_format.value}")

    # -------------------------------------------------------------------------
    # Project Key
    # -------------------------------------------------------------------------

    def _collect_project_key(self) -> None:
        """Optionally collect default project key."""
        self.console.print()
        self.console.info("Default project key (optional)")
        self.console.detail("This will be used as the default for new epics")

        project = self._prompt_input("Project key (e.g., PROJ): ", default="")
        if project:
            self.config.project_key = project.strip().upper()

    # -------------------------------------------------------------------------
    # Config File Creation
    # -------------------------------------------------------------------------

    def _create_config_file(self) -> bool:
        """Create the configuration file."""
        self.console.section("Creating Configuration")
        self.console.print()

        try:
            if self.config.config_format == ConfigFormat.ENV:
                self._create_env_file()
            elif self.config.config_format == ConfigFormat.YAML:
                self._create_yaml_file()
            elif self.config.config_format == ConfigFormat.TOML:
                self._create_toml_file()

            return True

        except Exception as e:
            self.console.error(f"Failed to create config file: {e}")
            return False

    def _create_env_file(self) -> None:
        """Create .env configuration file."""
        path = Path(".env")

        content = f"""# spectra Configuration
# Generated by spectra init

# Jira Instance URL
JIRA_URL={self.config.jira_url}

# Jira Account Email
JIRA_EMAIL={self.config.jira_email}

# Jira API Token
# Generate at: https://id.atlassian.com/manage-profile/security/api-tokens
JIRA_API_TOKEN={self.config.jira_api_token}
"""

        if self.config.project_key:
            content += f"""
# Default Project Key
JIRA_PROJECT={self.config.project_key}
"""

        path.write_text(content)
        self.console.success(f"Created {path}")

        # Add to .gitignore if it exists
        self._add_to_gitignore(".env")

    def _create_yaml_file(self) -> None:
        """Create .spectra.yaml configuration file."""
        path = Path(".spectra.yaml")

        content = f"""# spectra Configuration
# Generated by spectra init

jira:
  # Jira Instance URL
  url: {self.config.jira_url}

  # Jira Account Email
  email: {self.config.jira_email}

  # Jira API Token
  # Generate at: https://id.atlassian.com/manage-profile/security/api-tokens
  api_token: {self.config.jira_api_token}
"""

        if self.config.project_key:
            content += f"""
  # Default Project Key
  project: {self.config.project_key}
"""

        content += """
sync:
  # Enable verbose output
  verbose: false

  # Skip confirmation prompts
  no_confirm: false
"""

        path.write_text(content)
        self.console.success(f"Created {path}")

        # Add to .gitignore if it exists
        self._add_to_gitignore(".spectra.yaml")

    def _create_toml_file(self) -> None:
        """Create .spectra.toml configuration file."""
        path = Path(".spectra.toml")

        content = f"""# spectra Configuration
# Generated by spectra init

[jira]
# Jira Instance URL
url = "{self.config.jira_url}"

# Jira Account Email
email = "{self.config.jira_email}"

# Jira API Token
# Generate at: https://id.atlassian.com/manage-profile/security/api-tokens
api_token = "{self.config.jira_api_token}"
"""

        if self.config.project_key:
            content += f"""
# Default Project Key
project = "{self.config.project_key}"
"""

        content += """
[sync]
# Enable verbose output
verbose = false

# Skip confirmation prompts
no_confirm = false
"""

        path.write_text(content)
        self.console.success(f"Created {path}")

        # Add to .gitignore if it exists
        self._add_to_gitignore(".spectra.toml")

    def _add_to_gitignore(self, filename: str) -> None:
        """Add a file to .gitignore if it exists."""
        gitignore = Path(".gitignore")

        if not gitignore.exists():
            return

        content = gitignore.read_text()

        # Check if already in gitignore
        if filename in content:
            return

        # Add to gitignore
        with gitignore.open("a") as f:
            if not content.endswith("\n"):
                f.write("\n")
            f.write("\n# spectra configuration (contains credentials)\n")
            f.write(f"{filename}\n")

        self.console.detail(f"Added {filename} to .gitignore")

    # -------------------------------------------------------------------------
    # Sample Markdown
    # -------------------------------------------------------------------------

    def _prompt_create_sample(self) -> bool:
        """Prompt user about creating a sample markdown file."""
        self.console.print()
        return self._prompt_yes_no(
            "Create a sample epic markdown file?",
            default=True,
        )

    def _create_sample_markdown(self) -> None:
        """Create a sample markdown file."""
        self.console.print()

        default_path = "EPIC.md"
        if self.config.project_key:
            default_path = f"{self.config.project_key}-EPIC.md"

        path_input = self._prompt_input(
            f"Sample file path [{default_path}]: ",
            default=default_path,
        )

        path = Path(path_input)

        # Check if file exists
        if path.exists():
            if not self._prompt_yes_no(f"{path} exists. Overwrite?", default=False):
                self.console.info("Sample file not created")
                return

        # Create sample content
        content = self.SAMPLE_MARKDOWN
        if self.config.project_key:
            content = content.format(project_key=self.config.project_key)
        else:
            content = content.format(project_key="PROJ")

        path.write_text(content)
        self.console.success(f"Created sample file: {path}")
        self.config.sample_path = str(path)

    # -------------------------------------------------------------------------
    # Completion
    # -------------------------------------------------------------------------

    def _show_completion(self) -> None:
        """Show setup completion message."""
        self.console.print()
        self.console.header(f"Setup Complete! {Symbols.CHECK}")
        self.console.print()

        self.console.success("spectra is ready to use!")
        self.console.print()

        self.console.info("Next steps:")

        if self.config.create_sample:
            self.console.item(f"Edit {self.config.sample_path} with your epic content")
            self.console.item(
                f"Create the epic in Jira and note the key (e.g., {self.config.project_key or 'PROJ'}-123)"
            )
            self.console.item("Run a dry-run to preview changes:")
            self.console.detail(
                f"  spectra --input {self.config.sample_path} --epic {self.config.project_key or 'PROJ'}-123"
            )
            self.console.item("Execute the sync when ready:")
            self.console.detail(
                f"  spectra --input {self.config.sample_path} --epic {self.config.project_key or 'PROJ'}-123 --execute"
            )
        else:
            self.console.item("Create a markdown file with your epic content")
            self.console.item("Run a dry-run: spectra --input EPIC.md --epic PROJ-123")
            self.console.item(
                "Execute when ready: spectra --input EPIC.md --epic PROJ-123 --execute"
            )

        self.console.print()
        self.console.info("For more information:")
        self.console.detail("  Documentation: https://spectra.dev")
        self.console.detail("  Examples: spectra --help")

    # -------------------------------------------------------------------------
    # Input Helpers
    # -------------------------------------------------------------------------

    def _prompt_input(self, prompt: str, default: str = "") -> str:
        """
        Prompt for text input.

        Args:
            prompt: The prompt to display.
            default: Default value if user presses Enter.

        Returns:
            User input or default value.
        """
        try:
            if self.console.color:
                formatted_prompt = f"{Colors.CYAN}{prompt}{Colors.RESET}"
            else:
                formatted_prompt = prompt

            value = input(formatted_prompt)
            return value.strip() if value.strip() else default
        except (EOFError, KeyboardInterrupt):
            print()
            return default

    def _prompt_password(self, prompt: str) -> str:
        """
        Prompt for password input (hidden).

        Args:
            prompt: The prompt to display.

        Returns:
            Password input.
        """
        try:
            import getpass

            if self.console.color:
                pass
            else:
                pass

            # getpass doesn't support colors in the prompt on all terminals
            return getpass.getpass(prompt)
        except (EOFError, KeyboardInterrupt):
            print()
            return ""

    def _prompt_yes_no(self, question: str, default: bool = True) -> bool:
        """
        Prompt for yes/no confirmation.

        Args:
            question: The question to ask.
            default: Default answer if user presses Enter.

        Returns:
            True for yes, False for no.
        """
        default_hint = "Y/n" if default else "y/N"
        prompt = f"{question} [{default_hint}]: "

        try:
            if self.console.color:
                formatted_prompt = f"{Colors.YELLOW}{Symbols.WARN} {prompt}{Colors.RESET}"
            else:
                formatted_prompt = prompt

            response = input(formatted_prompt).strip().lower()

            if not response:
                return default

            return response in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            print()
            return default


def run_init(console: Console) -> int:
    """
    Run the init wizard.

    Args:
        console: Console instance for output.

    Returns:
        Exit code.
    """
    from .exit_codes import ExitCode

    wizard = InitWizard(console)

    try:
        success = wizard.run()
        return ExitCode.SUCCESS if success else ExitCode.CANCELLED
    except KeyboardInterrupt:
        console.print()
        console.warning("Setup cancelled by user")
        return ExitCode.SIGINT
    except Exception as e:
        console.error_rich(e)
        return ExitCode.ERROR
