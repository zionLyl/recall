"""MCP server: expose memstash's memory to any MCP-aware agent.

This turns your local memstash brain into a set of MCP tools, so editors and
agents (Claude Desktop, Claude Code, Cursor, etc.) can read and write the *same*
memory store you use from the CLI — without anything leaving your machine.

Run it:

    memstash mcp                      # stdio transport (the usual MCP wiring)

Then point your MCP client at that command. Example client config entry:

    {
      "mcpServers": {
        "memstash": { "command": "memstash", "args": ["mcp"] }
      }
    }

Requires the MCP SDK:  pip install 'memstash[mcp]'

Tools exposed:
  - remember(content, tags?, scope?)        store a memory
  - recall_search(query, limit?, scope?)    semantic/keyword search
  - list_memories(scope?, all_scopes?)      list stored memories
  - forget(memory_id)                       delete a memory
  - usage_stats()                           tokens / cost / budget snapshot
"""

from __future__ import annotations

from typing import Optional

from .core import Recall


def build_server(recall: Optional[Recall] = None):
    """Construct the FastMCP server with memstash's tools registered."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as e:  # pragma: no cover - depends on optional extra
        raise RuntimeError(
            "MCP SDK not installed. Run: pip install 'memstash[mcp]'"
        ) from e

    r = recall or Recall()
    mcp = FastMCP("memstash")

    @mcp.tool()
    def remember(content: str, tags: Optional[list[str]] = None,
                 scope: Optional[str] = None) -> str:
        """Store a durable memory (fact/preference) in the local memstash store.

        Use this whenever the user states a stable preference or fact worth
        remembering across sessions.
        """
        mid = r.remember(content, tags=tags, scope=scope, source="mcp")
        if mid is None:
            return "Already remembered (duplicate skipped)."
        return f"Remembered #{mid} in scope '{scope or r.scope}'."

    @mcp.tool()
    def recall_search(query: str, limit: int = 5,
                      scope: Optional[str] = None, all_scopes: bool = False) -> list[dict]:
        """Search stored memories. Call this before answering to recall what you
        already know about the user."""
        hits = r.recall_memories(query, limit=limit, scope=None if all_scopes else (scope or r.scope))
        return [
            {"id": m.id, "content": m.content, "tags": m.tags,
             "scope": m.scope, "score": round(m.score, 3)}
            for m in hits
        ]

    @mcp.tool()
    def list_memories(scope: Optional[str] = None, all_scopes: bool = False) -> list[dict]:
        """List stored memories (active scope by default, or all scopes)."""
        mems = r.store.all_memories(scope=None if all_scopes else (scope or r.scope))
        return [
            {"id": m.id, "content": m.content, "tags": m.tags,
             "scope": m.scope, "source": m.source}
            for m in mems
        ]

    @mcp.tool()
    def forget(memory_id: int) -> str:
        """Delete a memory by its ID."""
        ok = r.store.delete_memory(memory_id)
        return f"Forgot #{memory_id}." if ok else f"No memory #{memory_id}."

    @mcp.tool()
    def usage_stats() -> dict:
        """Return token usage, cost, today's spend, and configured budget."""
        s = r.stats()
        return {
            "memories": s["memory_count"],
            "calls": s["calls"],
            "input_tokens": s["input_tokens"],
            "output_tokens": s["output_tokens"],
            "total_cost_usd": round(s["cost_usd"], 6),
            "cost_today_usd": round(s.get("cost_today", 0) or 0, 6),
            "daily_budget_usd": s.get("daily_budget", 0) or 0,
        }

    return mcp


def serve() -> None:
    """Run the MCP server over stdio (the standard MCP transport)."""
    build_server().run()
