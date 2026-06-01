"""Tests for memory provenance (source_trace)."""

import tempfile
from pathlib import Path

from memstash.adapters.base import Adapter, ChatResult
from memstash.config import Config
from memstash.core import Recall
from memstash.store import Store


def _tmp_store() -> Store:
    d = tempfile.mkdtemp()
    return Store(Path(d) / "test.db")


def _tmp_recall(monkeypatch) -> Recall:
    d = tempfile.mkdtemp()
    monkeypatch.setenv("MEMSTASH_HOME", d)
    return Recall(Path(d) / "recall.db", config=Config())


def test_add_memory_stores_source_trace():
    s = _tmp_store()
    mid = s.add_memory("I like tea", source="auto", source_trace=42)
    assert s.get_memory(mid).source_trace == 42


def test_manual_memory_has_no_source():
    s = _tmp_store()
    mid = s.add_memory("manual note")
    assert s.get_memory(mid).source_trace is None


class FakeAdapter(Adapter):
    provider = "fake"
    def chat(self, prompt, system=None, history=None):
        return ChatResult("ok", 5, 2, self.model, self.provider)


def test_auto_captured_memory_links_to_chat_trace(monkeypatch):
    r = _tmp_recall(monkeypatch)
    import memstash.core as core
    monkeypatch.setattr(core, "get_adapter", lambda *a, **k: FakeAdapter("fake-model"))
    # heuristic extraction will capture this first-person preference
    r.chat("fake", "fake-model", "I prefer concise answers", auto_memory=True)
    mems = r.store.all_memories()
    assert mems, "a memory should have been auto-captured"
    m = mems[0]
    assert m.source == "auto"
    assert m.source_trace is not None
    # the linked trace is the chat call
    tr = r.store.get_trace(m.source_trace)
    assert tr is not None and tr["kind"] == "chat"
