# How memstash memory works

A precise, no-magic description of what memstash stores, how it recalls, how it
forgets, how it guards against poisoning, and how you stay in control. Everything
lives in one local SQLite file (`~/.memstash/memstash.db`); nothing leaves your
machine.

## What's stored

Each **memory** is one row with:

| Field | Meaning |
|---|---|
| `content` | the text (a fact/preference/decision/…), not a raw transcript |
| `mem_type` | `note` (default) / `preference` / `fact` / `decision` / `constraint` / `event` / `lesson` (free-form) |
| `confidence` | 0–1, how sure (manual = 1.0; you can lower it) |
| `scope` | namespace for isolation (`default`, `work`, a project, …) |
| `tags` | free-form labels |
| `source` | origin category: `manual` / `auto` / `document` / `mcp` / `imported` / `web` / `tool` … |
| `source_ref` | where it came from (URL / file path / origin) |
| `source_trace` | the chat call it was auto-captured from (provenance) |
| `created_at`, `valid_from`, `valid_to` | timeline (for bi-temporal queries) |
| `active`, `quarantined` | lifecycle / firewall state |
| `embedding` | optional vector for semantic search |

Separately, every model call is recorded as a **trace** (model, tokens, cost,
latency) — that's the observability side, kept apart from memories.

**What it does *not* store:** raw conversation transcripts as memories. Auto-capture
extracts durable first-person facts; the full prompt/reply lives only in the trace
log (truncated), not the memory store.

## How recall works

When memstash needs context (a chat turn, or `memstash search`):

1. **Scope** — only the active scope is searched (per-project isolation; see
   `scope_auto`).
2. **Hybrid retrieval** — semantic similarity (embeddings) **and** BM25 keyword
   match (SQLite FTS5) are fused with Reciprocal Rank Fusion. With no embeddings
   installed it's keyword-only.
3. **Relevance gate** — only memories scoring ≥ `memory_min_score` are kept
   (raise it to be stricter; if nothing is relevant, nothing is injected).
4. **Top-k** — at most `memory_inject_limit` memories are injected (default 5),
   so prompts stay small.
5. Optional **recency** (`recency_weight`) and **graph** (`graph_weight`) signals
   can be blended in.

Inactive and quarantined memories are never retrieved.

## How forgetting works

Memory is not a junk drawer — it decays and is correctable:

- **Soft-forget** (`forget --soft`, `prune`) deactivates a memory but keeps it as
  history; **hard `forget`** deletes it.
- **`prune --older-than DAYS --unused`** bulk-forgets stale / never-recalled memories.
- **Recency weighting** down-ranks old, unused memories at retrieval time.
- **Conflict resolution** (`memory_ops=llm`): a new fact can **UPDATE** or
  **DELETE** an existing one. UPDATE *supersedes* — the old fact's validity window
  is closed and kept as history, so point-in-time queries still work.
- **Bi-temporal**: `list --at <when>` shows what was valid at a past time.

## How poisoning is prevented (write firewall)

Long-term memory amplifies prompt injection, so writes are filtered:

- **Trusted sources** (`manual`, `auto` — your own input) pass through.
- **Untrusted origins** (`web`, `tool`, `external`) are **quarantined**.
- **Other sources** (`document`, `mcp`, …) are content-scanned for injection
  patterns and quarantined only if flagged.
- Quarantined memories are **inactive — never injected** — until you review them:
  `memstash quarantine` → `approve <id>` / `reject <id>`.
- Modes: `firewall_mode = quarantine` (default) / `warn` / `off`.

## Control, delete, migrate

- **Inspect**: `list`, `search`, `show <id>` (shows type, confidence, source, provenance).
- **Edit**: `edit <id>` rewrites content/tags (and re-embeds).
- **Delete**: `forget <id>` (hard) or `--soft`.
- **Export / import**: `export file.json` / `import file.json` — portable, plain JSON.
- **Move/back up**: copy the single SQLite file, or set `MEMSTASH_HOME`.

## Privacy

100% local: no account, no server, no telemetry. Your memories and prompts stay
in one file on your disk that you can read (it's SQLite), back up, sync yourself,
or delete. See [README](README.md) for setup and [ROADMAP](ROADMAP.md) for plans.
