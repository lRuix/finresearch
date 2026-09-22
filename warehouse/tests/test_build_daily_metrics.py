"""Daily A-share derived metrics tests."""
from __future__ import annotations

import uuid

import psycopg
import pytest

from etl.build_daily_metrics import build_daily_metrics, compute_rows, shares_as_of
from etl.db import connect
from etl.sync_external import get_watermark


TABLE = {
    "600519": (
        ["2025-09-01", "2026-05-28"],
        [(1252270215.0, 1252270215.0), (1250081601.0, 1250081601.0)],
    )
}

KLINES = [
    {"symbol": "600519", "trade_date": "2026-09-21", "close": 1252.57, "volume": 25017.0}
]


def test_shares_as_of_picks_latest_change_not_after_trade_date():
    assert shares_as_of(TABLE, "600519", "2026-06-30") == (1250081601.0, 1250081601.0)
    assert shares_as_of(TABLE, "600519", "2026-01-15") == (1252270215.0, 1252270215.0)


def test_shares_as_of_returns_none_before_first_change():
    assert shares_as_of(TABLE, "600519", "2025-01-01") is None


def test_shares_as_of_returns_none_for_unknown_symbol():
    assert shares_as_of(TABLE, "000001", "2026-09-21") is None


def test_compute_rows_turnover_matches_sina_reference():
    """600519 于 2026-09-21：新浪 turnover 实测 0.0020012（小数）= 0.20012%。"""
    rows = list(compute_rows(KLINES, TABLE))
    assert len(rows) == 1
    assert rows[0]["turnover_rate"] == pytest.approx(0.20012, rel=1e-3)
    assert rows[0]["market_cap"] == pytest.approx(1252.57 * 1250081601.0)


def test_compute_rows_skips_symbol_without_shares():
    klines = [{"symbol": "000001", "trade_date": "2026-09-21", "close": 10.0, "volume": 100.0}]
    assert list(compute_rows(klines, TABLE)) == []


def test_compute_rows_leaves_turnover_null_when_float_shares_missing():
    table = {"600519": (["2026-05-28"], [(1250081601.0, None)])}
    rows = list(compute_rows(KLINES, table))
    assert rows[0]["turnover_rate"] is None
    assert rows[0]["market_cap"] == pytest.approx(1252.57 * 1250081601.0)


# --- 入库级集成用例 ---------------------------------------------------------
#
# 水位线 scope 契约（本文件用字面量钉住命名，避免测试与实现同时漂移）：
#   增量水位线 = f"cn-daily:metrics:{symbol}"   （per-symbol，值为下一个待处理交易日）
#   旧全局水位线 = "cn-daily:metrics"           （已废弃，改造后必须被忽略）
SYMBOL_SYNCED = "TST900001"   # 已有水位线的标的
SYMBOL_BRAND_NEW = "TST900002"  # 全新标的（无任何水位线）
SYMBOLS = (SYMBOL_SYNCED, SYMBOL_BRAND_NEW)
TEST_DATES = ("2026-09-18", "2026-09-21")


def _metrics_scope(symbol: str) -> str:
    return f"cn-daily:metrics:{symbol}"


METRICS_SCOPES = [_metrics_scope(symbol) for symbol in SYMBOLS]


def _set_watermark(dsn: str, scope: str, value: str) -> None:
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO etl_watermarks (scope, last_value, updated_at)
            VALUES (%s, %s, now())
            ON CONFLICT (scope) DO UPDATE SET last_value = EXCLUDED.last_value
            """,
            (scope, value),
        )
        conn.commit()


def _seed_klines(
    dsn: str, symbol: str, dates: tuple[str, ...], close: float = 10.0, volume: float = 50000.0
) -> None:
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        for trade_date in dates:
            cur.execute(
                """
                INSERT INTO fact_kline
                  (market_id, instrument_id, provider_id, date_key, period, time,
                   open, high, low, close, volume)
                SELECT 'a-share', i.instrument_id, 'test-metrics', %s, 'd',
                       %s::timestamp AT TIME ZONE 'UTC', %s, %s, %s, %s, %s
                FROM dim_instrument i
                WHERE i.market_id = 'a-share' AND i.symbol = %s
                ON CONFLICT DO NOTHING
                """,
                (
                    trade_date,
                    f"{trade_date} 00:00:00",
                    close,
                    close,
                    close,
                    close,
                    volume,
                    symbol,
                ),
            )
        conn.commit()


def _seed_shares(
    dsn: str,
    symbol: str,
    change_date: str,
    total_shares: float,
    float_shares: float | None,
) -> None:
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ods_cn_share_structure
              (symbol, change_date, total_shares, float_shares, raw_payload, sync_batch_id)
            VALUES (%s, %s, %s, %s, '{}', 'test-metrics')
            ON CONFLICT (symbol, change_date) DO UPDATE SET
              total_shares = EXCLUDED.total_shares,
              float_shares = EXCLUDED.float_shares
            """,
            (symbol, change_date, total_shares, float_shares),
        )
        conn.commit()


