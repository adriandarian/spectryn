"""
Tests for Plugin Templates and Scaffold functionality.
"""

import json
from pathlib import Path

import pytest

from spectryn.plugins.templates import PluginScaffold, PluginTemplateType, scaffold_plugin
from spectryn.plugins.templates.scaffold import PluginScaffoldConfig


class TestPluginTemplateType:
    """Tests for PluginTemplateType enum."""

    def test_all_types_exist(self):
        """Test all expected template types are defined."""
        assert PluginTemplateType.PARSER
        assert PluginTemplateType.TRACKER
        assert PluginTemplateType.FORMATTER
        assert PluginTemplateType.HOOK
        assert PluginTemplateType.COMMAND


class TestPluginScaffoldConfig:
    """Tests for PluginScaffoldConfig dataclass."""

    def test_create_basic_config(self):
        """Test creating config with required fields."""
        config = PluginScaffoldConfig(
            name="test_plugin",
            description="A test plugin for testing",
            template_type=PluginTemplateType.PARSER,
            author_name="Test Author",
        )

        assert config.name == "test_plugin"
        assert config.description == "A test plugin for testing"
        assert config.template_type == PluginTemplateType.PARSER
        assert config.author_name == "Test Author"
        assert config.version == "0.1.0"
        assert config.license == "MIT"

    def test_create_full_config(self):
        """Test creating config with all fields."""
        config = PluginScaffoldConfig(
            name="full_plugin",
            description="A fully configured plugin",
            template_type=PluginTemplateType.TRACKER,
            author_name="Full Author",
            author_email="full@example.com",
            version="1.0.0",
            license="Apache-2.0",
            repository_url="https://github.com/test/full_plugin",
            include_tests=True,
            include_docs=True,
            include_ci=True,
            include_docker=True,
            keywords=["test", "plugin"],
        )

        assert config.version == "1.0.0"
        assert config.license == "Apache-2.0"
        assert config.include_docker is True


