"""Prompt template rendering.

Templates are plain strings with ``{var}`` placeholders. Rendering substitutes
provided variables and leaves any unknown ``{placeholder}`` untouched (so a
half-filled template never raises). Doubled braces ``{{`` / ``}}`` are literal.
"""

from __future__ import annotations

import re
from typing import Mapping

_VAR_RE = re.compile(r"\{\{|\}\}|\{(\w+)\}")


def render(content: str, variables: Mapping[str, str]) -> str:
    """Substitute {var} placeholders from `variables`; keep unknown ones as-is."""
    def _sub(m: re.Match) -> str:
        token = m.group(0)
        if token == "{{":
            return "{"
        if token == "}}":
            return "}"
        name = m.group(1)
        return str(variables.get(name, token))  # unknown → leave the {name} literal

    return _VAR_RE.sub(_sub, content or "")


def parse_vars(pairs) -> dict[str, str]:
    """Parse ['k=v', ...] CLI pairs into a dict (ignores malformed entries)."""
    out: dict[str, str] = {}
    for p in pairs or []:
        if "=" in p:
            k, v = p.split("=", 1)
            k = k.strip()
            if k:
                out[k] = v
    return out
