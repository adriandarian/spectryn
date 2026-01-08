"""
LLM Adapters - Native integrations with AI providers.

This module provides direct API integrations with:

**Cloud Providers** (require API keys):
- Anthropic (Claude 3.5 Sonnet, Claude 3 Opus)
- OpenAI (GPT-4o, GPT-4, GPT-3.5)
- Google (Gemini 1.5 Pro, Gemini 1.5 Flash)

**Local Providers** (no API keys required):
- Ollama (Llama, Mistral, CodeLlama, Phi, etc.)
- OpenAI-compatible servers (LM Studio, LocalAI, vLLM)

Usage:
    from spectryn.adapters.llm import create_llm_manager

    # Auto-detect available providers
    manager = create_llm_manager()

    # Prefer local models
    manager = create_llm_manager(prefer_local=True)

    # Use specific Ollama model
    manager = create_llm_manager(
        ollama_model="codellama",
        prefer_provider="ollama",
    )
"""

from .base import (
    LLMConfig,
    LLMMessage,
    LLMProvider,
    LLMResponse,
    LLMRole,
    MessageContent,
)
from .manager import (
    LLMManager,
    LLMManagerConfig,
    ProviderName,
    create_llm_manager,
)
from .registry import (
    LLMRegistry,
    ProviderInfo,
    ProviderType,
    create_provider,
    get_registry,
    list_all_providers,
    register_provider,
)


__all__ = [
    "LLMConfig",
    "LLMManager",
    "LLMManagerConfig",
    "LLMMessage",
    "LLMProvider",
    "LLMRegistry",
    "LLMResponse",
    "LLMRole",
    "MessageContent",
    "ProviderInfo",
    "ProviderName",
    "ProviderType",
    "create_llm_manager",
    "create_provider",
    "get_registry",
    "list_all_providers",
    "register_provider",
]

# Cloud providers (optional, require SDKs)
try:
    from .anthropic import AnthropicProvider, create_anthropic_provider

    __all__.extend(["AnthropicProvider", "create_anthropic_provider"])
except ImportError:
    pass

try:
    from .openai import OpenAIProvider, create_openai_provider

    __all__.extend(["OpenAIProvider", "create_openai_provider"])
except ImportError:
    pass

try:
    from .google import GoogleProvider, create_google_provider

    __all__.extend(["GoogleProvider", "create_google_provider"])
except ImportError:
    pass

# Local providers (no external dependencies)
from .ollama import OllamaProvider, create_ollama_provider
from .openai_compatible import (
    OpenAICompatibleProvider,
    create_lm_studio_provider,
    create_local_ai_provider,
    create_openai_compatible_provider,
    create_vllm_provider,
)


__all__.extend(
    [
        "OllamaProvider",
        "OpenAICompatibleProvider",
        "create_lm_studio_provider",
        "create_local_ai_provider",
        "create_ollama_provider",
        "create_openai_compatible_provider",
        "create_vllm_provider",
    ]
)
