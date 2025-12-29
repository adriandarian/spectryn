"""
Ollama Provider - Local LLM integration via Ollama.

Ollama runs local LLMs like Llama, Mistral, CodeLlama, etc.
See: https://ollama.ai

No external dependencies required - uses HTTP API directly.
"""

import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any

from .base import LLMConfig, LLMMessage, LLMProvider, LLMResponse


logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """
    Ollama local LLM provider.

    Supports any model available in Ollama:
    - llama3.2, llama3.1, llama3
    - mistral, mixtral
    - codellama, deepseek-coder
    - phi3, gemma2, qwen2.5
    - And many more via `ollama pull <model>`

    By default connects to http://localhost:11434
    """

    # Popular models - these are suggestions, any Ollama model works
    POPULAR_MODELS = [
        "llama3.2",
        "llama3.2:1b",
        "llama3.1",
        "llama3.1:70b",
        "mistral",
        "mixtral",
        "codellama",
        "deepseek-coder",
        "phi3",
        "gemma2",
        "qwen2.5-coder",
    ]

    DEFAULT_MODEL = "llama3.2"
    DEFAULT_BASE_URL = "http://localhost:11434"

    def __init__(self, config: LLMConfig | None = None):
        """
        Initialize Ollama provider.

        Args:
            config: Optional configuration. Uses defaults if not provided.
                   - base_url defaults to http://localhost:11434
                   - model defaults to llama3.2
                   - api_key is not needed (local)
        """
        if config is None:
            config = LLMConfig(
                base_url=os.environ.get("OLLAMA_HOST", self.DEFAULT_BASE_URL),
                model=os.environ.get("OLLAMA_MODEL", self.DEFAULT_MODEL),
            )
        elif not config.base_url:
            config.base_url = os.environ.get("OLLAMA_HOST", self.DEFAULT_BASE_URL)

        super().__init__(config)

        self._base_url = config.base_url or self.DEFAULT_BASE_URL
        # Remove trailing slash if present
        self._base_url = self._base_url.rstrip("/")
        self._available_models: list[str] | None = None

    @property
    def name(self) -> str:
        return "Ollama"

    @property
    def available_models(self) -> list[str]:
        """Get list of models available in Ollama."""
        if self._available_models is None:
            self._available_models = self._fetch_models()
        return self._available_models or self.POPULAR_MODELS

    @property
    def default_model(self) -> str:
        return self.DEFAULT_MODEL

    def is_available(self) -> bool:
        """Check if Ollama is running and accessible."""
        try:
            req = urllib.request.Request(
                f"{self._base_url}/api/tags",
                method="GET",
            )
            req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, timeout=5) as response:
                return bool(response.status == 200)
        except (urllib.error.URLError, TimeoutError, OSError):
            return False

    def _fetch_models(self) -> list[str]:
        """Fetch available models from Ollama."""
        try:
            req = urllib.request.Request(
                f"{self._base_url}/api/tags",
                method="GET",
            )
            req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
                models = data.get("models", [])
                return [m.get("name", "") for m in models if m.get("name")]
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
            self.logger.debug(f"Failed to fetch Ollama models: {e}")
            return []

    def complete(
        self,
        messages: list[LLMMessage],
        **kwargs: Any,
    ) -> LLMResponse:
        """
        Generate a completion using Ollama.

        Args:
            messages: List of messages in the conversation.
            **kwargs: Additional options (model, temperature, etc.)

        Returns:
            LLMResponse with the completion.
        """
        if not self.is_available():
            raise RuntimeError(
                f"Ollama not available at {self._base_url}. "
                "Install Ollama from https://ollama.ai and run: ollama serve"
            )

        # Convert messages to Ollama format
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
        options = {}

        if "temperature" in kwargs or self.config.temperature:
            options["temperature"] = kwargs.get("temperature", self.config.temperature)

        if "max_tokens" in kwargs or self.config.max_tokens:
            options["num_predict"] = kwargs.get("max_tokens", self.config.max_tokens)

        if self.config.top_p:
            options["top_p"] = self.config.top_p

        request_data = {
            "model": model,
            "messages": api_messages,
            "stream": False,
        }

        if options:
            request_data["options"] = options

        # Make request
        start_time = time.time()

        try:
            req = urllib.request.Request(
                f"{self._base_url}/api/chat",
                data=json.dumps(request_data).encode("utf-8"),
                method="POST",
            )
            req.add_header("Content-Type", "application/json")

            timeout = self.config.timeout_seconds or 120  # Local models can be slow
            with urllib.request.urlopen(req, timeout=timeout) as response:
                data = json.loads(response.read().decode())
        except urllib.error.URLError as e:
            raise RuntimeError(f"Ollama request failed: {e}")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Invalid response from Ollama: {e}")

        latency_ms = (time.time() - start_time) * 1000

        # Extract content
        content = ""
        message = data.get("message", {})
        if message:
            content = message.get("content", "")

        # Token usage (Ollama provides these)
        input_tokens = data.get("prompt_eval_count", 0)
        output_tokens = data.get("eval_count", 0)

        return LLMResponse(
            content=content,
            model=model,
            provider=self.name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            latency_ms=latency_ms,
            finish_reason=data.get("done_reason", "stop"),
            raw_response=data,
        )


def create_ollama_provider(
    model: str | None = None,
    base_url: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.7,
) -> OllamaProvider:
    """
    Create an Ollama provider with the given settings.

    Args:
        model: Model to use (defaults to llama3.2, or OLLAMA_MODEL env var).
        base_url: Ollama server URL (defaults to http://localhost:11434).
        max_tokens: Maximum tokens to generate.
        temperature: Sampling temperature.

    Returns:
        Configured OllamaProvider.
    """
    config = LLMConfig(
        base_url=base_url or os.environ.get("OLLAMA_HOST", OllamaProvider.DEFAULT_BASE_URL),
        model=model or os.environ.get("OLLAMA_MODEL", OllamaProvider.DEFAULT_MODEL),
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return OllamaProvider(config)
