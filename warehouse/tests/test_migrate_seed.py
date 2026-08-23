"""Seed migration helper tests."""
from __future__ import annotations

from datetime import datetime
import sqlite3
import uuid

import psycopg
import pytest

from etl.load_ods import MARKET_TABLES
from etl.migrate_seed import (
    _CN_TIMEZONE,
    _new_batch_id,
    _parse_news_time,
    _split_fx_currency,
    migrate_klines,
)

MIGRATE_SYMBOL_PREFIX = "TEST-MIGRATE-"


def _unique_symbol(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


def _unique_fx_symbol() -> str:
    letters = "".join(char for char in uuid.uuid4().hex.upper() if char.isalpha())
    return (letters + "AAAAAA")[:6] + "=X"


def test_fx_currency_parsing_supports_common_symbol_formats():
    assert _split_fx_currency("AUDUSD=X") == ("AUD", "USD")
    assert _split_fx_currency("EUR/USD") == ("EUR", "USD")
    assert _split_fx_currency("usdcny=x") == ("USD", "CNY")


def test_fx_currency_parsing_rejects_unrecognized_symbol():
    assert _split_fx_currency("INVALID") == (None, None)


def test_news_time_uses_current_year_and_cn_timezone():
    parsed = _parse_news_time("08-19 09:12")
    now = datetime.now(_CN_TIMEZONE)

    assert parsed.tzinfo == _CN_TIMEZONE
    assert parsed.year == now.year
    assert parsed.month == 8
    assert parsed.day == 19
    assert parsed.hour == 9
    assert parsed.minute == 12


def test_rss_news_time_is_stable_within_ingestion_day():
    first = _parse_news_time("RSS")
    second = _parse_news_time("RSS")

    assert first == second
    assert first.date() == datetime.now(_CN_TIMEZONE).date()
    assert first.hour == 0
    assert first.minute == 0


def test_batch_ids_are_unique():
    assert _new_batch_id() != _new_batch_id()
    assert _new_batch_id().startswith("seed-")


@pytest.fixture
def migrate_cleanup(dsn):
    batch_id = f"test-migrate-{uuid.uuid4()}"

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT market_id FROM dim_market")
        before_markets = {row[0] for row in cur.fetchall()}
        cur.execute("SELECT provider_id FROM dim_provider")
        before_providers = {row[0] for row in cur.fetchall()}
        cur.execute("SELECT date_key FROM dim_date")
        before_dates = {row[0] for row in cur.fetchall()}
        cur.execute("SELECT instrument_id FROM dim_instrument")
        before_instruments = {row[0] for row in cur.fetchall()}

    yield batch_id

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        symbols_by_market: dict[str, list[str]] = {}
        for market, table in MARKET_TABLES.items():
            cur.execute(
                f"SELECT symbol FROM {table} WHERE sync_batch_id = %s",
                (batch_id,),
            )
            symbols_by_market[market] = [row[0] for row in cur.fetchall()]
            cur.execute(
                f"DELETE FROM {table} WHERE sync_batch_id = %s",
                (batch_id,),
            )

        for market, symbols in symbols_by_market.items():
            if not symbols:
                continue
            cur.execute(
                """
                DELETE FROM fact_kline
                WHERE provider_id = 'sqlite'
                  AND instrument_id IN (
                      SELECT instrument_id
                      FROM dim_instrument
                      WHERE market_id = %s
                        AND symbol = ANY(%s)
                        AND instrument_id != ALL(%s)
                  )
                """,
                (market, symbols, list(before_instruments)),
            )
            cur.execute(
                """
                DELETE FROM dim_instrument
                WHERE market_id = %s
                  AND symbol = ANY(%s)
                  AND instrument_id != ALL(%s)
                """,
                (market, symbols, list(before_instruments)),
            )

        cur.execute(
            """
            DELETE FROM dim_provider
            WHERE provider_id = 'sqlite' AND provider_id != ALL(%s)
            """,
            (list(before_providers),),
        )
        cur.execute(
            "DELETE FROM dim_date WHERE date_key != ALL(%s)",
            (list(before_dates),),
        )
        cur.execute(
            "DELETE FROM dim_market WHERE market_id != ALL(%s)",
            (list(before_markets),),
        )
        conn.commit()


def _seed_sqlite_db(tmp_path, a_share_symbol: str, fx_symbol: str) -> str:
    db_path = tmp_path / "migrate-seed.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE klines (
          market TEXT, symbol TEXT, period TEXT, time TEXT,
          open REAL, high REAL, low REAL, close REAL, volume REAL
        )
        """
    )
    conn.executemany(
        """
        INSERT INTO klines
          (market, symbol, period, time, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "a-share",
                a_share_symbol,
                "d",
                "2026-01-01",
                1.0,
                2.0,
                0.5,
                1.5,
                100.0,
            ),
            (
                "a-share",
                a_share_symbol,
                "d",
                "2026-01-02",
                1.0,
                2.0,
                0.5,
                1.6,
                110.0,
            ),
            (
                "fx",
                fx_symbol,
                "d",
                "2026-01-01",
                1.1,
                1.2,
                1.0,
                1.15,
                0.0,
            ),
            (
                "fx",
                "INVALID",
                "d",
                "2026-01-02",
                1.2,
                1.3,
                1.1,
                1.25,
                0.0,
            ),
            (
                "unknown",
                f"{MIGRATE_SYMBOL_PREFIX}UNKNOWN",
                "d",
                "2026-01-01",
                1.0,
                2.0,
                0.5,
                1.0,
                10.0,
            ),
        ],
    )
    conn.commit()
    conn.close()
    return str(db_path)


