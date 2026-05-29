"""recall CLI.

  recall add "I prefer concise answers"      # store a memory
  recall search "preferences"                 # semantic/keyword search
  recall list                                 # list all memories
  recall forget 3                             # delete a memory
  recall chat openai gpt-4o-mini "..."        # chat with memory + tracing
  recall stats                                # tokens + cost overview
  recall recent                               # recent model calls
  recall models                               # supported providers
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .adapters import BASE_URLS, REGISTRY
from .core import Recall

app = typer.Typer(
    add_completion=False,
    help="Your local AI brain: persistent memory + full observability for any model.",
)
console = Console()


def _r() -> Recall:
    return Recall()


@app.command()
def add(
    content: str = typer.Argument(..., help="The memory to store."),
    tags: str = typer.Option("", "--tags", "-t", help="Comma-separated tags."),
):
    """Store a persistent memory."""
    r = _r()
    tag_list = [t for t in tags.split(",") if t.strip()]
    mid = r.remember(content, tags=tag_list)
    mode = "semantic" if r.memory.has_embeddings else "keyword"
    console.print(f"[green]✓[/green] Remembered #{mid} [dim]({mode} index)[/dim]")
    r.close()


@app.command()
def search(
    query: str = typer.Argument(..., help="What to look for."),
    limit: int = typer.Option(5, "--limit", "-n"),
):
    """Search your memories."""
    r = _r()
    hits = r.recall_memories(query, limit=limit)
    if not hits:
        console.print("[yellow]No matching memories.[/yellow]")
        r.close()
        return
    table = Table(title=f'Memories matching "{query}"')
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("Score", style="magenta", justify="right")
    table.add_column("Memory")
    table.add_column("Tags", style="dim")
    for m in hits:
        table.add_row(str(m.id), f"{m.score:.2f}", m.content, ", ".join(m.tags))
    console.print(table)
    r.close()


@app.command("list")
def list_memories():
    """List all stored memories."""
    r = _r()
    mems = r.store.all_memories()
    if not mems:
        console.print("[yellow]No memories yet. Add one with: recall add \"...\"[/yellow]")
        r.close()
        return
    table = Table(title=f"All memories ({len(mems)})")
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("Memory")
    table.add_column("Tags", style="dim")
    for m in mems:
        table.add_row(str(m.id), m.content, ", ".join(m.tags))
    console.print(table)
    r.close()


@app.command()
def forget(memory_id: int = typer.Argument(..., help="Memory ID to delete.")):
    """Delete a memory by ID."""
    r = _r()
    ok = r.store.delete_memory(memory_id)
    if ok:
        console.print(f"[green]✓[/green] Forgot #{memory_id}")
    else:
        console.print(f"[red]✗[/red] No memory #{memory_id}")
    r.close()


@app.command()
def chat(
    provider: str = typer.Argument(..., help=f"One of: {', '.join(sorted(REGISTRY))}"),
    model: str = typer.Argument(..., help="Model name, e.g. gpt-4o-mini"),
    prompt: str = typer.Argument(..., help="Your message."),
    system: str = typer.Option(None, "--system", "-s"),
    no_memory: bool = typer.Option(False, "--no-memory", help="Skip memory injection."),
):
    """Chat with any model — memory injected, cost & tokens traced automatically."""
    r = _r()
    try:
        result = r.chat(provider, model, prompt, system=system, use_memory=not no_memory)
    except Exception as e:  # noqa: BLE001 - surface adapter errors cleanly
        console.print(f"[red]Error:[/red] {e}")
        r.close()
        raise typer.Exit(1)
    console.print(result.text)
    console.print(
        f"\n[dim]— {result.model} · {result.input_tokens}+{result.output_tokens} tok[/dim]"
    )
    r.close()


@app.command()
def stats():
    """Show token usage and cost across all calls."""
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
    console.print(f"Avg latency     : [cyan]{s['avg_latency_ms']:.0f} ms[/cyan]")
    if s["by_model"]:
        table = Table(title="\nBy model")
        table.add_column("Model", style="cyan")
        table.add_column("Calls", justify="right")
        table.add_column("Tokens", justify="right")
        table.add_column("Cost", style="green", justify="right")
        for row in s["by_model"]:
            table.add_row(
                row["model"], str(row["calls"]), f"{row['tokens']:,}", f"${row['cost']:.4f}"
            )
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
            row["model"],
            str(row["input_tokens"]),
            str(row["output_tokens"]),
            f"${row['cost_usd']:.4f}",
            f"{row['latency_ms']} ms",
        )
    console.print(table)
    r.close()


@app.command()
def models():
    """List supported providers."""
    table = Table(title="Supported providers")
    table.add_column("Provider", style="cyan")
    table.add_column("Default base URL", style="dim")
    for name in sorted(REGISTRY):
        table.add_row(name, BASE_URLS.get(name, "(provider default)"))
    console.print(table)
    console.print(
        "\n[dim]Set the matching API key env var "
        "(OPENAI_API_KEY / ANTHROPIC_API_KEY / RECALL_API_KEY).[/dim]"
    )


@app.command()
def dashboard(port: int = typer.Option(8745, "--port", "-p")):
    """Launch the local web dashboard (requires: pip install 'recall-ai[dashboard]')."""
    try:
        from .dashboard.server import serve
    except ImportError as e:
        console.print(f"[red]Dashboard deps missing:[/red] {e}")
        console.print("Install with: pip install 'recall-ai[dashboard]'")
        raise typer.Exit(1)
    serve(port=port)


@app.command()
def version():
    """Print version."""
    console.print(f"recall {__version__}")


if __name__ == "__main__":
    app()
