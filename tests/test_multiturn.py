"""Tests for multi-turn conversation history threading."""

import tempfile
from pathlib import Path

from recall.adapters.base import Adapter, ChatResult
from recall.config import Config
from recall.core import Recall


def _tmp_recall(monkeypatch) -> Recall:
    d = tempfile.mkdtemp()
    monkeypatch.setenv("RECALL_HOME", d)
    return Recall(Path(d) / "recall.db", config=Config())


class RecordingAdapter(Adapter):
    provider = "fake"
    seen_history = None

    def chat(self, prompt, system=None, history=None):
        RecordingAdapter.seen_history = history
        return ChatResult("reply", 3, 2, self.model, self.provider)


def test_history_threaded_to_adapter(monkeypatch):
    r = _tmp_recall(monkeypatch)
    import recall.core as core
    monkeypatch.setattr(core, "get_adapter", lambda *a, **k: RecordingAdapter("m"))
    convo = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    r.chat("fake", "m", "how are you?", history=convo, auto_memory=False)
    assert RecordingAdapter.seen_history == convo


def test_no_history_defaults_none(monkeypatch):
    r = _tmp_recall(monkeypatch)
    import recall.core as core
    monkeypatch.setattr(core, "get_adapter", lambda *a, **k: RecordingAdapter("m"))
    RecordingAdapter.seen_history = "sentinel"
    r.chat("fake", "m", "hi", auto_memory=False)
    assert RecordingAdapter.seen_history is None


def test_openai_messages_include_history():
    from recall.adapters.openai_adapter import OpenAIAdapter
    a = OpenAIAdapter("gpt-4o-mini")
    msgs = a._messages(
        "now", system="sys",
        history=[{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}],
    )
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "user"]
    assert msgs[-1]["content"] == "now"


def test_gemini_contents_roles():
    from recall.adapters.gemini_adapter import GeminiAdapter
    contents = GeminiAdapter._contents(
        "now", [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}],
    )
    assert [c["role"] for c in contents] == ["user", "model", "user"]
    assert contents[-1]["parts"] == ["now"]
