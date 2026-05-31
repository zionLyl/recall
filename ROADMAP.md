# recall — roadmap & competitive analysis

Where recall sits in the AI-memory + LLM-observability landscape, what it does
better, and what's worth borrowing — filtered through one rule: **stay
local-first. One SQLite file. No server, no account, no telemetry.**

Star counts are approximate (mid-2026) and drift; orders of magnitude are the point.

## The landscape

### Memory layers
| Project | Stars≈ | License | Posture | Signature feature |
|---|---|---|---|---|
| [mem0](https://github.com/mem0ai/mem0) | 57k | Apache-2.0 | OSS lib + managed cloud | LLM-driven **ADD/UPDATE/DELETE/NOOP** per fact (conflict resolution) |
| [Letta / MemGPT](https://github.com/letta-ai/letta) | 23k | Apache-2.0 | Agent runtime/server | OS-style memory tiers + **self-editing memory**, sleep-time consolidation |
| [Zep / Graphiti](https://github.com/getzep/graphiti) | 27k | Apache-2.0 | Self-host + cloud | **Temporal knowledge graph** — facts invalidated, not deleted; provenance |
| [cognee](https://github.com/topoteretes/cognee) | 7k | OSS | Local-capable | `add → cognify → search`; doc-to-graph + graph retrieval |
| [memary](https://github.com/kingjulio8238/Memary) | niche | OSS | Local (Ollama) | Knowledge-graph memory, multimodal |
| [txtai](https://github.com/neuml/txtai) | mature | Apache-2.0 | Local | Embeddings DB + semantic/SQL hybrid (retrieval reference) |

### Observability / cost
| Project | Stars≈ | License | Posture | Signature feature |
|---|---|---|---|---|
| [Langfuse](https://github.com/langfuse/langfuse) | 28k | MIT (ex `/ee`) | Self-host (Postgres+ClickHouse) or cloud | Nested-span tracing, **evals**, prompt versioning, datasets |
| [Helicone](https://github.com/Helicone/helicone) | 6k | Apache-2.0 | Proxy (self-host heavy) or cloud | **Drop-in `baseURL`** logging, caching, rate-limit, routing |
| [Arize Phoenix](https://github.com/Arize-ai/phoenix) | 10k | ELv2 | Runs local | OTel/**OpenInference** tracing, retrieval evals, experiments |
| [OpenLLMetry](https://github.com/traceloop/openllmetry) | 7k | Apache-2.0 | SDK | Vendor-neutral **OTel spans**, portable to any backend |
| [LiteLLM](https://github.com/BerriAI/litellm) | 20k+ | MIT | SDK + proxy | **100+ providers**, in-process cost calc, routing, **budget enforcement** |

### Multi-provider / CLI / UI
| Project | Stars≈ | License | Posture | Signature feature |
|---|---|---|---|---|
| [simonw/llm](https://github.com/simonw/llm) | 12k | Apache-2.0 | Local CLI | **Logs every call to SQLite**, plugins, templates/fragments, schemas |
| [AnythingLLM](https://github.com/Mintplex-Labs/anything-llm) | 25k+ | OSS | On-device app | Workspaces, doc RAG, managed memories, MCP |
| [Open WebUI](https://github.com/open-webui/open-webui) | very large | OSS | Self-host (SQLite default) | Polished chat UI, RAG, per-message token capture |

## recall's genuine advantages (honest)

- **The combination is rare.** Memory tools (mem0, Letta, Zep, cognee) don't
  track cost/tokens/latency; observability tools (Langfuse, Helicone, Phoenix,
  OpenLLMetry) don't do persistent memory. recall does **both in one tool**. The
  closest sibling, simonw/llm, logs calls but has neither injected memory nor
  cost/budget.
- **Zero infrastructure.** Every serious competitor needs a backend — Langfuse
  (Postgres + ClickHouse), Helicone (5–6 services), LiteLLM proxy spend-logs
  (Postgres), Zep/cognee (graph DB). recall is one SQLite file with no daemon.
- **End-to-end memory loop out of the box** — capture → store → retrieve →
  inject into the system prompt. Most memory libraries leave injection to you.
- **22 providers + MCP in a tiny tool** — strong breadth-to-weight ratio.
- **Bilingual (EN + 中文) capture** — a real niche edge none of the majors ship.

Honest caveats: recall's memory intelligence is shallow (no conflict
resolution, no graph, no temporal model) and its observability is basic vs
Langfuse/Phoenix (no spans, no evals).

## Biggest gaps users will feel

Every gap from the original competitive analysis is now closed (see the table).
recall has reached feature parity-or-better with the field on its core promise —
local-first memory + observability — while keeping the single-SQLite, no-server
philosophy. Remaining work is depth/polish, not missing capabilities:

- **Eval depth** — only rule checks + single-criterion LLM judge; no datasets or
  regression suites across many traces (Langfuse/Phoenix go deeper).
- **Graph depth** — relations are 1-hop; no multi-hop traversal or graph viz.
- **Memory extraction quality** — heuristic + single-pass LLM; no benchmark
  harness (mem0 reports LoCoMo/LongMemEval scores).

*Closed across v0.3.0–v0.6.0:* conflict resolution (ADD/UPDATE/DELETE/NOOP),
memory lifecycle, relational memory (graph-lite), graph-aware retrieval, hybrid
FTS5+vector retrieval, similarity dedupe, per-turn trace trees, quality evals
(rules + LLM judge) with saved suites & auto-eval, prompt templates, budget
hard-stop, maintained pricing map, streaming, LLM extraction, MCP server,
**provenance**, **plugin hooks**, **OpenTelemetry export**.

## "Steal these" — ranked by impact × low-effort, local-first only

| # | Feature | Who does it | Effort | Status |
|---|---------|-------------|--------|--------|
| 1 | LLM **ADD/UPDATE/DELETE/NOOP** on memory add (conflict resolution) | mem0 | Med | ✅ done (v0.4.0) |
| 2 | Exact + near-dup dedupe before insert | mem0 | Low | ✅ done (v0.3.0) |
| 3 | **Hybrid retrieval** = semantic + BM25 (SQLite FTS5) fused by RRF | mem0, Zep | Low–Med | ✅ done (v0.3.0) |
| 4 | Recency/usage scoring + soft decay | Zep, Letta | Low | ✅ done (v0.4.0) |
| 5 | Prompt templates / fragments in CLI | simonw/llm | Low | ✅ done (v0.4.0) |
| 6 | Budget **hard-stop** (not just warn) | LiteLLM | Low | ✅ done (v0.3.0) |
| 7 | Provenance per memory (source msg + timestamp) | Graphiti | Low | partial (source, created_at, valid_from/to; relations link source_memory) |
| 8 | Maintained pricing map, LiteLLM `model_cost` style | LiteLLM | Low | ✅ done (v0.5.0) |
| 9 | Graph-lite: entity relations in SQLite | mem0/Zep/cognee | Med | ✅ done (v0.4.0) |
| 10 | Local trace tree (turn → chat + aux calls) | Langfuse (spans) | Med | ✅ done (v0.4.0) |
| 11 | Graph-aware retrieval (query → neighbor memories) | mem0/Zep | Med | ✅ done (v0.5.0) |
| 12 | Quality evals (rule checks + LLM judge) | Langfuse/Phoenix | Med | ✅ done (v0.5.0) |
| 13 | Plugin hooks for providers/extractors | simonw/llm | Med | ✅ done (v0.6.0) |
| 14 | Full provenance (source trace on memories) | Graphiti | Low | ✅ done (v0.6.0) |
| 15 | Opt-in OpenTelemetry / OpenInference span export | OpenLLMetry, Phoenix | Med | ✅ done (v0.6.0) |
| 16 | Eval ergonomics (suites, auto-eval, summary) | Langfuse/Phoenix | Med | ✅ done (v0.6.0) |
| — | In-process OpenAI `base_url` shim (drop-in logging) | Helicone (in-proc only) | Med | later |

**Do NOT adopt — breaks single-SQLite / no-server:** full graph-DB memory
(Neo4j/FalkorDB), server-mode proxy with Postgres/ClickHouse, managed-cloud sync.

## Prioritized roadmap (next)

The competitive gaps are closed. Remaining work is depth/polish, lower priority:

1. **Eval datasets / regression suites** — run a suite across many past traces
   and track score trends, not just per-trace checks.
2. **Multi-hop graph traversal + visualization** — relations are 1-hop today.
3. **Extraction-quality benchmark harness** — measure recall/precision of memory
   capture (mem0 publishes LoCoMo/LongMemEval numbers).
4. **In-process OpenAI `base_url` shim** — drop-in logging for existing apps
   without code changes (Helicone idea, kept in-process to stay server-free).

Done across v0.3.0 → v0.6.0: streaming, LLM extraction, MCP server, PyPI
publish, memory editing, similarity dedupe, hybrid FTS5+vector retrieval, budget
hard-stop, memory lifecycle, conflict resolution (ADD/UPDATE/DELETE/NOOP),
graph-lite, graph-aware retrieval, local trace tree, prompt templates, maintained
pricing map, quality evals (rules + LLM judge, suites, auto-eval), **provenance**,
**plugin hooks**, **OpenTelemetry export**.