def _cleanup_metrics_env(dsn: str) -> None:
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM ods_cn_daily_metrics WHERE symbol = ANY(%s)", (list(SYMBOLS),))
        cur.execute("DELETE FROM ods_cn_share_structure WHERE symbol = ANY(%s)", (list(SYMBOLS),))
        cur.execute(
            """
            DELETE FROM fact_indicator
            WHERE ref_key = ANY(%s)
              AND indicator_id IN (SELECT indicator_id FROM dim_indicator WHERE source = 'cn-daily')
            """,
            (list(SYMBOLS),),
        )
        cur.execute("DELETE FROM dim_indicator WHERE source = 'cn-daily'")
        cur.execute(
            "DELETE FROM fact_kline WHERE market_id = 'a-share' AND provider_id = 'test-metrics'"
        )
        cur.execute("DELETE FROM dim_instrument WHERE market_id = 'a-share' AND symbol = ANY(%s)", (list(SYMBOLS),))
        cur.execute(
            """
            DELETE FROM dim_market
            WHERE market_id = 'a-share'
              AND NOT EXISTS (SELECT 1 FROM dim_instrument WHERE market_id = 'a-share')
            """
        )
        cur.execute(
            """
            DELETE FROM etl_watermarks
            WHERE scope = 'cn-daily:metrics' OR scope = ANY(%s)
            """,
            (METRICS_SCOPES,),
        )
        conn.commit()


@pytest.fixture
def metrics_env(dsn):
    # 既清理残留（上轮失败留下的行），也在收尾时清理，保证断言与执行顺序无关
    _cleanup_metrics_env(dsn)
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO dim_market (market_id, name, region, currency)
            VALUES ('a-share', 'A股', 'CN', 'CNY')
            ON CONFLICT (market_id) DO NOTHING
            """
        )
        for symbol in SYMBOLS:
            cur.execute(
                """
                INSERT INTO dim_instrument (market_id, symbol, name)
                VALUES ('a-share', %s, %s)
                ON CONFLICT (market_id, symbol) DO NOTHING
                """,
                (symbol, f"测试标的{symbol}"),
            )
        conn.commit()

    yield SYMBOLS

    _cleanup_metrics_env(dsn)


def _metrics_rows(dsn: str) -> dict[tuple[str, str], dict]:
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT symbol, trade_date, close_price, turnover_rate, market_cap
            FROM ods_cn_daily_metrics
            WHERE symbol = ANY(%s)
            ORDER BY symbol, trade_date
            """,
            (list(SYMBOLS),),
        )
        return {
            (row[0], row[1]): {
                "close_price": row[2],
                "turnover_rate": row[3],
                "market_cap": row[4],
            }
            for row in cur.fetchall()
        }


