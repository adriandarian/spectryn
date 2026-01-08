"""
Plugin CLI Commands - Commands for managing plugins from the marketplace.

Provides CLI interface for:
- Searching the plugin marketplace
- Installing/uninstalling plugins
- Listing installed plugins
- Checking for updates
- Publishing plugins
"""

from .exit_codes import ExitCode
from .output import Console, Symbols


def run_plugin_search(
    console: Console,
    query: str | None = None,
    category: str | None = None,
    author: str | None = None,
    verified_only: bool = False,
    official_only: bool = False,
    limit: int = 20,
    output_format: str = "text",
) -> int:
    """
    Search for plugins in the marketplace.

    Args:
        console: Console instance for output
        query: Search query string
        category: Filter by category
        author: Filter by author
        verified_only: Show only verified plugins
        official_only: Show only official plugins
        limit: Maximum results to return
        output_format: Output format (text, json, yaml)

    Returns:
        Exit code
    """
    from spectryn.adapters.plugin_marketplace import GitHubPluginRegistry
    from spectryn.core.ports.plugin_marketplace import PluginCategory, SearchQuery

    console.info(f"{Symbols.SEARCH} Searching plugin marketplace...")

    try:
        registry = GitHubPluginRegistry()

        # Parse category
        cat = None
        if category:
            try:
                cat = PluginCategory[category.upper()]
            except KeyError:
                console.error(f"Invalid category: {category}")
                console.print(
                    "Valid categories: " + ", ".join(c.name.lower() for c in PluginCategory)
                )
                return ExitCode.ERROR

        search_query = SearchQuery(
            query=query,
            category=cat,
            author=author,
            verified_only=verified_only,
            official_only=official_only,
            limit=limit,
        )

        result = registry.search(search_query)

        if output_format == "json":
            import json

            data = {
                "total_count": result.total_count,
                "plugins": [
                    {
                        "name": p.name,
                        "description": p.description,
                        "category": p.category.name,
                        "author": p.author.name,
                        "version": p.latest_version,
                        "stars": p.stars,
                        "status": p.status.name,
                        "official": p.official,
                        "verified": p.verified,
                    }
                    for p in result.plugins
                ],
            }
            console.print(json.dumps(data, indent=2))
            return ExitCode.SUCCESS

        if not result.plugins:
            console.warning("No plugins found matching your search criteria.")
            return ExitCode.SUCCESS

        console.success(f"Found {result.total_count} plugins:")
        console.print("")

        # Display results in a table-like format
        for plugin in result.plugins:
            # Status indicator
            if plugin.official:
                badge = f"{Symbols.SUCCESS} [official]"
            elif plugin.verified:
                badge = f"{Symbols.INFO} [verified]"
            else:
                badge = ""

            status = ""
            if plugin.status.name == "INSTALLED":
                status = f" {Symbols.SUCCESS}(installed: v{plugin.installed_version})"

            console.print(f"  {Symbols.BULLET} {plugin.name} ({plugin.latest_version}){status}")
            console.print(
                f"    {plugin.description[:80]}..."
                if len(plugin.description) > 80
                else f"    {plugin.description}"
            )
            console.print(
                f"    {Symbols.STAR} {plugin.stars} | {plugin.category.name.lower()} | by {plugin.author.name} {badge}"
            )
            console.print("")

        registry.close()
        return ExitCode.SUCCESS

    except Exception as e:
        console.error(f"Search failed: {e}")
        return ExitCode.ERROR


def run_plugin_install(
    console: Console,
    name: str,
    version: str | None = None,
    force: bool = False,
) -> int:
    """
    Install a plugin from the marketplace.

    Args:
        console: Console instance
        name: Plugin name to install
        version: Specific version (optional)
        force: Force reinstall if already installed

    Returns:
        Exit code
    """
    from spectryn.adapters.plugin_marketplace import GitHubPluginRegistry
    from spectryn.core.ports.plugin_marketplace import InstallationError, PluginNotFoundError

    console.info(f"{Symbols.DOWNLOAD} Installing plugin: {name}...")

    try:
        registry = GitHubPluginRegistry()

        result = registry.install(name, version=version, force=force)

        if result.success:
            console.success(f"{Symbols.SUCCESS} {result.message}")
            if result.installed_path:
                console.print(f"  Installed to: {result.installed_path}")
            return ExitCode.SUCCESS
        console.error(f"{Symbols.ERROR} {result.message}")
        for err in result.errors:
            console.error(f"  - {err}")
        return ExitCode.ERROR

    except PluginNotFoundError as e:
        console.error(f"{Symbols.ERROR} Plugin not found: {e}")
        return ExitCode.ERROR
    except InstallationError as e:
        console.error(f"{Symbols.ERROR} Installation failed: {e}")
        return ExitCode.ERROR
    except Exception as e:
        console.error(f"{Symbols.ERROR} Error: {e}")
        return ExitCode.ERROR


