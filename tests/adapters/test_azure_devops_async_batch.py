"""
Tests for Azure DevOps async adapter and batch operations.

These tests cover the low-coverage modules:
- src/spectra/adapters/azure_devops/async_adapter.py
- src/spectra/adapters/azure_devops/batch.py
"""

from collections.abc import Generator
from unittest.mock import MagicMock, Mock, patch

import pytest


# =============================================================================
# Azure DevOps Batch Client Tests
# =============================================================================


class TestBatchOperation:
    """Tests for BatchOperation dataclass."""

    def test_batch_operation_success_str(self) -> None:
        """Test string representation for successful operation."""
        from spectryn.adapters.azure_devops.batch import BatchOperation

        op = BatchOperation(index=0, success=True, key="123")
        assert str(op) == "[0] 123: OK"

    def test_batch_operation_failure_str(self) -> None:
        """Test string representation for failed operation."""
        from spectryn.adapters.azure_devops.batch import BatchOperation

        op = BatchOperation(index=1, success=False, key="456", error="Connection failed")
        assert str(op) == "[1] 456: FAILED - Connection failed"

    def test_batch_operation_failure_no_key(self) -> None:
        """Test failure without key shows N/A."""
        from spectryn.adapters.azure_devops.batch import BatchOperation

        op = BatchOperation(index=2, success=False, error="Missing parent")
        assert str(op) == "[2] N/A: FAILED - Missing parent"


class TestBatchResult:
    """Tests for BatchResult dataclass."""

    def test_empty_result(self) -> None:
        """Test empty batch result."""
        from spectryn.adapters.azure_devops.batch import BatchResult

        result = BatchResult()
        assert result.success is True
        assert result.total == 0
        assert result.succeeded == 0
        assert result.failed == 0
        assert result.created_keys == []
        assert result.failed_indices == []

    def test_add_success(self) -> None:
        """Test adding successful operations."""
        from spectryn.adapters.azure_devops.batch import BatchResult

        result = BatchResult()
        result.add_success(0, "123", {"title": "Task 1"})
        result.add_success(1, "456", {"title": "Task 2"})

        assert result.success is True
        assert result.total == 2
        assert result.succeeded == 2
        assert result.failed == 0
        assert result.created_keys == ["123", "456"]
        assert result.failed_indices == []

    def test_add_failure(self) -> None:
        """Test adding failed operations."""
        from spectryn.adapters.azure_devops.batch import BatchResult

        result = BatchResult()
        result.add_failure(0, "Connection error", "123")
        result.add_failure(1, "Timeout", "456")

        assert result.success is False
        assert result.total == 2
        assert result.succeeded == 0
        assert result.failed == 2
        assert result.created_keys == []
        assert result.failed_indices == [0, 1]
        assert "Connection error" in result.errors
        assert "Timeout" in result.errors

    def test_mixed_success_and_failure(self) -> None:
        """Test mix of successful and failed operations."""
        from spectryn.adapters.azure_devops.batch import BatchResult

        result = BatchResult()
        result.add_success(0, "123")
        result.add_failure(1, "Error", "456")
        result.add_success(2, "789")

        assert result.success is False
        assert result.total == 3
        assert result.succeeded == 2
        assert result.failed == 1
        assert result.created_keys == ["123", "789"]
        assert result.failed_indices == [1]

    def test_summary(self) -> None:
        """Test summary generation."""
        from spectryn.adapters.azure_devops.batch import BatchResult

        result = BatchResult()
        result.add_success(0, "123")
        result.add_failure(1, "Error")
        result.add_success(2, "456")

        assert "2/3 succeeded" in result.summary()
        assert "1 failed" in result.summary()


