"""External sync orchestration tests."""
from __future__ import annotations

import uuid
from typing import Callable, NamedTuple

import psycopg
import pytest

from etl.db import connect
from etl.sync_external import (
    get_watermark,
    iso_week,
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
            "ods_cn_daily_metrics",
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
               OR scope = 'cn-daily:metrics' OR scope LIKE 'cn-daily:metrics:%'
               OR scope LIKE 'test:%'
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


# --- 周粒度水位线判据：sec / worldbank / akshare 三个源共用一份回归保护 -------
#
# 三个源的判据曾各自复制一份，只有 worldbank 被测试覆盖：把 sec / akshare 的
# 判据改回旧的 `is not None`（永久跳过）时全套测试仍然全绿。此处用同一组参数化
# 用例覆盖三个源。

SEC_CIKS = ("0000320193", "0001045810", "0000789019", "0001318605")
WORLDBANK_CODES = ("NY.GDP.MKTP.CD", "FP.CPI.TOTL.ZG", "FR.INR.LEND")
AKSHARE_FINANCE_SYMBOLS = ("600519", "000001", "300750", "601318", "600036")


class _WeeklySourceCase(NamedTuple):
    run: Callable[..., dict]
    scopes: list[str]
    calls: list[str]
    expected_calls: int


def _record(calls: list[str], key: str, payload):
    calls.append(key)
    return payload


def _weekly_source_case(name: str, monkeypatch) -> _WeeklySourceCase:
    """构造指定源的单次采集调用记录器，返回 (入口, 水位线 scope, 调用记录, 首次调用数)。"""
    from etl.sources import akshare_cn, sec_edgar, worldbank
    from etl.sync_external import sync_akshare, sync_sec

    calls: list[str] = []

    if name == "sec":
        monkeypatch.setattr(
            sec_edgar,
            "fetch_submissions",
            lambda cik: _record(
                calls,
                cik,
                {"cik": cik, "name": "X", "tickers": [], "exchanges": []},
            ),
        )
        monkeypatch.setattr(
            sec_edgar,
            "fetch_company_facts",
            lambda cik: _record(calls, cik, {"cik": cik, "facts": {}}),
        )
        return _WeeklySourceCase(
            sync_sec,
            [f"sec:cik:{cik}" for cik in SEC_CIKS],
            calls,
            len(SEC_CIKS) * 2,
        )

    if name == "akshare":
        monkeypatch.setattr(
            akshare_cn,
            "fetch_financials",
            lambda symbol: _record(calls, symbol, []),
        )
        monkeypatch.setattr(akshare_cn, "fetch_lhb", lambda _start, _end: [])
        return _WeeklySourceCase(
            sync_akshare,
            [f"akshare:finance:{symbol}" for symbol in AKSHARE_FINANCE_SYMBOLS],
            calls,
            len(AKSHARE_FINANCE_SYMBOLS),
        )

    monkeypatch.setattr(
        worldbank,
        "fetch_indicator",
        lambda _country, code: _record(
            calls,
            code,
            [
                {
                    "country": {"id": "CN"},
                    "indicator": {"id": code, "value": code},
                    "date": "2024",
                    "value": 1.0,
                }
            ],
        ),
    )
    return _WeeklySourceCase(
        sync_worldbank,
        [f"worldbank:series:{code}" for code in WORLDBANK_CODES],
        calls,
        len(WORLDBANK_CODES),
    )


def test_already_synced_this_week_compares_week_not_existence(
    dsn, cleanup_external_sync
):
    """共享判据：只有「水位线 == 本周」才算已同步；存在但过期不算。"""
    from etl.sync_external import _already_synced_this_week

    with connect(dsn) as conn:
        assert _already_synced_this_week(conn, "test:weekly:missing", iso_week()) is False
        set_watermark(conn, "test:weekly:stale", "2020-W01")
        assert _already_synced_this_week(conn, "test:weekly:stale", iso_week()) is False
        set_watermark(conn, "test:weekly:current", iso_week())
        assert _already_synced_this_week(conn, "test:weekly:current", iso_week()) is True
        conn.commit()


@pytest.mark.parametrize("name", ["sec", "worldbank", "akshare"])
def test_weekly_source_skips_within_same_week(
    dsn, cleanup_external_sync, monkeypatch, name
):
    case = _weekly_source_case(name, monkeypatch)
    batch = f"test-extsync-{uuid.uuid4()}"

    with connect(dsn) as conn:
        case.run(conn, batch_id=batch)
        conn.commit()
    assert len(case.calls) == case.expected_calls  # 首次全采

    case.calls.clear()
    with connect(dsn) as conn:
        case.run(conn, batch_id=batch)
        conn.commit()
    assert case.calls == []  # 同一周内全部跳过

    with connect(dsn) as conn:
        for scope in case.scopes:
            assert get_watermark(conn, scope) == iso_week()


@pytest.mark.parametrize("name", ["sec", "worldbank", "akshare"])
def test_weekly_source_resyncs_when_watermark_is_stale(
    dsn, cleanup_external_sync, monkeypatch, name
):
    """水位线不是本周时必须重采：旧判据 `is not None` 会永久跳过且无声无息。"""
    case = _weekly_source_case(name, monkeypatch)
    batch = f"test-extsync-{uuid.uuid4()}"

    with connect(dsn) as conn:
        for scope in case.scopes:
            set_watermark(conn, scope, "2020-W01")
        conn.commit()

    with connect(dsn) as conn:
        case.run(conn, batch_id=batch)
        conn.commit()

    assert len(case.calls) == case.expected_calls  # 水位线已过期，必须重新抓取
    with connect(dsn) as conn:
        for scope in case.scopes:
            assert get_watermark(conn, scope) == iso_week()  # 推进到当前周


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
    from etl.sync_external import metrics_scope, set_watermark, sync_share_structure

    monkeypatch.setattr("etl.sync_external._a_share_universe", lambda: ["600519"])
    monkeypatch.setattr(
        eastmoney_cn,
        "fetch_share_structure",
        lambda _code: [
            {"变更日期": "2026-05-28", "总股本": 1250081601, "已流通股份": 1250081601}
        ],
    )

    with connect(dsn) as conn:
        set_watermark(conn, metrics_scope("600519"), "2026-09-01")
        conn.commit()

    with connect(dsn) as conn:
        sync_share_structure(conn, batch_id=f"test-extsync-{uuid.uuid4()}")
        conn.commit()

    with connect(dsn) as conn:
        # 股本变更日期早于已处理区间，该标的的水位线必须回退以重算
        assert get_watermark(conn, metrics_scope("600519")) == "2026-05-28"


def test_sync_share_structure_rewinds_to_new_backfill_not_existing_history(
    dsn, cleanup_external_sync, monkeypatch
):
    from etl.sources import eastmoney_cn
    from etl.sync_external import metrics_scope, set_watermark, sync_share_structure

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
        set_watermark(conn, metrics_scope("600519"), "2026-09-01")
        conn.commit()

    with connect(dsn) as conn:
        sync_share_structure(conn, batch_id=f"test-extsync-{uuid.uuid4()}")
        conn.commit()

    with connect(dsn) as conn:
        # 回退目标应是本次新增的 2026-05-28，而非已存在的远古 1990-01-01
        assert get_watermark(conn, metrics_scope("600519")) == "2026-05-28"


def test_sync_share_structure_rewinds_only_the_backfilled_symbol(
    dsn, cleanup_external_sync, monkeypatch
):
    """股本回填只回退该标的的水位线，其他标的（尤其全市场 5000+）不受影响。

    全局水位线被拆除后，"某只标的回填导致全市场重算"是新的失效向量。
    """
    from etl.sources import eastmoney_cn
    from etl.sync_external import metrics_scope, set_watermark, sync_share_structure

    monkeypatch.setattr(
        "etl.sync_external._a_share_universe", lambda: ["600519", "000001"]
    )

    def _fetch(code: str) -> list[dict]:
        if code == "600519":
            return [
                {"变更日期": "2026-05-28", "总股本": 1250081601, "已流通股份": 1250081601}
            ]
        return [
            {"变更日期": "2026-09-10", "总股本": 1000, "已流通股份": 1000}
        ]

    monkeypatch.setattr(eastmoney_cn, "fetch_share_structure", _fetch)

    with connect(dsn) as conn:
        set_watermark(conn, metrics_scope("600519"), "2026-09-01")
        set_watermark(conn, metrics_scope("000001"), "2026-09-01")
        conn.commit()

    with connect(dsn) as conn:
        sync_share_structure(conn, batch_id=f"test-extsync-{uuid.uuid4()}")
        conn.commit()

    with connect(dsn) as conn:
        assert get_watermark(conn, metrics_scope("600519")) == "2026-05-28"
        assert get_watermark(conn, metrics_scope("000001")) == "2026-09-01"
