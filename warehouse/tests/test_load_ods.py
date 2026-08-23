"""ODS loading tests."""
from __future__ import annotations

import uuid

import psycopg
import pytest

from etl.load_ods import upsert_ods_rows


BATCH_ID = f"test-load-ods-{uuid.uuid4()}"
ODS_TABLES = [
    "ods_klines_a_share",
    "ods_klines_fund",
    "ods_klines_us",
    "ods_klines_kr",
    "ods_klines_hk",
    "ods_klines_fx",
    "ods_klines_crypto",
]


def _a_share_row(symbol: str, close: float) -> dict:
    return {
        "provider": "test-provider",
        "market": "a-share",
        "symbol": symbol,
        "interval": "1d",
        "ts": "2026-08-23",
        "open": 1.0,
        "high": 2.0,
        "low": 0.5,
        "close": close,
        "volume": 100.0,
        "amount": 200.0,
        "raw_payload": {"source": "unit-test"},
        "sync_batch_id": BATCH_ID,
    }


def _crypto_row(symbol: str, close: float) -> dict:
    return {
        "provider": "test-provider",
        "market": "crypto",
        "symbol": symbol,
        "interval": "1h",
        "ts": "2026-08-23T00:00:00+00:00",
        "open": 1.0,
        "high": 2.0,
        "low": 0.5,
        "close": close,
        "volume": 100.0,
        "quote_volume": 200.0,
        "raw_payload": {"source": "unit-test"},
        "sync_batch_id": BATCH_ID,
    }


@pytest.fixture(autouse=True)
def cleanup_ods_rows(dsn):
    yield
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        for table in ODS_TABLES:
            cur.execute(
                f"DELETE FROM {table} WHERE sync_batch_id = %s",
                (BATCH_ID,),
            )
        conn.commit()


def test_a_share_upsert_is_idempotent(dsn):
    symbol = "TEST-A-SHARE-IDEMPOTENT"
    row = _a_share_row(symbol, close=10.0)

    upsert_ods_rows(dsn, "a-share", [row])
    upsert_ods_rows(dsn, "a-share", [row])

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*), max(close)
            FROM ods_klines_a_share
            WHERE provider = %s AND market = %s
              AND symbol = %s AND interval = %s AND ts = %s
            """,
            (
                row["provider"],
                row["market"],
                row["symbol"],
                row["interval"],
                row["ts"],
            ),
        )
        result = cur.fetchall()

    assert len(result) == 1
    assert result[0][0] == 1
    assert result[0][1] == 10.0


def test_a_share_upsert_updates_business_fields(dsn):
    symbol = "TEST-A-SHARE-UPDATE"
    row = _a_share_row(symbol, close=10.0)
    updated_row = _a_share_row(symbol, close=11.0)

    upsert_ods_rows(dsn, "a-share", [row])
    upsert_ods_rows(dsn, "a-share", [updated_row])

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*), max(close)
            FROM ods_klines_a_share
            WHERE provider = %s AND market = %s
              AND symbol = %s AND interval = %s AND ts = %s
            """,
            (
                row["provider"],
                row["market"],
                row["symbol"],
                row["interval"],
                row["ts"],
            ),
        )
        count, close = cur.fetchone()

    assert count == 1
    assert close == 11.0


def test_crypto_rows_only_write_crypto_table(dsn):
    symbol = "TEST-CRYPTO-ROUTE"
    row = _crypto_row(symbol, close=100.0)

    upsert_ods_rows(dsn, "crypto", [row])

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)
            FROM ods_klines_crypto
            WHERE provider = %s AND market = %s
              AND symbol = %s AND interval = %s AND ts = %s
            """,
            (
                row["provider"],
                row["market"],
                row["symbol"],
                row["interval"],
                row["ts"],
            ),
        )
        crypto_count = cur.fetchone()[0]

        for table in ODS_TABLES:
            if table == "ods_klines_crypto":
                continue
            cur.execute(
                f"""
                SELECT count(*)
                FROM {table}
                WHERE provider = %s AND market = %s
                  AND symbol = %s AND interval = %s AND ts = %s
                """,
                (
                    row["provider"],
                    row["market"],
                    row["symbol"],
                    row["interval"],
                    row["ts"],
                ),
            )
            assert cur.fetchone()[0] == 0

    assert crypto_count == 1


def test_unknown_market_raises_value_error(dsn):
    row = {
        "provider": "test-provider",
        "market": "unknown",
        "symbol": "TEST-UNKNOWN-MARKET",
        "interval": "1d",
        "ts": "2026-08-23",
        "close": 1.0,
        "sync_batch_id": BATCH_ID,
    }

    with pytest.raises(ValueError, match="unknown market"):
        upsert_ods_rows(dsn, "unknown", [row])
