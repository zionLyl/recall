# Changelog

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
