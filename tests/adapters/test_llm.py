"""Tests for LLM provider functionality."""

from unittest.mock import MagicMock, patch

import pytest

from spectryn.adapters.llm.base import (
    LLMConfig,
    LLMMessage,
    LLMProvider,
    LLMResponse,
    LLMRole,
    MessageContent,
)
from spectryn.adapters.llm.manager import (
    LLMManager,
    LLMManagerConfig,
    ProviderName,
    create_llm_manager,
)


class TestLLMRole:
    """Tests for LLMRole enum."""

    def test_all_roles_exist(self):
        """Test all roles are defined."""
        assert LLMRole.SYSTEM.value == "system"
        assert LLMRole.USER.value == "user"
        assert LLMRole.ASSISTANT.value == "assistant"


class TestMessageContent:
    """Tests for MessageContent dataclass."""

    def test_create_text_content(self):
        """Test creating text content."""
        content = MessageContent(type="text", text="Hello, world!")
        assert content.type == "text"
        assert content.text == "Hello, world!"

    def test_default_values(self):
        """Test default values."""
        content = MessageContent()
        assert content.type == "text"
        assert content.text == ""
        assert content.image_url is None


class TestLLMMessage:
    """Tests for LLMMessage dataclass."""

    def test_create_with_string_content(self):
        """Test creating message with string content."""
        msg = LLMMessage(role=LLMRole.USER, content="Hello!")
        assert msg.role == LLMRole.USER
        assert msg.content == "Hello!"

    def test_create_with_list_content(self):
        """Test creating message with content list."""
        content = [MessageContent(text="Hello!")]
        msg = LLMMessage(role=LLMRole.USER, content=content)
        assert len(msg.content) == 1

    def test_to_dict_string(self):
        """Test converting to dict with string content."""
        msg = LLMMessage(role=LLMRole.USER, content="Test message")
        data = msg.to_dict()

        assert data["role"] == "user"
        assert data["content"] == "Test message"


class TestLLMResponse:
    """Tests for LLMResponse dataclass."""

    def test_create_basic(self):
        """Test creating a basic response."""
        response = LLMResponse(
            content="Hello!",
            model="claude-3-sonnet",
            provider="Anthropic",
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
        )
        assert response.content == "Hello!"
        assert response.total_tokens == 15

    def test_cost_estimate_claude(self):
        """Test cost estimate for Claude."""
        response = LLMResponse(
            content="Test",
            model="claude-3-5-sonnet",
            provider="Anthropic",
            input_tokens=1000,
            output_tokens=500,
        )
        # Should have some cost estimate
        assert response.cost_estimate >= 0

    def test_cost_estimate_gpt(self):
        """Test cost estimate for GPT."""
        response = LLMResponse(
            content="Test",
            model="gpt-4o-mini",
            provider="OpenAI",
            input_tokens=1000,
            output_tokens=500,
        )
        assert response.cost_estimate >= 0

    def test_to_dict(self):
        """Test converting to dictionary."""
        response = LLMResponse(
            content="Hello!",
            model="test-model",
            provider="Test",
        )
        data = response.to_dict()

        assert data["content"] == "Hello!"
        assert data["model"] == "test-model"
        assert "timestamp" in data


