"""Incremental warehouse sync.

以 SQLite ``research.db`` 为增量源：按 ``etl_watermarks`` 水位线只装载
每个 (market, symbol, period) 新增的 K 线，ODS/DWD/新闻装载与水位线推进在
同一事务内完成，失败回滚且不推进水位线；事务提交后再刷新 DWS 物化视图。
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime
import logging
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any, Iterator

from etl.build_dwd import _parse_time, build_dwd
from etl.build_dws import refresh_dws
from etl.db import connect
from etl.load_ods import upsert_ods_rows
from etl.migrate_seed import (
    _mapped_sqlite_row,
    _new_batch_id,
    _news_items,
    _news_params,
    _upsert_news,
    DEFAULT_DB_PATH,
    DEFAULT_DSN,
)


logger = logging.getLogger(__name__)

KLINE_SCOPE_PREFIX = "kline:"
NEWS_SCOPE = "news"


def _scope_key(market: str, symbol: str, period: str) -> str:
    return f"{KLINE_SCOPE_PREFIX}{market}:{symbol}:{period}"


def _read_watermarks(
    conn: Any,
) -> dict[tuple[str, str, str] | str, datetime | None]:
    """Load kline and news watermarks as {key: parsed datetime or None}."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT scope, last_value FROM etl_watermarks
            WHERE scope LIKE %s OR scope = %s
            """,
            (f"{KLINE_SCOPE_PREFIX}%", NEWS_SCOPE),
        )
        rows = cur.fetchall()
    watermarks: dict[tuple[str, str, str] | str, datetime | None] = {}
    for scope, last_value in rows:
        try:
            parsed = _parse_time(last_value)
        except (TypeError, ValueError):
            logger.warning("Skipping unparsable watermark %s=%s", scope, last_value)
            continue
        if scope == NEWS_SCOPE:
            watermarks[NEWS_SCOPE] = parsed
        elif scope.startswith(KLINE_SCOPE_PREFIX):
            market, symbol, period = scope[len(KLINE_SCOPE_PREFIX) :].split(":", 2)
            watermarks[(market, symbol, period)] = parsed
    return watermarks


def iter_sqlite_klines_after(
    db_path: str | Path,
    watermarks: dict[tuple[str, str, str], datetime | None],
    batch_id: str,
) -> Iterator[dict[str, Any]]:
    """Yield mapped ODS rows for SQLite klines past each key's watermark."""
    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            SELECT market, symbol, period, time, open, high, low, close, volume
            FROM klines
            ORDER BY market, symbol, period, time
            """
        )
        for row in cursor:
            key = (row["market"], row["symbol"], row["period"])
            last = watermarks.get(key)
            if last is not None:
                try:
                    ts = _parse_time(row["time"])
                except (TypeError, ValueError):
                    # 无法解析时间的行照常装载（由 DWD 层跳过），但不影响水位线。
                    ts = None
                if ts is not None and ts <= last:
                    continue
            mapped = _mapped_sqlite_row(row, batch_id)
            if mapped is not None:
                yield mapped


def sync_incremental(
    dsn: str,
    db_path: str | Path,
    include_rss: bool = False,
    batch_id: str | None = None,
) -> dict[str, Any]:
    """Incrementally sync SQLite deltas into ODS/DWD, then refresh DWS."""
    batch_id = batch_id or _new_batch_id()
    stats: dict[str, Any] = {"klines": {}, "news": 0}

    with connect(dsn) as conn:
        watermarks = _read_watermarks(conn)
        kline_wm = {
            key: value
            for key, value in watermarks.items()
            if isinstance(key, tuple)
        }
        news_wm = watermarks.get(NEWS_SCOPE)

        market_chunks: dict[str, list[dict[str, Any]]] = {}
        new_watermarks: dict[tuple[str, str, str], datetime] = {}
        for row in iter_sqlite_klines_after(db_path, kline_wm, batch_id):
            market = row["market"]
            market_chunks.setdefault(market, []).append(row)
            key = (market, row["symbol"], row["interval"])
            try:
                ts = _parse_time(row["ts"])
            except (TypeError, ValueError):
                continue
            if key not in new_watermarks or ts > new_watermarks[key]:
                new_watermarks[key] = ts

        for market, rows in market_chunks.items():
            upsert_ods_rows(dsn, market, rows, conn=conn)
            affected = build_dwd(dsn, market, conn=conn)
            stats["klines"][market] = {"ods": len(rows), "dwd": affected}

        with conn.cursor() as cur:
            for key, ts in new_watermarks.items():
                cur.execute(
                    """
                    INSERT INTO etl_watermarks (scope, last_value, updated_at)
                    VALUES (%s, %s, now())
                    ON CONFLICT (scope) DO UPDATE SET
                      last_value = EXCLUDED.last_value,
                      updated_at = now()
                    """,
                    (_scope_key(*key), ts.isoformat()),
                )

            news_params = _news_params(_news_items(include_rss), batch_id)
            if news_wm is not None:
                news_params = [
                    params for params in news_params if params[7] > news_wm
                ]
            if news_params:
                _upsert_news(conn, news_params)
                stats["news"] = len(news_params)
                max_news_time = max(params[7] for params in news_params)
                cur.execute(
                    """
                    INSERT INTO etl_watermarks (scope, last_value, updated_at)
                    VALUES (%s, %s, now())
                    ON CONFLICT (scope) DO UPDATE SET
                      last_value = EXCLUDED.last_value,
                      updated_at = now()
                    """,
                    (NEWS_SCOPE, max_news_time.isoformat()),
                )

        conn.commit()

    refresh_dws(dsn)
    return stats


def main() -> None:
    dsn = os.environ.get("WAREHOUSE_DSN", DEFAULT_DSN)
    db_path = Path(os.environ.get("WAREHOUSE_DB_PATH", str(DEFAULT_DB_PATH)))
    include_rss = os.environ.get("WAREHOUSE_LIVE_NEWS", "").lower() in {
        "1",
        "true",
        "yes",
    }
    stats = sync_incremental(dsn, db_path, include_rss=include_rss)
    for market, counts in stats["klines"].items():
        print(f"{market}: ODS={counts['ods']}, DWD={counts['dwd']}")
    print(f"news: {stats['news']}")


if __name__ == "__main__":
    main()
