"""External sync orchestration tests."""
from __future__ import annotations

import uuid

import psycopg
import pytest

from etl.db import connect
from etl.sync_external import (
    get_watermark,
    set_watermark,
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
            "ods_cn_balance",
            "ods_cn_share_structure",
        ):
            cur.execute(f"DELETE FROM {table} WHERE sync_batch_id LIKE 'test-extsync-%'")
        cur.execute(
            """
            DELETE FROM fact_indicator WHERE indicator_id IN (
              SELECT indicator_id FROM dim_indicator
              WHERE source IN ('crypto','macro','sec','cn-finance','cn-lhb','cn-balance','cn-daily')
            )
            """
        )
        cur.execute(
            """
            DELETE FROM dim_indicator
            WHERE source IN ('crypto','macro','sec','cn-finance','cn-lhb','cn-balance','cn-daily')
            """
        )
        cur.execute(
            """
            DELETE FROM etl_watermarks
            WHERE scope LIKE 'coingecko:%' OR scope LIKE 'sec:%'
               OR scope LIKE 'worldbank:%' OR scope LIKE 'akshare:%'
               OR scope LIKE 'cn-balance:%' OR scope LIKE 'cn-share:%'
               OR scope = 'cn-daily:metrics'
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
    monkeypatch.setattr("etl.sync_external._a_share_universe", lambda: [])
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
    monkeypatch.setattr("etl.sync_external._a_share_universe", lambda: [])

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


def test_sync_worldbank_resyncs_when_watermark_is_stale(
    dsn, cleanup_external_sync, monkeypatch
):
    from datetime import date

    from etl.sources import worldbank

    calls: list[str] = []

    def _fake(_country: str, code: str) -> list[dict]:
        calls.append(code)
        return [{"date": "2024", "value": 1.0, "indicator_name": code}]

    monkeypatch.setattr(worldbank, "fetch_indicator", _fake)
    batch = f"test-extsync-{uuid.uuid4()}"
    scopes = [
        f"worldbank:series:{code}"
        for code in ("NY.GDP.MKTP.CD", "FP.CPI.TOTL.ZG", "FR.INR.LEND")
    ]

    # 显式把水位线设成很早的周，模拟「跨周」：旧实现会因 is not None 永久跳过，
    # 从而暴露「跨周不重采」的缺陷。
    with connect(dsn) as conn:
        for scope in scopes:
            set_watermark(conn, scope, "2020-W01")
        conn.commit()

    with connect(dsn) as conn:
        sync_worldbank(conn, batch_id=batch)
        conn.commit()

    assert len(calls) == 3  # 水位线已过期，必须重新抓取

    iso = date.today().isocalendar()
    expected = f"{iso.year}-W{iso.week:02d}"
    with connect(dsn) as conn:
        for scope in scopes:
            assert get_watermark(conn, scope) == expected  # 水位线被推进到当前周


def test_sync_balance_sheet_tolerates_single_symbol_failure(
    dsn, cleanup_external_sync, monkeypatch
):
    from etl.sources import sina_cn
    from etl.sync_external import sync_balance_sheet

    monkeypatch.setattr(
        "etl.sync_external._a_share_universe", lambda: ["600519", "000001"]
    )

    def _fetch(code: str) -> list[dict]:
        if code == "000001":
            raise RuntimeError("network down")
        return [{"报告日": "20260630", "资产总计": 100.0}]

    monkeypatch.setattr(sina_cn, "fetch_balance_sheet", _fetch)

    with connect(dsn) as conn:
        stats = sync_balance_sheet(conn, batch_id=f"test-extsync-{uuid.uuid4()}")
        conn.commit()

    assert stats["rows"] == 1
    assert stats["failed"] == 1  # 000001 失败但不影响 600519


def test_sync_share_structure_rewinds_metrics_watermark_on_backfill(
    dsn, cleanup_external_sync, monkeypatch
):
    from etl.sources import eastmoney_cn
    from etl.sync_external import METRICS_SCOPE, set_watermark, sync_share_structure

    monkeypatch.setattr("etl.sync_external._a_share_universe", lambda: ["600519"])
    monkeypatch.setattr(
        eastmoney_cn,
        "fetch_share_structure",
        lambda _code: [
            {"变更日期": "2026-05-28", "总股本": 1250081601, "已流通股份": 1250081601}
        ],
    )

    with connect(dsn) as conn:
        set_watermark(conn, METRICS_SCOPE, "2026-09-01")
        conn.commit()

    with connect(dsn) as conn:
        sync_share_structure(conn, batch_id=f"test-extsync-{uuid.uuid4()}")
        conn.commit()

    with connect(dsn) as conn:
        # 股本变更日期早于已处理区间，水位线必须回退以重算
        assert get_watermark(conn, METRICS_SCOPE) == "2026-05-28"


def test_sync_share_structure_rewinds_to_new_backfill_not_existing_history(
    dsn, cleanup_external_sync, monkeypatch
):
    from etl.sources import eastmoney_cn
    from etl.sync_external import METRICS_SCOPE, set_watermark, sync_share_structure

    monkeypatch.setattr("etl.sync_external._a_share_universe", lambda: ["600519"])

    # 表中已有一条远古记录：本次全量重抓仍会返回它，但不该把水位线打回远古
    with connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ods_cn_share_structure
              (symbol, change_date, total_shares, float_shares, raw_payload, sync_batch_id)
            VALUES ('600519', '1990-01-01', 100, 100, '{}', 'test-extsync-preseed')
            ON CONFLICT DO NOTHING
            """
        )
        conn.commit()

    monkeypatch.setattr(
        eastmoney_cn,
        "fetch_share_structure",
        lambda _code: [
            {"变更日期": "1990-01-01", "总股本": 100, "已流通股份": 100},
            {"变更日期": "2026-05-28", "总股本": 1250081601, "已流通股份": 1250081601},
        ],
    )

    with connect(dsn) as conn:
        set_watermark(conn, METRICS_SCOPE, "2026-09-01")
        conn.commit()

    with connect(dsn) as conn:
        sync_share_structure(conn, batch_id=f"test-extsync-{uuid.uuid4()}")
        conn.commit()

    with connect(dsn) as conn:
        # 回退目标应是本次新增的 2026-05-28，而非已存在的远古 1990-01-01
        assert get_watermark(conn, METRICS_SCOPE) == "2026-05-28"
