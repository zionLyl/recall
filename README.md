# 🧠 recall

**Your local AI brain: persistent memory + full observability for any model.**
Data never leaves your machine.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.9+-blue.svg)
![Local-first](https://img.shields.io/badge/local--first-100%25-orange.svg)

---

AI agents have two chronic problems:

1. **They forget you.** Switch models or start a new session and you re-explain everything.
2. **You can't see what they're doing.** Which model? How many tokens? How much did that cost?

**recall fixes both, locally, for any model.** One small SQLite file holds your
memories *and* every call's tokens/cost/latency. Switch from GPT to Claude to
DeepSeek to Qwen — your memory and your bill follow you.

### What you get

- 🧠 **Persistent memory** across sessions *and* across models
- 🤖 **Auto-memory** — it captures your preferences from conversation (EN + 中文)
- 📊 **Full observability** — tokens, cost, and latency for every call
- 💰 **Daily budget** with 80% / 100% warnings
- 🗂️ **Scopes** — isolate memory per project (`work`, `home`, …)
- 🔌 **22 providers** — cloud, Chinese clouds, fast-inference hosts, local
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
pip install recall-ai            # base (keyword memory + tracing)
# optional extras:
#   pip install 'recall-ai[embeddings]'  # semantic memory search
#   pip install 'recall-ai[openai]'      # GPT / DeepSeek / Qwen
#   pip install 'recall-ai[anthropic]'   # Claude
#   pip install 'recall-ai[dashboard]'   # web dashboard
#   pip install 'recall-ai[all]'         # everything
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

# 3. See exactly what you spent (and your budget)
recall stats
```

```
recall stats  (v0.1.0)

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
pip install 'recall-ai[dashboard]'
recall dashboard          # → http://127.0.0.1:8745
```

A single local page: memory cards, cost-by-model, recent calls. No build step,
no telemetry, no cloud.

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
| `recall forget <id>` | Delete a memory |
| `recall scope [name]` | Switch / list scopes |
| `recall chat [provider model] "..."` | Chat with memory + tracing + auto-memory |
| `recall stats` | Tokens, cost & budget overview |
| `recall recent` | Recent model calls |
| `recall models` | Supported providers |
| `recall export/import <file>` | Backup / restore memories |
| `recall config show/set/path` | View & edit configuration |
| `recall dashboard` | Launch local web UI |

## Where is my data?

A single SQLite file at `~/.recall/recall.db` (override with `RECALL_HOME`).
That's it. No accounts, no servers, no telemetry. Back it up, sync it, delete
it — it's yours.

## Why local-first?

- **Privacy** — your memories and prompts stay on your disk.
- **Portability** — one file you can move, version, or sync yourself.
- **No lock-in** — works across providers; swap models freely.

## Roadmap

- [x] Auto-extract memories from conversations
- [x] Budget alerts ("you've spent $X today")
- [x] Gemini + local Ollama / LM Studio adapters
- [x] Export / import memories
- [x] Memory scopes
- [ ] Memory editing & merge / dedupe by similarity
- [ ] Streaming chat output
- [ ] LLM-based memory extraction (opt-in, higher recall)
- [ ] PyPI release (`pip install recall-ai`)
- [ ] MCP server so any agent can read/write recall memory

## Contributing

Issues and PRs welcome. Run tests with:

```bash
pip install 'recall-ai[dev]'
pytest
```

## License

MIT © [zionLyl](https://github.com/zionLyl)
