"""engram CLI.

  engram init                                 # guided first-time setup
  engram add "I prefer concise answers"       # store a memory
  engram search "preferences"                 # semantic/keyword search
  engram list                                 # list memories (active scope)
  engram forget 3                             # delete a memory
  engram chat openai gpt-4o-mini "..."        # chat with memory + tracing
  engram stats                                # tokens + cost + budget
  engram recent                               # recent model calls
  engram models                               # supported providers
  engram scope work                           # switch active memory scope
  engram config set daily_budget_usd 1.0      # configure defaults
  engram export mem.json / engram import ...   # backup & restore
  engram doctor                               # check which API keys are set
  engram dashboard                            # local web UI
"""

from __future__ import annotations

import os
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .adapters import BASE_URLS, KEY_ENV, REGISTRY
from .config import Config, config_path
from .core import Recall

app = typer.Typer(
    add_completion=False,
    help="Your local AI brain: persistent memory + full observability for any model.",
)
config_app = typer.Typer(help="View and edit configuration.")
app.add_typer(config_app, name="config")
prompt_app = typer.Typer(help="Save and reuse prompt templates / fragments.")
app.add_typer(prompt_app, name="prompt")
suite_app = typer.Typer(help="Save and reuse eval suites.")
app.add_typer(suite_app, name="eval-suite")
console = Console()


def _r() -> Recall:
    return Recall()


def _ollama_running(host: str = "localhost", port: int = 11434) -> bool:
    """Quick, non-blocking check for a local Ollama server (zero-key default)."""
    import socket
    try:
        with socket.create_connection((host, port), timeout=0.3):
            return True
    except OSError:
        return False


def _parse_when(s: str) -> float:
    """Parse a point in time: 'YYYY-MM-DD', a relative '30d'/'12h'/'45m' ago, or
    a raw epoch. Returns a Unix timestamp."""
    import re
    import time as _time
    from datetime import datetime

    s = s.strip()
    m = re.fullmatch(r"(\d+)\s*([dhm])", s)
    if m:
        unit = {"d": 86400, "h": 3600, "m": 60}[m.group(2)]
        return _time.time() - int(m.group(1)) * unit
    try:
        return datetime.fromisoformat(s).timestamp()
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError as e:
        raise typer.BadParameter(f"can't parse time '{s}' (use YYYY-MM-DD, '30d', or epoch)") from e


# ---- setup --------------------------------------------------------------
@app.command()
def init():
    """Guided first-time setup: pick a default model and detect API keys."""
    cfg = Config.load()
    console.print("[bold]🧠 engram setup[/bold]\n")

    available = [p for p in sorted(REGISTRY) if os.environ.get(KEY_ENV.get(p, ""))]
    ollama = _ollama_running()
    if available:
        console.print(f"Detected API keys for: [green]{', '.join(available)}[/green]")
    if ollama:
        console.print("Detected a running [green]Ollama[/green] at localhost:11434 "
                      "(local, no API key needed).")
    if not available and not ollama:
        console.print("[yellow]No provider API keys or local Ollama detected.[/yellow] "
                      "Set e.g. OPENAI_API_KEY, or run Ollama, then re-run.")

    # Prefer a key'd cloud provider; else local Ollama; else OpenAI as a hint.
    if available:
        default_provider, default_model = available[0], "gpt-4o-mini"
    elif ollama:
        default_provider, default_model = "ollama", "llama3"
    else:
        default_provider, default_model = "openai", "gpt-4o-mini"
    provider = typer.prompt("Default provider", default=cfg.default_provider or default_provider)
    model = typer.prompt("Default model", default=cfg.default_model or default_model)
    budget = typer.prompt("Daily budget USD (0 = none)", default=str(cfg.daily_budget_usd))

    cfg.default_provider = provider
    cfg.default_model = model
    cfg.daily_budget_usd = float(budget)
    cfg.save()
    console.print(f"\n[green]✓[/green] Saved to {config_path()}")
    console.print("Try: [cyan]engram add \"I prefer concise answers\"[/cyan] then "
                  "[cyan]engram chat \"hi\"[/cyan]")


@app.command()
def doctor():
    """Check which providers have API keys configured."""
    table = Table(title="Provider readiness")
    table.add_column("Provider", style="cyan")
    table.add_column("Key env", style="dim")
    table.add_column("Status")
    for name in sorted(REGISTRY):
        env = KEY_ENV.get(name, "ENGRAM_API_KEY")
        if name in ("ollama", "lmstudio"):
            status = "[blue]local (no key)[/blue]"
        elif os.environ.get(env) or os.environ.get("ENGRAM_API_KEY"):
            status = "[green]✓ ready[/green]"
        else:
            status = "[dim]— not set[/dim]"
        table.add_row(name, env, status)
    console.print(table)


