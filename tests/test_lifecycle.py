"""Tests for memory lifecycle: hit tracking, soft-forget, prune, recency rank."""

import tempfile
import time
from pathlib import Path

import engram.memory as memory_mod
from engram.memory import MemoryEngine, _rrf
from engram.store import Store


def _tmp_store() -> Store:
    d = tempfile.mkdtemp()
    return Store(Path(d) / "test.db")


# ---- hit tracking --------------------------------------------------------
def test_recall_touches_hits():
    s = _tmp_store()
    eng = MemoryEngine(s)
    mid = eng.remember("I do quant research")
    assert s.get_memory(mid).hit_count == 0
    eng.recall("quant")                       # keyword path (no embeddings)
    m = s.get_memory(mid)
    assert m.hit_count == 1 and m.last_used is not None
    eng.recall("quant")
    assert s.get_memory(mid).hit_count == 2


# ---- soft delete + active filtering -------------------------------------
def test_soft_delete_hides_from_search_and_list():
    s = _tmp_store()
    eng = MemoryEngine(s)
    mid = eng.remember("forget me about pizza")
    assert s.soft_delete(mid) is True
    assert s.get_memory(mid).active == 0          # row still there
    assert s.all_memories() == []                 # excluded by default
    assert len(s.all_memories(include_inactive=True)) == 1
    assert eng.recall("pizza") == []              # excluded from retrieval
    # soft-deleting again is a no-op (already inactive)
    assert s.soft_delete(mid) is False


def test_soft_deleted_content_can_be_re_added():
    # exact-dedupe should ignore inactive rows.
    s = _tmp_store()
    eng = MemoryEngine(s)
    mid = eng.remember("same thing")
    s.soft_delete(mid)
    assert eng.remember("same thing") is not None  # not blocked by the dead row


# ---- prune ---------------------------------------------------------------
def test_prune_unused():
    s = _tmp_store()
    eng = MemoryEngine(s)
    eng.remember("quant research notes")
    eng.remember("unrelated note about cats")
    eng.recall("quant")                           # only the quant memory gets a hit
    n = s.prune(unused=True)
    assert n == 1
    remaining = [m.content for m in s.all_memories()]
    assert remaining == ["quant research notes"]


def test_prune_older_than():
    s = _tmp_store()
    mid = s.add_memory("ancient")
    # backdate it 10 days
    s.conn.execute("UPDATE memories SET created_at = ? WHERE id = ?",
                   (time.time() - 10 * 86400, mid))
    s.conn.commit()
    s.add_memory("fresh")
    assert s.prune(older_than_days=7) == 1
    assert [m.content for m in s.all_memories()] == ["fresh"]


# ---- recency-weighted ranking -------------------------------------------
class _Vec:
    def __init__(self, v): self._v = v
    def tolist(self): return self._v


class FakeModel:
    """Maps text to a vector by a lookup so we can control similarity."""
    def __init__(self, table): self.table = table
    def encode(self, texts):
        return [_Vec(self.table.get(t, [0.0, 0.0, 1.0])) for t in texts]


def test_recency_weight_breaks_ties(monkeypatch):
    # Two memories equally relevant to the query; recency should order them.
    table = {
        "q": [1.0, 0.0, 0.0],
        "older fact": [1.0, 0.0, 0.0],
        "newer fact": [1.0, 0.0, 0.0],
    }
    monkeypatch.setattr(memory_mod, "_get_model", lambda: FakeModel(table))
    s = _tmp_store()
    eng = MemoryEngine(s)
    older = eng.remember("older fact")
    newer = eng.remember("newer fact")
    # Make `newer` more recently used.
    s.touch_memories([newer])
    hits = eng.recall("q", recency_weight=2.0)
    ids = [m.id for m in hits]
    assert ids[0] == newer and newer in ids and older in ids


def test_rrf_weights():
    # Down-weighting the second ranking lets the first dominate.
    s = _rrf([[1], [2]], weights=[1.0, 0.1])
    assert s[1] > s[2]
