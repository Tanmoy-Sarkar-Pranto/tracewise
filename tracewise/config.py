from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _default_db_path() -> str:
    return str(Path.home() / ".tracewise" / "traces.db")


@dataclass
class TraceWiseConfig:
    db_path: str = field(default_factory=_default_db_path)
    max_traces: int = 1000
    enabled: bool = True
