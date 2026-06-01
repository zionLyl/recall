"""Tests for quality evals: rule checks, judge parsing, persistence."""

import tempfile
from pathlib import Path

from memstash.config import Config
from memstash.core import Recall
from memstash.evals import (
    _parse_judge, check_contains, check_max_tokens, check_not_contains, check_regex,
)
from memstash.store import Trace


def _tmp_recall(monkeypatch) -> Recall:
    d = tempfile.mkdtemp()
    monkeypatch.setenv("MEMSTASH_HOME", d)
    return Recall(Path(d) / "recall.db", config=Config())


# ---- rule checks ---------------------------------------------------------
def test_check_contains():
    assert check_contains("Hello World", "world")["passed"] is True
    assert check_contains("Hello", "bye")["passed"] is False


def test_check_not_contains():
    assert check_not_contains("safe text", "forbidden")["passed"] is True
    assert check_not_contains("has forbidden word", "forbidden")["passed"] is False


def test_check_regex():
    assert check_regex("order #1234", r"#\d+")["passed"] is True
    assert check_regex("no number", r"#\d+")["passed"] is False
    assert check_regex("x", r"[")["passed"] is False        # bad pattern, no crash


def test_check_max_tokens():
    assert check_max_tokens(50, 100)["passed"] is True
    assert check_max_tokens(150, 100)["passed"] is False


# ---- judge parsing -------------------------------------------------------
def test_parse_judge_normalizes_1_to_5():
    assert _parse_judge('{"score": 5, "reason": "great"}')["score"] == 1.0
    assert _parse_judge('{"score": 1, "reason": "bad"}')["score"] == 0.0
    assert _parse_judge('{"score": 3, "reason": "ok"}')["score"] == 0.5


def test_parse_judge_accepts_0_1_scale():
    assert _parse_judge('{"score": 0.8}')["score"] == 0.8


def test_parse_judge_fenced_and_garbage():
    assert _parse_judge('```json\n{"score":4,"reason":"x"}\n```')["passed"] is True
    assert _parse_judge("not json") is None
    assert _parse_judge('{"reason":"no score"}') is None


# ---- persistence via Recall.evaluate ------------------------------------
def test_evaluate_runs_rules_and_persists(monkeypatch):
    r = _tmp_recall(monkeypatch)
    tid = r.store.add_trace(Trace(model="m", completion="The answer is 42.",
                                  output_tokens=8, kind="chat"))
    results = r.evaluate(tid, contains="42", not_contains="error", max_tokens=10)
    names = {x["name"]: x["passed"] for x in results}
    assert names == {"contains": True, "not_contains": True, "max_tokens": True}
    stored = r.evals_for(tid)
    assert len(stored) == 3
    summary = r.store.eval_summary()
    assert summary["count"] == 3 and summary["passed"] == 3


def test_evaluate_failing_rule(monkeypatch):
    r = _tmp_recall(monkeypatch)
    tid = r.store.add_trace(Trace(model="m", completion="short", output_tokens=2))
    results = r.evaluate(tid, contains="missing")
    assert results[0]["passed"] is False


def test_evaluate_missing_trace_raises(monkeypatch):
    r = _tmp_recall(monkeypatch)
    import pytest
    with pytest.raises(ValueError):
        r.evaluate(9999, contains="x")
