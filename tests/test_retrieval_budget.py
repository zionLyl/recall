"""Tests for hybrid retrieval (FTS5 + RRF) and budget hard-stop."""

import tempfile
from pathlib import Path

import pytest

from recall.adapters.base import Adapter, ChatResult
from recall.config import Config
from recall.core import BudgetExceeded, Recall
from recall.memory import _rrf
from recall.store import Store, Trace


def _tmp_store() -> Store:
    d = tempfile.mkdtemp()
    return Store(Path(d) / "test.db")


def _tmp_recall(monkeypatch) -> Recall:
    d = tempfile.mkdtemp()
    monkeypatch.setenv("RECALL_HOME", d)
    return Recall(Path(d) / "recall.db", config=Config())


# ---- FTS5 / keyword search ----------------------------------------------
def test_fts_enabled_in_this_env():
    s = _tmp_store()
    assert s.fts_enabled is True   # CI/sqlite here ships FTS5


def test_fts_match_builder():
    assert Store._fts_match("a-share quant") == '"a" OR "share" OR "quant"'
    assert Store._fts_match("   ") == ""


def test_keyword_search_finds_and_ranks():
    s = _tmp_store()
    s.add_memory("I do A-share and HK quant research", tags=["work"])
    s.add_memory("I like deep-dish pizza", tags=["food"])
    hits = s.keyword_search("quant research")
    assert hits and "quant" in hits[0].content
    assert all("pizza" not in h.content for h in hits)


def test_keyword_search_scope_filter():
    s = _tmp_store()
    s.add_memory("quant in work", scope="work")
    s.add_memory("quant at home", scope="home")
    assert len(s.keyword_search("quant", scope="work")) == 1
    assert len(s.keyword_search("quant")) == 2


def test_keyword_search_special_chars_dont_crash():
    s = _tmp_store()
    s.add_memory("normal memory about cats")
    # FTS5 would choke on raw quotes/parens; the tokenizer must neutralize them.
    for q in ['cats "(', 'NEAR(', 'a OR b AND', '*** ???']:
        assert isinstance(s.keyword_search(q), list)


def test_fts_stays_in_sync_on_delete_and_edit():
    s = _tmp_store()
    mid = s.add_memory("tea preferences")
    assert s.keyword_search("tea")
    s.update_memory(mid, content="coffee preferences")
    assert not s.keyword_search("tea")          # old term gone from index
    assert s.keyword_search("coffee")           # new term indexed
    s.delete_memory(mid)
    assert not s.keyword_search("coffee")        # removed from index


# ---- RRF fusion ----------------------------------------------------------
def test_rrf_rewards_agreement():
    # id 1 ranks top in both lists; id 3 only appears once and lower.
    scores = _rrf([[1, 2, 3], [1, 3]])
    assert scores[1] > scores[3] > scores[2]


def test_rrf_empty():
    assert _rrf([]) == {}
    assert _rrf([[], []]) == {}


# ---- budget hard-stop ----------------------------------------------------
class FakeAdapter(Adapter):
    provider = "fake"
    def chat(self, prompt, system=None):
        return ChatResult("ok", 1, 1, self.model, self.provider)
    def stream(self, prompt, system=None):
        self.last_result = ChatResult("ok", 1, 1, self.model, self.provider)
        yield "ok"


def _patch_adapter(monkeypatch):
    import recall.core as core
    monkeypatch.setattr(core, "get_adapter", lambda *a, **k: FakeAdapter("fake-model"))


def test_budget_enforce_blocks_over_budget(monkeypatch):
    r = _tmp_recall(monkeypatch)
    _patch_adapter(monkeypatch)
    r.config.daily_budget_usd = 0.001
    r.config.budget_enforce = True
    r.store.add_trace(Trace(model="x", cost_usd=0.01))   # already over budget
    with pytest.raises(BudgetExceeded):
        r.chat("fake", "fake-model", "hi", auto_memory=False)


def test_budget_warn_only_does_not_block(monkeypatch):
    r = _tmp_recall(monkeypatch)
    _patch_adapter(monkeypatch)
    r.config.daily_budget_usd = 0.001
    r.config.budget_enforce = False                       # warn, don't enforce
    r.store.add_trace(Trace(model="x", cost_usd=0.01))
    out = r.chat("fake", "fake-model", "hi", auto_memory=False)
    assert out.text == "ok"
    assert out.budget_warning and "exceeded" in out.budget_warning.lower()


def test_budget_enforce_allows_under_budget(monkeypatch):
    r = _tmp_recall(monkeypatch)
    _patch_adapter(monkeypatch)
    r.config.daily_budget_usd = 100.0
    r.config.budget_enforce = True
    out = r.chat("fake", "fake-model", "hi", auto_memory=False)   # well under
    assert out.text == "ok"
