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
# 1. Teach it about you (once)
recall add "I prefer concise answers with tables" --tags style
recall add "I do A-share & HK quant research"     --tags work

# 2. Chat with ANY model — it already knows you, and the call is traced
export OPENAI_API_KEY=sk-...
recall chat openai gpt-4o-mini "How should you reply to me?"

# 3. See exactly what you spent
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

## Supported models

| Provider | `provider` arg | Example models |
|---|---|---|
| OpenAI | `openai` | `gpt-4o`, `gpt-4o-mini`, `gpt-4.1` |
| Anthropic | `anthropic` | `claude-3-5-sonnet`, `claude-3-5-haiku` |
| DeepSeek | `deepseek` | `deepseek-chat`, `deepseek-reasoner` |
| Qwen (DashScope) | `qwen` | `qwen-plus`, `qwen-max` |
| Any OpenAI-compatible | `openai-compatible` | set `--base-url` |

```bash
recall models   # list providers + default base URLs
```

## CLI reference

| Command | What it does |
|---|---|
| `recall add "..." [--tags a,b]` | Store a memory |
| `recall search "..."` | Semantic (or keyword) search |
| `recall list` | List all memories |
| `recall forget <id>` | Delete a memory |
| `recall chat <provider> <model> "..."` | Chat with memory + tracing |
| `recall stats` | Token usage & cost overview |
| `recall recent` | Recent model calls |
| `recall models` | Supported providers |
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

- [ ] Auto-extract memories from conversations
- [ ] Memory editing & merge
- [ ] Budget alerts ("you've spent $X today")
- [ ] More adapters (Gemini, local Ollama)
- [ ] Export / import memories

## Contributing

Issues and PRs welcome. Run tests with:

```bash
pip install 'recall-ai[dev]'
pytest
```

## License

MIT © [zionLyl](https://github.com/zionLyl)
