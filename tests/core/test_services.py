"""
Tests for core services module.

Tests factory functions and service registration.
"""

from unittest.mock import MagicMock, patch

import pytest

from spectryn.core.container import Container
from spectryn.core.ports.config_provider import SyncConfig, TrackerConfig
from spectryn.core.ports.document_formatter import DocumentFormatterPort
from spectryn.core.ports.document_parser import DocumentParserPort
from spectryn.core.ports.issue_tracker import IssueTrackerPort
from spectryn.core.services import (
    AppConfig,
    DryRunMode,
    create_formatter_factory,
    create_output_factory,
    create_parser_factory,
    create_sync_orchestrator,
    create_test_container,
    create_tracker_factory,
    register_defaults,
    register_for_sync,
)


@pytest.fixture
def mock_tracker_config():
    """Create a mock TrackerConfig."""
    return TrackerConfig(
        url="https://test.atlassian.net",
        email="test@example.com",
        api_token="test_token_123",
        project_key="PROJ",
    )


@pytest.fixture
def mock_sync_config():
    """Create a mock SyncConfig."""
    return SyncConfig()


@pytest.fixture
def container():
    """Create a fresh container."""
    return Container()


class TestMarkerTypes:
    """Tests for marker types."""

    def test_app_config_marker(self):
        """Test AppConfig is a valid marker type."""
        config = AppConfig()
        assert config is not None

    def test_dry_run_mode_marker(self):
        """Test DryRunMode is a valid marker type."""
        mode = DryRunMode()
        assert mode is not None


class TestCreateTrackerFactory:
    """Tests for create_tracker_factory."""

    def test_create_jira_factory(self, container, mock_tracker_config):
        """Test creating Jira tracker factory."""
        factory = create_tracker_factory("jira")
        container.register_instance(TrackerConfig, mock_tracker_config)

        with patch("spectryn.adapters.jira.JiraAdapter") as MockJira:
            mock_adapter = MagicMock()
            MockJira.return_value = mock_adapter

            result = factory(container)

            assert result == mock_adapter
            MockJira.assert_called_once()

    def test_create_github_factory(self, container, mock_tracker_config):
        """Test creating GitHub tracker factory."""
        factory = create_tracker_factory("github")
        container.register_instance(TrackerConfig, mock_tracker_config)

        with patch("spectryn.adapters.github.GitHubAdapter") as MockGitHub:
            mock_adapter = MagicMock()
            MockGitHub.return_value = mock_adapter

            result = factory(container)

            assert result == mock_adapter

    def test_create_azure_factory(self, container, mock_tracker_config):
        """Test creating Azure DevOps tracker factory."""
        factory = create_tracker_factory("azure")
        container.register_instance(TrackerConfig, mock_tracker_config)

        with patch("spectryn.adapters.azure_devops.AzureDevOpsAdapter") as MockAzure:
            mock_adapter = MagicMock()
            MockAzure.return_value = mock_adapter

            result = factory(container)

            assert result == mock_adapter

    def test_create_linear_factory(self, container, mock_tracker_config):
        """Test creating Linear tracker factory."""
        factory = create_tracker_factory("linear")
        container.register_instance(TrackerConfig, mock_tracker_config)

        with patch("spectryn.adapters.linear.LinearAdapter") as MockLinear:
            mock_adapter = MagicMock()
            MockLinear.return_value = mock_adapter

            result = factory(container)

            assert result == mock_adapter

    def test_create_asana_factory(self, container, mock_tracker_config):
        """Test creating Asana tracker factory."""
        factory = create_tracker_factory("asana")
        container.register_instance(TrackerConfig, mock_tracker_config)

        with patch("spectryn.adapters.asana.AsanaAdapter") as MockAsana:
            mock_adapter = MagicMock()
            MockAsana.return_value = mock_adapter

            result = factory(container)

            assert result == mock_adapter

    def test_create_unknown_tracker_factory(self, container, mock_tracker_config):
        """Test creating unknown tracker factory raises error."""
        factory = create_tracker_factory("unknown")
        container.register_instance(TrackerConfig, mock_tracker_config)

        with pytest.raises(ValueError, match="Unknown tracker type"):
            factory(container)

    def test_factory_with_dry_run(self, container, mock_tracker_config):
        """Test factory respects dry-run mode."""
        factory = create_tracker_factory("jira")
        container.register_instance(TrackerConfig, mock_tracker_config)
        container.register_instance(DryRunMode, DryRunMode())

        with patch("spectryn.adapters.jira.JiraAdapter") as MockJira:
            mock_adapter = MagicMock()
            MockJira.return_value = mock_adapter

            factory(container)

            # Should be called with dry_run=True
            call_kwargs = MockJira.call_args.kwargs
            assert call_kwargs.get("dry_run") is True


