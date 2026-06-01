"""Tests for the pluggable embedding backend (local vs OpenAI-compatible API)."""

import json
import tempfile
from pathlib import Path

import engram.memory as memory_mod
from engram.memory import EmbedConfig, MemoryEngine, _embed_api
from engram.store import Store


def _tmp_store() -> Store:
    d = tempfile.mkdtemp()
    return Store(Path(d) / "test.db")


class _FakeResp:
    def __init__(self, payload): self._b = json.dumps(payload).encode()
    def read(self): return self._b
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_embed_api_parses_and_orders(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=30):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data)
        # return out-of-order indices to verify sorting
        return _FakeResp({"data": [
            {"index": 1, "embedding": [0.0, 1.0]},
            {"index": 0, "embedding": [1.0, 0.0]},
        ]})

    monkeypatch.setattr(memory_mod.urllib.request, "urlopen", fake_urlopen)
    vecs = _embed_api(["a", "b"], "http://localhost:11434/v1", "nomic-embed-text")
    assert vecs == [[1.0, 0.0], [0.0, 1.0]]          # reordered by index
    assert captured["url"].endswith("/embeddings")
    assert captured["body"]["model"] == "nomic-embed-text"


def test_embed_api_returns_none_on_error(monkeypatch):
    def boom(req, timeout=30):
        raise OSError("connection refused")
    monkeypatch.setattr(memory_mod.urllib.request, "urlopen", boom)
    assert _embed_api(["x"], "http://localhost:1/v1", "m") is None


def test_api_backend_has_embeddings_without_local_model():
    # API backend reports available purely from config — no model download.
    s = _tmp_store()
    cfg = EmbedConfig(backend="api", base_url="http://localhost:11434/v1", model="nomic-embed-text")
    eng = MemoryEngine(s, embed_cfg=cfg)
    assert eng.has_embeddings is True


def test_api_backend_incomplete_config_not_available():
    s = _tmp_store()
    eng = MemoryEngine(s, embed_cfg=EmbedConfig(backend="api"))  # no base_url/model
    assert eng.has_embeddings is False


def test_engine_uses_api_backend_for_recall(monkeypatch):
    # Drive a full remember+recall through the API backend with a fake endpoint.
    table = {"tea": [1.0, 0.0], "I like tea": [1.0, 0.0], "I work in finance": [0.0, 1.0]}

    def fake_urlopen(req, timeout=30):
        inp = json.loads(req.data)["input"]
        return _FakeResp({"data": [
            {"index": i, "embedding": table.get(t, [0.0, 0.0])} for i, t in enumerate(inp)
        ]})

    monkeypatch.setattr(memory_mod.urllib.request, "urlopen", fake_urlopen)
    s = _tmp_store()
    cfg = EmbedConfig(backend="api", base_url="http://x/v1", model="m")
    eng = MemoryEngine(s, embed_cfg=cfg)
    eng.remember("I like tea")
    eng.remember("I work in finance")
    hits = eng.recall("tea")
    assert hits and hits[0].content == "I like tea"   # semantic match via API embeddings


def test_default_backend_is_local():
    s = _tmp_store()
    eng = MemoryEngine(s)
    assert eng.embed_cfg.backend == "local"