def test_migrate_klines_streams_markets_and_skips_unknown(dsn, migrate_cleanup, tmp_path):
    a_share_symbol = _unique_symbol(f"{MIGRATE_SYMBOL_PREFIX}A")
    fx_symbol = _unique_fx_symbol()
    db_path = _seed_sqlite_db(tmp_path, a_share_symbol, fx_symbol)
    batch_id = migrate_cleanup

    stats = migrate_klines(dsn, db_path, batch_id=batch_id, ods_batch_size=1)

    assert stats["a-share"]["ods"] == 2
    assert stats["fx"]["ods"] == 1

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM ods_klines_a_share WHERE sync_batch_id = %s",
            (batch_id,),
        )
        assert cur.fetchone()[0] == 2
        cur.execute(
            "SELECT count(*) FROM ods_klines_fx WHERE sync_batch_id = %s",
            (batch_id,),
        )
        assert cur.fetchone()[0] == 1
        cur.execute(
            """
            SELECT count(*)
            FROM fact_kline f
            JOIN dim_instrument i ON i.instrument_id = f.instrument_id
            WHERE f.provider_id = 'sqlite' AND i.symbol = %s
            """,
            (a_share_symbol,),
        )
        assert cur.fetchone()[0] == 2
        cur.execute(
            """
            SELECT count(*)
            FROM fact_kline f
            JOIN dim_instrument i ON i.instrument_id = f.instrument_id
            WHERE f.provider_id = 'sqlite' AND i.symbol = %s
            """,
            (fx_symbol,),
        )
        assert cur.fetchone()[0] == 1
        cur.execute(
            """
            SELECT count(*)
            FROM ods_klines_fx
            WHERE sync_batch_id = %s AND symbol = %s
            """,
            (batch_id, "INVALID"),
        )
        assert cur.fetchone()[0] == 0
        cur.execute(
            """
            SELECT base_currency, quote_currency
            FROM ods_klines_fx
            WHERE sync_batch_id = %s
            """,
            (batch_id,),
        )
        assert cur.fetchone() == (fx_symbol[:3], fx_symbol[3:6])
