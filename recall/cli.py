"""recall CLI.

  recall init                                 # guided first-time setup
  recall add "I prefer concise answers"       # store a memory
  recall search "preferences"                 # semantic/keyword search
  recall list                                 # list memories (active scope)
  recall forget 3                             # delete a memory
  recall chat openai gpt-4o-mini "..."        # chat with memory + tracing
  recall stats                                # tokens + cost + budget
  recall recent                               # recent model calls
  recall models                               # supported providers
  recall scope work                           # switch active memory scope
  recall config set daily_budget_usd 1.0      # configure defaults
  recall export mem.json / recall import ...   # backup & restore
  recall doctor                               # check which API keys are set
  recall dashboard                            # local web UI
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
console = Console()


def _r() -> Recall:
    return Recall()


# ---- setup --------------------------------------------------------------
@app.command()
def init():
    """Guided first-time setup: pick a default model and detect API keys."""
    cfg = Config.load()
    console.print("[bold]🧠 recall setup[/bold]\n")

    available = [p for p in sorted(REGISTRY) if os.environ.get(KEY_ENV.get(p, ""))]
    if available:
        console.print(f"Detected API keys for: [green]{', '.join(available)}[/green]")
    else:
        console.print("[yellow]No provider API keys detected in env.[/yellow] "
                      "Set e.g. OPENAI_API_KEY, then re-run, or use local ollama.")

    default = available[0] if available else "openai"
    provider = typer.prompt("Default provider", default=cfg.default_provider or default)
    model = typer.prompt("Default model", default=cfg.default_model or "gpt-4o-mini")
    budget = typer.prompt("Daily budget USD (0 = none)", default=str(cfg.daily_budget_usd))

    cfg.default_provider = provider
    cfg.default_model = model
    cfg.daily_budget_usd = float(budget)
    cfg.save()
    console.print(f"\n[green]✓[/green] Saved to {config_path()}")
    console.print("Try: [cyan]recall add \"I prefer concise answers\"[/cyan] then "
                  "[cyan]recall chat \"hi\"[/cyan]")


@app.command()
def doctor():
    """Check which providers have API keys configured."""
    table = Table(title="Provider readiness")
    table.add_column("Provider", style="cyan")
    table.add_column("Key env", style="dim")
    table.add_column("Status")
    for name in sorted(REGISTRY):
        env = KEY_ENV.get(name, "RECALL_API_KEY")
        if name in ("ollama", "lmstudio"):
            status = "[blue]local (no key)[/blue]"
        elif os.environ.get(env) or os.environ.get("RECALL_API_KEY"):
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
):
    """List stored memories (active scope by default)."""
    r = _r()
    mems = r.store.all_memories(scope=None if all_scopes else r.scope)
    if not mems:
        console.print(f"[yellow]No memories in '{r.scope}'. Add one: recall add \"...\"[/yellow]")
        r.close()
        return
    table = Table(title=f"Memories ({len(mems)})" + ("" if all_scopes else f" · scope='{r.scope}'"))
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("Memory")
    table.add_column("Scope", style="blue")
    table.add_column("Src", style="dim")
    table.add_column("Tags", style="dim")
    for m in mems:
        src = "🤖" if m.source == "auto" else ""
        table.add_row(str(m.id), m.content, m.scope, src, ", ".join(m.tags))
    console.print(table)
    r.close()


@app.command()
def forget(memory_id: int = typer.Argument(..., help="Memory ID to delete.")):
    """Delete a memory by ID."""
    r = _r()
    ok = r.store.delete_memory(memory_id)
    console.print(f"[green]✓[/green] Forgot #{memory_id}" if ok else f"[red]✗[/red] No memory #{memory_id}")
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
            "Install: pip install 'recall-ai[embeddings]'", markup=False,
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
@app.command()
def chat(
    arg1: str = typer.Argument(..., help="Provider, OR the prompt if defaults are set."),
    arg2: str = typer.Argument(None, help="Model (when provider given)."),
    arg3: str = typer.Argument(None, help="Prompt (when provider+model given)."),
    system: str = typer.Option(None, "--system", "-s"),
    no_memory: bool = typer.Option(False, "--no-memory", help="Skip memory injection."),
    no_auto: bool = typer.Option(False, "--no-auto", help="Skip auto-memory capture."),
    stream: bool = typer.Option(None, "--stream/--no-stream", help="Stream output token-by-token (default from config)."),
):
    """Chat with any model — memory injected, cost & tokens traced automatically.

    Forms:
      recall chat <provider> <model> "prompt"
      recall chat "prompt"                  (uses configured defaults)
    """
    r = _r()
    # Flexible argument parsing.
    if arg2 is None and arg3 is None:
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

    try:
        if use_stream:
            # Write chunks straight to stdout (markup-free) for live typing.
            out = r.stream(
                provider, model, prompt,
                on_token=lambda t: (typer.echo(t, nl=False)),
                system=system, use_memory=not no_memory,
                auto_memory=not no_auto,
            )
            typer.echo("")  # newline after the streamed reply
        else:
            out = r.chat(
                provider, model, prompt,
                system=system, use_memory=not no_memory,
                auto_memory=not no_auto,
            )
            console.print(out.text, markup=False)
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]Error:[/red] {e}")
        r.close()
        raise typer.Exit(1)

    meta = f"[dim]— {out.model} · {out.input_tokens}+{out.output_tokens} tok · ${out.cost_usd:.4f} · {out.latency_ms}ms[/dim]"
    console.print(meta)
    if out.auto_remembered:
        console.print(f"[dim]🤖 remembered: {'; '.join(out.auto_remembered)}[/dim]")
    if out.budget_warning:
        console.print(f"[bold yellow]⚠ {out.budget_warning}[/bold yellow]")
    r.close()


# ---- observability ------------------------------------------------------
@app.command()
def stats():
    """Show token usage, cost, and budget."""
    r = _r()
    s = r.stats()
    console.print(f"[bold]recall stats[/bold]  [dim](v{__version__})[/dim]\n")
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
    table.add_column("Model", style="cyan")
    table.add_column("In", justify="right")
    table.add_column("Out", justify="right")
    table.add_column("Cost", style="green", justify="right")
    table.add_column("Latency", justify="right")
    for row in rows:
        table.add_row(
            row["model"], str(row["input_tokens"]), str(row["output_tokens"]),
            f"${row['cost_usd']:.4f}", f"{row['latency_ms']} ms",
        )
    console.print(table)
    r.close()


@app.command()
def models():
    """List supported providers."""
    table = Table(title=f"Supported providers ({len(REGISTRY)})")
    table.add_column("Provider", style="cyan")
    table.add_column("API key env var", style="green")
    table.add_column("Default base URL", style="dim")
    for name in sorted(REGISTRY):
        table.add_row(name, KEY_ENV.get(name, "RECALL_API_KEY"), BASE_URLS.get(name, "(provider default)"))
    console.print(table)
    console.print(
        "\n[dim]Set the matching env var, or RECALL_API_KEY as a fallback. "
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
              "auto_memory", "extraction_mode", "extraction_model",
              "memory_inject_limit", "dedupe_similarity", "stream", "active_scope"):
        table.add_row(k, str(getattr(cfg, k)))
    console.print(table)


@config_app.command("set")
def config_set(key: str = typer.Argument(...), value: str = typer.Argument(...)):
    """Set a config value, e.g. `recall config set daily_budget_usd 1.0`."""
    cfg = Config.load()
    cfg.set(key, value)
    cfg.save()
    console.print(f"[green]✓[/green] {key} = {cfg.get(key)}")


@config_app.command("path")
def config_path_cmd():
    """Print the config file path."""
    console.print(str(config_path()))


# ---- dashboard / version ------------------------------------------------
@app.command()
def dashboard(port: int = typer.Option(8745, "--port", "-p")):
    """Launch the local web dashboard (requires: pip install 'recall-ai[dashboard]')."""
    try:
        from .dashboard.server import serve
    except ImportError as e:
        console.print(f"[red]Dashboard deps missing:[/red] {e}", markup=False)
        console.print("Install with: pip install 'recall-ai[dashboard]'", markup=False)
        raise typer.Exit(1)
    serve(port=port)


@app.command()
def mcp():
    """Run recall as an MCP server (stdio) so any agent can read/write memory.

    Wire it into an MCP client with:
      {"mcpServers": {"recall": {"command": "recall", "args": ["mcp"]}}}

    Requires: pip install 'recall-ai[mcp]'
    """
    try:
        from .mcp_server import serve
        serve()
    except (ImportError, RuntimeError) as e:
        console.print(f"[red]MCP unavailable:[/red] {e}", markup=False)
        console.print("Install with: pip install 'recall-ai[mcp]'", markup=False)
        raise typer.Exit(1)


@app.command()
def version():
    """Print version."""
    console.print(f"recall {__version__}")


if __name__ == "__main__":
    app()
