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

import json
import os
import re
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
    updated_at REAL NOT NULL,
    -- lifecycle: usage tracking, soft-forget, temporal validity
    hit_count  INTEGER NOT NULL DEFAULT 0,
    last_used  REAL,
    valid_from REAL,
    valid_to   REAL,
    active     INTEGER NOT NULL DEFAULT 1,
    -- provenance: the chat trace this memory was auto-captured from
    source_trace INTEGER
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
    created_at  REAL NOT NULL,
    -- trace tree: group a turn's calls (chat + extraction/reconcile/graph)
    session_id  TEXT,
    parent_id   INTEGER,
    kind        TEXT NOT NULL DEFAULT 'chat'
);

-- graph-lite: entity relationships as (subject, predicate, object) triples.
-- A flat relations table gives relational queries without a graph database,
-- staying true to the single-SQLite philosophy.
CREATE TABLE IF NOT EXISTS relations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    subject       TEXT NOT NULL,
    predicate     TEXT NOT NULL,
    object        TEXT NOT NULL,
    scope         TEXT NOT NULL DEFAULT 'default',
    source_memory INTEGER,
    created_at    REAL NOT NULL
);

-- reusable prompt templates / fragments with {var} placeholders.
CREATE TABLE IF NOT EXISTS prompts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    content    TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

-- saved eval suites: a named bundle of checks (JSON spec).
CREATE TABLE IF NOT EXISTS eval_suites (
    name       TEXT PRIMARY KEY,
    spec       TEXT NOT NULL,
    created_at REAL NOT NULL
);

-- quality evals attached to a traced call (rule checks or LLM judge).
CREATE TABLE IF NOT EXISTS evals (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id   INTEGER,
    kind       TEXT NOT NULL,
    name       TEXT NOT NULL DEFAULT '',
    score      REAL NOT NULL DEFAULT 0.0,
    passed     INTEGER NOT NULL DEFAULT 0,
    detail     TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_traces_created ON traces(created_at);
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at);
CREATE INDEX IF NOT EXISTS idx_memories_scope ON memories(scope);
CREATE INDEX IF NOT EXISTS idx_relations_scope ON relations(scope);
CREATE INDEX IF NOT EXISTS idx_relations_subject ON relations(subject);
CREATE INDEX IF NOT EXISTS idx_relations_object ON relations(object);
"""

# Lightweight migrations for older DBs created before a column existed.
MIGRATIONS = [
    "ALTER TABLE memories ADD COLUMN scope TEXT NOT NULL DEFAULT 'default'",
    "ALTER TABLE memories ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'",
    "ALTER TABLE traces ADD COLUMN scope TEXT NOT NULL DEFAULT 'default'",
    "ALTER TABLE memories ADD COLUMN hit_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE memories ADD COLUMN last_used REAL",
    "ALTER TABLE memories ADD COLUMN valid_from REAL",
    "ALTER TABLE memories ADD COLUMN valid_to REAL",
    "ALTER TABLE memories ADD COLUMN active INTEGER NOT NULL DEFAULT 1",
    "ALTER TABLE traces ADD COLUMN session_id TEXT",
    "ALTER TABLE traces ADD COLUMN parent_id INTEGER",
    "ALTER TABLE traces ADD COLUMN kind TEXT NOT NULL DEFAULT 'chat'",
    "ALTER TABLE memories ADD COLUMN source_trace INTEGER",
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
    hit_count: int = 0
    last_used: Optional[float] = None
    active: int = 1
    source_trace: Optional[int] = None


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
    session_id: str = ""
    parent_id: Optional[int] = None
    kind: str = "chat"


# Full-text search over memories (BM25). FTS5 ships with most SQLite builds; if
# it's missing we silently fall back to LIKE search. An external-content table +
# triggers keeps the index in sync with the memories table.
FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    content, tags, content='memories', content_rowid='id'
);
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, content, tags) VALUES (new.id, new.content, new.tags);
END;
CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, tags)
        VALUES ('delete', old.id, old.content, old.tags);
END;
CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, tags)
        VALUES ('delete', old.id, old.content, old.tags);
    INSERT INTO memories_fts(rowid, content, tags) VALUES (new.id, new.content, new.tags);
END;
"""