class TestAzureDevOpsBatchClient:
    """Tests for AzureDevOpsBatchClient."""

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        """Create a mock AzureDevOpsApiClient."""
        client = MagicMock()
        client.dry_run = False
        return client

    @pytest.fixture
    def batch_client(self, mock_client: MagicMock) -> Generator:
        """Create a batch client with mock."""
        from spectryn.adapters.azure_devops.batch import AzureDevOpsBatchClient

        return AzureDevOpsBatchClient(client=mock_client, max_workers=5)

    def test_parse_work_item_id_valid(self, batch_client) -> None:
        """Test parsing valid work item IDs."""
        assert batch_client._parse_work_item_id("123") == 123
        assert batch_client._parse_work_item_id("WI-456") == 456
        assert batch_client._parse_work_item_id("#789") == 789

    def test_parse_work_item_id_invalid(self, batch_client) -> None:
        """Test parsing invalid work item IDs."""
        with pytest.raises(ValueError, match="Invalid work item key"):
            batch_client._parse_work_item_id("no-numbers-here")

    def test_markdown_to_html_headings(self, batch_client) -> None:
        """Test markdown to HTML conversion for headings."""
        html = batch_client._markdown_to_html("# H1\n## H2\n### H3")
        assert "<h1>H1</h1>" in html
        assert "<h2>H2</h2>" in html
        assert "<h3>H3</h3>" in html

    def test_markdown_to_html_formatting(self, batch_client) -> None:
        """Test markdown to HTML conversion for formatting."""
        html = batch_client._markdown_to_html("**bold** and *italic*")
        assert "<strong>bold</strong>" in html
        assert "<em>italic</em>" in html

    def test_markdown_to_html_code(self, batch_client) -> None:
        """Test markdown to HTML conversion for code."""
        html = batch_client._markdown_to_html("`inline code`")
        assert "<code>inline code</code>" in html

    def test_markdown_to_html_links(self, batch_client) -> None:
        """Test markdown to HTML conversion for links."""
        html = batch_client._markdown_to_html("[link](https://example.com)")
        assert '<a href="https://example.com">link</a>' in html

    # -------------------------------------------------------------------------
    # Bulk Create Subtasks
    # -------------------------------------------------------------------------

    def test_bulk_create_subtasks_empty(self, batch_client) -> None:
        """Test bulk create with empty list."""
        result = batch_client.bulk_create_subtasks([])
        assert result.total == 0
        assert result.success is True

    def test_bulk_create_subtasks_dry_run(self, mock_client) -> None:
        """Test bulk create in dry run mode."""
        from spectryn.adapters.azure_devops.batch import AzureDevOpsBatchClient

        mock_client.dry_run = True
        batch_client = AzureDevOpsBatchClient(client=mock_client)

        subtasks = [
            {"parent_key": "100", "summary": "Task 1"},
            {"parent_key": "100", "summary": "Task 2"},
        ]
        result = batch_client.bulk_create_subtasks(subtasks)

        assert result.total == 2
        assert result.succeeded == 2
        assert result.failed == 0
        mock_client.create_work_item.assert_not_called()

    def test_bulk_create_subtasks_success(self, batch_client, mock_client) -> None:
        """Test successful bulk create."""
        mock_client.create_work_item.side_effect = [
            {"id": 201},
            {"id": 202},
        ]

        subtasks = [
            {"parent_key": "100", "summary": "Task 1", "description": "Desc 1"},
            {"parent_key": "100", "summary": "Task 2", "description": "Desc 2", "story_points": 3},
        ]
        result = batch_client.bulk_create_subtasks(subtasks)

        assert result.total == 2
        assert result.succeeded == 2
        assert "201" in result.created_keys
        assert "202" in result.created_keys

    def test_bulk_create_subtasks_missing_parent(self, batch_client, mock_client) -> None:
        """Test bulk create with missing parent key."""
        subtasks = [
            {"summary": "Task without parent"},  # Missing parent_key
        ]
        result = batch_client.bulk_create_subtasks(subtasks)

        assert result.total == 1
        assert result.failed == 1
        assert "Missing parent_key" in result.errors[0]

    def test_bulk_create_subtasks_api_error(self, batch_client, mock_client) -> None:
        """Test bulk create with API error."""
        from spectryn.core.ports.issue_tracker import IssueTrackerError

        mock_client.create_work_item.side_effect = IssueTrackerError("API failure")

        subtasks = [
            {"parent_key": "100", "summary": "Task 1"},
        ]
        result = batch_client.bulk_create_subtasks(subtasks)

        assert result.total == 1
        assert result.failed == 1
        assert "API failure" in result.errors[0]

    # -------------------------------------------------------------------------
    # Bulk Update Work Items
    # -------------------------------------------------------------------------

    def test_bulk_update_work_items_empty(self, batch_client) -> None:
        """Test bulk update with empty list."""
        result = batch_client.bulk_update_work_items([])
        assert result.total == 0

    def test_bulk_update_work_items_dry_run(self, mock_client) -> None:
        """Test bulk update in dry run mode."""
        from spectryn.adapters.azure_devops.batch import AzureDevOpsBatchClient

        mock_client.dry_run = True
        batch_client = AzureDevOpsBatchClient(client=mock_client)

        updates = [
            {"work_item_id": 100, "title": "Updated Title"},
        ]
        result = batch_client.bulk_update_work_items(updates)

        assert result.total == 1
        assert result.succeeded == 1
        mock_client.update_work_item.assert_not_called()

    def test_bulk_update_work_items_success(self, batch_client, mock_client) -> None:
        """Test successful bulk update."""
        mock_client.update_work_item.return_value = {}

        updates = [
            {"work_item_id": 100, "title": "Title 1"},
            {"work_item_id": 101, "description": "Desc 2"},
        ]
        result = batch_client.bulk_update_work_items(updates)

        assert result.total == 2
        assert result.succeeded == 2

    def test_bulk_update_work_items_missing_id(self, batch_client) -> None:
        """Test bulk update with missing work item ID."""
        updates = [
            {"title": "No ID provided"},  # Missing work_item_id
        ]
        result = batch_client.bulk_update_work_items(updates)

        assert result.total == 1
        assert result.failed == 1
        assert "Missing work_item_id" in result.errors[0]

    def test_bulk_update_descriptions(self, batch_client, mock_client) -> None:
        """Test bulk update descriptions helper."""
        mock_client.update_work_item.return_value = {}

        updates = [
            ("100", "# New description"),
            ("101", "Another update"),
        ]
        result = batch_client.bulk_update_descriptions(updates)

        assert result.total == 2
        assert result.succeeded == 2

    # -------------------------------------------------------------------------
    # Bulk Transition Work Items
    # -------------------------------------------------------------------------

    def test_bulk_transition_empty(self, batch_client) -> None:
        """Test bulk transition with empty list."""
        result = batch_client.bulk_transition_work_items([])
        assert result.total == 0

    def test_bulk_transition_dry_run(self, mock_client) -> None:
        """Test bulk transition in dry run mode."""
        from spectryn.adapters.azure_devops.batch import AzureDevOpsBatchClient

        mock_client.dry_run = True
        batch_client = AzureDevOpsBatchClient(client=mock_client)

        transitions = [("100", "Done"), ("101", "Active")]
        result = batch_client.bulk_transition_work_items(transitions)

        assert result.total == 2
        assert result.succeeded == 2
        mock_client.update_work_item.assert_not_called()

    def test_bulk_transition_success(self, batch_client, mock_client) -> None:
        """Test successful bulk transition."""
        mock_client.update_work_item.return_value = {}

        transitions = [("100", "Done"), ("101", "Active")]
        result = batch_client.bulk_transition_work_items(transitions)

        assert result.total == 2
        assert result.succeeded == 2

    def test_bulk_transition_error(self, batch_client, mock_client) -> None:
        """Test bulk transition with error."""
        from spectryn.core.ports.issue_tracker import IssueTrackerError

        mock_client.update_work_item.side_effect = IssueTrackerError("Invalid state")

        transitions = [("100", "InvalidState")]
        result = batch_client.bulk_transition_work_items(transitions)

        assert result.total == 1
        assert result.failed == 1

    # -------------------------------------------------------------------------
    # Bulk Add Comments
    # -------------------------------------------------------------------------

    def test_bulk_add_comments_empty(self, batch_client) -> None:
        """Test bulk add comments with empty list."""
        result = batch_client.bulk_add_comments([])
        assert result.total == 0

    def test_bulk_add_comments_dry_run(self, mock_client) -> None:
        """Test bulk add comments in dry run mode."""
        from spectryn.adapters.azure_devops.batch import AzureDevOpsBatchClient

        mock_client.dry_run = True
        batch_client = AzureDevOpsBatchClient(client=mock_client)

        comments = [("100", "Comment 1"), ("101", "Comment 2")]
        result = batch_client.bulk_add_comments(comments)

        assert result.total == 2
        assert result.succeeded == 2
        mock_client.add_comment.assert_not_called()

    def test_bulk_add_comments_success(self, batch_client, mock_client) -> None:
        """Test successful bulk add comments."""
        mock_client.add_comment.return_value = {}

        comments = [("100", "Comment 1"), ("101", "Comment 2")]
        result = batch_client.bulk_add_comments(comments)

        assert result.total == 2
        assert result.succeeded == 2

    # -------------------------------------------------------------------------
    # Bulk Get Work Items
    # -------------------------------------------------------------------------

    def test_bulk_get_work_items_empty(self, batch_client) -> None:
        """Test bulk get with empty list."""
        result = batch_client.bulk_get_work_items([])
        assert result.total == 0

    def test_bulk_get_work_items_success(self, batch_client, mock_client) -> None:
        """Test successful bulk get."""
        mock_client.get_work_item.side_effect = [
            {"id": 100, "fields": {"System.Title": "Task 1"}},
            {"id": 101, "fields": {"System.Title": "Task 2"}},
        ]

        result = batch_client.bulk_get_work_items([100, 101])

        assert result.total == 2
        assert result.succeeded == 2
        assert len(result.created_keys) == 2

    def test_bulk_get_work_items_error(self, batch_client, mock_client) -> None:
        """Test bulk get with error."""
        from spectryn.core.ports.issue_tracker import IssueTrackerError

        mock_client.get_work_item.side_effect = IssueTrackerError("Not found")

        result = batch_client.bulk_get_work_items([999])

        assert result.total == 1
        assert result.failed == 1


