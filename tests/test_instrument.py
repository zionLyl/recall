"""Tests for reverse OTel ingestion (capturing third-party LLM spans)."""

import tempfile
from pathlib import Path

import pytest

from memstash.instrument import _record_spans, span_to_trace
from memstash.store import Store


def _tmp_store() -> Store:
    d = tempfile.mkdtemp()
    return Store(Path(d) / "test.db")


class FakeSpan:
    def __init__(self, attributes, name="", start_time=0, end_time=0):
        self.attributes = attributes
        self.name = name
        self.start_time = start_time
        self.end_time = end_time


_LLM_ATTRS = {
    "openinference.span.kind": "LLM",
    "llm.model_name": "gpt-4o-mini",
    "llm.provider": "openai",
    "llm.token_count.prompt": 100,
    "llm.token_count.completion": 50,
    "input.value": "hi",
    "output.value": "hello",
}


# ---- mapping -------------------------------------------------------------
def test_span_to_trace_maps_llm():
    t = span_to_trace(_LLM_ATTRS, "ChatOpenAI", duration_ms=420)
    assert t is not None
    assert t.model == "gpt-4o-mini" and t.provider == "openai"
    assert t.input_tokens == 100 and t.output_tokens == 50
    assert t.latency_ms == 420 and t.kind == "instrumented"
    assert t.cost_usd > 0          # priced via the maintained map


def test_span_to_trace_ignores_non_llm():
    assert span_to_trace({"openinference.span.kind": "CHAIN"}) is None
    assert span_to_trace({}) is None


def test_span_to_trace_handles_missing_tokens():
    t = span_to_trace({"openinference.span.kind": "LLM", "llm.model_name": "x"})
    assert t is not None and t.input_tokens == 0 and t.output_tokens == 0


# ---- recording -----------------------------------------------------------
def test_record_spans_writes_only_llm():
    s = _tmp_store()
    spans = [
        FakeSpan(_LLM_ATTRS, "ChatOpenAI", start_time=1_000_000, end_time=421_000_000),
        FakeSpan({"openinference.span.kind": "CHAIN"}, "chain"),
        FakeSpan(_LLM_ATTRS, "ChatOpenAI"),
    ]
    n = _record_spans(spans, s)
    assert n == 2
    rows = s.recent_traces()
    assert len(rows) == 2
    assert all(r["kind"] == "instrumented" for r in rows)
    # duration computed from start/end (ns → ms)
    assert any(r["latency_ms"] == 420 for r in rows)


# ---- full integration (requires the OTel SDK) ----------------------------
def test_instrument_end_to_end():
    pytest.importorskip("opentelemetry")
    from opentelemetry import trace
    from memstash.instrument import instrument

    d = tempfile.mkdtemp()
    db = Path(d) / "recall.db"
    instrument(db_path=db, auto=False)
    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("ChatOpenAI") as span:
        for k, v in _LLM_ATTRS.items():
            span.set_attribute(k, v)
    # SimpleSpanProcessor exports synchronously on span end
    rows = Store(db).recent_traces()
    assert any(r["kind"] == "instrumented" and r["model"] == "gpt-4o-mini" for r in rows)
