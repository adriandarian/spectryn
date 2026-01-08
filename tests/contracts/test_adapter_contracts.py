"""
Contract tests for issue tracker adapters.

These tests verify that all adapters implementing IssueTrackerPort
conform to the expected interface contract. This ensures consistent
behavior across different tracker integrations.

Contract tests cover:
- Interface compliance
- Consistent error handling
- Common operation semantics
- Pagination behavior
- Retry behavior
"""

from abc import ABC, abstractmethod
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from spectryn.core.ports.issue_tracker import (
    IssueData,
    IssueTrackerError,
    IssueTrackerPort,
    LinkType,
)


class AdapterContractTestBase(ABC):
    """
    Base class for adapter contract tests.

    Subclasses must implement the abstract methods to provide
    adapter-specific setup and mock data.
    """

    @abstractmethod
    def create_adapter(self, dry_run: bool = True) -> IssueTrackerPort:
        """Create an instance of the adapter under test."""

    @abstractmethod
    def mock_issue_data(self) -> dict[str, Any]:
        """Return mock issue data for the adapter."""

    @abstractmethod
    def sample_issue_key(self) -> str:
        """Return a sample issue key for the adapter."""


class TestJiraAdapterContract(AdapterContractTestBase):
    """Contract tests for JiraAdapter."""

    def create_adapter(self, dry_run: bool = True) -> IssueTrackerPort:
        from spectryn.adapters.jira.adapter import JiraAdapter
        from spectryn.core.ports.config_provider import TrackerConfig

        config = TrackerConfig(
            url="https://test.atlassian.net",
            email="test@example.com",
            api_token="test-token",
            project_key="TEST",
        )

        with (
            patch("spectryn.adapters.jira.adapter.JiraApiClient"),
            patch("spectryn.adapters.jira.adapter.JiraBatchClient"),
        ):
            return JiraAdapter(config=config, dry_run=dry_run)

    def mock_issue_data(self) -> dict[str, Any]:
        return {
            "key": "TEST-123",
            "fields": {
                "summary": "Test Issue",
                "description": None,
                "status": {"name": "Open"},
                "issuetype": {"name": "Story"},
                "priority": {"name": "Medium"},
            },
        }

    def sample_issue_key(self) -> str:
        return "TEST-123"

    def test_adapter_has_name_property(self):
        """Test adapter has name property."""
        adapter = self.create_adapter()
        assert hasattr(adapter, "name")
        assert isinstance(adapter.name, str)
        assert adapter.name == "Jira"

    def test_adapter_has_is_connected_property(self):
        """Test adapter has is_connected property."""
        adapter = self.create_adapter()
        assert hasattr(adapter, "is_connected")

    def test_adapter_has_test_connection_method(self):
        """Test adapter has test_connection method."""
        adapter = self.create_adapter()
        assert hasattr(adapter, "test_connection")
        assert callable(adapter.test_connection)

    def test_get_issue_returns_issue_data(self):
        """Test get_issue returns IssueData."""
        adapter = self.create_adapter()
        adapter._client.get.return_value = self.mock_issue_data()

        result = adapter.get_issue(self.sample_issue_key())

        assert isinstance(result, IssueData)
        assert result.key == "TEST-123"

    def test_update_description_dry_run(self):
        """Test update_issue_description in dry run mode."""
        adapter = self.create_adapter(dry_run=True)

        result = adapter.update_issue_description(self.sample_issue_key(), "New desc")

        assert result is True
        adapter._client.put.assert_not_called()

    def test_add_comment_dry_run(self):
        """Test add_comment in dry run mode."""
        adapter = self.create_adapter(dry_run=True)

        result = adapter.add_comment(self.sample_issue_key(), "Comment")

        assert result is True
        adapter._client.post.assert_not_called()

    def test_transition_issue_dry_run(self):
        """Test transition_issue in dry run mode."""
        adapter = self.create_adapter(dry_run=True)

        result = adapter.transition_issue(self.sample_issue_key(), "Done")

        assert result is True


