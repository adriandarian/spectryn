"""
Tests for GitHub Issues Adapter.
"""

from unittest.mock import MagicMock, patch

import pytest

from spectra.adapters.github.adapter import GitHubAdapter
from spectra.adapters.github.client import GitHubApiClient, GitHubRateLimiter
from spectra.adapters.github.plugin import GitHubTrackerPlugin, create_plugin
from spectra.core.ports.issue_tracker import (
    AuthenticationError,
    NotFoundError,
)


# =============================================================================
# Rate Limiter Tests
# =============================================================================


class TestGitHubRateLimiter:
    """Tests for GitHubRateLimiter."""

    def test_acquire_with_available_tokens(self):
        """Should immediately acquire when tokens available."""
        limiter = GitHubRateLimiter(requests_per_second=10.0, burst_size=5)

        # Should acquire immediately for first few requests
        assert limiter.acquire(timeout=0.1) is True
        assert limiter.acquire(timeout=0.1) is True
        assert limiter.acquire(timeout=0.1) is True

    def test_stats_tracking(self):
        """Should track request statistics."""
        limiter = GitHubRateLimiter(requests_per_second=10.0, burst_size=5)

        limiter.acquire()
        limiter.acquire()

        stats = limiter.stats
        assert stats["total_requests"] == 2
        assert "available_tokens" in stats
        assert "requests_per_second" in stats

    def test_update_from_response(self):
        """Should update state from GitHub response headers."""
        limiter = GitHubRateLimiter()

        # Mock response with rate limit headers
        mock_response = MagicMock()
        mock_response.headers = {
            "X-RateLimit-Remaining": "4999",
            "X-RateLimit-Reset": "1234567890",
        }
        mock_response.status_code = 200

        limiter.update_from_response(mock_response)

        stats = limiter.stats
        assert stats["github_remaining"] == 4999
        assert stats["github_reset"] == 1234567890.0

    def test_reset(self):
        """Should reset limiter state."""
        limiter = GitHubRateLimiter(burst_size=5)

        limiter.acquire()
        limiter.acquire()
        limiter.reset()

        stats = limiter.stats
        assert stats["total_requests"] == 0
        assert stats["total_wait_time"] == 0.0


# =============================================================================
# API Client Tests
# =============================================================================


