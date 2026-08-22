"""Application configuration."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = BASE_DIR / "data" / "research.db"


@dataclass(frozen=True)
class AppConfig:
    db_path: Path = DEFAULT_DB_PATH
    cache_ttl_seconds: int = 300
    breaker_seconds: int = 120
