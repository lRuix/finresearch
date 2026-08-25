"""Incremental sync tests."""
from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
import uuid

import psycopg
import pytest

from etl.load_ods import MARKET_TABLES, upsert_ods_rows
from etl.migrate_seed import _new_batch_id
from etl.sync_incremental import sync_incremental
from backend.infrastructure.datasources import macro_data


SYNC_SYMBOL_PREFIX = "TEST-SYNC-"


def _unique_symbol(prefix: str = SYNC_SYMBOL_PREFIX) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


def _unique_fx_symbol() -> str:
    letters = "".join(char for char in uuid.uuid4().hex.upper() if char.isalpha())
    return (letters + "AAAAAA")[:6] + "=X"


@pytest.fixture
def sync_cleanup(dsn):
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT market_id FROM dim_market")
        before_markets = {row[0] for row in cur.fetchall()}
        cur.execute("SELECT provider_id FROM dim_provider")
        before_providers = {row[0] for row in cur.fetchall()}
        cur.execute("SELECT date_key FROM dim_date")
        before_dates = {row[0] for row in cur.fetchall()}
        cur.execute("SELECT instrument_id FROM dim_instrument")
        before_instruments = {row[0] for row in cur.fetchall()}

    yield

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        symbols_by_market: dict[str, list[str]] = {}
        for market, table in MARKET_TABLES.items():
            cur.execute(
                f"SELECT DISTINCT symbol FROM {table} WHERE sync_batch_id LIKE 'test-sync-%'"
            )
            symbols_by_market[market] = [row[0] for row in cur.fetchall()]
            cur.execute(f"DELETE FROM {table} WHERE sync_batch_id LIKE 'test-sync-%'")

        for market, symbols in symbols_by_market.items():
            if not symbols:
                continue
            cur.execute(
                """
                DELETE FROM fact_kline
                WHERE provider_id = 'sqlite'
                  AND instrument_id IN (
                      SELECT instrument_id FROM dim_instrument
                      WHERE market_id = %s AND symbol = ANY(%s)
                  )
                """,
                (market, symbols),
            )
            cur.execute(
                """
                DELETE FROM dim_instrument
                WHERE market_id = %s AND symbol = ANY(%s)
                """,
                (market, symbols),
            )
            for symbol in symbols:
                cur.execute(
                    "DELETE FROM etl_watermarks WHERE scope LIKE %s",
                    (f"kline:{market}:{symbol}:%",),
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
        cur.execute(
            "DELETE FROM etl_watermarks WHERE scope = 'news'",
        )
        cur.execute(
            """
            DELETE FROM fact_news
            WHERE source = 'unit-test' AND title LIKE %s
            """,
            ("TEST-NEWS-%",),
        )
        cur.execute(
            "DELETE FROM ods_news WHERE source = 'unit-test' AND title LIKE %s",
            ("TEST-NEWS-%",),
        )
        conn.commit()


def _seed_sqlite_db(
    tmp_path,
    a_share_symbol: str,
    fx_symbol: str | None = None,
    extra_rows: list[tuple] | None = None,
) -> str:
    db_path = tmp_path / "sync-seed.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE klines (
          market TEXT, symbol TEXT, period TEXT, time TEXT,
          open REAL, high REAL, low REAL, close REAL, volume REAL
        )
        """
    )
    rows = [
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
    ]
    if fx_symbol is not None:
        rows.append(
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
            )
        )
    rows.extend(extra_rows or [])
    conn.executemany(
        """
        INSERT INTO klines
          (market, symbol, period, time, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()
    return str(db_path)


def _insert_sqlite_row(db_path: str, row: tuple) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO klines
          (market, symbol, period, time, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        row,
    )
    conn.commit()
    conn.close()


def _watermark(dsn: str, scope: str) -> str | None:
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT last_value FROM etl_watermarks WHERE scope = %s",
            (scope,),
        )
        row = cur.fetchone()
    return row[0] if row else None


def test_first_run_syncs_all_klines_and_records_watermark(
    dsn, sync_cleanup, tmp_path
):
    a_share_symbol = _unique_symbol()
    fx_symbol = _unique_fx_symbol()
    db_path = _seed_sqlite_db(tmp_path, a_share_symbol, fx_symbol)
    batch_id = f"test-sync-{uuid.uuid4()}"

    stats = sync_incremental(dsn, db_path, batch_id=batch_id)

    assert stats["klines"]["a-share"]["ods"] == 2
    assert stats["klines"]["a-share"]["dwd"] == 2
    assert stats["klines"]["fx"]["ods"] == 1

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM ods_klines_a_share WHERE sync_batch_id = %s",
            (batch_id,),
        )
        assert cur.fetchone()[0] == 2
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

    scope = f"kline:a-share:{a_share_symbol}:d"
    assert _watermark(dsn, scope) is not None
    assert datetime.fromisoformat(_watermark(dsn, scope)) == datetime(
        2026, 1, 2, tzinfo=timezone.utc
    )