class Store:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else default_db_path()
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        # WAL improves concurrent read/write robustness (e.g. dashboard reading
        # while the CLI writes). Harmless if the filesystem can't honor it.
        try:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.OperationalError:
            pass
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.fts_enabled = self._init_fts()
        self.conn.commit()

    def _migrate(self) -> None:
        for stmt in MIGRATIONS:
            try:
                self.conn.execute(stmt)
            except sqlite3.OperationalError:
                pass  # column already exists

    def _init_fts(self) -> bool:
        """Create the FTS5 index + triggers and sync them. Returns False (and
        keeps using LIKE search) if this SQLite build lacks FTS5."""
        try:
            self.conn.executescript(FTS_SCHEMA)
            # Backfill / repair the index when it's out of sync with memories
            # (e.g. an older DB created before FTS existed).
            fts_n = self.conn.execute("SELECT COUNT(*) AS c FROM memories_fts").fetchone()["c"]
            mem_n = self.conn.execute("SELECT COUNT(*) AS c FROM memories").fetchone()["c"]
            if fts_n != mem_n:
                self.conn.execute("INSERT INTO memories_fts(memories_fts) VALUES ('rebuild')")
            return True
        except sqlite3.OperationalError:
            return False

    # ---- memories -------------------------------------------------------
    def add_memory(
        self,
        content: str,
        tags: Optional[Iterable[str]] = None,
        embedding: Optional[bytes] = None,
        scope: str = "default",
        source: str = "manual",
        source_trace: Optional[int] = None,
    ) -> int:
        now = time.time()
        tag_str = ",".join(sorted(set(t.strip() for t in (tags or []) if t.strip())))
        cur = self.conn.execute(
            "INSERT INTO memories (content, tags, scope, source, embedding, created_at, "
            "updated_at, valid_from, active, source_trace) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)",
            (content, tag_str, scope, source, embedding, now, now, now, source_trace),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def _row_to_memory(self, r, score: float = 0.0) -> Memory:
        keys = r.keys()
        return Memory(
            id=r["id"],
            content=r["content"],
            tags=[t for t in r["tags"].split(",") if t],
            created_at=r["created_at"],
            scope=r["scope"],
            source=r["source"],
            score=score,
            hit_count=r["hit_count"] if "hit_count" in keys else 0,
            last_used=r["last_used"] if "last_used" in keys else None,
            active=r["active"] if "active" in keys else 1,
            source_trace=r["source_trace"] if "source_trace" in keys else None,
        )

    def all_memories(
        self, scope: Optional[str] = None, include_inactive: bool = False
    ) -> list[Memory]:
        where, params = [], []
        if scope:
            where.append("scope = ?")
            params.append(scope)
        if not include_inactive:
            where.append("active = 1")
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        rows = self.conn.execute(
            f"SELECT * FROM memories{clause} ORDER BY created_at DESC", params
        ).fetchall()
        return [self._row_to_memory(r) for r in rows]

    def all_memories_with_embeddings(
        self, scope: Optional[str] = None, include_inactive: bool = False
    ) -> list[tuple[int, str, list[str], Optional[bytes], float, str, str]]:
        where, params = [], []
        if scope:
            where.append("scope = ?")
            params.append(scope)
        if not include_inactive:
            where.append("active = 1")
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        rows = self.conn.execute(f"SELECT * FROM memories{clause}", params).fetchall()
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

    # ---- lifecycle ------------------------------------------------------
    def touch_memories(self, ids: Iterable[int]) -> None:
        """Record a retrieval hit: bump hit_count + last_used for these ids."""
        ids = list(ids)
        if not ids:
            return
        now = time.time()
        qmarks = ",".join("?" * len(ids))
        self.conn.execute(
            f"UPDATE memories SET hit_count = hit_count + 1, last_used = ? "
            f"WHERE id IN ({qmarks})",
            [now, *ids],
        )
        self.conn.commit()

    def soft_delete(self, memory_id: int) -> bool:
        """Soft-forget: mark inactive and stamp valid_to, keeping history."""
        cur = self.conn.execute(
            "UPDATE memories SET active = 0, valid_to = ? WHERE id = ? AND active = 1",
            (time.time(), memory_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def prune(
        self,
        scope: Optional[str] = None,
        older_than_days: Optional[float] = None,
        unused: bool = False,
    ) -> int:
        """Soft-forget stale memories. With ``older_than_days``, forgets memories
        created before that cutoff; with ``unused=True``, restricts to ones never
        retrieved (hit_count = 0). Returns how many were forgotten."""
        where = ["active = 1"]
        params: list = []
        if scope:
            where.append("scope = ?")
            params.append(scope)
        if older_than_days is not None:
            where.append("created_at < ?")
            params.append(time.time() - older_than_days * 86400)
        if unused:
            where.append("hit_count = 0")
        cur = self.conn.execute(
            f"UPDATE memories SET active = 0, valid_to = ? WHERE {' AND '.join(where)}",
            [time.time(), *params],
        )
        self.conn.commit()
        return cur.rowcount

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
            "SELECT 1 FROM memories WHERE content = ? AND scope = ? AND active = 1 LIMIT 1",
            (content.strip(), scope),
        ).fetchone()
        return row is not None

    def list_scopes(self) -> list[tuple[str, int]]:
        rows = self.conn.execute(
            "SELECT scope, COUNT(*) AS c FROM memories GROUP BY scope ORDER BY c DESC"
        ).fetchall()
        return [(r["scope"], r["c"]) for r in rows]

    @staticmethod
    def _fts_match(query: str) -> str:
        """Build a safe FTS5 MATCH expression: OR the query's word tokens, each
        quoted, so user input can't trigger FTS syntax errors."""
        tokens = re.findall(r"\w+", query, re.UNICODE)
        if not tokens:
            return ""
        return " OR ".join(f'"{t}"' for t in tokens)

    def keyword_search(self, query: str, limit: int = 5, scope: Optional[str] = None) -> list[Memory]:
        if self.fts_enabled:
            match = self._fts_match(query)
            if match:
                sql = (
                    "SELECT m.*, bm25(memories_fts) AS rank FROM memories_fts "
                    "JOIN memories m ON m.id = memories_fts.rowid "
                    "WHERE memories_fts MATCH ? AND m.active = 1"
                )
                params: list = [match]
                if scope:
                    sql += " AND m.scope = ?"
                    params.append(scope)
                sql += " ORDER BY rank LIMIT ?"  # bm25: lower rank = better
                params.append(limit)
                try:
                    rows = self.conn.execute(sql, params).fetchall()
                    return [self._row_to_memory(r, score=1.0) for r in rows]
                except sqlite3.OperationalError:
                    pass  # fall through to LIKE on any FTS hiccup

        like = f"%{query.strip()}%"
        if scope:
            rows = self.conn.execute(
                "SELECT * FROM memories "
                "WHERE (content LIKE ? OR tags LIKE ?) AND scope = ? AND active = 1 "
                "ORDER BY created_at DESC LIMIT ?",
                (like, like, scope, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM memories "
                "WHERE (content LIKE ? OR tags LIKE ?) AND active = 1 "
                "ORDER BY created_at DESC LIMIT ?",
                (like, like, limit),
            ).fetchall()
        return [self._row_to_memory(r, score=1.0) for r in rows]

    # ---- traces ---------------------------------------------------------
    def add_trace(self, trace: Trace) -> int:
        cur = self.conn.execute(
            "INSERT INTO traces (model, provider, prompt, completion, input_tokens, "
            "output_tokens, cost_usd, latency_ms, created_at, session_id, parent_id, kind) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                trace.session_id or None,
                trace.parent_id,
                trace.kind,
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
            "memory_count": self.conn.execute(
                "SELECT COUNT(*) AS c FROM memories WHERE active = 1"
            ).fetchone()["c"],
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
            "SELECT id, model, provider, input_tokens, output_tokens, cost_usd, latency_ms, "
            "created_at, kind FROM traces ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_trace(self, trace_id: int) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM traces WHERE id = ?", (trace_id,)).fetchone()
        return dict(row) if row else None

    def recent_sessions(self, limit: int = 10) -> list[dict]:
        """Group recent calls into turn trees: each top-level (chat) call plus
        its child calls (memory extraction / reconcile / graph), with totals."""
        parents = self.conn.execute(
            "SELECT * FROM traces WHERE parent_id IS NULL ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        out: list[dict] = []
        for p in parents:
            kids = self.conn.execute(
                "SELECT * FROM traces WHERE parent_id = ? ORDER BY created_at", (p["id"],)
            ).fetchall()
            children = [dict(k) for k in kids]
            total_cost = p["cost_usd"] + sum(k["cost_usd"] for k in kids)
            total_tokens = (
                p["input_tokens"] + p["output_tokens"]
                + sum(k["input_tokens"] + k["output_tokens"] for k in kids)
            )
            out.append({
                "parent": dict(p),
                "children": children,
                "total_cost": total_cost,
                "total_tokens": total_tokens,
            })
        return out

    # ---- graph-lite (relations) -----------------------------------------
    def relation_exists(self, subject: str, predicate: str, object_: str, scope: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM relations WHERE subject = ? AND predicate = ? AND object = ? "
            "AND scope = ? LIMIT 1",
            (subject, predicate, object_, scope),
        ).fetchone()
        return row is not None

    def add_relation(
        self, subject: str, predicate: str, object_: str,
        scope: str = "default", source_memory: Optional[int] = None,
    ) -> Optional[int]:
        subject, predicate, object_ = subject.strip(), predicate.strip(), object_.strip()
        if not (subject and predicate and object_):
            return None
        if self.relation_exists(subject, predicate, object_, scope):
            return None
        cur = self.conn.execute(
            "INSERT INTO relations (subject, predicate, object, scope, source_memory, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (subject, predicate, object_, scope, source_memory, time.time()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def all_relations(self, scope: Optional[str] = None) -> list[dict]:
        if scope:
            rows = self.conn.execute(
                "SELECT * FROM relations WHERE scope = ? ORDER BY created_at DESC", (scope,)
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM relations ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    def relations_for(self, entity: str, scope: Optional[str] = None) -> list[dict]:
        """All relations where `entity` is the subject or object (case-insensitive)."""
        like = entity.strip().lower()
        params: list = [like, like]
        sql = (
            "SELECT * FROM relations WHERE (LOWER(subject) = ? OR LOWER(object) = ?)"
        )
        if scope:
            sql += " AND scope = ?"
            params.append(scope)
        sql += " ORDER BY created_at DESC"
        return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def entities(self, scope: Optional[str] = None) -> list[tuple[str, int]]:
        """Distinct entity names (subjects + objects) with how many relations
        each touches, most-connected first."""
        scope_clause = " WHERE scope = ?" if scope else ""
        params = (scope,) if scope else ()
        rows = self.conn.execute(
            f"SELECT name, COUNT(*) AS c FROM ("
            f"  SELECT subject AS name FROM relations{scope_clause} "
            f"  UNION ALL SELECT object AS name FROM relations{scope_clause}"
            f") GROUP BY name ORDER BY c DESC",
            params + params,
        ).fetchall()
        return [(r["name"], r["c"]) for r in rows]

    # ---- prompt templates / fragments -----------------------------------
    def save_prompt(self, name: str, content: str) -> None:
        """Create or replace a named prompt template."""
        now = time.time()
        self.conn.execute(
            "INSERT INTO prompts (name, content, created_at, updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET content = excluded.content, updated_at = excluded.updated_at",
            (name.strip(), content, now, now),
        )
        self.conn.commit()

    def get_prompt(self, name: str) -> Optional[str]:
        row = self.conn.execute(
            "SELECT content FROM prompts WHERE name = ?", (name.strip(),)
        ).fetchone()
        return row["content"] if row else None

    def list_prompts(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT name, content, updated_at FROM prompts ORDER BY name"
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_prompt(self, name: str) -> bool:
        cur = self.conn.execute("DELETE FROM prompts WHERE name = ?", (name.strip(),))
        self.conn.commit()
        return cur.rowcount > 0

    # ---- evals ----------------------------------------------------------
    def add_eval(
        self, trace_id: Optional[int], kind: str, name: str,
        score: float, passed: bool, detail: str = "",
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO evals (trace_id, kind, name, score, passed, detail, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (trace_id, kind, name, score, 1 if passed else 0, detail, time.time()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def evals_for(self, trace_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM evals WHERE trace_id = ? ORDER BY created_at", (trace_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def recent_evals(self, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM evals ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def eval_summary(self) -> dict:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(AVG(score),0) AS avg_score, "
            "COALESCE(SUM(passed),0) AS passed FROM evals"
        ).fetchone()
        return {"count": row["n"], "avg_score": row["avg_score"], "passed": row["passed"]}

    # ---- eval suites ----------------------------------------------------
    def save_suite(self, name: str, spec: dict) -> None:
        self.conn.execute(
            "INSERT INTO eval_suites (name, spec, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET spec = excluded.spec",
            (name.strip(), json.dumps(spec), time.time()),
        )
        self.conn.commit()

    def get_suite(self, name: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT spec FROM eval_suites WHERE name = ?", (name.strip(),)
        ).fetchone()
        if not row:
            return None
        try:
            return json.loads(row["spec"])
        except (ValueError, TypeError):
            return None

    def list_suites(self) -> list[tuple[str, dict]]:
        rows = self.conn.execute(
            "SELECT name, spec FROM eval_suites ORDER BY name"
        ).fetchall()
        out = []
        for r in rows:
            try:
                out.append((r["name"], json.loads(r["spec"])))
            except (ValueError, TypeError):
                out.append((r["name"], {}))
        return out

    def delete_suite(self, name: str) -> bool:
        cur = self.conn.execute("DELETE FROM eval_suites WHERE name = ?", (name.strip(),))
        self.conn.commit()
        return cur.rowcount > 0

    def close(self) -> None:
        self.conn.close()