class TestGitHubApiClient:
    """Tests for GitHubApiClient."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock session for testing."""
        with patch("spectra.adapters.github.client.requests.Session") as mock:
            session = MagicMock()
            mock.return_value = session
            yield session

    @pytest.fixture
    def client(self, mock_session):
        """Create a test client with mocked session."""
        return GitHubApiClient(
            token="test-token",
            owner="test-owner",
            repo="test-repo",
            dry_run=False,
        )

    def test_initialization(self, mock_session):
        """Should initialize with correct configuration."""
        client = GitHubApiClient(
            token="my-token",
            owner="my-org",
            repo="my-repo",
        )

        assert client.owner == "my-org"
        assert client.repo == "my-repo"
        assert client.dry_run is True  # Default
        assert "Bearer my-token" in str(mock_session.headers.update.call_args)

    def test_repo_endpoint(self, client):
        """Should generate correct repo-scoped endpoints."""
        assert client.repo_endpoint() == "repos/test-owner/test-repo"
        assert client.repo_endpoint("issues") == "repos/test-owner/test-repo/issues"
        assert client.repo_endpoint("issues/123") == "repos/test-owner/test-repo/issues/123"

    def test_get_issue(self, client, mock_session):
        """Should fetch issue data."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = '{"number": 123, "title": "Test Issue"}'
        mock_response.json.return_value = {"number": 123, "title": "Test Issue"}
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        result = client.get_issue(123)

        assert result["number"] == 123
        assert result["title"] == "Test Issue"

    def test_create_issue(self, client, mock_session):
        """Should create a new issue."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = '{"number": 456, "title": "New Issue"}'
        mock_response.json.return_value = {"number": 456, "title": "New Issue"}
        mock_response.status_code = 201
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        result = client.create_issue(
            title="New Issue",
            body="Issue body",
            labels=["bug"],
        )

        assert result["number"] == 456

    def test_dry_run_blocks_writes(self, mock_session):
        """Should block write operations in dry_run mode."""
        client = GitHubApiClient(
            token="test",
            owner="test",
            repo="test",
            dry_run=True,
        )

        result = client.create_issue(title="Test")

        assert result == {}
        # Should not have made any actual POST request
        for call in mock_session.request.call_args_list:
            assert call[0][0] != "POST" or "search" in str(call)

    def test_authentication_error(self, client, mock_session):
        """Should raise AuthenticationError on 401."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        with pytest.raises(AuthenticationError):
            client.get("user")

    def test_not_found_error(self, client, mock_session):
        """Should raise NotFoundError on 404."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        with pytest.raises(NotFoundError):
            client.get_issue(99999)

    def test_list_issues(self, client, mock_session):
        """Should list issues with filters."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = '[{"number": 1}, {"number": 2}]'
        mock_response.json.return_value = [{"number": 1}, {"number": 2}]
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        result = client.list_issues(state="open", labels=["bug"])

        assert len(result) == 2
        assert result[0]["number"] == 1


# =============================================================================
# Adapter Tests
# =============================================================================


class TestGitHubAdapter:
    """Tests for GitHubAdapter."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock API client."""
        with patch("spectra.adapters.github.adapter.GitHubApiClient") as mock:
            client = MagicMock()
            client.list_labels.return_value = []
            mock.return_value = client
            yield client

    @pytest.fixture
    def adapter(self, mock_client):
        """Create a test adapter with mocked client."""
        return GitHubAdapter(
            token="test-token",
            owner="test-owner",
            repo="test-repo",
            dry_run=True,
        )

    def test_name_property(self, adapter):
        """Should return 'GitHub' as tracker name."""
        assert adapter.name == "GitHub"

    def test_get_issue(self, adapter, mock_client):
        """Should fetch and parse issue data."""
        mock_client.get_issue.return_value = {
            "number": 123,
            "title": "Test Story",
            "body": "Story description",
            "state": "open",
            "labels": [{"name": "story"}],
            "assignee": {"login": "testuser"},
        }

        result = adapter.get_issue("#123")

        assert result.key == "#123"
        assert result.summary == "Test Story"
        assert result.status == "open"
        assert result.issue_type == "Story"
        assert result.assignee == "testuser"

    def test_parse_issue_key_formats(self, adapter, mock_client):
        """Should parse various issue key formats."""
        mock_client.get_issue.return_value = {
            "number": 456,
            "title": "Test",
            "state": "open",
            "labels": [],
        }

        # Test different formats
        for key in ["456", "#456", "owner/repo#456"]:
            result = adapter.get_issue(key)
            assert result.key == "#456"
            mock_client.get_issue.assert_called_with(456)

    def test_get_epic_children_with_milestone(self, adapter, mock_client):
        """Should fetch children of a milestone epic."""
        mock_client.list_issues.return_value = [
            {"number": 1, "title": "Story 1", "state": "open", "labels": [{"name": "story"}]},
            {"number": 2, "title": "Story 2", "state": "closed", "labels": [{"name": "story"}]},
        ]

        result = adapter.get_epic_children("1")

        assert len(result) == 2
        assert result[0].summary == "Story 1"
        mock_client.list_issues.assert_called_once()

    def test_get_issue_status_with_label(self, adapter, mock_client):
        """Should return status from labels."""
        mock_client.get_issue.return_value = {
            "number": 123,
            "state": "open",
            "labels": [{"name": "status:in-progress"}, {"name": "story"}],
        }

        status = adapter.get_issue_status("#123")

        assert status == "in progress"

    def test_get_issue_status_fallback(self, adapter, mock_client):
        """Should fall back to state when no status label."""
        mock_client.get_issue.return_value = {
            "number": 123,
            "state": "closed",
            "labels": [{"name": "story"}],
        }

        status = adapter.get_issue_status("#123")

        assert status == "closed"

    def test_update_description_dry_run(self, adapter, mock_client):
        """Should not update in dry_run mode."""
        result = adapter.update_issue_description("#123", "New description")

        assert result is True
        mock_client.update_issue.assert_not_called()

    def test_create_subtask_as_task_list(self, adapter, mock_client):
        """Should create subtask as task list item by default."""
        result = adapter.create_subtask(
            parent_key="#123",
            summary="New subtask",
            description="Subtask description",
            project_key="test",
        )

        # In dry_run mode, returns None
        assert result is None

    def test_transition_issue_dry_run(self, adapter, mock_client):
        """Should not transition in dry_run mode."""
        result = adapter.transition_issue("#123", "in progress")

        assert result is True
        mock_client.update_issue.assert_not_called()

    def test_add_comment_dry_run(self, adapter, mock_client):
        """Should not add comment in dry_run mode."""
        result = adapter.add_comment("#123", "Test comment")

        assert result is True
        mock_client.add_issue_comment.assert_not_called()

    def test_format_description(self, adapter):
        """Should return markdown as-is."""
        markdown = "# Title\n\nSome **bold** text."

        result = adapter.format_description(markdown)

        assert result == markdown

    def test_get_available_transitions(self, adapter):
        """Should return configured status labels as transitions."""
        result = adapter.get_available_transitions("#123")

        assert len(result) >= 3
        statuses = [t["name"] for t in result]
        assert "open" in statuses
        assert "in progress" in statuses
        assert "done" in statuses

    def test_parse_task_list(self, adapter):
        """Should parse task list items from body."""
        body = """
## Description

Some description here.

## Tasks
- [ ] **Task 1**
  Description of task 1
- [x] **Task 2**
  Description of task 2
- [ ] **Task 3**
"""

        subtasks = adapter._parse_task_list(body)

        assert len(subtasks) == 3
        assert subtasks[0].summary == "Task 1"
        assert subtasks[0].status == "open"
        assert subtasks[1].summary == "Task 2"
        assert subtasks[1].status == "done"

    def test_story_points_from_label(self, adapter, mock_client):
        """Should extract story points from labels."""
        mock_client.get_issue.return_value = {
            "number": 123,
            "title": "Test",
            "state": "open",
            "labels": [{"name": "story"}, {"name": "points:5"}],
        }

        result = adapter.get_issue("#123")

        assert result.story_points == 5.0