def test_second_run_syncs_only_new_rows(dsn, sync_cleanup, tmp_path):
    a_share_symbol = _unique_symbol()
    db_path = _seed_sqlite_db(tmp_path, a_share_symbol)

    first_stats = sync_incremental(
        dsn, db_path, batch_id=f"test-sync-{uuid.uuid4()}"
    )
    assert first_stats["klines"]["a-share"]["ods"] == 2

    _insert_sqlite_row(
        db_path,
        ("a-share", a_share_symbol, "d", "2026-01-03", 1.0, 2.0, 0.5, 1.7, 120.0),
    )
    second_stats = sync_incremental(
        dsn, db_path, batch_id=f"test-sync-{uuid.uuid4()}"
    )

    assert second_stats["klines"]["a-share"]["ods"] == 1
    # build_dwd 返回受影响行数：本次 ODS 共有 3 行（2 旧幂等更新 + 1 新插入）。
    assert second_stats["klines"]["a-share"]["dwd"] == 3

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)
            FROM fact_kline f
            JOIN dim_instrument i ON i.instrument_id = f.instrument_id
            WHERE f.provider_id = 'sqlite' AND i.symbol = %s
            """,
            (a_share_symbol,),
        )
        assert cur.fetchone()[0] == 3

    assert datetime.fromisoformat(
        _watermark(dsn, f"kline:a-share:{a_share_symbol}:d")
    ) == datetime(2026, 1, 3, tzinfo=timezone.utc)


def test_failed_run_rolls_back_and_keeps_watermark(dsn, sync_cleanup, tmp_path):
    a_share_symbol = _unique_symbol()
    db_path = _seed_sqlite_db(tmp_path, a_share_symbol)

    sync_incremental(dsn, db_path, batch_id=f"test-sync-{uuid.uuid4()}")
    before = _watermark(dsn, f"kline:a-share:{a_share_symbol}:d")

    _insert_sqlite_row(
        db_path,
        ("a-share", a_share_symbol, "d", "2026-01-03", 1.0, 2.0, 0.5, 1.7, 120.0),
    )
    _insert_sqlite_row(
        db_path,
        ("a-share", None, "d", "2026-01-04", 1.0, 2.0, 0.5, 1.8, 130.0),
    )

    with pytest.raises(psycopg.Error):
        sync_incremental(dsn, db_path, batch_id=f"test-sync-{uuid.uuid4()}")

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)
            FROM fact_kline f
            JOIN dim_instrument i ON i.instrument_id = f.instrument_id
            WHERE f.provider_id = 'sqlite' AND i.symbol = %s AND f.date_key = %s
            """,
            (a_share_symbol, "2026-01-03"),
        )
        assert cur.fetchone()[0] == 0
        cur.execute(
            """
            SELECT count(*)
            FROM ods_klines_a_share
            WHERE symbol = %s AND ts = '2026-01-03'
            """,
            (a_share_symbol,),
        )
        assert cur.fetchone()[0] == 0

    assert _watermark(dsn, f"kline:a-share:{a_share_symbol}:d") == before


def test_news_incremental_loads_only_new_items(dsn, sync_cleanup, tmp_path, monkeypatch):
    a_share_symbol = _unique_symbol()
    db_path = _seed_sqlite_db(tmp_path, a_share_symbol)
    suffix = uuid.uuid4().hex[:8]
    first_item = {
        "time": "08-01 09:00",
        "title": f"TEST-NEWS-{suffix}-1",
        "source": "unit-test",
        "tags": [],
        "sentiment": 0.1,
    }
    second_item = {
        "time": "08-02 09:00",
        "title": f"TEST-NEWS-{suffix}-2",
        "source": "unit-test",
        "tags": [],
        "sentiment": 0.2,
    }

    monkeypatch.setattr(macro_data, "NEWS_ITEMS", [first_item])
    first_stats = sync_incremental(
        dsn, db_path, batch_id=f"test-sync-{uuid.uuid4()}"
    )
    assert first_stats["news"] == 1

    monkeypatch.setattr(macro_data, "NEWS_ITEMS", [first_item, second_item])
    second_stats = sync_incremental(
        dsn, db_path, batch_id=f"test-sync-{uuid.uuid4()}"
    )
    assert second_stats["news"] == 1

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM ods_news WHERE source = 'unit-test' AND title LIKE %s",
            ("TEST-NEWS-%",),
        )
        assert cur.fetchone()[0] == 2


def test_upsert_ods_reuses_connection_transaction(dsn, sync_cleanup):
    row = {
        "provider": "sqlite",
        "market": "a-share",
        "symbol": _unique_symbol(),
        "interval": "d",
        "ts": "2026-08-23",
        "open": 1.0,
        "high": 2.0,
        "low": 0.5,
        "close": 1.5,
        "volume": 100.0,
        "sync_batch_id": f"test-sync-{uuid.uuid4()}",
    }

    with psycopg.connect(dsn) as conn:
        upsert_ods_rows(dsn, "a-share", [row], conn=conn)
        with psycopg.connect(dsn) as other:
            with other.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM ods_klines_a_share WHERE symbol = %s",
                    (row["symbol"],),
                )
                assert cur.fetchone()[0] == 0
        conn.commit()

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM ods_klines_a_share WHERE symbol = %s",
            (row["symbol"],),
        )
        assert cur.fetchone()[0] == 1