class TestCreateParserFactory:
    """Tests for create_parser_factory."""

    def test_create_markdown_parser(self, container):
        """Test creating markdown parser."""
        factory = create_parser_factory("markdown")

        with patch("spectryn.adapters.parsers.MarkdownParser") as MockParser:
            mock_parser = MagicMock()
            MockParser.return_value = mock_parser

            result = factory(container)

            assert result == mock_parser

    def test_create_yaml_parser(self, container):
        """Test creating YAML parser."""
        factory = create_parser_factory("yaml")

        with patch("spectryn.adapters.parsers.YamlParser") as MockParser:
            mock_parser = MagicMock()
            MockParser.return_value = mock_parser

            result = factory(container)

            assert result == mock_parser

    def test_create_json_parser(self, container):
        """Test creating JSON parser."""
        factory = create_parser_factory("json")

        with patch("spectryn.adapters.parsers.JsonParser") as MockParser:
            mock_parser = MagicMock()
            MockParser.return_value = mock_parser

            result = factory(container)

            assert result == mock_parser

    def test_create_toml_parser(self, container):
        """Test creating TOML parser."""
        factory = create_parser_factory("toml")

        with patch("spectryn.adapters.parsers.TomlParser") as MockParser:
            mock_parser = MagicMock()
            MockParser.return_value = mock_parser

            result = factory(container)

            assert result == mock_parser

    def test_create_csv_parser(self, container):
        """Test creating CSV parser."""
        factory = create_parser_factory("csv")

        with patch("spectryn.adapters.parsers.CsvParser") as MockParser:
            mock_parser = MagicMock()
            MockParser.return_value = mock_parser

            result = factory(container)

            assert result == mock_parser

    def test_create_asciidoc_parser(self, container):
        """Test creating AsciiDoc parser."""
        factory = create_parser_factory("asciidoc")

        with patch("spectryn.adapters.parsers.AsciiDocParser") as MockParser:
            mock_parser = MagicMock()
            MockParser.return_value = mock_parser

            result = factory(container)

            assert result == mock_parser

    def test_create_excel_parser(self, container):
        """Test creating Excel parser."""
        factory = create_parser_factory("excel")

        with patch("spectryn.adapters.parsers.ExcelParser") as MockParser:
            mock_parser = MagicMock()
            MockParser.return_value = mock_parser

            result = factory(container)

            assert result == mock_parser

    def test_create_toon_parser(self, container):
        """Test creating TOON parser."""
        factory = create_parser_factory("toon")

        with patch("spectryn.adapters.parsers.ToonParser") as MockParser:
            mock_parser = MagicMock()
            MockParser.return_value = mock_parser

            result = factory(container)

            assert result == mock_parser

    def test_create_notion_parser(self, container):
        """Test creating Notion parser."""
        factory = create_parser_factory("notion")

        with patch("spectryn.adapters.parsers.NotionParser") as MockParser:
            mock_parser = MagicMock()
            MockParser.return_value = mock_parser

            result = factory(container)

            assert result == mock_parser

    def test_create_unknown_parser(self, container):
        """Test creating unknown parser raises error."""
        factory = create_parser_factory("unknown")

        with pytest.raises(ValueError, match="Unknown parser type"):
            factory(container)


class TestCreateFormatterFactory:
    """Tests for create_formatter_factory."""

    def test_create_formatter(self, container):
        """Test creating ADF formatter."""
        factory = create_formatter_factory()

        with patch("spectryn.adapters.formatters.adf.ADFFormatter") as MockFormatter:
            mock_formatter = MagicMock()
            MockFormatter.return_value = mock_formatter

            result = factory(container)

            assert result == mock_formatter


