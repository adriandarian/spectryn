"""
Tests for AsyncAsanaAdapter.

Tests async operations with mocked aiohttp.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from spectryn.adapters.asana.async_adapter import (
    ASYNC_AVAILABLE,
    AsyncAsanaAdapter,
    AsyncResult,
    is_async_available,
)
from spectryn.core.ports.config_provider import TrackerConfig


@pytest.fixture
def mock_config():
    """Create a mock TrackerConfig."""
    return TrackerConfig(
        url="https://app.asana.com/api/1.0",
        email="test@example.com",
        api_token="test_token_123",
        project_key="1234567890",
    )


@pytest.fixture
def mock_task_response():
    """Mock Asana task response."""
    return {
        "gid": "task-123",
        "name": "Test Task",
        "notes": "Task description",
        "completed": False,
        "resource_subtype": "default_task",
        "assignee": {"gid": "user-123", "name": "Test User"},
        "custom_fields": [
            {
                "gid": "field-1",
                "name": "Story Points",
                "number_value": 5.0,
            }
        ],
    }


class TestAsyncResult:
    """Tests for AsyncResult dataclass."""

    def test_async_result_success(self):
        """Test successful AsyncResult."""
        result = AsyncResult(success=True, key="task-123")
        assert result.success is True
        assert result.key == "task-123"
        assert result.error is None
        assert result.data is None

    def test_async_result_failure(self):
        """Test failed AsyncResult."""
        result = AsyncResult(success=False, key="task-123", error="API error")
        assert result.success is False
        assert result.error == "API error"

    def test_async_result_with_data(self):
        """Test AsyncResult with data."""
        data = {"gid": "task-123", "name": "Test"}
        result = AsyncResult(success=True, key="task-123", data=data)
        assert result.data == data


class TestIsAsyncAvailable:
    """Tests for is_async_available function."""

    def test_is_async_available(self):
        """Test is_async_available returns bool."""
        result = is_async_available()
        assert isinstance(result, bool)
        assert result == ASYNC_AVAILABLE


@pytest.mark.skipif(not ASYNC_AVAILABLE, reason="aiohttp not installed")
class TestAsyncAsanaAdapterInit:
    """Tests for AsyncAsanaAdapter initialization."""

    def test_init_with_defaults(self, mock_config):
        """Test adapter initialization with defaults."""
        adapter = AsyncAsanaAdapter(config=mock_config)
        assert adapter.config == mock_config
        assert adapter._dry_run is True
        assert adapter._concurrency == 10
        assert adapter.timeout == 30
        assert adapter._session is None

    def test_init_with_custom_settings(self, mock_config):
        """Test adapter initialization with custom settings."""
        adapter = AsyncAsanaAdapter(
            config=mock_config,
            dry_run=False,
            concurrency=5,
            timeout=60,
        )
        assert adapter._dry_run is False
        assert adapter._concurrency == 5
        assert adapter.timeout == 60

    def test_init_with_custom_base_url(self, mock_config):
        """Test adapter initialization with custom base URL."""
        adapter = AsyncAsanaAdapter(
            config=mock_config,
            base_url="https://custom.asana.com/api/1.0/",
        )
        assert adapter.base_url == "https://custom.asana.com/api/1.0"

    def test_build_url(self, mock_config):
        """Test URL building."""
        adapter = AsyncAsanaAdapter(config=mock_config)
        url = adapter._build_url("/tasks/123")
        assert url == "https://app.asana.com/api/1.0/tasks/123"


@pytest.mark.skipif(not ASYNC_AVAILABLE, reason="aiohttp not installed")
class TestAsyncAsanaAdapterConnection:
    """Tests for connection management."""

    @pytest.mark.asyncio
    async def test_connect(self, mock_config):
        """Test async connection setup."""
        adapter = AsyncAsanaAdapter(config=mock_config)

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session

            await adapter.connect()

            assert adapter._session is not None
            assert adapter._semaphore is not None
            mock_session_class.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect(self, mock_config):
        """Test async disconnect."""
        adapter = AsyncAsanaAdapter(config=mock_config)

        mock_session = AsyncMock()
        adapter._session = mock_session

        await adapter.disconnect()

        mock_session.close.assert_called_once()
        assert adapter._session is None

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_config):
        """Test async context manager."""
        adapter = AsyncAsanaAdapter(config=mock_config)

        with (
            patch.object(adapter, "connect", new_callable=AsyncMock) as mock_connect,
            patch.object(adapter, "disconnect", new_callable=AsyncMock) as mock_disconnect,
        ):
            async with adapter:
                mock_connect.assert_called_once()

            mock_disconnect.assert_called_once()

    def test_ensure_connected_not_connected(self, mock_config):
        """Test _ensure_connected raises when not connected."""
        adapter = AsyncAsanaAdapter(config=mock_config)

        with pytest.raises(RuntimeError, match="not connected"):
            adapter._ensure_connected()

    def test_ensure_connected_when_connected(self, mock_config):
        """Test _ensure_connected returns session when connected."""
        adapter = AsyncAsanaAdapter(config=mock_config)
        mock_session = MagicMock()
        adapter._session = mock_session

        result = adapter._ensure_connected()
        assert result == mock_session


@pytest.mark.skipif(not ASYNC_AVAILABLE, reason="aiohttp not installed")
class TestAsyncAsanaAdapterReadOps:
    """Tests for async read operations."""

    @pytest.mark.asyncio
    async def test_get_issue_async(self, mock_config, mock_task_response):
        """Test fetching a single task."""
        adapter = AsyncAsanaAdapter(config=mock_config)

        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_task_response

            result = await adapter.get_issue_async("task-123")

            assert result.key == "task-123"
            assert result.summary == "Test Task"
            assert result.description == "Task description"
            assert result.story_points == 5.0
            mock_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_issues_async(self, mock_config, mock_task_response):
        """Test fetching multiple tasks in parallel."""
        adapter = AsyncAsanaAdapter(config=mock_config)

        with patch.object(adapter, "get_issue_async", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = adapter._parse_task(mock_task_response)

            results = await adapter.get_issues_async(["task-1", "task-2", "task-3"])

            assert len(results) == 3
            assert mock_get.call_count == 3

    @pytest.mark.asyncio
    async def test_get_issues_async_with_failures(self, mock_config, mock_task_response):
        """Test fetching tasks with some failures."""
        adapter = AsyncAsanaAdapter(config=mock_config)

        async def mock_get(key):
            if key == "task-2":
                raise Exception("API error")
            return adapter._parse_task(mock_task_response)

        with patch.object(adapter, "get_issue_async", side_effect=mock_get):
            results = await adapter.get_issues_async(["task-1", "task-2", "task-3"])

            # Should return 2 successful results
            assert len(results) == 2

    @pytest.mark.asyncio
    async def test_get_epic_children_async(self, mock_config, mock_task_response):
        """Test fetching project tasks."""
        adapter = AsyncAsanaAdapter(config=mock_config)

        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = [mock_task_response, mock_task_response]

            results = await adapter.get_epic_children_async("project-123")

            assert len(results) == 2
            mock_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_epic_children_async_empty(self, mock_config):
        """Test fetching project tasks with empty response."""
        adapter = AsyncAsanaAdapter(config=mock_config)

        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {}

            results = await adapter.get_epic_children_async("project-123")

            assert results == []

    @pytest.mark.asyncio
    async def test_search_issues_async(self, mock_config, mock_task_response):
        """Test searching tasks."""
        adapter = AsyncAsanaAdapter(config=mock_config)

        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = [
                mock_task_response,
                {"gid": "task-456", "name": "Other Task", "notes": ""},
            ]

            results = await adapter.search_issues_async("Test", max_results=10)

            # Should only return task that matches "test"
            assert len(results) == 1
            assert results[0].key == "task-123"

    @pytest.mark.asyncio
    async def test_search_issues_async_empty(self, mock_config):
        """Test searching tasks with no results."""
        adapter = AsyncAsanaAdapter(config=mock_config)

        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {}

            results = await adapter.search_issues_async("NoMatch")

            assert results == []


@pytest.mark.skipif(not ASYNC_AVAILABLE, reason="aiohttp not installed")
class TestAsyncAsanaAdapterWriteOps:
    """Tests for async write operations."""

    @pytest.mark.asyncio
    async def test_update_descriptions_async_dry_run(self, mock_config):
        """Test updating descriptions in dry-run mode."""
        adapter = AsyncAsanaAdapter(config=mock_config, dry_run=True)

        updates = [("task-1", "New desc 1"), ("task-2", "New desc 2")]
        results = await adapter.update_descriptions_async(updates)

        assert len(results) == 2
        assert all(r[1] is True for r in results)  # All successful

    @pytest.mark.asyncio
    async def test_update_descriptions_async(self, mock_config):
        """Test updating descriptions."""
        adapter = AsyncAsanaAdapter(config=mock_config, dry_run=False)

        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {}

            updates = [("task-1", "New desc 1"), ("task-2", "New desc 2")]
            results = await adapter.update_descriptions_async(updates)

            assert len(results) == 2
            assert mock_request.call_count == 2

    @pytest.mark.asyncio
    async def test_create_subtasks_async_dry_run(self, mock_config):
        """Test creating subtasks in dry-run mode."""
        adapter = AsyncAsanaAdapter(config=mock_config, dry_run=True)

        subtasks = [
            {"parent_key": "task-1", "summary": "Subtask 1"},
            {"parent_key": "task-1", "summary": "Subtask 2"},
        ]
        results = await adapter.create_subtasks_async(subtasks)

        assert len(results) == 2
        assert all(r[1] is True for r in results)

    @pytest.mark.asyncio
    async def test_create_subtasks_async(self, mock_config):
        """Test creating subtasks."""
        adapter = AsyncAsanaAdapter(config=mock_config, dry_run=False)

        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"gid": "new-subtask-gid"}

            subtasks = [
                {"parent_key": "task-1", "summary": "Subtask 1", "assignee": "user-1"},
            ]
            results = await adapter.create_subtasks_async(subtasks)

            assert len(results) == 1
            assert results[0][0] == "new-subtask-gid"
            assert results[0][1] is True

    @pytest.mark.asyncio
    async def test_transition_issues_async_dry_run(self, mock_config):
        """Test transitioning issues in dry-run mode."""
        adapter = AsyncAsanaAdapter(config=mock_config, dry_run=True)

        transitions = [("task-1", "done"), ("task-2", "in progress")]
        results = await adapter.transition_issues_async(transitions)

        assert len(results) == 2
        assert all(r[1] is True for r in results)

    @pytest.mark.asyncio
    async def test_transition_issues_async(self, mock_config):
        """Test transitioning issues."""
        adapter = AsyncAsanaAdapter(config=mock_config, dry_run=False)

        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {}

            transitions = [("task-1", "done"), ("task-2", "complete")]
            results = await adapter.transition_issues_async(transitions)

            assert len(results) == 2
            # Check that completed=True was set for done/complete statuses
            assert mock_request.call_count == 2

    @pytest.mark.asyncio
    async def test_add_comments_async_dry_run(self, mock_config):
        """Test adding comments in dry-run mode."""
        adapter = AsyncAsanaAdapter(config=mock_config, dry_run=True)

        comments = [("task-1", "Comment 1"), ("task-2", "Comment 2")]
        results = await adapter.add_comments_async(comments)

        assert len(results) == 2
        assert all(r[1] is True for r in results)

    @pytest.mark.asyncio
    async def test_add_comments_async(self, mock_config):
        """Test adding comments."""
        adapter = AsyncAsanaAdapter(config=mock_config, dry_run=False)

        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {}

            comments = [("task-1", "Comment 1")]
            results = await adapter.add_comments_async(comments)

            assert len(results) == 1
            assert results[0][1] is True


@pytest.mark.skipif(not ASYNC_AVAILABLE, reason="aiohttp not installed")
class TestAsyncAsanaAdapterParseTask:
    """Tests for _parse_task method."""

    def test_parse_task_complete(self, mock_config, mock_task_response):
        """Test parsing a complete task."""
        adapter = AsyncAsanaAdapter(config=mock_config)

        result = adapter._parse_task(mock_task_response)

        assert result.key == "task-123"
        assert result.summary == "Test Task"
        assert result.description == "Task description"
        assert result.status == "In Progress"
        assert result.issue_type == "default_task"
        assert result.assignee == "user-123"
        assert result.story_points == 5.0

    def test_parse_task_completed(self, mock_config):
        """Test parsing a completed task."""
        adapter = AsyncAsanaAdapter(config=mock_config)

        task_data = {
            "gid": "task-123",
            "name": "Done Task",
            "notes": "",
            "completed": True,
            "custom_fields": [],
        }

        result = adapter._parse_task(task_data)

        assert result.status == "Done"

    def test_parse_task_no_assignee(self, mock_config):
        """Test parsing a task without assignee."""
        adapter = AsyncAsanaAdapter(config=mock_config)

        task_data = {
            "gid": "task-123",
            "name": "Unassigned Task",
            "notes": "",
            "completed": False,
            "assignee": None,
            "custom_fields": [],
        }

        result = adapter._parse_task(task_data)

        assert result.assignee is None

    def test_parse_task_invalid_story_points(self, mock_config):
        """Test parsing a task with invalid story points."""
        adapter = AsyncAsanaAdapter(config=mock_config)

        task_data = {
            "gid": "task-123",
            "name": "Test",
            "notes": "",
            "completed": False,
            "custom_fields": [
                {"name": "Story Points", "number_value": "invalid"},
            ],
        }

        result = adapter._parse_task(task_data)

        assert result.story_points is None


class TestAsyncNotAvailable:
    """Tests when aiohttp is not available."""

    def test_import_error_when_aiohttp_not_available(self, mock_config):
        """Test that ImportError is raised when aiohttp is not available."""
        with patch("spectryn.adapters.asana.async_adapter.ASYNC_AVAILABLE", False):
            from importlib import reload

            import spectryn.adapters.asana.async_adapter as async_module

            # Force reload to re-evaluate ASYNC_AVAILABLE
            original_available = async_module.ASYNC_AVAILABLE

            try:
                async_module.ASYNC_AVAILABLE = False

                with pytest.raises(ImportError, match="aiohttp"):
                    AsyncAsanaAdapter(config=mock_config)
            finally:
                async_module.ASYNC_AVAILABLE = original_available