def run_plugin_uninstall(console: Console, name: str) -> int:
    """
    Uninstall a plugin.

    Args:
        console: Console instance
        name: Plugin name to uninstall

    Returns:
        Exit code
    """
    from spectryn.adapters.plugin_marketplace import GitHubPluginRegistry
    from spectryn.core.ports.plugin_marketplace import PluginNotFoundError

    console.info(f"{Symbols.DELETE} Uninstalling plugin: {name}...")

    try:
        registry = GitHubPluginRegistry()

        if registry.uninstall(name):
            console.success(f"{Symbols.SUCCESS} Successfully uninstalled {name}")
            return ExitCode.SUCCESS
        console.error(f"{Symbols.ERROR} Failed to uninstall {name}")
        return ExitCode.ERROR

    except PluginNotFoundError as e:
        console.error(f"{Symbols.ERROR} {e}")
        return ExitCode.ERROR
    except Exception as e:
        console.error(f"{Symbols.ERROR} Error: {e}")
        return ExitCode.ERROR


def run_plugin_list(
    console: Console,
    show_updates: bool = False,
    output_format: str = "text",
) -> int:
    """
    List installed plugins.

    Args:
        console: Console instance
        show_updates: Check for available updates
        output_format: Output format (text, json)

    Returns:
        Exit code
    """
    from spectryn.adapters.plugin_marketplace import GitHubPluginRegistry

    console.info(f"{Symbols.PACKAGE} Listing installed plugins...")

    try:
        registry = GitHubPluginRegistry()
        plugins = registry.list_installed()

        if output_format == "json":
            import json

            data = {
                "plugins": [
                    {
                        "name": p.name,
                        "version": p.installed_version,
                        "category": p.category.name,
                        "status": p.status.name,
                    }
                    for p in plugins
                ]
            }
            console.print(json.dumps(data, indent=2))
            return ExitCode.SUCCESS

        if not plugins:
            console.print("No plugins installed.")
            return ExitCode.SUCCESS

        console.print(f"\nInstalled plugins ({len(plugins)}):\n")

        for plugin in plugins:
            console.print(f"  {Symbols.BULLET} {plugin.name} v{plugin.installed_version}")
            console.print(f"    Category: {plugin.category.name.lower()}")
            if plugin.repository_url:
                console.print(f"    Repository: {plugin.repository_url}")
            console.print("")

        if show_updates:
            console.print("Checking for updates...")
            updates = registry.check_updates()

            if updates:
                console.warning(f"\n{Symbols.WARNING} Updates available:")
                for plugin, new_version in updates:
                    console.print(f"  {plugin.name}: {plugin.installed_version} → {new_version}")
            else:
                console.success(f"{Symbols.SUCCESS} All plugins are up to date.")

        registry.close()
        return ExitCode.SUCCESS

    except Exception as e:
        console.error(f"Error listing plugins: {e}")
        return ExitCode.ERROR


def run_plugin_update(
    console: Console,
    name: str | None = None,
    version: str | None = None,
) -> int:
    """
    Update plugin(s).

    Args:
        console: Console instance
        name: Plugin name to update (None for all)
        version: Target version (None for latest)

    Returns:
        Exit code
    """
    from spectryn.adapters.plugin_marketplace import GitHubPluginRegistry
    from spectryn.core.ports.plugin_marketplace import PluginNotFoundError

    try:
        registry = GitHubPluginRegistry()

        if name:
            # Update single plugin
            console.info(f"{Symbols.UPDATE} Updating plugin: {name}...")

            result = registry.update(name, version=version)

            if result.success:
                console.success(f"{Symbols.SUCCESS} {result.message}")
                return ExitCode.SUCCESS
            console.error(f"{Symbols.ERROR} {result.message}")
            return ExitCode.ERROR
        # Update all plugins with available updates
        console.info(f"{Symbols.UPDATE} Checking for updates...")

        updates = registry.check_updates()

        if not updates:
            console.success(f"{Symbols.SUCCESS} All plugins are up to date.")
            return ExitCode.SUCCESS

        console.print(f"Found {len(updates)} updates available.\n")
        failed = 0

        for plugin, new_version in updates:
            console.print(f"Updating {plugin.name} to v{new_version}...")
            result = registry.update(plugin.name)

            if result.success:
                console.success(f"  {Symbols.SUCCESS} Updated successfully")
            else:
                console.error(f"  {Symbols.ERROR} Update failed: {result.message}")
                failed += 1

        if failed > 0:
            console.warning(f"\n{failed} plugin(s) failed to update.")
            return ExitCode.PARTIAL_SUCCESS
        console.success(f"\n{Symbols.SUCCESS} All plugins updated successfully.")
        return ExitCode.SUCCESS

    except PluginNotFoundError as e:
        console.error(f"{Symbols.ERROR} {e}")
        return ExitCode.ERROR
    except Exception as e:
        console.error(f"{Symbols.ERROR} Error: {e}")
        return ExitCode.ERROR


