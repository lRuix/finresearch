"""DWS materialized view refresh tests."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from unittest.mock import patch
import uuid

import psycopg
import pytest

import etl.build_dws as build_dws_module
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
        cur.execute("SELECT provider_id FROM dim_provider")
        before_providers = {row[0] for row in cur.fetchall()}
        cur.execute("SELECT date_key FROM dim_date")
        before_dates = {row[0] for row in cur.fetchall()}
        cur.execute("SELECT market_id, symbol FROM dim_instrument")
        before_instrument_symbols: dict[str, set[str]] = {}
        for market_id, symbol in cur.fetchall():
            before_instrument_symbols.setdefault(market_id, set()).add(symbol)

    context = DwsCleanupContext(batch_id, provider_id)
    yield context

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        market_symbols: dict[str, list[str]] = {}
        test_dates: set[date] = set()
        for market, table in MARKET_TABLES.items():
            cur.execute(
                f"SELECT symbol, ts FROM {table} WHERE sync_batch_id = %s",
                (batch_id,),
            )
            rows = cur.fetchall()
            market_symbols[market] = [row[0] for row in rows]
            for row in rows:
                try:
                    test_dates.add(date.fromisoformat(row[1][:10]))
                except (TypeError, ValueError):
                    pass
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
                USING dim_instrument i
                WHERE fact_kline.instrument_id = i.instrument_id
                  AND fact_kline.market_id = %s
                  AND fact_kline.provider_id = ANY(%s)
                  AND i.market_id = %s
                  AND i.symbol = ANY(%s)
                """,
                (market, providers, market, symbols),
            )
            before_symbols = before_instrument_symbols.get(market, set())
            if before_symbols:
                cur.execute(
                    """
                    SELECT instrument_id
                    FROM dim_instrument
                    WHERE market_id = %s
                      AND symbol = ANY(%s)
                      AND symbol != ALL(%s)
                    """,
                    (market, symbols, sorted(before_symbols)),
                )
            else:
                cur.execute(
                    """
                    SELECT instrument_id
                    FROM dim_instrument
                    WHERE market_id = %s
                      AND symbol = ANY(%s)
                    """,
                    (market, symbols),
                )
            created_instrument_ids = [row[0] for row in cur.fetchall()]
            if created_instrument_ids:
                cur.execute(
                    "DELETE FROM dim_instrument WHERE instrument_id = ANY(%s)",
                    (created_instrument_ids,),
                )

        if before_providers:
            cur.execute(
                """
                DELETE FROM dim_provider
                WHERE provider_id = ANY(%s)
                  AND provider_id != ALL(%s)
                """,
                (providers, sorted(before_providers)),
            )
        else:
            cur.execute(
                "DELETE FROM dim_provider WHERE provider_id = ANY(%s)",
                (providers,),
            )
        if test_dates:
            cur.execute(
                """
                DELETE FROM dim_date
                WHERE date_key = ANY(%s)
                  AND date_key != ALL(%s)
                """,
                (sorted(test_dates), sorted(before_dates)),
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
            SELECT i.symbol, d.rows_count, d.last_close, d.total_volume, d.amplitude
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


class _FailingDwsCursor:
    def __init__(self, real_cursor):
        self._real_cursor = real_cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        if "dws_market_daily" in query:
            raise psycopg.errors.UndefinedTable("injected second refresh failure")
        return self._real_cursor.execute(query, params)


class _FailingDwsConnection:
    def __init__(self, real_connection):
        self._real_connection = real_connection

    def cursor(self):
        return _FailingDwsCursor(self._real_connection.cursor())


class _NoCommitConnection:
    def __init__(self, real_connection):
        self._real_connection = real_connection

    def cursor(self):
        return self._real_connection.cursor()

    def commit(self):
        return None


@contextmanager
def _connect_with_failing_second_refresh(dsn: str):
    with psycopg.connect(dsn) as real_connection:
        yield _FailingDwsConnection(real_connection)


def _connect_with_existing_connection(connection):
    @contextmanager
    def _connect(_dsn: str):
        yield _NoCommitConnection(connection)

    return _connect


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
            ts=f"{date_key.isoformat()}T12:00:00+08:00",
            open=10.0,
            high=12.0,
            low=9.0,
            close=11.0,
            volume=100.0,
        ),
        _a_share_row(
            dws_cleanup.provider_id,
            symbol_a,
            dws_cleanup.batch_id,
            date_key,
            ts=f"{date_key.isoformat()}T14:00:00+08:00",
            open=11.5,
            high=13.0,
            low=10.5,
            close=12.5,
            volume=200.0,
        ),
        _a_share_row(
            dws_cleanup.provider_id,
            symbol_b,
            dws_cleanup.batch_id,
            date_key,
            ts=f"{date_key.isoformat()}T12:00:00+08:00",
            open=2.0,
            high=3.0,
            low=1.0,
            close=12.0,
            volume=250.0,
        ),
    ]

    upsert_ods_rows(dsn, "a-share", rows)
    assert build_dwd(dsn, "a-share") == 3
    refresh_dws(dsn)

    facts = _fact_rows(dsn, [symbol_a, symbol_b])
    assert len(facts) == 3

    instrument_rows = _dws_instrument_rows(dsn, "a-share", date_key, [symbol_a, symbol_b])
    assert len(instrument_rows) == 2
    expected = {
        symbol_a: {
            "rows_count": 2,
            "last_close": 12.5,
            "total_volume": 300.0,
            "amplitude": (13.0 - 9.0) / 9.0,
        },
        symbol_b: {
            "rows_count": 1,
            "last_close": 12.0,
            "total_volume": 250.0,
            "amplitude": (3.0 - 1.0) / 1.0,
        },
    }
    for symbol, rows_count, last_close, total_volume, amplitude in instrument_rows:
        expected_row = expected[symbol]
        assert rows_count == expected_row["rows_count"]
        assert last_close == pytest.approx(expected_row["last_close"], rel=1e-5)
        assert total_volume == pytest.approx(expected_row["total_volume"], rel=1e-5)
        assert amplitude == pytest.approx(expected_row["amplitude"], rel=1e-5)

    market_row = _dws_market_row(dsn, "a-share", date_key)
    assert market_row is not None
    instrument_count, total_volume, avg_daily_return = market_row
    expected_returns = [
        (11.0 - 10.0) / 10.0,
        (12.5 - 11.5) / 11.5,
        (12.0 - 2.0) / 2.0,
    ]
    assert instrument_count == 2
    assert total_volume == pytest.approx(100.0 + 200.0 + 250.0, rel=1e-5)
    assert avg_daily_return == pytest.approx(sum(expected_returns) / len(expected_returns), rel=1e-5)


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
    conn = psycopg.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM fact_kline")
        with patch.object(
            build_dws_module,
            "connect",
            _connect_with_existing_connection(conn),
        ):
            refresh_dws(dsn)
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM dws_instrument_daily")
            assert cur.fetchone()[0] == 0
            cur.execute("SELECT count(*) FROM dws_market_daily")
            assert cur.fetchone()[0] == 0
    finally:
        conn.rollback()
        conn.close()


