"""Model adapter registry.

A unified, minimal interface across providers so recall can attach memory and
observability to any model. Each adapter returns (text, input_tokens,
output_tokens). Adapters import their SDK lazily so the base install stays
dependency-free.
"""

from __future__ import annotations

from .base import Adapter, ChatResult
from .openai_adapter import OpenAIAdapter
from .anthropic_adapter import AnthropicAdapter

# provider name -> adapter class
REGISTRY: dict[str, type[Adapter]] = {
    "openai": OpenAIAdapter,
    "anthropic": AnthropicAdapter,
    # OpenAI-compatible providers reuse the OpenAI adapter with a custom base_url.
    "deepseek": OpenAIAdapter,
    "qwen": OpenAIAdapter,
    "openai-compatible": OpenAIAdapter,
}

# Sensible default base URLs for OpenAI-compatible providers.
BASE_URLS: dict[str, str] = {
    "deepseek": "https://api.deepseek.com",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
}


def get_adapter(provider: str, model: str, **kwargs) -> Adapter:
    provider = provider.lower()
    if provider not in REGISTRY:
        raise ValueError(
            f"Unknown provider '{provider}'. Supported: {', '.join(sorted(REGISTRY))}"
        )
    if provider in BASE_URLS and "base_url" not in kwargs:
        kwargs["base_url"] = BASE_URLS[provider]
    return REGISTRY[provider](model=model, **kwargs)


__all__ = ["Adapter", "ChatResult", "get_adapter", "REGISTRY", "BASE_URLS"]
