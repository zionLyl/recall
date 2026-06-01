"""Quality evals for traced calls — local rule checks and an LLM judge.

engram already shows *cost* per call; evals make *quality* observable too, the
local-first counterpart to Langfuse/Phoenix evals. Rule checks are free and
deterministic; the LLM judge scores a reply against a criterion.

Each check returns a result dict: {kind, name, score (0–1), passed (bool), detail}.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from .adapters import get_adapter
from .adapters.base import ChatResult


# ---- local rule checks (no model call) ----------------------------------
def check_contains(text: str, needle: str) -> dict:
    passed = needle.lower() in (text or "").lower()
    return {"kind": "rule", "name": "contains", "score": 1.0 if passed else 0.0,
            "passed": passed, "detail": f"contains {needle!r}"}


def check_not_contains(text: str, needle: str) -> dict:
    passed = needle.lower() not in (text or "").lower()
    return {"kind": "rule", "name": "not_contains", "score": 1.0 if passed else 0.0,
            "passed": passed, "detail": f"must not contain {needle!r}"}


def check_regex(text: str, pattern: str) -> dict:
    try:
        passed = re.search(pattern, text or "") is not None
    except re.error as e:
        return {"kind": "rule", "name": "regex", "score": 0.0, "passed": False,
                "detail": f"bad pattern: {e}"}
    return {"kind": "rule", "name": "regex", "score": 1.0 if passed else 0.0,
            "passed": passed, "detail": f"matches /{pattern}/"}


def check_max_tokens(output_tokens: int, limit: int) -> dict:
    passed = output_tokens <= limit
    return {"kind": "rule", "name": "max_tokens", "score": 1.0 if passed else 0.0,
            "passed": passed, "detail": f"{output_tokens} <= {limit} output tokens"}


# ---- LLM judge -----------------------------------------------------------
_JUDGE_SYSTEM = (
    "You are a strict evaluator. Rate how well the RESPONSE satisfies the "
    "CRITERION on a 1-5 scale (5 = fully satisfies, 1 = not at all).\n"
    "Reply with ONLY a JSON object: {\"score\": <1-5>, \"reason\": \"<short>\"}."
)


def _parse_judge(text: str) -> Optional[dict]:
    """Parse {score, reason}; normalize score to 0–1 (accepts a 1–5 or 0–1 scale)."""
    if not text:
        return None
    raw = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()
    if not raw.startswith("{"):
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            raw = m.group(0)
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict) or "score" not in data:
        return None
    try:
        raw_score = float(data["score"])
    except (ValueError, TypeError):
        return None
    # The judge prompt asks for 1-5, so any score >= 1 is on that scale
    # (1 -> 0.0, 5 -> 1.0); a fractional score in (0,1) is already normalized.
    norm = (raw_score - 1.0) / 4.0 if raw_score >= 1 else raw_score
    norm = max(0.0, min(1.0, norm))
    return {
        "kind": "judge", "name": "llm_judge", "score": round(norm, 3),
        "passed": norm >= 0.5,
        "detail": str(data.get("reason", ""))[:300],
    }


def judge(
    reply: str, criterion: str, provider: str, model: str,
    *, api_key: Optional[str] = None, base_url: Optional[str] = None,
) -> tuple[Optional[dict], Optional[ChatResult]]:
    """Score `reply` against `criterion` with a model. Raises on SDK errors."""
    prompt = f"CRITERION:\n{criterion}\n\nRESPONSE:\n{reply}\n\nRate it."
    adapter = get_adapter(provider, model, api_key=api_key, base_url=base_url)
    result = adapter.chat(prompt, system=_JUDGE_SYSTEM)
    return _parse_judge(result.text), result
