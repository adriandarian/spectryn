"""
Testing Utilities for spectra.

Provides pytest fixtures and helpers for testing with dependency injection.

Usage in tests:
    from spectra.testing import container_fixture, mock_tracker

    def test_sync(container_fixture, mock_tracker):
        container_fixture.register_instance(IssueTrackerPort, mock_tracker)
        # ... test code

Or import fixtures directly in conftest.py:
    from spectra.testing import container_fixture
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast
from unittest.mock import MagicMock, create_autospec

from .core.container import Container, reset_container
from .core.ports.config_provider import SyncConfig, TrackerConfig
from .core.ports.document_formatter import DocumentFormatterPort
from .core.ports.document_parser import DocumentParserPort
from .core.ports.issue_tracker import IssueData, IssueTrackerPort


# =============================================================================
# Test Container Management
# =============================================================================


@contextmanager
def test_container(
    overrides: dict[type, Any] | None = None,
) -> Iterator[Container]:
    """
    Context manager that provides a clean test container.

    Automatically clears the global container on exit.

    Args:
        overrides: Dict mapping types to mock instances

    Yields:
        Fresh Container for testing

    Example:
        >>> with test_container({IssueTrackerPort: mock}) as container:
        ...     result = my_function_using_di()
    """
    container = Container()

    if overrides:
        for service_type, instance in overrides.items():
            container.register_instance(service_type, instance)

    try:
        yield container
    finally:
        container.clear()
        reset_container()


def create_mock_tracker(
    issues: dict[str, IssueData] | None = None,
    connected: bool = True,
) -> MagicMock:
    """
    Create a mock IssueTrackerPort.

    Args:
        issues: Dict of issue_key -> IssueData to return from get_issue
        connected: Whether to return True for connection tests

    Returns:
        Configured mock tracker
    """
    mock = create_autospec(IssueTrackerPort, instance=True)

    # Configure connection
    mock.name = "MockTracker"
    mock.is_connected = connected
    mock.test_connection.return_value = connected
    mock.get_current_user.return_value = {
        "displayName": "Test User",
        "emailAddress": "test@example.com",
    }

    # Configure issue retrieval
    issues = issues or {}

    def get_issue(key: str) -> IssueData:
        if key in issues:
            return issues[key]
        from .core.ports.issue_tracker import NotFoundError

        raise NotFoundError(f"Issue not found: {key}")

    mock.get_issue.side_effect = get_issue
    mock.get_epic_children.return_value = []
    mock.search_issues.return_value = []

    # Configure write operations (return success by default)
    mock.update_issue_description.return_value = True
    mock.create_subtask.return_value = "MOCK-123"
    mock.transition_issue.return_value = True
    mock.add_comment.return_value = True

    return cast(MagicMock, mock)


def create_mock_parser(
    stories: list | None = None,
) -> MagicMock:
    """
    Create a mock DocumentParserPort.

    Args:
        stories: List of UserStory objects to return from parse

    Returns:
        Configured mock parser
    """
    from .core.domain import Epic

    mock = create_autospec(DocumentParserPort, instance=True)

    stories = stories or []
    epic = Epic(
        key="MOCK-EPIC",
        title="Mock Epic",
        stories=stories,
    )

    mock.parse.return_value = epic
    mock.parse_file.return_value = epic

    return cast(MagicMock, mock)


def create_mock_formatter() -> MagicMock:
    """
    Create a mock DocumentFormatterPort.

    Returns:
        Configured mock formatter
    """
    mock = create_autospec(DocumentFormatterPort, instance=True)

    # Return simple ADF-like structure
    mock.format_text.return_value = {
        "type": "doc",
        "version": 1,
        "content": [{"type": "paragraph", "content": []}],
    }
    mock.format_acceptance_criteria.return_value = mock.format_text.return_value
    mock.format_story.return_value = mock.format_text.return_value

    return cast(MagicMock, mock)


def create_test_config(
    url: str = "https://test.atlassian.net",
    email: str = "test@example.com",
    api_token: str = "test-token",
    project_key: str = "TEST",
) -> TrackerConfig:
    """
    Create a test TrackerConfig.

    Args:
        url: Jira URL
        email: User email
        api_token: API token
        project_key: Project key

    Returns:
        TrackerConfig for testing
    """
    return TrackerConfig(
        url=url,
        email=email,
        api_token=api_token,
        project_key=project_key,
    )


def create_test_sync_config(
    dry_run: bool = True,
    sync_descriptions: bool = True,
    sync_subtasks: bool = True,
) -> SyncConfig:
    """
    Create a test SyncConfig.

    Args:
        dry_run: Whether to run in dry-run mode
        sync_descriptions: Whether to sync descriptions
        sync_subtasks: Whether to sync subtasks

    Returns:
        SyncConfig for testing
    """
    return SyncConfig(
        dry_run=dry_run,
        sync_descriptions=sync_descriptions,
        sync_subtasks=sync_subtasks,
    )


# =============================================================================
# Pytest Fixtures (import into conftest.py)
# =============================================================================


def pytest_plugin_fixtures() -> dict[str, object]:
    """
    Returns pytest fixture functions that can be used in conftest.py.

    Usage in conftest.py:
        from spectra.testing import pytest_plugin_fixtures
        fixtures = pytest_plugin_fixtures()

        container_fixture = fixtures["container_fixture"]
        mock_tracker = fixtures["mock_tracker"]
    """
    import pytest

    @pytest.fixture
    def container_fixture() -> Iterator[Container]:
        """Provides a clean DI container for each test."""
        container = Container()
        yield container
        container.clear()
        reset_container()

    @pytest.fixture
    def mock_tracker() -> MagicMock:
        """Provides a mock IssueTrackerPort."""
        return create_mock_tracker()

    @pytest.fixture
    def mock_parser() -> MagicMock:
        """Provides a mock DocumentParserPort."""
        return create_mock_parser()

    @pytest.fixture
    def mock_formatter() -> MagicMock:
        """Provides a mock DocumentFormatterPort."""
        return create_mock_formatter()

    @pytest.fixture
    def test_tracker_config() -> TrackerConfig:
        """Provides a test TrackerConfig."""
        return create_test_config()

    @pytest.fixture
    def test_sync_config() -> SyncConfig:
        """Provides a test SyncConfig."""
        return create_test_sync_config()

    return {
        "container_fixture": container_fixture,
        "mock_tracker": mock_tracker,
        "mock_parser": mock_parser,
        "mock_formatter": mock_formatter,
        "test_tracker_config": test_tracker_config,
        "test_sync_config": test_sync_config,
    }


__all__ = [
    "create_mock_formatter",
    "create_mock_parser",
    # Mock creators
    "create_mock_tracker",
    "create_test_config",
    "create_test_sync_config",
    # Pytest plugin
    "pytest_plugin_fixtures",
    # Container utilities
    "test_container",
]
