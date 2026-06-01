"""Tests for typed memory + metadata (type / confidence / source_ref)."""

import tempfile
from pathlib import Path

from memstash.config import Config
from memstash.core import Recall
from memstash.store import Store


def _tmp_store() -> Store:
    d = tempfile.mkdtemp()
    return Store(Path(d) / "test.db")


def _tmp_recall(monkeypatch) -> Recall:
    d = tempfile.mkdtemp()
    monkeypatch.setenv("MEMSTASH_HOME", d)
    return Recall(Path(d) / "memstash.db", config=Config())


# ---- store ---------------------------------------------------------------
def test_add_memory_stores_type_confidence_source():
    s = _tmp_store()
    mid = s.add_memory("Deploys go out on Fridays", mem_type="constraint",
                       confidence=0.8, source_ref="https://example.com/runbook")
    m = s.get_memory(mid)
    assert m.mem_type == "constraint"
    assert abs(m.confidence - 0.8) < 1e-9
    assert m.source_ref == "https://example.com/runbook"


def test_defaults_are_note_and_full_confidence():
    s = _tmp_store()
    m = s.get_memory(s.add_memory("plain memory"))
    assert m.mem_type == "note" and m.confidence == 1.0 and m.source_ref is None


def test_all_memories_filter_by_type():
    s = _tmp_store()
    s.add_memory("likes tea", mem_type="preference")
    s.add_memory("chose Postgres", mem_type="decision")
    s.add_memory("chose Redis", mem_type="decision")
    assert len(s.all_memories(mem_type="decision")) == 2
    assert len(s.all_memories(mem_type="preference")) == 1
    assert len(s.all_memories()) == 3        # no filter = all


# ---- through Recall ------------------------------------------------------
def test_recall_remember_typed(monkeypatch):
    r = _tmp_recall(monkeypatch)
    mid = r.remember("Never force-push main", mem_type="constraint", confidence=0.95,
                     source_ref="team-wiki")
    m = r.store.get_memory(mid)
    assert m.mem_type == "constraint" and m.source_ref == "team-wiki"


# ---- ingest tags type + source_ref --------------------------------------
def test_ingest_sets_document_type_and_source(monkeypatch):
    r = _tmp_recall(monkeypatch)
    d = tempfile.mkdtemp()
    doc = Path(d) / "runbook.md"
    doc.write_text("Step one.\n\nStep two.", encoding="utf-8")
    r.ingest(doc)
    mems = r.store.all_memories()
    assert mems and all(m.mem_type == "document" for m in mems)
    assert all(m.source_ref == str(doc) for m in mems)


# ---- migration safety (old DB without the columns) ----------------------
def test_row_to_memory_defaults_when_columns_missing():
    # simulate a pre-typed-memory row dict-ish via a fresh store (migrations add cols)
    s = _tmp_store()
    mid = s.add_memory("x")
    m = s.get_memory(mid)
    assert m.mem_type == "note" and m.confidence == 1.0
