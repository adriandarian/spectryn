"""
Tests for ConfluenceClient.

Tests REST API client with mocked HTTP responses.
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from spectryn.adapters.confluence.client import (
    ConfluenceAPIError,
    ConfluenceClient,
    ConfluenceConfig,
)


@pytest.fixture
def config():
    """Create a ConfluenceConfig."""
    return ConfluenceConfig(
        base_url="https://test.atlassian.net/wiki",
        username="test@example.com",
        api_token="test_token_123",
        is_cloud=True,
    )


@pytest.fixture
def server_config():
    """Create a ConfluenceConfig for Server."""
    return ConfluenceConfig(
        base_url="https://confluence.company.com",
        username="testuser",
        api_token="password123",
        is_cloud=False,
    )


@pytest.fixture
def client(config):
    """Create a ConfluenceClient with mocked session."""
    c = ConfluenceClient(config)
    c._session = MagicMock(spec=requests.Session)
    return c


@pytest.fixture
def mock_page_response():
    """Mock Confluence page response."""
    return {
        "id": "123456",
        "type": "page",
        "title": "Test Page",
        "version": {"number": 1},
        "body": {"storage": {"value": "<p>Content</p>", "representation": "storage"}},
        "_links": {"webui": "/pages/123456"},
    }


class TestConfluenceConfig:
    """Tests for ConfluenceConfig."""

    def test_config_creation(self, config):
        """Test config is created correctly."""
        assert config.base_url == "https://test.atlassian.net/wiki"
        assert config.username == "test@example.com"
        assert config.is_cloud is True

    def test_server_config(self, server_config):
        """Test server config creation."""
        assert server_config.is_cloud is False


class TestConfluenceClientInit:
    """Tests for ConfluenceClient initialization."""

    def test_init_cloud(self, config):
        """Test Cloud API base path."""
        client = ConfluenceClient(config)
        assert "/wiki/rest/api" in client._api_base

    def test_init_server(self, server_config):
        """Test Server API base path."""
        client = ConfluenceClient(server_config)
        assert "/rest/api" in client._api_base
        assert "/wiki" not in client._api_base

    def test_init_cloud_without_wiki_path(self):
        """Test Cloud URL without /wiki is handled."""
        config = ConfluenceConfig(
            base_url="https://test.atlassian.net",
            username="test@example.com",
            api_token="token",
            is_cloud=True,
        )
        client = ConfluenceClient(config)
        assert "/wiki/rest/api" in client._api_base


class TestConfluenceClientSession:
    """Tests for session management."""

    def test_connect(self, config):
        """Test connect creates session."""
        client = ConfluenceClient(config)

        with patch("requests.Session") as MockSession:
            mock_session = MagicMock()
            MockSession.return_value = mock_session

            client.connect()

            assert client._session is not None
            MockSession.assert_called_once()

    def test_disconnect(self, client):
        """Test disconnect closes session."""
        mock_session = client._session

        client.disconnect()

        mock_session.close.assert_called_once()
        assert client._session is None

    def test_session_property_connects_if_needed(self, config):
        """Test session property auto-connects."""
        client = ConfluenceClient(config)
        assert client._session is None

        with patch.object(client, "connect") as mock_connect:
            mock_connect.side_effect = lambda: setattr(client, "_session", MagicMock())
            _ = client.session
            mock_connect.assert_called_once()


class TestConfluenceClientRequest:
    """Tests for HTTP request handling."""

    def test_request_success(self, client, mock_page_response):
        """Test successful request."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = mock_page_response
        client._session.request.return_value = mock_response

        result = client._request("GET", "/content/123")

        assert result["id"] == "123456"

    def test_request_204_no_content(self, client):
        """Test 204 returns empty dict."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 204
        client._session.request.return_value = mock_response

        result = client._request("DELETE", "/content/123")

        assert result == {}

    def test_request_error(self, client):
        """Test error handling."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 404
        mock_response.reason = "Not Found"
        mock_response.text = "Page not found"
        mock_response.json.return_value = {"message": "Not found"}
        client._session.request.return_value = mock_response

        with pytest.raises(ConfluenceAPIError) as exc_info:
            client._request("GET", "/content/999")

        assert exc_info.value.status_code == 404

    def test_request_rate_limit(self, client, mock_page_response):
        """Test rate limit handling with retry."""
        rate_limit_response = MagicMock()
        rate_limit_response.status_code = 429
        rate_limit_response.headers = {"Retry-After": "1"}

        success_response = MagicMock()
        success_response.ok = True
        success_response.status_code = 200
        success_response.json.return_value = mock_page_response

        client._session.request.side_effect = [rate_limit_response, success_response]
        client.config.max_retries = 3

        with patch("time.sleep"):
            result = client._request("GET", "/content/123")

        assert result["id"] == "123456"

    def test_request_rate_limit_exceeded(self, client):
        """Test rate limit exceeded after max retries."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "1"}
        client._session.request.return_value = mock_response
        client.config.max_retries = 2

        with patch("time.sleep"):
            with pytest.raises(ConfluenceAPIError) as exc_info:
                client._request("GET", "/content/123", retry_count=2)

            assert exc_info.value.status_code == 429

    def test_request_timeout_retry(self, client, mock_page_response):
        """Test timeout with retry."""
        success_response = MagicMock()
        success_response.ok = True
        success_response.status_code = 200
        success_response.json.return_value = mock_page_response

        client._session.request.side_effect = [
            requests.exceptions.Timeout(),
            success_response,
        ]
        client.config.max_retries = 3

        with patch("time.sleep"):
            result = client._request("GET", "/content/123")

        assert result["id"] == "123456"

    def test_request_connection_error(self, client):
        """Test connection error handling."""
        client._session.request.side_effect = requests.exceptions.ConnectionError(
            "Connection refused"
        )

        with pytest.raises(ConfluenceAPIError, match="Request failed"):
            client._request("GET", "/content/123")


class TestConfluenceClientParseError:
    """Tests for error parsing."""

    def test_parse_error_message(self, client):
        """Test parsing error with message field."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"message": "Page not found"}

        result = client._parse_error(mock_response)
        assert result == "Page not found"

    def test_parse_error_messages_list(self, client):
        """Test parsing error with errorMessages list."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"errorMessages": ["Error 1", "Error 2"]}

        result = client._parse_error(mock_response)
        assert "Error 1" in result
        assert "Error 2" in result

    def test_parse_error_fallback(self, client):
        """Test fallback to HTTP status."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.reason = "Internal Server Error"
        mock_response.json.side_effect = ValueError()

        result = client._parse_error(mock_response)
        assert "500" in result


