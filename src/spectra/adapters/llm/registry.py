"""
LLM Provider Registry - Dynamic provider registration and discovery.

Provides a central registry for all LLM providers, supporting:
- Built-in providers (Anthropic, OpenAI, Google)
- Local providers (Ollama, OpenAI-compatible)
- Custom/plugin providers
"""

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .base import LLMConfig, LLMProvider


logger = logging.getLogger(__name__)


class ProviderType(Enum):
    """Types of LLM providers."""

    CLOUD = "cloud"  # Cloud API providers (Anthropic, OpenAI, Google)
    LOCAL = "local"  # Local model providers (Ollama, LM Studio)
    CUSTOM = "custom"  # User-registered custom providers


@dataclass
class ProviderInfo:
    """Information about a registered provider."""

    name: str
    provider_type: ProviderType
    factory: Callable[[LLMConfig | None], LLMProvider]
    description: str = ""
    env_vars: list[str] = field(default_factory=list)
    default_base_url: str | None = None
    requires_api_key: bool = False
    models: list[str] = field(default_factory=list)


class LLMRegistry:
    """
    Registry for LLM providers.

    Supports dynamic registration and discovery of providers.
    """

    def __init__(self) -> None:
        """Initialize the registry with built-in providers."""
        self._providers: dict[str, ProviderInfo] = {}
        self._register_builtin_providers()

    def _register_builtin_providers(self) -> None:
        """Register built-in providers."""
        # Cloud providers
        self.register(
            name="anthropic",
            provider_type=ProviderType.CLOUD,
            factory=self._create_anthropic,
            description="Anthropic Claude (Claude 3.5 Sonnet, Claude 3 Opus, etc.)",
            env_vars=["ANTHROPIC_API_KEY"],
            requires_api_key=True,
            models=[
                "claude-3-5-sonnet-20241022",
                "claude-3-5-haiku-20241022",
                "claude-3-opus-20240229",
            ],
        )

        self.register(
            name="openai",
            provider_type=ProviderType.CLOUD,
            factory=self._create_openai,
            description="OpenAI GPT (GPT-4o, GPT-4, GPT-3.5)",
            env_vars=["OPENAI_API_KEY"],
            requires_api_key=True,
            models=["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo"],
        )

        self.register(
            name="google",
            provider_type=ProviderType.CLOUD,
            factory=self._create_google,
            description="Google Gemini (Gemini 1.5 Pro, Gemini 1.5 Flash)",
            env_vars=["GOOGLE_API_KEY"],
            requires_api_key=True,
            models=["gemini-1.5-pro", "gemini-1.5-flash", "gemini-1.5-flash-8b"],
        )

        # Local providers
        self.register(
            name="ollama",
            provider_type=ProviderType.LOCAL,
            factory=self._create_ollama,
            description="Ollama local models (Llama, Mistral, CodeLlama, etc.)",
            env_vars=["OLLAMA_HOST", "OLLAMA_MODEL"],
            default_base_url="http://localhost:11434",
            requires_api_key=False,
            models=["llama3.2", "mistral", "codellama", "phi3", "gemma2"],
        )

        self.register(
            name="openai-compatible",
            provider_type=ProviderType.LOCAL,
            factory=self._create_openai_compatible,
            description="OpenAI-compatible servers (LM Studio, LocalAI, vLLM)",
            env_vars=["OPENAI_COMPATIBLE_URL", "OPENAI_COMPATIBLE_MODEL"],
            default_base_url="http://localhost:1234/v1",
            requires_api_key=False,
            models=["local-model"],
        )

        self.register(
            name="lm-studio",
            provider_type=ProviderType.LOCAL,
            factory=self._create_lm_studio,
            description="LM Studio local server",
            default_base_url="http://localhost:1234/v1",
            requires_api_key=False,
            models=["local-model"],
        )

        self.register(
            name="localai",
            provider_type=ProviderType.LOCAL,
            factory=self._create_localai,
            description="LocalAI server",
            default_base_url="http://localhost:8080/v1",
            requires_api_key=False,
            models=["gpt-3.5-turbo"],
        )

        self.register(
            name="vllm",
            provider_type=ProviderType.LOCAL,
            factory=self._create_vllm,
            description="vLLM server",
            default_base_url="http://localhost:8000/v1",
            requires_api_key=False,
            models=[],
        )

    def register(
        self,
        name: str,
        provider_type: ProviderType,
        factory: Callable[[LLMConfig | None], LLMProvider],
        description: str = "",
        env_vars: list[str] | None = None,
        default_base_url: str | None = None,
        requires_api_key: bool = False,
        models: list[str] | None = None,
    ) -> None:
        """
        Register a provider.

        Args:
            name: Unique provider name (lowercase).
            provider_type: Type of provider (cloud, local, custom).
            factory: Factory function that creates the provider.
            description: Human-readable description.
            env_vars: Environment variables used for configuration.
            default_base_url: Default server URL (for local providers).
            requires_api_key: Whether an API key is required.
            models: List of known/supported models.
        """
        self._providers[name.lower()] = ProviderInfo(
            name=name.lower(),
            provider_type=provider_type,
            factory=factory,
            description=description,
            env_vars=env_vars or [],
            default_base_url=default_base_url,
            requires_api_key=requires_api_key,
            models=models or [],
        )

    def unregister(self, name: str) -> bool:
        """
        Unregister a provider.

        Args:
            name: Provider name.

        Returns:
            True if provider was removed, False if not found.
        """
        return self._providers.pop(name.lower(), None) is not None

    def get(self, name: str) -> ProviderInfo | None:
        """Get provider info by name."""
        return self._providers.get(name.lower())

    def list_providers(
        self,
        provider_type: ProviderType | None = None,
    ) -> list[ProviderInfo]:
        """
        List registered providers.

        Args:
            provider_type: Filter by provider type (optional).

        Returns:
            List of provider info objects.
        """
        providers = list(self._providers.values())
        if provider_type:
            providers = [p for p in providers if p.provider_type == provider_type]
        return providers

    def list_cloud_providers(self) -> list[ProviderInfo]:
        """List cloud API providers."""
        return self.list_providers(ProviderType.CLOUD)

    def list_local_providers(self) -> list[ProviderInfo]:
        """List local model providers."""
        return self.list_providers(ProviderType.LOCAL)

    def create_provider(
        self,
        name: str,
        config: LLMConfig | None = None,
    ) -> LLMProvider | None:
        """
        Create a provider instance.

        Args:
            name: Provider name.
            config: Optional configuration.

        Returns:
            Provider instance or None if provider not found.
        """
        info = self.get(name)
        if not info:
            return None

        try:
            return info.factory(config)
        except Exception as e:
            logger.warning(f"Failed to create provider '{name}': {e}")
            return None

    def detect_available_providers(self) -> list[tuple[str, LLMProvider]]:
        """
        Detect and create all available providers.

        Returns:
            List of (name, provider) tuples for available providers.
        """
        available = []

        for name, info in self._providers.items():
            try:
                provider = info.factory(None)
                if provider and provider.is_available():
                    available.append((name, provider))
            except Exception as e:
                logger.debug(f"Provider '{name}' not available: {e}")

        return available

    def get_provider_status(self) -> dict[str, Any]:
        """
        Get status of all providers.

        Returns:
            Dict with provider availability and configuration info.
        """
        status: dict[str, Any] = {
            "cloud_providers": {},
            "local_providers": {},
            "custom_providers": {},
        }

        for name, info in self._providers.items():
            provider_status: dict[str, Any] = {
                "available": False,
                "description": info.description,
                "env_vars": info.env_vars,
                "requires_api_key": info.requires_api_key,
            }

            if info.default_base_url:
                provider_status["default_url"] = info.default_base_url

            # Check availability
            try:
                provider = info.factory(None)
                if provider:
                    provider_status["available"] = provider.is_available()
                    if provider_status["available"]:
                        provider_status["models"] = provider.available_models
            except Exception:
                pass

            category = f"{info.provider_type.value}_providers"
            status[category][name] = provider_status

        return status

    # Factory methods for built-in providers

    @staticmethod
    def _create_anthropic(config: LLMConfig | None) -> LLMProvider:
        """Create Anthropic provider."""
        from .anthropic import AnthropicProvider

        return AnthropicProvider(config)

    @staticmethod
    def _create_openai(config: LLMConfig | None) -> LLMProvider:
        """Create OpenAI provider."""
        from .openai import OpenAIProvider

        return OpenAIProvider(config)

    @staticmethod
    def _create_google(config: LLMConfig | None) -> LLMProvider:
        """Create Google provider."""
        from .google import GoogleProvider

        return GoogleProvider(config)

    @staticmethod
    def _create_ollama(config: LLMConfig | None) -> LLMProvider:
        """Create Ollama provider."""
        from .ollama import OllamaProvider

        return OllamaProvider(config)

    @staticmethod
    def _create_openai_compatible(config: LLMConfig | None) -> LLMProvider:
        """Create OpenAI-compatible provider."""
        from .openai_compatible import OpenAICompatibleProvider

        return OpenAICompatibleProvider(config)

    @staticmethod
    def _create_lm_studio(config: LLMConfig | None) -> LLMProvider:
        """Create LM Studio provider."""
        from .openai_compatible import create_lm_studio_provider

        if config:
            return create_lm_studio_provider(
                model=config.model,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
            )
        return create_lm_studio_provider()

    @staticmethod
    def _create_localai(config: LLMConfig | None) -> LLMProvider:
        """Create LocalAI provider."""
        from .openai_compatible import create_local_ai_provider

        if config:
            return create_local_ai_provider(
                model=config.model,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
            )
        return create_local_ai_provider()

    @staticmethod
    def _create_vllm(config: LLMConfig | None) -> LLMProvider:
        """Create vLLM provider."""
        from .openai_compatible import create_vllm_provider

        model = config.model if config else os.environ.get("VLLM_MODEL", "default")
        if config:
            return create_vllm_provider(
                model=model,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
            )
        return create_vllm_provider(model=model)


# Global registry instance
_global_registry: LLMRegistry | None = None


def get_registry() -> LLMRegistry:
    """Get the global LLM provider registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = LLMRegistry()
    return _global_registry


def register_provider(
    name: str,
    provider_type: ProviderType,
    factory: Callable[[LLMConfig | None], LLMProvider],
    **kwargs: Any,
) -> None:
    """
    Register a custom provider in the global registry.

    Args:
        name: Unique provider name.
        provider_type: Type of provider.
        factory: Factory function.
        **kwargs: Additional options passed to registry.register().
    """
    get_registry().register(name, provider_type, factory, **kwargs)


def list_all_providers() -> list[ProviderInfo]:
    """List all registered providers."""
    return get_registry().list_providers()


def create_provider(name: str, config: LLMConfig | None = None) -> LLMProvider | None:
    """
    Create a provider from the global registry.

    Args:
        name: Provider name.
        config: Optional configuration.

    Returns:
        Provider instance or None.
    """
    return get_registry().create_provider(name, config)
