"""
Plugin Scaffold - Generate new plugin projects from templates.

This module provides scaffolding functionality to quickly create new plugins
with the correct structure, boilerplate code, and configuration files.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any


class PluginTemplateType(Enum):
    """Types of plugin templates available."""

    PARSER = auto()  # Document parser plugin
    TRACKER = auto()  # Issue tracker plugin
    FORMATTER = auto()  # Output formatter plugin
    HOOK = auto()  # Processing hook plugin
    COMMAND = auto()  # CLI command plugin


@dataclass
class PluginScaffoldConfig:
    """Configuration for scaffolding a new plugin."""

    # Plugin identification
    name: str
    description: str
    template_type: PluginTemplateType

    # Author info
    author_name: str
    author_email: str | None = None

    # Package info
    version: str = "0.1.0"
    license: str = "MIT"
    python_requires: str = ">=3.11"

    # Repository
    repository_url: str | None = None
    homepage_url: str | None = None

    # Features
    include_tests: bool = True
    include_docs: bool = True
    include_ci: bool = True
    include_docker: bool = False

    # Keywords for discovery
    keywords: list[str] = field(default_factory=list)


class PluginScaffold:
    """
    Generates plugin scaffolding from templates.

    Creates a complete plugin project structure including:
    - Package directory structure
    - Plugin implementation boilerplate
    - Configuration files (pyproject.toml, etc.)
    - Test suite
    - Documentation
    - CI/CD configuration
    """

    def __init__(self, config: PluginScaffoldConfig) -> None:
        """
        Initialize the scaffold generator.

        Args:
            config: Scaffold configuration
        """
        self.config = config
        self._validate_config()

    def _validate_config(self) -> None:
        """Validate the configuration."""
        # Validate name (must be valid Python package name)
        if not re.match(r"^[a-z][a-z0-9_]*$", self.config.name):
            raise ValueError(
                f"Invalid plugin name '{self.config.name}'. "
                "Name must start with a letter and contain only lowercase letters, numbers, and underscores."
            )

        if len(self.config.name) < 3:
            raise ValueError("Plugin name must be at least 3 characters long.")

        if len(self.config.description) < 10:
            raise ValueError("Description must be at least 10 characters long.")

    def generate(self, output_dir: Path) -> list[Path]:
        """
        Generate the plugin scaffolding.

        Args:
            output_dir: Directory to create the plugin in

        Returns:
            List of created file paths
        """
        plugin_dir = output_dir / f"spectra-{self.config.name}"
        created_files: list[Path] = []

        # Create directory structure
        dirs = self._get_directories()
        for d in dirs:
            (plugin_dir / d).mkdir(parents=True, exist_ok=True)

        # Generate files
        files = self._get_files()
        for rel_path, content in files.items():
            file_path = plugin_dir / rel_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)
            created_files.append(file_path)

        return created_files

    def _get_directories(self) -> list[str]:
        """Get the directory structure."""
        dirs = [
            f"src/spectra_{self.config.name}",
        ]

        if self.config.include_tests:
            dirs.append("tests")

        if self.config.include_docs:
            dirs.append("docs")

        return dirs

    def _get_files(self) -> dict[str, str]:
        """Get all files to generate with their content."""
        files: dict[str, str] = {}

        # Core package files
        pkg_name = f"spectra_{self.config.name}"

        files[f"src/{pkg_name}/__init__.py"] = self._get_init_py()
        files[f"src/{pkg_name}/plugin.py"] = self._get_plugin_py()

        # Add type-specific implementation
        if self.config.template_type == PluginTemplateType.PARSER:
            files[f"src/{pkg_name}/parser.py"] = self._get_parser_impl()
        elif self.config.template_type == PluginTemplateType.TRACKER:
            files[f"src/{pkg_name}/adapter.py"] = self._get_tracker_impl()
            files[f"src/{pkg_name}/client.py"] = self._get_client_impl()
        elif self.config.template_type == PluginTemplateType.FORMATTER:
            files[f"src/{pkg_name}/formatter.py"] = self._get_formatter_impl()
        elif self.config.template_type == PluginTemplateType.HOOK:
            files[f"src/{pkg_name}/hooks.py"] = self._get_hook_impl()
        elif self.config.template_type == PluginTemplateType.COMMAND:
            files[f"src/{pkg_name}/command.py"] = self._get_command_impl()

        # Configuration files
        files["pyproject.toml"] = self._get_pyproject_toml()
        files["README.md"] = self._get_readme()
        files["LICENSE"] = self._get_license()
        files[".gitignore"] = self._get_gitignore()
        files["plugin.json"] = self._get_plugin_json()

        # Tests
        if self.config.include_tests:
            files["tests/__init__.py"] = ""
            files["tests/conftest.py"] = self._get_conftest()
            files["tests/test_plugin.py"] = self._get_test_plugin()

        # Docs
        if self.config.include_docs:
            files["docs/index.md"] = self._get_docs_index()
            files["docs/installation.md"] = self._get_docs_install()
            files["docs/usage.md"] = self._get_docs_usage()

        # CI/CD
        if self.config.include_ci:
            files[".github/workflows/ci.yml"] = self._get_github_ci()

        # Docker
        if self.config.include_docker:
            files["Dockerfile"] = self._get_dockerfile()

        return files

    def _get_init_py(self) -> str:
        """Generate __init__.py content."""
        plugin_class = self._get_plugin_class_name()

        return f'''"""
{self.config.description}

