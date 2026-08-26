"""Initial warehouse migration and news seeding."""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta, timezone
import logging
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
logger = logging.getLogger(__name__)


def _new_batch_id() -> str:
    return f"seed-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%f}-{uuid.uuid4().hex[:8]}"


def _split_fx_currency(symbol: Any) -> tuple[str | None, str | None]:
    """Parse FX symbols like EURUSD=X or EUR/USD into a currency pair."""
    text = str(symbol).strip().upper().replace("/", "").replace("=X", "")
    if len(text) == 6 and text.isalpha():
        return text[:3], text[3:]
    return None, None


def _mapped_sqlite_row(row: sqlite3.Row, batch_id: str) -> dict[str, Any] | None:
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
        "sync_batch_id": batch_id,
    }
    if market == "fx":
        # ODS FX 表使用 rate 字段；沿用 SQLite 的 OHLCV 数值即可兼容现有 DWD 装载。
        base_currency, quote_currency = _split_fx_currency(row["symbol"])
        if base_currency is None or quote_currency is None:
            logger.warning(
                "Skipping FX kline symbol=%s: cannot parse currency pair",
                row["symbol"],
            )
            return None
        mapped.update(
            {
                "base_currency": base_currency,
                "quote_currency": quote_currency,
                "open_rate": row["open"],
                "high_rate": row["high"],
                "low_rate": row["low"],
                "close_rate": row["close"],
                "prev_rate": None,
            }
        )
    return mapped


def iter_sqlite_klines(
    db_path: Path | str, batch_id: str
) -> Iterator[dict[str, Any]]:
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
            mapped = _mapped_sqlite_row(row, batch_id)
            if mapped is not None:
                yield mapped


def migrate_klines(
    dsn: str,
    db_path: Path | str,
    batch_id: str | None = None,
    ods_batch_size: int = 1000,
) -> dict[str, dict[str, int]]:
    """Stream SQLite klines into ODS/DWD and return per-market row counts."""
    batch_id = batch_id or _new_batch_id()
    stats = {market: {"ods": 0, "dwd": 0} for market in MARKETS}

    current_market: str | None = None
    current_count = 0
    chunk: list[dict[str, Any]] = []

    def flush_ods() -> None:
        nonlocal chunk, current_count
        if chunk:
            upsert_ods_rows(dsn, current_market, chunk, batch_size=ods_batch_size)
            current_count += len(chunk)
            chunk = []

    def close_market() -> None:
        nonlocal current_count
        if current_market is None:
            return
        flush_ods()
        stats[current_market]["ods"] = current_count
        stats[current_market]["dwd"] = build_dwd(dsn, current_market)
        current_count = 0

    for row in iter_sqlite_klines(db_path, batch_id):
        market = row["market"]
        if market not in MARKET_TABLES:
            logger.warning("Skipping klines from unknown market: %s", market)
            continue
        if current_market is None:
            current_market = market
        elif market != current_market:
            close_market()
            current_market = market

        chunk.append(row)
        if len(chunk) >= ods_batch_size:
            flush_ods()

    close_market()
    return stats


def _parse_news_time(value: str) -> datetime:
    if str(value).strip().upper() == "RSS":
        now = datetime.now(_CN_TIMEZONE)
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    parsed = datetime.strptime(value, "%m-%d %H:%M")
    now = datetime.now(_CN_TIMEZONE)
    parsed = parsed.replace(year=now.year, tzinfo=_CN_TIMEZONE)
    if parsed > now + timedelta(days=7):
        parsed = parsed.replace(year=now.year - 1)
    return parsed


def _news_items(include_rss: bool) -> list[dict[str, Any]]:
    if include_rss:
        return macro_data.fetch_rss_news()
    return list(macro_data.NEWS_ITEMS)


def _news_params(items: list[dict[str, Any]], batch_id: str) -> list[tuple[Any, ...]]:
    params: list[tuple[Any, ...]] = []
    for item in items:
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
                batch_id,
            )
        )
    return params


def _upsert_news(conn: Any, news_params: list[tuple[Any, ...]]) -> None:
    """Upsert news params into ODS/fact tables on an open connection (no commit)."""
    with conn.cursor() as cur:
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


def load_news(
    dsn: str, batch_id: str | None = None, include_rss: bool = False
) -> int:
    """Load cached macro news into ODS and fact_news."""
    batch_id = batch_id or _new_batch_id()
    news_params = _news_params(_news_items(include_rss), batch_id)
    if not news_params:
        return 0

    with connect(dsn) as conn:
        _upsert_news(conn, news_params)
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
    include_rss = os.environ.get("WAREHOUSE_LIVE_NEWS", "").lower() in {
        "1",
        "true",
        "yes",
    }
    batch_id = _new_batch_id()

    kline_stats = migrate_klines(dsn, db_path, batch_id=batch_id)
    news_count = load_news(dsn, batch_id=batch_id, include_rss=include_rss)
    refresh_dws(dsn)

    _print_stats(kline_stats, news_count)


if __name__ == "__main__":
    main()