class TestCreateOutputFactory:
    """Tests for create_output_factory."""

    def test_create_confluence_output(self, container):
        """Test creating Confluence output."""
        factory = create_output_factory("confluence")

        with patch("spectryn.adapters.confluence.ConfluenceAdapter") as MockAdapter:
            mock_adapter = MagicMock()
            MockAdapter.return_value = mock_adapter

            result = factory(container)

            assert result == mock_adapter

    def test_create_unknown_output(self, container):
        """Test creating unknown output raises error."""
        factory = create_output_factory("unknown")

        with pytest.raises(ValueError, match="Unknown output type"):
            factory(container)


class TestRegisterDefaults:
    """Tests for register_defaults."""

    def test_register_with_config(self, container, mock_tracker_config, mock_sync_config):
        """Test registering with configurations."""
        result = register_defaults(
            container,
            tracker_config=mock_tracker_config,
            sync_config=mock_sync_config,
            dry_run=True,
        )

        assert result == container

        # Should be able to get registered services
        assert container.try_get(TrackerConfig) == mock_tracker_config
        assert container.try_get(SyncConfig) == mock_sync_config
        assert container.try_get(DryRunMode) is not None

    def test_register_without_dry_run(self, container, mock_tracker_config):
        """Test registering without dry-run mode."""
        register_defaults(
            container,
            tracker_config=mock_tracker_config,
            dry_run=False,
        )

        assert container.try_get(DryRunMode) is None

    def test_register_with_parser_type(self, container, mock_tracker_config):
        """Test registering with specific parser type."""
        register_defaults(
            container,
            tracker_config=mock_tracker_config,
            parser_type="yaml",
        )

        # Parser should be registered
        assert DocumentParserPort in container._services


class TestRegisterForSync:
    """Tests for register_for_sync."""

    def test_register_for_sync(self, container, mock_tracker_config, mock_sync_config):
        """Test registering for sync operations."""
        result = register_for_sync(
            container,
            tracker_config=mock_tracker_config,
            sync_config=mock_sync_config,
        )

        assert result == container


class TestCreateTestContainer:
    """Tests for create_test_container."""

    def test_create_empty_container(self):
        """Test creating empty test container."""
        container = create_test_container()

        assert container is not None
        assert isinstance(container, Container)

    def test_create_with_overrides(self):
        """Test creating container with overrides."""
        mock_tracker = MagicMock(spec=IssueTrackerPort)
        mock_parser = MagicMock(spec=DocumentParserPort)

        container = create_test_container(
            {
                IssueTrackerPort: mock_tracker,
                DocumentParserPort: mock_parser,
            }
        )

        assert container.get(IssueTrackerPort) == mock_tracker
        assert container.get(DocumentParserPort) == mock_parser


class TestCreateSyncOrchestrator:
    """Tests for create_sync_orchestrator."""

    def test_create_orchestrator(self):
        """Test creating sync orchestrator."""
        mock_tracker = MagicMock(spec=IssueTrackerPort)
        mock_parser = MagicMock(spec=DocumentParserPort)
        mock_formatter = MagicMock(spec=DocumentFormatterPort)

        container = create_test_container(
            {
                IssueTrackerPort: mock_tracker,
                DocumentParserPort: mock_parser,
                DocumentFormatterPort: mock_formatter,
            }
        )

        with patch("spectryn.application.sync.SyncOrchestrator") as MockOrchestrator:
            mock_orchestrator = MagicMock()
            MockOrchestrator.return_value = mock_orchestrator

            result = create_sync_orchestrator(container)

            assert result == mock_orchestrator

    def test_create_orchestrator_with_config(self):
        """Test creating orchestrator with sync config."""
        mock_tracker = MagicMock(spec=IssueTrackerPort)
        mock_parser = MagicMock(spec=DocumentParserPort)
        mock_formatter = MagicMock(spec=DocumentFormatterPort)
        sync_config = SyncConfig()

        container = create_test_container(
            {
                IssueTrackerPort: mock_tracker,
                DocumentParserPort: mock_parser,
                DocumentFormatterPort: mock_formatter,
            }
        )

        with patch("spectryn.application.sync.SyncOrchestrator") as MockOrchestrator:
            mock_orchestrator = MagicMock()
            MockOrchestrator.return_value = mock_orchestrator

            result = create_sync_orchestrator(container, sync_config=sync_config)

            assert result == mock_orchestrator
            # Verify config was passed
            call_kwargs = MockOrchestrator.call_args.kwargs
            assert call_kwargs.get("config") == sync_config
