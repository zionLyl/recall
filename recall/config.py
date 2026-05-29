"""User configuration for recall.

Stored as JSON at ~/.recall/config.json (override base with RECALL_HOME).
Holds defaults so users don't repeat themselves: default provider/model,
daily budget, auto-memory toggle, active scope, etc.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from .store import default_db_path


def config_path() -> Path:
    return default_db_path().parent / "config.json"


@dataclass
class Config:
    default_provider: Optional[str] = None
    default_model: Optional[str] = None
    daily_budget_usd: float = 0.0          # 0 = no budget
    auto_memory: bool = True               # auto-extract memories after chat
    memory_inject_limit: int = 5
    active_scope: str = "default"          # which memory scope is active
    extras: dict = field(default_factory=dict)

    @classmethod
    def load(cls) -> "Config":
        p = config_path()
        if not p.exists():
            return cls()
        try:
            data = json.loads(p.read_text())
        except (ValueError, OSError):
            return cls()
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    def save(self) -> None:
        p = config_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False))

    def get(self, key: str):
        return getattr(self, key, None) if hasattr(self, key) else self.extras.get(key)

    def set(self, key: str, value) -> None:
        if hasattr(self, key) and key != "extras":
            # Coerce types based on the existing field.
            current = getattr(self, key)
            if isinstance(current, bool):
                value = str(value).lower() in ("1", "true", "yes", "on")
            elif isinstance(current, float):
                value = float(value)
            elif isinstance(current, int):
                value = int(value)
            setattr(self, key, value)
        else:
            self.extras[key] = value
