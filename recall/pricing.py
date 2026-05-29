"""Per-million-token pricing (USD) for cost estimation.

These are best-effort defaults; users can override via RECALL_PRICING env var
(JSON mapping model -> {"input": x, "output": y} per 1M tokens). Pricing
changes often, so this is intentionally easy to override and never blocks a
call if a model is unknown (cost falls back to 0).
"""

from __future__ import annotations

import json
import os
from typing import Optional

# USD per 1,000,000 tokens.
DEFAULT_PRICING: dict[str, dict[str, float]] = {
    # OpenAI
    "gpt-4o": {"input": 2.5, "output": 10.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.6},
    "gpt-4.1": {"input": 2.0, "output": 8.0},
    "gpt-4.1-mini": {"input": 0.4, "output": 1.6},
    # Anthropic
    "claude-3-5-sonnet": {"input": 3.0, "output": 15.0},
    "claude-3-5-haiku": {"input": 0.8, "output": 4.0},
    "claude-3-opus": {"input": 15.0, "output": 75.0},
    # DeepSeek
    "deepseek-chat": {"input": 0.27, "output": 1.1},
    "deepseek-reasoner": {"input": 0.55, "output": 2.19},
    # Qwen (DashScope, approximate)
    "qwen-plus": {"input": 0.4, "output": 1.2},
    "qwen-max": {"input": 1.6, "output": 6.4},
    "qwen-turbo": {"input": 0.05, "output": 0.2},
    # Google Gemini
    "gemini-1.5-pro": {"input": 1.25, "output": 5.0},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.3},
    "gemini-2.0-flash": {"input": 0.1, "output": 0.4},
    # Moonshot / Kimi (approximate)
    "moonshot-v1-8k": {"input": 0.17, "output": 0.17},
    "moonshot-v1-32k": {"input": 0.34, "output": 0.34},
    "kimi": {"input": 0.17, "output": 0.17},
    # Zhipu / GLM
    "glm-4": {"input": 1.4, "output": 1.4},
    "glm-4-flash": {"input": 0.014, "output": 0.014},
    "glm-4-plus": {"input": 7.0, "output": 7.0},
    # MiniMax
    "abab6.5s": {"input": 0.14, "output": 0.14},
    # 01.AI / Yi
    "yi-large": {"input": 2.8, "output": 2.8},
    "yi-lightning": {"input": 0.14, "output": 0.14},
    # Mistral
    "mistral-large": {"input": 2.0, "output": 6.0},
    "mistral-small": {"input": 0.2, "output": 0.6},
    "open-mistral-nemo": {"input": 0.15, "output": 0.15},
    # xAI / Grok
    "grok-2": {"input": 2.0, "output": 10.0},
    "grok-beta": {"input": 5.0, "output": 15.0},
    # Groq (hosted open models, very cheap)
    "llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79},
    "llama-3.1-8b-instant": {"input": 0.05, "output": 0.08},
    # Perplexity
    "sonar": {"input": 1.0, "output": 1.0},
    "sonar-pro": {"input": 3.0, "output": 15.0},
    # Anthropic (newer, approximate)
    "claude-3-7-sonnet": {"input": 3.0, "output": 15.0},
    "claude-sonnet-4": {"input": 3.0, "output": 15.0},
    "claude-haiku-4": {"input": 1.0, "output": 5.0},
    # OpenAI (newer, approximate)
    "gpt-4.1-nano": {"input": 0.1, "output": 0.4},
    "o3-mini": {"input": 1.1, "output": 4.4},
    "o4-mini": {"input": 1.1, "output": 4.4},
    # Google (approximate)
    "gemini-2.5-pro": {"input": 1.25, "output": 10.0},
    "gemini-2.5-flash": {"input": 0.3, "output": 2.5},
    # DeepSeek v3 family (approximate)
    "deepseek-v3": {"input": 0.27, "output": 1.1},
    # Groq / open (approximate)
    "llama-3.1-70b-versatile": {"input": 0.59, "output": 0.79},
    # Local models (free)
    "llama3": {"input": 0.0, "output": 0.0},
    "qwen2.5": {"input": 0.0, "output": 0.0},
}


def _load_pricing() -> dict[str, dict[str, float]]:
    """Resolve the pricing map. Layering (later wins): built-in defaults →
    RECALL_PRICING_FILE (a JSON file path, LiteLLM model_cost-style) →
    RECALL_PRICING (inline JSON). Both overrides let you keep prices current
    without editing the package."""
    pricing = dict(DEFAULT_PRICING)
    path = os.environ.get("RECALL_PRICING_FILE")
    if path:
        try:
            with open(path) as f:
                pricing.update(json.load(f))
        except (ValueError, TypeError, OSError):
            pass
    override = os.environ.get("RECALL_PRICING")
    if override:
        try:
            pricing.update(json.loads(override))
        except (ValueError, TypeError):
            pass
    return pricing


def _candidates(model: str) -> list[str]:
    """Names to try, so provider-prefixed ids resolve too. e.g.
    'openrouter/openai/gpt-4o' → also try 'openai/gpt-4o' and 'gpt-4o'."""
    parts = model.split("/")
    out = [model]
    for i in range(1, len(parts)):
        out.append("/".join(parts[i:]))
    return out


def price_of(model: str) -> Optional[dict[str, float]]:
    """Return {'input','output'} per-1M-token pricing for a model, or None.

    Tries each name candidate exactly, then by longest matching prefix (so
    'gpt-4o-2024-08-06' resolves to 'gpt-4o' and 'gpt-4o-mini-x' beats 'gpt-4o')."""
    pricing = _load_pricing()
    for name in _candidates(model):
        if name in pricing:
            return pricing[name]
        best_key = ""
        for key in pricing:
            if name.startswith(key) and len(key) > len(best_key):
                best_key = key
        if best_key:
            return pricing[best_key]
    return None


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    entry = price_of(model)
    if entry is None:
        return 0.0
    return (input_tokens / 1_000_000) * entry["input"] + (
        output_tokens / 1_000_000
    ) * entry["output"]