A spectra plugin for {self.config.template_type.name.lower()} functionality.
"""

from .plugin import {plugin_class}, create_plugin

__version__ = "{self.config.version}"

__all__ = [
    "{plugin_class}",
    "create_plugin",
]
'''

    def _get_plugin_class_name(self) -> str:
        """Get the plugin class name."""
        # Convert snake_case to PascalCase
        parts = self.config.name.split("_")
        name = "".join(p.title() for p in parts)
        return f"{name}Plugin"

    def _get_plugin_py(self) -> str:
        """Generate main plugin.py content."""
        plugin_class = self._get_plugin_class_name()
        base_class = self._get_base_class()
        plugin_type = self.config.template_type.name

        return f'''"""
{self.config.name} Plugin - Main plugin implementation.

This module provides the plugin entry point and metadata.
"""

from typing import Any

from spectryn.plugins.base import {base_class}, PluginMetadata, PluginType


class {plugin_class}({base_class}):
    """
    {self.config.description}

    This plugin provides {self.config.template_type.name.lower()} functionality
    for the spectra sync tool.
    """

    # Configuration schema for validation
    CONFIG_SCHEMA = {{
        "type": "object",
        "properties": {{
            # Add your configuration options here
            "enabled": {{
                "type": "boolean",
                "description": "Enable this plugin",
                "default": True,
            }},
        }},
    }}

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """
        Initialize the plugin.

        Args:
            config: Optional plugin configuration
        """
        super().__init__(config)
        self._impl = None

    @property
    def metadata(self) -> PluginMetadata:
        """Get plugin metadata."""
        return PluginMetadata(
            name="{self.config.name}",
            version="{self.config.version}",
            description="{self.config.description}",
            author="{self.config.author_name}",
            plugin_type=PluginType.{plugin_type},
            requires=[],
            config_schema=self.CONFIG_SCHEMA,
        )

    def initialize(self) -> None:
        """Initialize the plugin resources."""
        # Initialize your implementation here
        self._initialized = True

    def shutdown(self) -> None:
        """Cleanup plugin resources."""
        self._impl = None
        self._initialized = False

{self._get_plugin_methods()}


def create_plugin(config: dict[str, Any] | None = None) -> {plugin_class}:
    """
    Factory function for plugin creation.

    This function is used by the plugin discovery system.

    Args:
        config: Plugin configuration

    Returns:
        Configured plugin instance
    """
    return {plugin_class}(config)
'''

    def _get_base_class(self) -> str:
        """Get the base class for the plugin type."""
        type_to_class = {
            PluginTemplateType.PARSER: "ParserPlugin",
            PluginTemplateType.TRACKER: "TrackerPlugin",
            PluginTemplateType.FORMATTER: "FormatterPlugin",
            PluginTemplateType.HOOK: "Plugin",
            PluginTemplateType.COMMAND: "Plugin",
        }
        return type_to_class[self.config.template_type]

    def _get_plugin_methods(self) -> str:
        """Get type-specific plugin methods."""
        if self.config.template_type == PluginTemplateType.PARSER:
            return '''    def get_parser(self) -> Any:
        """
        Get the parser instance.

        Returns:
            Parser implementing DocumentParserPort
        """
        from .parser import {name}Parser
        if self._impl is None:
            self._impl = {name}Parser()
        return self._impl
'''.format(name=self._get_plugin_class_name().replace("Plugin", ""))

        if self.config.template_type == PluginTemplateType.TRACKER:
            return '''    def get_tracker(self) -> Any:
        """
        Get the tracker adapter instance.

        Returns:
            Adapter implementing IssueTrackerPort
        """
        from .adapter import {name}Adapter
        if self._impl is None:
            self._impl = {name}Adapter(self.config)
        return self._impl
'''.format(name=self._get_plugin_class_name().replace("Plugin", ""))

        if self.config.template_type == PluginTemplateType.FORMATTER:
            return '''    def get_formatter(self) -> Any:
        """
        Get the formatter instance.

        Returns:
            Formatter implementing DocumentFormatterPort
        """
        from .formatter import {name}Formatter
        if self._impl is None:
            self._impl = {name}Formatter()
        return self._impl
'''.format(name=self._get_plugin_class_name().replace("Plugin", ""))

        return '''    def execute(self, context: dict[str, Any]) -> Any:
        """
        Execute the plugin functionality.

        Args:
            context: Execution context

        Returns:
            Plugin result
        """
        # Implement your plugin logic here
        pass
'''

    def _get_parser_impl(self) -> str:
        """Generate parser implementation template."""
        name = self._get_plugin_class_name().replace("Plugin", "")

        return f'''"""
{name} Parser - Document parser implementation.

