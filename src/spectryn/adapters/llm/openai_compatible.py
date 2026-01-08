"""
OpenAI-Compatible Provider - Support for OpenAI API-compatible servers.

Supports local and cloud servers that implement the OpenAI API:
- LM Studio (https://lmstudio.ai)
- LocalAI (https://localai.io)
- vLLM (https://vllm.ai)
- Text Generation WebUI (with OpenAI extension)
- Anyscale, Together.ai, etc.

Uses HTTP directly to avoid OpenAI SDK dependency for local use.
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


class OpenAICompatibleProvider(LLMProvider):
    """
    OpenAI API-compatible provider.

    Works with any server implementing the OpenAI chat completions API:
    - LM Studio: http://localhost:1234/v1
    - LocalAI: http://localhost:8080/v1
    - vLLM: http://localhost:8000/v1
    - Text Generation WebUI: http://localhost:5000/v1
    """

    DEFAULT_BASE_URL = "http://localhost:1234/v1"
    DEFAULT_MODEL = "local-model"

    def __init__(self, config: LLMConfig | None = None):
        """
        Initialize OpenAI-compatible provider.

        Args:
            config: Configuration with:
                   - base_url: Server URL (e.g., http://localhost:1234/v1)
                   - model: Model name (often just "local-model" for LM Studio)
                   - api_key: Optional API key (not needed for most local servers)
        """
        if config is None:
            config = LLMConfig(
                base_url=os.environ.get("OPENAI_COMPATIBLE_URL", self.DEFAULT_BASE_URL),
                model=os.environ.get("OPENAI_COMPATIBLE_MODEL", self.DEFAULT_MODEL),
                api_key=os.environ.get("OPENAI_COMPATIBLE_API_KEY"),
            )

        super().__init__(config)

        self._base_url = config.base_url or self.DEFAULT_BASE_URL
        # Ensure URL ends with /v1 if not present
        if not self._base_url.endswith("/v1"):
            self._base_url = self._base_url.rstrip("/") + "/v1"

        self._api_key = config.api_key
        self._available_models: list[str] | None = None
        self._server_name: str | None = None

    @property
    def name(self) -> str:
        if self._server_name:
            return f"OpenAI-Compatible ({self._server_name})"
        return "OpenAI-Compatible"

    @property
    def available_models(self) -> list[str]:
        """Get list of available models from the server."""
        if self._available_models is None:
            self._available_models = self._fetch_models()
        return self._available_models or [self.DEFAULT_MODEL]

    @property
    def default_model(self) -> str:
        return self.config.model or self.DEFAULT_MODEL

    def set_server_name(self, name: str) -> None:
        """Set a friendly name for this server (e.g., 'LM Studio')."""
        self._server_name = name

    def is_available(self) -> bool:
        """Check if the OpenAI-compatible server is accessible."""
        try:
            req = urllib.request.Request(
                f"{self._base_url}/models",
                method="GET",
            )
            if self._api_key:
                req.add_header("Authorization", f"Bearer {self._api_key}")
            with urllib.request.urlopen(req, timeout=5) as response:
                return bool(response.status == 200)
        except (urllib.error.URLError, TimeoutError, OSError):
            return False

    def _fetch_models(self) -> list[str]:
        """Fetch available models from the server."""
        try:
            req = urllib.request.Request(
                f"{self._base_url}/models",
                method="GET",
            )
            if self._api_key:
                req.add_header("Authorization", f"Bearer {self._api_key}")

            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
                models = data.get("data", [])
                return [m.get("id", "") for m in models if m.get("id")]
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
            self.logger.debug(f"Failed to fetch models from {self._base_url}: {e}")
            return []

    def complete(
        self,
        messages: list[LLMMessage],
        **kwargs: Any,
    ) -> LLMResponse:
        """
        Generate a completion using the OpenAI-compatible API.

        Args:
            messages: List of messages in the conversation.
            **kwargs: Additional options (model, max_tokens, temperature, etc.)

        Returns:
            LLMResponse with the completion.
        """
        if not self.is_available():
            raise RuntimeError(
                f"OpenAI-compatible server not available at {self._base_url}. "
                "Ensure your local server is running (LM Studio, LocalAI, vLLM, etc.)"
            )

        # Convert messages to OpenAI format
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

        request_data: dict[str, Any] = {
            "model": model,
            "messages": api_messages,
        }

        if "max_tokens" in kwargs or self.config.max_tokens:
            request_data["max_tokens"] = kwargs.get("max_tokens", self.config.max_tokens)

        if "temperature" in kwargs or self.config.temperature:
            request_data["temperature"] = kwargs.get("temperature", self.config.temperature)

        if self.config.top_p:
            request_data["top_p"] = self.config.top_p

        # Make request
        start_time = time.time()

        try:
            req = urllib.request.Request(
                f"{self._base_url}/chat/completions",
                data=json.dumps(request_data).encode("utf-8"),
                method="POST",
            )
            req.add_header("Content-Type", "application/json")
            if self._api_key:
                req.add_header("Authorization", f"Bearer {self._api_key}")

            timeout = self.config.timeout_seconds or 120
            with urllib.request.urlopen(req, timeout=timeout) as response:
                data = json.loads(response.read().decode())
        except urllib.error.URLError as e:
            raise RuntimeError(f"Request to {self._base_url} failed: {e}")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Invalid response from server: {e}")

        latency_ms = (time.time() - start_time) * 1000

        # Extract content (OpenAI format)
        content = ""
        finish_reason = None
        choices = data.get("choices", [])
        if choices:
            message = choices[0].get("message", {})
            content = message.get("content", "")
            finish_reason = choices[0].get("finish_reason")

        # Token usage
        usage = data.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)

        return LLMResponse(
            content=content,
            model=data.get("model", model),
            provider=self.name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            latency_ms=latency_ms,
            finish_reason=finish_reason,
            raw_response=data,
        )


def create_openai_compatible_provider(
    base_url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.7,
    server_name: str | None = None,
) -> OpenAICompatibleProvider:
    """
    Create an OpenAI-compatible provider for local LLM servers.

    Args:
        base_url: Server URL (defaults to http://localhost:1234/v1 for LM Studio).
        model: Model name (often "local-model" for local servers).
        api_key: Optional API key.
        max_tokens: Maximum tokens to generate.
        temperature: Sampling temperature.
        server_name: Friendly name for the server (e.g., 'LM Studio').

    Returns:
        Configured OpenAICompatibleProvider.

    Examples:
        # LM Studio
        provider = create_openai_compatible_provider(
            base_url="http://localhost:1234/v1",
            server_name="LM Studio",
        )

        # LocalAI
        provider = create_openai_compatible_provider(
            base_url="http://localhost:8080/v1",
            model="gpt-3.5-turbo",
            server_name="LocalAI",
        )

        # vLLM
        provider = create_openai_compatible_provider(
            base_url="http://localhost:8000/v1",
            model="meta-llama/Llama-2-7b-chat-hf",
            server_name="vLLM",
        )
    """
    config = LLMConfig(
        base_url=base_url
        or os.environ.get("OPENAI_COMPATIBLE_URL", OpenAICompatibleProvider.DEFAULT_BASE_URL),
        model=model
        or os.environ.get("OPENAI_COMPATIBLE_MODEL", OpenAICompatibleProvider.DEFAULT_MODEL),
        api_key=api_key or os.environ.get("OPENAI_COMPATIBLE_API_KEY"),
        max_tokens=max_tokens,
        temperature=temperature,
    )

    provider = OpenAICompatibleProvider(config)
    if server_name:
        provider.set_server_name(server_name)

    return provider


# Convenience factory functions for popular servers


def create_lm_studio_provider(
    model: str = "local-model",
    port: int = 1234,
    **kwargs: Any,
) -> OpenAICompatibleProvider:
    """
    Create a provider for LM Studio.

    Args:
        model: Model name (default: local-model).
        port: LM Studio port (default: 1234).
        **kwargs: Additional options passed to create_openai_compatible_provider.

    Returns:
        Configured provider for LM Studio.
    """
    return create_openai_compatible_provider(
        base_url=f"http://localhost:{port}/v1",
        model=model,
        server_name="LM Studio",
        **kwargs,
    )


def create_local_ai_provider(
    model: str = "gpt-3.5-turbo",
    port: int = 8080,
    **kwargs: Any,
) -> OpenAICompatibleProvider:
    """
    Create a provider for LocalAI.

    Args:
        model: Model name (default: gpt-3.5-turbo).
        port: LocalAI port (default: 8080).
        **kwargs: Additional options passed to create_openai_compatible_provider.

    Returns:
        Configured provider for LocalAI.
    """
    return create_openai_compatible_provider(
        base_url=f"http://localhost:{port}/v1",
        model=model,
        server_name="LocalAI",
        **kwargs,
    )


def create_vllm_provider(
    model: str,
    port: int = 8000,
    **kwargs: Any,
) -> OpenAICompatibleProvider:
    """
    Create a provider for vLLM.

    Args:
        model: Model name (e.g., "meta-llama/Llama-2-7b-chat-hf").
        port: vLLM port (default: 8000).
        **kwargs: Additional options passed to create_openai_compatible_provider.

    Returns:
        Configured provider for vLLM.
    """
    return create_openai_compatible_provider(
        base_url=f"http://localhost:{port}/v1",
        model=model,
        server_name="vLLM",
        **kwargs,
    )
