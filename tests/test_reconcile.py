"""Tests for ADD/UPDATE/DELETE/NOOP conflict resolution."""

import tempfile
from pathlib import Path

from engram.config import Config
from engram.core import Recall
from engram.reconcile import _parse_decision


def _tmp_recall(monkeypatch) -> Recall:
    d = tempfile.mkdtemp()
    monkeypatch.setenv("ENGRAM_HOME", d)
    r = Recall(Path(d) / "recall.db", config=Config())
    r.config.memory_ops = "llm"
    r.config.auto_memory = True
    return r


# ---- decision parsing ----------------------------------------------------
def test_parse_add():
    d = _parse_decision('{"op": "ADD", "id": null, "content": "I like tea"}')
    assert d == {"op": "ADD", "id": None, "content": "I like tea"}


def test_parse_update_with_string_id():
    d = _parse_decision('{"op":"update","id":"3","content":"I live in Berlin"}')
    assert d["op"] == "UPDATE" and d["id"] == 3 and d["content"] == "I live in Berlin"


def test_parse_delete_and_noop():
    assert _parse_decision('{"op":"DELETE","id":5,"content":null}')["op"] == "DELETE"
    assert _parse_decision('{"op":"NOOP","id":null,"content":null}')["op"] == "NOOP"


def test_parse_fenced_and_prose():
    d = _parse_decision('Here:\n```json\n{"op":"ADD","id":null,"content":"x"}\n```')
    assert d["op"] == "ADD"


def test_parse_garbage_and_bad_op():
    assert _parse_decision("nope") is None
    assert _parse_decision('{"op":"FROBNICATE"}') is None
    assert _parse_decision("") is None


# ---- apply paths (decision injected, no network) -------------------------
def _patch_decision(monkeypatch, op, mem_id=None, content=None):
    # _reconcile_capture does `from .reconcile import decide`, so patch it there.
    import engram.reconcile as rec
    monkeypatch.setattr(rec, "decide",
                        lambda *a, **k: ({"op": op, "id": mem_id, "content": content}, None))


def test_reconcile_add(monkeypatch):
    r = _tmp_recall(monkeypatch)
    _patch_decision(monkeypatch, "ADD", None, "I prefer tables")
    out = r._reconcile_capture("I prefer tables", "default", "openai", "gpt-4o-mini", None, None)
    assert out == "I prefer tables"
    assert len(r.store.all_memories()) == 1


def test_reconcile_update_supersedes(monkeypatch):
    r = _tmp_recall(monkeypatch)
    mid = r.remember("I live in NYC")
    _patch_decision(monkeypatch, "UPDATE", mid, "I live in Berlin")
    out = r._reconcile_capture("Actually I moved to Berlin", "default", "openai", "gpt-4o-mini", None, None)
    assert out.startswith(f"updated #{mid}")
    # old fact is superseded (kept as history, deactivated), new fact is active
    old = r.store.get_memory(mid)
    assert old.content == "I live in NYC" and old.active == 0
    actives = r.store.all_memories()
    assert len(actives) == 1 and actives[0].content == "I live in Berlin"


def test_reconcile_delete(monkeypatch):
    r = _tmp_recall(monkeypatch)
    mid = r.remember("I work at Acme")
    _patch_decision(monkeypatch, "DELETE", mid, None)
    out = r._reconcile_capture("I no longer work at Acme", "default", "openai", "gpt-4o-mini", None, None)
    assert out.startswith(f"forgot #{mid}")
    assert r.store.get_memory(mid).active == 0
    assert r.store.all_memories() == []              # soft-deleted


def test_reconcile_noop(monkeypatch):
    r = _tmp_recall(monkeypatch)
    r.remember("I like tea")
    _patch_decision(monkeypatch, "NOOP", None, None)
    out = r._reconcile_capture("I like tea", "default", "openai", "gpt-4o-mini", None, None)
    assert out is None
    assert len(r.store.all_memories()) == 1          # nothing added


def test_reconcile_falls_back_to_add_on_error(monkeypatch):
    r = _tmp_recall(monkeypatch)
    import engram.reconcile as rec

    def boom(*a, **k):
        raise RuntimeError("no key")

    monkeypatch.setattr(rec, "decide", boom)
    out = r._reconcile_capture("I enjoy hiking", "default", "openai", "gpt-4o-mini", None, None)
    assert out == "I enjoy hiking"                   # degraded to plain append
    assert len(r.store.all_memories()) == 1
