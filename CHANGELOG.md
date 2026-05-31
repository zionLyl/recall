# Changelog

## [0.12.0]

New capability (2/3): document ingestion.

### Added
- **`recall ingest <file>`**: read a `.txt` / `.md` (or `.pdf` with the `[pdf]`
  extra), split it into reasonably-sized chunks, and store each as a searchable
  memory tagged with the filename — so `recall search` and chat memory-injection
  cover your notes/docs. 100% local and deterministic (no LLM). Dedupes on
  re-ingest. `recall/ingest.py` (`chunk_text`, `read_file`) + `Recall.ingest`.

## [0.11.0]

New capability (1/3): bi-temporal memory.

### Added
- **Point-in-time queries**: `recall list --at <when>` shows the memories that
  were valid at a past time — `YYYY-MM-DD`, a relative `30d`/`12h`/`45m` ago, or
  an epoch. Includes since-forgotten memories whose validity window covers that
  moment. `Store.memories_as_of()` / `Recall.as_of()`.

### Changed
- **Conflict-resolution UPDATE now supersedes instead of overwriting**: the old
  fact's validity window is closed (kept as history, deactivated) and the new
  fact is added — so "what did I know on date X?" stays answerable.

## [0.10.0]

Credibility — reproducible quality numbers.

### Added
- **Benchmark harness** (`recall benchmark`): deterministic, key-free. Seeds a
  fixed, hand-labeled memory set into a throwaway store and reports retrieval
  quality — **recall@1, recall@k, precision@k, MRR** — plus a heuristic
  extraction fact-recall / false-capture check. Honestly labels whether the run
  used the semantic or keyword/BM25 backend, so numbers are comparable and not
  overstated. New `recall/bench.py` (`run_retrieval_benchmark`,
  `run_extraction_benchmark`, `run_all`). Baseline (keyword): recall@1 ≈ 0.50,
  MRR ≈ 0.69, extraction fact-recall 1.00 with 0 false captures; semantic
  embeddings score higher.

## [0.9.0]

Robustness & scale.

### Added
- **Vectorized retrieval**: semantic ranking now uses numpy (when present) to
  cosine-score all memories in one matrix op, with a pure-Python fallback —
  keeping recall fast as the store grows to thousands of memories. No new
  required dependency.

### Fixed
- **Embedding dimension safety**: stored vectors whose dimension differs from
  the query (e.g. after switching embedding models/backends) are now skipped
  instead of producing silently-wrong cosine scores. `_cosine` returns 0 on
  mismatch, protecting search, near-dup suppression, and dedupe.

### Changed
- SQLite now opens in **WAL** mode (`synchronous=NORMAL`) for safer concurrent
  reads/writes (e.g. the dashboard reading while the CLI writes).

## [0.8.0]

### Added
- **Pluggable embedding backend**: semantic search can now use any
  OpenAI-compatible `/embeddings` endpoint instead of the local
  sentence-transformers model — point at a local Ollama / LM Studio (no PyTorch
  download) or a cloud provider. Config: `embedding_backend = api`,
  `embedding_model`, `embedding_base_url`, `embedding_api_key_env`. Falls back to
  keyword/BM25 search if the endpoint is unreachable. Default stays `local`.

### Changed
- Published to PyPI as **`zion-recall-ai`** (`pip install zion-recall-ai`); the
  import package and `recall` CLI command are unchanged. README gains a PyPI
  badge + prominent install line.

## [0.7.0]

Usability & onboarding polish — informed by a competitive scan of how peers
(simonw/llm, Jan, Phoenix, mem0, …) handle ease-of-adoption.

### Added
- **Interactive chat REPL**: bare `recall chat` (no prompt) drops into a
  multi-turn conversation loop — memory injected + auto-captured each turn,
  cost traced, `/exit` or Ctrl-D to quit. Matches `llm chat`'s ergonomics.
- **Multi-turn conversation history**: adapters and `Recall.chat/stream` accept
  a `history` of prior turns, so chats are no longer single-shot. OpenAI,
  Anthropic, and Gemini adapters all thread it natively.
- **Zero-key local default**: `recall init` now detects a running Ollama
  (localhost:11434) and offers it as the default provider — no API key needed.

### Changed
- **Onboarding**: README leads with `pipx install 'zion-recall-ai[all]'` (and `uv tool
  install`); the quickstart's first chat command now installs a working provider
  extra instead of failing on the base install.
- First semantic search prints a one-time "loading embedding model (~80MB)"
  notice to stderr instead of hanging silently.

