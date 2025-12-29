"""
LLM Manager - Unified interface for multiple LLM providers.

Provides automatic provider selection, fallback, and common use cases.
Supports both cloud providers (Anthropic, OpenAI, Google) and local
providers (Ollama, LM Studio, LocalAI, vLLM).
"""

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .base import LLMConfig, LLMMessage, LLMProvider, LLMResponse, LLMRole


logger = logging.getLogger(__name__)


class ProviderName(Enum):
    """Supported LLM provider names."""

    # Cloud providers
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE = "google"

    # Local providers
    OLLAMA = "ollama"
    LM_STUDIO = "lm-studio"
    OPENAI_COMPATIBLE = "openai-compatible"


@dataclass
class LLMManagerConfig:
    """Configuration for LLM Manager."""

    # Provider preference order (can include local providers)
    provider_order: list[ProviderName] = field(
        default_factory=lambda: [
            ProviderName.ANTHROPIC,
            ProviderName.OPENAI,
            ProviderName.GOOGLE,
            ProviderName.OLLAMA,
            ProviderName.LM_STUDIO,
        ]
    )

    # Cloud API keys (optional, will use env vars if not set)
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    google_api_key: str | None = None

    # Local provider settings
    ollama_host: str | None = None  # e.g., http://localhost:11434
    ollama_model: str | None = None  # e.g., llama3.2

    # OpenAI-compatible server settings
    openai_compatible_url: str | None = None  # e.g., http://localhost:1234/v1
    openai_compatible_model: str | None = None
    openai_compatible_api_key: str | None = None

    # Default settings
    max_tokens: int = 4096
    temperature: float = 0.7

    # Fallback behavior
    enable_fallback: bool = True

    # Whether to prefer local providers over cloud
    prefer_local: bool = False


