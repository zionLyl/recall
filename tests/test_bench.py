"""Tests for the benchmark harness."""

import tempfile

from memstash.bench import (
    MEMORIES, QUERIES, _metrics_for, run_all, run_extraction_benchmark,
    run_retrieval_benchmark,
)
from memstash.config import Config


def test_metrics_for():
    # retrieved [1,2,3], relevant {2}: recall 1.0, precision@3 = 1/3, MRR = 1/2
    rc, pr, rr = _metrics_for([1, 2, 3], {2}, 3)
    assert rc == 1.0 and abs(pr - 1 / 3) < 1e-9 and rr == 0.5
    # nothing relevant retrieved
    rc, pr, rr = _metrics_for([1, 2, 3], {9}, 3)
    assert rc == 0.0 and pr == 0.0 and rr == 0.0


def test_dataset_relevant_contents_exist():
    # every query's relevant content must be a real memory (guards typos)
    contents = {c for c, _ in MEMORIES}
    for _q, rel in QUERIES:
        for c in rel:
            assert c in contents, f"query references unknown memory: {c}"


def test_retrieval_benchmark_runs(monkeypatch):
    d = tempfile.mkdtemp()
    monkeypatch.setenv("MEMSTASH_HOME", d)
    res = run_retrieval_benchmark(config=Config())
    assert res["mode"] in ("semantic", "keyword")
    assert res["queries"] == len(QUERIES)
    for key in ("recall_at_k", "precision_at_k", "mrr"):
        assert 0.0 <= res[key] <= 1.0
    # the harness should find a reasonable share even in keyword mode
    assert res["recall_at_k"] >= 0.4


def test_extraction_benchmark():
    res = run_extraction_benchmark()
    assert 0.0 <= res["fact_recall"] <= 1.0
    assert res["fact_recall"] >= 0.5          # heuristic catches the obvious facts
    assert res["false_captures"] <= 1          # near-zero noise on the empty cases


def test_run_all_shape(monkeypatch):
    d = tempfile.mkdtemp()
    monkeypatch.setenv("MEMSTASH_HOME", d)
    res = run_all(config=Config())
    assert "retrieval" in res and "extraction" in res
