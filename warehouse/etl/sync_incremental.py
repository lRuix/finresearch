"""Incremental warehouse sync.

直采全市场 K 线：按市场动态发现标的，按 ``etl_watermarks`` 水位线只装载
每个 (market, symbol, period) 新增的 K 线；ODS/DWD/新闻装载与水位线推进在
同一事务内完成，失败回滚且不推进水位线；事务提交后再刷新 DWS 物化视图。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
import logging
import os
import time
from typing import Any

from etl.build_dwd import _parse_time, build_dwd
from etl.build_dws import refresh_dws
from etl.db import connect
from etl.load_ods import upsert_ods_rows
from etl.migrate_seed import (
    _new_batch_id,
    _news_items,
    _news_params,
    _split_fx_currency,
    _upsert_news,
    DEFAULT_DSN,
)
from etl.sources import market


logger = logging.getLogger(__name__)

KLINE_SCOPE_PREFIX = "kline:"
NEWS_SCOPE = "news"
MARKETS = ("a-share", "fund", "us", "kr", "hk", "fx", "crypto")
REQUEST_DELAY_SECONDS = 0.15
FIRST_SYNC_START = "2024-01-01"


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


def sync_incremental(
    dsn: str,
    include_rss: bool = False,
    batch_id: str | None = None,
    markets: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """直采全市场 K 线增量：discover -> fetch -> ODS -> DWD -> 水位线。"""
    batch_id = batch_id or _new_batch_id()
    stats: dict[str, Any] = {"klines": {}, "news": 0}
    markets = markets or MARKETS

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
        today = date.today().isoformat()
        for market_id in markets:
            try:
                instruments = market.discover_instruments(market_id)
            except Exception as exc:  # noqa: BLE001 - 市场发现失败跳过该市场
                logger.warning("discover %s failed: %s", market_id, exc)
                continue
            for item in instruments:
                symbol = item["symbol"]
                key = (market_id, symbol, "d")
                last = kline_wm.get(key)
                start = (
                    (last + timedelta(days=1)).date().isoformat()
                    if last is not None
                    else FIRST_SYNC_START
                )
                try:
                    rows = market.fetch_klines(market_id, symbol, "d", start=start, end=today)
                except Exception as exc:  # noqa: BLE001 - 单标的失败跳过
                    logger.warning("fetch %s %s failed: %s", market_id, symbol, exc)
                    continue
                time.sleep(REQUEST_DELAY_SECONDS)
                if not rows:
                    continue
                market_ods_rows: list[dict[str, Any]] = []
                for row in rows:
                    ods_row = {
                        "provider": "market",
                        "market": market_id,
                        "symbol": symbol,
                        "interval": "d",
                        "ts": row["time"],
                        "open": row["open"],
                        "high": row["high"],
                        "low": row["low"],
                        "close": row["close"],
                        "volume": row["volume"],
                        "raw_payload": {},
                        "sync_batch_id": batch_id,
                    }
                    if market_id == "fx":
                        base_currency, quote_currency = _split_fx_currency(symbol)
                        if base_currency is None or quote_currency is None:
                            logger.warning(
                                "Skipping fx kline symbol=%s ts=%s: cannot parse currency pair",
                                symbol,
                                row["time"],
                            )
                            continue
                        ods_row.update(
                            {
                                "base_currency": base_currency,
                                "quote_currency": quote_currency,
                                "close_rate": row["close"],
                                "prev_rate": None,
                                "open_rate": row["open"],
                                "high_rate": row["high"],
                                "low_rate": row["low"],
                            }
                        )
                    market_ods_rows.append(ods_row)
                ods_rows = market_ods_rows
                market_chunks.setdefault(market_id, []).extend(ods_rows)
                try:
                    ts = max(_parse_time(row["time"]) for row in rows)
                except (TypeError, ValueError):
                    continue
                if key not in new_watermarks or ts > new_watermarks[key]:
                    new_watermarks[key] = ts

        for market_id, rows in market_chunks.items():
            upsert_ods_rows(dsn, market_id, rows, conn=conn)
            affected = build_dwd(dsn, market_id, conn=conn)
            stats["klines"][market_id] = {"ods": len(rows), "dwd": affected}

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
    include_rss = os.environ.get("WAREHOUSE_LIVE_NEWS", "").lower() in {
        "1",
        "true",
        "yes",
    }
    markets_env = os.environ.get("WAREHOUSE_MARKETS", "")
    markets = tuple(
        market.strip() for market in markets_env.split(",") if market.strip()
    ) or None
    stats = sync_incremental(dsn, include_rss=include_rss, markets=markets)
    for market, counts in stats["klines"].items():
        print(f"{market}: ODS={counts['ods']}, DWD={counts['dwd']}")
    print(f"news: {stats['news']}")


if __name__ == "__main__":
    main()
