"""LLM-based memory extraction (opt-in).

The heuristic extractor in ``extract.py`` is fast and free but only catches
phrases that match its cue patterns. This module instead asks a (cheap) model to
read the user's message and pull out durable, first-person facts/preferences —
higher recall, at the cost of one extra model call.

It's opt-in: set ``extraction_mode = "llm"`` in config. If the call fails for any
reason (no key, network, bad output), the caller falls back to the heuristic
extractor, so enabling this never breaks chat.

Returns ``(memories, trace)`` where ``trace`` is the extraction call's
``ChatResult`` (so the caller can record its token cost) or ``None``.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from .adapters import get_adapter
from .adapters.base import ChatResult

_SYSTEM = (
    "You extract durable memories about the user from a single message.\n"
    "Return ONLY a JSON array of short strings. Each string is one stable, "
    "first-person fact or preference worth remembering long-term (e.g. "
    "\"I prefer concise answers\", \"My timezone is UTC+8\", \"I work on A-share "
    "quant research\").\n"
    "Rules:\n"
    "- Rewrite each memory as a clean, self-contained first-person statement.\n"
    "- Keep the user's original language (English stays English, 中文保持中文).\n"
    "- Only include things that stay true across sessions. Skip questions, "
    "one-off requests, greetings, and anything ephemeral.\n"
    "- If there is nothing worth remembering, return [].\n"
    "- Output the JSON array and nothing else."
)


def _parse(text: str, max_items: int) -> list[str]:
    """Pull a JSON array of strings out of the model's reply, tolerating code
    fences and surrounding prose."""
    if not text:
        return []
    raw = text.strip()
    # Strip ```json ... ``` fences if present.
    fence = re.search(r"```(?:json)?\s*(.+?)```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()
    # Otherwise, isolate the first [...] block.
    if not raw.startswith("["):
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if m:
            raw = m.group(0)
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    out: list[str] = []
    for item in data:
        s = (item if isinstance(item, str) else str(item)).strip()
        if 1 <= len(s) <= 240:
            out.append(s)
        if len(out) >= max_items:
            break
    return out


def extract_memories_llm(
    text: str,
    provider: str,
    model: str,
    *,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    max_items: int = 5,
) -> tuple[list[str], Optional[ChatResult]]:
    """Extract memories from ``text`` using a model call.

    Raises on adapter/SDK errors; the caller is expected to catch and fall back
    to the heuristic extractor.
    """
    if not (text or "").strip():
        return [], None
    adapter = get_adapter(provider, model, api_key=api_key, base_url=base_url)
    result = adapter.chat(text, system=_SYSTEM)
    return _parse(result.text, max_items), result
