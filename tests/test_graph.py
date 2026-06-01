"""Tests for graph-lite: relations store + triple extraction parser."""

import tempfile
from pathlib import Path

from memstash.graph_extract import _parse
from memstash.store import Store


def _tmp_store() -> Store:
    d = tempfile.mkdtemp()
    return Store(Path(d) / "test.db")


# ---- relations store -----------------------------------------------------
def test_add_and_query_relation():
    s = _tmp_store()
    s.add_relation("Zion", "works at", "Acme", scope="work")
    s.add_relation("Acme", "is in", "Beijing", scope="work")
    assert len(s.all_relations()) == 2
    # query by entity (subject or object, case-insensitive)
    acme = s.relations_for("acme")
    assert len(acme) == 2
    assert {r["predicate"] for r in acme} == {"works at", "is in"}


def test_relation_dedupe_and_blank():
    s = _tmp_store()
    assert s.add_relation("A", "rel", "B") is not None
    assert s.add_relation("A", "rel", "B") is None      # exact dup skipped
    assert s.add_relation("A", "", "B") is None         # blank predicate rejected
    assert len(s.all_relations()) == 1


def test_relations_scope_filter():
    s = _tmp_store()
    s.add_relation("X", "r", "Y", scope="work")
    s.add_relation("X", "r", "Z", scope="home")
    assert len(s.relations_for("X", scope="work")) == 1
    assert len(s.relations_for("X")) == 2


def test_entities_ranked_by_connections():
    s = _tmp_store()
    s.add_relation("Acme", "is in", "Beijing")
    s.add_relation("Zion", "works at", "Acme")
    ents = dict(s.entities())
    assert ents["Acme"] == 2          # appears as object once + subject once
    assert ents["Zion"] == 1


# ---- triple extraction parsing ------------------------------------------
def test_parse_triples():
    out = _parse('[["Zion","works at","Acme"],["Acme","is in","Beijing"]]', 8)
    assert out == [("Zion", "works at", "Acme"), ("Acme", "is in", "Beijing")]


def test_parse_fenced_and_skips_malformed():
    raw = '```json\n[["A","rel","B"], ["bad","pair"], ["C","rel","D"]]\n```'
    assert _parse(raw, 8) == [("A", "rel", "B"), ("C", "rel", "D")]


def test_parse_garbage_and_max():
    assert _parse("no json here", 8) == []
    assert _parse("", 8) == []
    assert len(_parse('[["a","b","c"],["d","e","f"],["g","h","i"]]', 2)) == 2
