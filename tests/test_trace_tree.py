"""Tests for the local trace tree (session_id / parent_id / kind)."""

import tempfile
from pathlib import Path

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


class FakeAdapter(Adapter):
    provider = "fake"
    def chat(self, prompt, system=None, history=None):
        return ChatResult("ok", 5, 2, self.model, self.provider)


def _patch_adapter(monkeypatch):
    import engram.core as core
    monkeypatch.setattr(core, "get_adapter", lambda *a, **k: FakeAdapter("fake-model"))


# ---- store grouping ------------------------------------------------------
def test_recent_sessions_groups_children_with_totals():
    s = _tmp_store()
    pid = s.add_trace(Trace(model="m", input_tokens=10, output_tokens=5,
                            cost_usd=0.01, session_id="s1", kind="chat"))
    s.add_trace(Trace(model="m", input_tokens=3, output_tokens=1, cost_usd=0.002,
                      session_id="s1", parent_id=pid, kind="extract"))
    sessions = s.recent_sessions()
    assert len(sessions) == 1
    sess = sessions[0]
    assert sess["parent"]["kind"] == "chat"
    assert len(sess["children"]) == 1
    assert sess["children"][0]["kind"] == "extract"
    assert abs(sess["total_cost"] - 0.012) < 1e-9
    assert sess["total_tokens"] == 19


# ---- core wiring ---------------------------------------------------------
def test_chat_records_session_and_kind(monkeypatch):
    r = _tmp_recall(monkeypatch)
    _patch_adapter(monkeypatch)
    r.chat("fake", "fake-model", "hi", auto_memory=False)
    sessions = r.recent_sessions()
    assert len(sessions) == 1
    assert sessions[0]["parent"]["kind"] == "chat"
    assert sessions[0]["parent"]["session_id"]          # a session id was set
    assert sessions[0]["children"] == []                # nothing spawned


def test_extraction_call_is_child_of_chat(monkeypatch):
    r = _tmp_recall(monkeypatch)
    _patch_adapter(monkeypatch)
    r.config.extraction_mode = "llm"
    import engram.extract_llm as ex
    monkeypatch.setattr(
        ex, "extract_memories_llm",
        lambda *a, **k: (["I like tea"], ChatResult("[\"I like tea\"]", 4, 3, "fake-model", "fake")),
    )
    r.chat("fake", "fake-model", "I like tea", auto_memory=True)
    sessions = r.recent_sessions()
    assert len(sessions) == 1                            # one turn tree
    kinds = [c["kind"] for c in sessions[0]["children"]]
    assert "extract" in kinds                            # extraction nested under chat
