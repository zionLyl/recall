"""LLM-driven memory conflict resolution (opt-in).

The default memory pipeline only ever *appends*, so contradictory facts pile up
("I live in NYC" + "I live in Berlin"). This module — mem0's signature idea —
compares a candidate new fact against the memories most related to it and asks
the model for ONE operation:

  - ADD    : genuinely new information → store it
  - UPDATE : corrects/refines an existing memory → rewrite that memory
  - DELETE : contradicts an existing memory that's now false → forget it
  - NOOP   : already known → do nothing

Opt-in via config `memory_ops = "llm"`. Like the LLM extractor, it degrades
gracefully: any failure (no key, network, bad output) falls back to a plain ADD,
so chat never breaks.

`decide()` returns ``(decision, trace)`` where decision is a dict
``{"op", "id", "content"}`` and trace is the call's ChatResult (for cost
accounting) or None.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from .adapters import get_adapter
from .adapters.base import ChatResult

_VALID_OPS = {"ADD", "UPDATE", "DELETE", "NOOP"}

_SYSTEM = (
    "You maintain a user's long-term memory. Given a NEW candidate fact and the "
    "EXISTING memories most related to it, decide the single best operation.\n"
    "Reply with ONLY a JSON object: {\"op\": ..., \"id\": ..., \"content\": ...}\n"
    "op is one of:\n"
    "  ADD    - the new fact is genuinely new; `id` null, `content` = the fact.\n"
    "  UPDATE - the new fact corrects/refines an existing memory; `id` = that "
    "memory's id, `content` = the merged, up-to-date statement.\n"
    "  DELETE - the new fact makes an existing memory false; `id` = that memory's "
    "id, `content` null.\n"
    "  NOOP   - the new fact is already captured; `id` null, `content` null.\n"
    "Rules: keep the user's language (中文保持中文). Prefer NOOP over storing "
    "duplicates. Only UPDATE/DELETE an id that is actually in the EXISTING list. "
    "Output the JSON object and nothing else."
)


def _parse_decision(text: str) -> Optional[dict]:
    """Extract the decision JSON object from the model reply."""
    if not text:
        return None
    raw = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()
    if not raw.startswith("{"):
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            raw = m.group(0)
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    op = str(data.get("op", "")).upper().strip()
    if op not in _VALID_OPS:
        return None
    raw_id = data.get("id")
    try:
        mem_id = int(raw_id) if raw_id not in (None, "", "null") else None
    except (ValueError, TypeError):
        mem_id = None
    content = data.get("content")
    content = content.strip() if isinstance(content, str) else None
    return {"op": op, "id": mem_id, "content": content}


def _format_related(related) -> str:
    if not related:
        return "(none)"
    return "\n".join(f"  [{m.id}] {m.content}" for m in related)


def decide(
    new_fact: str,
    related: list,
    provider: str,
    model: str,
    *,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> tuple[Optional[dict], Optional[ChatResult]]:
    """Ask the model how to reconcile ``new_fact`` against ``related`` memories.

    Raises on adapter/SDK errors; callers catch and fall back to a plain ADD.
    """
    if not (new_fact or "").strip():
        return None, None
    prompt = (
        f"NEW fact:\n  {new_fact}\n\n"
        f"EXISTING related memories:\n{_format_related(related)}\n\n"
        "Decide the operation."
    )
    adapter = get_adapter(provider, model, api_key=api_key, base_url=base_url)
    result = adapter.chat(prompt, system=_SYSTEM)
    return _parse_decision(result.text), result
