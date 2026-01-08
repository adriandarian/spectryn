"""
Service Registration for Dependency Injection.

Provides factory functions and default registrations for spectra services.
These factories configure the Container with production implementations.

Usage:
    # Register all defaults
    container = Container()
    register_defaults(container, config)

    # Get services
    tracker = container.get(IssueTrackerPort)
    parser = container.get(DocumentParserPort)

Testing:
    # Create a test container with mocks
    container = create_test_container({
        IssueTrackerPort: mock_tracker,
        DocumentParserPort: mock_parser,
    })
"""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from .container import Container, Lifecycle
from .ports.config_provider import SyncConfig, TrackerConfig
from .ports.document_formatter import DocumentFormatterPort
from .ports.document_output import DocumentOutputPort
from .ports.document_parser import DocumentParserPort
from .ports.issue_tracker import IssueTrackerPort


if TYPE_CHECKING:
    from spectryn.application.sync import SyncOrchestrator


logger = logging.getLogger("Services")


# =============================================================================
# Service Keys (for non-interface dependencies)
# =============================================================================


class AppConfig:
    """Marker type for application configuration."""


class DryRunMode:
    """Marker type for dry-run flag."""


# =============================================================================
# Factory Functions
# =============================================================================


def create_tracker_factory(
    tracker_type: str = "jira",
) -> Callable[[Container], IssueTrackerPort]:
    """
    Create a factory function for the issue tracker.

    Args:
        tracker_type: Type of tracker ('jira', 'github', 'azure', 'linear', 'asana', 'gitlab', 'monday', 'trello', 'shortcut', 'clickup', 'bitbucket', 'youtrack', 'basecamp', 'plane')

    Returns:
        Factory function that creates the tracker
    """

    def factory(container: Container) -> IssueTrackerPort:
        config = container.get(TrackerConfig)
        dry_run = container.try_get(DryRunMode)
        is_dry_run = dry_run is not None
        formatter = container.try_get(DocumentFormatterPort)

        if tracker_type == "jira":
            from spectryn.adapters.formatters.adf import ADFFormatter
            from spectryn.adapters.jira import JiraAdapter

            if formatter is None:
                formatter = ADFFormatter()

            return JiraAdapter(
                config=config,
                dry_run=is_dry_run,
                formatter=formatter,
            )
        if tracker_type == "github":
            from spectryn.adapters.github import GitHubAdapter

            return GitHubAdapter(
                config=config,
                dry_run=is_dry_run,
            )
        if tracker_type == "azure":
            from spectryn.adapters.azure_devops import AzureDevOpsAdapter

            return AzureDevOpsAdapter(
                config=config,
                dry_run=is_dry_run,
            )
        if tracker_type == "linear":
            from spectryn.adapters.linear import LinearAdapter

            return LinearAdapter(
                config=config,
                dry_run=is_dry_run,
            )
        if tracker_type == "asana":
            from spectryn.adapters.asana import AsanaAdapter

            return AsanaAdapter(
                config=config,
                dry_run=is_dry_run,
            )
        if tracker_type == "gitlab":
            from spectryn.adapters.gitlab import GitLabAdapter
            from spectryn.core.ports.config_provider import GitLabConfig

            if not isinstance(config, GitLabConfig):
                raise ValueError("GitLab adapter requires GitLabConfig")
            return GitLabAdapter(
                token=config.token,
                project_id=config.project_id,
                dry_run=is_dry_run,
                base_url=config.base_url,
                group_id=config.group_id,
                epic_label=config.epic_label,
                story_label=config.story_label,
                subtask_label=config.subtask_label,
                status_labels=config.status_labels,
                use_epics=config.use_epics,
            )
        if tracker_type == "monday":
            from spectryn.adapters.monday import MondayAdapter
            from spectryn.core.ports.config_provider import MondayConfig

            if not isinstance(config, MondayConfig):
                raise ValueError("Monday adapter requires MondayConfig")
            return MondayAdapter(
                api_token=config.api_token,
                board_id=config.board_id,
                workspace_id=config.workspace_id,
                dry_run=is_dry_run,
                api_url=config.api_url,
                status_column_id=config.status_column_id,
                priority_column_id=config.priority_column_id,
                story_points_column_id=config.story_points_column_id,
            )
        if tracker_type == "trello":
            from spectryn.adapters.trello import TrelloAdapter
            from spectryn.core.ports.config_provider import TrelloConfig

            if not isinstance(config, TrelloConfig):
                raise ValueError("Trello adapter requires TrelloConfig")
            return TrelloAdapter(
                config=config,
                dry_run=is_dry_run,
            )
        if tracker_type == "shortcut":
            from spectryn.adapters.shortcut import ShortcutAdapter
            from spectryn.core.ports.config_provider import ShortcutConfig

            if not isinstance(config, ShortcutConfig):
                raise ValueError("Shortcut adapter requires ShortcutConfig")
            return ShortcutAdapter(
                api_token=config.api_token,
                workspace_id=config.workspace_id,
                dry_run=is_dry_run,
                api_url=config.api_url,
            )
        if tracker_type == "clickup":
            from spectryn.adapters.clickup import ClickUpAdapter
            from spectryn.core.ports.config_provider import ClickUpConfig

            if not isinstance(config, ClickUpConfig):
                raise ValueError("ClickUp adapter requires ClickUpConfig")
            return ClickUpAdapter(
                api_token=config.api_token,
                space_id=config.space_id,
                folder_id=config.folder_id,
                list_id=config.list_id,
                dry_run=is_dry_run,
                api_url=config.api_url,
            )
        if tracker_type == "bitbucket":
            from spectryn.adapters.bitbucket import BitbucketAdapter
            from spectryn.core.ports.config_provider import BitbucketConfig

            if not isinstance(config, BitbucketConfig):
                raise ValueError("Bitbucket adapter requires BitbucketConfig")
            return BitbucketAdapter(
                username=config.username,
                app_password=config.app_password,
                workspace=config.workspace,
                repo=config.repo,
                dry_run=is_dry_run,
                base_url=config.base_url,
                epic_label=config.epic_label,
                story_label=config.story_label,
                subtask_label=config.subtask_label,
                status_mapping=config.status_mapping,
                priority_mapping=config.priority_mapping,
            )
        if tracker_type == "youtrack":
            from spectryn.adapters.youtrack import YouTrackAdapter
            from spectryn.core.ports.config_provider import YouTrackConfig

            if not isinstance(config, YouTrackConfig):
                raise ValueError("YouTrack adapter requires YouTrackConfig")
            return YouTrackAdapter(
                config=config,
                dry_run=is_dry_run,
            )
        if tracker_type == "basecamp":
            from spectryn.adapters.basecamp import BasecampAdapter
            from spectryn.core.ports.config_provider import BasecampConfig

            if not isinstance(config, BasecampConfig):
                raise ValueError("Basecamp adapter requires BasecampConfig")
            return BasecampAdapter(
                access_token=config.access_token,
                account_id=config.account_id,
                project_id=config.project_id,
                dry_run=is_dry_run,
                api_url=config.api_url,
                use_messages_for_stories=config.use_messages_for_stories,
            )
        if tracker_type == "plane":
            from spectryn.adapters.plane import PlaneAdapter
            from spectryn.core.ports.config_provider import PlaneConfig

            if not isinstance(config, PlaneConfig):
                raise ValueError("Plane adapter requires PlaneConfig")
            return PlaneAdapter(
                config=config,
                dry_run=is_dry_run,
            )
        raise ValueError(f"Unknown tracker type: {tracker_type}")

    return factory