# =============================================================================
# Plugin Tests
# =============================================================================


class TestGitHubTrackerPlugin:
    """Tests for GitHubTrackerPlugin."""

    def test_metadata(self):
        """Should have correct metadata."""
        plugin = GitHubTrackerPlugin()

        assert plugin.metadata.name == "github-issues"
        assert plugin.metadata.version == "1.0.0"
        assert "GitHub" in plugin.metadata.description

    def test_validate_config_missing_token(self):
        """Should report missing token."""
        plugin = GitHubTrackerPlugin(
            {
                "owner": "test",
                "repo": "test",
            }
        )

        with patch.dict("os.environ", {}, clear=True):
            errors = plugin.validate_config()

        assert any("token" in e.lower() for e in errors)

    def test_validate_config_from_env(self):
        """Should accept config from environment variables."""
        plugin = GitHubTrackerPlugin()

        with patch.dict(
            "os.environ",
            {
                "GITHUB_TOKEN": "test-token",
                "GITHUB_OWNER": "test-owner",
                "GITHUB_REPO": "test-repo",
            },
        ):
            errors = plugin.validate_config()

        assert len(errors) == 0

    def test_initialize_creates_adapter(self):
        """Should create adapter on initialize."""
        plugin = GitHubTrackerPlugin(
            {
                "token": "test-token",
                "owner": "test-owner",
                "repo": "test-repo",
                "dry_run": True,
            }
        )

        with patch("spectra.adapters.github.plugin.GitHubAdapter") as MockAdapter:
            mock_adapter = MagicMock()
            MockAdapter.return_value = mock_adapter

            plugin.initialize()

            assert plugin.is_initialized
            MockAdapter.assert_called_once()

    def test_get_tracker_before_initialize(self):
        """Should raise error if not initialized."""
        plugin = GitHubTrackerPlugin()

        with pytest.raises(RuntimeError):
            plugin.get_tracker()

    def test_shutdown_cleans_up(self):
        """Should cleanup on shutdown."""
        plugin = GitHubTrackerPlugin(
            {
                "token": "test",
                "owner": "test",
                "repo": "test",
            }
        )

        with patch("spectra.adapters.github.plugin.GitHubAdapter") as MockAdapter:
            mock_adapter = MagicMock()
            MockAdapter.return_value = mock_adapter

            plugin.initialize()
            plugin.shutdown()

            assert not plugin.is_initialized
            mock_adapter._client.close.assert_called_once()

    def test_create_plugin_factory(self):
        """Should create plugin via factory function."""
        config = {
            "token": "test",
            "owner": "test",
            "repo": "test",
        }

        plugin = create_plugin(config)

        assert isinstance(plugin, GitHubTrackerPlugin)
        assert plugin.config == config


# =============================================================================
# Integration-style Tests
# =============================================================================