class TestPluginScaffold:
    """Tests for PluginScaffold class."""

    @pytest.fixture
    def basic_config(self):
        """Create a basic scaffold config."""
        return PluginScaffoldConfig(
            name="test_parser",
            description="A test parser plugin for testing",
            template_type=PluginTemplateType.PARSER,
            author_name="Test Author",
            author_email="test@example.com",
        )

    @pytest.fixture
    def tracker_config(self):
        """Create a tracker scaffold config."""
        return PluginScaffoldConfig(
            name="test_tracker",
            description="A test tracker plugin for testing",
            template_type=PluginTemplateType.TRACKER,
            author_name="Test Author",
        )

    def test_validate_valid_name(self, basic_config):
        """Test validation passes for valid name."""
        scaffold = PluginScaffold(basic_config)
        assert scaffold.config.name == "test_parser"

    def test_validate_invalid_name_uppercase(self):
        """Test validation fails for uppercase name."""
        config = PluginScaffoldConfig(
            name="TestPlugin",
            description="A test plugin for testing",
            template_type=PluginTemplateType.PARSER,
            author_name="Test",
        )

        with pytest.raises(ValueError, match="Invalid plugin name"):
            PluginScaffold(config)

    def test_validate_invalid_name_starts_with_number(self):
        """Test validation fails for name starting with number."""
        config = PluginScaffoldConfig(
            name="123plugin",
            description="A test plugin for testing",
            template_type=PluginTemplateType.PARSER,
            author_name="Test",
        )

        with pytest.raises(ValueError, match="Invalid plugin name"):
            PluginScaffold(config)

    def test_validate_invalid_name_too_short(self):
        """Test validation fails for name too short."""
        config = PluginScaffoldConfig(
            name="ab",
            description="A test plugin for testing",
            template_type=PluginTemplateType.PARSER,
            author_name="Test",
        )

        with pytest.raises(ValueError, match="at least 3 characters"):
            PluginScaffold(config)

    def test_validate_invalid_description_too_short(self):
        """Test validation fails for description too short."""
        config = PluginScaffoldConfig(
            name="test_plugin",
            description="Short",
            template_type=PluginTemplateType.PARSER,
            author_name="Test",
        )

        with pytest.raises(ValueError, match="at least 10 characters"):
            PluginScaffold(config)

    def test_generate_creates_directory(self, tmp_path, basic_config):
        """Test generate creates plugin directory."""
        scaffold = PluginScaffold(basic_config)

        created_files = scaffold.generate(tmp_path)

        plugin_dir = tmp_path / "spectra-test_parser"
        assert plugin_dir.exists()
        assert len(created_files) > 0

    def test_generate_creates_package_files(self, tmp_path, basic_config):
        """Test generate creates package files."""
        scaffold = PluginScaffold(basic_config)

        scaffold.generate(tmp_path)

        plugin_dir = tmp_path / "spectra-test_parser"
        assert (plugin_dir / "src" / "spectra_test_parser" / "__init__.py").exists()
        assert (plugin_dir / "src" / "spectra_test_parser" / "plugin.py").exists()

    def test_generate_creates_parser_impl(self, tmp_path, basic_config):
        """Test generate creates parser implementation for parser type."""
        scaffold = PluginScaffold(basic_config)

        scaffold.generate(tmp_path)

        plugin_dir = tmp_path / "spectra-test_parser"
        assert (plugin_dir / "src" / "spectra_test_parser" / "parser.py").exists()

    def test_generate_creates_tracker_impl(self, tmp_path, tracker_config):
        """Test generate creates tracker implementation for tracker type."""
        scaffold = PluginScaffold(tracker_config)

        scaffold.generate(tmp_path)

        plugin_dir = tmp_path / "spectra-test_tracker"
        assert (plugin_dir / "src" / "spectra_test_tracker" / "adapter.py").exists()
        assert (plugin_dir / "src" / "spectra_test_tracker" / "client.py").exists()

    def test_generate_creates_pyproject(self, tmp_path, basic_config):
        """Test generate creates pyproject.toml."""
        scaffold = PluginScaffold(basic_config)

        scaffold.generate(tmp_path)

        plugin_dir = tmp_path / "spectra-test_parser"
        pyproject = plugin_dir / "pyproject.toml"

        assert pyproject.exists()

        content = pyproject.read_text()
        assert 'name = "spectra-test_parser"' in content
        assert 'version = "0.1.0"' in content
        assert "spectra-plugin" in content

    def test_generate_creates_readme(self, tmp_path, basic_config):
        """Test generate creates README.md."""
        scaffold = PluginScaffold(basic_config)

        scaffold.generate(tmp_path)

        plugin_dir = tmp_path / "spectra-test_parser"
        readme = plugin_dir / "README.md"

        assert readme.exists()

        content = readme.read_text()
        assert "spectra-test_parser" in content
        assert basic_config.description in content

    def test_generate_creates_license(self, tmp_path, basic_config):
        """Test generate creates LICENSE file."""
        scaffold = PluginScaffold(basic_config)

        scaffold.generate(tmp_path)

        plugin_dir = tmp_path / "spectra-test_parser"
        license_file = plugin_dir / "LICENSE"

        assert license_file.exists()

        content = license_file.read_text()
        assert "MIT License" in content
        assert basic_config.author_name in content

    def test_generate_creates_gitignore(self, tmp_path, basic_config):
        """Test generate creates .gitignore."""
        scaffold = PluginScaffold(basic_config)

        scaffold.generate(tmp_path)

        plugin_dir = tmp_path / "spectra-test_parser"
        gitignore = plugin_dir / ".gitignore"

        assert gitignore.exists()

        content = gitignore.read_text()
        assert "__pycache__" in content
        assert ".venv" in content

    def test_generate_creates_plugin_json(self, tmp_path, basic_config):
        """Test generate creates plugin.json."""
        scaffold = PluginScaffold(basic_config)

        scaffold.generate(tmp_path)

        plugin_dir = tmp_path / "spectra-test_parser"
        plugin_json = plugin_dir / "plugin.json"

        assert plugin_json.exists()

        data = json.loads(plugin_json.read_text())
        assert data["name"] == "test_parser"
        assert data["version"] == "0.1.0"
        assert data["type"] == "parser"

    def test_generate_creates_tests(self, tmp_path, basic_config):
        """Test generate creates test files when include_tests=True."""
        scaffold = PluginScaffold(basic_config)

        scaffold.generate(tmp_path)

        plugin_dir = tmp_path / "spectra-test_parser"
        assert (plugin_dir / "tests" / "__init__.py").exists()
        assert (plugin_dir / "tests" / "conftest.py").exists()
        assert (plugin_dir / "tests" / "test_plugin.py").exists()

    def test_generate_skips_tests_when_disabled(self, tmp_path):
        """Test generate skips tests when include_tests=False."""
        config = PluginScaffoldConfig(
            name="no_tests",
            description="Plugin without tests",
            template_type=PluginTemplateType.HOOK,
            author_name="Test",
            include_tests=False,
        )
        scaffold = PluginScaffold(config)

        scaffold.generate(tmp_path)

        plugin_dir = tmp_path / "spectra-no_tests"
        assert not (plugin_dir / "tests").exists()

    def test_generate_creates_docs(self, tmp_path, basic_config):
        """Test generate creates documentation when include_docs=True."""
        scaffold = PluginScaffold(basic_config)

        scaffold.generate(tmp_path)

        plugin_dir = tmp_path / "spectra-test_parser"
        assert (plugin_dir / "docs" / "index.md").exists()
        assert (plugin_dir / "docs" / "installation.md").exists()
        assert (plugin_dir / "docs" / "usage.md").exists()

    def test_generate_creates_ci(self, tmp_path, basic_config):
        """Test generate creates CI config when include_ci=True."""
        scaffold = PluginScaffold(basic_config)

        scaffold.generate(tmp_path)

        plugin_dir = tmp_path / "spectra-test_parser"
        ci_file = plugin_dir / ".github" / "workflows" / "ci.yml"

        assert ci_file.exists()

        content = ci_file.read_text()
        assert "pytest" in content
        assert "ruff" in content
        assert "mypy" in content

    def test_generate_creates_dockerfile(self, tmp_path):
        """Test generate creates Dockerfile when include_docker=True."""
        config = PluginScaffoldConfig(
            name="docker_plugin",
            description="Plugin with Docker support",
            template_type=PluginTemplateType.HOOK,
            author_name="Test",
            include_docker=True,
        )
        scaffold = PluginScaffold(config)

        scaffold.generate(tmp_path)

        plugin_dir = tmp_path / "spectra-docker_plugin"
        dockerfile = plugin_dir / "Dockerfile"

        assert dockerfile.exists()

        content = dockerfile.read_text()
        assert "FROM python" in content