class TestConfluenceClientSpaceAPI:
    """Tests for Space API."""

    def test_get_space(self, client):
        """Test getting a space."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"key": "DEV", "name": "Development"}
        client._session.request.return_value = mock_response

        result = client.get_space("DEV")

        assert result["key"] == "DEV"

    def test_list_spaces(self, client):
        """Test listing spaces."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": [{"key": "DEV"}, {"key": "PROD"}]}
        client._session.request.return_value = mock_response

        result = client.list_spaces()

        assert len(result) == 2


class TestConfluenceClientContentAPI:
    """Tests for Content/Page API."""

    def test_get_content(self, client, mock_page_response):
        """Test getting content."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = mock_page_response
        client._session.request.return_value = mock_response

        result = client.get_content("123456")

        assert result["id"] == "123456"

    def test_get_content_with_expand(self, client, mock_page_response):
        """Test getting content with expand."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = mock_page_response
        client._session.request.return_value = mock_response

        client.get_content("123456", expand=["body.storage", "version"])

        call_args = client._session.request.call_args
        assert "body.storage,version" in str(call_args)

    def test_get_content_by_title(self, client, mock_page_response):
        """Test finding content by title."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": [mock_page_response]}
        client._session.request.return_value = mock_response

        result = client.get_content_by_title("DEV", "Test Page")

        assert result["title"] == "Test Page"

    def test_get_content_by_title_not_found(self, client):
        """Test content by title not found."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}
        client._session.request.return_value = mock_response

        result = client.get_content_by_title("DEV", "Nonexistent")

        assert result is None

    def test_create_content(self, client, mock_page_response):
        """Test creating content."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = mock_page_response
        client._session.request.return_value = mock_response

        result = client.create_content(
            space_key="DEV",
            title="New Page",
            body="<p>Content</p>",
        )

        assert result["id"] == "123456"

    def test_create_content_with_parent(self, client, mock_page_response):
        """Test creating content with parent."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = mock_page_response
        client._session.request.return_value = mock_response

        client.create_content(
            space_key="DEV",
            title="Child Page",
            body="<p>Content</p>",
            parent_id="parent-123",
        )

        call_args = client._session.request.call_args
        assert "ancestors" in str(call_args)

    def test_update_content(self, client, mock_page_response):
        """Test updating content."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_page_response["version"]["number"] = 2
        mock_response.json.return_value = mock_page_response
        client._session.request.return_value = mock_response

        result = client.update_content(
            content_id="123456",
            title="Updated Page",
            body="<p>Updated content</p>",
            version=1,
        )

        assert result["version"]["number"] == 2

    def test_delete_content(self, client):
        """Test deleting content."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 204
        client._session.request.return_value = mock_response

        client.delete_content("123456")

        client._session.request.assert_called_once()


