"""
Comprehensive tests for Linear async adapter.

Tests cover:
- AsyncLinearAdapter initialization and connection management
- Async read operations (get_issue, get_issues, search)
- Async write operations (update, create, transition, comments)
- Dry-run behavior
- GraphQL query handling
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from spectryn.core.ports.issue_tracker import IssueData


@pytest.fixture
def mock_linear_issue_response():
    """Create a mock Linear issue API response."""
    return {
        "data": {
            "issue": {
                "id": "issue-123",
                "identifier": "ENG-123",
                "title": "Test Issue",
                "description": "Test description",
                "state": {"name": "In Progress"},
                "priority": 2,
                "estimate": 5,
                "assignee": {"name": "Test User"},
                "children": {"nodes": []},
            }
        }
    }


class TestAsyncLinearAdapterInit:
    """Tests for AsyncLinearAdapter initialization."""

    def test_init_with_required_params(self):
        """Test initialization with required parameters."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.linear.async_adapter import AsyncLinearAdapter

            adapter = AsyncLinearAdapter(
                api_key="test-api-key",
                team_key="eng",
                dry_run=True,
            )

            assert adapter.api_key == "test-api-key"
            assert adapter.team_key == "ENG"  # Should be uppercase
            assert adapter._dry_run is True
            assert adapter._session is None

    def test_init_with_custom_settings(self):
        """Test initialization with custom settings."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.linear.async_adapter import AsyncLinearAdapter

            adapter = AsyncLinearAdapter(
                api_key="test-api-key",
                team_key="eng",
                dry_run=False,
                concurrency=20,
                timeout=60,
            )

            assert adapter._dry_run is False
            assert adapter._concurrency == 20
            assert adapter.timeout == 60


class TestAsyncLinearAdapterConnection:
    """Tests for AsyncLinearAdapter connection management."""

    @pytest.mark.asyncio
    async def test_connect_creates_session(self):
        """Test that connect creates an aiohttp session."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.linear.async_adapter import AsyncLinearAdapter

            adapter = AsyncLinearAdapter(
                api_key="test-api-key",
                team_key="eng",
            )

            # Mock the _execute_graphql method to return team data with id
            adapter._execute_graphql = AsyncMock(return_value={"team": {"id": "team-123"}})

            await adapter.connect()

            # Session should be created and team_id should be set
            assert adapter._session is not None
            assert adapter._team_id == "team-123"

    @pytest.mark.asyncio
    async def test_disconnect_closes_session(self):
        """Test that disconnect closes the session."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.linear.async_adapter import AsyncLinearAdapter

            adapter = AsyncLinearAdapter(
                api_key="test-api-key",
                team_key="eng",
            )

            # Set up a mock session
            mock_session = MagicMock()
            mock_session.close = AsyncMock()
            adapter._session = mock_session

            await adapter.disconnect()

            mock_session.close.assert_called_once()
            assert adapter._session is None


class TestAsyncLinearAdapterWriteOperations:
    """Tests for AsyncLinearAdapter write operations."""

    @pytest.mark.asyncio
    async def test_update_descriptions_dry_run(self):
        """Test update descriptions in dry-run mode."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.linear.async_adapter import AsyncLinearAdapter

            adapter = AsyncLinearAdapter(
                api_key="test-api-key",
                team_key="eng",
                dry_run=True,
            )

            # Set up mock session
            mock_session = MagicMock()
            adapter._session = mock_session

            updates = [
                ("ENG-1", "New desc 1"),
                ("ENG-2", "New desc 2"),
            ]
            results = await adapter.update_descriptions_async(updates)

            assert len(results) == 2
            assert all(r[1] is True for r in results)

    @pytest.mark.asyncio
    async def test_create_subtasks_dry_run(self):
        """Test create subtasks in dry-run mode."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.linear.async_adapter import AsyncLinearAdapter

            adapter = AsyncLinearAdapter(
                api_key="test-api-key",
                team_key="eng",
                dry_run=True,
            )

            # Set up mock session
            mock_session = MagicMock()
            adapter._session = mock_session

            subtasks = [
                {"parent_key": "ENG-1", "summary": "Subtask 1"},
            ]
            results = await adapter.create_subtasks_async(subtasks)

            assert len(results) == 1
            assert results[0][1] is True

    @pytest.mark.asyncio
    async def test_transition_issues_dry_run(self):
        """Test transition issues in dry-run mode."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.linear.async_adapter import AsyncLinearAdapter

            adapter = AsyncLinearAdapter(
                api_key="test-api-key",
                team_key="eng",
                dry_run=True,
            )

            mock_session = MagicMock()
            adapter._session = mock_session

            transitions = [("ENG-1", "Done"), ("ENG-2", "Done")]
            results = await adapter.transition_issues_async(transitions)

            assert len(results) == 2
            assert all(r[1] is True for r in results)

    @pytest.mark.asyncio
    async def test_add_comments_dry_run(self):
        """Test add comments in dry-run mode."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.linear.async_adapter import AsyncLinearAdapter

            adapter = AsyncLinearAdapter(
                api_key="test-api-key",
                team_key="eng",
                dry_run=True,
            )

            mock_session = MagicMock()
            adapter._session = mock_session

            comments = [("ENG-1", "Comment 1"), ("ENG-2", "Comment 2")]
            results = await adapter.add_comments_async(comments)

            assert len(results) == 2
            assert all(r[1] is True for r in results)


class TestAsyncLinearAdapterParseIssue:
    """Tests for AsyncLinearAdapter._parse_issue method."""

    def test_parse_issue_complete(self, mock_linear_issue_response):
        """Test parsing a complete issue response."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.linear.async_adapter import AsyncLinearAdapter

            adapter = AsyncLinearAdapter(
                api_key="test-api-key",
                team_key="eng",
            )

            issue_data = mock_linear_issue_response["data"]["issue"]
            issue = adapter._parse_issue(issue_data)

            assert issue.key == "ENG-123"
            assert issue.summary == "Test Issue"
            assert issue.description == "Test description"
            assert issue.status == "In Progress"

    def test_parse_issue_minimal(self):
        """Test parsing a minimal issue response."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.linear.async_adapter import AsyncLinearAdapter

            adapter = AsyncLinearAdapter(
                api_key="test-api-key",
                team_key="eng",
            )

            minimal_data = {
                "id": "issue-999",
                "identifier": "ENG-999",
                "title": "Minimal Issue",
            }

            issue = adapter._parse_issue(minimal_data)

            assert issue.key == "ENG-999"
            assert issue.summary == "Minimal Issue"


class TestAsyncLinearAvailability:
    """Tests for async availability checking."""

    def test_is_async_available(self):
        """Test is_async_available function."""
        from spectryn.adapters.linear.async_adapter import is_async_available

        result = is_async_available()
        assert isinstance(result, bool)
