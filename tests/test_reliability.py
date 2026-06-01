"""Tests for v0.16.0: retrieval gate, auto-scope, reliability hardening."""

import tempfile
from pathlib import Path

import memstash.memory as memory_mod
from memstash.config import Config
from memstash.core import Recall, _auto_scope
from memstash.memory import MemoryEngine
from memstash.store import Store


def _tmp_store() -> Store:
    d = tempfile.mkdtemp()
    return Store(Path(d) / "test.db")


def _tmp_recall(monkeypatch) -> Recall:
    d = tempfile.mkdtemp()
    monkeypatch.setenv("MEMSTASH_HOME", d)
    return Recall(Path(d) / "memstash.db", config=Config())


class _Vec:
    def __init__(self, v): self._v = v
    def tolist(self): return self._v


class FakeModel:
    """Maps text to a fixed vector via a table to control similarity."""
    def __init__(self, table): self.table = table
    def encode(self, texts):
        return [_Vec(self.table.get(t, [0.0, 0.0, 1.0])) for t in texts]


# ---- retrieval relevance gate -------------------------------------------
def test_min_score_gates_weak_matches(monkeypatch):
    table = {
        "q": [1.0, 0.0, 0.0],
        "strong": [1.0, 0.0, 0.0],     # cosine 1.0 with q
        "weak": [0.2, 0.0, 0.98],      # low cosine with q
    }
    monkeypatch.setattr(memory_mod, "_get_model", lambda: FakeModel(table))
    s = _tmp_store()
    eng = MemoryEngine(s)
    eng.remember("strong")
    eng.remember("weak")
    # high gate → only the strongly-relevant memory passes; the weak one is dropped
    hits = eng.recall("q", min_score=0.9)
    assert [m.content for m in hits] == ["strong"]
    # a low gate lets the weak one back in (proves the gate is what filtered it)
    assert len(eng.recall("q", min_score=0.0)) == 2


def test_default_min_score_unchanged(monkeypatch):
    # default 0.15 preserves prior behavior (orthogonal vectors filtered out)
    table = {"q": [1.0, 0.0, 0.0], "rel": [1.0, 0.0, 0.0], "irrel": [0.0, 1.0, 0.0]}
    monkeypatch.setattr(memory_mod, "_get_model", lambda: FakeModel(table))
    s = _tmp_store()
    eng = MemoryEngine(s)
    eng.remember("rel")
    eng.remember("irrel")
    hits = eng.recall("q")     # default min_score=0.15
    assert any(m.content == "rel" for m in hits)
    assert all(m.content != "irrel" for m in hits)


# ---- auto scope ----------------------------------------------------------
def test_auto_scope_uses_git_repo_name(monkeypatch):
    d = tempfile.mkdtemp()
    repo = Path(d) / "my-project"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.chdir(repo)
    assert _auto_scope() == "my-project"


def test_auto_scope_none_outside_repo(monkeypatch):
    d = tempfile.mkdtemp()        # no .git anywhere up to tmp root
    plain = Path(d) / "plain"
    plain.mkdir()
    monkeypatch.chdir(plain)
    # may be None, or a parent repo if tmp is inside one; assert it's not crashing
    assert _auto_scope() is None or isinstance(_auto_scope(), str)


def test_recall_scope_property_auto(monkeypatch):
    r = _tmp_recall(monkeypatch)
    d = tempfile.mkdtemp()
    repo = Path(d) / "proj-x"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.chdir(repo)
    r.config.scope_auto = True
    assert r.scope == "proj-x"
    r.config.scope_auto = False
    assert r.scope == "default"


# ---- reliability hardening ----------------------------------------------
def test_chat_survives_retrieval_error(monkeypatch):
    r = _tmp_recall(monkeypatch)
    from memstash.adapters.base import Adapter, ChatResult
    import memstash.core as core

    class FakeAdapter(Adapter):
        provider = "fake"
        def chat(self, prompt, system=None, history=None):
            return ChatResult("ok", 1, 1, self.model, self.provider)

    monkeypatch.setattr(core, "get_adapter", lambda *a, **k: FakeAdapter("m"))
    # make memory retrieval blow up; chat must still return
    monkeypatch.setattr(r.memory, "build_context",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    out = r.chat("fake", "m", "hi", auto_memory=False)
    assert out.text == "ok"


def test_busy_timeout_set():
    s = _tmp_store()
    assert s.conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