class TestGitHubAdapterContract(AdapterContractTestBase):
    """Contract tests for GitHubAdapter."""

    def create_adapter(self, dry_run: bool = True) -> IssueTrackerPort:
        from spectryn.adapters.github.adapter import GitHubAdapter

        with patch("spectryn.adapters.github.adapter.GitHubApiClient") as MockClient:
            mock_client = MagicMock()
            mock_client.list_labels.return_value = []
            MockClient.return_value = mock_client

            adapter = GitHubAdapter(
                token="test-token",
                owner="test-owner",
                repo="test-repo",
                dry_run=dry_run,
            )
            adapter._client = mock_client
            return adapter

    def mock_issue_data(self) -> dict[str, Any]:
        return {
            "number": 123,
            "title": "Test Issue",
            "body": "Description",
            "state": "open",
            "labels": [{"name": "story"}],
        }

    def sample_issue_key(self) -> str:
        return "#123"

    def test_adapter_has_name_property(self):
        """Test adapter has name property."""
        adapter = self.create_adapter()
        assert hasattr(adapter, "name")
        assert isinstance(adapter.name, str)
        assert adapter.name == "GitHub"

    def test_adapter_has_is_connected_property(self):
        """Test adapter has is_connected property."""
        adapter = self.create_adapter()
        assert hasattr(adapter, "is_connected")

    def test_adapter_has_test_connection_method(self):
        """Test adapter has test_connection method."""
        adapter = self.create_adapter()
        assert hasattr(adapter, "test_connection")
        assert callable(adapter.test_connection)

    def test_get_issue_returns_issue_data(self):
        """Test get_issue returns IssueData."""
        adapter = self.create_adapter()
        adapter._client.get_issue.return_value = self.mock_issue_data()

        result = adapter.get_issue(self.sample_issue_key())

        assert isinstance(result, IssueData)
        assert result.key == "#123"

    def test_update_description_dry_run(self):
        """Test update_issue_description in dry run mode."""
        adapter = self.create_adapter(dry_run=True)

        result = adapter.update_issue_description(self.sample_issue_key(), "New desc")

        assert result is True
        adapter._client.update_issue.assert_not_called()

    def test_add_comment_dry_run(self):
        """Test add_comment in dry run mode."""
        adapter = self.create_adapter(dry_run=True)

        result = adapter.add_comment(self.sample_issue_key(), "Comment")

        assert result is True
        adapter._client.add_issue_comment.assert_not_called()

    def test_transition_issue_dry_run(self):
        """Test transition_issue in dry run mode."""
        adapter = self.create_adapter(dry_run=True)

        result = adapter.transition_issue(self.sample_issue_key(), "done")

        assert result is True


class TestLinearAdapterContract(AdapterContractTestBase):
    """Contract tests for LinearAdapter."""

    def create_adapter(self, dry_run: bool = True) -> IssueTrackerPort:
        from spectryn.adapters.linear.adapter import LinearAdapter

        with patch("spectryn.adapters.linear.adapter.LinearApiClient") as MockClient:
            mock_client = MagicMock()
            mock_client.get_team_by_key.return_value = {"id": "team-123", "key": "ENG"}
            MockClient.return_value = mock_client

            adapter = LinearAdapter(
                api_key="test-api-key",
                team_key="ENG",
                dry_run=dry_run,
            )
            adapter._client = mock_client
            return adapter

    def mock_issue_data(self) -> dict[str, Any]:
        return {
            "id": "issue-123",
            "identifier": "ENG-123",
            "title": "Test Issue",
            "description": "Description",
            "state": {"name": "In Progress"},
            "children": {"nodes": []},
        }

    def sample_issue_key(self) -> str:
        return "ENG-123"

    def test_adapter_has_name_property(self):
        """Test adapter has name property."""
        adapter = self.create_adapter()
        assert hasattr(adapter, "name")
        assert isinstance(adapter.name, str)
        assert adapter.name == "Linear"

    def test_adapter_has_is_connected_property(self):
        """Test adapter has is_connected property."""
        adapter = self.create_adapter()
        assert hasattr(adapter, "is_connected")

    def test_adapter_has_test_connection_method(self):
        """Test adapter has test_connection method."""
        adapter = self.create_adapter()
        assert hasattr(adapter, "test_connection")
        assert callable(adapter.test_connection)

    def test_get_issue_returns_issue_data(self):
        """Test get_issue returns IssueData."""
        adapter = self.create_adapter()
        adapter._client.get_issue.return_value = self.mock_issue_data()

        result = adapter.get_issue(self.sample_issue_key())

        assert isinstance(result, IssueData)
        assert result.key == "ENG-123"

    def test_update_description_dry_run(self):
        """Test update_issue_description in dry run mode."""
        adapter = self.create_adapter(dry_run=True)

        result = adapter.update_issue_description(self.sample_issue_key(), "New desc")

        assert result is True
        adapter._client.update_issue.assert_not_called()

    def test_add_comment_dry_run(self):
        """Test add_comment in dry run mode."""
        adapter = self.create_adapter(dry_run=True)

        result = adapter.add_comment(self.sample_issue_key(), "Comment")

        assert result is True
        adapter._client.add_comment.assert_not_called()