This module provides the parser for {self.config.name} format documents.
"""

from typing import Any

from spectryn.core.domain.entities import Epic
from spectryn.core.ports.document_parser import DocumentParserPort, ParserError


class {name}Parser(DocumentParserPort):
    """
    Parser for {self.config.name} format documents.

    Implements DocumentParserPort to parse {self.config.name} files
    into spectra domain entities.
    """

    def __init__(self) -> None:
        """Initialize the parser."""
        pass

    def parse(self, content: str) -> Epic:
        """
        Parse document content into an Epic.

        Args:
            content: Document content string

        Returns:
            Parsed Epic entity

        Raises:
            ParserError: If parsing fails
        """
        try:
            # TODO: Implement parsing logic
            # This should parse the content and return an Epic with stories

            raise NotImplementedError("Parser not yet implemented")

        except Exception as e:
            raise ParserError(f"Failed to parse {self.config.name} document: {{e}}") from e

    def validate(self, content: str) -> list[str]:
        """
        Validate document structure without full parsing.

        Args:
            content: Document content string

        Returns:
            List of validation error messages (empty if valid)
        """
        errors: list[str] = []

        # TODO: Add validation logic

        return errors

    def get_supported_extensions(self) -> list[str]:
        """
        Get list of supported file extensions.

        Returns:
            List of extensions (e.g., ['.json', '.yaml'])
        """
        # TODO: Return your supported extensions
        return []
'''

    def _get_tracker_impl(self) -> str:
        """Generate tracker adapter implementation template."""
        name = self._get_plugin_class_name().replace("Plugin", "")

        return f'''"""
{name} Adapter - Issue tracker adapter implementation.

