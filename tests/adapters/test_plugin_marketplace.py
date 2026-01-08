"""
Tests for Plugin Marketplace Port and GitHub Registry implementation.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from spectryn.core.ports.plugin_marketplace import (
    InstallResult,
    MarketplaceInfo,
    MarketplacePlugin,
    PluginAuthor,
    PluginCategory,
    PluginMarketplaceError,
    PluginNotFoundError,
    PluginStatus,
    PluginVersionInfo,
    PublishResult,
    SearchQuery,
    SearchResult,
)


class TestPluginCategory:
    """Tests for PluginCategory enum."""

    def test_all_categories_exist(self):
        """Test all expected categories are defined."""
        assert PluginCategory.PARSER
        assert PluginCategory.TRACKER
        assert PluginCategory.FORMATTER
        assert PluginCategory.HOOK
        assert PluginCategory.COMMAND
        assert PluginCategory.THEME
        assert PluginCategory.TEMPLATE
        assert PluginCategory.OTHER


class TestPluginStatus:
    """Tests for PluginStatus enum."""

    def test_all_statuses_exist(self):
        """Test all expected statuses are defined."""
        assert PluginStatus.NOT_INSTALLED
        assert PluginStatus.INSTALLED
        assert PluginStatus.UPDATE_AVAILABLE
        assert PluginStatus.DEPRECATED


class TestPluginAuthor:
    """Tests for PluginAuthor dataclass."""

    def test_create_basic_author(self):
        """Test creating author with just name."""
        author = PluginAuthor(name="test-author")

        assert author.name == "test-author"
        assert author.email is None
        assert author.url is None
        assert author.github is None

    def test_create_full_author(self):
        """Test creating author with all fields."""
        author = PluginAuthor(
            name="Test Author",
            email="test@example.com",
            url="https://example.com",
            github="testuser",
        )

        assert author.name == "Test Author"
        assert author.email == "test@example.com"
        assert author.url == "https://example.com"
        assert author.github == "testuser"


class TestPluginVersionInfo:
    """Tests for PluginVersionInfo dataclass."""

    def test_create_version_info(self):
        """Test creating version info."""
        now = datetime.now(timezone.utc)
        version = PluginVersionInfo(
            version="1.0.0",
            release_date=now,
            download_url="https://github.com/test/releases/download/v1.0.0/test.tar.gz",
            checksum="sha256:abc123",
            changelog="Initial release",
        )

        assert version.version == "1.0.0"
        assert version.release_date == now
        assert version.download_url.endswith("test.tar.gz")
        assert version.checksum == "sha256:abc123"
        assert version.changelog == "Initial release"
        assert version.dependencies == []


class TestMarketplacePlugin:
    """Tests for MarketplacePlugin dataclass."""

    def test_create_basic_plugin(self):
        """Test creating plugin with required fields."""
        plugin = MarketplacePlugin(
            name="test-plugin",
            description="A test plugin",
            category=PluginCategory.PARSER,
            author=PluginAuthor(name="test"),
            latest_version="1.0.0",
        )

        assert plugin.name == "test-plugin"
        assert plugin.description == "A test plugin"
        assert plugin.category == PluginCategory.PARSER
        assert plugin.latest_version == "1.0.0"
        assert plugin.downloads == 0
        assert plugin.stars == 0
        assert plugin.status == PluginStatus.NOT_INSTALLED

    def test_create_full_plugin(self):
        """Test creating plugin with all fields."""
        now = datetime.now(timezone.utc)
        plugin = MarketplacePlugin(
            name="full-plugin",
            description="A fully configured plugin",
            category=PluginCategory.TRACKER,
            author=PluginAuthor(name="author", github="author"),
            latest_version="2.0.0",
            versions=[
                PluginVersionInfo(
                    version="2.0.0",
                    release_date=now,
                    download_url="https://example.com/v2.tar.gz",
                )
            ],
            repository_url="https://github.com/author/full-plugin",
            downloads=1000,
            stars=50,
            last_updated=now,
            keywords=["test", "plugin"],
            license="MIT",
            status=PluginStatus.INSTALLED,
            installed_version="1.9.0",
            verified=True,
            official=True,
        )

        assert plugin.name == "full-plugin"
        assert len(plugin.versions) == 1
        assert plugin.downloads == 1000
        assert plugin.stars == 50
        assert plugin.verified is True
        assert plugin.official is True
        assert plugin.installed_version == "1.9.0"


class TestSearchQuery:
    """Tests for SearchQuery dataclass."""

    def test_default_values(self):
        """Test default query values."""
        query = SearchQuery()

        assert query.query is None
        assert query.category is None
        assert query.author is None
        assert query.keywords == []
        assert query.verified_only is False
        assert query.official_only is False
        assert query.sort_by == "downloads"
        assert query.sort_order == "desc"
        assert query.limit == 50
        assert query.offset == 0

    def test_custom_query(self):
        """Test custom query parameters."""
        query = SearchQuery(
            query="yaml parser",
            category=PluginCategory.PARSER,
            author="testuser",
            keywords=["yaml", "json"],
            verified_only=True,
            limit=10,
        )

        assert query.query == "yaml parser"
        assert query.category == PluginCategory.PARSER
        assert query.author == "testuser"
        assert "yaml" in query.keywords


class TestSearchResult:
    """Tests for SearchResult dataclass."""

    def test_create_result(self):
        """Test creating search result."""
        query = SearchQuery(query="test")
        plugins = [
            MarketplacePlugin(
                name="plugin1",
                description="desc1",
                category=PluginCategory.PARSER,
                author=PluginAuthor(name="a"),
                latest_version="1.0.0",
            )
        ]

        result = SearchResult(
            plugins=plugins,
            total_count=100,
            query=query,
        )

        assert len(result.plugins) == 1
        assert result.total_count == 100
        assert result.query.query == "test"


class TestInstallResult:
    """Tests for InstallResult dataclass."""

    def test_successful_install(self):
        """Test successful installation result."""
        result = InstallResult(
            success=True,
            plugin_name="test-plugin",
            version="1.0.0",
            message="Successfully installed",
            installed_path="/path/to/plugin",
        )

        assert result.success is True
        assert result.plugin_name == "test-plugin"
        assert result.version == "1.0.0"
        assert result.installed_path == "/path/to/plugin"
        assert result.errors == []

    def test_failed_install(self):
        """Test failed installation result."""
        result = InstallResult(
            success=False,
            plugin_name="test-plugin",
            version="1.0.0",
            message="Installation failed",
            errors=["Network error", "Invalid checksum"],
        )

        assert result.success is False
        assert len(result.errors) == 2


class TestPublishResult:
    """Tests for PublishResult dataclass."""

    def test_successful_publish(self):
        """Test successful publish result."""
        result = PublishResult(
            success=True,
            plugin_name="my-plugin",
            version="1.0.0",
            message="Published successfully",
            marketplace_url="https://github.com/test/my-plugin/releases/tag/v1.0.0",
        )

        assert result.success is True
        assert result.marketplace_url is not None


class TestMarketplaceInfo:
    """Tests for MarketplaceInfo dataclass."""

    def test_create_info(self):
        """Test creating marketplace info."""
        info = MarketplaceInfo(
            name="GitHub Plugin Registry",
            url="https://api.github.com",
            total_plugins=150,
            connected=True,
            api_version="v3",
        )

        assert info.name == "GitHub Plugin Registry"
        assert info.total_plugins == 150
        assert info.connected is True


class TestGitHubPluginRegistry:
    """Tests for GitHubPluginRegistry implementation."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock requests session."""
        with patch("requests.Session") as mock:
            session = MagicMock()
            mock.return_value = session
            yield session

    @pytest.fixture
    def registry(self, tmp_path, mock_session):
        """Create a registry instance with mocked session."""
        from spectryn.adapters.plugin_marketplace.github_registry import (
            GitHubPluginRegistry,
            GitHubRegistryConfig,
        )

        config = GitHubRegistryConfig(
            plugin_dir=tmp_path / "plugins",
            cache_dir=tmp_path / "cache",
            github_token="test-token",
        )
        return GitHubPluginRegistry(config)

    def test_search_returns_results(self, registry, mock_session):
        """Test search returns plugins."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps(
            {
                "total_count": 1,
                "items": [
                    {
                        "name": "spectra-yaml-parser",
                        "description": "YAML parser plugin",
                        "owner": {"login": "testuser", "html_url": "https://github.com/testuser"},
                        "topics": ["spectra-plugin", "spectra-parser"],
                        "stargazers_count": 10,
                        "pushed_at": "2024-01-01T00:00:00Z",
                    }
                ],
            }
        )
        mock_response.json.return_value = json.loads(mock_response.text)
        mock_session.request.return_value = mock_response

        result = registry.search(SearchQuery(query="yaml"))

        assert result.total_count == 1
        assert len(result.plugins) == 1
        assert result.plugins[0].name == "spectra-yaml-parser"
        assert result.plugins[0].category == PluginCategory.PARSER

    def test_search_handles_empty_results(self, registry, mock_session):
        """Test search with no results."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps({"total_count": 0, "items": []})
        mock_response.json.return_value = {"total_count": 0, "items": []}
        mock_session.request.return_value = mock_response

        result = registry.search(SearchQuery(query="nonexistent"))

        assert result.total_count == 0
        assert len(result.plugins) == 0

    def test_get_plugin_not_found(self, registry, mock_session):
        """Test get_plugin returns None for nonexistent plugin."""

        def mock_request(method, url, **kwargs):
            mock_response = MagicMock()
            if "/search/repositories" in url:
                # Search returns empty results
                mock_response.status_code = 200
                mock_response.text = json.dumps({"total_count": 0, "items": []})
                mock_response.json.return_value = {"total_count": 0, "items": []}
            else:
                # Direct repo lookup returns 404
                mock_response.status_code = 404
                mock_response.text = ""
                mock_response.json.return_value = {}
            return mock_response

        mock_session.request.side_effect = mock_request

        plugin = registry.get_plugin("nonexistent-plugin")

        assert plugin is None

    def test_list_installed_empty(self, registry):
        """Test listing installed plugins when none installed."""
        plugins = registry.list_installed()

        assert plugins == []

    def test_info_returns_marketplace_info(self, registry, mock_session):
        """Test info returns marketplace connection info."""
        # Mock rate limit response
        mock_rate = MagicMock()
        mock_rate.status_code = 200
        mock_rate.text = json.dumps({"rate": {"limit": 5000}})
        mock_rate.json.return_value = {"rate": {"limit": 5000}}

        # Mock search response for plugin count
        mock_search = MagicMock()
        mock_search.status_code = 200
        mock_search.text = json.dumps({"total_count": 50, "items": []})
        mock_search.json.return_value = {"total_count": 50, "items": []}

        mock_session.request.side_effect = [mock_rate, mock_search]

        info = registry.info()

        assert info.name == "GitHub Plugin Registry"
        assert info.connected is True
        assert info.total_plugins == 50

    def test_close_closes_session(self, registry, mock_session):
        """Test close method closes the HTTP session."""
        registry.close()

        mock_session.close.assert_called_once()


