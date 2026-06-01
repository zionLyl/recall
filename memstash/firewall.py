"""Memory write firewall — guards long-term memory against poisoning.

Long-term memory amplifies prompt injection: untrusted content (web pages, repo
READMEs, tool output) can carry instructions or false "facts" that get stored and
later re-injected into prompts, steering an agent persistently. The firewall
decides, per write, whether to **quarantine** it:

  - Trusted sources (the user's own input: `manual`, `auto`) pass through.
  - Untrusted-by-origin sources (`web`, `tool`, `external`) are quarantined.
  - Everything else (`document`, `mcp`, `imported`, …) is content-scanned and
    quarantined only if it trips an injection heuristic.

Quarantined memories are stored but inactive, so they're **never injected** into
prompts until you `approve` them. Mode is configurable: quarantine / warn / off.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# Origins we never trust by default — quarantine on sight.
_UNTRUSTED_SOURCES = {"web", "tool", "external", "browser", "scrape"}

# Lightweight injection / poisoning heuristics (EN + 中文). First hit wins.
_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts?)",
    r"disregard\s+(the\s+)?(previous|above|all|prior)",
    r"forget\s+(everything|all\s+previous|the\s+above)",
    r"you\s+are\s+now\b",
    r"\bact\s+as\s+(an?\s+)?",
    r"new\s+(system\s+)?instructions?\b",
    r"</?(system|assistant|user)>",
    r"\bsystem\s*prompt\b",
    r"override\s+(your|the)\s+(instructions|rules|guardrails)",
    r"do\s+not\s+(tell|inform|reveal)\b",
    r"(send|exfiltrate|leak|post)\s+.{0,30}(api[_\s-]?key|token|password|secret)",
    r"(run|execute)\s+the\s+following",
    r"curl\s+\S+\s*\|\s*(sh|bash)",
    r"rm\s+-rf\b",
    r"忽略(以上|之前|前面|上述).{0,6}(指令|指示|提示)",
    r"忘记(之前|以上|前面)",
    r"你现在是",
    r"(执行|运行)以下",
    r"不要(告诉|透露|提及)",
]
_RE = re.compile("|".join(_PATTERNS), re.IGNORECASE)


def scan(content: str) -> tuple[bool, str]:
    """Return (risky, reason). Pure, local, no LLM."""
    m = _RE.search(content or "")
    if m:
        return True, f"matched injection pattern: {m.group(0)[:60]!r}"
    return False, ""


@dataclass
class FirewallConfig:
    mode: str = "quarantine"          # "quarantine" | "warn" | "off"
    trusted_sources: tuple = ("manual", "auto")

    @classmethod
    def from_strings(cls, mode: str, trusted_csv: str) -> "FirewallConfig":
        srcs = tuple(s.strip() for s in (trusted_csv or "").split(",") if s.strip()) or ("manual", "auto")
        return cls(mode=mode or "quarantine", trusted_sources=srcs)


def evaluate(content: str, source: str, cfg: Optional[FirewallConfig] = None) -> tuple[bool, str]:
    """Decide whether a write should be quarantined. Returns (quarantine, reason).
    In 'warn' mode it never quarantines but still returns the reason; in 'off'
    mode it's a no-op."""
    cfg = cfg or FirewallConfig()
    if cfg.mode == "off":
        return False, ""
    if source in cfg.trusted_sources:
        return False, ""
    reason = ""
    if source in _UNTRUSTED_SOURCES:
        reason = f"untrusted source '{source}'"
    else:
        risky, why = scan(content)
        if risky:
            reason = why
    if not reason:
        return False, ""
    # reason found: quarantine (or just flag in warn mode)
    return (cfg.mode == "quarantine"), reason
