"""
Comprehensive tests for Jira async adapter and client.

Tests cover:
- AsyncJiraAdapter initialization and connection management
- Async read operations (get_issue, get_issues, search)
- Async write operations (update, create, transition, comments)
- Dry-run behavior
- Error handling
- AsyncJiraApiClient functionality
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from spectryn.core.ports.issue_tracker import IssueData


@pytest.fixture
def mock_tracker_config():
    """Create a mock tracker configuration."""
    config = MagicMock()
    config.url = "https://test.atlassian.net"
    config.email = "test@example.com"
    config.api_token = "test-token"
    config.project_key = "TEST"
    return config


@pytest.fixture
def mock_jira_issue_response():
    """Create a mock Jira issue API response."""
    return {
        "key": "TEST-123",
        "fields": {
            "summary": "Test Issue",
            "description": "Test description",
            "status": {"name": "Open"},
            "issuetype": {"name": "Story"},
            "subtasks": [
                {
                    "key": "TEST-124",
                    "fields": {
                        "summary": "Test Subtask",
                        "status": {"name": "To Do"},
                    },
                }
            ],
        },
    }


@pytest.fixture
def mock_jira_search_response():
    """Create a mock Jira search API response."""
    return {
        "issues": [
            {
                "key": "TEST-1",
                "fields": {
                    "summary": "Issue 1",
                    "status": {"name": "Open"},
                    "issuetype": {"name": "Story"},
                    "subtasks": [],
                },
            },
            {
                "key": "TEST-2",
                "fields": {
                    "summary": "Issue 2",
                    "status": {"name": "Done"},
                    "issuetype": {"name": "Bug"},
                    "subtasks": [],
                },
            },
        ],
        "total": 2,
    }


class TestAsyncJiraAdapterInit:
    """Tests for AsyncJiraAdapter initialization."""

    def test_init_requires_async_support(self, mock_tracker_config):
        """Test that adapter imports correctly when async is available."""
        from spectryn.adapters.jira.async_adapter import AsyncJiraAdapter

        adapter = AsyncJiraAdapter(
            config=mock_tracker_config,
            dry_run=True,
            concurrency=5,
        )

        assert adapter.config == mock_tracker_config
        assert adapter._dry_run is True
        assert adapter._concurrency == 5
        assert adapter._client is None

    def test_init_creates_default_formatter(self, mock_tracker_config):
        """Test that adapter creates default ADF formatter."""
        from spectryn.adapters.jira.async_adapter import AsyncJiraAdapter

        adapter = AsyncJiraAdapter(
            config=mock_tracker_config,
            dry_run=True,
        )

        assert adapter.formatter is not None


class TestAsyncJiraAdapterConnection:
    """Tests for AsyncJiraAdapter connection management."""

    @pytest.mark.asyncio
    async def test_connect_creates_client(self, mock_tracker_config):
        """Test that connect creates and initializes the client."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.jira.async_adapter import AsyncJiraAdapter

            with patch(
                "spectryn.adapters.jira.async_adapter.AsyncJiraApiClient"
            ) as mock_client_cls:
                mock_client = MagicMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_cls.return_value = mock_client

                adapter = AsyncJiraAdapter(
                    config=mock_tracker_config,
                    dry_run=True,
                )

                await adapter.connect()

                mock_client_cls.assert_called_once()
                assert adapter._client is not None

    @pytest.mark.asyncio
    async def test_disconnect_closes_client(self, mock_tracker_config):
        """Test that disconnect properly closes the client."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.jira.async_adapter import AsyncJiraAdapter

            with patch(
                "spectryn.adapters.jira.async_adapter.AsyncJiraApiClient"
            ) as mock_client_cls:
                mock_client = MagicMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_cls.return_value = mock_client

                adapter = AsyncJiraAdapter(
                    config=mock_tracker_config,
                    dry_run=True,
                )

                await adapter.connect()
                await adapter.disconnect()

                mock_client.__aexit__.assert_called_once()
                assert adapter._client is None

    @pytest.mark.asyncio
    async def test_ensure_connected_raises_when_not_connected(self, mock_tracker_config):
        """Test that operations fail when not connected."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.jira.async_adapter import AsyncJiraAdapter

            adapter = AsyncJiraAdapter(
                config=mock_tracker_config,
                dry_run=True,
            )

        with pytest.raises(RuntimeError, match="not connected"):
            adapter._ensure_connected()