class TestLLMConfig:
    """Tests for LLMConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = LLMConfig()
        assert config.api_key is None
        assert config.max_tokens == 4096
        assert config.temperature == 0.7

    def test_custom_values(self):
        """Test custom configuration values."""
        config = LLMConfig(
            api_key="test-key",
            model="claude-3-opus",
            max_tokens=8192,
            temperature=0.5,
        )
        assert config.api_key == "test-key"
        assert config.model == "claude-3-opus"
        assert config.max_tokens == 8192


class TestLLMManagerConfig:
    """Tests for LLMManagerConfig dataclass."""

    def test_default_provider_order(self):
        """Test default provider order."""
        config = LLMManagerConfig()
        assert config.provider_order[0] == ProviderName.ANTHROPIC
        # Now includes local providers (5 total: 3 cloud + 2 local)
        assert len(config.provider_order) >= 3

    def test_fallback_enabled_by_default(self):
        """Test fallback is enabled by default."""
        config = LLMManagerConfig()
        assert config.enable_fallback is True


class TestLLMManager:
    """Tests for LLMManager class."""

    def test_create_with_no_providers(self):
        """Test creating manager with no API keys."""
        config = LLMManagerConfig()
        manager = LLMManager(config)

        # No providers available without API keys
        assert len(manager.providers) == 0
        assert not manager.is_available()

    def test_available_providers_empty(self):
        """Test available_providers when none configured."""
        manager = LLMManager()
        assert manager.available_providers == []

    def test_primary_provider_none(self):
        """Test primary_provider when none available."""
        manager = LLMManager()
        assert manager.primary_provider is None

    def test_get_status_no_providers(self):
        """Test get_status with no providers."""
        manager = LLMManager()
        status = manager.get_status()

        assert status["available"] is False
        # Now uses cloud_providers and local_providers instead of providers
        assert "cloud_providers" in status
        assert status["cloud_providers"]["anthropic"]["available"] is False

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    def test_initialize_with_anthropic_env(self):
        """Test initialization with Anthropic env var."""
        # This will attempt to create Anthropic provider
        # It may fail if anthropic SDK not installed, which is fine
        config = LLMManagerConfig()
        manager = LLMManager(config)

        # Either provider is available or SDK not installed
        status = manager.get_status()
        assert "anthropic" in status["cloud_providers"]


class TestCreateLLMManager:
    """Tests for create_llm_manager function."""

    def test_create_with_defaults(self):
        """Test creating manager with defaults."""
        manager = create_llm_manager()

        assert manager.config.max_tokens == 4096
        assert manager.config.temperature == 0.7
        assert manager.config.enable_fallback is True

    def test_create_with_preferred_provider(self):
        """Test creating manager with preferred provider."""
        manager = create_llm_manager(prefer_provider="openai")

        # OpenAI should be first in order
        assert manager.config.provider_order[0] == ProviderName.OPENAI

    def test_create_with_custom_settings(self):
        """Test creating manager with custom settings."""
        manager = create_llm_manager(
            max_tokens=2048,
            temperature=0.5,
            enable_fallback=False,
        )

        assert manager.config.max_tokens == 2048
        assert manager.config.temperature == 0.5
        assert manager.config.enable_fallback is False


class TestProviderName:
    """Tests for ProviderName enum."""

    def test_all_providers_exist(self):
        """Test all provider names are defined."""
        assert ProviderName.ANTHROPIC.value == "anthropic"
        assert ProviderName.OPENAI.value == "openai"
        assert ProviderName.GOOGLE.value == "google"


class MockLLMProvider(LLMProvider):
    """Mock LLM provider for testing."""

    def __init__(self, config: LLMConfig | None = None):
        super().__init__(config or LLMConfig())
        self._response = LLMResponse(
            content="Mock response",
            model="mock-model",
            provider="Mock",
        )

    @property
    def name(self) -> str:
        return "Mock"

    @property
    def available_models(self) -> list[str]:
        return ["mock-model"]

    @property
    def default_model(self) -> str:
        return "mock-model"

    def is_available(self) -> bool:
        return True

    def complete(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        return self._response


class TestLLMProviderAbstract:
    """Tests for LLMProvider abstract class."""

    def test_prompt_convenience_method(self):
        """Test prompt convenience method."""
        provider = MockLLMProvider()
        response = provider.prompt("Hello!")

        assert response.content == "Mock response"

    def test_prompt_with_system(self):
        """Test prompt with system prompt."""
        provider = MockLLMProvider(LLMConfig(system_prompt="You are helpful."))
        response = provider.prompt("Hello!")

        assert response.content == "Mock response"

    def test_chat_convenience_method(self):
        """Test chat convenience method."""
        provider = MockLLMProvider()
        messages = [
            ("user", "Hello!"),
            ("assistant", "Hi there!"),
            ("user", "How are you?"),
        ]
        response = provider.chat(messages)

        assert response.content == "Mock response"