class TestPluginTemplateTypes:
    """Tests for different plugin template types."""

    @pytest.fixture
    def make_config(self):
        """Factory for creating configs of different types."""

        def _make_config(template_type: PluginTemplateType, name: str):
            return PluginScaffoldConfig(
                name=name,
                description=f"A {template_type.name.lower()} plugin for testing",
                template_type=template_type,
                author_name="Test Author",
            )

        return _make_config

    def test_parser_template(self, tmp_path, make_config):
        """Test parser template generates correct files."""
        config = make_config(PluginTemplateType.PARSER, "my_parser")
        scaffold = PluginScaffold(config)

        scaffold.generate(tmp_path)

        plugin_dir = tmp_path / "spectra-my_parser"
        parser_file = plugin_dir / "src" / "spectra_my_parser" / "parser.py"

        assert parser_file.exists()

        content = parser_file.read_text()
        assert "DocumentParserPort" in content
        assert "def parse" in content

    def test_tracker_template(self, tmp_path, make_config):
        """Test tracker template generates correct files."""
        config = make_config(PluginTemplateType.TRACKER, "my_tracker")
        scaffold = PluginScaffold(config)

        scaffold.generate(tmp_path)

        plugin_dir = tmp_path / "spectra-my_tracker"

        adapter_file = plugin_dir / "src" / "spectra_my_tracker" / "adapter.py"
        client_file = plugin_dir / "src" / "spectra_my_tracker" / "client.py"

        assert adapter_file.exists()
        assert client_file.exists()

        adapter_content = adapter_file.read_text()
        assert "IssueTrackerPort" in adapter_content
        assert "def get_epic" in adapter_content
        assert "def create_story" in adapter_content

    def test_formatter_template(self, tmp_path, make_config):
        """Test formatter template generates correct files."""
        config = make_config(PluginTemplateType.FORMATTER, "my_formatter")
        scaffold = PluginScaffold(config)

        scaffold.generate(tmp_path)

        plugin_dir = tmp_path / "spectra-my_formatter"
        formatter_file = plugin_dir / "src" / "spectra_my_formatter" / "formatter.py"

        assert formatter_file.exists()

        content = formatter_file.read_text()
        assert "DocumentFormatterPort" in content
        assert "def format_epic" in content
        assert "def format_story" in content

    def test_hook_template(self, tmp_path, make_config):
        """Test hook template generates correct files."""
        config = make_config(PluginTemplateType.HOOK, "my_hook")
        scaffold = PluginScaffold(config)

        scaffold.generate(tmp_path)

        plugin_dir = tmp_path / "spectra-my_hook"
        hooks_file = plugin_dir / "src" / "spectra_my_hook" / "hooks.py"

        assert hooks_file.exists()

        content = hooks_file.read_text()
        assert "Hook" in content
        assert "HookPoint" in content
        assert "PRE_SYNC" in content
        assert "POST_SYNC" in content

    def test_command_template(self, tmp_path, make_config):
        """Test command template generates correct files."""
        config = make_config(PluginTemplateType.COMMAND, "my_command")
        scaffold = PluginScaffold(config)

        scaffold.generate(tmp_path)

        plugin_dir = tmp_path / "spectra-my_command"
        command_file = plugin_dir / "src" / "spectra_my_command" / "command.py"

        assert command_file.exists()

        content = command_file.read_text()
        assert "argparse" in content
        assert "def add_arguments" in content
        assert "def execute" in content


