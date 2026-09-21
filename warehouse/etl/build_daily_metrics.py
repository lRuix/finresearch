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
from etl.sync_external import METRICS_SCOPE, get_watermark, set_watermark

DEFAULT_DSN = "postgresql://warehouse:warehouse@127.0.0.1:5432/warehouse"
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


def _fetch_klines(conn: Any, since: str) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT i.symbol, k.date_key::text AS trade_date, k.close, k.volume
            FROM fact_kline k
            JOIN dim_instrument i ON i.instrument_id = k.instrument_id
            WHERE k.market_id = 'a-share' AND k.period = 'd' AND k.date_key >= %s
            ORDER BY k.date_key, i.symbol
            """,
            (since,),
        )
        return cur.fetchall()


def build_daily_metrics(dsn: str, batch_id: str | None = None) -> dict[str, Any]:
    batch_id = batch_id or f"daily-metrics-{date.today().isoformat()}"
    with connect(dsn) as conn:
        since = get_watermark(conn, METRICS_SCOPE) or _EPOCH
        klines = _fetch_klines(conn, since)
        if not klines:
            return {"rows": 0, "through": None}
        table = load_share_structures(conn)
        rows = [
            {**row, "raw_payload": {}, "sync_batch_id": batch_id}
            for row in compute_rows(klines, table)
        ]
        if rows:
            upsert_external_rows(conn, "cn_daily_metrics", rows)
            build_indicators(conn, "cn-daily")
        last_date = max(row["trade_date"] for row in klines)
        next_date = (date.fromisoformat(last_date) + timedelta(days=1)).isoformat()
        set_watermark(conn, METRICS_SCOPE, next_date)
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("REFRESH MATERIALIZED VIEW dws_indicator_daily")
        conn.commit()
    return {"rows": len(rows), "through": last_date}


def main() -> None:
    dsn = os.environ.get("WAREHOUSE_DSN", DEFAULT_DSN)
    print(build_daily_metrics(dsn))


if __name__ == "__main__":
    main()