def create_parser_factory(
    parser_type: str = "markdown",
) -> Callable[[Container], DocumentParserPort]:
    """
    Create a factory function for the document parser.

    Args:
        parser_type: Type of parser. Supported types:
            - 'markdown' - Markdown files (.md, .markdown)
            - 'yaml' - YAML files (.yaml, .yml)
            - 'json' - JSON files (.json)
            - 'toml' - TOML files (.toml)
            - 'csv' - CSV/TSV files (.csv, .tsv)
            - 'asciidoc' - AsciiDoc files (.adoc, .asciidoc)
            - 'excel' - Excel files (.xlsx, .xlsm, .xls)
            - 'toon' - TOON files (.toon)
            - 'notion' - Notion export files

    Returns:
        Factory function that creates the parser
    """

    def factory(container: Container) -> DocumentParserPort:
        if parser_type == "markdown":
            from spectryn.adapters.parsers import MarkdownParser

            return MarkdownParser()
        if parser_type == "yaml":
            from spectryn.adapters.parsers import YamlParser

            return YamlParser()
        if parser_type == "json":
            from spectryn.adapters.parsers import JsonParser

            return JsonParser()
        if parser_type == "toml":
            from spectryn.adapters.parsers import TomlParser

            return TomlParser()
        if parser_type == "csv":
            from spectryn.adapters.parsers import CsvParser

            return CsvParser()
        if parser_type == "asciidoc":
            from spectryn.adapters.parsers import AsciiDocParser

            return AsciiDocParser()
        if parser_type == "excel":
            from spectryn.adapters.parsers import ExcelParser

            return ExcelParser()
        if parser_type == "toon":
            from spectryn.adapters.parsers import ToonParser

            return ToonParser()
        if parser_type == "notion":
            from spectryn.adapters.parsers import NotionParser

            return NotionParser()
        raise ValueError(f"Unknown parser type: {parser_type}")

    return factory


def create_formatter_factory() -> Callable[[Container], DocumentFormatterPort]:
    """
    Create a factory function for the document formatter.

    Returns:
        Factory function that creates the ADF formatter
    """

    def factory(container: Container) -> DocumentFormatterPort:
        from spectryn.adapters.formatters.adf import ADFFormatter

        return ADFFormatter()

    return factory


def create_output_factory(
    output_type: str = "confluence",
) -> Callable[[Container], DocumentOutputPort]:
    """
    Create a factory function for the document output.

    Args:
        output_type: Type of output ('confluence')

    Returns:
        Factory function that creates the output adapter
    """

    def factory(container: Container) -> DocumentOutputPort:
        if output_type == "confluence":
            from spectryn.adapters.confluence import ConfluenceAdapter

            # Get config from container or use defaults
            return ConfluenceAdapter()
        raise ValueError(f"Unknown output type: {output_type}")

    return factory