class TestScaffoldPluginFunction:
    """Tests for the scaffold_plugin convenience function."""

    def test_scaffold_plugin_creates_structure(self, tmp_path):
        """Test scaffold_plugin function creates complete structure."""
        created_files = scaffold_plugin(
            name="quick_plugin",
            description="A quick plugin created with the function",
            template_type=PluginTemplateType.HOOK,
            output_dir=tmp_path,
            author_name="Quick Author",
        )

        assert len(created_files) > 0
        assert (tmp_path / "spectra-quick_plugin").exists()

    def test_scaffold_plugin_with_all_options(self, tmp_path):
        """Test scaffold_plugin with all options."""
        created_files = scaffold_plugin(
            name="full_plugin",
            description="A fully configured plugin",
            template_type=PluginTemplateType.PARSER,
            output_dir=tmp_path,
            author_name="Full Author",
            author_email="full@example.com",
            version="1.0.0",
            license="Apache-2.0",
            keywords=["custom", "keywords"],
        )

        assert len(created_files) > 0

        plugin_json = tmp_path / "spectra-full_plugin" / "plugin.json"
        data = json.loads(plugin_json.read_text())

        assert data["version"] == "1.0.0"
        assert "custom" in data["keywords"]


class TestPluginEntryPoint:
    """Tests for plugin entry point configuration."""

    def test_entry_point_in_pyproject(self, tmp_path):
        """Test entry point is correctly configured in pyproject.toml."""
        config = PluginScaffoldConfig(
            name="entry_test",
            description="Plugin with entry point",
            template_type=PluginTemplateType.PARSER,
            author_name="Test",
        )
        scaffold = PluginScaffold(config)

        scaffold.generate(tmp_path)

        pyproject = tmp_path / "spectra-entry_test" / "pyproject.toml"
        content = pyproject.read_text()

        # Check entry point is defined
        assert '[project.entry-points."spectryn.plugins"]' in content
        assert 'entry_test = "spectra_entry_test:create_plugin"' in content
