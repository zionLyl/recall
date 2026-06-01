"""User configuration for memstash.

Stored as JSON at ~/.memstash/config.json (override base with MEMSTASH_HOME).
Holds defaults so users don't repeat themselves: default provider/model,
daily budget, auto-memory toggle, active scope, etc.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from .store import default_db_path


def config_path() -> Path:
    return default_db_path().parent / "config.json"


@dataclass
class Config:
    default_provider: Optional[str] = None
    default_model: Optional[str] = None
    daily_budget_usd: float = 0.0          # 0 = no budget
    budget_enforce: bool = False           # hard-stop (refuse calls) once the daily budget is hit
    auto_memory: bool = True               # auto-extract memories after chat
    extraction_mode: str = "heuristic"     # "heuristic" (free) or "llm" (opt-in, higher recall)
    extraction_model: Optional[str] = None  # model for llm extraction (defaults to chat model)
    memory_ops: str = "append"             # "append" or "llm" (opt-in ADD/UPDATE/DELETE/NOOP conflict resolution)
    graph_extract: bool = False            # opt-in: mine (subject, predicate, object) relations from chats
    memory_inject_limit: int = 5
    embedding_backend: str = "local"       # "local" (sentence-transformers) or "api" (OpenAI-compatible /embeddings)
    embedding_model: Optional[str] = None  # required for api backend, e.g. "nomic-embed-text"
    embedding_base_url: Optional[str] = None  # api backend, e.g. http://localhost:11434/v1 (Ollama)
    embedding_api_key_env: Optional[str] = None  # env var with the key (optional; local servers need none)
    dedupe_similarity: float = 0.0         # 0 = exact-only; e.g. 0.95 suppresses near-dupes on add (needs embeddings)
    recency_weight: float = 0.0            # 0 = pure relevance; >0 blends recency/usage into retrieval ranking
    graph_weight: float = 0.0              # 0 = off; >0 blends graph-connected memories into retrieval (needs relations)
    stream: bool = True                    # stream chat output token-by-token
    otel_export: bool = False              # opt-in: mirror calls as OpenTelemetry/OpenInference spans
    auto_eval_suite: Optional[str] = None  # opt-in: run this saved eval suite on every chat reply
    active_scope: str = "default"          # which memory scope is active
    extras: dict = field(default_factory=dict)

    @classmethod
    def load(cls) -> "Config":
        p = config_path()
        if not p.exists():
            return cls()
        try:
            data = json.loads(p.read_text())
        except (ValueError, OSError):
            return cls()
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    def save(self) -> None:
        p = config_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False))

    def get(self, key: str):
        return getattr(self, key, None) if hasattr(self, key) else self.extras.get(key)

    def set(self, key: str, value) -> None:
        if hasattr(self, key) and key != "extras":
            # Coerce types based on the existing field.
            current = getattr(self, key)
            if isinstance(current, bool):
                value = str(value).lower() in ("1", "true", "yes", "on")
            elif isinstance(current, float):
                value = float(value)
            elif isinstance(current, int):
                value = int(value)
            setattr(self, key, value)
        else:
            self.extras[key] = value
