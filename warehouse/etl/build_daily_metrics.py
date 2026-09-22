"""Derive daily A-share metrics (turnover rate, market cap) from klines."""
from __future__ import annotations

import bisect
import os
from datetime import date, timedelta
from typing import Any, Iterable, Iterator

from psycopg.rows import dict_row

from etl.build_indicator import build_indicators
from etl.db import connect
from etl.load_external import upsert_external_rows
from etl.sync_external import get_watermarks, metrics_scope, set_watermark

DEFAULT_DSN = "postgresql://warehouse:warehouse@127.0.0.1:5432/warehouse"
# 新标的水位线缺失等价于「从未计算过」，回溯到该常量之前没有意义。
# 注：旧实现把单个全局水位线存在 "cn-daily:metrics"（无 symbol 后缀），该
# scope 已废弃——见 sync_external.metrics_scope() 的说明，本模块不再读写它。
_EPOCH = "1970-01-01"


def load_share_structures(conn: Any) -> dict[str, tuple[list[str], list[tuple[float, float | None]]]]:
    """symbol -> (升序变更日期, [(总股本, 流通股本), ...])"""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT symbol, change_date, total_shares, float_shares
            FROM ods_cn_share_structure
            ORDER BY symbol, change_date
            """
        )
        table: dict[str, tuple[list[str], list[tuple[float, float | None]]]] = {}
        for row in cur.fetchall():
            dates, values = table.setdefault(row["symbol"], ([], []))
            dates.append(row["change_date"])
            values.append((row["total_shares"], row["float_shares"]))
        return table


def shares_as_of(
    table: dict[str, tuple[list[str], list[tuple[float, float | None]]]],
    symbol: str,
    trade_date: str,
) -> tuple[float, float | None] | None:
    """取 change_date <= trade_date 的最新股本记录；无记录返回 None。"""
    entry = table.get(symbol)
    if entry is None:
        return None
    dates, values = entry
    index = bisect.bisect_right(dates, trade_date) - 1
    if index < 0:
        return None
    return values[index]


def compute_rows(
    klines: Iterable[dict[str, Any]],
    table: dict[str, tuple[list[str], list[tuple[float, float | None]]]],
) -> Iterator[dict[str, Any]]:
    for row in klines:
        shares = shares_as_of(table, row["symbol"], row["trade_date"])
        if shares is None:
            continue
        total_shares, float_shares = shares
        market_cap = row["close"] * total_shares if total_shares else None
        turnover_rate = (
            row["volume"] * 10000.0 / float_shares if float_shares else None
        )
        yield {
            "symbol": row["symbol"],
            "trade_date": row["trade_date"],
            "close_price": row["close"],
            "turnover_rate": turnover_rate,
            "market_cap": market_cap,
        }


def _a_share_symbols(conn: Any) -> list[str]:
    """fact_kline 中已有日线行情的 A 股标的。"""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT i.symbol
            FROM fact_kline k
            JOIN dim_instrument i ON i.instrument_id = k.instrument_id
            WHERE k.market_id = 'a-share' AND k.period = 'd'
            ORDER BY i.symbol
            """
        )
        return [row[0] for row in cur.fetchall()]


def _fetch_klines(
    conn: Any, since_by_symbol: dict[str, str]
) -> list[dict[str, Any]]:
    """按每个 symbol **各自**的水位线取 K 线。

    未在 `since_by_symbol` 中的 symbol 视为新标的，回溯全部历史（`_EPOCH`）。
    相同的 since 值合并成一次查询：既有新标的时不会退化成全表重扫，也不必为
    5000+ 标的逐个发查询。
    """
    groups: dict[str, list[str]] = {}
    for symbol in _a_share_symbols(conn):
        groups.setdefault(since_by_symbol.get(symbol, _EPOCH), []).append(symbol)

    rows: list[dict[str, Any]] = []
    with conn.cursor(row_factory=dict_row) as cur:
        for since, symbols in groups.items():
            cur.execute(
                """
                SELECT i.symbol, k.date_key::text AS trade_date, k.close, k.volume
                FROM fact_kline k
                JOIN dim_instrument i ON i.instrument_id = k.instrument_id
                WHERE k.market_id = 'a-share' AND k.period = 'd'
                  AND i.symbol = ANY(%s) AND k.date_key >= %s
                ORDER BY k.date_key, i.symbol
                """,
                (symbols, since),
            )
            rows.extend(cur.fetchall())
    return rows


def build_daily_metrics(dsn: str, batch_id: str | None = None) -> dict[str, Any]:
    batch_id = batch_id or f"daily-metrics-{date.today().isoformat()}"
    with connect(dsn) as conn:
        symbols = _a_share_symbols(conn)
        scopes = {symbol: metrics_scope(symbol) for symbol in symbols}
        existing = get_watermarks(conn, list(scopes.values()))
        since_by_symbol = {
            symbol: existing[scope]
            for symbol, scope in scopes.items()
            if scope in existing
        }
        klines = _fetch_klines(conn, since_by_symbol)
        if not klines:
            return {"rows": 0, "through": None, "symbols": 0}
        table = load_share_structures(conn)
        rows = [
            {**row, "raw_payload": {}, "sync_batch_id": batch_id}
            for row in compute_rows(klines, table)
        ]
        if rows:
            upsert_external_rows(conn, "cn_daily_metrics", rows)
            build_indicators(conn, "cn-daily")
        # 水位线按标的推进到「已处理的最大交易日 + 1 天」。没有股本记录、因而
        # 未产出任何指标行的标的同样要推进，否则它每次运行都会被重新扫描。
        processed_through: dict[str, str] = {}
        for row in klines:
            symbol = row["symbol"]
            if row["trade_date"] > processed_through.get(symbol, ""):
                processed_through[symbol] = row["trade_date"]
        for symbol, last_date in processed_through.items():
            set_watermark(
                conn,
                metrics_scope(symbol),
                (date.fromisoformat(last_date) + timedelta(days=1)).isoformat(),
            )
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("REFRESH MATERIALIZED VIEW dws_indicator_daily")
        conn.commit()
    return {
        "rows": len(rows),
        "through": max(processed_through.values()),
        "symbols": len(processed_through),
    }


def main() -> None:
    dsn = os.environ.get("WAREHOUSE_DSN", DEFAULT_DSN)
    print(build_daily_metrics(dsn))


if __name__ == "__main__":
    main()
