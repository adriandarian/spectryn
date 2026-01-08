"""
GitHub Plugin Registry - Plugin marketplace backed by GitHub repositories.

This implementation uses GitHub as a plugin registry, where:
- Plugins are stored as GitHub repositories with a specific topic (spectra-plugin)
- Plugin metadata is stored in pyproject.toml or plugin.json
- Installation uses pip or direct download
- Publishing creates/updates GitHub releases
"""

import contextlib
import json
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from spectryn.core.ports.plugin_marketplace import (
    AuthenticationError,
    InstallationError,
    InstallResult,
    MarketplaceInfo,
    MarketplacePlugin,
    PluginAuthor,
    PluginCategory,
    PluginMarketplaceError,
    PluginMarketplacePort,
    PluginNotFoundError,
    PluginStatus,
    PluginVersionInfo,
    PublishError,
    PublishResult,
    SearchQuery,
    SearchResult,
)


logger = logging.getLogger(__name__)


# Default plugin directory
DEFAULT_PLUGIN_DIR = Path.home() / ".spectra" / "plugins"

# GitHub API base URL
GITHUB_API_URL = "https://api.github.com"

# Topic used to identify spectra plugins
PLUGIN_TOPIC = "spectra-plugin"

# Official spectra organization
OFFICIAL_ORG = "spectra-sync"


@dataclass
class GitHubRegistryConfig:
    """Configuration for the GitHub plugin registry."""

    # Plugin installation directory
    plugin_dir: Path = DEFAULT_PLUGIN_DIR

    # GitHub API token (optional, increases rate limits)
    github_token: str | None = None

    # Cache directory for plugin index
    cache_dir: Path = Path.home() / ".spectra" / "cache" / "marketplace"

    # Cache TTL in seconds (1 hour)
    cache_ttl: int = 3600

    # Custom registry URL (for enterprise GitHub)
    api_url: str = GITHUB_API_URL

    # Organizations to search (in addition to topic search)
    organizations: list[str] | None = None

    # Verify plugin checksums
    verify_checksums: bool = True