## [0.6.0]

The rest of the roadmap — extensibility, interop, auditing, and eval workflow.

### Added
- **Provenance**: auto-captured memories record the chat trace they came from
  (`source_trace`); `recall show <id>` prints a memory's detail plus the source
  call's model and prompt snippet for end-to-end auditing.
- **Plugin hooks**: `recall.register_adapter(...)` for runtime custom providers,
  and auto-discovery of adapters published under the `recall.adapters`
  entry-point group. *(simonw/llm-style.)*
- **OpenTelemetry export** (opt-in): `config otel_export true` mirrors calls as
  OpenInference LLM spans to an OTLP backend (Phoenix/Langfuse) or the console —
  no server dependency. `pip install 'zion-recall-ai[otel]'`.
- **Eval ergonomics**: saved eval suites (`recall eval-suite save/list/rm`,
  `recall eval <id> --suite NAME`), an eval pass-rate/score summary in
  `recall stats`, and opt-in **auto-eval after chat** (`config auto_eval_suite`).

## [0.5.0]

Retrieval, cost accuracy, and quality — the next batch from the roadmap.

### Added
- **Graph-aware retrieval**: with `graph_weight > 0`, recall finds entities
  named in the query, expands to their neighbors via the graph-lite relations,
  and pulls in memories about those neighbors as an extra RRF signal — surfacing
  connected memories the query never mentions. *(mem0/Zep-style.)*
- **Maintained pricing map**: provider-prefixed ids resolve
  (`openrouter/openai/gpt-4o` → `gpt-4o`); override without editing the package
  via `RECALL_PRICING_FILE` (JSON file) layered under `RECALL_PRICING` (inline);
  more current models added; `recall pricing [model]` to inspect. *(LiteLLM-style.)*
- **Quality evals**: attach checks to a traced reply — local rules
  (`--contains` / `--not-contains` / `--regex` / `--max-tokens`, free &
  deterministic) and an opt-in `--judge "criterion"` LLM score (1–5 → 0–1).
  `recall eval <trace_id> ...` and `recall evals` list results; `recall recent`
  now shows trace IDs and kind. *(Langfuse/Phoenix-style, local.)*

## [0.4.0]

Memory intelligence + deeper local observability — closing the biggest gaps vs
mem0 / Letta / Zep / Langfuse, while staying single-file and server-free.

### Added
- **Memory lifecycle**: memories track `hit_count` / `last_used` and a
  `valid_from` / `valid_to` / `active` window. Retrieval records hits and skips
  inactive memories. Soft-forget via `recall forget --soft` and bulk
  `recall prune --older-than DAYS --unused`. Opt-in recency/usage ranking
  (`config recency_weight`) blends a lifecycle signal into retrieval via
  weighted RRF. *(Zep/Letta-inspired.)*