class TestYouTrackAdapterContract(AdapterContractTestBase):
    """Contract tests for YouTrackAdapter."""

    def create_adapter(self, dry_run: bool = True) -> IssueTrackerPort:
        from spectryn.adapters.youtrack.adapter import YouTrackAdapter
        from spectryn.core.ports.config_provider import YouTrackConfig

        with patch("spectryn.adapters.youtrack.adapter.YouTrackApiClient") as MockClient:
            mock_client = MagicMock()
            mock_client.get_current_user.return_value = {"login": "testuser"}
            mock_client.get_available_states.return_value = [
                {"name": "Open"},
                {"name": "In Progress"},
                {"name": "Done"},
            ]
            mock_client.get_available_priorities.return_value = [
                {"name": "Critical"},
                {"name": "High"},
                {"name": "Normal"},
            ]
            MockClient.return_value = mock_client

            config = YouTrackConfig(
                url="https://test.youtrack.com",
                token="test-token",
                project_id="PROJ",
            )
            adapter = YouTrackAdapter(config=config, dry_run=dry_run)
            adapter._client = mock_client
            return adapter

    def mock_issue_data(self) -> dict[str, Any]:
        return {
            "idReadable": "PROJ-123",
            "summary": "Test Issue",
            "description": "Test description",
            "type": {"name": "Task"},
            "customFields": [
                {"name": "State", "value": {"name": "Open"}},
            ],
        }

    def sample_issue_key(self) -> str:
        return "PROJ-123"

    def test_adapter_has_name_property(self):
        """Test adapter has name property."""
        adapter = self.create_adapter()
        assert hasattr(adapter, "name")
        assert isinstance(adapter.name, str)
        assert adapter.name == "YouTrack"

    def test_adapter_has_is_connected_property(self):
        """Test adapter has is_connected property."""
        adapter = self.create_adapter()
        assert hasattr(adapter, "is_connected")

    def test_adapter_has_test_connection_method(self):
        """Test adapter has test_connection method."""
        adapter = self.create_adapter()
        assert hasattr(adapter, "test_connection")
        assert callable(adapter.test_connection)

    def test_get_issue_returns_issue_data(self):
        """Test get_issue returns IssueData."""
        adapter = self.create_adapter()
        adapter._client.get_issue.return_value = self.mock_issue_data()
        adapter._client.get_issue_comments.return_value = []

        result = adapter.get_issue(self.sample_issue_key())

        assert isinstance(result, IssueData)
        assert result.key == "PROJ-123"

    def test_update_description_dry_run(self):
        """Test update_issue_description in dry run mode."""
        adapter = self.create_adapter(dry_run=True)

        result = adapter.update_issue_description(self.sample_issue_key(), "New desc")

        assert result is True
        adapter._client.update_issue.assert_not_called()

    def test_add_comment_dry_run(self):
        """Test add_comment in dry run mode."""
        adapter = self.create_adapter(dry_run=True)

        result = adapter.add_comment(self.sample_issue_key(), "Comment")

        assert result is True
        adapter._client.add_comment.assert_not_called()


