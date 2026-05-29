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

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .adapters import get_adapter
from .adapters.base import ChatResult
from .config import Config
from .extract import extract_memories
from .memory import MemoryEngine
from .pricing import estimate_cost
from .store import Store, Trace


@dataclass
class ChatOutcome:
    """Result of a chat call, enriched with recall metadata."""

    text: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    auto_remembered: list[str]      # memories captured from this turn
    budget_warning: Optional[str]   # set if daily budget exceeded


class Recall:
    def __init__(self, db_path: Optional[Path] = None, config: Optional[Config] = None):
        self.store = Store(db_path)
        self.memory = MemoryEngine(self.store)
        self.config = config or Config.load()

    @property
    def scope(self) -> str:
        return self.config.active_scope or "default"

    # ---- memory ---------------------------------------------------------
    def remember(
        self,
        content: str,
        tags: Optional[list[str]] = None,
        scope: Optional[str] = None,
        source: str = "manual",
    ) -> Optional[int]:
        return self.memory.remember(
            content, tags=tags, scope=scope or self.scope, source=source
        )

    def recall_memories(self, query: str, limit: int = 5, scope: Optional[str] = None):
        return self.memory.recall(query, limit=limit, scope=scope or self.scope)

    # ---- chat (memory + tracing wrapped around any model) ---------------
    def _resolve(self, provider, model, scope, memory_limit):
        provider = provider or self.config.default_provider
        model = model or self.config.default_model
        if not provider or not model:
            raise ValueError(
                "No provider/model given and no defaults configured. "
                "Run `recall config set default_provider ...` or pass them explicitly."
            )
        scope = scope or self.scope
        memory_limit = (
            memory_limit if memory_limit is not None else self.config.memory_inject_limit
        )
        return provider, model, scope, memory_limit

    def _inject(self, prompt, system, use_memory, memory_limit, scope) -> Optional[str]:
        final_system = system or ""
        if use_memory:
            ctx = self.memory.build_context(prompt, limit=memory_limit, scope=scope)
            if ctx:
                final_system = (final_system + "\n\n" + ctx).strip()
        return final_system or None

    def _finalize(
        self, result: ChatResult, prompt, latency_ms, auto_memory, scope, provider, model,
        api_key, base_url,
    ) -> ChatOutcome:
        """Record the trace, auto-capture memories, and build the outcome."""
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
        captured = self._auto_capture(
            prompt, auto_memory, scope, provider, model, api_key, base_url
        )
        return ChatOutcome(
            text=result.text,
            model=result.model,
            provider=result.provider,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
            auto_remembered=captured,
            budget_warning=self._budget_warning(),
        )

    def _auto_capture(
        self, prompt, auto_memory, scope, provider, model, api_key, base_url
    ) -> list[str]:
        auto = auto_memory if auto_memory is not None else self.config.auto_memory
        if not auto:
            return []

        candidates: list[str] = []
        if getattr(self.config, "extraction_mode", "heuristic") == "llm":
            try:
                from .extract_llm import extract_memories_llm

                ex_model = self.config.extraction_model or model
                candidates, ex_result = extract_memories_llm(
                    prompt, provider, ex_model, api_key=api_key, base_url=base_url
                )
                # Record the extraction call's cost so the budget stays honest.
                if ex_result is not None:
                    self.store.add_trace(
                        Trace(
                            model=ex_result.model,
                            provider=ex_result.provider,
                            prompt="[memory-extraction]",
                            completion=ex_result.text,
                            input_tokens=ex_result.input_tokens,
                            output_tokens=ex_result.output_tokens,
                            cost_usd=estimate_cost(
                                ex_result.model,
                                ex_result.input_tokens,
                                ex_result.output_tokens,
                            ),
                        )
                    )
            except Exception:  # noqa: BLE001 — fall back to heuristic on any failure
                candidates = extract_memories(prompt)
        else:
            candidates = extract_memories(prompt)

        captured: list[str] = []
        for cand in candidates:
            mid = self.memory.remember(cand, scope=scope, source="auto")
            if mid is not None:
                captured.append(cand)
        return captured

    def chat(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        prompt: str = "",
        *,
        system: Optional[str] = None,
        use_memory: bool = True,
        memory_limit: Optional[int] = None,
        auto_memory: Optional[bool] = None,
        scope: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> ChatOutcome:
        provider, model, scope, memory_limit = self._resolve(
            provider, model, scope, memory_limit
        )
        final_system = self._inject(prompt, system, use_memory, memory_limit, scope)
        adapter = get_adapter(provider, model, api_key=api_key, base_url=base_url)

        start = time.time()
        result = adapter.chat(prompt, system=final_system)
        latency_ms = int((time.time() - start) * 1000)

        return self._finalize(
            result, prompt, latency_ms, auto_memory, scope, provider, model,
            api_key, base_url,
        )

    def stream(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        prompt: str = "",
        *,
        on_token: Optional[Callable[[str], None]] = None,
        system: Optional[str] = None,
        use_memory: bool = True,
        memory_limit: Optional[int] = None,
        auto_memory: Optional[bool] = None,
        scope: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> ChatOutcome:
        """Like ``chat()`` but streams the reply token-by-token.

        Each chunk is passed to ``on_token`` as it arrives; the full outcome
        (text, tokens, cost, auto-memory, budget) is returned once complete.
        """
        provider, model, scope, memory_limit = self._resolve(
            provider, model, scope, memory_limit
        )
        final_system = self._inject(prompt, system, use_memory, memory_limit, scope)
        adapter = get_adapter(provider, model, api_key=api_key, base_url=base_url)

        start = time.time()
        parts: list[str] = []
        for chunk in adapter.stream(prompt, system=final_system):
            parts.append(chunk)
            if on_token is not None:
                on_token(chunk)
        latency_ms = int((time.time() - start) * 1000)

        result = adapter.last_result or ChatResult(
            text="".join(parts), input_tokens=0, output_tokens=0,
            model=model, provider=provider,
        )
        return self._finalize(
            result, prompt, latency_ms, auto_memory, scope, provider, model,
            api_key, base_url,
        )

    def _budget_warning(self) -> Optional[str]:
        budget = self.config.daily_budget_usd
        if not budget or budget <= 0:
            return None
        start_of_day = time.time() - (time.time() % 86400)
        spent = self.store.cost_since(start_of_day)
        if spent >= budget:
            return f"Daily budget exceeded: ${spent:.4f} / ${budget:.2f}"
        if spent >= budget * 0.8:
            return f"Approaching daily budget: ${spent:.4f} / ${budget:.2f}"
        return None

    # ---- observability --------------------------------------------------
    def stats(self) -> dict:
        s = self.store.stats()
        start_of_day = time.time() - (time.time() % 86400)
        s["cost_today"] = self.store.cost_since(start_of_day)
        s["daily_budget"] = self.config.daily_budget_usd
        s["scopes"] = self.store.list_scopes()
        return s

    def recent(self, limit: int = 20):
        return self.store.recent_traces(limit=limit)

    # ---- export / import ------------------------------------------------
    def export_memories(self, path: Path, scope: Optional[str] = None) -> int:
        data = self.store.export_memories(scope=scope)
        Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False))
        return len(data)

    def import_memories(self, path: Path) -> int:
        data = json.loads(Path(path).read_text())
        count = 0
        for item in data:
            mid = self.memory.remember(
                item["content"],
                tags=item.get("tags", []),
                scope=item.get("scope", "default"),
                source=item.get("source", "imported"),
            )
            if mid is not None:
                count += 1
        return count

    def close(self) -> None:
        self.store.close()
