"""Core tests that run without any model API or embedding deps."""

import tempfile
from pathlib import Path

from recall.store import Store, Trace
from recall.memory import MemoryEngine
from recall.pricing import estimate_cost


def _tmp_store() -> Store:
    d = tempfile.mkdtemp()
    return Store(Path(d) / "test.db")


def test_add_and_list_memory():
    s = _tmp_store()
    mid = s.add_memory("I prefer concise answers", tags=["style"])
    assert mid == 1
    mems = s.all_memories()
    assert len(mems) == 1
    assert mems[0].content == "I prefer concise answers"
    assert mems[0].tags == ["style"]


def test_keyword_search():
    s = _tmp_store()
    s.add_memory("星弟 does A-share quant research", tags=["work"])
    s.add_memory("I like pizza", tags=["food"])
    hits = s.keyword_search("quant")
    assert len(hits) == 1
    assert "quant" in hits[0].content


def test_delete_memory():
    s = _tmp_store()
    mid = s.add_memory("temporary")
    assert s.delete_memory(mid) is True
    assert s.delete_memory(9999) is False
    assert s.all_memories() == []


def test_trace_and_stats():
    s = _tmp_store()
    s.add_trace(Trace(model="gpt-4o-mini", input_tokens=100, output_tokens=50, cost_usd=0.001, latency_ms=200))
    s.add_trace(Trace(model="gpt-4o-mini", input_tokens=200, output_tokens=80, cost_usd=0.002, latency_ms=300))
    st = s.stats()
    assert st["calls"] == 2
    assert st["input_tokens"] == 300
    assert st["output_tokens"] == 130
    assert abs(st["cost_usd"] - 0.003) < 1e-9
    assert st["by_model"][0]["model"] == "gpt-4o-mini"


def test_memory_engine_fallback():
    # Without embeddings installed this must fall back to keyword search.
    s = _tmp_store()
    eng = MemoryEngine(s)
    eng.remember("星弟 prefers tables", tags=["style"])
    hits = eng.recall("tables")
    assert len(hits) >= 1


def test_pricing_known_and_prefix():
    # exact
    c = estimate_cost("gpt-4o-mini", 1_000_000, 1_000_000)
    assert abs(c - (0.15 + 0.6)) < 1e-6
    # prefix match
    c2 = estimate_cost("gpt-4o-mini-2024-07-18", 1_000_000, 0)
    assert abs(c2 - 0.15) < 1e-6
    # unknown -> 0
    assert estimate_cost("totally-unknown-model", 1000, 1000) == 0.0


def test_provider_registry_and_base_urls():
    from recall.adapters import BASE_URLS, KEY_ENV, REGISTRY, get_adapter

    # Broad provider coverage (ECC-style).
    assert len(REGISTRY) >= 20
    for p in ("openai", "anthropic", "gemini", "deepseek", "qwen", "moonshot",
              "zhipu", "mistral", "xai", "groq", "openrouter", "ollama"):
        assert p in REGISTRY, f"missing provider {p}"

    # OpenAI-compatible providers get a default base URL injected.
    a = get_adapter("deepseek", "deepseek-chat", api_key="x")
    assert a.base_url == BASE_URLS["deepseek"]

    # Unknown provider raises clearly.
    import pytest
    with pytest.raises(ValueError):
        get_adapter("nope", "model")

    # Every provider has a key env mapping (except generic compatible default).
    assert KEY_ENV["openai"] == "OPENAI_API_KEY"


def test_build_context():
    s = _tmp_store()
    eng = MemoryEngine(s)
    eng.remember("I prefer concise answers")
    ctx = eng.build_context("concise")
    assert "remember" in ctx.lower()
    assert "concise" in ctx
