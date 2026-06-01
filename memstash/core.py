"""Recall core: the one object that wires memory + observability around any model.

Library usage:

    from memstash import Recall

    r = Recall()
    r.remember("I prefer concise answers")
    out = r.chat("openai", "gpt-4o-mini", "How should you reply to me?")
    print(out.text)        # the model will know your preference
    print(r.stats())       # tokens + cost across all calls
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .adapters import get_adapter
from .adapters.base import ChatResult
from .config import Config
from .extract import extract_memories
from .memory import EmbedConfig, MemoryEngine
from .pricing import estimate_cost
from .store import Store, Trace


def _auto_scope() -> Optional[str]:
    """Derive a scope name from the nearest git repo root (else None). Pure,
    no subprocess — walks up from the current directory looking for `.git`."""
    try:
        cwd = Path.cwd()
    except OSError:
        return None
    for d in (cwd, *cwd.parents):
        if (d / ".git").exists():
            return d.name
    return None


class BudgetExceeded(RuntimeError):
    """Raised when budget_enforce is on and today's spend hit the daily budget."""


@dataclass
class ChatOutcome:
    """Result of a chat call, enriched with memstash metadata."""

    text: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    auto_remembered: list[str]      # memories captured from this turn
    budget_warning: Optional[str]   # set if daily budget exceeded
    graph_added: int = 0            # relations mined this turn (graph_extract)


