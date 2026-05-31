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
from .gemini_adapter import GeminiAdapter

# provider name -> adapter class
REGISTRY: dict[str, type[Adapter]] = {
    # Native adapters
    "openai": OpenAIAdapter,
    "anthropic": AnthropicAdapter,
    "gemini": GeminiAdapter,
    # OpenAI-compatible providers reuse the OpenAI adapter with a custom base_url.
    "deepseek": OpenAIAdapter,
    "qwen": OpenAIAdapter,
    "moonshot": OpenAIAdapter,        # Kimi
    "zhipu": OpenAIAdapter,           # GLM / 智谱
    "minimax": OpenAIAdapter,
    "baichuan": OpenAIAdapter,
    "yi": OpenAIAdapter,              # 01.AI / 零一万物
    "stepfun": OpenAIAdapter,        # 阶跃星辰
    "mistral": OpenAIAdapter,
    "groq": OpenAIAdapter,
    "together": OpenAIAdapter,
    "fireworks": OpenAIAdapter,
    "deepinfra": OpenAIAdapter,
    "perplexity": OpenAIAdapter,
    "xai": OpenAIAdapter,            # Grok
    "openrouter": OpenAIAdapter,     # 400+ models behind one key
    "ollama": OpenAIAdapter,         # local models
    "lmstudio": OpenAIAdapter,       # local models
    "openai-compatible": OpenAIAdapter,
}

# Sensible default base URLs for OpenAI-compatible providers.
BASE_URLS: dict[str, str] = {
    "deepseek": "https://api.deepseek.com",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "moonshot": "https://api.moonshot.cn/v1",
    "zhipu": "https://open.bigmodel.cn/api/paas/v4",
    "minimax": "https://api.minimax.chat/v1",
    "baichuan": "https://api.baichuan-ai.com/v1",
    "yi": "https://api.lingyiwanwu.com/v1",
    "stepfun": "https://api.stepfun.com/v1",
    "mistral": "https://api.mistral.ai/v1",
    "groq": "https://api.groq.com/openai/v1",
    "together": "https://api.together.xyz/v1",
    "fireworks": "https://api.fireworks.ai/inference/v1",
    "deepinfra": "https://api.deepinfra.com/v1/openai",
    "perplexity": "https://api.perplexity.ai",
    "xai": "https://api.x.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "ollama": "http://localhost:11434/v1",
    "lmstudio": "http://localhost:1234/v1",
}

# Provider -> env var name to read the API key from (falls back to RECALL_API_KEY).
KEY_ENV: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "qwen": "DASHSCOPE_API_KEY",
    "moonshot": "MOONSHOT_API_KEY",
    "zhipu": "ZHIPU_API_KEY",
    "minimax": "MINIMAX_API_KEY",
    "baichuan": "BAICHUAN_API_KEY",
    "yi": "YI_API_KEY",
    "stepfun": "STEPFUN_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "groq": "GROQ_API_KEY",
    "together": "TOGETHER_API_KEY",
    "fireworks": "FIREWORKS_API_KEY",
    "deepinfra": "DEEPINFRA_API_KEY",
    "perplexity": "PERPLEXITY_API_KEY",
    "xai": "XAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "ollama": "OLLAMA_API_KEY",      # usually unused; ollama ignores it
    "lmstudio": "LMSTUDIO_API_KEY",  # usually unused
}


def register(
    name: str,
    adapter_cls: type[Adapter],
    base_url: str | None = None,
    key_env: str | None = None,
) -> None:
    """Register a custom adapter at runtime so `recall chat <name> ...` works.

    Third parties can also ship adapters as a package and expose them under the
    ``recall.adapters`` entry-point group (entry name = provider key, value = an
    Adapter subclass, optionally with ``BASE_URL`` / ``KEY_ENV`` class attrs);
    those load automatically on import.
    """
    name = name.lower()
    REGISTRY[name] = adapter_cls
    if base_url:
        BASE_URLS[name] = base_url
    if key_env:
        KEY_ENV[name] = key_env


def _load_plugins() -> None:
    """Discover and register adapters published under the `recall.adapters`
    entry-point group. Never raises — a broken plugin is skipped."""
    try:
        from importlib.metadata import entry_points
    except ImportError:  # pragma: no cover
        return
    try:
        eps = entry_points(group="recall.adapters")
    except TypeError:  # Python < 3.10: entry_points() returns a dict
        eps = entry_points().get("recall.adapters", [])
    for ep in eps:
        try:
            obj = ep.load()
            register(
                ep.name, obj,
                base_url=getattr(obj, "BASE_URL", None),
                key_env=getattr(obj, "KEY_ENV", None),
            )
        except Exception:  # noqa: BLE001 — a bad plugin must not break recall
            continue


def get_adapter(provider: str, model: str, **kwargs) -> Adapter:
    provider = provider.lower()
    if provider not in REGISTRY:
        raise ValueError(
            f"Unknown provider '{provider}'. Supported: {', '.join(sorted(REGISTRY))}"
        )
    if provider in BASE_URLS and not kwargs.get("base_url"):
        kwargs["base_url"] = BASE_URLS[provider]
    # Resolve the provider-specific API key env var if no key was passed.
    if not kwargs.get("api_key"):
        import os

        env_name = KEY_ENV.get(provider)
        if env_name:
            kwargs["api_key"] = os.environ.get(env_name) or os.environ.get("RECALL_API_KEY")
    return REGISTRY[provider](model=model, **kwargs)


__all__ = [
    "Adapter",
    "ChatResult",
    "get_adapter",
    "register",
    "REGISTRY",
    "BASE_URLS",
    "KEY_ENV",
]

# Load third-party adapter plugins (no-op if none installed).
_load_plugins()
