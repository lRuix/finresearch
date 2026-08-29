"""Incremental sync tests (direct market collection, network mocked)."""
from __future__ import annotations

from datetime import datetime, timezone
import uuid

import psycopg
import pytest

from etl.load_ods import MARKET_TABLES, upsert_ods_rows
from etl.migrate_seed import _new_batch_id
from etl.sync_incremental import sync_incremental
from etl.sources import registry
from backend.infrastructure.datasources import macro_data


SYNC_SYMBOL_PREFIX = "TEST-SYNC-"


def _unique_symbol(prefix: str = SYNC_SYMBOL_PREFIX) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


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
        for market_id, table in MARKET_TABLES.items():
            cur.execute(
                f"SELECT DISTINCT symbol FROM {table} WHERE sync_batch_id LIKE 'test-sync-%'"
            )
            symbols_by_market[market_id] = [row[0] for row in cur.fetchall()]
            cur.execute(f"DELETE FROM {table} WHERE sync_batch_id LIKE 'test-sync-%'")
        for market_id, symbols in symbols_by_market.items():
            if not symbols:
                continue
            cur.execute(
                """
                DELETE FROM fact_kline
                WHERE provider_id = 'market'
                  AND instrument_id IN (
                      SELECT instrument_id FROM dim_instrument
                      WHERE market_id = %s AND symbol = ANY(%s)
                  )
                """,
                (market_id, symbols),
            )
            cur.execute(
                """
                DELETE FROM dim_instrument
                WHERE market_id = %s AND symbol = ANY(%s)
                """,
                (market_id, symbols),
            )
            for symbol in symbols:
                cur.execute(
                    "DELETE FROM etl_watermarks WHERE scope LIKE %s",
                    (f"kline:{market_id}:{symbol}:%",),
                )
        cur.execute(
            """
            DELETE FROM dim_provider
            WHERE provider_id = 'market' AND provider_id != ALL(%s)
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
        cur.execute("DELETE FROM etl_watermarks WHERE scope = 'news'")
        cur.execute(
            "DELETE FROM fact_news WHERE source = 'unit-test' AND title LIKE %s",
            ("TEST-NEWS-%",),
        )
        cur.execute(
            "DELETE FROM ods_news WHERE source = 'unit-test' AND title LIKE %s",
            ("TEST-NEWS-%",),
        )
        conn.commit()


def _kline_row(day: str, close: float) -> dict:
    return {
        "time": day,
        "open": 1.0,
        "high": 2.0,
        "low": 0.5,
        "close": close,
        "volume": 100.0,
    }


def _fake_market(a_share_symbol: str, rows: list[dict]):
    def discover(market_id: str) -> list[dict]:
        if market_id == "a-share":
            return [
                {
                    "market": "a-share",
                    "symbol": a_share_symbol,
                    "name": "T",
                    "currency": "CNY",
                }
            ]
        return []

    def fetch(market_id: str, symbol: str, period: str, start=None, end=None):
        if market_id != "a-share" or symbol != a_share_symbol:
            return []
        return [row for row in rows if start is None or row["time"] >= start]

    return discover, fetch


def _watermark(dsn: str, scope: str) -> str | None:
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT last_value FROM etl_watermarks WHERE scope = %s",
            (scope,),
        )
        row = cur.fetchone()
    return row[0] if row else None


def test_first_run_collects_new_symbols(dsn, sync_cleanup, monkeypatch):
    a_share_symbol = _unique_symbol()
    discover, fetch = _fake_market(
        a_share_symbol, [_kline_row("2026-08-01", 1.5), _kline_row("2026-08-02", 1.6)]
    )
    monkeypatch.setattr(registry, "discover_instruments", discover)
    monkeypatch.setattr(registry, "fetch_klines", fetch)

    stats = sync_incremental(dsn, batch_id=f"test-sync-{uuid.uuid4()}")

    assert stats["klines"]["a-share"]["ods"] == 2
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)
            FROM fact_kline f
            JOIN dim_instrument i ON i.instrument_id = f.instrument_id
            WHERE f.provider_id = 'market' AND i.symbol = %s
            """,
            (a_share_symbol,),
        )
        assert cur.fetchone()[0] == 2
    assert datetime.fromisoformat(
        _watermark(dsn, f"kline:a-share:{a_share_symbol}:d")
    ) == datetime(2026, 8, 2, tzinfo=timezone.utc)


