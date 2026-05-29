"""Tests for opt-in OpenTelemetry export."""

import importlib.util

from recall.otel_export import export, is_available, oi_attributes


def test_oi_attributes_mapping():
    attrs = oi_attributes({
        "model": "gpt-4o-mini", "provider": "openai",
        "input_tokens": 10, "output_tokens": 5, "cost_usd": 0.001,
        "prompt": "hi", "completion": "hello", "kind": "chat",
    })
    assert attrs["openinference.span.kind"] == "LLM"
    assert attrs["llm.model_name"] == "gpt-4o-mini"
    assert attrs["llm.token_count.prompt"] == 10
    assert attrs["llm.token_count.total"] == 15
    assert attrs["input.value"] == "hi" and attrs["output.value"] == "hello"


def test_oi_attributes_drops_none():
    attrs = oi_attributes({"model": "m", "input_tokens": 1, "output_tokens": 0})
    assert "output.value" not in attrs        # no completion → omitted
    assert "llm.provider" not in attrs


def test_export_is_safe_regardless_of_sdk():
    # Whether or not the OTel SDK is installed, export must return a bool, never raise.
    ok = export({"model": "m", "input_tokens": 1, "output_tokens": 1, "kind": "chat"})
    assert isinstance(ok, bool)
    if importlib.util.find_spec("opentelemetry") is None:
        assert ok is False and is_available() is False
