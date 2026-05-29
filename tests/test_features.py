"""Tests for the richer feature set: scopes, dedupe, extraction, config,
budget, export/import."""

import tempfile
from pathlib import Path

from recall.config import Config
from recall.core import Recall
from recall.extract import extract_memories
from recall.store import Store, Trace


def _tmp_recall(monkeypatch):
    d = tempfile.mkdtemp()
    monkeypatch.setenv("RECALL_HOME", d)
    return Recall(Path(d) / "recall.db", config=Config())


# ---- extraction ----------------------------------------------------------
def test_extract_english_preferences():
    text = "I prefer concise answers. What time is it? My timezone is UTC+8."
    out = extract_memories(text)
    assert any("concise" in m for m in out)
    assert any("timezone" in m for m in out)
    # the question must be skipped
    assert not any("time is it" in m for m in out)


def test_extract_chinese_preferences():
    text = "我喜欢简洁的回答。今天天气怎么样？我在做量化研究。"
    out = extract_memories(text)
    assert any("简洁" in m for m in out)
    assert any("量化" in m for m in out)


def test_extract_ignores_plain_text():
    assert extract_memories("The sky is blue and the sea is deep.") == []


# ---- scopes & dedupe -----------------------------------------------------
def test_scopes_isolated(monkeypatch):
    r = _tmp_recall(monkeypatch)
    r.remember("work fact", scope="work")
    r.remember("home fact", scope="home")
    assert len(r.store.all_memories(scope="work")) == 1
    assert len(r.store.all_memories(scope="home")) == 1
    assert len(r.store.all_memories()) == 2
    scopes = dict(r.store.list_scopes())
    assert scopes["work"] == 1 and scopes["home"] == 1


def test_dedupe(monkeypatch):
    r = _tmp_recall(monkeypatch)
    assert r.remember("same thing") is not None
    assert r.remember("same thing") is None  # duplicate skipped
    assert len(r.store.all_memories()) == 1


# ---- config --------------------------------------------------------------
def test_config_roundtrip(monkeypatch):
    d = tempfile.mkdtemp()
    monkeypatch.setenv("RECALL_HOME", d)
    cfg = Config()
    cfg.set("daily_budget_usd", "2.5")
    cfg.set("auto_memory", "false")
    cfg.set("default_provider", "deepseek")
    cfg.save()
    loaded = Config.load()
    assert loaded.daily_budget_usd == 2.5
    assert loaded.auto_memory is False
    assert loaded.default_provider == "deepseek"


# ---- budget --------------------------------------------------------------
def test_budget_warning(monkeypatch):
    r = _tmp_recall(monkeypatch)
    r.config.daily_budget_usd = 0.001
    # log a trace that exceeds budget
    r.store.add_trace(Trace(model="gpt-4o", cost_usd=0.01))
    warn = r._budget_warning()
    assert warn is not None and "exceeded" in warn.lower()


def test_no_budget_no_warning(monkeypatch):
    r = _tmp_recall(monkeypatch)
    r.config.daily_budget_usd = 0
    assert r._budget_warning() is None


# ---- export / import -----------------------------------------------------
def test_export_import(monkeypatch):
    r = _tmp_recall(monkeypatch)
    r.remember("alpha", tags=["x"], scope="work")
    r.remember("beta", scope="home")
    out = Path(tempfile.mkdtemp()) / "mem.json"
    n = r.export_memories(out)
    assert n == 2

    # import into a fresh store
    d2 = tempfile.mkdtemp()
    monkeypatch.setenv("RECALL_HOME", d2)
    r2 = Recall(Path(d2) / "recall.db", config=Config())
    imported = r2.import_memories(out)
    assert imported == 2
    assert len(r2.store.all_memories()) == 2


# ---- migration safety ----------------------------------------------------
def test_migration_idempotent(monkeypatch):
    d = tempfile.mkdtemp()
    monkeypatch.setenv("RECALL_HOME", d)
    p = Path(d) / "recall.db"
    s1 = Store(p)
    s1.add_memory("x")
    s1.close()
    # reopen should not error (migrations run again)
    s2 = Store(p)
    assert len(s2.all_memories()) == 1
