"""DWS materialized view refresh tests."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import uuid
from typing import Any

import psycopg
import pytest

from etl.build_dwd import build_dwd
from etl.build_dws import refresh_dws
from etl.load_ods import MARKET_TABLES, upsert_ods_rows


@dataclass
class DwsCleanupContext:
    batch_id: str
    provider_id: str
    provider_ids: list[str] = field(default_factory=list)


@pytest.fixture
def dws_cleanup(dsn):
    batch_id = f"test-build-dws-{uuid.uuid4()}"
    provider_id = f"test-build-dws-{uuid.uuid4().hex}"

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT market_id FROM dim_market")
        before_markets = {row[0] for row in cur.fetchall()}
        cur.execute("SELECT provider_id FROM dim_provider")
        before_providers = {row[0] for row in cur.fetchall()}
        cur.execute("SELECT date_key FROM dim_date")
        before_dates = {row[0] for row in cur.fetchall()}
        cur.execute("SELECT instrument_id FROM dim_instrument")
        before_instruments = {row[0] for row in cur.fetchall()}

    context = DwsCleanupContext(batch_id, provider_id)
    yield context

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        market_symbols: dict[str, list[str]] = {}
        for market, table in MARKET_TABLES.items():
            cur.execute(
                f"SELECT symbol FROM {table} WHERE sync_batch_id = %s",
                (batch_id,),
            )
            market_symbols[market] = [row[0] for row in cur.fetchall()]
            cur.execute(
                f"DELETE FROM {table} WHERE sync_batch_id = %s",
                (batch_id,),
            )

        providers = sorted({context.provider_id, *context.provider_ids})
        for market, symbols in market_symbols.items():
            if not symbols:
                continue

            cur.execute(
                """
                DELETE FROM fact_kline
                WHERE provider_id = ANY(%s)
                  AND instrument_id IN (
                      SELECT instrument_id
                      FROM dim_instrument
                      WHERE market_id = %s AND symbol = ANY(%s)
                  )
                """,
                (providers, market, symbols),
            )
            cur.execute(
                """
                SELECT instrument_id
                FROM dim_instrument
                WHERE market_id = %s
                  AND symbol = ANY(%s)
                  AND instrument_id != ALL(%s)
                """,
                (market, symbols, list(before_instruments)),
            )
            created_instrument_ids = [row[0] for row in cur.fetchall()]
            if created_instrument_ids:
                cur.execute(
                    "DELETE FROM dim_instrument WHERE instrument_id = ANY(%s)",
                    (created_instrument_ids,),
                )

        cur.execute(
            "DELETE FROM dim_provider WHERE provider_id = ANY(%s) AND provider_id != ALL(%s)",
            (providers, list(before_providers)),
        )
        cur.execute(
            """
            DELETE FROM dim_date
            WHERE date_key != ALL(%s)
            """,
            (list(before_dates),),
        )
        cur.execute(
            """
            DELETE FROM dim_market
            WHERE market_id != ALL(%s)
            """,
            (list(before_markets),),
        )
        conn.commit()

    refresh_dws(dsn)


def _unique_symbol(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


def _unique_date() -> date:
    return date(2099, 1, (uuid.uuid4().int % 27) + 1)


def _a_share_row(
    provider_id: str,
    symbol: str,
    batch_id: str,
    date_key: date,
    **overrides: Any,
) -> dict[str, Any]:
    row = {
        "provider": provider_id,
        "market": "a-share",
        "symbol": symbol,
        "interval": "1d",
        "ts": f"{date_key.isoformat()}T12:00:00+08:00",
        "open": 1.0,
        "high": 2.0,
        "low": 0.5,
        "close": 10.0,
        "volume": 100.0,
        "amount": 200.0,
        "change_pct": 1.5,
        "raw_payload": {"source": "unit-test"},
        "sync_batch_id": batch_id,
    }
    row.update(overrides)
    return row


def _fact_rows(dsn: str, symbols: list[str]) -> list[tuple[Any, ...]]:
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT i.symbol, f.date_key, f.close, f.volume
            FROM fact_kline f
            JOIN dim_instrument i ON i.instrument_id = f.instrument_id
            WHERE i.market_id = 'a-share'
              AND i.symbol = ANY(%s)
              AND f.period = 'd'
            ORDER BY i.symbol
            """,
            (symbols,),
        )
        return cur.fetchall()


