"""PostgreSQL implementation of MarketDataRepository backed by the warehouse."""
from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from domain.models import Instrument, KlineRow


_PERIOD_ALIASES = {"1d": "d", "d": "d", "day": "d", "1h": "h", "1w": "w", "w": "w"}


class PostgresMarketDataRepository:
    """Read market data from the warehouse; sync writes are not supported."""

    def __init__(self, dsn: str):
        self._dsn = dsn

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self._dsn)

    def _normalize_period(self, period: str) -> str:
        return _PERIOD_ALIASES.get(str(period).lower(), str(period))

    def get_klines(
        self,
        market: str,
        symbol: str,
        period: str,
        start: str | None = None,
        end: str | None = None,
    ) -> list[KlineRow]:
        sql = """
            SELECT f.time, f.open, f.high, f.low, f.close, f.volume
            FROM fact_kline f
            JOIN dim_instrument i ON i.instrument_id = f.instrument_id
            WHERE i.market_id = %s AND i.symbol = %s AND f.period = %s
        """
        params: list[Any] = [market, symbol, self._normalize_period(period)]
        if start is not None:
            sql += " AND f.time >= %s"
            params.append(start)
        if end is not None:
            sql += " AND f.time <= %s"
            params.append(end)
        sql += " ORDER BY f.time ASC"
        with self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [
            KlineRow(
                time=row["time"].isoformat(),
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
            )
            for row in rows
        ]

    def save_evaluation(
        self, evaluated_on: str, market: str, symbol: str, score: float, payload: dict
    ) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO backend_evaluations (evaluated_on, market, symbol, score, payload)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (evaluated_on, market, symbol) DO UPDATE SET
                  score = EXCLUDED.score, payload = EXCLUDED.payload,
                  updated_at = now()
                """,
                (evaluated_on, market, symbol, score, Jsonb(payload)),
            )
            conn.commit()

    def get_evaluation(
        self, evaluated_on: str, market: str, symbol: str
    ) -> dict | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT payload FROM backend_evaluations
                WHERE evaluated_on = %s AND market = %s AND symbol = %s
                """,
                (evaluated_on, market, symbol),
            )
            row = cur.fetchone()
        return dict(row[0]) if row else None

    def upsert_snapshot(self, date: str, market: str, items: list[dict]) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO backend_market_snapshots (
                  date, market, symbol, name, turnover, market_cap, rank
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (date, market, symbol) DO UPDATE SET
                  name = EXCLUDED.name, turnover = EXCLUDED.turnover,
                  market_cap = EXCLUDED.market_cap, rank = EXCLUDED.rank
                """,
                [
                    (
                        date,
                        market,
                        item["symbol"],
                        item.get("name", ""),
                        item.get("turnover"),
                        item.get("market_cap"),
                        item["rank"],
                    )
                    for item in items
                ],
            )
            conn.commit()

    def get_snapshot(self, date: str, market: str) -> list[dict]:
        with self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT symbol, name, turnover, market_cap, rank
                FROM backend_market_snapshots
                WHERE date = %s AND market = %s
                ORDER BY rank ASC
                """,
                (date, market),
            )
            return [dict(row) for row in cur.fetchall()]

    def upsert_klines(
        self, market: str, symbol: str, period: str, rows: list[KlineRow]
    ) -> None:
        raise NotImplementedError("行情同步服务已下线：数据由数仓 ETL 维护")

    def upsert_instruments(self, items: list[Instrument]) -> None:
        raise NotImplementedError("标的写入已下线：由数仓 ETL 维护 dim_instrument")

    def get_watermark(self, market: str, symbol: str, period: str) -> str | None:
        raise NotImplementedError("行情同步服务已下线：不维护同步水位线")

    def set_watermark(self, market: str, symbol: str, period: str, as_of: str) -> None:
        raise NotImplementedError("行情同步服务已下线：不维护同步水位线")