# =============================================================================
# Azure DevOps Async Adapter Tests
# =============================================================================


class TestAsyncAzureDevOpsAdapterWithoutAiohttp:
    """Test async adapter behavior when aiohttp is not available."""

    def test_import_error_when_aiohttp_missing(self) -> None:
        """Test that ImportError is raised when aiohttp is not installed."""
        with patch.dict("sys.modules", {"aiohttp": None}):
            # Need to reload the module to test the import check
            import importlib

            from spectryn.adapters.azure_devops import async_adapter

            # Temporarily set ASYNC_AVAILABLE to False
            original = async_adapter.ASYNC_AVAILABLE

            try:
                async_adapter.ASYNC_AVAILABLE = False

                with pytest.raises(ImportError, match="aiohttp"):
                    async_adapter.AsyncAzureDevOpsAdapter(
                        organization="test-org",
                        project="test-project",
                        pat="test-pat",
                    )
            finally:
                async_adapter.ASYNC_AVAILABLE = original


@pytest.mark.asyncio
class TestAsyncAzureDevOpsAdapter:
    """Tests for AsyncAzureDevOpsAdapter."""

    @pytest.fixture
    def mock_aiohttp_session(self) -> MagicMock:
        """Create a mock aiohttp session."""
        return MagicMock()

    @pytest.fixture
    def adapter(self) -> Generator:
        """Create an async adapter for testing."""
        # Skip if aiohttp not available
        pytest.importorskip("aiohttp")

        from spectryn.adapters.azure_devops.async_adapter import AsyncAzureDevOpsAdapter

        return AsyncAzureDevOpsAdapter(
            organization="test-org",
            project="test-project",
            pat="test-pat",
            dry_run=True,
        )

    def test_init(self) -> None:
        """Test adapter initialization."""
        pytest.importorskip("aiohttp")
        from spectryn.adapters.azure_devops.async_adapter import AsyncAzureDevOpsAdapter

        adapter = AsyncAzureDevOpsAdapter(
            organization="my-org",
            project="my-project",
            pat="my-pat",
            dry_run=True,
            base_url="https://custom.azure.com",
            concurrency=5,
            timeout=60,
        )

        assert adapter.organization == "my-org"
        assert adapter.project == "my-project"
        assert adapter._dry_run is True
        assert adapter.base_url == "https://custom.azure.com"
        assert adapter._concurrency == 5
        assert adapter.timeout == 60

    def test_build_url_wit(self, adapter) -> None:
        """Test URL building for WIT area."""
        url = adapter._build_url("workitems/123")
        assert "test-org" in url
        assert "test-project" in url
        assert "_apis/wit/workitems/123" in url
        assert "api-version=" in url

    def test_build_url_core(self, adapter) -> None:
        """Test URL building for core area."""
        url = adapter._build_url("projects", area="core")
        assert "test-org" in url
        assert "_apis/projects" in url

    def test_build_url_full(self, adapter) -> None:
        """Test URL building with full URL."""
        full_url = "https://example.com/api/items"
        result = adapter._build_url(full_url)
        assert result == full_url

    def test_parse_work_item_id(self, adapter) -> None:
        """Test work item ID parsing."""
        assert adapter._parse_work_item_id("123") == 123
        assert adapter._parse_work_item_id("WI-456") == 456

    def test_parse_work_item_id_invalid(self, adapter) -> None:
        """Test invalid work item ID."""
        with pytest.raises(ValueError):
            adapter._parse_work_item_id("abc")

    def test_ensure_connected_raises(self, adapter) -> None:
        """Test ensure connected raises when not connected."""
        with pytest.raises(RuntimeError, match="not connected"):
            adapter._ensure_connected()

    def test_parse_work_item(self, adapter) -> None:
        """Test parsing work item data."""
        data = {
            "id": 123,
            "fields": {
                "System.Title": "Test Task",
                "System.Description": "<p>Description</p>",
                "System.State": "Active",
                "System.WorkItemType": "Task",
                "System.AssignedTo": {"uniqueName": "user@example.com"},
                "Microsoft.VSTS.Scheduling.StoryPoints": 5.0,
            },
        }

        issue = adapter._parse_work_item(data)

        assert issue.key == "123"
        assert issue.summary == "Test Task"
        assert issue.status == "Active"
        assert issue.issue_type == "Sub-task"  # Task maps to Sub-task
        assert issue.assignee == "user@example.com"
        assert issue.story_points == 5.0

    def test_parse_work_item_story_type(self, adapter) -> None:
        """Test parsing user story work item."""
        data = {
            "id": 456,
            "fields": {
                "System.Title": "User Story",
                "System.State": "New",
                "System.WorkItemType": "User Story",
            },
        }

        issue = adapter._parse_work_item(data)
        assert issue.issue_type == "Story"

    def test_markdown_to_html(self, adapter) -> None:
        """Test markdown to HTML conversion."""
        md = "# Title\n**bold** and *italic*\n`code`"
        html = adapter._markdown_to_html(md)

        assert "<h1>Title</h1>" in html
        assert "<strong>bold</strong>" in html
        assert "<em>italic</em>" in html
        assert "<code>code</code>" in html

    async def test_context_manager(self) -> None:
        """Test async context manager."""
        pytest.importorskip("aiohttp")
        from spectryn.adapters.azure_devops.async_adapter import AsyncAzureDevOpsAdapter

        adapter = AsyncAzureDevOpsAdapter(
            organization="test-org",
            project="test-project",
            pat="test-pat",
            dry_run=True,
        )

        async with adapter:
            assert adapter._session is not None
            assert adapter._semaphore is not None

        assert adapter._session is None

    async def test_update_descriptions_dry_run(self, adapter) -> None:
        """Test update descriptions in dry run mode."""
        # Connect first
        await adapter.connect()
        try:
            updates = [("100", "New desc 1"), ("101", "New desc 2")]
            results = await adapter.update_descriptions_async(updates)

            assert len(results) == 2
            assert all(r[1] for r in results)  # All succeeded
        finally:
            await adapter.disconnect()

    async def test_create_subtasks_dry_run(self, adapter) -> None:
        """Test create subtasks in dry run mode."""
        await adapter.connect()
        try:
            subtasks = [
                {"parent_key": "100", "summary": "Task 1"},
                {"parent_key": "100", "summary": "Task 2"},
            ]
            results = await adapter.create_subtasks_async(subtasks)

            assert len(results) == 2
            assert all(r[1] for r in results)
        finally:
            await adapter.disconnect()

    async def test_transition_issues_dry_run(self, adapter) -> None:
        """Test transition issues in dry run mode."""
        await adapter.connect()
        try:
            transitions = [("100", "Done"), ("101", "Active")]
            results = await adapter.transition_issues_async(transitions)

            assert len(results) == 2
            assert all(r[1] for r in results)
        finally:
            await adapter.disconnect()

    async def test_add_comments_dry_run(self, adapter) -> None:
        """Test add comments in dry run mode."""
        await adapter.connect()
        try:
            comments = [("100", "Comment 1"), ("101", "Comment 2")]
            results = await adapter.add_comments_async(comments)

            assert len(results) == 2
            assert all(r[1] for r in results)
        finally:
            await adapter.disconnect()


class TestIsAsyncAvailable:
    """Tests for is_async_available function."""

    def test_is_async_available(self) -> None:
        """Test is_async_available function."""
        from spectryn.adapters.azure_devops.async_adapter import is_async_available

        # Should return a boolean
        result = is_async_available()
        assert isinstance(result, bool)
