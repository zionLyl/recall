"""Tests for v0.3.0 features: streaming, LLM extraction, MCP server."""

import tempfile
from pathlib import Path

from recall.adapters.base import Adapter, ChatResult, approx_tokens
from recall.config import Config
from recall.core import Recall
from recall.extract_llm import _parse


def _tmp_recall(monkeypatch) -> Recall:
    d = tempfile.mkdtemp()
    monkeypatch.setenv("RECALL_HOME", d)
    return Recall(Path(d) / "recall.db", config=Config())


class FakeAdapter(Adapter):
    """A streaming adapter that doesn't touch the network."""

    provider = "fake"
    REPLY = ["Hello", ", ", "world"]

    def chat(self, prompt, system=None, history=None):
        text = "".join(self.REPLY)
        return ChatResult(text, 7, 3, self.model, self.provider)

    def stream(self, prompt, system=None, history=None):
        for chunk in self.REPLY:
            yield chunk
        self.last_result = ChatResult("".join(self.REPLY), 7, 3, self.model, self.provider)


def _patch_adapter(monkeypatch):
    import recall.core as core
    monkeypatch.setattr(core, "get_adapter", lambda *a, **k: FakeAdapter("fake-model"))


# ---- streaming -----------------------------------------------------------
def test_stream_collects_chunks_and_traces(monkeypatch):
    r = _tmp_recall(monkeypatch)
    _patch_adapter(monkeypatch)
    seen = []
    out = r.stream("fake", "fake-model", "hi", on_token=seen.append, auto_memory=False)
    assert seen == FakeAdapter.REPLY            # streamed token-by-token
    assert out.text == "Hello, world"           # full text assembled
    assert out.input_tokens == 7 and out.output_tokens == 3
    assert r.stats()["calls"] == 1              # the call was traced


def test_default_stream_fallback_yields_whole_reply():
    # The base Adapter.stream() default wraps chat() for non-streaming backends.
    class Blocking(Adapter):
        provider = "blocking"
        def chat(self, prompt, system=None, history=None):
            return ChatResult("one shot", 1, 2, self.model, self.provider)

    a = Blocking("m")
    chunks = list(a.stream("hi"))
    assert chunks == ["one shot"]
    assert a.last_result.output_tokens == 2


def test_approx_tokens():
    assert approx_tokens("") == 1
    assert approx_tokens("a" * 40) == 10


# ---- LLM extraction parsing ---------------------------------------------
def test_llm_parse_plain_array():
    out = _parse('["I like tea", "My name is Zion"]', 5)
    assert out == ["I like tea", "My name is Zion"]


def test_llm_parse_code_fenced():
    raw = 'Sure!\n```json\n["I prefer concise answers"]\n```'
    assert _parse(raw, 5) == ["I prefer concise answers"]


def test_llm_parse_garbage_returns_empty():
    assert _parse("I could not find anything useful.", 5) == []
    assert _parse("", 5) == []


def test_llm_parse_respects_max_items():
    out = _parse('["a","b","c","d"]', 2)
    assert out == ["a", "b"]


def test_llm_extraction_mode_falls_back_on_error(monkeypatch):
    # extraction_mode='llm' but extractor raises -> heuristic fallback, no crash.
    r = _tmp_recall(monkeypatch)
    r.config.extraction_mode = "llm"
    import recall.core as core

    def boom(*a, **k):
        raise RuntimeError("no api key")

    monkeypatch.setattr(core, "extract_memories", lambda text: ["I prefer concise answers"])
    monkeypatch.setattr("recall.extract_llm.extract_memories_llm", boom)
    captured = r._auto_capture("I prefer concise answers", True, "default",
                               "openai", "gpt-4o-mini", None, None)
    assert captured == ["I prefer concise answers"]


# ---- MCP server ----------------------------------------------------------
def test_build_server_importable():
    import importlib.util
    if importlib.util.find_spec("mcp") is None:
        import pytest
        pytest.skip("mcp SDK not installed")
    from recall.mcp_server import build_server
    server = build_server()
    assert server is not None