class Recall:
    def __init__(self, db_path: Optional[Path] = None, config: Optional[Config] = None):
        from .firewall import FirewallConfig

        self.store = Store(db_path)
        self.config = config or Config.load()
        fw = FirewallConfig.from_strings(
            getattr(self.config, "firewall_mode", "quarantine"),
            getattr(self.config, "firewall_trusted_sources", "manual,auto"),
        )
        self.memory = MemoryEngine(self.store, embed_cfg=self._embed_cfg(), firewall=fw)

    def _embed_cfg(self) -> EmbedConfig:
        c = self.config
        return EmbedConfig(
            backend=getattr(c, "embedding_backend", "local") or "local",
            model=getattr(c, "embedding_model", None),
            base_url=getattr(c, "embedding_base_url", None),
            api_key_env=getattr(c, "embedding_api_key_env", None),
        )

    @property
    def scope(self) -> str:
        # Auto scope: derive per-project memory from the current git repo / cwd,
        # so context doesn't bleed between projects. Falls back to the configured
        # scope if not in a recognizable project.
        if getattr(self.config, "scope_auto", False):
            auto = _auto_scope()
            if auto:
                return auto
        return self.config.active_scope or "default"

    # ---- memory ---------------------------------------------------------
    def remember(
        self,
        content: str,
        tags: Optional[list[str]] = None,
        scope: Optional[str] = None,
        source: str = "manual",
        mem_type: str = "note",
        confidence: float = 1.0,
        source_ref: Optional[str] = None,
    ) -> Optional[int]:
        return self.memory.remember(
            content, tags=tags, scope=scope or self.scope, source=source,
            similarity_threshold=getattr(self.config, "dedupe_similarity", 0.0),
            mem_type=mem_type, confidence=confidence, source_ref=source_ref,
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

    def as_of(self, ts: float, scope: Optional[str] = None):
        """Memories that were valid at time `ts` (bi-temporal point-in-time)."""
        return self.store.memories_as_of(ts, scope=scope or self.scope)

    def ingest(
        self,
        path,
        scope: Optional[str] = None,
        tags: Optional[list[str]] = None,
        max_chars: int = 500,
        source: str = "document",
    ) -> dict:
        """Ingest a document into memory as searchable chunks. Returns counts."""
        from pathlib import Path as _Path

        from .ingest import chunk_text, read_file

        chunks = chunk_text(read_file(path), max_chars=max_chars)
        tag_list = list(tags or []) + [_Path(path).stem]
        ref = str(path)
        new = 0
        for c in chunks:
            if self.memory.remember(
                c, tags=tag_list, scope=scope or self.scope, source=source,
                mem_type="document", source_ref=ref,
            ) is not None:
                new += 1
        return {"path": str(path), "chunks": len(chunks), "new": new}

    def recall_memories(self, query: str, limit: int = 5, scope: Optional[str] = None):
        return self.memory.recall(
            query, limit=limit, scope=scope or self.scope,
            recency_weight=getattr(self.config, "recency_weight", 0.0),
            graph_weight=getattr(self.config, "graph_weight", 0.0),
            min_score=getattr(self.config, "memory_min_score", 0.15),
        )

    def forget(self, memory_id: int, soft: bool = False) -> bool:
        if soft:
            return self.store.soft_delete(memory_id)
        return self.store.delete_memory(memory_id)

    # ---- write firewall -------------------------------------------------
    def quarantined(self, scope: Optional[str] = None):
        return self.store.quarantined_memories(scope=scope or self.scope)

    def approve(self, memory_id: int) -> bool:
        return self.store.approve(memory_id)

    def reject(self, memory_id: int) -> bool:
        return self.store.reject(memory_id)

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
                "Run `memstash config set default_provider ...` or pass them explicitly."
            )
        scope = scope or self.scope
        memory_limit = (
            memory_limit if memory_limit is not None else self.config.memory_inject_limit
        )
        return provider, model, scope, memory_limit

    def _inject(self, prompt, system, use_memory, memory_limit, scope) -> Optional[str]:
        final_system = system or ""
        if use_memory:
            try:
                ctx = self.memory.build_context(
                    prompt, limit=memory_limit, scope=scope,
                    recency_weight=getattr(self.config, "recency_weight", 0.0),
                    graph_weight=getattr(self.config, "graph_weight", 0.0),
                    min_score=getattr(self.config, "memory_min_score", 0.15),
                )
            except Exception:  # noqa: BLE001 — retrieval must never break the chat
                ctx = ""
            if ctx:
                final_system = (final_system + "\n\n" + ctx).strip()
        return final_system or None

    def _finalize(
        self, result: ChatResult, prompt, latency_ms, auto_memory, scope, provider, model,
        api_key, base_url,
    ) -> ChatOutcome:
        """Record the trace, auto-capture memories, and build the outcome."""
        cost = estimate_cost(result.model, result.input_tokens, result.output_tokens)
        session_id = uuid.uuid4().hex[:12]
        parent_id = self.store.add_trace(
            Trace(
                model=result.model,
                provider=result.provider,
                prompt=prompt,
                completion=result.text,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost_usd=cost,
                latency_ms=latency_ms,
                session_id=session_id,
                kind="chat",
            )
        )
        if getattr(self.config, "otel_export", False):
            try:
                from . import otel_export
                otel_export.export({
                    "model": result.model, "provider": result.provider,
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "cost_usd": cost, "prompt": prompt,
                    "completion": result.text, "kind": "chat",
                })
            except Exception:  # noqa: BLE001 — export must never break chat
                pass
        captured = self._auto_capture(
            prompt, auto_memory, scope, provider, model, api_key, base_url,
            session_id, parent_id,
        )
        graph_added = self._auto_graph(
            prompt, auto_memory, scope, provider, model, api_key, base_url,
            session_id, parent_id,
        )
        auto_suite = getattr(self.config, "auto_eval_suite", None)
        if auto_suite:
            try:
                self.run_suite(parent_id, auto_suite)
            except Exception:  # noqa: BLE001 — eval must never break chat
                pass
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
            graph_added=graph_added,
        )

    def _trace_aux(
        self, result: Optional[ChatResult], label: str, kind: str = "aux",
        session_id: str = "", parent_id: Optional[int] = None,
    ) -> None:
        """Record an auxiliary LLM call (extraction / reconcile / graph) as a
        child of the chat call, so its cost counts and the trace tree groups it."""
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
                session_id=session_id,
                parent_id=parent_id,
                kind=kind,
            )
        )

    def _auto_capture(
        self, prompt, auto_memory, scope, provider, model, api_key, base_url,
        session_id: str = "", parent_id: Optional[int] = None,
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
                self._trace_aux(ex_result, "[memory-extraction]", "extract",
                                session_id, parent_id)
            except Exception:  # noqa: BLE001 — fall back to heuristic on any failure
                candidates = extract_memories(prompt)
        else:
            candidates = extract_memories(prompt)

        ops_mode = getattr(self.config, "memory_ops", "append") == "llm"
        captured: list[str] = []
        for cand in candidates:
            if ops_mode:
                applied = self._reconcile_capture(
                    cand, scope, provider, model, api_key, base_url,
                    session_id, parent_id,
                )
                if applied:
                    captured.append(applied)
            else:
                mid = self.memory.remember(
                    cand, scope=scope, source="auto", source_trace=parent_id
                )
                if mid is not None:
                    captured.append(cand)
        return captured

    def _reconcile_capture(
        self, cand, scope, provider, model, api_key, base_url,
        session_id: str = "", parent_id: Optional[int] = None,
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
            self._trace_aux(re_result, "[memory-reconcile]", "reconcile",
                            session_id, parent_id)
        except Exception:  # noqa: BLE001 — degrade to plain append
            decision = None

        if decision is None:
            mid = self.memory.remember(cand, scope=scope, source="auto", source_trace=parent_id)
            return cand if mid is not None else None

        op = decision["op"]
        if op == "NOOP":
            return None
        if op == "UPDATE" and decision["id"] and decision["content"]:
            # Supersede, don't overwrite: close the old fact's validity window
            # (kept as history) and add the new one, so "what did I know then?"
            # stays answerable.
            if self.store.get_memory(decision["id"]) and self.store.soft_delete(decision["id"]):
                self.memory.remember(
                    decision["content"], scope=scope, source="auto", source_trace=parent_id
                )
                return f"updated #{decision['id']}: {decision['content']}"
            return None
        if op == "DELETE" and decision["id"]:
            if self.store.soft_delete(decision["id"]):
                return f"forgot #{decision['id']} (contradicted)"
            return None
        # ADD (or a malformed UPDATE/DELETE) → store the candidate.
        content = decision["content"] or cand
        mid = self.memory.remember(content, scope=scope, source="auto", source_trace=parent_id)
        return content if mid is not None else None

    def _auto_graph(
        self, prompt, auto_memory, scope, provider, model, api_key, base_url,
        session_id: str = "", parent_id: Optional[int] = None,
    ) -> int:
        """Mine (subject, predicate, object) relations from the prompt into the
        graph-lite store. Opt-in (config graph_extract); never breaks chat."""
        auto = auto_memory if auto_memory is not None else self.config.auto_memory
        if not auto or not getattr(self.config, "graph_extract", False):
            return 0
        try:
            from .graph_extract import extract_triples

            gx_model = self.config.extraction_model or model
            triples, gx_result = extract_triples(
                prompt, provider, gx_model, api_key=api_key, base_url=base_url
            )
            self._trace_aux(gx_result, "[graph-extract]", "graph",
                            session_id, parent_id)
        except Exception:  # noqa: BLE001
            return 0
        added = 0
        for s, p, o in triples:
            if self.store.add_relation(s, p, o, scope=scope) is not None:
                added += 1
        return added

    # ---- graph-lite -----------------------------------------------------
    def add_relation(self, subject, predicate, object_, scope: Optional[str] = None):
        return self.store.add_relation(subject, predicate, object_, scope=scope or self.scope)

    def graph(self, entity: Optional[str] = None, scope: Optional[str] = None) -> list[dict]:
        """Relations for `entity` (subject or object), or all relations in scope."""
        scope = scope or self.scope
        if entity:
            return self.store.relations_for(entity, scope=scope)
        return self.store.all_relations(scope=scope)

    # ---- prompt templates ----------------------------------------------
    def save_prompt(self, name: str, content: str) -> None:
        self.store.save_prompt(name, content)

    def render_prompt(self, name: str, variables: Optional[dict] = None) -> Optional[str]:
        """Load template `name` and render its {var} placeholders. None if absent."""
        from .prompts import render

        content = self.store.get_prompt(name)
        if content is None:
            return None
        return render(content, variables or {})

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
        history: Optional[list] = None,
    ) -> ChatOutcome:
        provider, model, scope, memory_limit = self._resolve(
            provider, model, scope, memory_limit
        )
        self._enforce_budget()
        final_system = self._inject(prompt, system, use_memory, memory_limit, scope)
        adapter = get_adapter(provider, model, api_key=api_key, base_url=base_url)

        start = time.time()
        result = adapter.chat(prompt, system=final_system, history=history)
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
        history: Optional[list] = None,
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
        for chunk in adapter.stream(prompt, system=final_system, history=history):
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
        s["evals"] = self.store.eval_summary()
        return s

    def recent(self, limit: int = 20):
        return self.store.recent_traces(limit=limit)

    def recent_sessions(self, limit: int = 10):
        return self.store.recent_sessions(limit=limit)

    # ---- evals ----------------------------------------------------------
    def evaluate(
        self,
        trace_id: int,
        *,
        contains: Optional[str] = None,
        not_contains: Optional[str] = None,
        regex: Optional[str] = None,
        max_tokens: Optional[int] = None,
        judge: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> list[dict]:
        """Run the requested checks against a traced call's reply and persist
        them. Returns the result dicts. Raises ValueError if the trace is gone."""
        from . import evals as ev

        trace = self.store.get_trace(trace_id)
        if trace is None:
            raise ValueError(f"No trace #{trace_id}")
        reply = trace.get("completion", "") or ""
        results: list[dict] = []
        if contains is not None:
            results.append(ev.check_contains(reply, contains))
        if not_contains is not None:
            results.append(ev.check_not_contains(reply, not_contains))
        if regex is not None:
            results.append(ev.check_regex(reply, regex))
        if max_tokens is not None:
            results.append(ev.check_max_tokens(trace.get("output_tokens", 0) or 0, max_tokens))
        if judge:
            prov = provider or self.config.default_provider
            mdl = self.config.extraction_model or model or self.config.default_model
            if prov and mdl:
                res, jr = ev.judge(reply, judge, prov, mdl, api_key=api_key, base_url=base_url)
                self._trace_aux(jr, "[eval-judge]", "eval")
                if res is not None:
                    res = {**res, "detail": f"{judge}: {res['detail']}"}
                    results.append(res)
        for r in results:
            self.store.add_eval(
                trace_id, r["kind"], r["name"], r["score"], r["passed"], r["detail"]
            )
        return results

    def evals_for(self, trace_id: int) -> list[dict]:
        return self.store.evals_for(trace_id)

    def run_suite(self, trace_id: int, suite_name: str, **overrides) -> list[dict]:
        """Run a saved eval suite against a trace. `overrides` win over the
        suite's spec. Raises ValueError if the suite or trace is missing."""
        spec = self.store.get_suite(suite_name)
        if spec is None:
            raise ValueError(f"No eval suite '{suite_name}'")
        merged = {**spec, **{k: v for k, v in overrides.items() if v is not None}}
        return self.evaluate(trace_id, **merged)

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
