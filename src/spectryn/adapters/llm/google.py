"""
Google Gemini Provider - Native Google AI API integration.

Requires: pip install google-generativeai
"""

import os
import time
from typing import Any

from .base import LLMConfig, LLMMessage, LLMProvider, LLMResponse, LLMRole


# Try to import google generativeai
try:
    import google.generativeai as genai

    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False
    genai = None  # type: ignore


class GoogleProvider(LLMProvider):
    """
    Google Gemini API provider.

    Supports Gemini 1.5 Pro, Gemini 1.5 Flash.
    """

    MODELS = [
        "gemini-1.5-pro",
        "gemini-1.5-flash",
        "gemini-1.5-flash-8b",
        "gemini-1.0-pro",
    ]

    DEFAULT_MODEL = "gemini-1.5-flash"

    def __init__(self, config: LLMConfig | None = None):
        """
        Initialize Google provider.

        Args:
            config: Optional configuration. If not provided, uses defaults
                   and GOOGLE_API_KEY environment variable.
        """
        if config is None:
            config = LLMConfig(
                api_key=os.environ.get("GOOGLE_API_KEY"),
                model=self.DEFAULT_MODEL,
            )

        super().__init__(config)

        self._model: Any = None
        if GOOGLE_AVAILABLE and self.config.api_key:
            genai.configure(api_key=self.config.api_key)
            model_name = self.config.model or self.DEFAULT_MODEL
            self._model = genai.GenerativeModel(model_name)

    @property
    def name(self) -> str:
        return "Google"

    @property
    def available_models(self) -> list[str]:
        return self.MODELS

    @property
    def default_model(self) -> str:
        return self.DEFAULT_MODEL

    def is_available(self) -> bool:
        """Check if Google API is available."""
        return GOOGLE_AVAILABLE and self._model is not None

    def complete(
        self,
        messages: list[LLMMessage],
        **kwargs: Any,
    ) -> LLMResponse:
        """
        Generate a completion using Gemini.

        Args:
            messages: List of messages in the conversation.
            **kwargs: Additional options (max_tokens, temperature, etc.)

        Returns:
            LLMResponse with the completion.
        """
        if not self.is_available():
            raise RuntimeError(
                "Google provider not available. Install with: pip install google-generativeai"
            )

        # Build conversation
        # Gemini uses a different format: alternate user/model messages
        system_instruction = None
        contents = []

        for msg in messages:
            if msg.role == LLMRole.SYSTEM:
                system_instruction = (
                    msg.content if isinstance(msg.content, str) else msg.content[0].text
                )
            elif msg.role == LLMRole.USER:
                content = msg.content if isinstance(msg.content, str) else msg.content[0].text
                contents.append({"role": "user", "parts": [content]})
            elif msg.role == LLMRole.ASSISTANT:
                content = msg.content if isinstance(msg.content, str) else msg.content[0].text
                contents.append({"role": "model", "parts": [content]})

        # Create model with system instruction if provided
        model = kwargs.get("model", self.config.model or self.DEFAULT_MODEL)

        if system_instruction:
            generation_model = genai.GenerativeModel(model, system_instruction=system_instruction)
        else:
            generation_model = self._model

        # Generation config
        generation_config = genai.GenerationConfig(
            max_output_tokens=kwargs.get("max_tokens", self.config.max_tokens),
            temperature=kwargs.get("temperature", self.config.temperature),
        )

        # Make request
        start_time = time.time()

        response = generation_model.generate_content(contents, generation_config=generation_config)

        latency_ms = (time.time() - start_time) * 1000

        # Extract content
        content = ""
        if response.text:
            content = response.text

        # Token usage (if available)
        input_tokens = 0
        output_tokens = 0
        if hasattr(response, "usage_metadata"):
            input_tokens = getattr(response.usage_metadata, "prompt_token_count", 0)
            output_tokens = getattr(response.usage_metadata, "candidates_token_count", 0)

        return LLMResponse(
            content=content,
            model=model,
            provider=self.name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            latency_ms=latency_ms,
            finish_reason="stop",
        )


def create_google_provider(
    api_key: str | None = None,
    model: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.7,
) -> GoogleProvider:
    """
    Create a Google provider with the given settings.

    Args:
        api_key: API key (defaults to GOOGLE_API_KEY env var).
        model: Model to use (defaults to gemini-1.5-flash).
        max_tokens: Maximum tokens to generate.
        temperature: Sampling temperature.

    Returns:
        Configured GoogleProvider.
    """
    config = LLMConfig(
        api_key=api_key or os.environ.get("GOOGLE_API_KEY"),
        model=model or GoogleProvider.DEFAULT_MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return GoogleProvider(config)