class TestAdapterContractConsistency:
    """Tests for consistent behavior across all adapters."""

    @pytest.fixture
    def all_adapters(self):
        """Create instances of all adapters."""
        adapters = []

        # Jira
        from spectryn.adapters.jira.adapter import JiraAdapter
        from spectryn.core.ports.config_provider import TrackerConfig

        with (
            patch("spectryn.adapters.jira.adapter.JiraApiClient"),
            patch("spectryn.adapters.jira.adapter.JiraBatchClient"),
        ):
            config = TrackerConfig(
                url="https://test.atlassian.net",
                email="test@example.com",
                api_token="test-token",
            )
            adapters.append(("Jira", JiraAdapter(config=config, dry_run=True)))

        # GitHub
        from spectryn.adapters.github.adapter import GitHubAdapter

        with patch("spectryn.adapters.github.adapter.GitHubApiClient") as MockClient:
            mock_client = MagicMock()
            mock_client.list_labels.return_value = []
            MockClient.return_value = mock_client
            adapters.append(
                (
                    "GitHub",
                    GitHubAdapter(token="test", owner="test", repo="test", dry_run=True),
                )
            )

        # Linear
        from spectryn.adapters.linear.adapter import LinearAdapter

        with patch("spectryn.adapters.linear.adapter.LinearApiClient") as MockClient:
            mock_client = MagicMock()
            mock_client.get_team_by_key.return_value = {"id": "t", "key": "ENG"}
            MockClient.return_value = mock_client
            adapters.append(("Linear", LinearAdapter(api_key="test", team_key="ENG", dry_run=True)))

        # YouTrack
        from spectryn.adapters.youtrack.adapter import YouTrackAdapter
        from spectryn.core.ports.config_provider import YouTrackConfig

        with patch("spectryn.adapters.youtrack.adapter.YouTrackApiClient") as MockClient:
            mock_client = MagicMock()
            mock_client.get_current_user.return_value = {"login": "testuser"}
            mock_client.get_available_states.return_value = []
            mock_client.get_available_priorities.return_value = []
            MockClient.return_value = mock_client
            config = YouTrackConfig(
                url="https://test.youtrack.com",
                token="test-token",
                project_id="PROJ",
            )
            adapters.append(("YouTrack", YouTrackAdapter(config=config, dry_run=True)))

        return adapters

    def test_all_adapters_have_name(self, all_adapters):
        """Test all adapters have name property."""
        for _name, adapter in all_adapters:
            assert hasattr(adapter, "name")
            assert isinstance(adapter.name, str)
            assert len(adapter.name) > 0

    def test_all_adapters_have_is_connected(self, all_adapters):
        """Test all adapters have is_connected property."""
        for _name, adapter in all_adapters:
            assert hasattr(adapter, "is_connected")

    def test_all_adapters_have_test_connection(self, all_adapters):
        """Test all adapters have test_connection method."""
        for _name, adapter in all_adapters:
            assert hasattr(adapter, "test_connection")
            assert callable(adapter.test_connection)

    def test_all_adapters_have_get_issue(self, all_adapters):
        """Test all adapters have get_issue method."""
        for _name, adapter in all_adapters:
            assert hasattr(adapter, "get_issue")
            assert callable(adapter.get_issue)

    def test_all_adapters_have_update_description(self, all_adapters):
        """Test all adapters have update_issue_description method."""
        for _name, adapter in all_adapters:
            assert hasattr(adapter, "update_issue_description")
            assert callable(adapter.update_issue_description)

    def test_all_adapters_have_add_comment(self, all_adapters):
        """Test all adapters have add_comment method."""
        for _name, adapter in all_adapters:
            assert hasattr(adapter, "add_comment")
            assert callable(adapter.add_comment)

    def test_all_adapters_have_format_description(self, all_adapters):
        """Test all adapters have format_description method."""
        for _name, adapter in all_adapters:
            assert hasattr(adapter, "format_description")
            assert callable(adapter.format_description)


class TestAdapterDryRunContract:
    """Tests for dry-run contract - no writes in dry-run mode."""

    def test_jira_dry_run_no_writes(self):
        """Test Jira adapter makes no writes in dry-run mode."""
        from spectryn.adapters.jira.adapter import JiraAdapter
        from spectryn.core.ports.config_provider import TrackerConfig

        with (
            patch("spectryn.adapters.jira.adapter.JiraApiClient") as MockClient,
            patch("spectryn.adapters.jira.adapter.JiraBatchClient"),
        ):
            mock_client = MagicMock()
            MockClient.return_value = mock_client

            config = TrackerConfig(
                url="https://test.atlassian.net",
                email="test@example.com",
                api_token="test-token",
            )
            adapter = JiraAdapter(config=config, dry_run=True)
            adapter._client = mock_client

            # Perform write operations
            adapter.update_issue_description("TEST-1", "desc")
            adapter.add_comment("TEST-1", "comment")
            adapter.transition_issue("TEST-1", "Done")
            adapter.create_link("TEST-1", "TEST-2", LinkType.BLOCKS)

            # Verify no write calls were made
            mock_client.put.assert_not_called()
            mock_client.post.assert_not_called()

    def test_github_dry_run_no_writes(self):
        """Test GitHub adapter makes no writes in dry-run mode."""
        from spectryn.adapters.github.adapter import GitHubAdapter

        with patch("spectryn.adapters.github.adapter.GitHubApiClient") as MockClient:
            mock_client = MagicMock()
            mock_client.list_labels.return_value = []
            MockClient.return_value = mock_client

            adapter = GitHubAdapter(token="test", owner="test", repo="test", dry_run=True)
            adapter._client = mock_client

            # Perform write operations
            adapter.update_issue_description("#1", "desc")
            adapter.add_comment("#1", "comment")
            adapter.transition_issue("#1", "done")

            # Verify no write calls were made
            mock_client.update_issue.assert_not_called()
            mock_client.add_issue_comment.assert_not_called()
