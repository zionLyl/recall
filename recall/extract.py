"""Heuristic memory extraction from a user message.

After a chat, recall can auto-capture durable facts/preferences the user stated
about themselves — without an extra LLM call. This is intentionally
conservative: it only grabs first-person statements that look like stable
preferences or facts, so the memory store stays signal-rich.

Works for English and Chinese. Override or disable via config.auto_memory.
"""

from __future__ import annotations

import re

# First-person preference / fact cues.
_EN_CUES = [
    r"\bi (?:prefer|like|love|hate|dislike|want|need|use|work on|am|'m)\b",
    r"\bmy (?:name|email|timezone|preference|goal|project|stack)\b",
    r"\bplease (?:always|never)\b",
    r"\bcall me\b",
    r"\bremember that\b",
]
_ZH_CUES = [
    r"我(?:喜欢|讨厌|偏好|习惯|想要|需要|使用|用|是|叫|在做|正在做)",
    r"我的(?:名字|邮箱|时区|偏好|目标|项目|风格)",
    r"请(?:务必|一定|总是|永远不要|不要)",
    r"叫我",
    r"记住",
]

_CUE_RE = re.compile("|".join(_EN_CUES + _ZH_CUES), re.IGNORECASE)

# Sentence splitter that handles EN + ZH punctuation.
_SPLIT_RE = re.compile(r"[.!?。！？\n]+")

# Skip questions and ephemeral asks.
_SKIP_RE = re.compile(r"\?|？|^(?:what|how|why|when|who|where|can you|could you|帮我|请问)", re.IGNORECASE)


def extract_memories(text: str, max_items: int = 3) -> list[str]:
    """Return a small list of candidate memory strings from `text`."""
    out: list[str] = []
    for raw in _SPLIT_RE.split(text or ""):
        s = raw.strip()
        if len(s) < 6 or len(s) > 240:
            continue
        if _SKIP_RE.search(s):
            continue
        if _CUE_RE.search(s):
            out.append(s)
        if len(out) >= max_items:
            break
    return out