class TestAsyncJiraAdapterReadOperations:
    """Tests for AsyncJiraAdapter read operations."""

    @pytest.mark.asyncio
    async def test_get_issue_async(self, mock_tracker_config, mock_jira_issue_response):
        """Test fetching a single issue asynchronously."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.jira.async_adapter import AsyncJiraAdapter

            with patch(
                "spectryn.adapters.jira.async_adapter.AsyncJiraApiClient"
            ) as mock_client_cls:
                mock_client = MagicMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_jira_issue_response)
                mock_client_cls.return_value = mock_client

                adapter = AsyncJiraAdapter(
                    config=mock_tracker_config,
                    dry_run=True,
                )

                await adapter.connect()
                issue = await adapter.get_issue_async("TEST-123")

                assert isinstance(issue, IssueData)
                assert issue.key == "TEST-123"
                assert issue.summary == "Test Issue"
                assert issue.status == "Open"
                assert len(issue.subtasks) == 1


class TestAsyncJiraAdapterWriteOperations:
    """Tests for AsyncJiraAdapter write operations."""

    @pytest.mark.asyncio
    async def test_update_descriptions_dry_run(self, mock_tracker_config):
        """Test update descriptions in dry-run mode."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.jira.async_adapter import AsyncJiraAdapter

            with patch(
                "spectryn.adapters.jira.async_adapter.AsyncJiraApiClient"
            ) as mock_client_cls:
                mock_client = MagicMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_cls.return_value = mock_client

                adapter = AsyncJiraAdapter(
                    config=mock_tracker_config,
                    dry_run=True,
                )

                await adapter.connect()
                updates = [
                    ("TEST-1", {"description": "New desc 1"}),
                    ("TEST-2", {"description": "New desc 2"}),
                ]
                results = await adapter.update_descriptions_async(updates)

                assert len(results) == 2
                assert all(r[1] is True for r in results)

    @pytest.mark.asyncio
    async def test_create_subtasks_dry_run(self, mock_tracker_config):
        """Test create subtasks in dry-run mode."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.jira.async_adapter import AsyncJiraAdapter

            with patch(
                "spectryn.adapters.jira.async_adapter.AsyncJiraApiClient"
            ) as mock_client_cls:
                mock_client = MagicMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_cls.return_value = mock_client

                adapter = AsyncJiraAdapter(
                    config=mock_tracker_config,
                    dry_run=True,
                )

                await adapter.connect()
                subtasks = [
                    {
                        "project_key": "TEST",
                        "parent_key": "TEST-1",
                        "summary": "Subtask 1",
                    },
                ]
                results = await adapter.create_subtasks_async(subtasks)

                assert len(results) == 1
                assert results[0][1] is True

    @pytest.mark.asyncio
    async def test_transition_issues_dry_run(self, mock_tracker_config):
        """Test transition issues in dry-run mode."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.jira.async_adapter import AsyncJiraAdapter

            with patch(
                "spectryn.adapters.jira.async_adapter.AsyncJiraApiClient"
            ) as mock_client_cls:
                mock_client = MagicMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_cls.return_value = mock_client

                adapter = AsyncJiraAdapter(
                    config=mock_tracker_config,
                    dry_run=True,
                )

                await adapter.connect()
                transitions = [("TEST-1", "Done"), ("TEST-2", "Done")]
                results = await adapter.transition_issues_async(transitions)

                assert len(results) == 2
                assert all(r[1] is True for r in results)

    @pytest.mark.asyncio
    async def test_add_comments_dry_run(self, mock_tracker_config):
        """Test add comments in dry-run mode."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.jira.async_adapter import AsyncJiraAdapter

            with patch(
                "spectryn.adapters.jira.async_adapter.AsyncJiraApiClient"
            ) as mock_client_cls:
                mock_client = MagicMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock()
                mock_client_cls.return_value = mock_client

                adapter = AsyncJiraAdapter(
                    config=mock_tracker_config,
                    dry_run=True,
                )

                await adapter.connect()
                comments = [("TEST-1", "Comment 1"), ("TEST-2", "Comment 2")]
                results = await adapter.add_comments_async(comments)

                assert len(results) == 2
                assert all(r[1] is True for r in results)


class TestAsyncJiraAdapterParseIssue:
    """Tests for AsyncJiraAdapter._parse_issue method."""

    def test_parse_issue_complete(self, mock_tracker_config, mock_jira_issue_response):
        """Test parsing a complete issue response."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.jira.async_adapter import AsyncJiraAdapter

            adapter = AsyncJiraAdapter(
                config=mock_tracker_config,
                dry_run=True,
            )

            issue = adapter._parse_issue(mock_jira_issue_response)

            assert issue.key == "TEST-123"
            assert issue.summary == "Test Issue"
            assert issue.description == "Test description"
            assert issue.status == "Open"
            assert issue.issue_type == "Story"
            assert len(issue.subtasks) == 1
            assert issue.subtasks[0].key == "TEST-124"

    def test_parse_issue_minimal(self, mock_tracker_config):
        """Test parsing a minimal issue response."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.jira.async_adapter import AsyncJiraAdapter

            adapter = AsyncJiraAdapter(
                config=mock_tracker_config,
                dry_run=True,
            )

            minimal_response = {
                "key": "TEST-999",
                "fields": {},
            }

            issue = adapter._parse_issue(minimal_response)

            assert issue.key == "TEST-999"
            assert issue.summary == ""
            assert issue.description is None
            assert issue.status == ""
            assert issue.subtasks == []


class TestAsyncJiraApiClientInit:
    """Tests for AsyncJiraApiClient initialization."""

    def test_init_sets_api_url(self):
        """Test that initialization correctly sets the API URL."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.jira.async_client import AsyncJiraApiClient

            client = AsyncJiraApiClient(
                base_url="https://test.atlassian.net",
                email="test@example.com",
                api_token="test-token",
            )

            assert "/rest/api/3" in client.base_url
            assert client.dry_run is True
            assert client.concurrency == 5

    def test_init_custom_settings(self):
        """Test initialization with custom settings."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.jira.async_client import AsyncJiraApiClient

            client = AsyncJiraApiClient(
                base_url="https://test.atlassian.net",
                email="test@example.com",
                api_token="test-token",
                dry_run=False,
                concurrency=10,
                max_retries=5,
                timeout=60.0,
            )

            assert client.dry_run is False
            assert client.concurrency == 10


class TestAsyncJiraApiClientDryRun:
    """Tests for AsyncJiraApiClient dry-run behavior."""

    @pytest.mark.asyncio
    async def test_post_dry_run_skips_write(self):
        """Test that POST requests are skipped in dry-run mode."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.jira.async_client import AsyncJiraApiClient

            client = AsyncJiraApiClient(
                base_url="https://test.atlassian.net",
                email="test@example.com",
                api_token="test-token",
                dry_run=True,
            )

            result = await client.post("issue", json={"fields": {}})
            assert result == {}

    @pytest.mark.asyncio
    async def test_put_dry_run_skips(self):
        """Test that PUT requests are skipped in dry-run mode."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.jira.async_client import AsyncJiraApiClient

            client = AsyncJiraApiClient(
                base_url="https://test.atlassian.net",
                email="test@example.com",
                api_token="test-token",
                dry_run=True,
            )

            result = await client.put("issue/TEST-1", json={"fields": {}})
            assert result == {}

    @pytest.mark.asyncio
    async def test_delete_dry_run_skips(self):
        """Test that DELETE requests are skipped in dry-run mode."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.jira.async_client import AsyncJiraApiClient

            client = AsyncJiraApiClient(
                base_url="https://test.atlassian.net",
                email="test@example.com",
                api_token="test-token",
                dry_run=True,
            )

            result = await client.delete("issue/TEST-1")
            assert result == {}


