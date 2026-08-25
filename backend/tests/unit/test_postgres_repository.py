"""PostgreSQL repository tests against the warehouse_test database."""
from __future__ import annotations

import psycopg
import pytest

from domain.models import Instrument, KlineRow
from infrastructure.repository.postgres import PostgresMarketDataRepository


DSN = "postgresql://warehouse:warehouse@127.0.0.1:5432/warehouse_test"
SYMBOL = "TEST-PG-600519"


@pytest.fixture
def repo():
    return PostgresMarketDataRepository(DSN)


@pytest.fixture
def seed_kline():
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO dim_market (market_id, name, region, currency)
            VALUES ('a-share', 'A-Share', 'CN', 'CNY')
            ON CONFLICT DO NOTHING
            """
        )
        cur.execute(
            """
            INSERT INTO dim_instrument (market_id, symbol, name)
            VALUES ('a-share', %s, 'TEST')
            ON CONFLICT (market_id, symbol) DO NOTHING
            RETURNING instrument_id
            """,
            (SYMBOL,),
        )
        row = cur.fetchone()
        instrument_id = row[0] if row else None
        if instrument_id is None:
            cur.execute(
                """
                SELECT instrument_id FROM dim_instrument
                WHERE market_id = 'a-share' AND symbol = %s
                """,
                (SYMBOL,),
            )
            instrument_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO fact_kline (
              market_id, instrument_id, provider_id, date_key, period,
              time, open, high, low, close, volume
            ) VALUES
              ('a-share', %s, 'backend', '2026-08-01', 'd',
               '2026-08-01T00:00:00+00:00', 10, 11, 9, 10.5, 100),
              ('a-share', %s, 'backend', '2026-08-02', 'd',
               '2026-08-02T00:00:00+00:00', 10.5, 12, 10, 11.5, 120)
            ON CONFLICT (market_id, instrument_id, period, time) DO UPDATE SET
              open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
              close = EXCLUDED.close, volume = EXCLUDED.volume
            """,
            (instrument_id, instrument_id),
        )
        conn.commit()

    yield
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM fact_kline WHERE provider_id = 'backend'
              AND instrument_id IN (
                SELECT instrument_id FROM dim_instrument WHERE symbol = %s)
            """,
            (SYMBOL,),
        )
        cur.execute("DELETE FROM dim_instrument WHERE symbol = %s", (SYMBOL,))
        cur.execute("DELETE FROM backend_evaluations WHERE symbol LIKE 'TEST-PG-%'")
        cur.execute("DELETE FROM backend_market_snapshots WHERE symbol LIKE 'TEST-PG-%'")
        conn.commit()


def test_get_klines_reads_fact_kline(repo, seed_kline):
    rows = repo.get_klines("a-share", SYMBOL, "d")
    assert len(rows) == 2
    assert rows[0].time == "2026-08-01T00:00:00+00:00"
    assert rows[0].open == 10
    assert rows[0].close == 10.5
    assert rows[1].close == 11.5
    assert [row.time for row in rows] == sorted(row.time for row in rows)


def test_get_klines_filters_by_time_range(repo, seed_kline):
    rows = repo.get_klines("a-share", SYMBOL, "d", start="2026-08-02")
    assert len(rows) == 1
    assert rows[0].time == "2026-08-02T00:00:00+00:00"


def test_get_klines_empty_when_missing(repo, seed_kline):
    assert repo.get_klines("a-share", "TEST-PG-NOPE", "d") == []


def test_save_and_get_evaluation(repo, seed_kline):
    repo.save_evaluation("2026-08-25", "all", "TEST-PG-EVAL", 88.5, {"k": "v"})
    result = repo.get_evaluation("2026-08-25", "all", "TEST-PG-EVAL")
    assert result == {"k": "v"}
    repo.save_evaluation("2026-08-25", "all", "TEST-PG-EVAL", 90.0, {"k": "v2"})
    assert repo.get_evaluation("2026-08-25", "all", "TEST-PG-EVAL") == {"k": "v2"}


def test_upsert_and_get_snapshot(repo, seed_kline):
    items = [
        {"symbol": "TEST-PG-SNAP", "name": "S", "turnover": 1.0, "market_cap": 2.0, "rank": 1},
        {"symbol": "TEST-PG-SNAP2", "name": "S2", "turnover": 3.0, "market_cap": 4.0, "rank": 2},
    ]
    repo.upsert_snapshot("2026-08-25", "a-share", items)
    snap = repo.get_snapshot("2026-08-25", "a-share")
    assert len(snap) == 2
    assert snap[0]["rank"] <= snap[1]["rank"]


def test_sync_methods_raise_not_implemented(repo):
    with pytest.raises(NotImplementedError):
        repo.upsert_klines("a-share", "X", "d", [KlineRow("2026-08-01", 1, 2, 0.5, 1.5, 10)])
    with pytest.raises(NotImplementedError):
        repo.upsert_instruments([Instrument(market="a-share", symbol="X", name="X", currency="CNY")])
    with pytest.raises(NotImplementedError):
        repo.set_watermark("a-share", "X", "d", "2026-08-01")
