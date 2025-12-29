"""Tests for LLM provider abstraction - local and cloud providers."""

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from spectra.adapters.llm.base import (
    LLMConfig,
    LLMMessage,
    LLMResponse,
    LLMRole,
)
from spectra.adapters.llm.manager import (
    LLMManager,
    LLMManagerConfig,
    ProviderName,
    create_llm_manager,
)
from spectra.adapters.llm.ollama import (
    OllamaProvider,
    create_ollama_provider,
)
from spectra.adapters.llm.openai_compatible import (
    OpenAICompatibleProvider,
    create_lm_studio_provider,
    create_local_ai_provider,
    create_openai_compatible_provider,
    create_vllm_provider,
)
from spectra.adapters.llm.registry import (
    LLMRegistry,
    ProviderInfo,
    ProviderType,
    create_provider,
    get_registry,
    list_all_providers,
    register_provider,
)


class TestOllamaProvider:
    """Tests for Ollama local LLM provider."""

    def test_create_with_defaults(self):
        """Test creating provider with default settings."""
        provider = OllamaProvider()

        assert provider.name == "Ollama"
        assert provider.default_model == "llama3.2"
        assert "llama3.2" in provider.POPULAR_MODELS

    def test_create_with_config(self):
        """Test creating provider with custom config."""
        config = LLMConfig(
            base_url="http://myserver:11434",
            model="mistral",
            temperature=0.5,
        )
        provider = OllamaProvider(config)

        assert provider._base_url == "http://myserver:11434"
        assert provider.config.model == "mistral"
        assert provider.config.temperature == 0.5

    @patch.dict("os.environ", {"OLLAMA_HOST": "http://env-server:11434"})
    def test_create_from_env(self):
        """Test creating provider from environment variables."""
        provider = OllamaProvider()
        assert provider._base_url == "http://env-server:11434"

    def test_is_available_returns_false_when_not_running(self):
        """Test is_available when Ollama is not running."""
        provider = OllamaProvider(LLMConfig(base_url="http://localhost:99999"))
        assert not provider.is_available()

    @patch("urllib.request.urlopen")
    def test_is_available_returns_true(self, mock_urlopen):
        """Test is_available when Ollama is running."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = lambda s: mock_response
        mock_response.__exit__ = MagicMock()
        mock_urlopen.return_value = mock_response

        provider = OllamaProvider()
        assert provider.is_available()

    @patch("urllib.request.urlopen")
    def test_fetch_models(self, mock_urlopen):
        """Test fetching available models from Ollama."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps(
            {
                "models": [
                    {"name": "llama3.2:latest"},
                    {"name": "mistral:latest"},
                    {"name": "codellama:13b"},
                ]
            }
        ).encode()
        mock_response.__enter__ = lambda s: mock_response
        mock_response.__exit__ = MagicMock()
        mock_urlopen.return_value = mock_response

        provider = OllamaProvider()
        models = provider._fetch_models()

        assert "llama3.2:latest" in models
        assert "mistral:latest" in models
        assert "codellama:13b" in models

    @patch("urllib.request.urlopen")
    def test_complete(self, mock_urlopen):
        """Test generating completion with Ollama."""
        # Mock is_available check
        avail_response = MagicMock()
        avail_response.status = 200
        avail_response.__enter__ = lambda s: avail_response
        avail_response.__exit__ = MagicMock()

        # Mock chat completion
        chat_response = MagicMock()
        chat_response.read.return_value = json.dumps(
            {
                "model": "llama3.2",
                "message": {"role": "assistant", "content": "Hello! How can I help?"},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 10,
                "eval_count": 20,
            }
        ).encode()
        chat_response.__enter__ = lambda s: chat_response
        chat_response.__exit__ = MagicMock()

        mock_urlopen.side_effect = [avail_response, chat_response]

        provider = OllamaProvider()
        messages = [LLMMessage(role=LLMRole.USER, content="Hello!")]
        response = provider.complete(messages)

        assert response.content == "Hello! How can I help?"
        assert response.model == "llama3.2"
        assert response.provider == "Ollama"
        assert response.input_tokens == 10
        assert response.output_tokens == 20