- **Conflict resolution (ADD/UPDATE/DELETE/NOOP)**: opt-in `memory_ops = "llm"`
  reconciles each new fact against its most-related memories so contradictions
  are updated/removed instead of piling up. New `reconcile.py`; cost traced;
  degrades to a plain ADD on any failure. *(mem0's signature.)*
- **Graph-lite**: a `relations` table stores `(subject, predicate, object)`
  triples per scope — relational memory without a graph DB. Opt-in LLM mining
  (`graph_extract`) from chats; `recall graph [entity]` to query, `--add` to add
  manually. *(mem0/Zep/cognee-style, single-SQLite.)*
- **Local trace tree**: traces gain `session_id` / `parent_id` / `kind`, so a
  turn's chat + its extraction/reconcile/graph calls form a tree. `recall trace`
  renders per-turn call trees with token/cost totals; the dashboard gains a
  "Recent turns" section.
- **Prompt templates / fragments**: `recall prompt save/list/show/use/rm` with
  `{var}` substitution; `recall chat --template NAME --var k=v`. *(simonw/llm-style.)*

## [0.3.0]

Streaming, smarter memory, and the MCP bridge.

### Added
- **Streaming chat**: replies now type out token-by-token. `Recall.stream(...)`
  yields chunks via an `on_token` callback and still returns the full
  `ChatOutcome` (text, tokens, cost, auto-memory, budget). CLI: streams by
  default; toggle with `recall chat --no-stream` or `config set stream false`.
  Every adapter supports it — native OpenAI / Anthropic / Gemini adapters stream
  for real, others transparently fall back to a single chunk.
- **LLM-based memory extraction** (opt-in): set `extraction_mode = "llm"` to let
  a model pull durable first-person facts from each message — higher recall than
  the heuristic patterns. Configurable extraction model (`extraction_model`),
  its cost is traced, and it falls back to the heuristic extractor on any error.
- **MCP server** (`recall mcp`): exposes your memory to any MCP-aware agent
  (Claude Desktop, Claude Code, Cursor, …) as tools — `remember`,
  `recall_search`, `list_memories`, `forget`, `usage_stats`. Same local SQLite
  store, nothing leaves your machine. Install with `pip install 'zion-recall-ai[mcp]'`.
- **Memory editing**: `recall edit <id> "new content" [--tags ...]` updates a
  memory in place and re-embeds it. Library: `Recall.edit(...)`.
- **Similarity merge / dedupe**: `recall dedupe [--threshold 0.9] [--all]
  [--dry-run]` clusters near-duplicate memories by cosine similarity, keeps the
  earliest, and unions their tags. Optional on-add suppression via
  `config set dedupe_similarity 0.95` (both need embeddings; exact dedupe still
  works without them).
- **Hybrid retrieval**: memory search now fuses semantic (embeddings) with
  BM25 keyword ranking (SQLite FTS5) via Reciprocal Rank Fusion — exact terms,
  names, and IDs the embeddings blur now surface, while semantically-close
  memories still rank. FTS5 stays in sync via triggers and falls back to LIKE
  where unavailable. No new dependencies. *(mem0 / Zep do the same.)*
- **Budget hard-stop**: `config set budget_enforce true` makes recall *refuse*
  a call once today's spend hits `daily_budget_usd` (raises `BudgetExceeded`),
  instead of only warning. *(LiteLLM-style.)*

### Fixed
- Install hints (`zion-recall-ai[dashboard]`, `zion-recall-ai[mcp]`) and model output are
  no longer mangled by Rich markup parsing.

### Packaging
- PyPI Trusted Publishing workflow (`.github/workflows/publish.yml`): push a
  `vX.Y.Z` tag to publish. CI workflow runs lint + tests on 3.9 / 3.11 / 3.12.

## [0.2.0]

Major feature round.

### Added
- **Auto-memory**: after each chat, recall heuristically captures durable
  first-person facts/preferences (English + Chinese), tagged as `auto`.
- **Memory scopes**: isolate memories per project/context
  (`recall scope work`, `--scope`, `--all`). Active scope stored in config.
- **Config system** (`~/.recall/config.json`): default provider/model, daily
  budget, auto-memory toggle, inject limit, active scope.
  CLI: `recall config show|set|path`.
- **Daily budget + warnings**: set `daily_budget_usd`; chat and `stats` warn at
  80% and 100% of the day's spend.
- **Guided setup**: `recall init` (pick defaults, detect keys) and
  `recall doctor` (which providers are ready).
- **Export / import**: `recall export mem.json` / `recall import mem.json`
  (JSON, dedupe-aware).
- **Deduplication**: identical memories in the same scope are skipped.
- **Flexible chat**: `recall chat "prompt"` uses configured defaults; the
  three-arg form still works.
- **Dashboard upgrades**: auto-refresh, daily-budget bar, scope chips.
- Safe schema migrations for existing databases.

### Changed
- `Recall.chat()` now returns a richer `ChatOutcome` (cost, latency,
  auto-remembered list, budget warning).

## [0.1.0]

First MVP.

### Added
- Local-first SQLite store (`~/.recall/recall.db`) for memories + call traces.
- Memory engine with semantic search (sentence-transformers) and automatic
  keyword fallback when embeddings are not installed.
- **22 model providers** out of the box: OpenAI, Anthropic, Gemini, DeepSeek,
  Qwen, Moonshot (Kimi), Zhipu (GLM), MiniMax, Baichuan, 01.AI (Yi), StepFun,
  Mistral, xAI (Grok), Groq, Together, Fireworks, DeepInfra, Perplexity,
  OpenRouter, Ollama, LM Studio, and any OpenAI-compatible endpoint.
- Per-provider API key env var resolution with `RECALL_API_KEY` fallback.
- Expanded pricing table covering the new providers.
- Automatic per-call tracing: tokens, estimated cost, latency.
- CLI: `add`, `search`, `list`, `forget`, `chat`, `stats`, `recent`, `models`,
  `dashboard`, `version`.
- Minimal local web dashboard (FastAPI, single page, no build step).
- Library API via `from recall import Recall`.
