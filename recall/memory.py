"""Memory engine: store, embed, and retrieve memories.

Semantic search has two embedding backends:
  - "local" (default): a sentence-transformers model (downloads ~80MB on first
    use). Falls back to SQLite keyword search if the package isn't installed.
  - "api": any OpenAI-compatible /embeddings endpoint — point at a local Ollama
    or LM Studio server for semantic search with *no* heavy PyTorch download, or
    at a cloud provider. Configured via embedding_backend / embedding_model /
    embedding_base_url / embedding_api_key_env.
"""

from __future__ import annotations

import json
import os
import struct
import urllib.request
from dataclasses import dataclass
from typing import Optional

from .store import Memory, Store

_MODEL = None  # lazily loaded sentence-transformers model


@dataclass
class EmbedConfig:
    backend: str = "local"            # "local" | "api"
    model: Optional[str] = None       # required for "api"
    base_url: Optional[str] = None    # required for "api", e.g. http://localhost:11434/v1
    api_key_env: Optional[str] = None # env var holding the key (optional; Ollama needs none)


def _get_model():
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return None
    # One-time heads-up: the first load downloads ~80MB and can take a moment.
    import sys
    print(
        "recall: loading the embedding model for semantic search "
        "(first run may download ~80MB)…",
        file=sys.stderr, flush=True,
    )
    # Small, fast, good enough for local memory recall.
    _MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    return _MODEL


