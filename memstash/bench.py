"""Reproducible benchmark for memstash's memory quality.

Deterministic and API-key-free: seeds a fixed memory set into a throwaway store,
then measures how well retrieval surfaces the *relevant* memories for each query
(recall@k, precision@k, MRR). It honestly reports whether semantic embeddings or
keyword/BM25 was used, so the numbers are comparable and not overstated. A small
extraction check measures how well the heuristic auto-capture catches durable
facts while ignoring questions.

Run:  memstash benchmark

The headline numbers depend on the active embedding backend — install
`memstash[embeddings]` (or configure an api backend) for the semantic
numbers; otherwise you get the keyword/BM25 baseline.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

# A fixed, hand-labeled memory set (content, tags). Ids are assigned on insert.
MEMORIES: list[tuple[str, list[str]]] = [
    ("I prefer concise answers with tables", ["style"]),
    ("I work on A-share and Hong Kong quant research", ["work"]),
    ("My timezone is UTC+8 (Beijing)", ["profile"]),
    ("I write Python with pandas and numpy every day", ["tools"]),
    ("I'm allergic to peanuts", ["health"]),
    ("我喜欢喝乌龙茶", ["drink"]),
    ("The alpha research report is due this Friday", ["work"]),
    ("I drive a blue Tesla Model 3", ["personal"]),
    ("My cat's name is Mochi", ["personal"]),
    ("I prefer dark mode in all my editors", ["style"]),
    ("I studied statistics at Tsinghua University", ["background"]),
    ("Keep meetings under 30 minutes, I dislike long ones", ["work"]),
    ("My favorite language for systems work is Rust", ["tools"]),
    ("I live in Shanghai", ["personal"]),
]

# (query, [relevant memory contents]). Some queries share words with their
# target (keyword can find them); others are paraphrases (only semantic finds).
QUERIES: list[tuple[str, list[str]]] = [
    ("how should you format answers for me?", ["I prefer concise answers with tables"]),
    ("what kind of research do I do?", ["I work on A-share and Hong Kong quant research"]),
    ("what timezone am I in?", ["My timezone is UTC+8 (Beijing)"]),
    ("which Python libraries do I use?", ["I write Python with pandas and numpy every day"]),
    ("do I have any food allergies?", ["I'm allergic to peanuts"]),  # paraphrase (allergic≠allergies)
    ("what report has an upcoming deadline?", ["The alpha research report is due this Friday"]),
    ("what car do I own?", ["I drive a blue Tesla Model 3"]),  # paraphrase (car≠Tesla/drive)
    ("what is my pet called?", ["My cat's name is Mochi"]),  # paraphrase (pet≠cat)
    ("what's my editor theme preference?", ["I prefer dark mode in all my editors"]),
    ("where did I study?", ["I studied statistics at Tsinghua University"]),
    ("how long should meetings be?", ["Keep meetings under 30 minutes, I dislike long ones"]),
    ("which city do I live in?", ["I live in Shanghai"]),
]

# Heuristic-extraction check: (message, facts that SHOULD be captured).
# The empty-list cases must capture nothing (noise check).
EXTRACT_CASES: list[tuple[str, list[str]]] = [
    ("I prefer tea over coffee. What time is it?", ["tea"]),
    ("My name is Zion and I work in finance.", ["name", "work"]),
    ("The weather is nice today and the sky is blue.", []),
    ("我喜欢简洁的回答。今天几号?", ["简洁"]),
    ("Please always use metric units.", ["metric"]),
    ("Can you summarize this article?", []),
]


def _metrics_for(retrieved_ids, relevant_ids, k):
    topk = retrieved_ids[:k]
    hits = [i for i in topk if i in relevant_ids]
    recall = len(set(hits)) / len(relevant_ids) if relevant_ids else 0.0
    precision = len(hits) / k if k else 0.0
    rr = 0.0
    for rank, i in enumerate(topk, 1):
        if i in relevant_ids:
            rr = 1.0 / rank
            break
    return recall, precision, rr


def run_retrieval_benchmark(k: int = 5, config=None) -> dict:
    """Seed MEMORIES into a temp store and score retrieval over QUERIES."""
    from .config import Config
    from .core import Recall

    cfg = config or Config.load()
    cfg.active_scope = "bench"
    d = tempfile.mkdtemp()
    r = Recall(Path(d) / "bench.db", config=cfg)
    ids = {}
    for content, tags in MEMORIES:
        ids[content] = r.remember(content, tags=tags, scope="bench")
    mode = "semantic" if r.memory.has_embeddings else "keyword"

    r1s, recalls, precs, rrs, per_query = [], [], [], [], []
    for q, rel in QUERIES:
        rel_ids = {ids[c] for c in rel}
        retrieved = [h.id for h in r.recall_memories(q, limit=k, scope="bench")]
        r1, _, _ = _metrics_for(retrieved, rel_ids, 1)   # recall@1 (rank-1 quality)
        rc, pr, rr = _metrics_for(retrieved, rel_ids, k)
        r1s.append(r1)
        recalls.append(rc)
        precs.append(pr)
        rrs.append(rr)
        per_query.append({"query": q, "recall": rc, "top1": r1 > 0})
    r.close()

    n = len(QUERIES)
    return {
        "mode": mode,
        "queries": n,
        "k": k,
        "recall_at_1": sum(r1s) / n,
        "recall_at_k": sum(recalls) / n,
        "precision_at_k": sum(precs) / n,
        "mrr": sum(rrs) / n,
        "per_query": per_query,
    }


def run_extraction_benchmark() -> dict:
    """Measure heuristic auto-capture recall + false-capture (noise) rate."""
    from .extract import extract_memories

    expected_total = caught = 0
    noise = 0
    for msg, facts in EXTRACT_CASES:
        got = extract_memories(msg)
        blob = " || ".join(got).lower()
        if not facts:
            if got:
                noise += 1
            continue
        for fact in facts:
            expected_total += 1
            if fact.lower() in blob:
                caught += 1
    return {
        "cases": len(EXTRACT_CASES),
        "fact_recall": caught / expected_total if expected_total else 0.0,
        "false_captures": noise,
    }


def run_all(k: int = 5, config=None) -> dict:
    return {
        "retrieval": run_retrieval_benchmark(k=k, config=config),
        "extraction": run_extraction_benchmark(),
    }
