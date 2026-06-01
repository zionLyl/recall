"""Tests for eval ergonomics: saved suites, summary, auto-eval."""

import tempfile
from pathlib import Path

import pytest

from engram.adapters.base import Adapter, ChatResult
from engram.config import Config
from engram.core import Recall
from engram.store import Store, Trace


def _tmp_store() -> Store:
    d = tempfile.mkdtemp()
    return Store(Path(d) / "test.db")


def _tmp_recall(monkeypatch) -> Recall:
    d = tempfile.mkdtemp()
    monkeypatch.setenv("ENGRAM_HOME", d)
    return Recall(Path(d) / "recall.db", config=Config())


# ---- suite store ---------------------------------------------------------
def test_suite_save_get_list_delete():
    s = _tmp_store()
    s.save_suite("safety", {"not_contains": "password", "max_tokens": 500})
    assert s.get_suite("safety") == {"not_contains": "password", "max_tokens": 500}
    assert s.list_suites()[0][0] == "safety"
    assert s.delete_suite("safety") is True
    assert s.get_suite("safety") is None


def test_suite_upsert():
    s = _tmp_store()
    s.save_suite("x", {"contains": "a"})
    s.save_suite("x", {"contains": "b"})
    assert s.get_suite("x") == {"contains": "b"}
    assert len(s.list_suites()) == 1


# ---- run_suite -----------------------------------------------------------
def test_run_suite_applies_spec(monkeypatch):
    r = _tmp_recall(monkeypatch)
    tid = r.store.add_trace(Trace(model="m", completion="The answer is 42.", output_tokens=8))
    r.store.save_suite("basics", {"contains": "42", "max_tokens": 100})
    results = r.run_suite(tid, "basics")
    assert {x["name"] for x in results} == {"contains", "max_tokens"}
    assert all(x["passed"] for x in results)


def test_run_suite_overrides_win(monkeypatch):
    r = _tmp_recall(monkeypatch)
    tid = r.store.add_trace(Trace(model="m", completion="hello world", output_tokens=2))
    r.store.save_suite("s", {"contains": "hello"})
    results = r.run_suite(tid, "s", contains="missing")   # override → should fail
    assert results[0]["passed"] is False


def test_run_suite_unknown_raises(monkeypatch):
    r = _tmp_recall(monkeypatch)
    tid = r.store.add_trace(Trace(model="m", completion="x"))
    with pytest.raises(ValueError):
        r.run_suite(tid, "nope")


# ---- summary in stats ----------------------------------------------------
def test_stats_includes_eval_summary(monkeypatch):
    r = _tmp_recall(monkeypatch)
    tid = r.store.add_trace(Trace(model="m", completion="ok answer", output_tokens=3))
    r.evaluate(tid, contains="ok")
    summary = r.stats()["evals"]
    assert summary["count"] == 1 and summary["passed"] == 1


# ---- auto-eval after chat ------------------------------------------------
class FakeAdapter(Adapter):
    provider = "fake"
    def chat(self, prompt, system=None, history=None):
        return ChatResult("the capital is Paris", 5, 4, self.model, self.provider)


def test_auto_eval_runs_configured_suite(monkeypatch):
    r = _tmp_recall(monkeypatch)
    import engram.core as core
    monkeypatch.setattr(core, "get_adapter", lambda *a, **k: FakeAdapter("fake-model"))
    r.store.save_suite("q", {"contains": "Paris"})
    r.config.auto_eval_suite = "q"
    r.chat("fake", "fake-model", "capital of France?", auto_memory=False)
    # the chat trace should now have an eval attached
    assert r.stats()["evals"]["count"] == 1
