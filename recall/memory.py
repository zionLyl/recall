"""Memory engine: store, embed, and retrieve memories.

Semantic search uses sentence-transformers if installed; otherwise it
gracefully falls back to SQLite keyword search. This keeps the default install
tiny while letting power users opt into embeddings.
"""

from __future__ import annotations

import struct
from typing import Optional

from .store import Memory, Store

_MODEL = None  # lazily loaded sentence-transformers model


def _get_model():
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return None
    # Small, fast, good enough for local memory recall.
    _MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    return _MODEL


def _pack(vec) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _unpack(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class MemoryEngine:
    def __init__(self, store: Store):
        self.store = store

    @property
    def has_embeddings(self) -> bool:
        return _get_model() is not None

    def remember(
        self,
        content: str,
        tags: Optional[list[str]] = None,
        scope: str = "default",
        source: str = "manual",
        dedupe: bool = True,
    ) -> Optional[int]:
        content = content.strip()
        if not content:
            return None
        if dedupe and self.store.memory_exists(content, scope=scope):
            return None
        embedding = None
        model = _get_model()
        if model is not None:
            vec = model.encode([content])[0].tolist()
            embedding = _pack(vec)
        return self.store.add_memory(
            content, tags=tags, embedding=embedding, scope=scope, source=source
        )

    def recall(self, query: str, limit: int = 5, scope: Optional[str] = None) -> list[Memory]:
        model = _get_model()
        if model is None:
            return self.store.keyword_search(query, limit=limit, scope=scope)

        qvec = model.encode([query])[0].tolist()
        scored: list[Memory] = []
        for mid, content, tags, blob, created, sc, src in self.store.all_memories_with_embeddings(scope=scope):
            if not blob:
                continue
            score = _cosine(qvec, _unpack(blob))
            scored.append(
                Memory(id=mid, content=content, tags=tags, created_at=created, scope=sc, source=src, score=score)
            )
        scored.sort(key=lambda m: m.score, reverse=True)
        top = [m for m in scored if m.score > 0.15][:limit]
        # If embeddings missed everything, fall back to keyword.
        return top or self.store.keyword_search(query, limit=limit, scope=scope)

    def build_context(self, query: str, limit: int = 5, scope: Optional[str] = None) -> str:
        """Return a context block to prepend to a prompt."""
        hits = self.recall(query, limit=limit, scope=scope)
        if not hits:
            return ""
        lines = ["[Things I remember about you]"]
        for m in hits:
            lines.append(f"- {m.content}")
        return "\n".join(lines)
