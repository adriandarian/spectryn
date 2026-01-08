"""
Comprehensive tests for Asana async adapter.

Tests cover:
- AsyncAsanaAdapter initialization and connection management
- Async read operations
- Async write operations
- Dry-run behavior
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from spectryn.core.ports.config_provider import TrackerConfig
from spectryn.core.ports.issue_tracker import IssueData


@pytest.fixture
def mock_asana_config():
    """Create a mock TrackerConfig for Asana."""
    return TrackerConfig(
        url="https://app.asana.com/api/1.0",
        email="test@example.com",
        api_token="test-token",
        project_key="project-123",
    )


@pytest.fixture
def mock_asana_task_response():
    """Create a mock Asana task API response."""
    return {
        "data": {
            "gid": "task-123",
            "name": "Test Task",
            "notes": "Test description",
            "completed": False,
            "custom_fields": [],
            "memberships": [{"section": {"name": "In Progress"}}],
            "assignee": {"name": "Test User"},
        }
    }


class TestAsyncAsanaAdapterInit:
    """Tests for AsyncAsanaAdapter initialization."""

    def test_init_with_required_params(self, mock_asana_config):
        """Test initialization with required parameters."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.asana.async_adapter import AsyncAsanaAdapter

            adapter = AsyncAsanaAdapter(
                config=mock_asana_config,
                dry_run=True,
            )

            assert adapter.config == mock_asana_config
            assert adapter._dry_run is True
            assert adapter._session is None

    def test_init_with_custom_settings(self, mock_asana_config):
        """Test initialization with custom settings."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.asana.async_adapter import AsyncAsanaAdapter

            adapter = AsyncAsanaAdapter(
                config=mock_asana_config,
                dry_run=False,
                concurrency=20,
            )

            assert adapter._dry_run is False
            assert adapter._concurrency == 20


class TestAsyncAsanaAdapterConnection:
    """Tests for AsyncAsanaAdapter connection management."""

    @pytest.mark.asyncio
    async def test_connect_creates_session(self, mock_asana_config):
        """Test that connect creates an aiohttp session."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.asana.async_adapter import AsyncAsanaAdapter

            adapter = AsyncAsanaAdapter(
                config=mock_asana_config,
            )

            await adapter.connect()

            # Session should be created
            assert adapter._session is not None

    @pytest.mark.asyncio
    async def test_disconnect_closes_session(self, mock_asana_config):
        """Test that disconnect closes the session."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.asana.async_adapter import AsyncAsanaAdapter

            adapter = AsyncAsanaAdapter(
                config=mock_asana_config,
            )

            # Set up a mock session
            mock_session = MagicMock()
            mock_session.close = AsyncMock()
            adapter._session = mock_session

            await adapter.disconnect()

            mock_session.close.assert_called_once()
            assert adapter._session is None


class TestAsyncAsanaAdapterWriteOperations:
    """Tests for AsyncAsanaAdapter write operations."""

    @pytest.mark.asyncio
    async def test_update_descriptions_dry_run(self, mock_asana_config):
        """Test update descriptions in dry-run mode."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.asana.async_adapter import AsyncAsanaAdapter

            adapter = AsyncAsanaAdapter(
                config=mock_asana_config,
                dry_run=True,
            )

            # Set up mock session
            mock_session = MagicMock()
            adapter._session = mock_session

            updates = [
                ("task-1", "New desc 1"),
                ("task-2", "New desc 2"),
            ]
            results = await adapter.update_descriptions_async(updates)

            assert len(results) == 2
            assert all(r[1] is True for r in results)

    @pytest.mark.asyncio
    async def test_create_subtasks_dry_run(self, mock_asana_config):
        """Test create subtasks in dry-run mode."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.asana.async_adapter import AsyncAsanaAdapter

            adapter = AsyncAsanaAdapter(
                config=mock_asana_config,
                dry_run=True,
            )

            mock_session = MagicMock()
            adapter._session = mock_session

            subtasks = [
                {"parent_key": "task-1", "summary": "Subtask 1"},
            ]
            results = await adapter.create_subtasks_async(subtasks)

            assert len(results) == 1
            assert results[0][1] is True

    @pytest.mark.asyncio
    async def test_transition_issues_dry_run(self, mock_asana_config):
        """Test transition issues in dry-run mode."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.asana.async_adapter import AsyncAsanaAdapter

            adapter = AsyncAsanaAdapter(
                config=mock_asana_config,
                dry_run=True,
            )

            mock_session = MagicMock()
            adapter._session = mock_session

            transitions = [("task-1", "Done"), ("task-2", "Done")]
            results = await adapter.transition_issues_async(transitions)

            assert len(results) == 2
            assert all(r[1] is True for r in results)

    @pytest.mark.asyncio
    async def test_add_comments_dry_run(self, mock_asana_config):
        """Test add comments in dry-run mode."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.asana.async_adapter import AsyncAsanaAdapter

            adapter = AsyncAsanaAdapter(
                config=mock_asana_config,
                dry_run=True,
            )

            mock_session = MagicMock()
            adapter._session = mock_session

            comments = [("task-1", "Comment 1"), ("task-2", "Comment 2")]
            results = await adapter.add_comments_async(comments)

            assert len(results) == 2
            assert all(r[1] is True for r in results)


class TestAsyncAsanaAdapterParseTask:
    """Tests for AsyncAsanaAdapter._parse_task method."""

    def test_parse_task_complete(self, mock_asana_config, mock_asana_task_response):
        """Test parsing a complete task response."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.asana.async_adapter import AsyncAsanaAdapter

            adapter = AsyncAsanaAdapter(
                config=mock_asana_config,
            )

            task_data = mock_asana_task_response["data"]
            issue = adapter._parse_task(task_data)

            assert issue.key == "task-123"
            assert issue.summary == "Test Task"
            assert issue.description == "Test description"

    def test_parse_task_minimal(self, mock_asana_config):
        """Test parsing a minimal task response."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.asana.async_adapter import AsyncAsanaAdapter

            adapter = AsyncAsanaAdapter(
                config=mock_asana_config,
            )

            minimal_data = {
                "gid": "task-999",
                "name": "Minimal Task",
            }

            issue = adapter._parse_task(minimal_data)

            assert issue.key == "task-999"
            assert issue.summary == "Minimal Task"


class TestAsyncAsanaAvailability:
    """Tests for async availability checking."""

    def test_is_async_available(self):
        """Test is_async_available function."""
        from spectryn.adapters.asana.async_adapter import is_async_available

        result = is_async_available()
        assert isinstance(result, bool)
