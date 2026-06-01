"""Capture *other* libraries' LLM calls into engram's local SQLite.

Phoenix/Langfuse can observe calls made by LangChain, LlamaIndex, the OpenAI SDK,
etc. via OpenInference/OpenTelemetry instrumentation. `engram.instrument()` makes
engram a *local sink* for those same spans: any OpenInference LLM span produced
in your process is written to `~/.engram/engram.db` as a trace (model, tokens,
cost, latency) — visible in `engram recent` / `engram stats` / `engram trace`.

Usage (in your app):

    import engram
    engram.instrument()                 # local sink, no server

    # then instrument whatever you use, e.g.:
    from openinference.instrumentation.openai import OpenAIInstrumentor
    OpenAIInstrumentor().instrument()
    # ...your normal OpenAI / LangChain / LlamaIndex code now lands in engram.

Requires the OTel SDK: `pip install 'engram-ai[otel]'`. `instrument()` also
best-effort enables the OpenAI / LangChain OpenInference instrumentors if their
packages are installed.
"""

from __future__ import annotations

from typing import Optional

from .pricing import estimate_cost
from .store import Trace


def span_to_trace(attrs: dict, name: str = "", duration_ms: float = 0) -> Optional[Trace]:
    """Map an OpenInference LLM span's attributes to a engram Trace, or None if
    the span isn't an LLM call."""
    kind = str(attrs.get("openinference.span.kind", "")).upper()
    if kind != "LLM":
        return None
    model = (attrs.get("llm.model_name") or attrs.get("llm.model") or name or "unknown")
    provider = attrs.get("llm.provider") or attrs.get("llm.system") or ""
    try:
        in_tok = int(attrs.get("llm.token_count.prompt") or 0)
        out_tok = int(attrs.get("llm.token_count.completion") or 0)
    except (TypeError, ValueError):
        in_tok = out_tok = 0
    return Trace(
        model=str(model),
        provider=str(provider),
        prompt=str(attrs.get("input.value") or "")[:2000],
        completion=str(attrs.get("output.value") or "")[:2000],
        input_tokens=in_tok,
        output_tokens=out_tok,
        cost_usd=estimate_cost(str(model), in_tok, out_tok),
        latency_ms=int(duration_ms),
        kind="instrumented",
    )


def _record_spans(spans, store) -> int:
    """Write LLM spans to the store. `spans` are OTel ReadableSpans (duck-typed:
    .attributes, .name, .start_time/.end_time in ns). Returns count written."""
    n = 0
    for sp in spans:
        attrs = dict(getattr(sp, "attributes", {}) or {})
        start = getattr(sp, "start_time", None)
        end = getattr(sp, "end_time", None)
        duration_ms = (end - start) / 1e6 if (start and end) else 0
        trace = span_to_trace(attrs, getattr(sp, "name", "") or "", duration_ms)
        if trace is not None:
            store.add_trace(trace)
            n += 1
    return n


def instrument(db_path=None, auto: bool = True):
    """Install engram as a local OpenInference span sink. Returns the Store the
    spans write to. Best-effort enables OpenAI/LangChain instrumentors when `auto`
    and their packages are present."""
    try:
        from opentelemetry import trace as _trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            SimpleSpanProcessor, SpanExporter, SpanExportResult,
        )
    except ImportError as e:
        raise RuntimeError(
            "instrument() needs the OTel SDK: pip install 'engram-ai[otel]'"
        ) from e

    from .store import Store

    store = Store(db_path)

    class _RecallExporter(SpanExporter):
        def export(self, spans):
            try:
                _record_spans(spans, store)
                return SpanExportResult.SUCCESS
            except Exception:  # noqa: BLE001
                return SpanExportResult.FAILURE

        def shutdown(self):
            store.close()

    provider = _trace.get_tracer_provider()
    if not isinstance(provider, TracerProvider):
        provider = TracerProvider()
        _trace.set_tracer_provider(provider)
    provider.add_span_processor(SimpleSpanProcessor(_RecallExporter()))

    if auto:
        for mod, cls in (
            ("openinference.instrumentation.openai", "OpenAIInstrumentor"),
            ("openinference.instrumentation.langchain", "LangChainInstrumentor"),
        ):
            try:
                m = __import__(mod, fromlist=[cls])
                getattr(m, cls)().instrument()
            except Exception:  # noqa: BLE001 — instrumentor not installed / already on
                pass

    return store
