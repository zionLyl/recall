"""Tests for document ingestion."""

import tempfile
from pathlib import Path

import pytest

from memstash.config import Config
from memstash.core import Recall
from memstash.ingest import chunk_text, read_file


def _tmp_recall(monkeypatch) -> Recall:
    d = tempfile.mkdtemp()
    monkeypatch.setenv("MEMSTASH_HOME", d)
    return Recall(Path(d) / "recall.db", config=Config())


# ---- chunking ------------------------------------------------------------
def test_chunk_by_paragraph():
    text = "First paragraph here.\n\nSecond paragraph here.\n\n\nThird."
    chunks = chunk_text(text)
    assert chunks == ["First paragraph here.", "Second paragraph here.", "Third."]


def test_chunk_splits_long_paragraph_on_sentences():
    para = ("Sentence one is fairly long. Sentence two is also here. "
            "Sentence three closes it out.")
    chunks = chunk_text(para, max_chars=40)
    assert len(chunks) >= 2
    assert all(len(c) <= 40 for c in chunks)


def test_chunk_hard_splits_oversized_sentence():
    chunks = chunk_text("x" * 250, max_chars=100)
    assert all(len(c) <= 100 for c in chunks)
    assert "".join(chunks) == "x" * 250


def test_chunk_skips_blank():
    assert chunk_text("\n\n   \n\n") == []


# ---- read_file -----------------------------------------------------------
def test_read_txt(tmp_path=None):
    d = tempfile.mkdtemp()
    p = Path(d) / "note.md"
    p.write_text("# Title\n\nHello world.", encoding="utf-8")
    assert "Hello world." in read_file(p)


def test_read_missing_raises():
    with pytest.raises(FileNotFoundError):
        read_file("/no/such/file.txt")


# ---- end-to-end ingest ---------------------------------------------------
def test_ingest_stores_searchable_chunks(monkeypatch):
    r = _tmp_recall(monkeypatch)
    d = tempfile.mkdtemp()
    doc = Path(d) / "notes.md"
    doc.write_text(
        "I use Postgres for the analytics warehouse.\n\n"
        "The deploy runs every Friday at 9am.\n\n"
        "Our on-call rotation is weekly.",
        encoding="utf-8",
    )
    res = r.ingest(doc, scope="work")
    assert res["chunks"] == 3 and res["new"] == 3
    mems = r.store.all_memories(scope="work")
    assert len(mems) == 3
    assert all(m.source == "document" for m in mems)
    assert all("notes" in m.tags for m in mems)            # tagged with filename stem
    # searchable
    hits = r.recall_memories("Postgres warehouse", scope="work")
    assert any("Postgres" in h.content for h in hits)


def test_ingest_dedupes_on_reingest(monkeypatch):
    r = _tmp_recall(monkeypatch)
    d = tempfile.mkdtemp()
    doc = Path(d) / "a.txt"
    doc.write_text("Alpha fact.\n\nBeta fact.", encoding="utf-8")
    r.ingest(doc)
    res2 = r.ingest(doc)                 # second pass: all duplicates
    assert res2["chunks"] == 2 and res2["new"] == 0
    assert len(r.store.all_memories()) == 2
