"""Tests for retrieval robustness & scale: vectorized cosine, dim safety, WAL."""

import tempfile
from pathlib import Path

import engram.memory as memory_mod
from engram.memory import MemoryEngine, _cosine, _pack, _semantic_rank
from engram.store import Store


def _tmp_store() -> Store:
    d = tempfile.mkdtemp()
    return Store(Path(d) / "test.db")


# ---- dimension safety ----------------------------------------------------
def test_cosine_dim_mismatch_is_zero():
    assert _cosine([1.0, 0.0], [1.0, 0.0, 0.0]) == 0.0   # different dims → 0
    assert _cosine([1.0, 0.0], [1.0, 0.0]) == 1.0


def test_semantic_rank_skips_mismatched_dims():
    s = _tmp_store()
    s.add_memory("2d-a", embedding=_pack([1.0, 0.0]))
    s.add_memory("3d-old-model", embedding=_pack([1.0, 0.0, 0.0]))  # stale dim
    rows = s.all_memories_with_embeddings()
    ranked = _semantic_rank([1.0, 0.0], rows)
    contents = [r[1] for r in ranked]
    assert "2d-a" in contents
    assert "3d-old-model" not in contents          # skipped, not silently wrong


def test_semantic_rank_matches_pure_python(monkeypatch):
    # The numpy fast path and the pure-Python fallback must agree.
    s = _tmp_store()
    s.add_memory("a", embedding=_pack([1.0, 0.0, 0.0]))
    s.add_memory("b", embedding=_pack([0.0, 1.0, 0.0]))
    s.add_memory("c", embedding=_pack([0.6, 0.8, 0.0]))
    rows = list(s.all_memories_with_embeddings())
    q = [1.0, 0.0, 0.0]

    fast = {r[1]: round(r[6], 4) for r in _semantic_rank(q, rows)}

    # Force the fallback by making `import numpy` fail inside the helper.
    import builtins
    real_import = builtins.__import__
    def no_numpy(name, *a, **k):
        if name == "numpy":
            raise ImportError("blocked")
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", no_numpy)
    slow = {r[1]: round(r[6], 4) for r in _semantic_rank(q, rows)}

    assert fast == slow
    assert fast["a"] == 1.0 and fast["b"] == 0.0 and abs(fast["c"] - 0.6) < 1e-3


def test_recall_ignores_stale_dim_embeddings(monkeypatch):
    # Switching embedding models leaves old-dim vectors; recall must not crash
    # or mis-rank — it should just use the comparable ones.
    monkeypatch.setattr(memory_mod, "_get_model", lambda: _FakeModel([1.0, 0.0]))
    s = _tmp_store()
    s.add_memory("old model entry", embedding=_pack([1.0, 0.0, 0.0]))  # 3-dim
    eng = MemoryEngine(s)
    eng.remember("new entry about tea")                                # 2-dim now
    hits = eng.recall("tea")
    assert all("old model entry" != h.content for h in hits)


class _FakeModel:
    def __init__(self, vec): self.vec = vec
    def encode(self, texts):
        class V:
            def __init__(self, v): self._v = v
            def tolist(self): return self._v
        return [V(self.vec) for _ in texts]


# ---- WAL ----------------------------------------------------------------
def test_wal_mode_enabled():
    s = _tmp_store()
    mode = s.conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"
