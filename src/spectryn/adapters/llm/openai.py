"""
OpenAI Provider - Native OpenAI API integration.

Requires: pip install openai
"""

import os
import time
from typing import Any

from .base import LLMConfig, LLMMessage, LLMProvider, LLMResponse


# Try to import openai
try:
    import openai

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    openai = None  # type: ignore


class OpenAIProvider(LLMProvider):
    """
    OpenAI API provider.

    Supports GPT-4, GPT-4 Turbo, GPT-3.5 Turbo.
    """

    MODELS = [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "gpt-4-turbo-preview",
        "gpt-4",
        "gpt-3.5-turbo",
        "gpt-3.5-turbo-16k",
    ]

    DEFAULT_MODEL = "gpt-4o-mini"

    def __init__(self, config: LLMConfig | None = None):
        """
        Initialize OpenAI provider.

        Args:
            config: Optional configuration. If not provided, uses defaults
                   and OPENAI_API_KEY environment variable.
        """
        if config is None:
            config = LLMConfig(
                api_key=os.environ.get("OPENAI_API_KEY"),
                model=self.DEFAULT_MODEL,
            )

        super().__init__(config)

        self._client: Any = None
        if OPENAI_AVAILABLE and self.config.api_key:
            client_kwargs: dict[str, Any] = {
                "api_key": self.config.api_key,
                "timeout": self.config.timeout_seconds,
                "max_retries": self.config.max_retries,
            }
            if self.config.base_url:
                client_kwargs["base_url"] = self.config.base_url

            self._client = openai.OpenAI(**client_kwargs)

    @property
    def name(self) -> str:
        return "OpenAI"

    @property
    def available_models(self) -> list[str]:
        return self.MODELS

    @property
    def default_model(self) -> str:
        return self.DEFAULT_MODEL

    def is_available(self) -> bool:
        """Check if OpenAI API is available."""
        return OPENAI_AVAILABLE and self._client is not None

    def complete(
        self,
        messages: list[LLMMessage],
        **kwargs: Any,
    ) -> LLMResponse:
        """
        Generate a completion using GPT.

        Args:
            messages: List of messages in the conversation.
            **kwargs: Additional options (model, max_tokens, temperature, etc.)

        Returns:
            LLMResponse with the completion.
        """
        if not self.is_available():
            raise RuntimeError("OpenAI provider not available. Install with: pip install openai")

        # Convert messages
        api_messages = []
        for msg in messages:
            content = msg.content if isinstance(msg.content, str) else msg.content[0].text
            api_messages.append(
                {
                    "role": msg.role.value,
                    "content": content,
                }
            )

        # Build request
        model = kwargs.get("model", self.config.model or self.DEFAULT_MODEL)
        max_tokens = kwargs.get("max_tokens", self.config.max_tokens)
        temperature = kwargs.get("temperature", self.config.temperature)

        request_kwargs: dict[str, Any] = {
            "model": model,
            "messages": api_messages,
        }

        if max_tokens:
            request_kwargs["max_tokens"] = max_tokens

        if temperature is not None:
            request_kwargs["temperature"] = temperature

        # Make request
        start_time = time.time()

        response = self._client.chat.completions.create(**request_kwargs)

        latency_ms = (time.time() - start_time) * 1000

        # Extract content
        content = ""
        if response.choices:
            content = response.choices[0].message.content or ""

        # Token usage
        input_tokens = 0
        output_tokens = 0
        if response.usage:
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens

        return LLMResponse(
            content=content,
            model=response.model,
            provider=self.name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            latency_ms=latency_ms,
            finish_reason=response.choices[0].finish_reason if response.choices else None,
            raw_response=response.model_dump() if hasattr(response, "model_dump") else {},
        )


def create_openai_provider(
    api_key: str | None = None,
    model: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.7,
    base_url: str | None = None,
) -> OpenAIProvider:
    """
    Create an OpenAI provider with the given settings.

    Args:
        api_key: API key (defaults to OPENAI_API_KEY env var).
        model: Model to use (defaults to gpt-4o-mini).
        max_tokens: Maximum tokens to generate.
        temperature: Sampling temperature.
        base_url: Custom base URL (for Azure, local proxies, etc.).

    Returns:
        Configured OpenAIProvider.
    """
    config = LLMConfig(
        api_key=api_key or os.environ.get("OPENAI_API_KEY"),
        model=model or OpenAIProvider.DEFAULT_MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        base_url=base_url,
    )
    return OpenAIProvider(config)
