"""Tests for prompt templates / fragments."""

import tempfile
from pathlib import Path

from memstash.prompts import parse_vars, render
from memstash.store import Store


def _tmp_store() -> Store:
    d = tempfile.mkdtemp()
    return Store(Path(d) / "test.db")


# ---- rendering -----------------------------------------------------------
def test_render_substitutes_known_vars():
    assert render("Summarize {topic} in {n} words", {"topic": "AI", "n": "5"}) == \
        "Summarize AI in 5 words"


def test_render_leaves_unknown_placeholders():
    assert render("Hi {name}, about {topic}", {"name": "Zion"}) == "Hi Zion, about {topic}"


def test_render_literal_braces():
    assert render("use {{curly}} and {x}", {"x": "X"}) == "use {curly} and X"


def test_parse_vars():
    assert parse_vars(["a=1", "b=hello world", "bad", "c="]) == \
        {"a": "1", "b": "hello world", "c": ""}


# ---- store ---------------------------------------------------------------
def test_save_get_list_delete_prompt():
    s = _tmp_store()
    s.save_prompt("greet", "Hello {who}")
    assert s.get_prompt("greet") == "Hello {who}"
    assert [p["name"] for p in s.list_prompts()] == ["greet"]
    assert s.delete_prompt("greet") is True
    assert s.get_prompt("greet") is None
    assert s.delete_prompt("greet") is False


def test_save_prompt_upserts():
    s = _tmp_store()
    s.save_prompt("t", "v1")
    s.save_prompt("t", "v2")              # same name → replace, not duplicate
    assert s.get_prompt("t") == "v2"
    assert len(s.list_prompts()) == 1
