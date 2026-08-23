"""DWD kline build helpers."""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

from psycopg.rows import dict_row

from etl.db import connect
from etl.load_ods import MARKET_TABLES

logger = logging.getLogger(__name__)


MARKET_META = {
    "a-share": ("A-Share", "CN", "CNY"),
    "fund": ("Offshore Fund", "CN", "CNY"),
    "us": ("US Stock", "US", "USD"),
    "kr": ("Korea Stock", "KR", "KRW"),
    "hk": ("Hong Kong Stock", "HK", "HKD"),
    "fx": ("Foreign Exchange", "GLOBAL", "USD"),
    "crypto": ("Crypto", "GLOBAL", "USD"),
}

_PERIOD_ALIASES = {
    "1d": "d",
    "d": "d",
    "day": "d",
    "1h": "h",
    "1w": "w",
    "w": "w",
}


def _normalize_period(value: str) -> str:
    return _PERIOD_ALIASES.get(str(value).lower(), str(value))


def _parse_time(value: str) -> datetime:
    """Parse an ODS timestamp as UTC-aware.

    Naive timestamps are interpreted as UTC; a trailing Z is equivalent to +00:00.
    """
    text = str(value).strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _ensure_market(cur: Any, market_id: str) -> None:
    name, region, currency = MARKET_META[market_id]
    cur.execute(
        """
        INSERT INTO dim_market (market_id, name, region, currency)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (market_id) DO NOTHING
        """,
        (market_id, name, region, currency),
    )


def _ensure_provider(cur: Any, provider_id: str) -> None:
    cur.execute(
        """
        INSERT INTO dim_provider (provider_id, name)
        VALUES (%s, %s)
        ON CONFLICT (provider_id) DO NOTHING
        """,
        (provider_id, provider_id),
    )


def _ensure_date(cur: Any, date_key: date) -> None:
    cur.execute(
        """
        INSERT INTO dim_date (date_key, year, month, day, is_trading_day)
        VALUES (%s, %s, %s, %s, TRUE)
        ON CONFLICT (date_key) DO NOTHING
        """,
        (date_key, date_key.year, date_key.month, date_key.day),
    )


def _ensure_instrument(cur: Any, market_id: str, symbol: str) -> int:
    cur.execute(
        """
        SELECT instrument_id
        FROM dim_instrument
        WHERE market_id = %s AND symbol = %s
        """,
        (market_id, symbol),
    )
    row = cur.fetchone()
    if row is not None:
        return row["instrument_id"]

    cur.execute(
        """
        INSERT INTO dim_instrument (market_id, symbol, name)
        VALUES (%s, %s, %s)
        ON CONFLICT (market_id, symbol) DO NOTHING
        RETURNING instrument_id
        """,
        (market_id, symbol, symbol),
    )
    row = cur.fetchone()
    if row is not None:
        return row["instrument_id"]

    cur.execute(
        """
        SELECT instrument_id
        FROM dim_instrument
        WHERE market_id = %s AND symbol = %s
        """,
        (market_id, symbol),
    )
    return cur.fetchone()["instrument_id"]


def _map_ohlc(
    row: dict[str, Any], market: str
) -> tuple[float | None, float | None, float | None, float | None]:
    """Return normalized OHLC values, allowing None for rows that must be skipped."""
    if market == "fx":
        close = row.get("close_rate")
        if close is None:
            close = row.get("prev_rate")

        open_ = row.get("open_rate")
        high = row.get("high_rate")
        low = row.get("low_rate")
        if open_ is None:
            open_ = close
        if high is None:
            high = close
        if low is None:
            low = close
        return open_, high, low, close

    open_ = row.get("open")
    high = row.get("high")
    low = row.get("low")
    close = row.get("close")

    if market == "fund":
        nav = row.get("nav")
        if close is None:
            close = nav
        if open_ is None:
            open_ = close
        if high is None:
            high = close
        if low is None:
            low = close

    return open_, high, low, close


def build_dwd(dsn: str, market: str) -> int:
    """Load one market's ODS klines into the normalized fact table."""
    table = MARKET_TABLES.get(market)
    if table is None:
        raise ValueError(f"unknown market: {market}")

    with connect(dsn) as conn, conn.cursor(row_factory=dict_row) as cur:
        # 排序保证同键多 provider 时写入顺序确定；当前按排序后的最后一行生效，
        # 主源优先级语义后续由 ODS 层显式标记。
        cur.execute(f"SELECT * FROM {table} ORDER BY provider, symbol, interval, ts")
        ods_rows = cur.fetchall()
        if not ods_rows:
            return 0

        _ensure_market(cur, market)
        affected = 0
        for row in ods_rows:
            try:
                time = _parse_time(row["ts"])
            except (TypeError, ValueError):
                logger.warning(
                    "Skipping %s kline symbol=%s ts=%s: invalid timestamp",
                    market,
                    row.get("symbol"),
                    row.get("ts"),
                )
                continue

            open_, high, low, close = _map_ohlc(row, market)
            if any(value is None for value in (open_, high, low, close)):
                logger.warning(
                    "Skipping %s kline symbol=%s ts=%s: missing required OHLC values",
                    market,
                    row.get("symbol"),
                    row.get("ts"),
                )
                continue

            # date_key 取 time 的 UTC 自然日。
            date_key = time.astimezone(timezone.utc).date()

            provider_id = row["provider"]
            symbol = row["symbol"]
            instrument_id = _ensure_instrument(cur, market, symbol)
            _ensure_provider(cur, provider_id)
            _ensure_date(cur, date_key)

            period = _normalize_period(row["interval"])
            if market == "fx":
                volume = 0.0
            else:
                volume = row.get("volume")
                if volume is None:
                    volume = 0.0

            cur.execute(
                """
                INSERT INTO fact_kline (
                  market_id, instrument_id, provider_id, date_key,
                  period, time, open, high, low, close, volume
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (market_id, instrument_id, period, time)
                DO UPDATE SET
                  provider_id = EXCLUDED.provider_id,
                  date_key = EXCLUDED.date_key,
                  open = EXCLUDED.open,
                  high = EXCLUDED.high,
                  low = EXCLUDED.low,
                  close = EXCLUDED.close,
                  volume = EXCLUDED.volume
                """,
                (
                    market,
                    instrument_id,
                    provider_id,
                    date_key,
                    period,
                    time,
                    open_,
                    high,
                    low,
                    close,
                    volume,
                ),
            )
            affected += cur.rowcount

        conn.commit()
        return affected