def test_new_symbol_without_watermark_processes_its_full_history(
    dsn, metrics_env
):
    """标的 A 已有水位线、标的 B 是全新标的 → B 的全部历史 K 线都必须被计算。

    旧实现用单个全局水位线 `cn-daily:metrics`，且只取 `date_key >= 水位线`：
    K 线全市场补采后新增标的的历史全部落在水位线之前，会被静默丢弃，
    输出仍是 `{'rows': ...}`、退出码 0，与正确全量从外部无法区分。
    真实库中该全局水位线残留为 2016-06-30，本用例同时钉住「已废弃 scope 被忽略」。
    """
    for symbol in SYMBOLS:
        _seed_klines(dsn, symbol, TEST_DATES)
        _seed_shares(dsn, symbol, "2026-05-28", 1_000_000_000.0, 500_000_000.0)

    # A 已处理到 2026-09-18，水位线 = 下一个待处理交易日 2026-09-21
    _set_watermark(dsn, _metrics_scope(SYMBOL_SYNCED), "2026-09-21")
    # 旧全局水位线残留（真实库实测 2016-06-30）：改造后必须被忽略
    _set_watermark(dsn, "cn-daily:metrics", "2026-09-21")

    build_daily_metrics(dsn, batch_id=f"test-metrics-{uuid.uuid4()}")

    rows = _metrics_rows(dsn)
    assert set(rows) == {
        (SYMBOL_SYNCED, "2026-09-21"),
        (SYMBOL_BRAND_NEW, "2026-09-18"),
        (SYMBOL_BRAND_NEW, "2026-09-21"),
    }

    with connect(dsn) as conn:
        assert get_watermark(conn, _metrics_scope(SYMBOL_SYNCED)) == "2026-09-22"
        assert get_watermark(conn, _metrics_scope(SYMBOL_BRAND_NEW)) == "2026-09-22"


def _daily_indicator_rows(dsn: str, symbol: str) -> list[tuple[str, str, float]]:
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT d.source_key, f.as_of_date::text, f.value
            FROM fact_indicator f
            JOIN dim_indicator d ON d.indicator_id = f.indicator_id
            WHERE d.source = 'cn-daily' AND f.ref_key = %s
            ORDER BY d.source_key
            """,
            (symbol,),
        )
        return cur.fetchall()


def test_cn_daily_indicators_are_loaded_with_correct_units(dsn, metrics_env):
    """cn-daily 指标分支的入库级覆盖：换手率（%）与总市值（CNY）。

    该分支此前没有任何测试执行过。换手率以百分数（小数形式）落库是最易错、
    错了会静默污染下游因子的约定，必须钉住单位与数值。
    """
    _seed_klines(dsn, SYMBOL_BRAND_NEW, ("2026-09-21",), close=10.0, volume=50000.0)
    _seed_shares(dsn, SYMBOL_BRAND_NEW, "2026-05-28", 1_000_000_000.0, 500_000_000.0)

    build_daily_metrics(dsn, batch_id=f"test-metrics-{uuid.uuid4()}")

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT source_key, name, unit FROM dim_indicator
            WHERE source = 'cn-daily' ORDER BY source_key
            """
        )
        assert cur.fetchall() == [
            ("market_cap", "总市值", "CNY"),
            ("turnover_rate", "换手率", "%"),
        ]

    # 换手率 = volume(手) × 10000 ÷ 流通股本 = 50000 × 10000 ÷ 5e8 = 1.0(%)
    # 总市值 = close × 总股本 = 10 × 1e9 = 1e10(CNY)
    rows = _daily_indicator_rows(dsn, SYMBOL_BRAND_NEW)
    assert [(key, as_of) for key, as_of, _ in rows] == [
        ("market_cap", "2026-09-21"),
        ("turnover_rate", "2026-09-21"),
    ]
    assert rows[0][2] == pytest.approx(1e10)
    assert rows[1][2] == pytest.approx(1.0)

    with connect(dsn) as conn:
        assert get_watermark(conn, _metrics_scope(SYMBOL_BRAND_NEW)) == "2026-09-22"


def test_cn_daily_skips_turnover_indicator_when_float_shares_missing(
    dsn, metrics_env
):
    """流通股本缺失时跳过换手率（不写 0），总市值仍然产出。"""
    _seed_klines(dsn, SYMBOL_BRAND_NEW, ("2026-09-21",), close=10.0, volume=50000.0)
    _seed_shares(dsn, SYMBOL_BRAND_NEW, "2026-05-28", 1_000_000_000.0, None)

    build_daily_metrics(dsn, batch_id=f"test-metrics-{uuid.uuid4()}")

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT source_key FROM dim_indicator WHERE source = 'cn-daily' ORDER BY source_key"
        )
        # 换手率整条不产出：既不建 dim_indicator，也不写 0
        assert cur.fetchall() == [("market_cap",)]

    rows = _daily_indicator_rows(dsn, SYMBOL_BRAND_NEW)
    assert [(key, as_of) for key, as_of, _ in rows] == [("market_cap", "2026-09-21")]
    assert rows[0][2] == pytest.approx(1e10)