This module provides the adapter for {self.config.name} issue tracker integration.
"""

from typing import Any

from spectryn.core.domain.entities import Epic, UserStory, Subtask
from spectryn.core.domain.enums import Status, Priority
from spectryn.core.ports.issue_tracker import IssueTrackerPort, IssueTrackerError

from .client import {name}Client


class {name}Adapter(IssueTrackerPort):
    """
    Adapter for {self.config.name} issue tracker.

    Implements IssueTrackerPort to sync stories with {self.config.name}.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """
        Initialize the adapter.

        Args:
            config: Adapter configuration including credentials
        """
        self._client = {name}Client(
            api_url=config.get("api_url", ""),
            api_token=config.get("api_token", ""),
        )
        self._project_key = config.get("project_key", "")

    def get_epic(self, epic_key: str) -> Epic:
        """
        Retrieve an epic from the tracker.

        Args:
            epic_key: Epic identifier

        Returns:
            Epic entity with stories

        Raises:
            IssueTrackerError: If retrieval fails
        """
        # TODO: Implement epic retrieval
        raise NotImplementedError("get_epic not yet implemented")

    def create_story(self, story: UserStory, epic_key: str) -> str:
        """
        Create a new story in the tracker.

        Args:
            story: Story to create
            epic_key: Parent epic key

        Returns:
            Created story key

        Raises:
            IssueTrackerError: If creation fails
        """
        # TODO: Implement story creation
        raise NotImplementedError("create_story not yet implemented")

    def update_story(self, story: UserStory) -> None:
        """
        Update an existing story.

        Args:
            story: Story with updated fields

        Raises:
            IssueTrackerError: If update fails
        """
        # TODO: Implement story update
        raise NotImplementedError("update_story not yet implemented")

    def delete_story(self, story_key: str) -> None:
        """
        Delete a story from the tracker.

        Args:
            story_key: Story identifier

        Raises:
            IssueTrackerError: If deletion fails
        """
        # TODO: Implement story deletion
        raise NotImplementedError("delete_story not yet implemented")

    def create_subtask(self, subtask: Subtask, story_key: str) -> str:
        """
        Create a subtask under a story.

        Args:
            subtask: Subtask to create
            story_key: Parent story key

        Returns:
            Created subtask key

        Raises:
            IssueTrackerError: If creation fails
        """
        # TODO: Implement subtask creation
        raise NotImplementedError("create_subtask not yet implemented")

    def update_subtask(self, subtask: Subtask) -> None:
        """
        Update an existing subtask.

        Args:
            subtask: Subtask with updated fields

        Raises:
            IssueTrackerError: If update fails
        """
        # TODO: Implement subtask update
        raise NotImplementedError("update_subtask not yet implemented")

    def delete_subtask(self, subtask_key: str) -> None:
        """
        Delete a subtask from the tracker.

        Args:
            subtask_key: Subtask identifier

        Raises:
            IssueTrackerError: If deletion fails
        """
        # TODO: Implement subtask deletion
        raise NotImplementedError("delete_subtask not yet implemented")

    def transition_status(self, issue_key: str, status: Status) -> None:
        """
        Transition an issue to a new status.

        Args:
            issue_key: Issue identifier
            status: Target status

        Raises:
            IssueTrackerError: If transition fails
        """
        # TODO: Implement status transition
        raise NotImplementedError("transition_status not yet implemented")
'''

    def _get_client_impl(self) -> str:
        """Generate API client implementation template."""
        name = self._get_plugin_class_name().replace("Plugin", "")

        return f'''"""
{name} Client - Low-level API client for {self.config.name}.

This module provides HTTP client functionality for the {self.config.name} API.
"""

from typing import Any

import requests


class {name}ClientError(Exception):
    """Error from {name} API client."""
    pass