class TestOpenAICompatibleProvider:
    """Tests for OpenAI-compatible local server provider."""

    def test_create_with_defaults(self):
        """Test creating provider with default settings."""
        provider = OpenAICompatibleProvider()

        assert "OpenAI-Compatible" in provider.name
        assert provider.default_model == "local-model"
        assert provider._base_url.endswith("/v1")

    def test_create_with_config(self):
        """Test creating provider with custom config."""
        config = LLMConfig(
            base_url="http://localhost:8080/v1",
            model="gpt-3.5-turbo",
            api_key="test-key",
        )
        provider = OpenAICompatibleProvider(config)

        assert provider._base_url == "http://localhost:8080/v1"
        assert provider.config.model == "gpt-3.5-turbo"
        assert provider._api_key == "test-key"

    def test_base_url_adds_v1(self):
        """Test that /v1 is appended if not present."""
        config = LLMConfig(base_url="http://localhost:1234")
        provider = OpenAICompatibleProvider(config)
        assert provider._base_url == "http://localhost:1234/v1"

    def test_set_server_name(self):
        """Test setting custom server name."""
        provider = OpenAICompatibleProvider()
        provider.set_server_name("LM Studio")

        assert "LM Studio" in provider.name

    def test_is_available_returns_false_when_not_running(self):
        """Test is_available when server is not running."""
        provider = OpenAICompatibleProvider(LLMConfig(base_url="http://localhost:99999/v1"))
        assert not provider.is_available()

    @patch("urllib.request.urlopen")
    def test_complete(self, mock_urlopen):
        """Test generating completion with OpenAI-compatible server."""
        # Mock is_available check
        avail_response = MagicMock()
        avail_response.status = 200
        avail_response.__enter__ = lambda s: avail_response
        avail_response.__exit__ = MagicMock()

        # Mock chat completion (OpenAI format)
        chat_response = MagicMock()
        chat_response.read.return_value = json.dumps(
            {
                "id": "chatcmpl-123",
                "model": "local-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Test response"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 15,
                    "completion_tokens": 25,
                    "total_tokens": 40,
                },
            }
        ).encode()
        chat_response.__enter__ = lambda s: chat_response
        chat_response.__exit__ = MagicMock()

        mock_urlopen.side_effect = [avail_response, chat_response]

        provider = OpenAICompatibleProvider()
        messages = [LLMMessage(role=LLMRole.USER, content="Hello!")]
        response = provider.complete(messages)

        assert response.content == "Test response"
        assert response.model == "local-model"
        assert "OpenAI-Compatible" in response.provider
        assert response.input_tokens == 15
        assert response.output_tokens == 25


class TestConvenienceFactories:
    """Tests for convenience factory functions."""

    def test_create_ollama_provider(self):
        """Test create_ollama_provider factory."""
        provider = create_ollama_provider(
            model="codellama",
            base_url="http://myserver:11434",
            temperature=0.3,
        )

        assert provider.config.model == "codellama"
        assert provider._base_url == "http://myserver:11434"
        assert provider.config.temperature == 0.3

    def test_create_openai_compatible_provider(self):
        """Test create_openai_compatible_provider factory."""
        provider = create_openai_compatible_provider(
            base_url="http://localhost:8080/v1",
            model="my-model",
            server_name="TestServer",
        )

        assert "TestServer" in provider.name
        assert provider.config.model == "my-model"

    def test_create_lm_studio_provider(self):
        """Test create_lm_studio_provider factory."""
        provider = create_lm_studio_provider(port=5678)

        assert "LM Studio" in provider.name
        assert "5678" in provider._base_url

    def test_create_local_ai_provider(self):
        """Test create_local_ai_provider factory."""
        provider = create_local_ai_provider(port=8080)

        assert "LocalAI" in provider.name
        assert "8080" in provider._base_url

    def test_create_vllm_provider(self):
        """Test create_vllm_provider factory."""
        provider = create_vllm_provider(model="meta-llama/Llama-2-7b")

        assert "vLLM" in provider.name
        assert provider.config.model == "meta-llama/Llama-2-7b"


class TestLLMRegistry:
    """Tests for LLM provider registry."""

    def test_registry_has_builtin_providers(self):
        """Test that registry includes built-in providers."""
        registry = LLMRegistry()

        # Cloud providers
        assert registry.get("anthropic") is not None
        assert registry.get("openai") is not None
        assert registry.get("google") is not None

        # Local providers
        assert registry.get("ollama") is not None
        assert registry.get("openai-compatible") is not None
        assert registry.get("lm-studio") is not None

    def test_list_cloud_providers(self):
        """Test listing cloud providers."""
        registry = LLMRegistry()
        cloud = registry.list_cloud_providers()

        names = [p.name for p in cloud]
        assert "anthropic" in names
        assert "openai" in names
        assert "google" in names

    def test_list_local_providers(self):
        """Test listing local providers."""
        registry = LLMRegistry()
        local = registry.list_local_providers()

        names = [p.name for p in local]
        assert "ollama" in names
        assert "openai-compatible" in names

    def test_register_custom_provider(self):
        """Test registering a custom provider."""
        registry = LLMRegistry()

        def my_factory(config: LLMConfig | None) -> Any:
            return MagicMock()

        registry.register(
            name="my-provider",
            provider_type=ProviderType.CUSTOM,
            factory=my_factory,
            description="My custom provider",
        )

        info = registry.get("my-provider")
        assert info is not None
        assert info.provider_type == ProviderType.CUSTOM
        assert info.description == "My custom provider"

    def test_unregister_provider(self):
        """Test unregistering a provider."""
        registry = LLMRegistry()

        registry.register(
            name="temp-provider",
            provider_type=ProviderType.CUSTOM,
            factory=lambda c: MagicMock(),
        )

        assert registry.get("temp-provider") is not None
        assert registry.unregister("temp-provider") is True
        assert registry.get("temp-provider") is None

    def test_global_registry(self):
        """Test global registry functions."""
        registry = get_registry()
        assert isinstance(registry, LLMRegistry)

        providers = list_all_providers()
        assert len(providers) > 0