class TestGitHubRegistryInstallation:
    """Tests for plugin installation functionality."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock requests session."""
        with patch("requests.Session") as mock:
            session = MagicMock()
            mock.return_value = session
            yield session

    @pytest.fixture
    def registry(self, tmp_path, mock_session):
        """Create a registry instance."""
        from spectryn.adapters.plugin_marketplace.github_registry import (
            GitHubPluginRegistry,
            GitHubRegistryConfig,
        )

        config = GitHubRegistryConfig(
            plugin_dir=tmp_path / "plugins",
            cache_dir=tmp_path / "cache",
        )
        return GitHubPluginRegistry(config)

    def test_install_already_installed(self, registry, mock_session):
        """Test install fails when plugin already installed."""
        # Manually add to installed
        registry._installed_plugins["test-plugin"] = {"version": "1.0.0"}

        result = registry.install("test-plugin", force=False)

        assert result.success is False
        assert "already installed" in result.message.lower()

    def test_uninstall_not_installed(self, registry):
        """Test uninstall raises error for non-installed plugin."""
        with pytest.raises(PluginNotFoundError):
            registry.uninstall("not-installed")

    def test_check_updates_empty(self, registry):
        """Test check_updates with no plugins installed."""
        updates = registry.check_updates()

        assert updates == []