class TestGitHubAdapterIntegration:
    """Integration-style tests for GitHubAdapter workflows."""

    @pytest.fixture
    def live_adapter(self):
        """Create adapter with mocked client for workflow tests."""
        with patch("spectra.adapters.github.adapter.GitHubApiClient") as MockClient:
            client = MagicMock()
            client.list_labels.return_value = []
            client.is_connected = True
            MockClient.return_value = client

            adapter = GitHubAdapter(
                token="test",
                owner="test",
                repo="test",
                dry_run=False,
            )
            adapter._client = client
            yield adapter, client

    def test_create_story_workflow(self, live_adapter):
        """Should create a story linked to milestone."""
        adapter, client = live_adapter
        client.create_issue.return_value = {"number": 42}

        result = adapter.create_story(
            title="New feature",
            description="Feature description",
            epic_key="milestone:1",
            story_points=3,
            assignee="developer",
        )

        assert result == "#42"
        client.create_issue.assert_called_once()
        call_kwargs = client.create_issue.call_args[1]
        assert call_kwargs["title"] == "New feature"
        assert "story" in call_kwargs["labels"]
        assert "points:3" in call_kwargs["labels"]
        assert call_kwargs["milestone"] == 1
        assert call_kwargs["assignees"] == ["developer"]

    def test_transition_to_done_closes_issue(self, live_adapter):
        """Should close issue when transitioning to done."""
        adapter, client = live_adapter
        client.get_issue.return_value = {
            "number": 123,
            "state": "open",
            "labels": [{"name": "story"}, {"name": "status:in-progress"}],
        }

        adapter.transition_issue("#123", "done")

        client.update_issue.assert_called_once()
        call_kwargs = client.update_issue.call_args[1]
        assert call_kwargs["state"] == "closed"
        assert "status:done" in call_kwargs["labels"]
        assert "status:in-progress" not in call_kwargs["labels"]

    def test_create_subtask_as_separate_issue(self, live_adapter):
        """Should create subtask as separate issue when configured."""
        adapter, client = live_adapter
        adapter.subtasks_as_issues = True
        client.create_issue.return_value = {"number": 99}

        result = adapter.create_subtask(
            parent_key="#123",
            summary="Subtask title",
            description="Subtask body",
            project_key="test",
            story_points=1,
        )

        assert result == "#99"
        client.create_issue.assert_called_once()
        call_kwargs = client.create_issue.call_args[1]
        assert "subtask" in call_kwargs["labels"]
        assert "points:1" in call_kwargs["labels"]
        assert "Parent: #123" in call_kwargs["body"]

    def test_update_subtask_with_all_fields(self, live_adapter):
        """Should update all subtask fields."""
        adapter, client = live_adapter
        client.get_issue.return_value = {
            "number": 99,
            "labels": [{"name": "subtask"}, {"name": "points:2"}],
        }

        adapter.update_subtask(
            issue_key="#99",
            description="Updated description",
            story_points=3,
            assignee="newdev",
        )

        client.update_issue.assert_called_once()
        call_kwargs = client.update_issue.call_args[1]
        assert call_kwargs["body"] == "Updated description"
        assert call_kwargs["assignees"] == ["newdev"]
        assert "points:3" in call_kwargs["labels"]
        assert "points:2" not in call_kwargs["labels"]


# =============================================================================
# Link Operations Tests
# =============================================================================


