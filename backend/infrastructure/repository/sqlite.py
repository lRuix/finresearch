"""SQLite implementation of MarketDataRepository."""
from __future__ import annotations

from contextlib import closing
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from domain.models import Instrument, KlineRow


_SCHEMA = """
CREATE TABLE IF NOT EXISTS instruments (
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  name TEXT NOT NULL,
  currency TEXT NOT NULL,
  sector TEXT,
  base_risk REAL,
  liquidity REAL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (market, symbol)
);

CREATE TABLE IF NOT EXISTS klines (
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  period TEXT NOT NULL,
  time TEXT NOT NULL,
  open REAL NOT NULL,
  high REAL NOT NULL,
  low REAL NOT NULL,
  close REAL NOT NULL,
  volume REAL NOT NULL,
  PRIMARY KEY (market, symbol, period, time)
);

CREATE TABLE IF NOT EXISTS market_snapshots (
  date TEXT NOT NULL,
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  name TEXT NOT NULL,
  turnover REAL,
  market_cap REAL,
  rank INTEGER NOT NULL,
  PRIMARY KEY (date, market, symbol)
);

CREATE INDEX IF NOT EXISTS idx_market_snapshots_date_market
  ON market_snapshots(date, market);

CREATE TABLE IF NOT EXISTS evaluations (
  evaluated_on TEXT NOT NULL,
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  score REAL NOT NULL,
  payload TEXT NOT NULL,
  PRIMARY KEY (evaluated_on, market, symbol)
);

CREATE TABLE IF NOT EXISTS sync_watermarks (
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  period TEXT NOT NULL,
  as_of TEXT NOT NULL,
  PRIMARY KEY (market, symbol, period)
);
"""


class SqliteMarketDataRepository:
    def __init__(self, db_path: Path):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def _init_schema(self) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.executescript(_SCHEMA)
            conn.commit()

    def upsert_instruments(self, items: list[Instrument]) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO instruments
                  (market, symbol, name, currency, sector, base_risk, liquidity, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.market, item.symbol, item.name, item.currency,
                        item.sector, item.base_risk, item.liquidity,
                        datetime.now(timezone.utc).isoformat(),
                    )
                    for item in items
                ],
            )
            conn.commit()

    def upsert_klines(self, market: str, symbol: str, period: str,
                      rows: list[KlineRow]) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO klines
                  (market, symbol, period, time, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (market, symbol, period, row.time, row.open, row.high,
                     row.low, row.close, row.volume)
                    for row in rows
                ],
            )
            conn.commit()

    def get_klines(self, market: str, symbol: str, period: str,
                   start: str | None = None, end: str | None = None) -> list[KlineRow]:
        """Return klines in ascending ISO time order.

        start / end are inclusive bounds; time strings are compared as ISO text.
        """
        sql = """
            SELECT time, open, high, low, close, volume FROM klines
            WHERE market = ? AND symbol = ? AND period = ?
        """
        params = [market, symbol, period]
        if start is not None:
            sql += " AND time >= ?"
            params.append(start)
        if end is not None:
            sql += " AND time <= ?"
            params.append(end)
        sql += " ORDER BY time ASC"
        with self._lock, closing(self._connect()) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [KlineRow(**dict(row)) for row in rows]

    def get_watermark(self, market: str, symbol: str, period: str) -> str | None:
        with self._lock, closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT as_of FROM sync_watermarks WHERE market = ? AND symbol = ? AND period = ?",
                (market, symbol, period),
            ).fetchone()
        return row["as_of"] if row else None

    def set_watermark(self, market: str, symbol: str, period: str, as_of: str) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sync_watermarks
                  (market, symbol, period, as_of)
                VALUES (?, ?, ?, ?)
                """,
                (market, symbol, period, as_of),
            )
            conn.commit()

    def upsert_snapshot(self, date: str, market: str, items: list[dict]) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.execute(
                "DELETE FROM market_snapshots WHERE date = ? AND market = ?",
                (date, market),
            )
            conn.executemany(
                """
                INSERT OR REPLACE INTO market_snapshots
                  (date, market, symbol, name, turnover, market_cap, rank)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        date, market, item["symbol"], item.get("name", item["symbol"]),
                        item.get("turnover"), item.get("market_cap"), rank,
                    )
                    for rank, item in enumerate(items, start=1)
                ],
            )
            conn.commit()

    def get_snapshot(self, date: str, market: str) -> list[dict]:
        with self._lock, closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT symbol, name, turnover, market_cap, rank
                FROM market_snapshots
                WHERE date = ? AND market = ?
                ORDER BY rank ASC
                """,
                (date, market),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_evaluation(self, evaluated_on: str, market: str, symbol: str,
                        score: float, payload: dict) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO evaluations
                  (evaluated_on, market, symbol, score, payload)
                VALUES (?, ?, ?, ?, ?)
                """,
                (evaluated_on, market, symbol, score, json.dumps(payload, ensure_ascii=False)),
            )
            conn.commit()

    def get_evaluation(self, evaluated_on: str, market: str, symbol: str) -> dict | None:
        with self._lock, closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT payload FROM evaluations
                WHERE evaluated_on = ? AND market = ? AND symbol = ?
                """,
                (evaluated_on, market, symbol),
            ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row["payload"])
        except (ValueError, TypeError):
            return None
