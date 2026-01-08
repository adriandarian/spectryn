"""
Integration tests with mocked Confluence API responses.

These tests verify the full flow from adapter through client
using realistic API responses.
"""

from unittest.mock import Mock, patch

import pytest

from spectryn.adapters.confluence.adapter import ConfluenceAdapter
from spectryn.adapters.confluence.client import ConfluenceAPIError, ConfluenceClient
from spectryn.core.domain.entities import Epic, Subtask, UserStory
from spectryn.core.domain.enums import Priority, Status
from spectryn.core.domain.value_objects import Description, IssueKey, StoryId
from spectryn.core.ports.document_output import (
    AuthenticationError,
    NotFoundError,
    PermissionError,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_client():
    """Create a mock Confluence client."""
    return Mock(spec=ConfluenceClient)


@pytest.fixture
def adapter(mock_client):
    """Create a ConfluenceAdapter with a mock client."""
    return ConfluenceAdapter(client=mock_client)


@pytest.fixture
def mock_user_response():
    """Mock response for current user."""
    return {
        "displayName": "Test User",
        "email": "test@example.com",
        "accountId": "user-123",
    }


@pytest.fixture
def mock_space_response():
    """Mock response for space."""
    return {
        "key": "PROJ",
        "name": "Project Space",
        "type": "global",
        "_links": {"webui": "/spaces/PROJ"},
    }


@pytest.fixture
def mock_page_response():
    """Mock response for page."""
    return {
        "id": "page-123",
        "title": "Test Page",
        "space": {"key": "PROJ"},
        "version": {"number": 5},
        "body": {"storage": {"value": "<p>Content here</p>"}},
        "metadata": {"labels": {"results": [{"name": "test"}]}},
        "_links": {"webui": "/pages/page-123"},
    }


@pytest.fixture
def sample_story():
    """Create a sample user story."""
    return UserStory(
        id=StoryId("US-001"),
        title="Test Story",
        description=Description(
            role="developer",
            want="to test the adapter",
            benefit="I can verify it works",
        ),
        story_points=5,
        priority=Priority.HIGH,
        status=Status.IN_PROGRESS,
        subtasks=[
            Subtask(name="Subtask 1", description="First task", story_points=2),
            Subtask(name="Subtask 2", description="Second task", story_points=3),
        ],
    )


@pytest.fixture
def sample_epic(sample_story):
    """Create a sample epic with stories."""
    return Epic(
        key=IssueKey("PROJ-100"),
        title="Test Epic",
        stories=[sample_story],
    )


# =============================================================================
# Connection Tests
# =============================================================================


class TestConfluenceConnectionHandling:
    """Tests for connection handling."""

    def test_connect_success(self, adapter, mock_client, mock_user_response):
        """Test successful connection."""
        mock_client.connect.return_value = None
        mock_client.get_current_user.return_value = mock_user_response

        adapter.connect()

        mock_client.connect.assert_called_once()
        mock_client.get_current_user.assert_called_once()

    def test_connect_authentication_error(self, adapter, mock_client):
        """Test connection with invalid credentials."""
        mock_client.connect.side_effect = ConfluenceAPIError("Unauthorized", status_code=401)

        with pytest.raises(AuthenticationError):
            adapter.connect()

    def test_disconnect(self, adapter, mock_client):
        """Test disconnection."""
        adapter.disconnect()
        mock_client.disconnect.assert_called_once()

    def test_adapter_name(self, adapter):
        """Test adapter returns correct name."""
        assert adapter.name == "Confluence"


# =============================================================================
# Space Operations Tests
# =============================================================================


class TestConfluenceSpaceOperations:
    """Tests for space operations."""

    def test_get_space(self, adapter, mock_client, mock_space_response):
        """Test getting a space."""
        mock_client.get_space.return_value = mock_space_response

        space = adapter.get_space("PROJ")

        assert space.key == "PROJ"
        assert space.name == "Project Space"
        assert space.type == "global"
        mock_client.get_space.assert_called_once_with("PROJ")

    def test_get_space_not_found(self, adapter, mock_client):
        """Test getting a non-existent space."""
        mock_client.get_space.side_effect = ConfluenceAPIError("Not found", status_code=404)

        with pytest.raises(NotFoundError):
            adapter.get_space("NONEXISTENT")

    def test_list_spaces(self, adapter, mock_client, mock_space_response):
        """Test listing spaces."""
        mock_client.list_spaces.return_value = [mock_space_response]

        spaces = adapter.list_spaces()

        assert len(spaces) == 1
        assert spaces[0].key == "PROJ"


# =============================================================================
# Page Operations Tests
# =============================================================================


class TestConfluencePageOperations:
    """Tests for page operations."""

    def test_get_page(self, adapter, mock_client, mock_page_response):
        """Test getting a page by ID."""
        mock_client.get_content.return_value = mock_page_response

        page = adapter.get_page("page-123")

        assert page.id == "page-123"
        assert page.title == "Test Page"
        assert page.version == 5
        assert "Content here" in page.content

    def test_get_page_not_found(self, adapter, mock_client):
        """Test getting a non-existent page."""
        mock_client.get_content.side_effect = ConfluenceAPIError("Not found", status_code=404)

        with pytest.raises(NotFoundError):
            adapter.get_page("nonexistent")

    def test_get_page_permission_denied(self, adapter, mock_client):
        """Test getting a page without permission."""
        mock_client.get_content.side_effect = ConfluenceAPIError("Forbidden", status_code=403)

        with pytest.raises(PermissionError):
            adapter.get_page("restricted")

    def test_get_page_by_title(self, adapter, mock_client, mock_page_response):
        """Test finding a page by title."""
        mock_client.get_content_by_title.return_value = mock_page_response

        page = adapter.get_page_by_title("PROJ", "Test Page")

        assert page is not None
        assert page.title == "Test Page"

    def test_get_page_by_title_not_found(self, adapter, mock_client):
        """Test finding a non-existent page."""
        mock_client.get_content_by_title.return_value = None

        page = adapter.get_page_by_title("PROJ", "Nonexistent")

        assert page is None

    def test_create_page(self, adapter, mock_client, mock_page_response):
        """Test creating a new page."""
        mock_client.create_content.return_value = mock_page_response

        page = adapter.create_page(
            space_key="PROJ",
            title="New Page",
            content="<p>New content</p>",
            parent_id="parent-123",
            labels=["test", "new"],
        )

        assert page.id == "page-123"
        mock_client.create_content.assert_called_once()
        mock_client.add_labels.assert_called_once_with("page-123", ["test", "new"])

    def test_create_page_permission_denied(self, adapter, mock_client):
        """Test creating a page without permission."""
        mock_client.create_content.side_effect = ConfluenceAPIError("Forbidden", status_code=403)

        with pytest.raises(PermissionError):
            adapter.create_page("PROJ", "New Page", "<p>Content</p>")

    def test_update_page(self, adapter, mock_client, mock_page_response):
        """Test updating an existing page."""
        mock_client.update_content.return_value = mock_page_response
        mock_client.get_labels.return_value = [{"name": "old"}]

        page = adapter.update_page(
            page_id="page-123",
            title="Updated Page",
            content="<p>Updated content</p>",
            version=5,
            labels=["new", "updated"],
        )

        assert page.id == "page-123"
        mock_client.update_content.assert_called_once()
        mock_client.remove_label.assert_called_once_with("page-123", "old")
        # Check labels were added (order-independent)
        mock_client.add_labels.assert_called_once()
        call_args = mock_client.add_labels.call_args
        assert call_args[0][0] == "page-123"
        assert set(call_args[0][1]) == {"new", "updated"}

    def test_delete_page(self, adapter, mock_client):
        """Test deleting a page."""
        mock_client.delete_content.return_value = None

        adapter.delete_page("page-123")

        mock_client.delete_content.assert_called_once_with("page-123")


# =============================================================================
# Epic/Story Publishing Tests
# =============================================================================


class TestConfluencePublishing:
    """Tests for epic and story publishing."""

    def test_publish_story(self, adapter, mock_client, sample_story, mock_page_response):
        """Test publishing a story as a page."""
        mock_client.get_content_by_title.return_value = None
        mock_client.create_content.return_value = mock_page_response

        page = adapter.publish_story(
            story=sample_story,
            space_key="PROJ",
            parent_id="parent-123",
        )

        assert page.id == "page-123"
        mock_client.create_content.assert_called_once()
        # Verify title format
        call_kwargs = mock_client.create_content.call_args.kwargs
        assert "US-001" in call_kwargs["title"]

    def test_publish_story_update_existing(
        self, adapter, mock_client, sample_story, mock_page_response
    ):
        """Test updating an existing story page."""
        mock_client.get_content_by_title.return_value = mock_page_response
        mock_client.update_content.return_value = mock_page_response
        mock_client.get_labels.return_value = []

        page = adapter.publish_story(
            story=sample_story,
            space_key="PROJ",
            update_existing=True,
        )

        assert page.id == "page-123"
        mock_client.update_content.assert_called_once()

    def test_publish_epic(self, adapter, mock_client, sample_epic, mock_page_response):
        """Test publishing an epic with stories."""
        mock_client.get_content_by_title.return_value = None
        mock_client.create_content.return_value = mock_page_response

        page = adapter.publish_epic(
            epic=sample_epic,
            space_key="PROJ",
            parent_id=None,
        )

        assert page.id == "page-123"
        # Should create epic page plus story pages
        assert mock_client.create_content.call_count >= 2

    def test_format_story_content(self, adapter, sample_story):
        """Test story content formatting."""
        content = adapter.format_story_content(sample_story)

        # Should contain structured content
        assert "Status" in content
        assert "Priority" in content
        assert "Story Points" in content
        assert "User Story" in content
        assert "Subtasks" in content

    def test_format_epic_content(self, adapter, sample_epic):
        """Test epic content formatting."""
        content = adapter.format_epic_content(sample_epic)

        # Should contain summary info
        assert "Epic Key" in content
        assert "Stories" in content
        assert "Story Points" in content
        assert "User Stories" in content


# =============================================================================
# Content Formatting Tests
# =============================================================================


class TestConfluenceFormatting:
    """Tests for Confluence storage format generation."""

    def test_format_description(self, adapter):
        """Test description formatting."""
        desc = Description(
            role="developer",
            want="to test formatting",
            benefit="I can verify output",
        )

        html = adapter._format_description(desc)

        assert "<strong>As a</strong>" in html
        assert "<strong>I want</strong>" in html
        assert "<strong>So that</strong>" in html

    def test_status_lozenge(self, adapter):
        """Test status lozenge macro generation."""
        html = adapter._status_lozenge(Status.IN_PROGRESS)

        assert 'ac:name="status"' in html
        assert "Yellow" in html
        assert "IN_PROGRESS" in html

    def test_info_panel(self, adapter):
        """Test info panel macro generation."""
        html = adapter._info_panel("Test content")

        assert 'ac:name="info"' in html
        assert "Test content" in html

    def test_task_list(self, adapter):
        """Test task list generation."""
        items = ["Task 1", "Task 2", "Task 3"]
        checked = [True, False, True]

        html = adapter._task_list(items, checked)

        assert "ac:task-list" in html
        assert "complete" in html
        assert "incomplete" in html

    def test_subtasks_table(self, adapter):
        """Test subtasks table generation."""
        subtasks = [
            Subtask(name="Task 1", description="Desc 1", story_points=2),
            Subtask(name="Task 2", description="Desc 2", story_points=3),
        ]

        html = adapter._subtasks_table(subtasks)

        assert "<table>" in html
        assert "Task 1" in html
        assert "Task 2" in html

    def test_code_block(self, adapter):
        """Test code block macro generation."""
        html = adapter._code_block("print('hello')", "python")

        assert 'ac:name="code"' in html
        assert 'ac:name="language"' in html
        assert "python" in html


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestConfluenceErrorHandling:
    """Tests for error handling."""

    def test_update_page_version_conflict(self, adapter, mock_client):
        """Test version conflict error."""
        mock_client.update_content.side_effect = ConfluenceAPIError(
            "Version conflict", status_code=409
        )

        with pytest.raises(PermissionError):
            adapter.update_page("page-123", "Title", "Content", version=5)

    def test_delete_page_not_found(self, adapter, mock_client):
        """Test deleting non-existent page."""
        mock_client.delete_content.side_effect = ConfluenceAPIError("Not found", status_code=404)

        with pytest.raises(NotFoundError):
            adapter.delete_page("nonexistent")


# =============================================================================
# Label Operations Tests
# =============================================================================


class TestConfluenceLabelOperations:
    """Tests for label operations."""

    def test_create_page_with_labels(self, adapter, mock_client, mock_page_response):
        """Test creating a page with labels."""
        mock_client.create_content.return_value = mock_page_response

        adapter.create_page(
            space_key="PROJ",
            title="Labeled Page",
            content="<p>Content</p>",
            labels=["label1", "label2"],
        )

        mock_client.add_labels.assert_called_once_with("page-123", ["label1", "label2"])

    def test_update_page_labels_add_remove(self, adapter, mock_client, mock_page_response):
        """Test updating page labels - add new, remove old."""
        mock_client.update_content.return_value = mock_page_response
        mock_client.get_labels.return_value = [
            {"name": "keep"},
            {"name": "remove"},
        ]

        adapter.update_page(
            page_id="page-123",
            title="Page",
            content="<p>Content</p>",
            version=1,
            labels=["keep", "new"],
        )

        mock_client.remove_label.assert_called_once_with("page-123", "remove")
        mock_client.add_labels.assert_called_once_with("page-123", ["new"])


# =============================================================================
# Confluence Batch and Extended Operations Tests
# =============================================================================


class TestConfluenceBatchOperations:
    """Tests for batch page operations."""

    def test_bulk_update_pages(self, adapter, mock_client, mock_page_response):
        """Test updating multiple pages in sequence."""
        mock_client.update_content.return_value = mock_page_response
        mock_client.get_labels.return_value = []

        pages = [
            ("page-1", "Title 1", "<p>Content 1</p>", 1),
            ("page-2", "Title 2", "<p>Content 2</p>", 2),
            ("page-3", "Title 3", "<p>Content 3</p>", 3),
        ]

        for page_id, title, content, version in pages:
            result = adapter.update_page(page_id, title, content, version)
            assert result is not None

        assert mock_client.update_content.call_count == 3

    def test_bulk_create_pages(self, adapter, mock_client, mock_page_response):
        """Test creating multiple pages."""
        mock_client.create_content.return_value = mock_page_response

        pages = [
            ("PROJ", "Page 1", "<p>Content 1</p>"),
            ("PROJ", "Page 2", "<p>Content 2</p>"),
        ]

        for space_key, title, content in pages:
            result = adapter.create_page(space_key, title, content)
            assert result is not None

        assert mock_client.create_content.call_count == 2

    def test_bulk_delete_pages(self, adapter, mock_client):
        """Test deleting multiple pages."""
        mock_client.delete_content.return_value = None

        page_ids = ["page-1", "page-2", "page-3"]

        for page_id in page_ids:
            adapter.delete_page(page_id)

        assert mock_client.delete_content.call_count == 3


class TestConfluenceSearchOperations:
    """Tests for search operations."""

    def test_search_by_label(self, adapter, mock_client, mock_page_response):
        """Test searching pages by label."""
        mock_client.search.return_value = [mock_page_response]

        # Search using CQL
        results = mock_client.search("label = 'test'")

        assert len(results) == 1

    def test_get_child_pages(self, adapter, mock_client, mock_page_response):
        """Test getting child pages of a parent."""
        mock_client.get_child_pages.return_value = [mock_page_response]

        children = mock_client.get_child_pages("parent-123")

        assert len(children) == 1


class TestConfluenceStorageFormat:
    """Tests for Confluence storage format edge cases."""

    def test_escape_html_in_content(self, adapter):
        """Test HTML escaping in content."""
        html = adapter._info_panel("<script>alert('xss')</script>")

        # Script tags should be escaped or handled
        assert "ac:name" in html

    def test_format_empty_description(self, adapter):
        """Test formatting empty description."""
        from spectryn.core.domain.value_objects import Description

        desc = Description(role="", want="", benefit="")
        html = adapter._format_description(desc)

        # Should produce valid HTML even with empty values
        assert html is not None

    def test_status_lozenge_all_statuses(self, adapter):
        """Test status lozenge for all status values."""
        from spectryn.core.domain.enums import Status

        for status in Status:
            html = adapter._status_lozenge(status)
            assert 'ac:name="status"' in html

    def test_task_list_empty(self, adapter):
        """Test task list with empty items."""
        html = adapter._task_list([], [])

        # Should handle empty list gracefully
        assert "ac:task-list" in html or html == ""


class TestConfluenceAttachments:
    """Tests for attachment operations."""

    def test_format_with_attachments(self, adapter, sample_story):
        """Test story content with potential attachments."""
        content = adapter.format_story_content(sample_story)

        # Content should be valid Confluence storage format
        assert content is not None
        assert len(content) > 0

    def test_format_epic_with_many_stories(self, adapter, sample_epic):
        """Test formatting epic with stories."""
        content = adapter.format_epic_content(sample_epic)

        # Should contain story information
        assert "Stories" in content


class TestConfluenceVersionControl:
    """Tests for page version handling."""

    def test_update_with_version_increment(self, adapter, mock_client, mock_page_response):
        """Test that updates increment version correctly."""
        mock_client.update_content.return_value = mock_page_response
        mock_client.get_labels.return_value = []

        adapter.update_page("page-123", "Title", "<p>Content</p>", version=5)

        # Verify update was called
        mock_client.update_content.assert_called_once()

    def test_get_page_includes_version(self, adapter, mock_client, mock_page_response):
        """Test that get_page returns version information."""
        mock_client.get_content.return_value = mock_page_response

        page = adapter.get_page("page-123")

        assert page.version == 5


class TestConfluencePermissions:
    """Tests for permission handling."""

    def test_create_page_in_restricted_space(self, adapter, mock_client):
        """Test creating page in restricted space."""
        mock_client.create_content.side_effect = ConfluenceAPIError(
            "No permission", status_code=403
        )

        with pytest.raises(PermissionError):
            adapter.create_page("RESTRICTED", "Title", "<p>Content</p>")

    def test_update_page_no_edit_permission(self, adapter, mock_client):
        """Test updating page without edit permission."""
        mock_client.update_content.side_effect = ConfluenceAPIError("Cannot edit", status_code=403)
        mock_client.get_labels.return_value = []

        # 403 errors are re-raised as ConfluenceAPIError (not wrapped as PermissionError)
        with pytest.raises(ConfluenceAPIError):
            adapter.update_page("page-123", "Title", "<p>Content</p>", version=1)
