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

1. **No conflict resolution.** recall appends; contradictory facts ("I live in
   NYC" + "I live in Berlin") accumulate. mem0 (ADD/UPDATE/DELETE/NOOP) and Zep
   (temporal invalidation) reconcile. *The most-felt gap.*
2. **No memory lifecycle** — no decay, recency/usage scoring, or "this is now
   wrong." (Zep, Letta.)
3. **No graph / relational memory.** (mem0, Zep, cognee, memary.)
4. **Observability has no tracing or evals.** (Langfuse, Phoenix.)
5. **No prompt management** (versioning/templates). (Langfuse, Helicone, simonw/llm.)
6. **Budget warns but doesn't enforce.** (LiteLLM hard-stops.)
7. **No OpenTelemetry export** — data is siloed in SQLite. (OpenLLMetry, Phoenix.)

## "Steal these" — ranked by impact × low-effort, local-first only

| # | Feature | Who does it | Effort | Status |
|---|---------|-------------|--------|--------|
| 1 | LLM **ADD/UPDATE/DELETE/NOOP** on memory add (conflict resolution) | mem0 | Med | planned |
| 2 | Exact + near-dup dedupe before insert | mem0 | Low | ✅ done (v0.3.0) |
| 3 | **Hybrid retrieval** = semantic + BM25 (SQLite FTS5) fused by RRF | mem0, Zep | Low–Med | ✅ done |
| 4 | Recency/usage scoring + soft decay | Zep, Letta | Low | planned |
| 5 | Prompt templates / fragments in CLI | simonw/llm | Low | planned |
| 6 | Budget **hard-stop** (not just warn) | LiteLLM | Low | ✅ done |
| 7 | Provenance per memory (source msg + timestamp) | Graphiti | Low | partial (source/created_at) |
| 8 | Maintained pricing map, LiteLLM `model_cost` style | LiteLLM | Low | planned |
| 9 | Plugin hooks for providers/extractors | simonw/llm | Med | later |
| 10 | In-process OpenAI `base_url` shim (drop-in logging) | Helicone (in-proc only) | Med | later |
| 11 | Opt-in OpenTelemetry / OpenInference span export | OpenLLMetry, Phoenix | Med | later |
| 12 | Temporal fact invalidation (`valid_from/valid_to`) | Zep/Graphiti | Med | later |

**Do NOT adopt — breaks single-SQLite / no-server:** full graph-DB memory
(Neo4j/FalkorDB), server-mode proxy with Postgres/ClickHouse, managed-cloud sync.

## Prioritized roadmap (next)

1. **LLM merge/update (ADD/UPDATE/DELETE/NOOP)** — highest-impact gap closer.
   Behind the existing opt-in LLM extractor: retrieve top-k related memories,
   let the model decide the op per fact. *(mem0-style.)*
2. **Provenance + lifecycle columns** — `source_msg`, `valid_from/valid_to`,
   `last_used`, `hit_count`. Unlocks auditing, soft decay, and temporal
   supersession *without* a graph.
3. **Recency/usage-weighted ranking + soft forgetting** — builds on (2).
4. **Maintained pricing map** — keep cost accurate as models change.
5. **Prompt templates / fragments** — cheap day-to-day utility.
6. **Opt-in OpenTelemetry export** — coexist with Langfuse/Phoenix for users who
   outgrow the local dashboard, without abandoning local-first.

Done recently: streaming, LLM extraction (opt-in), MCP server, PyPI publish,
memory editing, similarity merge/dedupe, **hybrid FTS5+vector retrieval**,
**budget hard-stop**.
