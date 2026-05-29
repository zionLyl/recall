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


class BudgetExceeded(RuntimeError):
    """Raised when budget_enforce is on and today's spend hit the daily budget."""


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
            content, tags=tags, scope=scope or self.scope, source=source,
            similarity_threshold=getattr(self.config, "dedupe_similarity", 0.0),
        )

    def edit(
        self,
        memory_id: int,
        content: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> bool:
        return self.memory.edit(memory_id, content=content, tags=tags)

    def dedupe(self, scope: Optional[str] = None, threshold: float = 0.9) -> list[dict]:
        return self.memory.dedupe(scope=scope, threshold=threshold)

    def recall_memories(self, query: str, limit: int = 5, scope: Optional[str] = None):
        return self.memory.recall(
            query, limit=limit, scope=scope or self.scope,
            recency_weight=getattr(self.config, "recency_weight", 0.0),
        )

    def forget(self, memory_id: int, soft: bool = False) -> bool:
        if soft:
            return self.store.soft_delete(memory_id)
        return self.store.delete_memory(memory_id)

    def prune(
        self,
        scope: Optional[str] = None,
        older_than_days: Optional[float] = None,
        unused: bool = False,
    ) -> int:
        return self.store.prune(
            scope=scope, older_than_days=older_than_days, unused=unused
        )

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
            ctx = self.memory.build_context(
                prompt, limit=memory_limit, scope=scope,
                recency_weight=getattr(self.config, "recency_weight", 0.0),
            )
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

    def _trace_aux(self, result: Optional[ChatResult], label: str) -> None:
        """Record an auxiliary LLM call (extraction / reconcile) so its token
        cost counts toward stats and the budget."""
        if result is None:
            return
        self.store.add_trace(
            Trace(
                model=result.model,
                provider=result.provider,
                prompt=label,
                completion=result.text,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost_usd=estimate_cost(
                    result.model, result.input_tokens, result.output_tokens
                ),
            )
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
                self._trace_aux(ex_result, "[memory-extraction]")
            except Exception:  # noqa: BLE001 — fall back to heuristic on any failure
                candidates = extract_memories(prompt)
        else:
            candidates = extract_memories(prompt)

        ops_mode = getattr(self.config, "memory_ops", "append") == "llm"
        captured: list[str] = []
        for cand in candidates:
            if ops_mode:
                applied = self._reconcile_capture(
                    cand, scope, provider, model, api_key, base_url
                )
                if applied:
                    captured.append(applied)
            else:
                mid = self.memory.remember(cand, scope=scope, source="auto")
                if mid is not None:
                    captured.append(cand)
        return captured

    def _reconcile_capture(
        self, cand, scope, provider, model, api_key, base_url
    ) -> Optional[str]:
        """Apply one mem0-style ADD/UPDATE/DELETE/NOOP decision for `cand`.

        Returns a human-readable summary of what changed, or None for NOOP.
        Falls back to a plain ADD on any failure.
        """
        try:
            from .reconcile import decide

            related = self.memory.recall(cand, limit=5, scope=scope, touch=False)
            re_model = self.config.extraction_model or model
            decision, re_result = decide(
                cand, related, provider, re_model, api_key=api_key, base_url=base_url
            )
            self._trace_aux(re_result, "[memory-reconcile]")
        except Exception:  # noqa: BLE001 — degrade to plain append
            decision = None

        if decision is None:
            mid = self.memory.remember(cand, scope=scope, source="auto")
            return cand if mid is not None else None

        op = decision["op"]
        if op == "NOOP":
            return None
        if op == "UPDATE" and decision["id"] and decision["content"]:
            if self.memory.edit(decision["id"], content=decision["content"]):
                return f"updated #{decision['id']}: {decision['content']}"
            return None
        if op == "DELETE" and decision["id"]:
            if self.store.soft_delete(decision["id"]):
                return f"forgot #{decision['id']} (contradicted)"
            return None
        # ADD (or a malformed UPDATE/DELETE) → store the candidate.
        content = decision["content"] or cand
        mid = self.memory.remember(content, scope=scope, source="auto")
        return content if mid is not None else None

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
        self._enforce_budget()
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
        self._enforce_budget()
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

    def _spent_today(self) -> float:
        start_of_day = time.time() - (time.time() % 86400)
        return self.store.cost_since(start_of_day)

    def _budget_warning(self) -> Optional[str]:
        budget = self.config.daily_budget_usd
        if not budget or budget <= 0:
            return None
        spent = self._spent_today()
        if spent >= budget:
            return f"Daily budget exceeded: ${spent:.4f} / ${budget:.2f}"
        if spent >= budget * 0.8:
            return f"Approaching daily budget: ${spent:.4f} / ${budget:.2f}"
        return None

    def _enforce_budget(self) -> None:
        """Hard-stop: refuse a new call if today's spend already hit the budget
        and enforcement is on. Warnings alone don't raise."""
        budget = self.config.daily_budget_usd
        if not getattr(self.config, "budget_enforce", False) or not budget or budget <= 0:
            return
        spent = self._spent_today()
        if spent >= budget:
            raise BudgetExceeded(
                f"Daily budget reached (${spent:.4f} / ${budget:.2f}); refusing call. "
                f"Raise daily_budget_usd or turn off budget_enforce."
            )

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
