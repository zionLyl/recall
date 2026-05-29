# Changelog

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
  store, nothing leaves your machine. Install with `pip install 'recall-ai[mcp]'`.
- **Memory editing**: `recall edit <id> "new content" [--tags ...]` updates a
  memory in place and re-embeds it. Library: `Recall.edit(...)`.
- **Similarity merge / dedupe**: `recall dedupe [--threshold 0.9] [--all]
  [--dry-run]` clusters near-duplicate memories by cosine similarity, keeps the
  earliest, and unions their tags. Optional on-add suppression via
  `config set dedupe_similarity 0.95` (both need embeddings; exact dedupe still
  works without them).

### Fixed
- Install hints (`recall-ai[dashboard]`, `recall-ai[mcp]`) and model output are
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