def _embed_api(texts, base_url: str, model: str, api_key: Optional[str] = None):
    """Embed via an OpenAI-compatible /embeddings endpoint. Returns a list of
    vectors, or None on any failure (caller falls back to keyword search)."""
    url = base_url.rstrip("/") + "/embeddings"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    body = json.dumps({"model": model, "input": list(texts)}).encode()
    try:
        req = urllib.request.Request(url, data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        items = sorted(data["data"], key=lambda d: d.get("index", 0))
        return [it["embedding"] for it in items]
    except Exception:  # noqa: BLE001 — network/parse error → degrade to keyword
        return None


def _pack(vec) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _unpack(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def _cosine(a: list[float], b: list[float]) -> float:
    # Dimension mismatch (e.g. embeddings from different models) → not comparable.
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _semantic_rank(qvec, rows):
    """Score `rows` (from all_memories_with_embeddings) against `qvec` by cosine,
    numpy-accelerated when available with a pure-Python fallback. Skips rows whose
    embedding dimension differs from the query (e.g. after switching embedding
    models). Returns list of (id, content, tags, created, scope, source, score)."""
    qd = len(qvec)
    meta, vecs = [], []
    for mid, content, tags, blob, created, sc, src in rows:
        if not blob:
            continue
        v = _unpack(blob)
        if len(v) != qd:          # different embedding model → not comparable
            continue
        meta.append((mid, content, tags, created, sc, src))
        vecs.append(v)
    if not meta:
        return []
    try:
        import numpy as np

        M = np.asarray(vecs, dtype="float32")
        q = np.asarray(qvec, dtype="float32")
        Mn = np.linalg.norm(M, axis=1)
        qn = float(np.linalg.norm(q))
        denom = Mn * qn
        sims = np.divide(M @ q, denom, out=np.zeros(len(M), dtype="float32"), where=denom > 0)
        scores = sims.tolist()
    except Exception:  # noqa: BLE001 — numpy missing/any failure → pure Python
        scores = [_cosine(qvec, v) for v in vecs]
    return [(*meta[i], scores[i]) for i in range(len(meta))]


def _rrf(
    rankings: list[list[int]], k: int = 60, weights: Optional[list[float]] = None
) -> dict[int, float]:
    """Reciprocal Rank Fusion: combine several ranked id-lists into one score
    map. An item's score is the weighted sum of 1/(k + rank) across the lists it
    appears in (rank is 0-based), so items ranked highly by multiple signals
    rise. Per-ranking ``weights`` let one signal (e.g. recency) count for less."""
    if weights is None:
        weights = [1.0] * len(rankings)
    scores: dict[int, float] = {}
    for ranking, weight in zip(rankings, weights):
        for rank, item_id in enumerate(ranking):
            scores[item_id] = scores.get(item_id, 0.0) + weight * (1.0 / (k + rank))
    return scores


class MemoryEngine:
    def __init__(self, store: Store, embed_cfg: Optional[EmbedConfig] = None):
        self.store = store
        self.embed_cfg = embed_cfg or EmbedConfig()

    @property
    def has_embeddings(self) -> bool:
        if self.embed_cfg.backend == "api":
            return bool(self.embed_cfg.base_url and self.embed_cfg.model)
        return _get_model() is not None

    def _encode(self, texts: list[str]) -> Optional[list[list[float]]]:
        """Embed `texts` with the configured backend; None if unavailable."""
        cfg = self.embed_cfg
        if cfg.backend == "api":
            if not (cfg.base_url and cfg.model):
                return None
            key = os.environ.get(cfg.api_key_env or "", "") or os.environ.get("RECALL_API_KEY", "")
            return _embed_api(texts, cfg.base_url, cfg.model, key or None)
        model = _get_model()
        if model is None:
            return None
        return [v.tolist() for v in model.encode(list(texts))]

    def _embed(self, text: str) -> Optional[bytes]:
        vecs = self._encode([text])
        return _pack(vecs[0]) if vecs else None

    def remember(
        self,
        content: str,
        tags: Optional[list[str]] = None,
        scope: str = "default",
        source: str = "manual",
        dedupe: bool = True,
        similarity_threshold: float = 0.0,
        source_trace: Optional[int] = None,
    ) -> Optional[int]:
        content = content.strip()
        if not content:
            return None
        if dedupe and self.store.memory_exists(content, scope=scope):
            return None
        embedding = self._embed(content)
        # Near-duplicate suppression: if embeddings are available and a
        # threshold is set, skip content that's semantically almost identical to
        # something already stored in this scope (e.g. "I like tea" vs "I really
        # like tea"). Exact dedupe above still applies when embeddings are off.
        if dedupe and embedding is not None and similarity_threshold > 0:
            match = self._find_similar(embedding, scope, similarity_threshold)
            if match is not None:
                return None
        return self.store.add_memory(
            content, tags=tags, embedding=embedding, scope=scope, source=source,
            source_trace=source_trace,
        )

    def edit(
        self,
        memory_id: int,
        content: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> bool:
        """Edit a memory's content and/or tags, re-embedding if content changed."""
        embedding = None
        embedding_set = False
        if content is not None:
            content = content.strip()
            if not content:
                return False
            embedding = self._embed(content)
            embedding_set = True
        return self.store.update_memory(
            memory_id, content=content, tags=tags,
            embedding=embedding, embedding_set=embedding_set,
        )

    def _find_similar(
        self, embedding: bytes, scope: str, threshold: float, exclude_id: Optional[int] = None
    ) -> Optional[tuple[int, float]]:
        """Return (id, score) of the most similar stored memory above threshold."""
        qvec = _unpack(embedding)
        best: Optional[tuple[int, float]] = None
        for mid, _content, _tags, blob, _created, _sc, _src in (
            self.store.all_memories_with_embeddings(scope=scope)
        ):
            if not blob or mid == exclude_id:
                continue
            score = _cosine(qvec, _unpack(blob))
            if score >= threshold and (best is None or score > best[1]):
                best = (mid, score)
        return best

    def dedupe(self, scope: Optional[str] = None, threshold: float = 0.9) -> list[dict]:
        """Merge near-duplicate memories by cosine similarity.

        Within each scope, greedily clusters memories whose embeddings are at or
        above ``threshold``, keeps the earliest one as canonical, unions tags
        onto it, and deletes the rest. Requires embeddings; memories without an
        embedding are left untouched. Returns a list of merge records.
        """
        if not self.has_embeddings:
            return []
        rows = self.store.all_memories_with_embeddings(scope=scope)
        # (id, content, tags, vec, created, scope)
        items = [
            (mid, content, tags, _unpack(blob), created, sc)
            for mid, content, tags, blob, created, sc, _src in rows
            if blob
        ]
        # Cluster per scope; keep the earliest created as canonical.
        items.sort(key=lambda x: (x[5], x[4]))  # by scope, then created_at
        merged_ids: set[int] = set()
        merges: list[dict] = []
        for i, (mid, content, tags, vec, _created, sc) in enumerate(items):
            if mid in merged_ids:
                continue
            absorbed: list[int] = []
            tag_union = set(tags)
            for mid2, content2, tags2, vec2, _c2, sc2 in items[i + 1:]:
                if mid2 in merged_ids or sc2 != sc:
                    continue
                if _cosine(vec, vec2) >= threshold:
                    absorbed.append(mid2)
                    tag_union.update(tags2)
                    merged_ids.add(mid2)
            if absorbed:
                self.store.update_memory(mid, tags=sorted(tag_union))
                for dup in absorbed:
                    self.store.delete_memory(dup)
                merges.append({
                    "kept": mid, "kept_content": content,
                    "removed": absorbed, "scope": sc,
                })
        return merges

    def _graph_expand(self, query: str, scope: Optional[str], limit: int) -> list[Memory]:
        """Use the graph-lite relations to pull in memories about entities
        *connected* to those named in the query — even if the query doesn't
        mention them. e.g. query "Acme" → neighbor "Beijing" → memories about
        Beijing surface too. Returns memories in expansion order."""
        entities = [name for name, _ in self.store.entities(scope=scope)]
        if not entities:
            return []
        ql = query.lower()
        matched = [e for e in entities if e.lower() in ql]
        if not matched:
            return []
        matched_lower = {e.lower() for e in matched}
        neighbors: list[str] = []
        seen_n: set[str] = set()
        for entity in matched:
            for rel in self.store.relations_for(entity, scope=scope):
                other = rel["object"] if rel["subject"].lower() == entity.lower() else rel["subject"]
                if other.lower() not in matched_lower and other.lower() not in seen_n:
                    seen_n.add(other.lower())
                    neighbors.append(other)
        out: list[Memory] = []
        seen_ids: set[int] = set()
        for neighbor in neighbors:
            for m in self.store.keyword_search(neighbor, limit=limit, scope=scope):
                if m.id not in seen_ids:
                    seen_ids.add(m.id)
                    out.append(m)
        return out

    def recall(
        self, query: str, limit: int = 5, scope: Optional[str] = None,
        recency_weight: float = 0.0, graph_weight: float = 0.0, touch: bool = True,
    ) -> list[Memory]:
        qvecs = self._encode([query]) if self.has_embeddings else None
        if not qvecs:
            # No embeddings (or backend unreachable): keyword/BM25 is all we have.
            hits = self.store.keyword_search(query, limit=limit, scope=scope)
            if touch:
                self.store.touch_memories([m.id for m in hits])
            return hits

        # Semantic ranking over all embedded memories (vectorized when numpy is
        # present; dimension-mismatched vectors are skipped).
        qvec = qvecs[0]
        ranked = _semantic_rank(qvec, self.store.all_memories_with_embeddings(scope=scope))
        scored = [
            Memory(id=mid, content=content, tags=tags, created_at=created,
                   scope=sc, source=src, score=score)
            for mid, content, tags, created, sc, src, score in ranked
        ]
        scored.sort(key=lambda m: m.score, reverse=True)
        semantic = [m for m in scored if m.score > 0.15]

        # Keyword/BM25 ranking (catches exact terms, names, IDs the embeddings
        # may blur). Pull a wider pool than `limit` so fusion has signal.
        pool = max(limit * 4, 10)
        keyword = self.store.keyword_search(query, limit=pool, scope=scope)

        # Graph-aware expansion: memories about entities connected to the query.
        graph_hits = self._graph_expand(query, scope, pool) if graph_weight > 0 else []

        if not semantic and not keyword and not graph_hits:
            return []

        # Hybrid: fuse rankings with Reciprocal Rank Fusion so a memory ranked
        # well by *any* signal surfaces, and one strong on several wins (mem0 /
        # Zep do semantic + BM25 + graph). Kept dependency-free; RRF handles empties.
        by_id: dict[int, Memory] = {}
        for m in semantic[:pool] + keyword + graph_hits:
            by_id.setdefault(m.id, m)
        rankings = [[m.id for m in semantic[:pool]], [m.id for m in keyword]]
        weights = [1.0, 1.0]
        if graph_hits:
            rankings.append([m.id for m in graph_hits])
            weights.append(graph_weight)
        if recency_weight > 0 and by_id:
            # Lifecycle ranking: most-recently-used, then most-hit, ranks first.
            life = sorted(
                by_id.values(),
                key=lambda m: (m.last_used or m.created_at, m.hit_count),
                reverse=True,
            )
            rankings.append([m.id for m in life])
            weights.append(recency_weight)

        fused = _rrf(rankings, weights=weights)
        ranked_ids = sorted(fused, key=lambda i: fused[i], reverse=True)[:limit]
        out: list[Memory] = []
        for mid in ranked_ids:
            m = by_id[mid]
            m.score = round(fused[mid], 4)
            out.append(m)
        if touch:
            self.store.touch_memories([m.id for m in out])
        return out

    def build_context(
        self, query: str, limit: int = 5, scope: Optional[str] = None,
        recency_weight: float = 0.0, graph_weight: float = 0.0,
    ) -> str:
        """Return a context block to prepend to a prompt."""
        hits = self.recall(
            query, limit=limit, scope=scope,
            recency_weight=recency_weight, graph_weight=graph_weight,
        )
        if not hits:
            return ""
        lines = ["[Things I remember about you]"]
        for m in hits:
            lines.append(f"- {m.content}")
        return "\n".join(lines)