def create_orchestrator_factory() -> Callable[[Container], "SyncOrchestrator"]:
    """
    Create a factory function for the sync orchestrator.

    Returns:
        Factory function that creates the orchestrator
    """
    from spectryn.application.sync import SyncOrchestrator

    def factory(container: Container) -> SyncOrchestrator:
        tracker = container.get(IssueTrackerPort)
        parser = container.get(DocumentParserPort)
        formatter = container.get(DocumentFormatterPort)
        sync_config = container.try_get(SyncConfig)

        if sync_config is None:
            sync_config = SyncConfig()

        return SyncOrchestrator(
            tracker=tracker,
            parser=parser,
            formatter=formatter,
            config=sync_config,
        )

    return factory


# =============================================================================
# Registration Functions
# =============================================================================


def register_defaults(
    container: Container,
    tracker_config: TrackerConfig | None = None,
    sync_config: SyncConfig | None = None,
    dry_run: bool = True,
    tracker_type: str = "jira",
    parser_type: str = "markdown",
) -> Container:
    """
    Register default service implementations.

    Args:
        container: Container to register services in
        tracker_config: Tracker configuration
        sync_config: Sync configuration
        dry_run: Whether to run in dry-run mode
        tracker_type: Type of tracker to use
        parser_type: Type of parser to use

    Returns:
        The container (for chaining)
    """
    # Register configuration
    if tracker_config is not None:
        container.register_instance(TrackerConfig, tracker_config)

    if sync_config is not None:
        container.register_instance(SyncConfig, sync_config)

    if dry_run:
        container.register_instance(DryRunMode, DryRunMode())

    # Register core services
    container.register(
        DocumentFormatterPort,
        create_formatter_factory(),
        Lifecycle.SINGLETON,
    )

    container.register(
        DocumentParserPort,
        create_parser_factory(parser_type),
        Lifecycle.SINGLETON,
    )

    container.register(
        IssueTrackerPort,
        create_tracker_factory(tracker_type),
        Lifecycle.SINGLETON,
    )

    logger.debug(f"Registered defaults: tracker={tracker_type}, parser={parser_type}")

    return container


def register_for_sync(
    container: Container,
    tracker_config: TrackerConfig,
    sync_config: SyncConfig,
    dry_run: bool = True,
    tracker_type: str = "jira",
) -> Container:
    """
    Register services needed for sync operations.

    This is a convenience function for the common sync use case.

    Args:
        container: Container to register services in
        tracker_config: Tracker configuration
        sync_config: Sync configuration
        dry_run: Whether to run in dry-run mode
        tracker_type: Type of tracker to use

    Returns:
        The container (for chaining)
    """
    register_defaults(
        container,
        tracker_config=tracker_config,
        sync_config=sync_config,
        dry_run=dry_run,
        tracker_type=tracker_type,
    )

    # Register orchestrator factory
    from spectryn.application.sync import SyncOrchestrator

    container.register(
        SyncOrchestrator,
        create_orchestrator_factory(),
        Lifecycle.TRANSIENT,  # New orchestrator each time
    )

    return container


# =============================================================================
# Testing Utilities
# =============================================================================


def create_test_container(
    overrides: dict[type, Any] | None = None,
) -> Container:
    """
    Create a container configured for testing.

    Args:
        overrides: Dict mapping types to mock instances

    Returns:
        Container with mocks registered

    Example:
        >>> container = create_test_container({
        ...     IssueTrackerPort: mock_tracker,
        ...     DocumentParserPort: mock_parser,
        ... })
        >>> orchestrator = create_sync_orchestrator(container)
    """
    container = Container()

    if overrides:
        for service_type, instance in overrides.items():
            container.register_instance(service_type, instance)

    return container


def create_sync_orchestrator(
    container: Container,
    sync_config: SyncConfig | None = None,
) -> "SyncOrchestrator":
    """
    Create a SyncOrchestrator from a container.

    Convenience function that handles missing optional services.

    Args:
        container: Container with tracker, parser, formatter registered
        sync_config: Optional sync config (uses default if not provided)

    Returns:
        Configured SyncOrchestrator
    """
    from spectryn.application.sync import SyncOrchestrator

    tracker = container.get(IssueTrackerPort)
    parser = container.get(DocumentParserPort)
    formatter = container.get(DocumentFormatterPort)

    if sync_config is None:
        sync_config = container.try_get(SyncConfig) or SyncConfig()

    return SyncOrchestrator(
        tracker=tracker,
        parser=parser,
        formatter=formatter,
        config=sync_config,
    )


__all__ = [
    # Service keys
    "AppConfig",
    "DryRunMode",
    "create_formatter_factory",
    "create_orchestrator_factory",
    "create_output_factory",
    "create_parser_factory",
    "create_sync_orchestrator",
    # Testing
    "create_test_container",
    # Factory creators
    "create_tracker_factory",
    # Registration
    "register_defaults",
    "register_for_sync",
]
