"""
Anthropic Claude Provider - Native Claude API integration.

Requires: pip install anthropic
"""

import os
import time
from typing import Any

from .base import LLMConfig, LLMMessage, LLMProvider, LLMResponse, LLMRole


# Try to import anthropic
try:
    import anthropic

    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    anthropic = None  # type: ignore


class AnthropicProvider(LLMProvider):
    """
    Anthropic Claude API provider.

    Supports Claude 3 family: Opus, Sonnet, Haiku.
    """

    MODELS = [
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229",
        "claude-3-sonnet-20240229",
        "claude-3-haiku-20240307",
    ]

    DEFAULT_MODEL = "claude-3-5-sonnet-20241022"

    def __init__(self, config: LLMConfig | None = None):
        """
        Initialize Anthropic provider.

        Args:
            config: Optional configuration. If not provided, uses defaults
                   and ANTHROPIC_API_KEY environment variable.
        """
        if config is None:
            config = LLMConfig(
                api_key=os.environ.get("ANTHROPIC_API_KEY"),
                model=self.DEFAULT_MODEL,
            )

        super().__init__(config)

        self._client: Any = None
        if ANTHROPIC_AVAILABLE and self.config.api_key:
            self._client = anthropic.Anthropic(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
                timeout=self.config.timeout_seconds,
                max_retries=self.config.max_retries,
            )

    @property
    def name(self) -> str:
        return "Anthropic"

    @property
    def available_models(self) -> list[str]:
        return self.MODELS

    @property
    def default_model(self) -> str:
        return self.DEFAULT_MODEL

    def is_available(self) -> bool:
        """Check if Anthropic API is available."""
        return ANTHROPIC_AVAILABLE and self._client is not None

    def complete(
        self,
        messages: list[LLMMessage],
        **kwargs: Any,
    ) -> LLMResponse:
        """
        Generate a completion using Claude.

        Args:
            messages: List of messages in the conversation.
            **kwargs: Additional options (model, max_tokens, temperature, etc.)

        Returns:
            LLMResponse with the completion.
        """
        if not self.is_available():
            raise RuntimeError(
                "Anthropic provider not available. Install with: pip install anthropic"
            )

        # Extract system message if present
        system_content = None
        api_messages = []

        for msg in messages:
            if msg.role == LLMRole.SYSTEM:
                system_content = (
                    msg.content if isinstance(msg.content, str) else msg.content[0].text
                )
            else:
                api_messages.append(
                    {
                        "role": msg.role.value,
                        "content": msg.content
                        if isinstance(msg.content, str)
                        else msg.content[0].text,
                    }
                )

        # Build request
        model = kwargs.get("model", self.config.model or self.DEFAULT_MODEL)
        max_tokens = kwargs.get("max_tokens", self.config.max_tokens)
        temperature = kwargs.get("temperature", self.config.temperature)

        request_kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": api_messages,
        }

        if system_content:
            request_kwargs["system"] = system_content

        if temperature is not None:
            request_kwargs["temperature"] = temperature

        # Make request
        start_time = time.time()

        response = self._client.messages.create(**request_kwargs)

        latency_ms = (time.time() - start_time) * 1000

        # Extract content
        content = ""
        if response.content:
            content = response.content[0].text

        return LLMResponse(
            content=content,
            model=response.model,
            provider=self.name,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            total_tokens=response.usage.input_tokens + response.usage.output_tokens,
            latency_ms=latency_ms,
            finish_reason=response.stop_reason,
            raw_response=response.model_dump() if hasattr(response, "model_dump") else {},
        )


def create_anthropic_provider(
    api_key: str | None = None,
    model: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.7,
) -> AnthropicProvider:
    """
    Create an Anthropic provider with the given settings.

    Args:
        api_key: API key (defaults to ANTHROPIC_API_KEY env var).
        model: Model to use (defaults to claude-3-5-sonnet).
        max_tokens: Maximum tokens to generate.
        temperature: Sampling temperature.

    Returns:
        Configured AnthropicProvider.
    """
    config = LLMConfig(
        api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"),
        model=model or AnthropicProvider.DEFAULT_MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return AnthropicProvider(config)