def run_plugin_info(console: Console, name: str) -> int:
    """
    Show detailed information about a plugin.

    Args:
        console: Console instance
        name: Plugin name

    Returns:
        Exit code
    """
    from spectryn.adapters.plugin_marketplace import GitHubPluginRegistry

    console.info(f"{Symbols.INFO} Getting plugin info: {name}...")

    try:
        registry = GitHubPluginRegistry()
        plugin = registry.get_plugin(name)

        if not plugin:
            console.error(f"Plugin '{name}' not found.")
            return ExitCode.ERROR

        console.print(f"\n{Symbols.PACKAGE} {plugin.name}\n")
        console.print(f"  Description: {plugin.description}")
        console.print(f"  Category:    {plugin.category.name.lower()}")
        console.print(f"  Author:      {plugin.author.name}")
        console.print(f"  Version:     {plugin.latest_version}")
        console.print(f"  Stars:       {plugin.stars}")

        if plugin.license:
            console.print(f"  License:     {plugin.license}")

        if plugin.repository_url:
            console.print(f"  Repository:  {plugin.repository_url}")

        if plugin.homepage_url:
            console.print(f"  Homepage:    {plugin.homepage_url}")

        if plugin.official:
            console.print(f"  {Symbols.SUCCESS} Official plugin")
        elif plugin.verified:
            console.print(f"  {Symbols.INFO} Verified plugin")

        console.print(f"\n  Status: {plugin.status.name}")
        if plugin.installed_version:
            console.print(f"  Installed Version: {plugin.installed_version}")

        if plugin.versions:
            console.print("\n  Recent Versions:")
            for v in plugin.versions[:5]:
                console.print(f"    - {v.version} ({v.release_date.strftime('%Y-%m-%d')})")

        registry.close()
        return ExitCode.SUCCESS

    except Exception as e:
        console.error(f"Error: {e}")
        return ExitCode.ERROR


def run_plugin_publish(
    console: Console,
    plugin_path: str,
    token: str | None = None,
) -> int:
    """
    Publish a plugin to the marketplace.

    Args:
        console: Console instance
        plugin_path: Path to plugin directory
        token: GitHub token (optional, uses GITHUB_TOKEN env var)

    Returns:
        Exit code
    """
    from spectryn.adapters.plugin_marketplace import GitHubPluginRegistry
    from spectryn.core.ports.plugin_marketplace import AuthenticationError, PublishError

    console.info(f"{Symbols.UPLOAD} Publishing plugin from: {plugin_path}...")

    try:
        registry = GitHubPluginRegistry()

        result = registry.publish(plugin_path, token=token)

        if result.success:
            console.success(f"{Symbols.SUCCESS} {result.message}")
            if result.marketplace_url:
                console.print(f"  Published to: {result.marketplace_url}")
            return ExitCode.SUCCESS
        console.error(f"{Symbols.ERROR} {result.message}")
        for err in result.errors:
            console.error(f"  - {err}")
        return ExitCode.ERROR

    except AuthenticationError as e:
        console.error(f"{Symbols.ERROR} Authentication failed: {e}")
        console.print("Set GITHUB_TOKEN environment variable or use --token option.")
        return ExitCode.ERROR
    except PublishError as e:
        console.error(f"{Symbols.ERROR} Publish failed: {e}")
        return ExitCode.ERROR
    except Exception as e:
        console.error(f"{Symbols.ERROR} Error: {e}")
        return ExitCode.ERROR


def run_plugin_marketplace_info(console: Console) -> int:
    """
    Show marketplace connection info and statistics.

    Args:
        console: Console instance

    Returns:
        Exit code
    """
    from spectryn.adapters.plugin_marketplace import GitHubPluginRegistry

    console.info(f"{Symbols.INFO} Marketplace Info\n")

    try:
        registry = GitHubPluginRegistry()
        info = registry.info()

        status = (
            f"{Symbols.SUCCESS} Connected" if info.connected else f"{Symbols.ERROR} Disconnected"
        )

        console.print(f"  Name:          {info.name}")
        console.print(f"  URL:           {info.url}")
        console.print(f"  Status:        {status}")
        console.print(f"  API Version:   {info.api_version or 'unknown'}")
        console.print(f"  Total Plugins: {info.total_plugins}")

        if info.last_sync:
            console.print(f"  Last Sync:     {info.last_sync.strftime('%Y-%m-%d %H:%M:%S')}")

        # Show categories
        console.print("\n  Categories:")
        categories = registry.list_categories()
        for cat, count in categories:
            console.print(f"    {cat.name.lower()}: {count}")

        registry.close()
        return ExitCode.SUCCESS

    except Exception as e:
        console.error(f"Error: {e}")
        return ExitCode.ERROR
