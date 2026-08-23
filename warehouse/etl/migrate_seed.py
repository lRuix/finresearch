"""Initial warehouse migration and news seeding."""
from __future__ import annotations

from collections import defaultdict
from contextlib import closing
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any, Iterator
import uuid

from psycopg.types.json import Jsonb

from etl.build_dwd import build_dwd
from etl.build_dws import refresh_dws
from etl.db import connect
from etl.load_ods import MARKET_TABLES, upsert_ods_rows


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.infrastructure.datasources import macro_data


DEFAULT_DSN = "postgresql://warehouse:warehouse@127.0.0.1:5432/warehouse"
DEFAULT_DB_PATH = ROOT / "backend" / "data" / "research.db"
MARKETS = tuple(MARKET_TABLES)

_CN_TIMEZONE = timezone(timedelta(hours=8))
_BATCH_ID = f"seed-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%f}-{uuid.uuid4().hex[:8]}"

# RSS 暂不默认抓取：外部网络不稳定，后续可在 load_news 中合并 fetch_rss_news 的结果。


def _mapped_sqlite_row(row: sqlite3.Row) -> dict[str, Any]:
    """Map one legacy kline row to the shared ODS shape."""
    market = row["market"]
    mapped: dict[str, Any] = {
        "provider": "sqlite",
        "market": market,
        "symbol": row["symbol"],
        "interval": row["period"],
        "ts": row["time"],
        "open": row["open"],
        "high": row["high"],
        "low": row["low"],
        "close": row["close"],
        "volume": row["volume"],
        "raw_payload": {},
        "sync_batch_id": _BATCH_ID,
    }
    if market == "fx":
        # ODS FX 表使用 rate 字段；沿用 SQLite 的 OHLCV 数值即可兼容现有 DWD 装载。
        mapped.update(
            {
                "base_currency": row["symbol"][:3],
                "quote_currency": row["symbol"][3:6],
                "open_rate": row["open"],
                "high_rate": row["high"],
                "low_rate": row["low"],
                "close_rate": row["close"],
                "prev_rate": None,
            }
        )
    return mapped


def iter_sqlite_klines(db_path: Path | str) -> Iterator[dict[str, Any]]:
    """Yield legacy SQLite klines as ODS rows."""
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
            yield _mapped_sqlite_row(row)


def migrate_klines(dsn: str, db_path: Path | str) -> dict[str, dict[str, int]]:
    """Load SQLite klines into ODS/DWD and return per-market row counts."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in iter_sqlite_klines(db_path):
        grouped[row["market"]].append(row)

    stats: dict[str, dict[str, int]] = {}
    for market in MARKETS:
        rows = grouped.get(market, [])
        if not rows:
            stats[market] = {"ods": 0, "dwd": 0}
            continue

        upsert_ods_rows(dsn, market, rows)
        dwd_count = build_dwd(dsn, market)
        stats[market] = {"ods": len(rows), "dwd": dwd_count}
    return stats


def _parse_news_time(value: str) -> datetime:
    parsed = datetime.strptime(value, "%m-%d %H:%M")
    return parsed.replace(year=datetime.now(_CN_TIMEZONE).year, tzinfo=_CN_TIMEZONE)


def _news_params() -> list[tuple[Any, ...]]:
    params: list[tuple[Any, ...]] = []
    for item in macro_data.NEWS_ITEMS:
        published_at = _parse_news_time(item["time"])
        params.append(
            (
                "macro-data",
                "global",
                published_at.isoformat(),
                item["title"],
                item["source"],
                Jsonb(item["tags"]),
                item["sentiment"],
                published_at,
                Jsonb({}),
                _BATCH_ID,
            )
        )
    return params


def load_news(dsn: str) -> int:
    """Load cached macro news into ODS and fact_news."""
    news_params = _news_params()
    if not news_params:
        return 0

    with connect(dsn) as conn, conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO ods_news (
              provider, market, ts, title, source, tags, sentiment,
              published_at, raw_payload, sync_batch_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source, published_at, title) DO UPDATE SET
              provider = EXCLUDED.provider,
              market = EXCLUDED.market,
              ts = EXCLUDED.ts,
              tags = EXCLUDED.tags,
              sentiment = EXCLUDED.sentiment,
              raw_payload = EXCLUDED.raw_payload,
              sync_batch_id = EXCLUDED.sync_batch_id
            """,
            news_params,
        )
        cur.executemany(
            """
            INSERT INTO fact_news (source, published_at, title, sentiment, tags)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (source, published_at, title) DO UPDATE SET
              sentiment = EXCLUDED.sentiment,
              tags = EXCLUDED.tags
            """,
            [
                (
                    source,
                    published_at,
                    title,
                    sentiment,
                    tags,
                )
                for _, _, _, title, source, tags, sentiment, published_at, _, _ in news_params
            ],
        )
        conn.commit()
    return len(news_params)


def _print_stats(
    kline_stats: dict[str, dict[str, int]], news_count: int
) -> None:
    for market in MARKETS:
        counts = kline_stats[market]
        print(f"{market}: ODS={counts['ods']}, DWD={counts['dwd']}")
    print(f"news: {news_count}")


def main() -> None:
    dsn = os.environ.get("WAREHOUSE_DSN", DEFAULT_DSN)
    db_path = Path(os.environ.get("WAREHOUSE_DB_PATH", str(DEFAULT_DB_PATH)))

    kline_stats = migrate_klines(dsn, db_path)
    news_count = load_news(dsn)
    refresh_dws(dsn)

    _print_stats(kline_stats, news_count)


if __name__ == "__main__":
    main()
