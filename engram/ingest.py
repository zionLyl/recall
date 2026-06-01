"""Ingest documents into searchable memory.

Reads a text/markdown file (or PDF if `pypdf` is installed), splits it into
reasonably-sized chunks, and stores each as a memory — so `engram search` and
chat memory-injection cover your notes/docs, not just facts you typed in. Purely
local and deterministic; no LLM or external service involved.
"""

from __future__ import annotations

import re
from pathlib import Path


def chunk_text(text: str, max_chars: int = 500) -> list[str]:
    """Split text into chunks: one per paragraph, further split long paragraphs
    on sentence boundaries (and hard-split any single oversized sentence)."""
    out: list[str] = []
    for para in re.split(r"\n\s*\n", text or ""):
        para = re.sub(r"\s+", " ", para).strip()
        if not para:
            continue
        if len(para) <= max_chars:
            out.append(para)
            continue
        cur = ""
        for sent in re.split(r"(?<=[.!?。！？])\s+", para):
            if not cur:
                cur = sent
            elif len(cur) + 1 + len(sent) <= max_chars:
                cur += " " + sent
            else:
                out.append(cur)
                cur = sent
            while len(cur) > max_chars:        # a single very long sentence
                out.append(cur[:max_chars])
                cur = cur[max_chars:]
        if cur.strip():
            out.append(cur)
    return [c for c in out if c.strip()]


def read_file(path) -> str:
    """Read a document to text. Supports .txt/.md natively; .pdf via pypdf."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"No such file: {path}")
    if p.suffix.lower() == ".pdf":
        try:
            import pypdf
        except ImportError as e:
            raise RuntimeError(
                "PDF support needs: pip install 'engram-ai[pdf]'"
            ) from e
        reader = pypdf.PdfReader(str(p))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)
    return p.read_text(encoding="utf-8", errors="replace")
