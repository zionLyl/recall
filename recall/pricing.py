"""Per-million-token pricing (USD) for cost estimation.

These are best-effort defaults; users can override via RECALL_PRICING env var
(JSON mapping model -> {"input": x, "output": y} per 1M tokens). Pricing
changes often, so this is intentionally easy to override and never blocks a
call if a model is unknown (cost falls back to 0).
"""

from __future__ import annotations

import json
import os

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
}


def _load_pricing() -> dict[str, dict[str, float]]:
    pricing = dict(DEFAULT_PRICING)
    override = os.environ.get("RECALL_PRICING")
    if override:
        try:
            pricing.update(json.loads(override))
        except (ValueError, TypeError):
            pass
    return pricing


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = _load_pricing()
    # Match on prefix so "gpt-4o-2024-08-06" still resolves to "gpt-4o".
    entry = pricing.get(model)
    if entry is None:
        # Match the longest prefix so "gpt-4o-mini-..." beats "gpt-4o".
        best_key = ""
        for key in pricing:
            if model.startswith(key) and len(key) > len(best_key):
                best_key = key
        entry = pricing.get(best_key) if best_key else None
    if entry is None:
        return 0.0
    return (input_tokens / 1_000_000) * entry["input"] + (
        output_tokens / 1_000_000
    ) * entry["output"]