class TestGitHubAdapterLinks:
    """Tests for GitHub adapter link operations."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock API client."""
        with patch("spectra.adapters.github.adapter.GitHubApiClient") as mock:
            client = MagicMock()
            client.list_labels.return_value = []
            mock.return_value = client
            yield client

    @pytest.fixture
    def adapter(self, mock_client):
        """Create a test adapter."""
        return GitHubAdapter(
            token="test-token",
            owner="test-owner",
            repo="test-repo",
            dry_run=False,
        )

    def test_get_issue_links_empty_body(self, adapter, mock_client):
        """Should return empty list for issue without links."""
        mock_client.get_issue.return_value = {
            "number": 123,
            "body": "Just a regular description",
        }

        links = adapter.get_issue_links("#123")

        assert links == []

    def test_get_issue_links_blocks(self, adapter, mock_client):
        """Should parse Blocks links from body."""
        mock_client.get_issue.return_value = {
            "number": 123,
            "body": "Description\n\n**Blocks:** #456, #789",
        }

        links = adapter.get_issue_links("#123")

        assert len(links) == 2
        assert any(l.target_key == "#456" for l in links)
        assert any(l.target_key == "#789" for l in links)

    def test_get_issue_links_blocked_by(self, adapter, mock_client):
        """Should parse Blocked by links from body."""
        mock_client.get_issue.return_value = {
            "number": 123,
            "body": "Description\n\n**Blocked by:** #100",
        }

        links = adapter.get_issue_links("#123")

        assert len(links) == 1
        assert links[0].target_key == "#100"
        assert links[0].link_type.value == "is blocked by"

    def test_get_issue_links_multiple_types(self, adapter, mock_client):
        """Should parse multiple link types from body."""
        mock_client.get_issue.return_value = {
            "number": 123,
            "body": """Description

**Blocks:** #456
**Related to:** #789
**Depends on:** #111
""",
        }

        links = adapter.get_issue_links("#123")

        assert len(links) == 3

    def test_create_link_adds_to_body(self, adapter, mock_client):
        """Should add link reference to issue body."""
        from spectra.core.ports.issue_tracker import LinkType

        mock_client.get_issue.return_value = {
            "number": 123,
            "body": "Original description",
        }

        result = adapter.create_link("#123", "#456", LinkType.BLOCKS)

        assert result is True
        mock_client.update_issue.assert_called_once()
        call_args = mock_client.update_issue.call_args
        assert "#456" in call_args[1]["body"]
        assert "**Blocks:**" in call_args[1]["body"]

    def test_create_link_appends_to_existing(self, adapter, mock_client):
        """Should append to existing link section."""
        from spectra.core.ports.issue_tracker import LinkType

        mock_client.get_issue.return_value = {
            "number": 123,
            "body": "Description\n\n**Blocks:** #456",
        }

        result = adapter.create_link("#123", "#789", LinkType.BLOCKS)

        assert result is True
        call_args = mock_client.update_issue.call_args
        assert "#456" in call_args[1]["body"]
        assert "#789" in call_args[1]["body"]

    def test_create_link_no_duplicate(self, adapter, mock_client):
        """Should not duplicate existing link."""
        from spectra.core.ports.issue_tracker import LinkType

        mock_client.get_issue.return_value = {
            "number": 123,
            "body": "Description\n\n**Blocks:** #456",
        }

        result = adapter.create_link("#123", "#456", LinkType.BLOCKS)

        # Should succeed but not call update since link already exists
        assert result is True
        mock_client.update_issue.assert_not_called()

    def test_create_link_dry_run(self, mock_client):
        """Should not modify issue in dry run mode."""
        from spectra.core.ports.issue_tracker import LinkType

        adapter = GitHubAdapter(
            token="test-token",
            owner="test-owner",
            repo="test-repo",
            dry_run=True,
        )

        result = adapter.create_link("#123", "#456", LinkType.BLOCKS)

        assert result is True
        mock_client.update_issue.assert_not_called()

    def test_delete_link_removes_from_body(self, adapter, mock_client):
        """Should remove link reference from body."""
        from spectra.core.ports.issue_tracker import LinkType

        mock_client.get_issue.return_value = {
            "number": 123,
            "body": "Description\n\n**Blocks:** #456, #789",
        }

        result = adapter.delete_link("#123", "#456", LinkType.BLOCKS)

        assert result is True
        call_args = mock_client.update_issue.call_args
        assert "#456" not in call_args[1]["body"]
        assert "#789" in call_args[1]["body"]

    def test_get_link_types(self, adapter):
        """Should return supported link types."""
        link_types = adapter.get_link_types()

        assert len(link_types) > 0
        assert any(lt["name"] == "Blocks" for lt in link_types)
        assert any(lt["name"] == "Relates" for lt in link_types)

    def test_sync_links_creates_missing(self, adapter, mock_client):
        """Should create links that don't exist."""
        mock_client.get_issue.return_value = {
            "number": 123,
            "body": "Description",
        }

        desired_links = [("blocks", "#456"), ("relates to", "#789")]
        result = adapter.sync_links("#123", desired_links)

        assert result["created"] == 2
        assert result["unchanged"] == 0

    def test_sync_links_preserves_existing(self, adapter, mock_client):
        """Should not recreate existing links."""
        mock_client.get_issue.return_value = {
            "number": 123,
            "body": "Description\n\n**Blocks:** #456",
        }

        desired_links = [("blocks", "#456"), ("relates to", "#789")]
        result = adapter.sync_links("#123", desired_links)

        assert result["unchanged"] == 1
        assert result["created"] == 1