# ---- memory -------------------------------------------------------------
@app.command()
def add(
    content: str = typer.Argument(..., help="The memory to store."),
    tags: str = typer.Option("", "--tags", "-t", help="Comma-separated tags."),
    scope: str = typer.Option(None, "--scope", help="Memory scope (defaults to active)."),
):
    """Store a persistent memory."""
    r = _r()
    tag_list = [t for t in tags.split(",") if t.strip()]
    mid = r.remember(content, tags=tag_list, scope=scope)
    if mid is None:
        console.print("[yellow]Already remembered (duplicate skipped).[/yellow]")
    else:
        mode = "semantic" if r.memory.has_embeddings else "keyword"
        console.print(f"[green]✓[/green] Remembered #{mid} in '{scope or r.scope}' [dim]({mode})[/dim]")
    r.close()


@app.command()
def search(
    query: str = typer.Argument(..., help="What to look for."),
    limit: int = typer.Option(5, "--limit", "-n"),
    all_scopes: bool = typer.Option(False, "--all", help="Search across all scopes."),
):
    """Search your memories."""
    r = _r()
    hits = r.recall_memories(query, limit=limit, scope=None if all_scopes else r.scope)
    if not hits:
        console.print("[yellow]No matching memories.[/yellow]")
        r.close()
        return
    table = Table(title=f'Memories matching "{query}"')
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("Score", style="magenta", justify="right")
    table.add_column("Memory")
    table.add_column("Scope", style="blue")
    table.add_column("Tags", style="dim")
    for m in hits:
        table.add_row(str(m.id), f"{m.score:.2f}", m.content, m.scope, ", ".join(m.tags))
    console.print(table)
    r.close()


@app.command("list")
def list_memories(
    all_scopes: bool = typer.Option(False, "--all", help="List across all scopes."),
    at: str = typer.Option(None, "--at", help="Time-travel: memories valid at this time (YYYY-MM-DD, '30d'/'12h' ago, or epoch)."),
):
    """List stored memories (active scope by default). With --at, show what was
    valid at a past time (includes since-forgotten memories)."""
    r = _r()
    scope = None if all_scopes else r.scope
    if at is not None:
        ts = _parse_when(at)
        mems = r.store.memories_as_of(ts, scope=scope)
        title_suffix = f" · as of {at}"
    else:
        mems = r.store.all_memories(scope=scope)
        title_suffix = "" if all_scopes else f" · scope='{r.scope}'"
    if not mems:
        msg = f"No memories valid as of {at}." if at else f"No memories in '{r.scope}'. Add one: engram add \"...\""
        console.print(f"[yellow]{msg}[/yellow]")
        r.close()
        return
    table = Table(title=f"Memories ({len(mems)})" + title_suffix)
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("Memory")
    table.add_column("Scope", style="blue")
    table.add_column("Src", style="dim")
    table.add_column("Tags", style="dim")
    from rich.markup import escape
    for m in mems:
        src = "🤖" if m.source == "auto" else ""
        marker = "" if m.active else "[dim](past)[/dim] "
        table.add_row(str(m.id), marker + escape(m.content), m.scope, src, ", ".join(m.tags))
    console.print(table)
    r.close()


@app.command()
def ingest(
    path: str = typer.Argument(..., help="Path to a .txt / .md (or .pdf) file."),
    scope: str = typer.Option(None, "--scope", help="Scope to store into (defaults to active)."),
    tags: str = typer.Option("", "--tags", "-t", help="Extra comma-separated tags."),
    max_chars: int = typer.Option(500, "--max-chars", help="Max characters per chunk."),
):
    """Ingest a document into searchable memory (chunked; 100% local)."""
    r = _r()
    tag_list = [t for t in tags.split(",") if t.strip()]
    try:
        res = r.ingest(path, scope=scope, tags=tag_list, max_chars=max_chars)
    except (FileNotFoundError, RuntimeError) as e:
        console.print(f"[red]{e}[/red]", markup=False)
        r.close()
        raise typer.Exit(1)
    from rich.markup import escape
    console.print(
        f"[green]✓[/green] Ingested {res['new']}/{res['chunks']} chunk(s) from "
        f"{escape(res['path'])} into '{escape(scope or r.scope)}'"
    )
    r.close()


@app.command()
def show(memory_id: int = typer.Argument(..., help="Memory ID to inspect.")):
    """Show a memory's full detail, including provenance (the chat it came from)."""
    r = _r()
    m = r.store.get_memory(memory_id)
    if m is None:
        console.print(f"[red]✗[/red] No memory #{memory_id}")
        r.close()
        raise typer.Exit(1)
    console.print(f"[bold]#{m.id}[/bold] [dim]({m.scope})[/dim]")
    console.print(m.content, markup=False)
    console.print(f"[dim]source={m.source} · tags={', '.join(m.tags) or '—'} · "
                  f"hits={m.hit_count} · active={bool(m.active)}[/dim]")
    if m.source_trace:
        tr = r.store.get_trace(m.source_trace)
        if tr:
            snippet = (tr.get("prompt") or "")[:200]
            console.print(f"[dim]captured from call #{m.source_trace} "
                          f"({tr.get('model','?')}):[/dim]")
            console.print(f"  [dim]{snippet}[/dim]", markup=False)
    r.close()


