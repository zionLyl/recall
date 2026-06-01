"""Tests for memory editing + similarity merge/dedupe (v0.3.0)."""

import tempfile
from pathlib import Path

import memstash.memory as memory_mod
from memstash.memory import MemoryEngine, _pack
from memstash.store import Store


def _tmp_store() -> Store:
    d = tempfile.mkdtemp()
    return Store(Path(d) / "test.db")


class _Vec:
    def __init__(self, vec):
        self._vec = vec
    def tolist(self):
        return self._vec


class FakeModel:
    """Encodes every text to the same fixed vector (cosine == 1.0)."""
    def __init__(self, vec):
        self.vec = vec
    def encode(self, texts):
        return [_Vec(self.vec) for _ in texts]


# ---- editing -------------------------------------------------------------
def test_edit_content_and_tags():
    s = _tmp_store()
    eng = MemoryEngine(s)
    mid = eng.remember("I like coffee", tags=["food"])
    assert eng.edit(mid, content="I like tea", tags=["drink", "pref"]) is True
    m = s.get_memory(mid)
    assert m.content == "I like tea"
    assert m.tags == ["drink", "pref"]


def test_edit_tags_only_keeps_content():
    s = _tmp_store()
    eng = MemoryEngine(s)
    mid = eng.remember("keep me")
    assert eng.edit(mid, tags=["x"]) is True
    m = s.get_memory(mid)
    assert m.content == "keep me" and m.tags == ["x"]


def test_edit_missing_returns_false():
    s = _tmp_store()
    eng = MemoryEngine(s)
    assert eng.edit(9999, content="nope") is False


def test_get_memory_none():
    s = _tmp_store()
    assert s.get_memory(123) is None


def test_update_memory_noop():
    s = _tmp_store()
    mid = s.add_memory("x")
    assert s.update_memory(mid) is False  # nothing to set


# ---- similarity dedupe (with a fake embedding model) ---------------------
def test_remember_suppresses_near_duplicate(monkeypatch):
    monkeypatch.setattr(memory_mod, "_get_model", lambda: FakeModel([1.0, 0.0, 0.0]))
    s = _tmp_store()
    eng = MemoryEngine(s)
    assert eng.remember("I like tea", similarity_threshold=0.95) is not None
    # Different text, identical embedding → cosine 1.0 → suppressed.
    assert eng.remember("I really like tea", similarity_threshold=0.95) is None
    assert len(s.all_memories()) == 1


def test_remember_no_threshold_keeps_both(monkeypatch):
    monkeypatch.setattr(memory_mod, "_get_model", lambda: FakeModel([1.0, 0.0, 0.0]))
    s = _tmp_store()
    eng = MemoryEngine(s)
    eng.remember("a", similarity_threshold=0.0)
    eng.remember("b", similarity_threshold=0.0)   # threshold off → both stored
    assert len(s.all_memories()) == 2


def test_dedupe_merges_similar_and_unions_tags(monkeypatch):
    monkeypatch.setattr(memory_mod, "_get_model", lambda: FakeModel([1.0, 0.0]))
    s = _tmp_store()
    # Two near-identical (same vector) + one orthogonal.
    s.add_memory("I like tea", tags=["a"], embedding=_pack([1.0, 0.0]))
    s.add_memory("I like tea a lot", tags=["b"], embedding=_pack([1.0, 0.0]))
    s.add_memory("I work in finance", tags=["c"], embedding=_pack([0.0, 1.0]))
    eng = MemoryEngine(s)
    merges = eng.dedupe(threshold=0.9)
    assert len(merges) == 1
    assert len(merges[0]["removed"]) == 1
    remaining = s.all_memories()
    assert len(remaining) == 2                    # one duplicate removed
    kept = s.get_memory(merges[0]["kept"])
    assert set(kept.tags) == {"a", "b"}           # tags unioned onto canonical


def test_dedupe_no_embeddings_returns_empty():
    # Without an embedding model, dedupe is a no-op (exact-only world).
    s = _tmp_store()
    s.add_memory("x")
    s.add_memory("y")
    eng = MemoryEngine(s)
    assert eng.dedupe() == []
    assert len(s.all_memories()) == 2