class GitHubPluginRegistry(PluginMarketplacePort):
    """
    GitHub-based plugin marketplace implementation.

    Discovers plugins using GitHub's search API with topic filters.
    Plugins must have the 'spectra-plugin' topic and follow conventions.
    """

    def __init__(self, config: GitHubRegistryConfig | None = None) -> None:
        """
        Initialize the GitHub plugin registry.

        Args:
            config: Registry configuration
        """
        self.config = config or GitHubRegistryConfig()
        self._session = requests.Session()
        self._cache: dict[str, Any] = {}
        self._cache_time: dict[str, datetime] = {}
        self._installed_plugins: dict[str, dict[str, Any]] = {}

        # Setup directories
        self.config.plugin_dir.mkdir(parents=True, exist_ok=True)
        self.config.cache_dir.mkdir(parents=True, exist_ok=True)

        # Load installed plugins index
        self._load_installed_index()

        # Setup auth header if token provided
        if self.config.github_token:
            self._session.headers["Authorization"] = f"Bearer {self.config.github_token}"

        self._session.headers["Accept"] = "application/vnd.github.v3+json"
        self._session.headers["User-Agent"] = "spectra-plugin-registry"

    def _load_installed_index(self) -> None:
        """Load the index of installed plugins."""
        index_path = self.config.plugin_dir / "index.json"
        if index_path.exists():
            try:
                with open(index_path) as f:
                    self._installed_plugins = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to load plugin index: {e}")
                self._installed_plugins = {}

    def _save_installed_index(self) -> None:
        """Save the index of installed plugins."""
        index_path = self.config.plugin_dir / "index.json"
        try:
            with open(index_path, "w") as f:
                json.dump(self._installed_plugins, f, indent=2, default=str)
        except OSError as e:
            logger.error(f"Failed to save plugin index: {e}")

    def _github_request(
        self,
        endpoint: str,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        """
        Make a request to the GitHub API.

        Args:
            endpoint: API endpoint path
            method: HTTP method
            params: Query parameters
            data: Request body (for POST/PUT)

        Returns:
            Response JSON

        Raises:
            PluginMarketplaceError: If request fails
        """
        url = f"{self.config.api_url}{endpoint}"

        try:
            response = self._session.request(
                method=method,
                url=url,
                params=params,
                json=data,
                timeout=30,
            )

            if response.status_code == 401:
                raise AuthenticationError("GitHub authentication failed")

            if response.status_code == 404:
                return {}

            response.raise_for_status()

            return response.json() if response.text else {}

        except requests.exceptions.RequestException as e:
            raise PluginMarketplaceError(f"GitHub API request failed: {e}") from e

    def _parse_plugin_metadata(self, repo: dict[str, Any]) -> MarketplacePlugin:
        """
        Parse GitHub repository data into a MarketplacePlugin.

        Args:
            repo: GitHub repository JSON

        Returns:
            MarketplacePlugin instance
        """
        # Determine category from topics
        topics = repo.get("topics", [])
        category = PluginCategory.OTHER
        for topic in topics:
            if topic == "spectra-parser":
                category = PluginCategory.PARSER
                break
            if topic == "spectra-tracker":
                category = PluginCategory.TRACKER
                break
            if topic == "spectra-formatter":
                category = PluginCategory.FORMATTER
                break
            if topic == "spectra-hook":
                category = PluginCategory.HOOK
                break
            if topic == "spectra-command":
                category = PluginCategory.COMMAND
                break
            if topic == "spectra-theme":
                category = PluginCategory.THEME
                break
            if topic == "spectra-template":
                category = PluginCategory.TEMPLATE
                break

        # Parse owner info
        owner = repo.get("owner", {})
        author = PluginAuthor(
            name=owner.get("login", "unknown"),
            github=owner.get("login"),
            url=owner.get("html_url"),
        )

        # Parse dates
        last_updated = None
        if repo.get("pushed_at"):
            with contextlib.suppress(ValueError):
                last_updated = datetime.fromisoformat(repo["pushed_at"].replace("Z", "+00:00"))

        # Check installation status
        name = repo.get("name", "")
        installed_info = self._installed_plugins.get(name, {})
        if installed_info:
            status = PluginStatus.INSTALLED
            installed_version = installed_info.get("version")
        else:
            status = PluginStatus.NOT_INSTALLED
            installed_version = None

        # Check if official
        official = owner.get("login") == OFFICIAL_ORG

        return MarketplacePlugin(
            name=name,
            description=repo.get("description") or "",
            category=category,
            author=author,
            latest_version=repo.get("default_branch", "main"),  # Will be updated from releases
            repository_url=repo.get("html_url"),
            homepage_url=repo.get("homepage"),
            downloads=0,  # GitHub doesn't track this directly
            stars=repo.get("stargazers_count", 0),
            last_updated=last_updated,
            keywords=topics,
            license=repo.get("license", {}).get("spdx_id") if repo.get("license") else None,
            status=status,
            installed_version=installed_version,
            verified=repo.get("archived", False) is False,
            official=official,
        )

    def _get_releases(self, owner: str, repo: str) -> list[PluginVersionInfo]:
        """
        Get release versions for a repository.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            List of version info
        """
        try:
            releases = self._github_request(f"/repos/{owner}/{repo}/releases")
            if not isinstance(releases, list):
                return []

            versions = []
            for release in releases[:10]:  # Limit to 10 recent releases
                try:
                    release_date = datetime.fromisoformat(
                        release["published_at"].replace("Z", "+00:00")
                    )
                except (ValueError, KeyError):
                    release_date = datetime.now(timezone.utc)

                # Find tarball or zipball URL
                download_url = release.get("tarball_url") or release.get("zipball_url", "")

                versions.append(
                    PluginVersionInfo(
                        version=release.get("tag_name", ""),
                        release_date=release_date,
                        download_url=download_url,
                        changelog=release.get("body"),
                    )
                )

            return versions

        except PluginMarketplaceError:
            return []

    # -------------------------------------------------------------------------
    # Search & Discovery
    # -------------------------------------------------------------------------

    def search(self, query: SearchQuery) -> SearchResult:
        """Search for plugins in GitHub repositories."""
        # Build search query
        search_parts = [f"topic:{PLUGIN_TOPIC}"]

        if query.query:
            search_parts.append(query.query)

        if query.author:
            search_parts.append(f"user:{query.author}")

        if query.keywords:
            for kw in query.keywords:
                search_parts.append(f"topic:{kw}")

        search_q = " ".join(search_parts)

        # Determine sort
        sort_map = {
            "downloads": "stars",  # Use stars as proxy for downloads
            "stars": "stars",
            "updated": "updated",
            "name": "name",
        }
        sort = sort_map.get(query.sort_by, "stars")

        # Make search request
        params = {
            "q": search_q,
            "sort": sort if sort != "name" else None,
            "order": query.sort_order,
            "per_page": min(query.limit, 100),
            "page": (query.offset // query.limit) + 1 if query.limit > 0 else 1,
        }

        # Remove None values
        params = {k: v for k, v in params.items() if v is not None}

        result = self._github_request("/search/repositories", params=params)
        items = result.get("items", []) if isinstance(result, dict) else []
        total = result.get("total_count", 0) if isinstance(result, dict) else 0

        # Parse plugins
        plugins = []
        for repo in items:
            plugin = self._parse_plugin_metadata(repo)

            # Apply filters
            if query.category and plugin.category != query.category:
                continue
            if query.verified_only and not plugin.verified:
                continue
            if query.official_only and not plugin.official:
                continue

            plugins.append(plugin)

        return SearchResult(
            plugins=plugins,
            total_count=total,
            query=query,
        )

    def get_plugin(self, name: str) -> MarketplacePlugin | None:
        """Get detailed information about a specific plugin."""
        # Search for exact match
        result = self.search(SearchQuery(query=f"repo:{name}"))
        if result.plugins:
            plugin = result.plugins[0]

            # Get version info from releases
            if plugin.repository_url:
                # Extract owner from URL
                parts = plugin.repository_url.rstrip("/").split("/")
                if len(parts) >= 2:
                    owner = parts[-2]
                    repo_name = parts[-1]
                    plugin.versions = self._get_releases(owner, repo_name)
                    if plugin.versions:
                        plugin.latest_version = plugin.versions[0].version

            return plugin

        # Try direct repository lookup
        # First try official org
        repo = self._github_request(f"/repos/{OFFICIAL_ORG}/{name}")
        if not repo or not isinstance(repo, dict):
            # Search across all users
            result = self.search(SearchQuery(query=name, limit=1))
            if result.plugins:
                return result.plugins[0]
            return None

        return self._parse_plugin_metadata(repo)

    def list_categories(self) -> list[tuple[PluginCategory, int]]:
        """List all categories with plugin counts."""
        counts: dict[PluginCategory, int] = dict.fromkeys(PluginCategory, 0)

        # Search for all plugins
        result = self.search(SearchQuery(limit=100))

        for plugin in result.plugins:
            counts[plugin.category] += 1

        return [(cat, count) for cat, count in counts.items() if count > 0]

    def get_featured(self, limit: int = 10) -> list[MarketplacePlugin]:
        """Get featured/recommended plugins (official + high stars)."""
        # Search official plugins
        result = self.search(
            SearchQuery(
                official_only=True,
                sort_by="stars",
                limit=limit,
            )
        )
        return result.plugins

    def get_trending(self, limit: int = 10, period: str = "week") -> list[MarketplacePlugin]:
        """Get trending plugins by recent activity."""
        # For GitHub, we use recent updates as a proxy for trending
        result = self.search(
            SearchQuery(
                sort_by="updated",
                limit=limit,
            )
        )
        return result.plugins

    # -------------------------------------------------------------------------
    # Installation
    # -------------------------------------------------------------------------

    def install(
        self,
        name: str,
        version: str | None = None,
        force: bool = False,
    ) -> InstallResult:
        """Install a plugin from GitHub."""
        # Check if already installed
        if name in self._installed_plugins and not force:
            return InstallResult(
                success=False,
                plugin_name=name,
                version=self._installed_plugins[name].get("version", "unknown"),
                message=f"Plugin '{name}' is already installed. Use force=True to reinstall.",
            )

        # Get plugin info
        plugin = self.get_plugin(name)
        if not plugin:
            raise PluginNotFoundError(f"Plugin '{name}' not found in marketplace")

        # Determine version to install
        target_version = version or plugin.latest_version

        # Try pip install first (preferred method)
        try:
            return self._pip_install(plugin, target_version, force)
        except InstallationError:
            # Fall back to git clone
            return self._git_install(plugin, target_version)

    def _pip_install(
        self,
        plugin: MarketplacePlugin,
        version: str,
        force: bool,
    ) -> InstallResult:
        """Install plugin using pip."""
        # Construct pip install target
        if plugin.repository_url:
            # Install directly from GitHub
            pip_target = f"git+{plugin.repository_url}"
            if version and version not in {"main", "master"}:
                pip_target += f"@{version}"
        else:
            # Try PyPI
            pip_target = plugin.name
            if version:
                pip_target += f"=={version}"

        cmd = [sys.executable, "-m", "pip", "install"]
        if force:
            cmd.append("--force-reinstall")
        cmd.append(pip_target)

        try:
            result = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=300,
            )

            if result.returncode == 0:
                # Record installation
                self._installed_plugins[plugin.name] = {
                    "version": version,
                    "installed_at": datetime.now(timezone.utc).isoformat(),
                    "method": "pip",
                    "repository_url": plugin.repository_url,
                }
                self._save_installed_index()

                return InstallResult(
                    success=True,
                    plugin_name=plugin.name,
                    version=version,
                    message=f"Successfully installed {plugin.name} v{version}",
                )
            raise InstallationError(f"pip install failed: {result.stderr}")

        except subprocess.TimeoutExpired as e:
            raise InstallationError(f"Installation timed out: {e}") from e
        except subprocess.SubprocessError as e:
            raise InstallationError(f"Installation failed: {e}") from e

    def _git_install(self, plugin: MarketplacePlugin, version: str) -> InstallResult:
        """Install plugin by cloning repository."""
        if not plugin.repository_url:
            raise InstallationError("No repository URL available")

        target_dir = self.config.plugin_dir / plugin.name

        # Remove existing if present
        if target_dir.exists():
            shutil.rmtree(target_dir)

        try:
            # Clone repository
            cmd = ["git", "clone", "--depth", "1"]
            if version and version not in ("main", "master"):
                cmd.extend(["--branch", version])
            cmd.extend([plugin.repository_url, str(target_dir)])

            result = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode != 0:
                raise InstallationError(f"git clone failed: {result.stderr}")

            # Record installation
            self._installed_plugins[plugin.name] = {
                "version": version,
                "installed_at": datetime.now(timezone.utc).isoformat(),
                "method": "git",
                "path": str(target_dir),
                "repository_url": plugin.repository_url,
            }
            self._save_installed_index()

            return InstallResult(
                success=True,
                plugin_name=plugin.name,
                version=version,
                message=f"Successfully cloned {plugin.name} to {target_dir}",
                installed_path=str(target_dir),
            )

        except subprocess.TimeoutExpired as e:
            raise InstallationError(f"Clone timed out: {e}") from e
        except subprocess.SubprocessError as e:
            raise InstallationError(f"Clone failed: {e}") from e

    def uninstall(self, name: str) -> bool:
        """Uninstall a plugin."""
        if name not in self._installed_plugins:
            raise PluginNotFoundError(f"Plugin '{name}' is not installed")

        info = self._installed_plugins[name]
        method = info.get("method", "pip")

        try:
            if method == "pip":
                # Uninstall via pip
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "uninstall", "-y", name],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if result.returncode != 0:
                    logger.warning(f"pip uninstall returned non-zero: {result.stderr}")

            elif method == "git":
                # Remove cloned directory
                plugin_path = info.get("path")
                if plugin_path and Path(plugin_path).exists():
                    shutil.rmtree(plugin_path)

            # Remove from index
            del self._installed_plugins[name]
            self._save_installed_index()

            return True

        except (subprocess.SubprocessError, OSError) as e:
            logger.error(f"Uninstall failed: {e}")
            return False

    def update(self, name: str, version: str | None = None) -> InstallResult:
        """Update an installed plugin."""
        if name not in self._installed_plugins:
            raise PluginNotFoundError(f"Plugin '{name}' is not installed")

        # Reinstall with force
        return self.install(name, version=version, force=True)

    def list_installed(self) -> list[MarketplacePlugin]:
        """List all installed plugins with marketplace info."""
        plugins = []

        for name, info in self._installed_plugins.items():
            # Try to get marketplace info
            marketplace_plugin = self.get_plugin(name)

            if marketplace_plugin:
                marketplace_plugin.status = PluginStatus.INSTALLED
                marketplace_plugin.installed_version = info.get("version")
                plugins.append(marketplace_plugin)
            else:
                # Create basic plugin info from local data
                plugins.append(
                    MarketplacePlugin(
                        name=name,
                        description="Locally installed plugin",
                        category=PluginCategory.OTHER,
                        author=PluginAuthor(name="unknown"),
                        latest_version=info.get("version", "unknown"),
                        repository_url=info.get("repository_url"),
                        status=PluginStatus.INSTALLED,
                        installed_version=info.get("version"),
                    )
                )

        return plugins

    def check_updates(self) -> list[tuple[MarketplacePlugin, str]]:
        """Check for available updates."""
        updates = []

        for name, info in self._installed_plugins.items():
            current_version = info.get("version", "")
            marketplace_plugin = self.get_plugin(name)

            if marketplace_plugin and marketplace_plugin.latest_version != current_version:
                updates.append((marketplace_plugin, marketplace_plugin.latest_version))

        return updates

    # -------------------------------------------------------------------------
    # Publishing
    # -------------------------------------------------------------------------

    def publish(
        self,
        plugin_path: str,
        token: str | None = None,
    ) -> PublishResult:
        """Publish a plugin to GitHub (creates/updates release)."""
        path = Path(plugin_path)

        if not path.exists():
            raise PublishError(f"Plugin path does not exist: {plugin_path}")

        # Read plugin metadata
        metadata = self._read_plugin_metadata(path)

        if not metadata:
            raise PublishError(
                "Could not read plugin metadata. Ensure plugin.json or pyproject.toml exists."
            )

        name = metadata.get("name")
        version = metadata.get("version")

        if not name or not version:
            raise PublishError("Plugin metadata must include 'name' and 'version'")

        # Use provided token or configured token
        auth_token = token or self.config.github_token

        if not auth_token:
            raise AuthenticationError(
                "GitHub token required for publishing. "
                "Set GITHUB_TOKEN environment variable or provide token parameter."
            )

        # Check if repository exists
        repo_url = metadata.get("repository")
        if not repo_url:
            raise PublishError("Plugin metadata must include 'repository' URL")

        # Extract owner/repo from URL
        parts = repo_url.rstrip("/").split("/")
        if len(parts) < 2:
            raise PublishError(f"Invalid repository URL: {repo_url}")

        owner = parts[-2]
        repo = parts[-1].replace(".git", "")

        # Create release
        try:
            # Check if tag exists
            existing = self._github_request(f"/repos/{owner}/{repo}/releases/tags/v{version}")

            if existing and isinstance(existing, dict) and existing.get("id"):
                # Update existing release
                release_id = existing["id"]
                self._github_request(
                    f"/repos/{owner}/{repo}/releases/{release_id}",
                    method="PATCH",
                    data={
                        "tag_name": f"v{version}",
                        "name": f"{name} v{version}",
                        "body": metadata.get("changelog", f"Release {version}"),
                    },
                )
            else:
                # Create new release
                self._github_request(
                    f"/repos/{owner}/{repo}/releases",
                    method="POST",
                    data={
                        "tag_name": f"v{version}",
                        "name": f"{name} v{version}",
                        "body": metadata.get("changelog", f"Release {version}"),
                        "draft": False,
                        "prerelease": "-" in version,  # Pre-release if version has dash
                    },
                )

            return PublishResult(
                success=True,
                plugin_name=name,
                version=version,
                message=f"Successfully published {name} v{version}",
                marketplace_url=f"https://github.com/{owner}/{repo}/releases/tag/v{version}",
            )

        except PluginMarketplaceError as e:
            raise PublishError(f"Failed to publish: {e}") from e

    def _read_plugin_metadata(self, path: Path) -> dict[str, Any]:
        """Read plugin metadata from directory."""
        # Try plugin.json first
        plugin_json = path / "plugin.json"
        if plugin_json.exists():
            try:
                with open(plugin_json) as f:
                    data: dict[str, Any] = json.load(f)
                    return data
            except (json.JSONDecodeError, OSError):
                pass

        # Try pyproject.toml
        pyproject = path / "pyproject.toml"
        if pyproject.exists():
            try:
                import tomllib

                with open(pyproject, "rb") as f:
                    data = tomllib.load(f)
                    project = data.get("project", {})
                    result: dict[str, Any] = {
                        "name": project.get("name"),
                        "version": project.get("version"),
                        "description": project.get("description"),
                        "repository": project.get("urls", {}).get("Repository"),
                    }
                    return result
            except (ImportError, OSError):
                pass

        return {}

    def unpublish(self, name: str, version: str | None = None, token: str | None = None) -> bool:
        """Remove a plugin release from GitHub."""
        plugin = self.get_plugin(name)

        if not plugin or not plugin.repository_url:
            raise PluginNotFoundError(f"Plugin '{name}' not found")

        auth_token = token or self.config.github_token
        if not auth_token:
            raise AuthenticationError("GitHub token required for unpublishing")

        # Extract owner/repo
        parts = plugin.repository_url.rstrip("/").split("/")
        owner = parts[-2]
        repo = parts[-1]

        try:
            if version:
                # Delete specific release
                release = self._github_request(f"/repos/{owner}/{repo}/releases/tags/v{version}")
                if release and isinstance(release, dict) and release.get("id"):
                    self._github_request(
                        f"/repos/{owner}/{repo}/releases/{release['id']}",
                        method="DELETE",
                    )
            else:
                # Delete all releases (dangerous!)
                releases = self._github_request(f"/repos/{owner}/{repo}/releases")
                if isinstance(releases, list):
                    for release in releases:
                        self._github_request(
                            f"/repos/{owner}/{repo}/releases/{release['id']}",
                            method="DELETE",
                        )

            return True

        except PluginMarketplaceError as e:
            logger.error(f"Failed to unpublish: {e}")
            return False

    # -------------------------------------------------------------------------
    # Marketplace Info
    # -------------------------------------------------------------------------

    def info(self) -> MarketplaceInfo:
        """Get marketplace connection information."""
        # Try to get rate limit info (also tests connectivity)
        try:
            self._github_request("/rate_limit")
            connected = True
        except PluginMarketplaceError:
            connected = False

        # Count plugins
        try:
            result = self.search(SearchQuery(limit=1))
            total_plugins = result.total_count
        except PluginMarketplaceError:
            total_plugins = 0

        return MarketplaceInfo(
            name="GitHub Plugin Registry",
            url=self.config.api_url,
            total_plugins=total_plugins,
            connected=connected,
            api_version="v3",
        )

    def sync(self) -> bool:
        """Synchronize local cache with marketplace."""
        try:
            # Clear cache
            self._cache.clear()
            self._cache_time.clear()

            # Verify installed plugins still exist
            for name in list(self._installed_plugins.keys()):
                info = self._installed_plugins[name]
                if info.get("method") == "git":
                    path = info.get("path")
                    if path and not Path(path).exists():
                        del self._installed_plugins[name]

            self._save_installed_index()
            return True

        except Exception as e:
            logger.error(f"Sync failed: {e}")
            return False

    def close(self) -> None:
        """Close the session."""
        self._session.close()


def create_registry(
    plugin_dir: str | Path | None = None,
    github_token: str | None = None,
) -> GitHubPluginRegistry:
    """
    Create a GitHub plugin registry with optional configuration.

    Args:
        plugin_dir: Directory for plugin installations
        github_token: GitHub API token (or uses GITHUB_TOKEN env var)

    Returns:
        Configured GitHubPluginRegistry instance
    """
    config = GitHubRegistryConfig(
        plugin_dir=Path(plugin_dir) if plugin_dir else DEFAULT_PLUGIN_DIR,
        github_token=github_token or os.environ.get("GITHUB_TOKEN"),
    )
    return GitHubPluginRegistry(config)
