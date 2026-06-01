"""Opt-in OpenTelemetry / OpenInference span export.

engram stays local-first by default — every call already lives in SQLite. But
power users who outgrow the local dashboard can mirror calls as OpenTelemetry
spans (using OpenInference's LLM semantic conventions) into Phoenix, Langfuse,
or any OTLP backend, *without* engram depending on a server.

Enable with `config set otel_export true`. Spans go to the OTLP endpoint in
`OTEL_EXPORTER_OTLP_ENDPOINT` if set, otherwise the console. Requires the SDK:
`pip install 'engram-ai[otel]'`. If it's missing or disabled, `export()` is a
no-op that returns False — it never breaks chat.
"""

from __future__ import annotations

import os

_TRACER = None
_INIT_FAILED = False


def oi_attributes(trace: dict) -> dict:
    """Map a engram trace to OpenInference LLM span attributes."""
    in_tok = trace.get("input_tokens", 0) or 0
    out_tok = trace.get("output_tokens", 0) or 0
    attrs = {
        "openinference.span.kind": "LLM",
        "llm.model_name": trace.get("model"),
        "llm.provider": trace.get("provider"),
        "llm.token_count.prompt": in_tok,
        "llm.token_count.completion": out_tok,
        "llm.token_count.total": in_tok + out_tok,
        "input.value": trace.get("prompt"),
        "output.value": trace.get("completion"),
        "engram.cost_usd": trace.get("cost_usd"),
        "engram.kind": trace.get("kind", "chat"),
    }
    return {k: v for k, v in attrs.items() if v is not None}


def _get_tracer():
    global _TRACER, _INIT_FAILED
    if _TRACER is not None:
        return _TRACER
    if _INIT_FAILED:
        return None
    try:
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

        provider = TracerProvider()
        exporter = None
        if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
            try:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                    OTLPSpanExporter,
                )
                exporter = OTLPSpanExporter()
            except ImportError:
                exporter = None
        provider.add_span_processor(SimpleSpanProcessor(exporter or ConsoleSpanExporter()))
        _TRACER = provider.get_tracer("engram")
        return _TRACER
    except Exception:  # noqa: BLE001 — SDK missing or misconfigured
        _INIT_FAILED = True
        return None


def is_available() -> bool:
    return _get_tracer() is not None


def export(trace: dict) -> bool:
    """Emit one OpenInference span for a trace. Returns False (no-op) if the SDK
    isn't installed or export fails — never raises."""
    tracer = _get_tracer()
    if tracer is None:
        return False
    try:
        name = f"{trace.get('kind', 'chat')}:{trace.get('model', 'model')}"
        with tracer.start_as_current_span(name) as span:
            for key, value in oi_attributes(trace).items():
                span.set_attribute(key, value)
        return True
    except Exception:  # noqa: BLE001
        return False


def _reset_for_test() -> None:  # pragma: no cover - test helper
    global _TRACER, _INIT_FAILED
    _TRACER = None
    _INIT_FAILED = False