def _dws_instrument_rows(
    dsn: str,
    market_id: str,
    date_key: date,
    symbols: list[str],
) -> list[tuple[Any, ...]]:
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT i.symbol, d.rows_count, d.last_close, d.total_volume
            FROM dws_instrument_daily d
            JOIN dim_instrument i ON i.instrument_id = d.instrument_id
            WHERE d.market_id = %s
              AND d.date_key = %s
              AND i.symbol = ANY(%s)
            ORDER BY i.symbol
            """,
            (market_id, date_key, symbols),
        )
        return cur.fetchall()


def _dws_market_row(dsn: str, market_id: str, date_key: date):
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT instrument_count, total_volume, avg_daily_return
            FROM dws_market_daily
            WHERE market_id = %s AND date_key = %s
            """,
            (market_id, date_key),
        )
        return cur.fetchone()


def test_refresh_dws_aggregates_daily_a_share_facts(dsn, dws_cleanup):
    date_key = _unique_date()
    symbol_a = _unique_symbol("TEST-DWS-A")
    symbol_b = _unique_symbol("TEST-DWS-B")
    rows = [
        _a_share_row(
            dws_cleanup.provider_id,
            symbol_a,
            dws_cleanup.batch_id,
            date_key,
            close=10.0,
            volume=100.0,
        ),
        _a_share_row(
            dws_cleanup.provider_id,
            symbol_b,
            dws_cleanup.batch_id,
            date_key,
            open=2.0,
            high=3.0,
            low=1.0,
            close=12.0,
            volume=250.0,
        ),
    ]

    upsert_ods_rows(dsn, "a-share", rows)
    assert build_dwd(dsn, "a-share") == 2
    refresh_dws(dsn)

    facts = _fact_rows(dsn, [symbol_a, symbol_b])
    assert len(facts) == 2
    fact_by_symbol = {row[0]: row for row in facts}

    instrument_rows = _dws_instrument_rows(dsn, "a-share", date_key, [symbol_a, symbol_b])
    assert len(instrument_rows) == 2
    for symbol, rows_count, last_close, total_volume in instrument_rows:
        fact = fact_by_symbol[symbol]
        assert rows_count == 1
        assert last_close == pytest.approx(fact[2])
        assert total_volume == pytest.approx(fact[3])

    market_row = _dws_market_row(dsn, "a-share", date_key)
    assert market_row is not None
    instrument_count, total_volume, _ = market_row
    assert instrument_count == 2
    assert total_volume == pytest.approx(100.0 + 250.0)


def test_refresh_dws_is_idempotent(dsn, dws_cleanup):
    date_key = _unique_date()
    symbol = _unique_symbol("TEST-DWS-IDEMPOTENT")
    row = _a_share_row(
        dws_cleanup.provider_id,
        symbol,
        dws_cleanup.batch_id,
        date_key,
        close=8.5,
        volume=80.0,
    )

    upsert_ods_rows(dsn, "a-share", [row])
    build_dwd(dsn, "a-share")
    refresh_dws(dsn)
    before = _dws_instrument_rows(dsn, "a-share", date_key, [symbol])

    refresh_dws(dsn)
    after = _dws_instrument_rows(dsn, "a-share", date_key, [symbol])

    assert before == after


def test_refresh_dws_on_empty_database_is_ok(dsn, dws_cleanup):
    refresh_dws(dsn)

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM dws_instrument_daily")
        cur.fetchone()
        cur.execute("SELECT count(*) FROM dws_market_daily")
        cur.fetchone()