@app.command()
def forget(
    memory_id: int = typer.Argument(..., help="Memory ID to delete."),
    soft: bool = typer.Option(False, "--soft", help="Soft-forget (deactivate, keep history) instead of hard delete."),
):
    """Delete a memory by ID (hard delete, or --soft to keep history)."""
    r = _r()
    ok = r.forget(memory_id, soft=soft)
    verb = "Soft-forgot" if soft else "Forgot"
    console.print(f"[green]✓[/green] {verb} #{memory_id}" if ok else f"[red]✗[/red] No memory #{memory_id}")
    r.close()


@app.command()
def prune(
    older_than: float = typer.Option(None, "--older-than", help="Soft-forget memories older than N days."),
    unused: bool = typer.Option(False, "--unused", help="Restrict to memories never retrieved (hit_count = 0)."),
    all_scopes: bool = typer.Option(False, "--all", help="Prune across all scopes."),
):
    """Soft-forget stale memories (deactivate, keeping history)."""
    r = _r()
    if older_than is None and not unused:
        console.print("[yellow]Specify --older-than DAYS and/or --unused.[/yellow]")
        r.close()
        raise typer.Exit(1)
    n = r.prune(scope=None if all_scopes else r.scope, older_than_days=older_than, unused=unused)
    console.print(f"[green]✓[/green] Soft-forgot {n} memory/-ies.")
    r.close()


@app.command()
def edit(
    memory_id: int = typer.Argument(..., help="Memory ID to edit."),
    content: str = typer.Argument(None, help="New content (omit to only change tags)."),
    tags: str = typer.Option(None, "--tags", "-t", help="Replace tags (comma-separated)."),
):
    """Edit a memory's content and/or tags (re-embeds if content changed)."""
    r = _r()
    if content is None and tags is None:
        console.print("[yellow]Nothing to change — pass new content and/or --tags.[/yellow]")
        r.close()
        raise typer.Exit(1)
    if r.store.get_memory(memory_id) is None:
        console.print(f"[red]✗[/red] No memory #{memory_id}")
        r.close()
        raise typer.Exit(1)
    tag_list = [t for t in tags.split(",") if t.strip()] if tags is not None else None
    ok = r.edit(memory_id, content=content, tags=tag_list)
    console.print(f"[green]✓[/green] Updated #{memory_id}" if ok else "[red]✗[/red] No change")
    r.close()