class LLMManager:
    """
    Manages multiple LLM providers with automatic selection and fallback.
    """

    def __init__(self, config: LLMManagerConfig | None = None):
        """
        Initialize the LLM manager.

        Args:
            config: Manager configuration.
        """
        self.config = config or LLMManagerConfig()
        self.providers: dict[ProviderName, LLMProvider] = {}
        self.logger = logging.getLogger("LLMManager")

        self._initialize_providers()

    def _initialize_providers(self) -> None:
        """Initialize available providers based on configuration."""
        # Cloud providers
        self._init_anthropic()
        self._init_openai()
        self._init_google()

        # Local providers
        self._init_ollama()
        self._init_openai_compatible()

    def _init_anthropic(self) -> None:
        """Initialize Anthropic provider."""
        anthropic_key = self.config.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
        if anthropic_key:
            try:
                from .anthropic import AnthropicProvider

                provider = AnthropicProvider(
                    LLMConfig(
                        api_key=anthropic_key,
                        max_tokens=self.config.max_tokens,
                        temperature=self.config.temperature,
                    )
                )
                if provider.is_available():
                    self.providers[ProviderName.ANTHROPIC] = provider
                    self.logger.debug("Anthropic provider initialized")
            except ImportError:
                self.logger.debug("Anthropic SDK not installed")

    def _init_openai(self) -> None:
        """Initialize OpenAI provider."""
        openai_key = self.config.openai_api_key or os.environ.get("OPENAI_API_KEY")
        if openai_key:
            try:
                from .openai import OpenAIProvider

                provider = OpenAIProvider(
                    LLMConfig(
                        api_key=openai_key,
                        max_tokens=self.config.max_tokens,
                        temperature=self.config.temperature,
                    )
                )
                if provider.is_available():
                    self.providers[ProviderName.OPENAI] = provider
                    self.logger.debug("OpenAI provider initialized")
            except ImportError:
                self.logger.debug("OpenAI SDK not installed")

    def _init_google(self) -> None:
        """Initialize Google provider."""
        google_key = self.config.google_api_key or os.environ.get("GOOGLE_API_KEY")
        if google_key:
            try:
                from .google import GoogleProvider

                provider = GoogleProvider(
                    LLMConfig(
                        api_key=google_key,
                        max_tokens=self.config.max_tokens,
                        temperature=self.config.temperature,
                    )
                )
                if provider.is_available():
                    self.providers[ProviderName.GOOGLE] = provider
                    self.logger.debug("Google provider initialized")
            except ImportError:
                self.logger.debug("Google SDK not installed")

    def _init_ollama(self) -> None:
        """Initialize Ollama provider for local models."""
        # Ollama doesn't require an API key - just check if server is available
        ollama_host = self.config.ollama_host or os.environ.get("OLLAMA_HOST")
        ollama_model = self.config.ollama_model or os.environ.get("OLLAMA_MODEL")

        try:
            from .ollama import OllamaProvider

            provider = OllamaProvider(
                LLMConfig(
                    base_url=ollama_host,
                    model=ollama_model or OllamaProvider.DEFAULT_MODEL,
                    max_tokens=self.config.max_tokens,
                    temperature=self.config.temperature,
                )
            )
            if provider.is_available():
                self.providers[ProviderName.OLLAMA] = provider
                self.logger.debug("Ollama provider initialized")
        except Exception as e:
            self.logger.debug(f"Ollama not available: {e}")

    def _init_openai_compatible(self) -> None:
        """Initialize OpenAI-compatible provider for local servers."""
        compat_url = self.config.openai_compatible_url or os.environ.get("OPENAI_COMPATIBLE_URL")
        compat_model = self.config.openai_compatible_model or os.environ.get(
            "OPENAI_COMPATIBLE_MODEL"
        )
        compat_key = self.config.openai_compatible_api_key or os.environ.get(
            "OPENAI_COMPATIBLE_API_KEY"
        )

        if compat_url:
            try:
                from .openai_compatible import OpenAICompatibleProvider

                provider = OpenAICompatibleProvider(
                    LLMConfig(
                        base_url=compat_url,
                        model=compat_model or "local-model",
                        api_key=compat_key,
                        max_tokens=self.config.max_tokens,
                        temperature=self.config.temperature,
                    )
                )
                if provider.is_available():
                    self.providers[ProviderName.OPENAI_COMPATIBLE] = provider
                    self.logger.debug("OpenAI-compatible provider initialized")

                    # Also register as LM Studio if it's the default port
                    if "1234" in compat_url:
                        self.providers[ProviderName.LM_STUDIO] = provider
            except Exception as e:
                self.logger.debug(f"OpenAI-compatible provider not available: {e}")

    @property
    def available_providers(self) -> list[ProviderName]:
        """Get list of available providers."""
        return list(self.providers.keys())

    @property
    def primary_provider(self) -> LLMProvider | None:
        """Get the primary (first available) provider."""
        # If prefer_local is set, try local providers first
        if self.config.prefer_local:
            local_providers = [
                ProviderName.OLLAMA,
                ProviderName.LM_STUDIO,
                ProviderName.OPENAI_COMPATIBLE,
            ]
            for name in local_providers:
                if name in self.providers:
                    return self.providers[name]

        # Follow configured order
        for name in self.config.provider_order:
            if name in self.providers:
                return self.providers[name]
        return None

    @property
    def has_local_provider(self) -> bool:
        """Check if any local provider is available."""
        local_names = {
            ProviderName.OLLAMA,
            ProviderName.LM_STUDIO,
            ProviderName.OPENAI_COMPATIBLE,
        }
        return bool(local_names & set(self.providers.keys()))

    @property
    def has_cloud_provider(self) -> bool:
        """Check if any cloud provider is available."""
        cloud_names = {
            ProviderName.ANTHROPIC,
            ProviderName.OPENAI,
            ProviderName.GOOGLE,
        }
        return bool(cloud_names & set(self.providers.keys()))

    def get_provider(self, name: ProviderName | str) -> LLMProvider | None:
        """Get a specific provider by name."""
        if isinstance(name, str):
            try:
                name = ProviderName(name.lower())
            except ValueError:
                return None
        return self.providers.get(name)

    def is_available(self) -> bool:
        """Check if any provider is available."""
        return len(self.providers) > 0

    def complete(
        self,
        messages: list[LLMMessage],
        provider: ProviderName | str | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """
        Generate a completion using the best available provider.

        Args:
            messages: List of messages.
            provider: Optional specific provider to use.
            **kwargs: Additional options.

        Returns:
            LLMResponse with the completion.

        Raises:
            RuntimeError: If no providers are available.
        """
        # Determine which provider to use
        if provider:
            llm = self.get_provider(provider)
            if not llm:
                raise RuntimeError(f"Provider '{provider}' not available")
            return llm.complete(messages, **kwargs)

        # Use primary provider
        llm = self.primary_provider
        if not llm:
            raise RuntimeError(
                "No LLM providers available. Options:\n"
                "  Cloud: Set ANTHROPIC_API_KEY, OPENAI_API_KEY, or GOOGLE_API_KEY\n"
                "  Local: Run Ollama (ollama serve) or LM Studio"
            )

        # Try with fallback
        if self.config.enable_fallback:
            return self._complete_with_fallback(messages, **kwargs)

        return llm.complete(messages, **kwargs)

    def _complete_with_fallback(
        self,
        messages: list[LLMMessage],
        **kwargs: Any,
    ) -> LLMResponse:
        """Complete with fallback to other providers on failure."""
        errors = []

        for name in self.config.provider_order:
            if name not in self.providers:
                continue

            provider = self.providers[name]
            try:
                return provider.complete(messages, **kwargs)
            except Exception as e:
                self.logger.warning(f"{name.value} failed: {e}")
                errors.append(f"{name.value}: {e}")

        raise RuntimeError(f"All providers failed: {'; '.join(errors)}")

    def prompt(
        self,
        user_message: str,
        system_prompt: str | None = None,
        provider: ProviderName | str | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """
        Simple single-turn prompt.

        Args:
            user_message: The user's message.
            system_prompt: Optional system prompt.
            provider: Optional specific provider.
            **kwargs: Additional options.

        Returns:
            LLMResponse with the completion.
        """
        messages = []

        if system_prompt:
            messages.append(LLMMessage(role=LLMRole.SYSTEM, content=system_prompt))

        messages.append(LLMMessage(role=LLMRole.USER, content=user_message))

        return self.complete(messages, provider=provider, **kwargs)

    def get_status(self) -> dict[str, Any]:
        """Get status of all providers."""
        status: dict[str, Any] = {
            "available": self.is_available(),
            "has_cloud": self.has_cloud_provider,
            "has_local": self.has_local_provider,
            "cloud_providers": {},
            "local_providers": {},
        }

        cloud_names = {ProviderName.ANTHROPIC, ProviderName.OPENAI, ProviderName.GOOGLE}

        for name in ProviderName:
            provider = self.providers.get(name)
            category = "cloud_providers" if name in cloud_names else "local_providers"

            if provider:
                status[category][name.value] = {
                    "available": True,
                    "models": provider.available_models[:5],  # Limit for display
                    "default_model": provider.default_model,
                }
            else:
                status[category][name.value] = {"available": False}

        if self.primary_provider:
            status["primary"] = self.primary_provider.name

        return status


def create_llm_manager(
    # Cloud provider keys
    anthropic_api_key: str | None = None,
    openai_api_key: str | None = None,
    google_api_key: str | None = None,
    # Local provider settings
    ollama_host: str | None = None,
    ollama_model: str | None = None,
    openai_compatible_url: str | None = None,
    openai_compatible_model: str | None = None,
    # General settings
    prefer_provider: str | None = None,
    prefer_local: bool = False,
    max_tokens: int = 4096,
    temperature: float = 0.7,
    enable_fallback: bool = True,
) -> LLMManager:
    """
    Create an LLM manager with the given settings.

    Supports both cloud providers (Anthropic, OpenAI, Google) and local
    providers (Ollama, LM Studio, LocalAI, vLLM).

    Args:
        anthropic_api_key: Anthropic API key.
        openai_api_key: OpenAI API key.
        google_api_key: Google API key.
        ollama_host: Ollama server URL (default: http://localhost:11434).
        ollama_model: Ollama model to use (default: llama3.2).
        openai_compatible_url: OpenAI-compatible server URL.
        openai_compatible_model: Model name for OpenAI-compatible server.
        prefer_provider: Preferred provider name.
        prefer_local: If True, prefer local providers over cloud.
        max_tokens: Maximum tokens to generate.
        temperature: Sampling temperature.
        enable_fallback: Enable fallback to other providers on failure.

    Returns:
        Configured LLMManager.

    Examples:
        # Use cloud providers (auto-detected from env vars)
        manager = create_llm_manager()

        # Prefer local Ollama
        manager = create_llm_manager(prefer_local=True)

        # Use specific Ollama model
        manager = create_llm_manager(
            ollama_model="codellama",
            prefer_provider="ollama",
        )

        # Use LM Studio
        manager = create_llm_manager(
            openai_compatible_url="http://localhost:1234/v1",
            prefer_provider="openai-compatible",
        )
    """
    # Determine provider order
    provider_order = [
        ProviderName.ANTHROPIC,
        ProviderName.OPENAI,
        ProviderName.GOOGLE,
        ProviderName.OLLAMA,
        ProviderName.LM_STUDIO,
        ProviderName.OPENAI_COMPATIBLE,
    ]

    if prefer_provider:
        try:
            # Handle both enum values and string names
            provider_name = prefer_provider.lower().replace("_", "-")
            preferred = ProviderName(provider_name)
            if preferred in provider_order:
                provider_order.remove(preferred)
            provider_order.insert(0, preferred)
        except ValueError:
            pass

    config = LLMManagerConfig(
        provider_order=provider_order,
        # Cloud keys
        anthropic_api_key=anthropic_api_key,
        openai_api_key=openai_api_key,
        google_api_key=google_api_key,
        # Local settings
        ollama_host=ollama_host,
        ollama_model=ollama_model,
        openai_compatible_url=openai_compatible_url,
        openai_compatible_model=openai_compatible_model,
        # General
        max_tokens=max_tokens,
        temperature=temperature,
        enable_fallback=enable_fallback,
        prefer_local=prefer_local,
    )

    return LLMManager(config)
