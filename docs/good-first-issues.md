# Good first issues

Starter tasks for new contributors. Each is scoped, testable offline, and fits
the local-first / single-SQLite philosophy. (Maintainer: file these as GitHub
issues labeled `good first issue` so they show up in the repo's contributor UI.)

1. **`memstash tui`** — a Textual TUI to browse memories / traces / stats over
   the existing SQLite. Read-only first. *(Closes the "no GUI" gap, stays local.)*

2. **More provider pricing** — extend `memstash/pricing.py` with current models
   (add tests in `tests/test_pricing_map.py`). Pure data + a prefix-match test.

3. **`memstash export --format md|csv`** — export memories as Markdown or CSV in
   addition to JSON. Small `store.export_memories` + CLI flag + test.

4. **MCP resource for memories** — add an MCP *resource* (not just tools) so
   clients can browse memory read-only. Extends `memstash/mcp_server.py`.

5. **`memstash import` from ChatGPT/Claude export** — parse an exported
   conversation file and ingest durable facts. Builds on `ingest.py`.

6. **Stopword filtering in FTS query builder** — improve BM25 precision by
   dropping ultra-common tokens in `Store._fts_match`; verify with a benchmark
   delta in `bench.py`.

7. **`memstash doctor` upgrades** — also report embedding backend status, whether
   numpy is present (vectorized retrieval), and pricing coverage.

8. **Shell completion** — ship `memstash --install-completion` docs and test the
   Typer completion wiring.

Pick one, open a draft PR early, run `pytest -q` + `ruff check memstash`.