@app.command()
def dedupe(
    threshold: float = typer.Option(0.9, "--threshold", "-th", help="Cosine similarity to merge (0–1)."),
    all_scopes: bool = typer.Option(False, "--all", help="Dedupe across all scopes."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would merge without changing anything."),
):
    """Merge near-duplicate memories by similarity (keeps the earliest, unions tags)."""
    r = _r()
    if not r.memory.has_embeddings:
        console.print(
            "[yellow]Similarity dedupe needs embeddings.[/yellow] "
            "Install: pip install 'engram-ai[embeddings]'", markup=False,
        )
        r.close()
        raise typer.Exit(1)
    scope = None if all_scopes else r.scope
    if dry_run:
        # Preview: run the same clustering but don't persist.
        from .memory import _cosine, _unpack
        rows = r.store.all_memories_with_embeddings(scope=scope)
        items = [(mid, c, _unpack(b), sc) for mid, c, _t, b, _cr, sc, _s in rows if b]
        items.sort(key=lambda x: x[0])
        seen, groups = set(), []
        for i, (mid, c, vec, sc) in enumerate(items):
            if mid in seen:
                continue
            dupes = [(m2, c2) for m2, c2, v2, sc2 in items[i + 1:]
                     if m2 not in seen and sc2 == sc and _cosine(vec, v2) >= threshold]
            if dupes:
                for m2, _ in dupes:
                    seen.add(m2)
                groups.append((mid, c, dupes))
        if not groups:
            console.print("[green]No near-duplicates found.[/green]")
        else:
            for kept, kept_c, dupes in groups:
                console.print(f"[cyan]keep #{kept}[/cyan] {kept_c}", markup=False)
                for m2, c2 in dupes:
                    console.print(f"  [dim]merge #{m2}[/dim] {c2}", markup=False)
            console.print(f"\n[yellow]Dry run — {sum(len(d) for _,_,d in groups)} "
                          f"memories would be merged. Re-run without --dry-run.[/yellow]")
        r.close()
        return
    merges = r.dedupe(scope=scope, threshold=threshold)
    removed = sum(len(m["removed"]) for m in merges)
    if not merges:
        console.print("[green]No near-duplicates found.[/green]")
    else:
        console.print(f"[green]✓[/green] Merged {removed} duplicate(s) into {len(merges)} memory/-ies.")
    r.close()


@app.command()
def graph(
    entity: str = typer.Argument(None, help="Entity to query (omit to list all relations)."),
    add: str = typer.Option(None, "--add", help='Add a triple: "subject|predicate|object".'),
):
    """View or add entity relationships (graph-lite). Mined from chats when
    `config set graph_extract true`."""
    r = _r()
    if add:
        parts = [p.strip() for p in add.split("|")]
        if len(parts) != 3:
            console.print('[red]Use --add "subject|predicate|object"[/red]')
            r.close()
            raise typer.Exit(1)
        rid = r.add_relation(*parts)
        console.print(f"[green]✓[/green] Added relation #{rid}" if rid else "[yellow]Already known.[/yellow]")
        r.close()
        return
    rels = r.graph(entity)
    if not rels:
        msg = f"No relations for '{entity}'." if entity else "No relations yet."
        console.print(f"[yellow]{msg}[/yellow]")
        r.close()
        return
    title = f"Relations · {entity}" if entity else f"Relations ({len(rels)}) · scope='{r.scope}'"
    table = Table(title=title)
    table.add_column("Subject", style="cyan")
    table.add_column("Predicate", style="magenta")
    table.add_column("Object", style="cyan")
    for rel in rels:
        table.add_row(rel["subject"], rel["predicate"], rel["object"])
    console.print(table)
    r.close()


@app.command()
def scope(name: str = typer.Argument(None, help="Scope to switch to. Omit to list scopes.")):
    """Switch the active memory scope, or list scopes."""
    r = _r()
    if name is None:
        scopes = r.store.list_scopes()
        table = Table(title="Memory scopes")
        table.add_column("Scope", style="cyan")
        table.add_column("Memories", justify="right")
        table.add_column("Active", justify="center")
        seen = {s for s, _ in scopes}
        if r.scope not in seen:
            scopes.append((r.scope, 0))
        for s, c in scopes:
            table.add_row(s, str(c), "✓" if s == r.scope else "")
        console.print(table)
    else:
        r.config.active_scope = name
        r.config.save()
        console.print(f"[green]✓[/green] Active scope → '{name}'")
    r.close()


# ---- chat ---------------------------------------------------------------
def _print_chat_meta(out) -> None:
    console.print(
        f"[dim]— {out.model} · {out.input_tokens}+{out.output_tokens} tok · "
        f"${out.cost_usd:.4f} · {out.latency_ms}ms[/dim]"
    )
    if out.auto_remembered:
        console.print(f"[dim]🤖 remembered: {'; '.join(out.auto_remembered)}[/dim]", markup=False)
    if out.graph_added:
        console.print(f"[dim]🕸 +{out.graph_added} relation(s)[/dim]")
    if out.budget_warning:
        console.print(f"[bold yellow]⚠ {out.budget_warning}[/bold yellow]")


def _send_chat(r, provider, model, prompt, system, use_memory, auto, use_stream, history=None):
    """Send one turn; print the reply (streamed or whole). Returns the outcome,
    or None on error (already reported)."""
    try:
        if use_stream:
            out = r.stream(
                provider, model, prompt,
                on_token=lambda t: typer.echo(t, nl=False),
                system=system, use_memory=use_memory, auto_memory=auto, history=history,
            )
            typer.echo("")
        else:
            out = r.chat(
                provider, model, prompt, system=system,
                use_memory=use_memory, auto_memory=auto, history=history,
            )
            console.print(out.text, markup=False)
        return out
    except Exception as e:  # noqa: BLE001
        from rich.markup import escape
        console.print(f"[red]Error:[/red] {escape(str(e))}")
        return None


def _chat_repl(r, provider, model, system, use_memory, auto, use_stream) -> None:
    """Interactive multi-turn chat loop over the configured model. Memory is
    injected + auto-captured each turn; conversation history is kept in-session."""
    console.print(
        "[dim]Interactive chat — memory + tracing on. /exit or Ctrl-D to quit.[/dim]"
    )
    history: list[dict] = []
    while True:
        try:
            line = console.input("[bold cyan]you ›[/bold cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break
        if not line:
            continue
        if line in ("/exit", "/quit"):
            break
        out = _send_chat(r, provider, model, line, system, use_memory, auto, use_stream, history)
        if out is None:
            if not history:   # first turn failed (e.g. no provider/model) → stop
                break
            continue
        _print_chat_meta(out)
        history.append({"role": "user", "content": line})
        history.append({"role": "assistant", "content": out.text})


@app.command()
def chat(
    arg1: str = typer.Argument(None, help="Provider, OR the prompt if defaults are set."),
    arg2: str = typer.Argument(None, help="Model (when provider given)."),
    arg3: str = typer.Argument(None, help="Prompt (when provider+model given)."),
    system: str = typer.Option(None, "--system", "-s"),
    no_memory: bool = typer.Option(False, "--no-memory", help="Skip memory injection."),
    no_auto: bool = typer.Option(False, "--no-auto", help="Skip auto-memory capture."),
    stream: bool = typer.Option(None, "--stream/--no-stream", help="Stream output token-by-token (default from config)."),
    template: str = typer.Option(None, "--template", "-T", help="Use a saved prompt template as the prompt."),
    var: list[str] = typer.Option(None, "--var", "-V", help="Template variable k=v (repeatable)."),
):
    """Chat with any model — memory injected, cost & tokens traced automatically.

    Forms:
      engram chat <provider> <model> "prompt"
      engram chat "prompt"                  (uses configured defaults)
    """
    r = _r()
    repl = False
    if template is not None:
        # Template supplies the prompt; positionals (if any) are provider/model.
        from .prompts import parse_vars
        prompt = r.render_prompt(template, parse_vars(var))
        if prompt is None:
            console.print(f"[red]No template '{template}'[/red]")
            r.close()
            raise typer.Exit(1)
        provider, model = (arg1, arg2) if arg2 is not None else (None, None)
    elif arg1 is None:
        # No prompt → drop into an interactive REPL using configured defaults.
        provider, model, prompt, repl = None, None, None, True
    # Flexible argument parsing.
    elif arg2 is None and arg3 is None:
        provider, model, prompt = None, None, arg1
    elif arg3 is None:
        # ambiguous: treat as provider+prompt only if defaults missing model
        provider, model, prompt = arg1, arg2, None
        if prompt is None:
            console.print("[red]Provide a prompt.[/red]")
            r.close()
            raise typer.Exit(1)
    else:
        provider, model, prompt = arg1, arg2, arg3

    use_stream = r.config.stream if stream is None else stream

    if repl:
        _chat_repl(r, provider, model, system, not no_memory, not no_auto, use_stream)
        r.close()
        return

    out = _send_chat(r, provider, model, prompt, system, not no_memory, not no_auto, use_stream)
    if out is None:
        r.close()
        raise typer.Exit(1)
    _print_chat_meta(out)
    r.close()


# ---- observability ------------------------------------------------------
@app.command()
def stats():
    """Show token usage, cost, and budget."""
    r = _r()
    s = r.stats()
    console.print(f"[bold]engram stats[/bold]  [dim](v{__version__})[/dim]\n")
    console.print(f"Memories stored : [cyan]{s['memory_count']}[/cyan]")
    console.print(f"Model calls     : [cyan]{s['calls']}[/cyan]")
    console.print(
        f"Tokens          : [cyan]{s['input_tokens']:,}[/cyan] in / "
        f"[cyan]{s['output_tokens']:,}[/cyan] out"
    )
    console.print(f"Total cost      : [green]${s['cost_usd']:.4f}[/green]")
    budget = s.get("daily_budget", 0)
    today = s.get("cost_today", 0)
    if budget and budget > 0:
        pct = today / budget * 100
        color = "red" if pct >= 100 else "yellow" if pct >= 80 else "green"
        console.print(f"Today           : [{color}]${today:.4f} / ${budget:.2f} ({pct:.0f}%)[/{color}]")
    else:
        console.print(f"Cost today      : [green]${today:.4f}[/green]")
    console.print(f"Avg latency     : [cyan]{s['avg_latency_ms']:.0f} ms[/cyan]")
    ev = s.get("evals", {})
    if ev.get("count"):
        console.print(
            f"Evals           : [cyan]{ev['passed']}/{ev['count']} passed[/cyan] "
            f"[dim](avg score {ev['avg_score']:.2f})[/dim]"
        )

    if s["by_model"]:
        table = Table(title="\nBy model")
        table.add_column("Model", style="cyan")
        table.add_column("Calls", justify="right")
        table.add_column("Tokens", justify="right")
        table.add_column("Cost", style="green", justify="right")
        for row in s["by_model"]:
            table.add_row(row["model"], str(row["calls"]), f"{row['tokens']:,}", f"${row['cost']:.4f}")
        console.print(table)
    r.close()


@app.command()
def recent(limit: int = typer.Option(20, "--limit", "-n")):
    """Show recent model calls."""
    r = _r()
    rows = r.recent(limit=limit)
    if not rows:
        console.print("[yellow]No calls traced yet.[/yellow]")
        r.close()
        return
    table = Table(title="Recent calls")
    table.add_column("ID", style="dim", justify="right")
    table.add_column("Model", style="cyan")
    table.add_column("Kind", style="dim")
    table.add_column("In", justify="right")
    table.add_column("Out", justify="right")
    table.add_column("Cost", style="green", justify="right")
    table.add_column("Latency", justify="right")
    for row in rows:
        table.add_row(
            str(row["id"]), row["model"], row.get("kind", "chat"),
            str(row["input_tokens"]), str(row["output_tokens"]),
            f"${row['cost_usd']:.4f}", f"{row['latency_ms']} ms",
        )
    console.print(table)
    r.close()


@app.command()
def trace(limit: int = typer.Option(10, "--limit", "-n", help="How many recent turns.")):
    """Show recent turns as call trees: the chat call plus the memory
    extraction / reconcile / graph calls it spawned, with per-turn totals."""
    r = _r()
    sessions = r.recent_sessions(limit=limit)
    if not sessions:
        console.print("[yellow]No calls traced yet.[/yellow]")
        r.close()
        return
    from rich.tree import Tree

    for s in sessions:
        p = s["parent"]
        root = Tree(
            f"[cyan]{p['kind']}[/cyan] [bold]{p['model']}[/bold] · "
            f"{p['input_tokens']}+{p['output_tokens']} tok · "
            f"${p['cost_usd']:.4f} · {p['latency_ms']}ms"
        )
        for c in s["children"]:
            root.add(
                f"[magenta]{c['kind']}[/magenta] {c['model']} · "
                f"{c['input_tokens']}+{c['output_tokens']} tok · ${c['cost_usd']:.4f}"
            )
        if s["children"]:
            root.add(f"[dim]turn total: {s['total_tokens']} tok · ${s['total_cost']:.4f}[/dim]")
        console.print(root)
    r.close()


@app.command()
def pricing(model: str = typer.Argument(None, help="Model to look up (omit to list the table).")):
    """Show per-1M-token pricing. Override with ENGRAM_PRICING_FILE (a JSON file)
    or ENGRAM_PRICING (inline JSON) — no code edits needed."""
    from .pricing import _load_pricing, price_of

    if model:
        entry = price_of(model)
        if entry is None:
            console.print(f"[yellow]No price for '{model}' — it traces at $0. "
                          f"Add it via ENGRAM_PRICING_FILE.[/yellow]", markup=False)
        else:
            console.print(f"[cyan]{model}[/cyan]: ${entry['input']}/1M in · ${entry['output']}/1M out", markup=False)
        return
    table = Table(title="Pricing (USD per 1M tokens)")
    table.add_column("Model", style="cyan")
    table.add_column("Input", justify="right")
    table.add_column("Output", justify="right")
    for name, p in sorted(_load_pricing().items()):
        table.add_row(name, f"${p['input']}", f"${p['output']}")
    console.print(table)


@app.command("eval")
def eval_cmd(
    trace_id: int = typer.Argument(..., help="Trace ID to evaluate (see `engram recent`)."),
    contains: str = typer.Option(None, "--contains", help="Reply must contain this text."),
    not_contains: str = typer.Option(None, "--not-contains", help="Reply must NOT contain this text."),
    regex: str = typer.Option(None, "--regex", help="Reply must match this regex."),
    max_tokens: int = typer.Option(None, "--max-tokens", help="Reply output tokens must be <= N."),
    judge: str = typer.Option(None, "--judge", help="LLM-judge the reply against this criterion."),
    suite: str = typer.Option(None, "--suite", help="Run a saved eval suite (flags override it)."),
):
    """Score a traced reply with local rules and/or an LLM judge; store results."""
    r = _r()
    if not any([contains, not_contains, regex, max_tokens, judge, suite]):
        console.print("[yellow]Pass at least one check or --suite NAME[/yellow]")
        r.close()
        raise typer.Exit(1)
    try:
        if suite:
            results = r.run_suite(
                trace_id, suite, contains=contains, not_contains=not_contains,
                regex=regex, max_tokens=max_tokens, judge=judge,
            )
        else:
            results = r.evaluate(
                trace_id, contains=contains, not_contains=not_contains, regex=regex,
                max_tokens=max_tokens, judge=judge,
            )
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        r.close()
        raise typer.Exit(1)
    if not results:
        console.print("[yellow]No eval ran (judge needs a configured provider/model).[/yellow]")
    for res in results:
        mark = "✓" if res["passed"] else "✗"
        color = "green" if res["passed"] else "red"
        console.print(f"[{color}]{mark}[/{color}] {res['name']} ({res['score']:.2f})")
        console.print(f"   {res['detail']}", markup=False)
    r.close()


@app.command()
def evals(trace_id: int = typer.Option(None, "--trace", help="Filter to one trace ID.")):
    """List recent eval results."""
    r = _r()
    rows = r.evals_for(trace_id) if trace_id else r.store.recent_evals()
    if not rows:
        console.print("[yellow]No evals yet. Run: engram eval <trace_id> --judge \"...\"[/yellow]")
        r.close()
        return
    table = Table(title="Evals")
    table.add_column("Trace", style="dim", justify="right")
    table.add_column("Kind", style="dim")
    table.add_column("Name", style="cyan")
    table.add_column("Score", justify="right")
    table.add_column("Pass", justify="center")
    table.add_column("Detail")
    for row in rows:
        table.add_row(
            str(row["trace_id"]), row["kind"], row["name"], f"{row['score']:.2f}",
            "✓" if row["passed"] else "✗", row["detail"],
        )
    console.print(table)
    r.close()


@suite_app.command("save")
def suite_save(
    name: str = typer.Argument(..., help="Suite name."),
    contains: str = typer.Option(None, "--contains"),
    not_contains: str = typer.Option(None, "--not-contains"),
    regex: str = typer.Option(None, "--regex"),
    max_tokens: int = typer.Option(None, "--max-tokens"),
    judge: str = typer.Option(None, "--judge"),
):
    """Save a reusable eval suite (a bundle of checks)."""
    spec = {k: v for k, v in {
        "contains": contains, "not_contains": not_contains, "regex": regex,
        "max_tokens": max_tokens, "judge": judge,
    }.items() if v is not None}
    if not spec:
        console.print("[yellow]Add at least one check.[/yellow]")
        raise typer.Exit(1)
    r = _r()
    r.store.save_suite(name, spec)
    console.print(f"[green]✓[/green] Saved eval suite '{name}'")
    r.close()


@suite_app.command("list")
def suite_list():
    """List saved eval suites."""
    r = _r()
    suites = r.store.list_suites()
    if not suites:
        console.print("[yellow]No eval suites. Save one: engram eval-suite save <name> --judge \"...\"[/yellow]")
        r.close()
        return
    table = Table(title="Eval suites")
    table.add_column("Name", style="cyan")
    table.add_column("Checks")
    for name, spec in suites:
        table.add_row(name, ", ".join(f"{k}={v}" for k, v in spec.items()))
    console.print(table)
    r.close()


@suite_app.command("rm")
def suite_rm(name: str = typer.Argument(..., help="Suite name.")):
    """Delete an eval suite."""
    r = _r()
    ok = r.store.delete_suite(name)
    console.print(f"[green]✓[/green] Deleted '{name}'" if ok else f"[red]No suite '{name}'[/red]")
    r.close()


@app.command()
def benchmark(k: int = typer.Option(5, "--k", help="Retrieval cutoff for recall@k / precision@k.")):
    """Run the reproducible memory-quality benchmark (retrieval + extraction).

    Deterministic and key-free; reports semantic vs keyword mode honestly.
    """
    from .bench import run_all
    res = run_all(k=k)
    rt, ex = res["retrieval"], res["extraction"]
    console.print(f"[bold]engram benchmark[/bold]  [dim](v{__version__})[/dim]\n")
    console.print(f"Retrieval backend : [cyan]{rt['mode']}[/cyan]  "
                  f"[dim]({rt['queries']} queries, k={rt['k']})[/dim]")
    table = Table(title="Retrieval quality")
    table.add_column("Metric", style="cyan")
    table.add_column("Score", justify="right")
    table.add_row("recall@1", f"{rt['recall_at_1']:.3f}")
    table.add_row(f"recall@{k}", f"{rt['recall_at_k']:.3f}")
    table.add_row(f"precision@{k}", f"{rt['precision_at_k']:.3f}")
    table.add_row("MRR", f"{rt['mrr']:.3f}")
    console.print(table)
    console.print(f"Extraction        : [cyan]fact-engram {ex['fact_recall']:.3f}[/cyan] "
                  f"[dim]({ex['cases']} cases, {ex['false_captures']} false capture(s))[/dim]")
    console.print(
        f"\n[dim]cite: recall@1={rt['recall_at_1']:.2f}, MRR={rt['mrr']:.2f} "
        f"({rt['mode']}, {rt['queries']} queries)[/dim]"
    )
    if rt["mode"] == "keyword":
        console.print("[dim]tip: install 'engram-ai[embeddings]' (or set an api backend) "
                      "for the semantic numbers.[/dim]", markup=False)


@app.command()
def models():
    """List supported providers."""
    table = Table(title=f"Supported providers ({len(REGISTRY)})")
    table.add_column("Provider", style="cyan")
    table.add_column("API key env var", style="green")
    table.add_column("Default base URL", style="dim")
    for name in sorted(REGISTRY):
        table.add_row(name, KEY_ENV.get(name, "ENGRAM_API_KEY"), BASE_URLS.get(name, "(provider default)"))
    console.print(table)
    console.print(
        "\n[dim]Set the matching env var, or ENGRAM_API_KEY as a fallback. "
        "ollama / lmstudio run locally and usually need no key.[/dim]"
    )


# ---- export / import ----------------------------------------------------
@app.command("export")
def export_cmd(
    path: str = typer.Argument(..., help="Output JSON file."),
    all_scopes: bool = typer.Option(True, "--all/--scope-only", help="Export all scopes."),
):
    """Export memories to a JSON file."""
    r = _r()
    n = r.export_memories(Path(path), scope=None if all_scopes else r.scope)
    console.print(f"[green]✓[/green] Exported {n} memories → {path}")
    r.close()


@app.command("import")
def import_cmd(path: str = typer.Argument(..., help="Input JSON file.")):
    """Import memories from a JSON file (duplicates skipped)."""
    r = _r()
    n = r.import_memories(Path(path))
    console.print(f"[green]✓[/green] Imported {n} new memories from {path}")
    r.close()


# ---- config -------------------------------------------------------------
@config_app.command("show")
def config_show():
    """Show current configuration."""
    cfg = Config.load()
    table = Table(title=f"Config ({config_path()})")
    table.add_column("Key", style="cyan")
    table.add_column("Value")
    for k in ("default_provider", "default_model", "daily_budget_usd",
              "budget_enforce", "auto_memory", "extraction_mode", "extraction_model",
              "memory_ops", "graph_extract", "memory_inject_limit",
              "embedding_backend", "embedding_model", "embedding_base_url",
              "dedupe_similarity", "recency_weight", "graph_weight", "stream",
              "otel_export", "auto_eval_suite", "active_scope"):
        table.add_row(k, str(getattr(cfg, k)))
    console.print(table)


@config_app.command("set")
def config_set(key: str = typer.Argument(...), value: str = typer.Argument(...)):
    """Set a config value, e.g. `engram config set daily_budget_usd 1.0`."""
    cfg = Config.load()
    cfg.set(key, value)
    cfg.save()
    console.print(f"[green]✓[/green] {key} = {cfg.get(key)}")


@config_app.command("path")
def config_path_cmd():
    """Print the config file path."""
    console.print(str(config_path()))


# ---- prompt templates ---------------------------------------------------
@prompt_app.command("save")
def prompt_save(
    name: str = typer.Argument(..., help="Template name."),
    content: str = typer.Argument(..., help="Template text; use {var} placeholders."),
):
    """Save (or replace) a prompt template / fragment."""
    r = _r()
    r.save_prompt(name, content)
    console.print(f"[green]✓[/green] Saved template '{name}'")
    r.close()


@prompt_app.command("list")
def prompt_list():
    """List saved templates."""
    r = _r()
    rows = r.store.list_prompts()
    if not rows:
        console.print("[yellow]No templates. Save one: engram prompt save <name> \"...\"[/yellow]")
        r.close()
        return
    table = Table(title="Prompt templates")
    table.add_column("Name", style="cyan")
    table.add_column("Content")
    for row in rows:
        preview = row["content"] if len(row["content"]) <= 70 else row["content"][:67] + "..."
        table.add_row(row["name"], preview)
    console.print(table)
    r.close()


@prompt_app.command("show")
def prompt_show(name: str = typer.Argument(..., help="Template name.")):
    """Print a template's raw content."""
    r = _r()
    content = r.store.get_prompt(name)
    console.print(content, markup=False) if content is not None else console.print(f"[red]No template '{name}'[/red]")
    r.close()


@prompt_app.command("rm")
def prompt_rm(name: str = typer.Argument(..., help="Template name.")):
    """Delete a template."""
    r = _r()
    ok = r.store.delete_prompt(name)
    console.print(f"[green]✓[/green] Deleted '{name}'" if ok else f"[red]No template '{name}'[/red]")
    r.close()


@prompt_app.command("use")
def prompt_use(
    name: str = typer.Argument(..., help="Template name."),
    var: list[str] = typer.Option(None, "--var", "-V", help="Variable k=v (repeatable)."),
):
    """Render a template with variables and print it."""
    from .prompts import parse_vars
    r = _r()
    rendered = r.render_prompt(name, parse_vars(var))
    if rendered is None:
        console.print(f"[red]No template '{name}'[/red]")
        r.close()
        raise typer.Exit(1)
    console.print(rendered, markup=False)
    r.close()


# ---- dashboard / version ------------------------------------------------
@app.command()
def dashboard(port: int = typer.Option(8745, "--port", "-p")):
    """Launch the local web dashboard (requires: pip install 'engram-ai[dashboard]')."""
    try:
        from .dashboard.server import serve
    except ImportError as e:
        console.print(f"[red]Dashboard deps missing:[/red] {e}", markup=False)
        console.print("Install with: pip install 'engram-ai[dashboard]'", markup=False)
        raise typer.Exit(1)
    serve(port=port)


@app.command()
def mcp():
    """Run engram as an MCP server (stdio) so any agent can read/write memory.

    Wire it into an MCP client with:
      {"mcpServers": {"engram": {"command": "engram", "args": ["mcp"]}}}

    Requires: pip install 'engram-ai[mcp]'
    """
    try:
        from .mcp_server import serve
        serve()
    except (ImportError, RuntimeError) as e:
        console.print(f"[red]MCP unavailable:[/red] {e}", markup=False)
        console.print("Install with: pip install 'engram-ai[mcp]'", markup=False)
        raise typer.Exit(1)


@app.command()
def version():
    """Print version."""
    console.print(f"engram {__version__}")


if __name__ == "__main__":
    app()
