"""
Base LLM Provider - Abstract interfaces for LLM integrations.

Defines the common interface and data structures for all LLM providers.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


logger = logging.getLogger(__name__)


class LLMRole(Enum):
    """Message roles in a conversation."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class MessageContent:
    """Content of a message (text or other types)."""

    type: str = "text"
    text: str = ""
    # For image inputs (future)
    image_url: str | None = None
    image_base64: str | None = None


@dataclass
class LLMMessage:
    """A message in a conversation."""

    role: LLMRole
    content: str | list[MessageContent]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API calls."""
        if isinstance(self.content, str):
            return {"role": self.role.value, "content": self.content}
        return {
            "role": self.role.value,
            "content": [c.__dict__ for c in self.content],
        }


@dataclass
class LLMResponse:
    """Response from an LLM provider."""

    content: str
    model: str
    provider: str

    # Token usage
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    # Timing
    latency_ms: float = 0
    timestamp: datetime = field(default_factory=datetime.now)

    # Metadata
    finish_reason: str | None = None
    raw_response: dict[str, Any] = field(default_factory=dict)

    @property
    def cost_estimate(self) -> float:
        """Estimate cost based on token usage (approximate)."""
        # Very rough estimates per 1M tokens
        cost_per_million = {
            "claude-3-opus": (15.0, 75.0),  # input, output
            "claude-3-sonnet": (3.0, 15.0),
            "claude-3-haiku": (0.25, 1.25),
            "claude-3-5-sonnet": (3.0, 15.0),
            "gpt-4o": (2.5, 10.0),
            "gpt-4o-mini": (0.15, 0.6),
            "gpt-4-turbo": (10.0, 30.0),
            "gpt-4": (30.0, 60.0),
            "gpt-3.5-turbo": (0.5, 1.5),
            "gemini-1.5-pro": (1.25, 5.0),
            "gemini-1.5-flash": (0.075, 0.3),
        }

        for model_prefix, (input_cost, output_cost) in cost_per_million.items():
            if model_prefix in self.model.lower():
                input_price = (self.input_tokens / 1_000_000) * input_cost
                output_price = (self.output_tokens / 1_000_000) * output_cost
                return input_price + output_price

        return 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "content": self.content,
            "model": self.model,
            "provider": self.provider,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp.isoformat(),
            "finish_reason": self.finish_reason,
        }


@dataclass
class LLMConfig:
    """Configuration for an LLM provider."""

    # API settings
    api_key: str | None = None
    base_url: str | None = None

    # Model settings
    model: str = ""
    max_tokens: int = 4096
    temperature: float = 0.7
    top_p: float = 1.0

    # Behavior
    timeout_seconds: float = 60.0
    max_retries: int = 3
    retry_delay: float = 1.0

    # System prompt
    system_prompt: str | None = None


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, config: LLMConfig):
        """
        Initialize the LLM provider.

        Args:
            config: Provider configuration.
        """
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'Anthropic', 'OpenAI')."""
        ...

    @property
    @abstractmethod
    def available_models(self) -> list[str]:
        """List of available models for this provider."""
        ...

    @property
    @abstractmethod
    def default_model(self) -> str:
        """Default model to use."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is available (API key set, etc.)."""
        ...

    @abstractmethod
    def complete(
        self,
        messages: list[LLMMessage],
        **kwargs: Any,
    ) -> LLMResponse:
        """
        Generate a completion for the given messages.

        Args:
            messages: List of messages in the conversation.
            **kwargs: Additional provider-specific options.

        Returns:
            LLMResponse with the completion.
        """
        ...

    def prompt(
        self,
        user_message: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """
        Simple single-turn prompt.

        Args:
            user_message: The user's message.
            system_prompt: Optional system prompt.
            **kwargs: Additional options.

        Returns:
            LLMResponse with the completion.
        """
        messages = []

        # Add system prompt
        system = system_prompt or self.config.system_prompt
        if system:
            messages.append(LLMMessage(role=LLMRole.SYSTEM, content=system))

        # Add user message
        messages.append(LLMMessage(role=LLMRole.USER, content=user_message))

        return self.complete(messages, **kwargs)

    def chat(
        self,
        messages: list[tuple[str, str]],
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """
        Multi-turn chat convenience method.

        Args:
            messages: List of (role, content) tuples.
            system_prompt: Optional system prompt.
            **kwargs: Additional options.

        Returns:
            LLMResponse with the completion.
        """
        llm_messages = []

        # Add system prompt
        system = system_prompt or self.config.system_prompt
        if system:
            llm_messages.append(LLMMessage(role=LLMRole.SYSTEM, content=system))

        # Add conversation messages
        for role, content in messages:
            llm_role = LLMRole(role) if role in ("user", "assistant", "system") else LLMRole.USER
            llm_messages.append(LLMMessage(role=llm_role, content=content))

        return self.complete(llm_messages, **kwargs)
