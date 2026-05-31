# 🧠 recall

**Your local AI brain: persistent memory + full observability for any model.**
Data never leaves your machine.

[![PyPI](https://img.shields.io/pypi/v/zion-recall-ai.svg)](https://pypi.org/project/zion-recall-ai/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.9+-blue.svg)
![Local-first](https://img.shields.io/badge/local--first-100%25-orange.svg)

```bash
pipx install 'zion-recall-ai[all]'      # or: pip install 'zion-recall-ai[openai]'
```

---

AI agents have two chronic problems:

1. **They forget you.** Switch models or start a new session and you re-explain everything.
2. **You can't see what they're doing.** Which model? How many tokens? How much did that cost?

**recall fixes both, locally, for any model.** One small SQLite file holds your
memories *and* every call's tokens/cost/latency. Switch from GPT to Claude to
DeepSeek to Qwen — your memory and your bill follow you.

### What you get

- 🧠 **Persistent memory** across sessions *and* across models
- 🔎 **Hybrid retrieval** — semantic + BM25 keyword search, fused (no extra deps)
- 🤖 **Auto-memory** — it captures your preferences from conversation (EN + 中文)
- 🧬 **LLM extraction** (opt-in) — let a model pull memories for higher recall
- ♻️ **Conflict resolution** (opt-in) — ADD/UPDATE/DELETE/NOOP so facts stay current, not piled up
- ⏳ **Lifecycle** — usage tracking, soft-forget, prune, recency-weighted ranking
- 🕸️ **Graph-lite** — entity relationships in SQLite (no graph DB)
- 🌊 **Streaming** — replies type out token-by-token
- 📊 **Observability** — tokens/cost/latency per call, plus per-turn **trace trees**
- 💰 **Daily budget** — 80% / 100% warnings, optional hard-stop
- 🗂️ **Scopes** — isolate memory per project (`work`, `home`, …)
- 🔌 **22 providers** — cloud, Chinese clouds, fast-inference hosts, local
- 🔗 **MCP server** — any agent (Claude Desktop/Code, Cursor) reads/writes your memory
- 📝 **Prompt templates** — reusable prompts with `{var}` substitution
- 📦 **Export / import** — your memory is portable JSON
- 🖥️ **Local web dashboard** — memory + cost at a glance
- 🏠 **100% local** — no accounts, no servers, no telemetry

```
┌──────────────┐     ┌─────────────────────────────┐
│  any model   │     │  recall (local SQLite)       │
│  GPT / Claude│ ◄──►│  • memories  → auto-injected │
│  DeepSeek/Qwen│    │  • traces    → tokens & cost │
└──────────────┘     └─────────────────────────────┘
        nothing leaves your machine
```

## Quickstart (30 seconds)

```bash
# Recommended: isolated CLI install with everything wired up
pipx install 'zion-recall-ai[all]'        # or: uv tool install 'zion-recall-ai[all]'

# Or pick what you need (base = keyword memory + tracing, no heavy deps):
pip install 'zion-recall-ai[openai]'      # GPT / DeepSeek / Qwen / OpenAI-compatible
#   pip install 'zion-recall-ai[anthropic]'   # Claude
#   pip install 'zion-recall-ai[gemini]'      # Gemini
#   pip install 'zion-recall-ai[embeddings]'  # semantic memory search (downloads a model)
#   pip install 'zion-recall-ai[dashboard]'   # web dashboard
#   pip install 'zion-recall-ai[mcp]'         # MCP server
#   pip install 'zion-recall-ai[otel]'        # OpenTelemetry export
#   pip install zion-recall-ai                # base only (keyword + tracing)

# not on PyPI yet? install straight from source:
#   pipx install 'git+https://github.com/zionLyl/recall.git#egg=zion-recall-ai[all]'
```

```bash
# 0. (optional) guided setup: pick a default model, detect API keys
recall init

# 1. Teach it about you (once)
recall add "I prefer concise answers with tables" --tags style
recall add "I do A-share & HK quant research"     --tags work

# 2. Chat with ANY model — it already knows you, and the call is traced
export OPENAI_API_KEY=sk-...
recall chat openai gpt-4o-mini "How should you reply to me?"
#   ↑ also auto-captures new preferences you mention

# with defaults configured, just:
recall chat "what do I work on?"

# or drop into an interactive, multi-turn chat (memory + tracing on):
recall chat

# 3. See exactly what you spent (and your budget)
recall stats
```

```
recall stats

Memories stored : 2
Model calls     : 1
Tokens          : 312 in / 88 out
Total cost      : $0.0001
Avg latency     : 740 ms
```

Switch model, same memory, same ledger:

```bash
export ANTHROPIC_API_KEY=sk-...
recall chat anthropic claude-3-5-sonnet "Remind me what I work on"
# → still remembers your A-share / HK quant work
```

## Use as a library

```python
from recall import Recall

r = Recall()
r.remember("I prefer concise answers", tags=["style"])

out = r.chat("openai", "gpt-4o-mini", "How should you reply to me?")
print(out.text)          # the model already knows your preference

print(r.stats())         # {'calls': 1, 'cost_usd': ..., ...}
```

## Web dashboard

```bash
pip install 'zion-recall-ai[dashboard]'
recall dashboard          # → http://127.0.0.1:8745
```

A single local page: memory cards, cost-by-model, recent calls. No build step,
no telemetry, no cloud.

## Streaming

Replies stream by default — you see tokens as the model produces them, then the
usual cost/latency footer.

```bash
recall chat "draft a haiku about memory"   # streams token-by-token
recall chat                                # interactive multi-turn REPL
recall chat --no-stream "..."              # wait for the full reply instead
recall config set stream false             # make non-streaming the default
```

In the REPL each turn keeps the in-session conversation history *and* your
long-term memories are injected — type `/exit` or Ctrl-D to leave.

From the library, pass an `on_token` callback; you still get the full outcome:

```python
out = r.stream("openai", "gpt-4o-mini", "tell me a joke",
               on_token=lambda t: print(t, end="", flush=True))
print(out.cost_usd, out.output_tokens)     # full accounting after streaming
```

## Smarter memory extraction (opt-in)

By default recall captures memories with fast, free heuristics (regex cues, EN +
中文). Flip on LLM extraction to have a model read each message and pull durable
first-person facts — higher recall, at the cost of one extra (cheap) call that's
also traced toward your budget.

```bash
recall config set extraction_mode llm          # heuristic (default) | llm
recall config set extraction_model gpt-4o-mini # optional; defaults to chat model
```

If the extraction call ever fails (no key, network, bad output) recall silently
falls back to the heuristic extractor, so chat never breaks.

## Curate your memory

```bash
recall edit 3 "I prefer concise answers with tables"   # rewrite a memory
recall edit 3 --tags style,format                       # or just retag it

# Merge near-duplicates that pile up from auto-capture (needs embeddings)
recall dedupe --dry-run        # preview which memories would merge
recall dedupe --threshold 0.9  # keep the earliest, union tags, drop the rest
recall config set dedupe_similarity 0.95   # also suppress near-dupes on add
```

Editing re-embeds the memory so semantic search stays accurate. Dedupe groups
memories whose embeddings are ≥ the threshold, keeps the earliest as canonical,
and unions tags onto it — exact-duplicate skipping still works even without
embeddings installed.

## Semantic search without the model download

By default, semantic search uses a local `sentence-transformers` model
(`pip install 'zion-recall-ai[embeddings]'`, ~80MB on first use). If you'd rather
not pull in PyTorch, point recall at any **OpenAI-compatible `/embeddings`
endpoint** — e.g. a local Ollama or LM Studio you already run:

```bash
recall config set embedding_backend api
recall config set embedding_base_url http://localhost:11434/v1   # Ollama
recall config set embedding_model nomic-embed-text
# cloud endpoints: also set embedding_api_key_env to the env var holding the key
```

Now `recall add` / `recall search` get semantic embeddings over HTTP — no heavy
local dependency. If the endpoint is unreachable, recall transparently falls
back to keyword/BM25 search.

## MCP server — plug recall into any agent

Expose your local memory to any MCP-aware client (Claude Desktop, Claude Code,
Cursor, …) so the agent can read and write the *same* brain you use from the CLI.

```bash
pip install 'zion-recall-ai[mcp]'
recall mcp        # runs an MCP server over stdio
```

Wire it into your MCP client config:

```json
{
  "mcpServers": {
    "recall": { "command": "recall", "args": ["mcp"] }
  }
}
```

Tools exposed: `remember`, `recall_search`, `list_memories`, `forget`,
`usage_stats`. Same local SQLite store — nothing leaves your machine.

## Supported models (22 providers)

Mix and match across clouds, Chinese providers, fast inference hosts, and local
models — your memory and cost ledger follow you everywhere.

| Provider | `provider` arg | Example models | API key env |
|---|---|---|---|
| OpenAI | `openai` | `gpt-4o`, `gpt-4o-mini`, `gpt-4.1` | `OPENAI_API_KEY` |
| Anthropic | `anthropic` | `claude-3-5-sonnet`, `claude-3-5-haiku` | `ANTHROPIC_API_KEY` |
| Google Gemini | `gemini` | `gemini-1.5-pro`, `gemini-2.0-flash` | `GEMINI_API_KEY` |
| DeepSeek | `deepseek` | `deepseek-chat`, `deepseek-reasoner` | `DEEPSEEK_API_KEY` |
| Qwen (DashScope) | `qwen` | `qwen-plus`, `qwen-max` | `DASHSCOPE_API_KEY` |
| Moonshot (Kimi) | `moonshot` | `moonshot-v1-8k`, `moonshot-v1-32k` | `MOONSHOT_API_KEY` |
| Zhipu (GLM) | `zhipu` | `glm-4`, `glm-4-flash` | `ZHIPU_API_KEY` |
| MiniMax | `minimax` | `abab6.5s` | `MINIMAX_API_KEY` |
| Baichuan | `baichuan` | `Baichuan4` | `BAICHUAN_API_KEY` |
| 01.AI (Yi) | `yi` | `yi-large`, `yi-lightning` | `YI_API_KEY` |
| StepFun | `stepfun` | `step-1` | `STEPFUN_API_KEY` |
| Mistral | `mistral` | `mistral-large`, `mistral-small` | `MISTRAL_API_KEY` |
| xAI (Grok) | `xai` | `grok-2`, `grok-beta` | `XAI_API_KEY` |
| Groq | `groq` | `llama-3.3-70b-versatile` | `GROQ_API_KEY` |
| Together | `together` | open models | `TOGETHER_API_KEY` |
| Fireworks | `fireworks` | open models | `FIREWORKS_API_KEY` |
| DeepInfra | `deepinfra` | open models | `DEEPINFRA_API_KEY` |
| Perplexity | `perplexity` | `sonar`, `sonar-pro` | `PERPLEXITY_API_KEY` |
| OpenRouter | `openrouter` | 400+ models, one key | `OPENROUTER_API_KEY` |
| Ollama (local) | `ollama` | `llama3`, `qwen2.5` | — |
| LM Studio (local) | `lmstudio` | any loaded model | — |
| Any OpenAI-compatible | `openai-compatible` | set `--base-url` | `RECALL_API_KEY` |

```bash
recall models   # list all providers + key env vars + base URLs
```

> Most providers speak the OpenAI API, so they share one adapter — just point
> at the right base URL (handled automatically). Gemini has its own native
> adapter. Local models (Ollama / LM Studio) need no key and no cloud.

## Scopes, budget & config

```bash
# Isolate memory per project
recall scope work            # switch active scope
recall add "deadline Friday" # stored in 'work'
recall scope                 # list all scopes
recall list --all            # see every scope

# Set a daily spend cap (warns at 80% and 100%)
recall config set daily_budget_usd 1.0
recall config set budget_enforce true   # hard-stop: refuse calls once the cap is hit

# Defaults so you can just `recall chat "..."`
recall config set default_provider deepseek
recall config set default_model deepseek-chat
recall config show

# Backup / move your brain
recall export my-brain.json
recall import my-brain.json
```

## CLI reference

| Command | What it does |
|---|---|
| `recall init` | Guided first-time setup |
| `recall doctor` | Show which providers have keys |
| `recall add "..." [--tags a,b] [--scope s]` | Store a memory |
| `recall search "..." [--all]` | Semantic (or keyword) search |
| `recall list [--all]` | List memories (active scope) |
| `recall show <id>` | Inspect a memory + its provenance (source chat) |
| `recall edit <id> ["new content"] [--tags ...]` | Edit a memory in place |
| `recall forget <id> [--soft]` | Delete (or soft-forget) a memory |
| `recall prune [--older-than DAYS] [--unused] [--all]` | Soft-forget stale memories |
| `recall dedupe [--threshold 0.9] [--all] [--dry-run]` | Merge near-duplicate memories |
| `recall graph [entity] [--add "s\|p\|o"]` | View / add entity relationships |
| `recall scope [name]` | Switch / list scopes |
| `recall chat [provider model] "..." [-T tmpl -V k=v] [--no-stream]` | Chat with memory + tracing + auto-memory |
| `recall chat` | Interactive multi-turn chat (REPL) |
| `recall stats` | Tokens, cost & budget overview |
| `recall recent` | Recent model calls (with trace IDs) |
| `recall trace` | Recent turns as call trees |
| `recall eval <id> [--contains/--regex/--judge/--suite ...]` | Score a traced reply (rules / LLM judge) |
| `recall evals [--trace id]` | List eval results |
| `recall eval-suite save/list/rm` | Manage reusable eval suites |
| `recall pricing [model]` | Show resolved per-1M-token pricing |
| `recall benchmark` | Reproducible retrieval/extraction quality numbers |
| `recall models` | Supported providers |
| `recall prompt save/list/show/use/rm` | Manage prompt templates |
| `recall export/import <file>` | Backup / restore memories |
| `recall config show/set/path` | View & edit configuration |
| `recall dashboard` | Launch local web UI |
| `recall mcp` | Run as an MCP server (stdio) for any agent |

## Where is my data?

A single SQLite file at `~/.recall/recall.db` (override with `RECALL_HOME`).
That's it. No accounts, no servers, no telemetry. Back it up, sync it, delete
it — it's yours.

## Why local-first?

- **Privacy** — your memories and prompts stay on your disk.
- **Portability** — one file you can move, version, or sync yourself.
- **No lock-in** — works across providers; swap models freely.

## Benchmark

recall ships a reproducible, key-free quality benchmark:

```bash
recall benchmark
```

It seeds a fixed, hand-labeled memory set and measures retrieval quality
(recall@1, recall@k, precision@k, MRR) plus heuristic-extraction fact-recall —
honestly labeling whether it ran in **semantic** or **keyword/BM25** mode.
Keyword baseline: `recall@1 ≈ 0.50, MRR ≈ 0.69`, extraction fact-recall `1.00`
with `0` false captures; installing `[embeddings]` (or an api backend) scores
higher. Numbers are deterministic, so you can track them across changes.

## Roadmap

See [ROADMAP.md](ROADMAP.md) for how recall compares to mem0 / Letta / Zep /
Langfuse / LiteLLM / simonw's `llm`, what it does better, and what's planned next.

- [x] Auto-extract memories from conversations
- [x] Budget alerts ("you've spent $X today")
- [x] Gemini + local Ollama / LM Studio adapters
- [x] Export / import memories
- [x] Memory scopes
- [x] Streaming chat output
- [x] LLM-based memory extraction (opt-in, higher recall)
- [x] MCP server so any agent can read/write recall memory
- [x] PyPI release (`pip install zion-recall-ai`) — automated via tag push
- [x] Memory editing & merge / dedupe by similarity

## Contributing

Issues and PRs welcome. Run tests with:

```bash
pip install 'zion-recall-ai[dev]'
pytest
```

## License

MIT © [zionLyl](https://github.com/zionLyl)
