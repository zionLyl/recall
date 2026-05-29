"""Local-first storage layer for recall.

Everything lives in a single SQLite file under ~/.recall/recall.db by default.
Two core tables:
  - memories: persistent facts/preferences, optionally with an embedding for
    semantic search.
  - traces: one row per model call (model, tokens, cost, latency) for
    observability.

No data ever leaves the machine.
"""

from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


def default_db_path() -> Path:
    """Resolve the DB path. Override with the RECALL_HOME env var."""
    home = os.environ.get("RECALL_HOME")
    base = Path(home) if home else Path.home() / ".recall"
    base.mkdir(parents=True, exist_ok=True)
    return base / "recall.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    content    TEXT NOT NULL,
    tags       TEXT NOT NULL DEFAULT '',
    scope      TEXT NOT NULL DEFAULT 'default',
    source     TEXT NOT NULL DEFAULT 'manual',
    embedding  BLOB,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS traces (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    model       TEXT NOT NULL,
    provider    TEXT NOT NULL DEFAULT '',
    prompt      TEXT NOT NULL DEFAULT '',
    completion  TEXT NOT NULL DEFAULT '',
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd    REAL NOT NULL DEFAULT 0.0,
    latency_ms  INTEGER NOT NULL DEFAULT 0,
    created_at  REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_traces_created ON traces(created_at);
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at);
CREATE INDEX IF NOT EXISTS idx_memories_scope ON memories(scope);
"""

# Lightweight migrations for older DBs created before a column existed.
MIGRATIONS = [
    "ALTER TABLE memories ADD COLUMN scope TEXT NOT NULL DEFAULT 'default'",
    "ALTER TABLE memories ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'",
    "ALTER TABLE traces ADD COLUMN scope TEXT NOT NULL DEFAULT 'default'",
]


@dataclass
class Memory:
    id: int
    content: str
    tags: list[str]
    created_at: float
    scope: str = "default"
    source: str = "manual"
    score: float = 0.0  # populated during search


@dataclass
class Trace:
    model: str
    provider: str = ""
    prompt: str = ""
    completion: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0


class Store:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else default_db_path()
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        for stmt in MIGRATIONS:
            try:
                self.conn.execute(stmt)
            except sqlite3.OperationalError:
                pass  # column already exists

    # ---- memories -------------------------------------------------------
    def add_memory(
        self,
        content: str,
        tags: Optional[Iterable[str]] = None,
        embedding: Optional[bytes] = None,
        scope: str = "default",
        source: str = "manual",
    ) -> int:
        now = time.time()
        tag_str = ",".join(sorted(set(t.strip() for t in (tags or []) if t.strip())))
        cur = self.conn.execute(
            "INSERT INTO memories (content, tags, scope, source, embedding, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (content, tag_str, scope, source, embedding, now, now),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def _row_to_memory(self, r, score: float = 0.0) -> Memory:
        return Memory(
            id=r["id"],
            content=r["content"],
            tags=[t for t in r["tags"].split(",") if t],
            created_at=r["created_at"],
            scope=r["scope"],
            source=r["source"],
            score=score,
        )

    def all_memories(self, scope: Optional[str] = None) -> list[Memory]:
        if scope:
            rows = self.conn.execute(
                "SELECT * FROM memories WHERE scope = ? ORDER BY created_at DESC", (scope,)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM memories ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_memory(r) for r in rows]

    def all_memories_with_embeddings(
        self, scope: Optional[str] = None
    ) -> list[tuple[int, str, list[str], Optional[bytes], float, str, str]]:
        if scope:
            rows = self.conn.execute(
                "SELECT * FROM memories WHERE scope = ?", (scope,)
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM memories").fetchall()
        return [
            (
                r["id"], r["content"], [t for t in r["tags"].split(",") if t],
                r["embedding"], r["created_at"], r["scope"], r["source"],
            )
            for r in rows
        ]

    def delete_memory(self, memory_id: int) -> bool:
        cur = self.conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def get_memory(self, memory_id: int) -> Optional[Memory]:
        row = self.conn.execute(
            "SELECT * FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        return self._row_to_memory(row) if row else None

    def update_memory(
        self,
        memory_id: int,
        content: Optional[str] = None,
        tags: Optional[Iterable[str]] = None,
        embedding: Optional[bytes] = None,
        embedding_set: bool = False,
    ) -> bool:
        """Update a memory's content and/or tags in place.

        Only the provided fields change. ``embedding_set=True`` writes the given
        embedding (used when content changed and was re-encoded).
        """
        sets, params = [], []
        if content is not None:
            sets.append("content = ?")
            params.append(content)
        if tags is not None:
            tag_str = ",".join(sorted(set(t.strip() for t in tags if t.strip())))
            sets.append("tags = ?")
            params.append(tag_str)
        if embedding_set:
            sets.append("embedding = ?")
            params.append(embedding)
        if not sets:
            return False
        sets.append("updated_at = ?")
        params.append(time.time())
        params.append(memory_id)
        cur = self.conn.execute(
            f"UPDATE memories SET {', '.join(sets)} WHERE id = ?", params
        )
        self.conn.commit()
        return cur.rowcount > 0

    def memory_exists(self, content: str, scope: str = "default") -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM memories WHERE content = ? AND scope = ? LIMIT 1",
            (content.strip(), scope),
        ).fetchone()
        return row is not None

    def list_scopes(self) -> list[tuple[str, int]]:
        rows = self.conn.execute(
            "SELECT scope, COUNT(*) AS c FROM memories GROUP BY scope ORDER BY c DESC"
        ).fetchall()
        return [(r["scope"], r["c"]) for r in rows]

    def keyword_search(self, query: str, limit: int = 5, scope: Optional[str] = None) -> list[Memory]:
        like = f"%{query.strip()}%"
        if scope:
            rows = self.conn.execute(
                "SELECT * FROM memories "
                "WHERE (content LIKE ? OR tags LIKE ?) AND scope = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (like, like, scope, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM memories "
                "WHERE content LIKE ? OR tags LIKE ? ORDER BY created_at DESC LIMIT ?",
                (like, like, limit),
            ).fetchall()
        return [self._row_to_memory(r, score=1.0) for r in rows]

    # ---- traces ---------------------------------------------------------
    def add_trace(self, trace: Trace) -> int:
        cur = self.conn.execute(
            "INSERT INTO traces (model, provider, prompt, completion, input_tokens, "
            "output_tokens, cost_usd, latency_ms, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                trace.model,
                trace.provider,
                trace.prompt[:2000],
                trace.completion[:2000],
                trace.input_tokens,
                trace.output_tokens,
                trace.cost_usd,
                trace.latency_ms,
                time.time(),
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def stats(self) -> dict:
        row = self.conn.execute(
            "SELECT COUNT(*) AS calls, "
            "COALESCE(SUM(input_tokens),0) AS in_tok, "
            "COALESCE(SUM(output_tokens),0) AS out_tok, "
            "COALESCE(SUM(cost_usd),0) AS cost, "
            "COALESCE(AVG(latency_ms),0) AS avg_latency "
            "FROM traces"
        ).fetchone()
        by_model = self.conn.execute(
            "SELECT model, COUNT(*) AS calls, COALESCE(SUM(cost_usd),0) AS cost, "
            "COALESCE(SUM(input_tokens+output_tokens),0) AS tokens "
            "FROM traces GROUP BY model ORDER BY cost DESC"
        ).fetchall()
        return {
            "calls": row["calls"],
            "input_tokens": row["in_tok"],
            "output_tokens": row["out_tok"],
            "cost_usd": row["cost"],
            "avg_latency_ms": row["avg_latency"],
            "by_model": [dict(r) for r in by_model],
            "memory_count": self.conn.execute("SELECT COUNT(*) AS c FROM memories").fetchone()["c"],
        }

    def cost_since(self, since_ts: float) -> float:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(cost_usd),0) AS cost FROM traces WHERE created_at >= ?",
            (since_ts,),
        ).fetchone()
        return row["cost"]

    def export_memories(self, scope: Optional[str] = None) -> list[dict]:
        mems = self.all_memories(scope=scope)
        return [
            {
                "content": m.content,
                "tags": m.tags,
                "scope": m.scope,
                "source": m.source,
                "created_at": m.created_at,
            }
            for m in mems
        ]

    def recent_traces(self, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT model, provider, input_tokens, output_tokens, cost_usd, latency_ms, created_at "
            "FROM traces ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self.conn.close()