class TestConfluenceClientLabelsAPI:
    """Tests for Labels API."""

    def test_get_labels(self, client):
        """Test getting labels."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": [{"name": "label1"}, {"name": "label2"}]}
        client._session.request.return_value = mock_response

        result = client.get_labels("123456")

        assert len(result) == 2

    def test_add_labels(self, client):
        """Test adding labels."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": [{"name": "new-label"}]}
        client._session.request.return_value = mock_response

        result = client.add_labels("123456", ["new-label"])

        assert len(result) == 1

    def test_remove_label(self, client):
        """Test removing a label."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 204
        client._session.request.return_value = mock_response

        client.remove_label("123456", "old-label")

        client._session.request.assert_called_once()


class TestConfluenceClientSearchAPI:
    """Tests for Search API."""

    def test_search(self, client, mock_page_response):
        """Test CQL search."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": [mock_page_response]}
        client._session.request.return_value = mock_response

        result = client.search("space = DEV and type = page")

        assert len(result) == 1

    def test_search_with_expand(self, client, mock_page_response):
        """Test search with expand."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": [mock_page_response]}
        client._session.request.return_value = mock_response

        client.search("type = page", expand=["body.storage"])

        call_args = client._session.request.call_args
        assert "body.storage" in str(call_args)


class TestConfluenceClientUserAPI:
    """Tests for User API."""

    def test_get_current_user(self, client):
        """Test getting current user."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "accountId": "user-123",
            "displayName": "Test User",
        }
        client._session.request.return_value = mock_response

        result = client.get_current_user()

        assert result["displayName"] == "Test User"


class TestConfluenceClientChildPagesAPI:
    """Tests for Child Pages API."""

    def test_get_child_pages(self, client, mock_page_response):
        """Test getting child pages."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": [mock_page_response]}
        client._session.request.return_value = mock_response

        result = client.get_child_pages("parent-123")

        assert len(result) == 1

    def test_get_child_pages_with_expand(self, client, mock_page_response):
        """Test getting child pages with expand."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": [mock_page_response]}
        client._session.request.return_value = mock_response

        client.get_child_pages("parent-123", expand=["body.storage"])

        call_args = client._session.request.call_args
        assert "body.storage" in str(call_args)


class TestConfluenceAPIError:
    """Tests for ConfluenceAPIError."""

    def test_error_with_status_code(self):
        """Test error with status code."""
        error = ConfluenceAPIError("Not found", status_code=404)
        assert error.status_code == 404

    def test_error_with_response_body(self):
        """Test error with response body."""
        error = ConfluenceAPIError(
            "Bad request",
            status_code=400,
            response_body='{"error": "Invalid"}',
        )
        assert error.response_body == '{"error": "Invalid"}'
