# Contributing to memstash

Thanks for your interest! memstash is a **local-first** LLM memory +
observability tool — a single SQLite file, no server, no account. Contributions
that keep that philosophy are very welcome.

## Dev setup

```bash
git clone https://github.com/zionLyl/memstash.git memstash && cd memstash
pip install -e '.[dev]'        # add [all] for every optional feature
pytest -q                      # 150+ tests, all offline (no API key needed)
ruff check memstash            # lint
```

Tests are deterministic and never hit the network — adapters are faked, so the
whole suite runs in ~2s with no keys.

## Project layout

| Path | What |
|---|---|
| `memstash/core.py` | `Memstash` (aka `Recall`) — chat + memory + tracing glue |
| `memstash/store.py` | SQLite layer (memories, traces, relations, prompts, evals) |
| `memstash/memory.py` | retrieval: embeddings + BM25 fusion, lifecycle, dedupe |
| `memstash/adapters/` | provider adapters (OpenAI-compatible, Anthropic, Gemini) |
| `memstash/bench.py` | reproducible benchmark (`memstash benchmark`) |
| `memstash/cli.py` | the `memstash` CLI |

## Ground rules

- **Stay local-first.** No mandatory server, account, telemetry, or external
  database. Optional integrations are fine; required ones are not.
- **Optional deps stay optional.** Lazy-import heavy packages; the base install
  is just `typer` + `rich`.
- **Add a test** for any behavior change. Keep the suite offline & deterministic.
- **Run `ruff check memstash` and `pytest -q`** before opening a PR.

## Good first issues

See [`docs/good-first-issues.md`](docs/good-first-issues.md) for a starter list
(a TUI, more provider pricing, an `mcp` resource, export formats, …).

## Releasing (maintainers)

Bump the version in `pyproject.toml` + `memstash/__init__.py`, update
`CHANGELOG.md`, then push a tag: `git tag vX.Y.Z && git push origin vX.Y.Z`.
The `publish.yml` workflow builds and publishes to PyPI via Trusted Publishing.