def test_second_run_syncs_only_new_rows(dsn, sync_cleanup, monkeypatch):
    a_share_symbol = _unique_symbol()
    rows = [_kline_row("2026-08-01", 1.5), _kline_row("2026-08-02", 1.6)]
    discover, fetch = _fake_market(a_share_symbol, rows)
    monkeypatch.setattr(registry, "discover_instruments", discover)
    monkeypatch.setattr(registry, "fetch_klines", fetch)

    sync_incremental(dsn, batch_id=f"test-sync-{uuid.uuid4()}")

    rows.append(_kline_row("2026-08-03", 1.7))
    second_stats = sync_incremental(dsn, batch_id=f"test-sync-{uuid.uuid4()}")

    assert second_stats["klines"]["a-share"]["ods"] == 1
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)
            FROM fact_kline f
            JOIN dim_instrument i ON i.instrument_id = f.instrument_id
            WHERE f.provider_id = 'market' AND i.symbol = %s
            """,
            (a_share_symbol,),
        )
        assert cur.fetchone()[0] == 3


def test_fx_rows_map_rate_fields(dsn, sync_cleanup, monkeypatch):
    fx_symbol = "USDCNY=X"
    rows = [
        {
            "time": "2026-08-01",
            "base": "USD",
            "quote": "CNY",
            "rate": 7.2,
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 7.2,
            "volume": 0.0,
        },
        {
            "time": "2026-08-02",
            "base": "USD",
            "quote": "CNY",
            "rate": 7.25,
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 7.25,
            "volume": 0.0,
        },
    ]

    def discover(market_id: str) -> list[dict]:
        if market_id == "fx":
            return [
                {
                    "market": "fx",
                    "symbol": fx_symbol,
                    "name": "USD/CNY",
                    "currency": "CNY",
                }
            ]
        return []

    def fetch(market_id: str, symbol: str, period: str, start=None, end=None):
        if market_id != "fx" or symbol != fx_symbol:
            return []
        return [row for row in rows if start is None or row["time"] >= start]

    monkeypatch.setattr(registry, "discover_instruments", discover)
    monkeypatch.setattr(registry, "fetch_klines", fetch)

    stats = sync_incremental(
        dsn, batch_id=f"test-sync-{uuid.uuid4()}", markets=("fx",)
    )

    assert stats["klines"]["fx"]["ods"] == 2
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT base_currency, quote_currency, close_rate, open_rate, high_rate, low_rate
            FROM ods_klines_fx
            WHERE provider = 'market' AND symbol = %s
            ORDER BY ts
            """,
            (fx_symbol,),
        )
        rows = cur.fetchall()
        assert len(rows) == 2
        assert rows[-1] == ("USD", "CNY", 7.25, 1.0, 2.0, 0.5)
        cur.execute(
            """
            SELECT count(*)
            FROM fact_kline f
            JOIN dim_instrument i ON i.instrument_id = f.instrument_id
            WHERE f.provider_id = 'market' AND i.market_id = 'fx' AND i.symbol = %s
            """,
            (fx_symbol,),
        )
        assert cur.fetchone()[0] == 2


def test_failed_run_rolls_back_and_keeps_watermark(dsn, sync_cleanup, monkeypatch):
    a_share_symbol = _unique_symbol()
    discover, fetch = _fake_market(a_share_symbol, [_kline_row("2026-08-01", 1.5)])
    monkeypatch.setattr(registry, "discover_instruments", discover)
    monkeypatch.setattr(registry, "fetch_klines", fetch)
    sync_incremental(dsn, batch_id=f"test-sync-{uuid.uuid4()}")
    before = _watermark(dsn, f"kline:a-share:{a_share_symbol}:d")

    discover2, fetch2 = _fake_market(
        a_share_symbol, [_kline_row("2026-08-02", 1.6)]
    )
    monkeypatch.setattr(registry, "discover_instruments", discover2)
    monkeypatch.setattr(registry, "fetch_klines", fetch2)

    def boom(*args, **kwargs):
        raise RuntimeError("dwd build failed")

    monkeypatch.setattr("etl.sync_incremental.build_dwd", boom)
    with pytest.raises(RuntimeError):
        sync_incremental(dsn, batch_id=f"test-sync-{uuid.uuid4()}")

    assert _watermark(dsn, f"kline:a-share:{a_share_symbol}:d") == before
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)
            FROM fact_kline f
            JOIN dim_instrument i ON i.instrument_id = f.instrument_id
            WHERE f.provider_id = 'market' AND i.symbol = %s AND f.date_key = '2026-08-02'
            """,
            (a_share_symbol,),
        )
        assert cur.fetchone()[0] == 0


def test_news_incremental_loads_only_new_items(dsn, sync_cleanup, monkeypatch):
    a_share_symbol = _unique_symbol()
    discover, fetch = _fake_market(a_share_symbol, [_kline_row("2026-08-01", 1.5)])
    monkeypatch.setattr(registry, "discover_instruments", discover)
    monkeypatch.setattr(registry, "fetch_klines", fetch)
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
    first_stats = sync_incremental(dsn, batch_id=f"test-sync-{uuid.uuid4()}")
    assert first_stats["news"] == 1

    monkeypatch.setattr(macro_data, "NEWS_ITEMS", [first_item, second_item])
    second_stats = sync_incremental(dsn, batch_id=f"test-sync-{uuid.uuid4()}")
    assert second_stats["news"] == 1

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM ods_news WHERE source = 'unit-test' AND title LIKE %s",
            ("TEST-NEWS-%",),
        )
        assert cur.fetchone()[0] == 2


def test_ods_writes_native_raw_payload(dsn, sync_cleanup, monkeypatch):
    symbol = _unique_symbol()
    native = [{
        "time": "2026-08-29",
        "open": 1.0,
        "high": 2.0,
        "low": 0.5,
        "close": 1.5,
        "volume": 100.0,
        "amount": 200.0,
        "source_specific": "keep-me",
    }]

    def discover(market_id):
        if market_id == "a-share":
            return [{"symbol": symbol, "name": "T", "market": "a-share", "currency": "CNY"}]
        return []

    def fetch(market_id, sym, period="d", start=None, end=None, limit=1000):
        if market_id == "a-share" and sym == symbol:
            return native
        return []

    monkeypatch.setattr(registry, "discover_instruments", discover)
    monkeypatch.setattr(registry, "fetch_klines", fetch)
    sync_incremental(dsn, batch_id=f"test-sync-{uuid.uuid4()}", markets=("a-share",))

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT amount, raw_payload FROM ods_klines_a_share WHERE symbol = %s",
            (symbol,),
        )
        row = cur.fetchone()
    assert row[0] == 200.0
    assert row[1]["source_specific"] == "keep-me"


def test_upsert_ods_reuses_connection_transaction(dsn, sync_cleanup):
    row = {
        "provider": "market",
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
