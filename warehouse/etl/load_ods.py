"""ODS kline loading helpers."""
from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from etl.db import connect


MARKET_TABLES = {
    "a-share": "ods_klines_a_share",
    "fund": "ods_klines_fund",
    "us": "ods_klines_us",
    "kr": "ods_klines_kr",
    "hk": "ods_klines_hk",
    "fx": "ods_klines_fx",
    "crypto": "ods_klines_crypto",
}

_COMMON_COLUMNS = (
    "provider",
    "market",
    "symbol",
    "interval",
    "ts",
)

_TABLE_COLUMNS = {
    "ods_klines_a_share": (
        *_COMMON_COLUMNS,
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "change_pct",
        "turnover_rate",
        "amplitude",
        "raw_payload",
        "sync_batch_id",
    ),
    "ods_klines_fund": (
        *_COMMON_COLUMNS,
        "open",
        "high",
        "low",
        "close",
        "volume",
        "nav",
        "accum_nav",
        "daily_growth_pct",
        "purchase_status",
        "redeem_status",
        "raw_payload",
        "sync_batch_id",
    ),
    "ods_klines_us": (
        *_COMMON_COLUMNS,
        "open",
        "high",
        "low",
        "close",
        "volume",
        "adj_close",
        "dividends",
        "stock_splits",
        "raw_payload",
        "sync_batch_id",
    ),
    "ods_klines_kr": (
        *_COMMON_COLUMNS,
        "open",
        "high",
        "low",
        "close",
        "volume",
        "raw_payload",
        "sync_batch_id",
    ),
    "ods_klines_hk": (
        *_COMMON_COLUMNS,
        "open",
        "high",
        "low",
        "close",
        "volume",
        "corporate_events",
        "raw_payload",
        "sync_batch_id",
    ),
    "ods_klines_fx": (
        *_COMMON_COLUMNS,
        "base_currency",
        "quote_currency",
        "close_rate",
        "prev_rate",
        "open_rate",
        "high_rate",
        "low_rate",
        "raw_payload",
        "sync_batch_id",
    ),
    "ods_klines_crypto": (
        *_COMMON_COLUMNS,
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "trades_count",
        "funding_rate",
        "raw_payload",
        "sync_batch_id",
    ),
}

_JSONB_COLUMNS = {"raw_payload", "corporate_events"}
_KEY_COLUMNS = _COMMON_COLUMNS


def _row_params(row: dict[str, Any], columns: tuple[str, ...]) -> tuple[Any, ...]:
    """Convert a row into typed SQL params for the given table columns."""
    params: list[Any] = []
    for column in columns:
        value = row.get(column)
        if column == "raw_payload" and value is None:
            value = {}
        if column in _JSONB_COLUMNS and value is not None:
            params.append(Jsonb(value))
        else:
            params.append(value)
    return tuple(params)


def upsert_ods_rows(
    dsn: str, market: str, rows: list[dict[str, Any]], batch_size: int = 1000
) -> None:
    """Insert ODS klines, updating conflicting rows in one transaction."""
    table = MARKET_TABLES.get(market)
    if table is None:
        raise ValueError(f"unknown market: {market}")
    if not rows:
        return
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    columns = _TABLE_COLUMNS[table]
    insert_columns = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    conflict_columns = ", ".join(_KEY_COLUMNS)
    update_columns = [column for column in columns if column not in _KEY_COLUMNS]
    assignments = ", ".join(f"{column} = EXCLUDED.{column}" for column in update_columns)
    sql = (
        f"INSERT INTO {table} ({insert_columns}) "
        f"VALUES ({placeholders}) "
        f"ON CONFLICT ({conflict_columns}) DO UPDATE SET {assignments}"
    )

    with connect(dsn) as conn, conn.cursor() as cur:
        chunk: list[tuple[Any, ...]] = []
        for row in rows:
            chunk.append(_row_params({**row, "market": market}, columns))
            if len(chunk) >= batch_size:
                cur.executemany(sql, chunk)
                chunk.clear()
        if chunk:
            cur.executemany(sql, chunk)
        conn.commit()
