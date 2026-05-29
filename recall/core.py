"""Recall core: the one object that wires memory + observability around any model.

Library usage:

    from recall import Recall

    r = Recall()
    r.remember("I prefer concise answers")
    out = r.chat("openai", "gpt-4o-mini", "How should you reply to me?")
    print(out.text)        # the model will know your preference
    print(r.stats())       # tokens + cost across all calls
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from .adapters import get_adapter
from .adapters.base import ChatResult
from .memory import MemoryEngine
from .pricing import estimate_cost
from .store import Store, Trace


class Recall:
    def __init__(self, db_path: Optional[Path] = None):
        self.store = Store(db_path)
        self.memory = MemoryEngine(self.store)

    # ---- memory ---------------------------------------------------------
    def remember(self, content: str, tags: Optional[list[str]] = None) -> int:
        return self.memory.remember(content, tags=tags)

    def recall_memories(self, query: str, limit: int = 5):
        return self.memory.recall(query, limit=limit)

    # ---- chat (memory + tracing wrapped around any model) ---------------
    def chat(
        self,
        provider: str,
        model: str,
        prompt: str,
        *,
        system: Optional[str] = None,
        use_memory: bool = True,
        memory_limit: int = 5,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> ChatResult:
        # Inject relevant memories into the system prompt.
        final_system = system or ""
        if use_memory:
            ctx = self.memory.build_context(prompt, limit=memory_limit)
            if ctx:
                final_system = (final_system + "\n\n" + ctx).strip()

        adapter = get_adapter(provider, model, api_key=api_key, base_url=base_url)

        start = time.time()
        result = adapter.chat(prompt, system=final_system or None)
        latency_ms = int((time.time() - start) * 1000)

        cost = estimate_cost(result.model, result.input_tokens, result.output_tokens)
        self.store.add_trace(
            Trace(
                model=result.model,
                provider=result.provider,
                prompt=prompt,
                completion=result.text,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost_usd=cost,
                latency_ms=latency_ms,
            )
        )
        return result

    # ---- observability --------------------------------------------------
    def stats(self) -> dict:
        return self.store.stats()

    def recent(self, limit: int = 20):
        return self.store.recent_traces(limit=limit)

    def close(self) -> None:
        self.store.close()