class TestAsyncJiraApiClientUserApi:
    """Tests for AsyncJiraApiClient user API methods."""

    @pytest.mark.asyncio
    async def test_get_myself_caches_result(self):
        """Test that get_myself caches the result."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.jira.async_client import AsyncJiraApiClient

            client = AsyncJiraApiClient(
                base_url="https://test.atlassian.net",
                email="test@example.com",
                api_token="test-token",
            )

            client._current_user = {"accountId": "123", "displayName": "Test User"}

            result = await client.get_myself()
            assert result["accountId"] == "123"

    @pytest.mark.asyncio
    async def test_get_current_user_id(self):
        """Test getting the current user ID."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.jira.async_client import AsyncJiraApiClient

            client = AsyncJiraApiClient(
                base_url="https://test.atlassian.net",
                email="test@example.com",
                api_token="test-token",
            )

            client._current_user = {"accountId": "user-123"}

            user_id = await client.get_current_user_id()
            assert user_id == "user-123"


class TestAsyncJiraApiClientIssueApi:
    """Tests for AsyncJiraApiClient issue API methods."""

    @pytest.mark.asyncio
    async def test_get_issue_with_fields(self):
        """Test getting an issue with specific fields."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.jira.async_client import AsyncJiraApiClient

            client = AsyncJiraApiClient(
                base_url="https://test.atlassian.net",
                email="test@example.com",
                api_token="test-token",
            )

            with patch.object(client, "get", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = {"key": "TEST-1", "fields": {}}

                await client.get_issue("TEST-1", fields=["summary", "status"])

                mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_issue(self):
        """Test updating an issue."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.jira.async_client import AsyncJiraApiClient

            client = AsyncJiraApiClient(
                base_url="https://test.atlassian.net",
                email="test@example.com",
                api_token="test-token",
                dry_run=False,
            )

            with patch.object(client, "put", new_callable=AsyncMock) as mock_put:
                mock_put.return_value = {}

                await client.update_issue("TEST-1", {"description": "New desc"})

                mock_put.assert_called_once_with(
                    "issue/TEST-1", json={"fields": {"description": "New desc"}}
                )

    @pytest.mark.asyncio
    async def test_create_issue(self):
        """Test creating an issue."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.jira.async_client import AsyncJiraApiClient

            client = AsyncJiraApiClient(
                base_url="https://test.atlassian.net",
                email="test@example.com",
                api_token="test-token",
                dry_run=False,
            )

            with patch.object(client, "post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = {"key": "TEST-100"}

                result = await client.create_issue({"summary": "New Issue"})

                mock_post.assert_called_once()
                assert result == {"key": "TEST-100"}


class TestAsyncJiraApiClientCommentsApi:
    """Tests for AsyncJiraApiClient comments API methods."""

    @pytest.mark.asyncio
    async def test_get_comments(self):
        """Test getting comments on an issue."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.jira.async_client import AsyncJiraApiClient

            client = AsyncJiraApiClient(
                base_url="https://test.atlassian.net",
                email="test@example.com",
                api_token="test-token",
            )

            with patch.object(client, "get", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = {
                    "comments": [
                        {"id": "1", "body": "Comment 1"},
                        {"id": "2", "body": "Comment 2"},
                    ]
                }

                result = await client.get_comments("TEST-1")

                assert len(result) == 2
                mock_get.assert_called_once_with("issue/TEST-1/comment")

    @pytest.mark.asyncio
    async def test_add_comment(self):
        """Test adding a comment to an issue."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.jira.async_client import AsyncJiraApiClient

            client = AsyncJiraApiClient(
                base_url="https://test.atlassian.net",
                email="test@example.com",
                api_token="test-token",
                dry_run=False,
            )

            with patch.object(client, "post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = {"id": "new-comment"}

                await client.add_comment("TEST-1", "New comment")

                mock_post.assert_called_once()


class TestAsyncJiraApiClientTransitionsApi:
    """Tests for AsyncJiraApiClient transitions API methods."""

    @pytest.mark.asyncio
    async def test_get_transitions(self):
        """Test getting available transitions for an issue."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.jira.async_client import AsyncJiraApiClient

            client = AsyncJiraApiClient(
                base_url="https://test.atlassian.net",
                email="test@example.com",
                api_token="test-token",
            )

            with patch.object(client, "get", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = {
                    "transitions": [
                        {"id": "1", "name": "Start"},
                        {"id": "2", "name": "Done"},
                    ]
                }

                result = await client.get_transitions("TEST-1")

                assert len(result) == 2
                mock_get.assert_called_once_with("issue/TEST-1/transitions")

    @pytest.mark.asyncio
    async def test_transition_issue(self):
        """Test transitioning an issue."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.jira.async_client import AsyncJiraApiClient

            client = AsyncJiraApiClient(
                base_url="https://test.atlassian.net",
                email="test@example.com",
                api_token="test-token",
                dry_run=False,
            )

            with patch.object(client, "post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = {}

                await client.transition_issue("TEST-1", "2")

                mock_post.assert_called_once()


class TestAsyncJiraApiClientSearchApi:
    """Tests for AsyncJiraApiClient search API methods."""

    @pytest.mark.asyncio
    async def test_search_jql(self):
        """Test JQL search."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.jira.async_client import AsyncJiraApiClient

            client = AsyncJiraApiClient(
                base_url="https://test.atlassian.net",
                email="test@example.com",
                api_token="test-token",
            )

            with patch.object(client, "post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = {"issues": [], "total": 0}

                result = await client.search_jql(
                    "project = TEST",
                    ["summary", "status"],
                    max_results=50,
                )

                mock_post.assert_called_once()
                assert result == {"issues": [], "total": 0}

    @pytest.mark.asyncio
    async def test_search_all_jql_single_page(self):
        """Test JQL search with single page of results."""
        with patch.dict("sys.modules", {"aiohttp": MagicMock()}):
            from spectryn.adapters.jira.async_client import AsyncJiraApiClient

            client = AsyncJiraApiClient(
                base_url="https://test.atlassian.net",
                email="test@example.com",
                api_token="test-token",
            )

            with patch.object(client, "search_jql", new_callable=AsyncMock) as mock_search:
                mock_search.return_value = {
                    "issues": [{"key": "TEST-1"}, {"key": "TEST-2"}],
                    "total": 2,
                }

                result = await client.search_all_jql(
                    "project = TEST",
                    ["summary"],
                )

                assert len(result) == 2
                mock_search.assert_called_once()


class TestAsyncAvailability:
    """Tests for async availability checking."""

    def test_is_async_available(self):
        """Test is_async_available function."""
        from spectryn.adapters.jira.async_adapter import is_async_available

        result = is_async_available()
        assert isinstance(result, bool)