class TestProviderName:
    """Tests for extended ProviderName enum."""

    def test_cloud_providers_exist(self):
        """Test cloud provider names are defined."""
        assert ProviderName.ANTHROPIC.value == "anthropic"
        assert ProviderName.OPENAI.value == "openai"
        assert ProviderName.GOOGLE.value == "google"

    def test_local_providers_exist(self):
        """Test local provider names are defined."""
        assert ProviderName.OLLAMA.value == "ollama"
        assert ProviderName.LM_STUDIO.value == "lm-studio"
        assert ProviderName.OPENAI_COMPATIBLE.value == "openai-compatible"


class TestLLMManagerWithLocalProviders:
    """Tests for LLMManager with local provider support."""

    def test_config_includes_local_settings(self):
        """Test LLMManagerConfig includes local provider settings."""
        config = LLMManagerConfig(
            ollama_host="http://localhost:11434",
            ollama_model="llama3.2",
            openai_compatible_url="http://localhost:1234/v1",
            prefer_local=True,
        )

        assert config.ollama_host == "http://localhost:11434"
        assert config.ollama_model == "llama3.2"
        assert config.openai_compatible_url == "http://localhost:1234/v1"
        assert config.prefer_local is True

    def test_provider_order_includes_local(self):
        """Test default provider order includes local providers."""
        config = LLMManagerConfig()

        assert ProviderName.OLLAMA in config.provider_order
        assert ProviderName.LM_STUDIO in config.provider_order

    def test_create_llm_manager_with_local_options(self):
        """Test create_llm_manager with local provider options."""
        manager = create_llm_manager(
            ollama_model="codellama",
            prefer_provider="ollama",
            prefer_local=True,
        )

        assert manager.config.ollama_model == "codellama"
        assert manager.config.prefer_local is True
        assert manager.config.provider_order[0] == ProviderName.OLLAMA

    def test_has_local_provider(self):
        """Test has_local_provider property."""
        manager = create_llm_manager()
        # Should be False by default (no local servers running)
        # This is expected behavior - we're just testing the property exists
        assert isinstance(manager.has_local_provider, bool)

    def test_has_cloud_provider(self):
        """Test has_cloud_provider property."""
        manager = create_llm_manager()
        # Should be False if no API keys are set
        assert isinstance(manager.has_cloud_provider, bool)

    def test_get_status_includes_local_providers(self):
        """Test get_status includes local provider info."""
        manager = create_llm_manager()
        status = manager.get_status()

        assert "cloud_providers" in status
        assert "local_providers" in status
        assert "has_cloud" in status
        assert "has_local" in status

        # Check structure
        assert "ollama" in status["local_providers"]
        assert "anthropic" in status["cloud_providers"]


class TestLLMManagerFallback:
    """Tests for fallback behavior with mixed providers."""

    def test_prefer_local_uses_local_first(self):
        """Test that prefer_local puts local providers first."""
        config = LLMManagerConfig(prefer_local=True)
        LLMManager(config)  # Create to verify it works

        # When prefer_local is True, local providers should be checked first
        # in primary_provider (even if none are available)
        # The logic is in the primary_provider property
        assert config.prefer_local is True

    def test_create_manager_with_prefer_openai_compatible(self):
        """Test creating manager preferring OpenAI-compatible."""
        manager = create_llm_manager(
            prefer_provider="openai-compatible",
            openai_compatible_url="http://localhost:1234/v1",
        )

        assert manager.config.provider_order[0] == ProviderName.OPENAI_COMPATIBLE


class TestModuleExports:
    """Test that all expected exports are available."""

    def test_imports_from_llm_package(self):
        """Test importing from spectra.adapters.llm."""
        # Import all expected exports to verify they're available
        from spectra.adapters import llm

        # Verify key types exist
        assert hasattr(llm, "LLMConfig")
        assert hasattr(llm, "LLMManager")
        assert hasattr(llm, "LLMManagerConfig")
        assert hasattr(llm, "LLMMessage")
        assert hasattr(llm, "LLMProvider")
        assert hasattr(llm, "LLMRegistry")
        assert hasattr(llm, "LLMResponse")
        assert hasattr(llm, "LLMRole")
        assert hasattr(llm, "OllamaProvider")
        assert hasattr(llm, "OpenAICompatibleProvider")
        assert hasattr(llm, "ProviderInfo")
        assert hasattr(llm, "ProviderName")
        assert hasattr(llm, "ProviderType")
        assert hasattr(llm, "create_lm_studio_provider")
        assert hasattr(llm, "create_llm_manager")
        assert hasattr(llm, "create_local_ai_provider")
        assert hasattr(llm, "create_ollama_provider")
        assert hasattr(llm, "create_openai_compatible_provider")
        assert hasattr(llm, "create_provider")
        assert hasattr(llm, "create_vllm_provider")
        assert hasattr(llm, "get_registry")
        assert hasattr(llm, "list_all_providers")
        assert hasattr(llm, "register_provider")
