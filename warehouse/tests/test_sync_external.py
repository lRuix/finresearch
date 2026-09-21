"""External sync orchestration tests."""
from __future__ import annotations

import uuid

import psycopg
import pytest

from etl.db import connect
from etl.sync_external import (
    get_watermark,
    sync_coingecko,
    sync_external,
    sync_worldbank,
)


@pytest.fixture
def cleanup_external_sync(dsn):
    yield
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        for table in (
            "ods_crypto_meta",
            "ods_sec_submissions",
            "ods_sec_facts",
            "ods_macro_indicators",
            "ods_cn_financials",
            "ods_cn_lhb",
        ):
            cur.execute(f"DELETE FROM {table} WHERE sync_batch_id LIKE 'test-extsync-%'")
        cur.execute(
            """
            DELETE FROM fact_indicator WHERE indicator_id IN (
              SELECT indicator_id FROM dim_indicator
              WHERE source IN ('crypto','macro','sec','cn-finance','cn-lhb')
            )
            """
        )
        cur.execute(
            """
            DELETE FROM dim_indicator
            WHERE source IN ('crypto','macro','sec','cn-finance','cn-lhb')
            """
        )
        cur.execute(
            """
            DELETE FROM etl_watermarks
            WHERE scope LIKE 'coingecko:%' OR scope LIKE 'sec:%'
               OR scope LIKE 'worldbank:%' OR scope LIKE 'akshare:%'
            """
        )
        conn.commit()


def _fake_markets(_ids: list[str]) -> list[dict]:
    return [
        {
            "id": "bitcoin",
            "symbol": "btc",
            "name": "Bitcoin",
            "current_price": 79000.0,
            "market_cap": 1.5e12,
            "total_volume": 5.0e10,
            "high_24h": 80000.0,
            "low_24h": 78000.0,
            "market_cap_rank": 1,
        }
    ]


def test_sync_coingecko_first_run_then_incremental(
    dsn, cleanup_external_sync, monkeypatch
):
    from etl.sources import coingecko

    monkeypatch.setattr(coingecko, "fetch_markets", _fake_markets)
    with connect(dsn) as conn:
        stats = sync_coingecko(conn, batch_id=f"test-extsync-{uuid.uuid4()}")
        conn.commit()
    assert stats["rows"] == 1

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM ods_crypto_meta WHERE coin_id = 'bitcoin'")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT count(*) FROM fact_indicator")
        assert cur.fetchone()[0] == 3

    with connect(dsn) as conn:
        second = sync_coingecko(conn, batch_id=f"test-extsync-{uuid.uuid4()}")
        conn.commit()
    assert second["rows"] == 0  # 同一天快照已存在，增量跳过


def test_sync_external_failed_source_does_not_block_others(
    dsn, cleanup_external_sync, monkeypatch
):
    from etl.sources import coingecko, worldbank

    monkeypatch.setattr(coingecko, "fetch_markets", _fake_markets)

    def boom(_country: str, _code: str):
        raise RuntimeError("network down")

    monkeypatch.setattr(worldbank, "fetch_indicator", boom)
    stats = sync_external(dsn, batch_id=f"test-extsync-{uuid.uuid4()}")
    assert stats["coingecko"]["status"] == "ok"
    assert stats["worldbank"]["status"] == "error"


def test_sync_external_refreshes_indicator_dws(dsn, cleanup_external_sync, monkeypatch):
    from etl.sources import coingecko, worldbank, akshare_cn, sec_edgar

    monkeypatch.setattr(coingecko, "fetch_markets", _fake_markets)
    monkeypatch.setattr(worldbank, "fetch_indicator", lambda _c, _i: [])
    monkeypatch.setattr(akshare_cn, "fetch_financials", lambda _s: [])
    monkeypatch.setattr(akshare_cn, "fetch_lhb", lambda _a, _b: [])

    def _no_sec(_cik):
        return {"cik": _cik, "facts": {}}

    monkeypatch.setattr(sec_edgar, "fetch_submissions", lambda _cik: {"cik": _cik, "name": "X", "tickers": [], "exchanges": []})
    monkeypatch.setattr(sec_edgar, "fetch_company_facts", _no_sec)

    sync_external(dsn, batch_id=f"test-extsync-{uuid.uuid4()}")
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM dws_indicator_daily")
        assert cur.fetchone()[0] == 3


def test_get_watermark_missing_scope_returns_none(dsn):
    with psycopg.connect(dsn) as conn:
        assert get_watermark(conn, "coingecko:coin:does-not-exist") is None


def test_iso_week_formats_with_zero_padded_week():
    from datetime import date

    from etl.sync_external import iso_week

    assert iso_week(date(2026, 9, 22)) == "2026-W39"
    assert iso_week(date(2026, 1, 5)) == "2026-W02"


def test_sync_worldbank_skips_within_same_week(dsn, cleanup_external_sync, monkeypatch):
    from etl.sources import worldbank

    calls: list[str] = []

    def _fake(_country: str, code: str) -> list[dict]:
        calls.append(code)
        return [{"date": "2024", "value": 1.0, "indicator_name": code}]

    monkeypatch.setattr(worldbank, "fetch_indicator", _fake)
    batch = f"test-extsync-{uuid.uuid4()}"

    with connect(dsn) as conn:
        first = sync_worldbank(conn, batch_id=batch)
        conn.commit()
    assert len(calls) == 3  # 三个指标各取一次

    calls.clear()
    with connect(dsn) as conn:
        second = sync_worldbank(conn, batch_id=batch)
        conn.commit()
    assert calls == []  # 同一周内全部跳过
    assert second["rows"] == 0
