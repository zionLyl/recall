"""LLM extraction of entity relationships as (subject, predicate, object) triples.

Opt-in (config `graph_extract = true`). Turns free text into a small set of
relational facts that recall stores in its graph-lite `relations` table, enabling
queries like "what do I know about Acme?" without a graph database.

Like the other LLM helpers it degrades gracefully — any failure yields no
triples rather than breaking chat. Returns ``(triples, trace)``.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from .adapters import get_adapter
from .adapters.base import ChatResult

_SYSTEM = (
    "Extract entity relationships from the user's message as triples.\n"
    "Return ONLY a JSON array of [subject, predicate, object] arrays — concise "
    "noun/verb/noun, e.g. [\"Zion\", \"works at\", \"Acme\"], "
    "[\"Acme\", \"is in\", \"Beijing\"].\n"
    "Rules: subject/object are concrete entities (people, orgs, places, projects, "
    "tools); predicate is a short relation. Keep the user's language. Skip vague "
    "statements. If there are no clear relationships, return [].\n"
    "Output the JSON array and nothing else."
)


def _parse(text: str, max_items: int) -> list[tuple[str, str, str]]:
    if not text:
        return []
    raw = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()
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
    out: list[tuple[str, str, str]] = []
    for item in data:
        if isinstance(item, (list, tuple)) and len(item) == 3:
            s, p, o = (str(x).strip() for x in item)
            if s and p and o:
                out.append((s, p, o))
        if len(out) >= max_items:
            break
    return out


def extract_triples(
    text: str,
    provider: str,
    model: str,
    *,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    max_items: int = 8,
) -> tuple[list[tuple[str, str, str]], Optional[ChatResult]]:
    """Extract (subject, predicate, object) triples from ``text``.

    Raises on adapter/SDK errors; callers catch and skip graph extraction.
    """
    if not (text or "").strip():
        return [], None
    adapter = get_adapter(provider, model, api_key=api_key, base_url=base_url)
    result = adapter.chat(text, system=_SYSTEM)
    return _parse(result.text, max_items), result
