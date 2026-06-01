"""Tests for the maintained pricing map: normalization + overrides."""

import json
import tempfile
from pathlib import Path

from engram.pricing import _candidates, estimate_cost, price_of


def test_provider_prefixed_names_resolve():
    # OpenRouter-style "openai/gpt-4o" and even double-prefixed forms.
    assert _candidates("openrouter/openai/gpt-4o")[-1] == "gpt-4o"
    assert price_of("openai/gpt-4o") == price_of("gpt-4o")
    assert price_of("openrouter/openai/gpt-4o") is not None


def test_prefix_and_longest_match():
    # date-suffixed and mini variants resolve to the right base
    assert price_of("gpt-4o-mini-2024-07-18") == price_of("gpt-4o-mini")
    assert price_of("gpt-4o-2024-08-06") == price_of("gpt-4o")


def test_unknown_is_zero():
    assert price_of("totally-made-up-model") is None
    assert estimate_cost("totally-made-up-model", 1000, 1000) == 0.0


def test_inline_override(monkeypatch):
    monkeypatch.setenv("ENGRAM_PRICING", json.dumps({"my-model": {"input": 1.0, "output": 2.0}}))
    assert estimate_cost("my-model", 1_000_000, 1_000_000) == 3.0


def test_file_override(monkeypatch):
    d = tempfile.mkdtemp()
    p = Path(d) / "prices.json"
    p.write_text(json.dumps({"file-model": {"input": 5.0, "output": 0.0}}))
    monkeypatch.setenv("ENGRAM_PRICING_FILE", str(p))
    assert estimate_cost("file-model", 1_000_000, 0) == 5.0


def test_inline_beats_file(monkeypatch):
    d = tempfile.mkdtemp()
    p = Path(d) / "prices.json"
    p.write_text(json.dumps({"m": {"input": 1.0, "output": 1.0}}))
    monkeypatch.setenv("ENGRAM_PRICING_FILE", str(p))
    monkeypatch.setenv("ENGRAM_PRICING", json.dumps({"m": {"input": 9.0, "output": 0.0}}))
    assert estimate_cost("m", 1_000_000, 0) == 9.0   # inline override wins