class {name}Client:
    """
    Low-level HTTP client for {self.config.name} API.

    Handles authentication, request construction, and error handling.
    """

    def __init__(
        self,
        api_url: str,
        api_token: str,
        timeout: int = 30,
    ) -> None:
        """
        Initialize the client.

        Args:
            api_url: Base URL for the API
            api_token: Authentication token
            timeout: Request timeout in seconds
        """
        self.api_url = api_url.rstrip("/")
        self.api_token = api_token
        self.timeout = timeout

        self._session = requests.Session()
        self._setup_auth()

    def _setup_auth(self) -> None:
        """Configure authentication headers."""
        # TODO: Set up your authentication headers
        self._session.headers.update({{
            "Authorization": f"Bearer {{self.api_token}}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }})

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> Any:
        """
        Make an API request.

        Args:
            method: HTTP method
            endpoint: API endpoint path
            params: Query parameters
            data: Request body data

        Returns:
            Response JSON

        Raises:
            {name}ClientError: If request fails
        """
        url = f"{{self.api_url}}{{endpoint}}"

        try:
            response = self._session.request(
                method=method,
                url=url,
                params=params,
                json=data,
                timeout=self.timeout,
            )

            response.raise_for_status()

            if response.text:
                return response.json()
            return None

        except requests.exceptions.HTTPError as e:
            raise {name}ClientError(f"API error: {{e.response.status_code}} - {{e.response.text}}") from e
        except requests.exceptions.RequestException as e:
            raise {name}ClientError(f"Request failed: {{e}}") from e

    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        """Make a GET request."""
        return self._request("GET", endpoint, params=params)

    def post(self, endpoint: str, data: dict[str, Any] | None = None) -> Any:
        """Make a POST request."""
        return self._request("POST", endpoint, data=data)

    def put(self, endpoint: str, data: dict[str, Any] | None = None) -> Any:
        """Make a PUT request."""
        return self._request("PUT", endpoint, data=data)

    def delete(self, endpoint: str) -> Any:
        """Make a DELETE request."""
        return self._request("DELETE", endpoint)

    def close(self) -> None:
        """Close the session."""
        self._session.close()
'''

    def _get_formatter_impl(self) -> str:
        """Generate formatter implementation template."""
        name = self._get_plugin_class_name().replace("Plugin", "")

        return f'''"""
{name} Formatter - Output formatter implementation.

This module provides formatting for {self.config.name} output format.
"""

from typing import Any

from spectryn.core.domain.entities import Epic, UserStory
from spectryn.core.ports.document_formatter import DocumentFormatterPort


class {name}Formatter(DocumentFormatterPort):
    """
    Formatter for {self.config.name} output format.

    Implements DocumentFormatterPort to format stories for {self.config.name}.
    """

    def __init__(self) -> None:
        """Initialize the formatter."""
        pass

    def format_epic(self, epic: Epic) -> str:
        """
        Format an epic for output.

        Args:
            epic: Epic to format

        Returns:
            Formatted string
        """
        # TODO: Implement epic formatting
        raise NotImplementedError("format_epic not yet implemented")

    def format_story(self, story: UserStory) -> str:
        """
        Format a story for output.

        Args:
            story: Story to format

        Returns:
            Formatted string
        """
        # TODO: Implement story formatting
        raise NotImplementedError("format_story not yet implemented")

    def format_description(self, description: str) -> str:
        """
        Format a description field.

        Args:
            description: Raw description text

        Returns:
            Formatted description
        """
        # TODO: Implement description formatting
        return description
'''

    def _get_hook_impl(self) -> str:
        """Generate hook implementation template."""
        name = self._get_plugin_class_name().replace("Plugin", "")

        return f'''"""
{name} Hooks - Processing hooks for {self.config.name}.

This module provides hook implementations for extending spectra functionality.
"""

from typing import Any

from spectryn.plugins.hooks import Hook, HookContext, HookPoint


class PreSync{name}Hook(Hook):
    """
    Hook that runs before sync operations.

    Use this to validate or modify data before syncing.
    """

    @property
    def hook_point(self) -> HookPoint:
        """Get the hook point."""
        return HookPoint.PRE_SYNC

    @property
    def priority(self) -> int:
        """Get hook priority (lower = runs first)."""
        return 100

    def execute(self, context: HookContext) -> HookContext:
        """
        Execute the hook.

        Args:
            context: Hook execution context

        Returns:
            Modified context
        """
        # TODO: Implement hook logic
        return context


class PostSync{name}Hook(Hook):
    """
    Hook that runs after sync operations.

    Use this for cleanup, notifications, or logging.
    """

    @property
    def hook_point(self) -> HookPoint:
        """Get the hook point."""
        return HookPoint.POST_SYNC

    @property
    def priority(self) -> int:
        """Get hook priority (lower = runs first)."""
        return 100

    def execute(self, context: HookContext) -> HookContext:
        """
        Execute the hook.

        Args:
            context: Hook execution context

        Returns:
            Modified context
        """
        # TODO: Implement hook logic
        return context
'''

    def _get_command_impl(self) -> str:
        """Generate command implementation template."""
        name = self._get_plugin_class_name().replace("Plugin", "")

        return f'''"""
{name} Command - Custom CLI command for {self.config.name}.

This module provides a custom CLI command extending spectra.
"""

import argparse
from typing import Any


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """
    Add command-specific arguments.

    Args:
        parser: Argument parser to add arguments to
    """
    parser.add_argument(
        "--{self.config.name.replace("_", "-")}-option",
        type=str,
        help="An option for the {self.config.name} command",
    )


def execute(args: argparse.Namespace) -> int:
    """
    Execute the command.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 for success)
    """
    # TODO: Implement command logic
    print(f"Running {self.config.name} command...")

    return 0
'''

    def _get_pyproject_toml(self) -> str:
        """Generate pyproject.toml content."""
        keywords = ", ".join(f'"{k}"' for k in self.config.keywords)
        type_keyword = f'"spectra-{self.config.template_type.name.lower()}"'

        return f"""[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "spectra-{self.config.name}"
version = "{self.config.version}"
description = "{self.config.description}"
readme = "README.md"
license = "{self.config.license}"
requires-python = "{self.config.python_requires}"
authors = [
    {{ name = "{self.config.author_name}", email = "{self.config.author_email or ""}" }},
]
keywords = ["spectra", "spectra-plugin", {type_keyword}, {keywords}]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
]
dependencies = [
    "spectra-sync>=0.1.0",
    "requests>=2.28.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-cov>=4.0.0",
    "ruff>=0.1.0",
    "mypy>=1.0.0",
]

[project.urls]
Homepage = "{self.config.homepage_url or f"https://github.com/{self.config.author_name}/spectra-{self.config.name}"}"
Repository = "{self.config.repository_url or f"https://github.com/{self.config.author_name}/spectra-{self.config.name}"}"
Documentation = "{self.config.homepage_url or f"https://github.com/{self.config.author_name}/spectra-{self.config.name}"}"

[project.entry-points."spectryn.plugins"]
{self.config.name} = "spectra_{self.config.name}:create_plugin"

[tool.setuptools.packages.find]
where = ["src"]

[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]

[tool.mypy]
python_version = "3.11"
strict = true

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = "test_*.py"
"""

    def _get_readme(self) -> str:
        """Generate README.md content."""
        return f"""# spectra-{self.config.name}

{self.config.description}

A spectra plugin for {self.config.template_type.name.lower()} functionality.

## Installation

```bash
pip install spectra-{self.config.name}
```

Or install from source:

```bash
git clone {self.config.repository_url or f"https://github.com/{self.config.author_name}/spectra-{self.config.name}"}
cd spectra-{self.config.name}
pip install -e ".[dev]"
```

## Usage

After installation, the plugin will be automatically discovered by spectra.

```bash
# Verify plugin is loaded
spectra plugin list
```

### Configuration

Add to your `.spectra.yaml`:

```yaml
plugins:
  {self.config.name}:
    enabled: true
    # Add your configuration options here
```

## Development

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linting
ruff check src tests
ruff format src tests

# Type checking
mypy src
```

## License

{self.config.license}

## Author

{self.config.author_name}{f" <{self.config.author_email}>" if self.config.author_email else ""}
"""

    def _get_license(self) -> str:
        """Generate LICENSE file content."""
        year = datetime.now().year

        if self.config.license == "MIT":
            return f"""MIT License

Copyright (c) {year} {self.config.author_name}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
        if self.config.license == "Apache-2.0":
            return f"""Apache License
Version 2.0, January 2004
http://www.apache.org/licenses/

Copyright {year} {self.config.author_name}

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
        return f"Copyright (c) {year} {self.config.author_name}\n\nLicense: {self.config.license}"

    def _get_gitignore(self) -> str:
        """Generate .gitignore content."""
        return """# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual environments
.env
.venv
env/
venv/
ENV/

# IDE
.idea/
.vscode/
*.swp
*.swo
*~

# Testing
.tox/
.coverage
.coverage.*
htmlcov/
.pytest_cache/
.mypy_cache/

# Build
*.manifest
*.spec

# Documentation
docs/_build/
site/

# OS
.DS_Store
Thumbs.db
"""

    def _get_plugin_json(self) -> str:
        """Generate plugin.json content."""
        import json

        data = {
            "name": self.config.name,
            "version": self.config.version,
            "description": self.config.description,
            "type": self.config.template_type.name.lower(),
            "author": {
                "name": self.config.author_name,
                "email": self.config.author_email,
            },
            "repository": self.config.repository_url,
            "keywords": ["spectra", "spectra-plugin", *self.config.keywords],
            "spectra": {
                "minVersion": "0.1.0",
            },
        }

        return json.dumps(data, indent=2) + "\n"

    def _get_conftest(self) -> str:
        """Generate tests/conftest.py content."""
        return '''"""
Test fixtures for plugin tests.
"""

import pytest


@pytest.fixture
def plugin_config():
    """Provide default plugin configuration."""
    return {
        "enabled": True,
    }
'''

    def _get_test_plugin(self) -> str:
        """Generate tests/test_plugin.py content."""
        plugin_class = self._get_plugin_class_name()
        pkg_name = f"spectra_{self.config.name}"

        return f'''"""
Tests for {self.config.name} plugin.
"""

import pytest

from {pkg_name} import {plugin_class}, create_plugin


class Test{plugin_class}:
    """Tests for the main plugin class."""

    def test_create_plugin(self):
        """Test plugin creation via factory function."""
        plugin = create_plugin()

        assert plugin is not None
        assert isinstance(plugin, {plugin_class})

    def test_create_plugin_with_config(self, plugin_config):
        """Test plugin creation with configuration."""
        plugin = create_plugin(plugin_config)

        assert plugin.config == plugin_config

    def test_metadata(self):
        """Test plugin metadata."""
        plugin = create_plugin()
        meta = plugin.metadata

        assert meta.name == "{self.config.name}"
        assert meta.version == "{self.config.version}"
        assert meta.description

    def test_initialize(self):
        """Test plugin initialization."""
        plugin = create_plugin()

        assert not plugin.is_initialized

        plugin.initialize()

        assert plugin.is_initialized

    def test_shutdown(self):
        """Test plugin shutdown."""
        plugin = create_plugin()
        plugin.initialize()

        assert plugin.is_initialized

        plugin.shutdown()

        assert not plugin.is_initialized

    def test_config_validation(self):
        """Test configuration validation."""
        plugin = create_plugin({{"enabled": True}})

        errors = plugin.validate_config()

        assert errors == []
'''

    def _get_docs_index(self) -> str:
        """Generate docs/index.md content."""
        return f"""# spectra-{self.config.name}

{self.config.description}

## Overview

This plugin provides {self.config.template_type.name.lower()} functionality for spectra,
the markdown-to-issue-tracker sync tool.

## Quick Start

1. Install the plugin:

   ```bash
   pip install spectra-{self.config.name}
   ```

2. Configure in `.spectra.yaml`:

   ```yaml
   plugins:
     {self.config.name}:
       enabled: true
   ```

3. Run spectra as usual - the plugin will be automatically loaded.

## Documentation

- [Installation](installation.md)
- [Usage](usage.md)

## Support

For issues and feature requests, please use the
[GitHub issue tracker]({self.config.repository_url or f"https://github.com/{self.config.author_name}/spectra-{self.config.name}"}/issues).
"""

    def _get_docs_install(self) -> str:
        """Generate docs/installation.md content."""
        return f"""# Installation

## Requirements

- Python {self.config.python_requires}
- spectra >= 0.1.0

## Install from PyPI

```bash
pip install spectra-{self.config.name}
```

## Install from Source

```bash
git clone {self.config.repository_url or f"https://github.com/{self.config.author_name}/spectra-{self.config.name}"}
cd spectra-{self.config.name}
pip install -e .
```

## Development Installation

For contributing to the plugin:

```bash
pip install -e ".[dev]"
```

## Verify Installation

```bash
spectra plugin list
```

You should see `{self.config.name}` in the list of installed plugins.
"""

    def _get_docs_usage(self) -> str:
        """Generate docs/usage.md content."""
        return f"""# Usage

## Configuration

Add the plugin configuration to your `.spectra.yaml`:

```yaml
plugins:
  {self.config.name}:
    enabled: true
    # Add your configuration options here
```

## Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | boolean | `true` | Enable/disable the plugin |

## Examples

### Basic Usage

```bash
spectra sync -f EPIC.md -e PROJ-123
```

The plugin will automatically be used during sync operations.

### Verbose Output

```bash
spectra sync -f EPIC.md -e PROJ-123 --verbose
```

## Troubleshooting

### Plugin Not Loading

1. Verify installation: `spectra plugin list`
2. Check configuration in `.spectra.yaml`
3. Run with `--verbose` for detailed output

### Common Issues

- **Issue**: Plugin not found
  **Solution**: Ensure package is installed in same Python environment as spectra

- **Issue**: Configuration errors
  **Solution**: Check YAML syntax and required options
"""

    def _get_github_ci(self) -> str:
        """Generate .github/workflows/ci.yml content."""
        return f"""name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12", "3.13"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{{{ matrix.python-version }}}}
        uses: actions/setup-python@v5
        with:
          python-version: ${{{{ matrix.python-version }}}}

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]"

      - name: Run linting
        run: |
          ruff check src tests
          ruff format --check src tests

      - name: Run type checking
        run: |
          mypy src

      - name: Run tests
        run: |
          pytest --cov=spectra_{self.config.name} --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          files: coverage.xml
          fail_ci_if_error: false

  publish:
    needs: test
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install build tools
        run: |
          python -m pip install --upgrade pip build twine

      - name: Build package
        run: python -m build

      - name: Publish to PyPI
        env:
          TWINE_USERNAME: __token__
          TWINE_PASSWORD: ${{{{ secrets.PYPI_API_TOKEN }}}}
        run: twine upload dist/*
"""

    def _get_dockerfile(self) -> str:
        """Generate Dockerfile content."""
        return f"""FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml .
COPY README.md .
COPY src/ src/

RUN pip install --no-cache-dir .

# Default command
CMD ["python", "-c", "from spectra_{self.config.name} import create_plugin; print(create_plugin().metadata)"]
"""


def scaffold_plugin(
    name: str,
    description: str,
    template_type: PluginTemplateType,
    output_dir: Path,
    author_name: str,
    author_email: str | None = None,
    **kwargs: Any,
) -> list[Path]:
    """
    Scaffold a new plugin project.

    This is a convenience function that creates a PluginScaffoldConfig
    and generates the plugin structure.

    Args:
        name: Plugin name (lowercase, underscores allowed)
        description: Plugin description
        template_type: Type of plugin to create
        output_dir: Directory to create plugin in
        author_name: Author name
        author_email: Author email (optional)
        **kwargs: Additional configuration options

    Returns:
        List of created file paths
    """
    config = PluginScaffoldConfig(
        name=name,
        description=description,
        template_type=template_type,
        author_name=author_name,
        author_email=author_email,
        **kwargs,
    )

    scaffold = PluginScaffold(config)
    return scaffold.generate(output_dir)
