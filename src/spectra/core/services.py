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
from typing import Any

from .container import Container, Lifecycle
from .ports.config_provider import SyncConfig, TrackerConfig
from .ports.document_formatter import DocumentFormatterPort
from .ports.document_output import DocumentOutputPort
from .ports.document_parser import DocumentParserPort
from .ports.issue_tracker import IssueTrackerPort


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
) -> Any:
    """
    Create a factory function for the issue tracker.

    Args:
        tracker_type: Type of tracker ('jira', 'github', 'azure', 'linear')

    Returns:
        Factory function that creates the tracker
    """

    def factory(container: Container) -> IssueTrackerPort:
        config = container.get(TrackerConfig)
        dry_run = container.try_get(DryRunMode)
        is_dry_run = dry_run is not None
        formatter = container.try_get(DocumentFormatterPort)

        if tracker_type == "jira":
            from spectra.adapters.formatters.adf import ADFFormatter
            from spectra.adapters.jira import JiraAdapter

            if formatter is None:
                formatter = ADFFormatter()

            return JiraAdapter(
                config=config,
                dry_run=is_dry_run,
                formatter=formatter,
            )
        if tracker_type == "github":
            from spectra.adapters.github import GitHubAdapter

            return GitHubAdapter(
                config=config,
                dry_run=is_dry_run,
            )
        if tracker_type == "azure":
            from spectra.adapters.azure_devops import AzureDevOpsAdapter

            return AzureDevOpsAdapter(
                config=config,
                dry_run=is_dry_run,
            )
        if tracker_type == "linear":
            from spectra.adapters.linear import LinearAdapter

            return LinearAdapter(
                config=config,
                dry_run=is_dry_run,
            )
        raise ValueError(f"Unknown tracker type: {tracker_type}")

    return factory


def create_parser_factory(
    parser_type: str = "markdown",
) -> Any:
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
            from spectra.adapters.parsers import MarkdownParser

            return MarkdownParser()
        if parser_type == "yaml":
            from spectra.adapters.parsers import YamlParser

            return YamlParser()
        if parser_type == "json":
            from spectra.adapters.parsers import JsonParser

            return JsonParser()
        if parser_type == "toml":
            from spectra.adapters.parsers import TomlParser

            return TomlParser()
        if parser_type == "csv":
            from spectra.adapters.parsers import CsvParser

            return CsvParser()
        if parser_type == "asciidoc":
            from spectra.adapters.parsers import AsciiDocParser

            return AsciiDocParser()
        if parser_type == "excel":
            from spectra.adapters.parsers import ExcelParser

            return ExcelParser()
        if parser_type == "toon":
            from spectra.adapters.parsers import ToonParser

            return ToonParser()
        if parser_type == "notion":
            from spectra.adapters.parsers import NotionParser

            return NotionParser()
        raise ValueError(f"Unknown parser type: {parser_type}")

    return factory


def create_formatter_factory() -> Any:
    """
    Create a factory function for the document formatter.

    Returns:
        Factory function that creates the ADF formatter
    """

    def factory(container: Container) -> DocumentFormatterPort:
        from spectra.adapters.formatters.adf import ADFFormatter

        return ADFFormatter()

    return factory


def create_output_factory(
    output_type: str = "confluence",
) -> Any:
    """
    Create a factory function for the document output.

    Args:
        output_type: Type of output ('confluence')

    Returns:
        Factory function that creates the output adapter
    """

    def factory(container: Container) -> DocumentOutputPort:
        if output_type == "confluence":
            from spectra.adapters.confluence import ConfluenceAdapter

            # Get config from container or use defaults
            return ConfluenceAdapter()
        raise ValueError(f"Unknown output type: {output_type}")

    return factory


def create_orchestrator_factory() -> Any:
    """
    Create a factory function for the sync orchestrator.

    Returns:
        Factory function that creates the orchestrator
    """

    def factory(container: Container) -> Any:
        from spectra.application.sync import SyncOrchestrator

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
    from spectra.application.sync import SyncOrchestrator

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
) -> Any:
    """
    Create a SyncOrchestrator from a container.

    Convenience function that handles missing optional services.

    Args:
        container: Container with tracker, parser, formatter registered
        sync_config: Optional sync config (uses default if not provided)

    Returns:
        Configured SyncOrchestrator
    """
    from spectra.application.sync import SyncOrchestrator

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
