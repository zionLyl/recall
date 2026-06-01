# Launch copy for memstash

Ready-to-post drafts. Replace the demo GIF/asciinema link where noted. Post in
**your own voice** — these are starting points. Be present in the comments for
the first few hours (that's what converts views → stars).

---

## Show HN

**Title** (HN likes plain + specific; ≤ 80 chars):

> Show HN: Memstash – local-first memory + cost tracking for LLMs, one SQLite file

**First comment (you, right after posting):**

> I kept re-explaining myself to every LLM and had no idea what any of it cost.
> Existing fixes were either memory-only (mem0, Zep) or observability-only
> (Langfuse, Helicone), and the serious ones want a Postgres/ClickHouse/graph-DB
> stack or a cloud account.
>
> Memstash does both in one local SQLite file — `pip install memstash`, no
> server, no account, nothing leaves your machine:
>
> - Persistent memory auto-injected into any model (GPT/Claude/DeepSeek/Qwen/…,
>   22 providers). Switch models, your memory + bill follow you.
> - Hybrid retrieval (embeddings + BM25 via SQLite FTS5), opt-in conflict
>   resolution (mem0-style ADD/UPDATE/DELETE/NOOP), bi-temporal "what did I know
>   on date X", graph-lite relations, doc ingestion.
> - Per-call tokens/cost/latency, per-turn trace trees, budgets, and quality
>   evals — the observability side, also local.
> - MCP server so Claude Desktop/Cursor read/write the same memory; can also
>   sink LangChain/OpenAI-SDK calls via OpenInference.
>
> It ships a reproducible benchmark (`memstash benchmark`) so the retrieval
> numbers are honest, not vibes. MIT. Feedback very welcome — especially on the
> local-first constraints I'm trying to hold.
>
> Repo: https://github.com/zionLyl/recall · `pip install memstash`

---

## r/LocalLLaMA  (the best-fit community — lead with "no cloud")

**Title:**

> Memstash: give any local model persistent memory + cost tracking, in one SQLite file (no server, no cloud)

**Body:**

> Built this for the "I run models locally and don't want a cloud memory service"
> crowd. `pip install memstash`, point it at Ollama / LM Studio (or any
> OpenAI-compatible endpoint), done. One SQLite file at `~/.memstash/` holds your
> memories *and* every call's tokens/cost/latency. No account, no server, no
> telemetry.
>
> - Works fully offline: keyword/BM25 memory with zero heavy deps; semantic
>   search via a local embedding model **or** your Ollama `/embeddings` (no
>   PyTorch download needed).
> - Memory auto-injected into chats; opt-in LLM conflict-resolution so facts stay
>   current instead of piling up; bi-temporal history; graph-lite relations.
> - `memstash chat` is an interactive REPL; `memstash stats`/`trace` show cost.
> - MCP server → Claude Desktop / Cursor use the same local brain.
>
> Honest about what it is: a local-first single-file tool, not a hosted service.
> Reproducible benchmark included. MIT. Would love feedback from people running
> local stacks: https://github.com/zionLyl/recall

*(Check r/LocalLLaMA self-promo rules; engage genuinely, don't drive-by.)*

---

## X / Twitter thread

**1/**
> Switching LLMs means re-explaining yourself every time — and you have no idea
> what any of it costs.
>
> Built Memstash: persistent memory + full cost/observability for any model, in
> one local SQLite file. `pip install memstash`. No server, no account. 🧵

**2/**
> Memory tools (mem0, Zep) don't track cost. Observability tools (Langfuse,
> Phoenix) don't do memory. The serious ones need Postgres/ClickHouse/a graph DB.
>
> Memstash does memory + observability + evals in one file. That's the whole pitch.

**3/**
> What you get, all local:
> • memory auto-injected into 22 providers (GPT/Claude/DeepSeek/Qwen…)
> • hybrid retrieval (embeddings + BM25)
> • conflict resolution, bi-temporal history, graph-lite
> • per-call tokens/cost/latency + trace trees + budgets + evals
> • MCP server

**4/**
> It even captures your *existing* app's calls: `memstash.instrument()` sinks
> LangChain / OpenAI-SDK spans (OpenInference) into the same local DB. The local
> counterpart to Phoenix/Langfuse — no backend.

**5/**
> Ships a reproducible benchmark so retrieval quality is measured, not claimed.
> MIT, 150+ tests, single SQLite file.
>
> `pip install memstash` → https://github.com/zionLyl/recall
> ⭐ if it's useful — building in the open. [attach demo GIF]

---

## dev.to / Hashnode article

**Title:** *I built a local-first memory + observability layer for LLMs (one `pip install`, one SQLite file)*

**Outline:**
1. The two problems: LLMs forget you; you can't see token/cost. Why I didn't want
   a cloud service or a Postgres/graph-DB stack to fix them.
2. The idea: one SQLite file = memories + traces. Show `pip install memstash`,
   `memstash add`, `memstash chat`, `memstash stats` (paste the real output).
3. How retrieval works: embeddings + BM25 (SQLite FTS5) fused with RRF; opt-in
   LLM conflict resolution; bi-temporal queries. Include the benchmark numbers.
4. The observability side: trace trees, budgets, evals, and `instrument()` for
   capturing existing LangChain/OpenAI-SDK apps.
5. The local-first constraint as a feature, and what it costs (no multi-device
   sync yet — honest).
6. Call to action: try it, file issues, the repo + good-first-issues.

---

## awesome-list PRs (easy, durable traffic)

Add an entry like this to relevant lists:

> **[memstash](https://github.com/zionLyl/recall)** — Local-first LLM memory +
> cost/observability + evals in a single SQLite file. No server, no account.
> Memory auto-injection across 22 providers, hybrid retrieval, MCP server. `pip
> install memstash`.

Target lists: awesome-llm, awesome-local-llm, awesome-mcp-servers,
awesome-python, awesome-llmops, awesome-ai-agents. (Read each list's
contribution guide; one focused PR each.)
