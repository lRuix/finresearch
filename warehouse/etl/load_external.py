"""Generic upsert helpers for external-source ODS tables."""
from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb


EXTERNAL_TABLES: dict[str, dict[str, Any]] = {
    "sec_submissions": {
        "table": "ods_sec_submissions",
        "key": ["cik"],
        "columns": [
            "cik",
            "ticker",
            "company_name",
            "exchange",
            "sic",
            "raw_payload",
            "sync_batch_id",
        ],
    },
    "sec_facts": {
        "table": "ods_sec_facts",
        "key": ["cik", "concept", "unit", "period_end"],
        "columns": [
            "cik",
            "concept",
            "unit",
            "period_end",
            "value",
            "raw_payload",
            "sync_batch_id",
        ],
    },
    "crypto_meta": {
        "table": "ods_crypto_meta",
        "key": ["coin_id", "snapshot_date"],
        "columns": [
            "coin_id",
            "symbol",
            "name",
            "snapshot_date",
            "current_price",
            "market_cap",
            "total_volume",
            "high_24h",
            "low_24h",
            "market_cap_rank",
            "raw_payload",
            "sync_batch_id",
        ],
    },
    "macro_indicators": {
        "table": "ods_macro_indicators",
        "key": ["country_code", "indicator_code", "date"],
        "columns": [
            "country_code",
            "indicator_code",
            "indicator_name",
            "date",
            "value",
            "raw_payload",
            "sync_batch_id",
        ],
    },
    "cn_financials": {
        "table": "ods_cn_financials",
        "key": ["symbol", "report_date", "indicator_name"],
        "columns": [
            "symbol",
            "report_date",
            "indicator_name",
            "indicator_value",
            "raw_payload",
            "sync_batch_id",
        ],
    },
    "cn_lhb": {
        "table": "ods_cn_lhb",
        "key": ["trade_date", "code", "reason"],
        "columns": [
            "trade_date",
            "code",
            "name",
            "close_price",
            "change_pct",
            "reason",
            "raw_payload",
            "sync_batch_id",
        ],
    },
}


def _row_params(row: dict[str, Any], columns: list[str]) -> tuple[Any, ...]:
    params: list[Any] = []
    for column in columns:
        value = row.get(column)
        if column == "raw_payload" and value is None:
            value = {}
        if column == "raw_payload" and value is not None:
            params.append(Jsonb(value))
        else:
            params.append(value)
    return tuple(params)


def upsert_external_rows(
    conn: Any,
    source_key: str,
    rows: list[dict[str, Any]],
    batch_size: int = 1000,
) -> None:
    """Upsert external ODS rows on an open connection (caller commits)."""
    meta = EXTERNAL_TABLES.get(source_key)
    if meta is None:
        raise ValueError(f"unknown external table: {source_key}")
    if not rows:
        return
    table = meta["table"]
    columns = meta["columns"]
    key_columns = meta["key"]
    insert_columns = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    conflict_columns = ", ".join(key_columns)
    update_columns = [column for column in columns if column not in key_columns]
    assignments = ", ".join(f"{column} = EXCLUDED.{column}" for column in update_columns)
    sql = (
        f"INSERT INTO {table} ({insert_columns}) VALUES ({placeholders}) "
        f"ON CONFLICT ({conflict_columns}) DO UPDATE SET {assignments}"
    )
    with conn.cursor() as cur:
        chunk: list[tuple[Any, ...]] = []
        for row in rows:
            chunk.append(_row_params(row, columns))
            if len(chunk) >= batch_size:
                cur.executemany(sql, chunk)
                chunk.clear()
        if chunk:
            cur.executemany(sql, chunk)
