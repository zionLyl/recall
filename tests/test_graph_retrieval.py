"""Tests for graph-aware retrieval (graph-lite wired into recall)."""

import tempfile
from pathlib import Path

import engram.memory as memory_mod
from engram.memory import MemoryEngine
from engram.store import Store


def _tmp_store() -> Store:
    d = tempfile.mkdtemp()
    return Store(Path(d) / "test.db")


class _Vec:
    def __init__(self, v): self._v = v
    def tolist(self): return self._v


class FakeModel:
    """Everything embeds orthogonally to the query unless listed, so semantic
    search contributes nothing — isolating the graph signal."""
    def __init__(self, table=None): self.table = table or {}
    def encode(self, texts):
        return [_Vec(self.table.get(t, [0.0, 0.0, 1.0])) for t in texts]


def test_graph_expand_finds_neighbor_memories():
    s = _tmp_store()
    # Acme is in Beijing; a memory about Beijing exists but doesn't mention Acme.
    s.add_relation("Acme", "is in", "Beijing", scope="default")
    s.add_memory("The Beijing office has 200 people")
    eng = MemoryEngine(s)
    hits = eng._graph_expand("tell me about Acme", scope="default", limit=10)
    assert any("Beijing office" in m.content for m in hits)


def test_graph_expand_no_match_returns_empty():
    s = _tmp_store()
    s.add_relation("Acme", "is in", "Beijing")
    eng = MemoryEngine(s)
    assert eng._graph_expand("unrelated query about cats", scope="default", limit=10) == []


def test_graph_weight_surfaces_connected_memory(monkeypatch):
    # Query mentions Acme; semantic+keyword won't find the Beijing memory, but
    # the graph link Acme→Beijing should pull it in when graph_weight > 0.
    monkeypatch.setattr(memory_mod, "_get_model", lambda: FakeModel())
    s = _tmp_store()
    s.add_relation("Acme", "is in", "Beijing")
    s.add_memory("The Beijing office has 200 people")
    eng = MemoryEngine(s)
    without = eng.recall("what about Acme", graph_weight=0.0)
    with_graph = eng.recall("what about Acme", graph_weight=2.0)
    assert not any("Beijing" in m.content for m in without)
    assert any("Beijing" in m.content for m in with_graph)
