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

Most of the original gaps are now closed (see the table below). What remains:

1. **No evals.** Trace trees show cost/latency per turn, but there's no
   reply-quality scoring (LLM-as-judge / rules). (Langfuse, Phoenix.)
2. **No OpenTelemetry export** — data is siloed in SQLite, can't pipe to
   Phoenix/Langfuse. (OpenLLMetry, Phoenix.)
3. **Graph is a parallel store** — relations are queryable but not yet wired
   into retrieval (no graph-expansion of queries). (mem0, Zep do graph-boosted recall.)
4. **No maintained pricing map** — costs drift as models change. (LiteLLM `model_cost`.)
5. **No plugin system** — adding a provider/extractor needs a core edit. (simonw/llm.)

*Closed since the first analysis:* conflict resolution (ADD/UPDATE/DELETE/NOOP),
memory lifecycle (decay/recency/soft-forget), relational memory (graph-lite),
basic tracing (per-turn trace trees), prompt templates, budget hard-stop.

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
| 8 | Maintained pricing map, LiteLLM `model_cost` style | LiteLLM | Low | planned |
| 9 | Graph-lite: entity relations in SQLite | mem0/Zep/cognee | Med | ✅ done (v0.4.0) |
| 10 | Local trace tree (turn → chat + aux calls) | Langfuse (spans) | Med | ✅ done (v0.4.0) |
| 11 | Plugin hooks for providers/extractors | simonw/llm | Med | later |
| 12 | In-process OpenAI `base_url` shim (drop-in logging) | Helicone (in-proc only) | Med | later |
| 13 | Opt-in OpenTelemetry / OpenInference span export | OpenLLMetry, Phoenix | Med | later |

**Do NOT adopt — breaks single-SQLite / no-server:** full graph-DB memory
(Neo4j/FalkorDB), server-mode proxy with Postgres/ClickHouse, managed-cloud sync.

## Prioritized roadmap (next)

1. **Maintained pricing map** — adopt a LiteLLM `model_cost`-style table so new
   models price correctly; keep `RECALL_PRICING` override.
2. **Graph-aware retrieval** — expand a query with related entities from the
   graph-lite relations to pull in connected memories (currently graph is a
   parallel store + query; wire it into recall).
3. **Eval hooks** — lightweight local scoring of replies (LLM-as-judge / rules)
   stored alongside traces, so quality is observable, not just cost.
4. **Opt-in OpenTelemetry/OpenInference export** — coexist with Langfuse/Phoenix
   for users who outgrow the local dashboard, without abandoning local-first.
5. **Plugin hooks** — let third parties add providers/extractors without core
   changes (simonw/llm-style entry points).
6. **Full provenance** — store the source message id on auto-captured memories
   for end-to-end auditing.

Done recently (v0.3.0 → v0.4.0): streaming, LLM extraction, MCP server, PyPI
publish, memory editing, similarity dedupe, hybrid FTS5+vector retrieval, budget
hard-stop, **memory lifecycle (usage/soft-forget/recency)**, **conflict
resolution (ADD/UPDATE/DELETE/NOOP)**, **graph-lite**, **local trace tree**,
**prompt templates**.
