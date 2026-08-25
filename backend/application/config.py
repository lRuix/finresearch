"""Application configuration."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = BASE_DIR / "data" / "research.db"


def _warehouse_dsn() -> str | None:
    return os.environ.get("WAREHOUSE_DSN") or None


@dataclass(frozen=True)
class AppConfig:
    db_path: Path = DEFAULT_DB_PATH
    warehouse_dsn: str | None = None
    cache_ttl_seconds: int = 300
    breaker_seconds: int = 120

    def __post_init__(self) -> None:
        if self.warehouse_dsn is None:
            object.__setattr__(self, "warehouse_dsn", _warehouse_dsn())
