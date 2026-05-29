# Changelog

## [0.1.0] - Unreleased

First MVP.

### Added
- Local-first SQLite store (`~/.recall/recall.db`) for memories + call traces.
- Memory engine with semantic search (sentence-transformers) and automatic
  keyword fallback when embeddings are not installed.
- Unified model adapters: OpenAI, Anthropic, and OpenAI-compatible providers
  (DeepSeek, Qwen, custom base URLs).
- Automatic per-call tracing: tokens, estimated cost, latency.
- CLI: `add`, `search`, `list`, `forget`, `chat`, `stats`, `recent`, `models`,
  `dashboard`, `version`.
- Minimal local web dashboard (FastAPI, single page, no build step).
- Library API via `from recall import Recall`.