def test_refresh_dws_rolls_back_first_refresh_when_second_fails(dsn, dws_cleanup):
    date_key = _unique_date()
    symbol = _unique_symbol("TEST-DWS-ROLLBACK")
    first_row = _a_share_row(
        dws_cleanup.provider_id,
        symbol,
        dws_cleanup.batch_id,
        date_key,
        close=10.0,
        volume=100.0,
    )

    upsert_ods_rows(dsn, "a-share", [first_row])
    assert build_dwd(dsn, "a-share") == 1
    refresh_dws(dsn)
    before = _dws_instrument_rows(dsn, "a-share", date_key, [symbol])
    assert len(before) == 1

    second_row = _a_share_row(
        dws_cleanup.provider_id,
        symbol,
        dws_cleanup.batch_id,
        date_key,
        ts=f"{date_key.isoformat()}T14:00:00+08:00",
        close=12.0,
        volume=200.0,
    )
    upsert_ods_rows(dsn, "a-share", [second_row])
    build_dwd(dsn, "a-share")
    assert len(_fact_rows(dsn, [symbol])) == 2

    with patch.object(
        build_dws_module,
        "connect",
        _connect_with_failing_second_refresh,
    ):
        with pytest.raises(psycopg.errors.UndefinedTable):
            refresh_dws(dsn)

    assert _dws_instrument_rows(dsn, "a-share", date_key, [symbol]) == before
