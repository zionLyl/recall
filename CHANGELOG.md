# Changelog

## [0.2.0] - Unreleased

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

## [0.1.0] - Unreleased

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
