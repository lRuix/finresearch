"""ODS loading tests."""
from __future__ import annotations

import uuid
from typing import Any

import psycopg
import pytest
from psycopg.types.json import Jsonb

from etl.load_ods import upsert_ods_rows


BATCH_ID = f"test-load-ods-{uuid.uuid4()}"
UPDATED_BATCH_ID = f"{BATCH_ID}-updated"
ODS_TABLES = [
    "ods_klines_a_share",
    "ods_klines_fund",
    "ods_klines_us",
    "ods_klines_kr",
    "ods_klines_hk",
    "ods_klines_fx",
    "ods_klines_crypto",
]


def _a_share_row(
    symbol: str,
    close: float,
    **overrides: Any,
) -> dict[str, Any]:
    row = {
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
    row.update(overrides)
    return row


def _crypto_row(symbol: str, close: float) -> dict[str, Any]:
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


@pytest.fixture
def cleanup_ods_rows(dsn):
    for table in ODS_TABLES:
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM {table} WHERE sync_batch_id LIKE %s",
                ("test-load-ods-%",),
            )
            conn.commit()
    yield
    for table in ODS_TABLES:
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM {table} WHERE sync_batch_id LIKE %s",
                ("test-load-ods-%",),
            )
            conn.commit()


def test_a_share_upsert_is_idempotent(dsn, cleanup_ods_rows):
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


def test_a_share_upsert_updates_business_fields(dsn, cleanup_ods_rows):
    symbol = "TEST-A-SHARE-UPDATE"
    row = _a_share_row(symbol, close=10.0)
    updated_raw_payload = {"source": "unit-test", "updated": True}
    updated_row = _a_share_row(
        symbol,
        close=11.0,
        amount=320.0,
        raw_payload=updated_raw_payload,
        sync_batch_id=UPDATED_BATCH_ID,
        volume=110.0,
        open=1.1,
        high=2.1,
        low=0.6,
        change_pct=2.5,
        turnover_rate=3.5,
        amplitude=4.5,
    )

    upsert_ods_rows(dsn, "a-share", [row])
    upsert_ods_rows(dsn, "a-share", [updated_row])

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)
            FROM ods_klines_a_share
            WHERE provider = %s AND market = %s
              AND symbol = %s AND interval = %s AND ts = %s
            """,
            (
                row["provider"],
                "a-share",
                row["symbol"],
                row["interval"],
                row["ts"],
            ),
        )
        count = cur.fetchone()[0]

        cur.execute(
            """
            SELECT close, amount, volume, open, high, low,
                   change_pct, turnover_rate, amplitude, sync_batch_id,
                   raw_payload = %s
            FROM ods_klines_a_share
            WHERE provider = %s AND market = %s
              AND symbol = %s AND interval = %s AND ts = %s
            """,
            (
                Jsonb(updated_raw_payload),
                row["provider"],
                "a-share",
                row["symbol"],
                row["interval"],
                row["ts"],
            ),
        )
        result = cur.fetchone()

    (
        close,
        amount,
        volume,
        open_,
        high,
        low,
        change_pct,
        turnover_rate,
        amplitude,
        sync_batch_id,
        raw_payload_updated,
    ) = result
    assert count == 1
    assert close == 11.0
    assert amount == 320.0
    assert volume == 110.0
    assert open_ == 1.1
    assert high == 2.1
    assert low == 0.6
    assert change_pct == 2.5
    assert turnover_rate == 3.5
    assert amplitude == 4.5
    assert sync_batch_id == UPDATED_BATCH_ID
    assert raw_payload_updated is True


def test_crypto_rows_only_write_crypto_table(dsn, cleanup_ods_rows):
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


def test_unknown_market_raises_value_error():
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
        upsert_ods_rows("postgresql://not-used", "unknown", [row])


def test_missing_raw_payload_defaults_to_empty_object(dsn, cleanup_ods_rows):
    symbol = "TEST-A-SHARE-MISSING-RAW"
    row = _a_share_row(symbol, close=1.0)
    row.pop("raw_payload")

    upsert_ods_rows(dsn, "a-share", [row])

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)
            FROM ods_klines_a_share
            WHERE provider = %s AND market = %s
              AND symbol = %s AND interval = %s AND ts = %s
            """,
            (
                row["provider"],
                "a-share",
                row["symbol"],
                row["interval"],
                row["ts"],
            ),
        )
        count = cur.fetchone()[0]

        cur.execute(
            """
            SELECT raw_payload = %s
            FROM ods_klines_a_share
            WHERE provider = %s AND market = %s
              AND symbol = %s AND interval = %s AND ts = %s
            """,
            (
                Jsonb({}),
                row["provider"],
                "a-share",
                row["symbol"],
                row["interval"],
                row["ts"],
            ),
        )
        raw_payload_is_empty = cur.fetchone()[0]

    assert count == 1
    assert raw_payload_is_empty is True


def test_market_argument_overrides_row_market(dsn, cleanup_ods_rows):
    symbol = "TEST-A-SHARE-MARKET-OVERRIDE"
    row = _a_share_row(symbol, close=1.0)
    row["market"] = "fund"

    upsert_ods_rows(dsn, "a-share", [row])

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT market
            FROM ods_klines_a_share
            WHERE provider = %s AND symbol = %s AND interval = %s AND ts = %s
            """,
            (
                row["provider"],
                row["symbol"],
                row["interval"],
                row["ts"],
            ),
        )
        market = cur.fetchone()[0]

    assert market == "a-share"


def test_extra_row_fields_are_filtered(dsn, cleanup_ods_rows):
    symbol = "TEST-A-SHARE-EXTRA-FIELDS"
    row = _a_share_row(symbol, close=1.0, unexpected_column="ignored")

    upsert_ods_rows(dsn, "a-share", [row])

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)
            FROM ods_klines_a_share
            WHERE provider = %s AND market = %s
              AND symbol = %s AND interval = %s AND ts = %s
            """,
            (
                row["provider"],
                "a-share",
                row["symbol"],
                row["interval"],
                row["ts"],
            ),
        )
        count = cur.fetchone()[0]

    assert count == 1


def test_batch_rolls_back_when_later_row_fails(dsn, cleanup_ods_rows):
    first_symbol = "TEST-A-SHARE-ROLLBACK-FIRST"
    second_symbol = "TEST-A-SHARE-ROLLBACK-SECOND"
    first = _a_share_row(first_symbol, close=1.0)
    second = _a_share_row(second_symbol, close=2.0, raw_payload=object())

    with pytest.raises((TypeError, psycopg.Error)):
        upsert_ods_rows(dsn, "a-share", [first, second])

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        for symbol in (first_symbol, second_symbol):
            cur.execute(
                """
                SELECT count(*)
                FROM ods_klines_a_share
                WHERE provider = %s AND market = %s
                  AND symbol = %s AND interval = %s AND ts = %s
                """,
                (
                    first["provider"],
                    "a-share",
                    symbol,
                    first["interval"],
                    first["ts"],
                ),
            )
            assert cur.fetchone()[0] == 0


def test_upsert_in_multiple_batches(dsn, cleanup_ods_rows):
    rows = [
        _a_share_row(f"TEST-BATCH-{index}", close=float(index))
        for index in range(5)
    ]

    upsert_ods_rows(dsn, "a-share", rows, batch_size=2)

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)
            FROM ods_klines_a_share
            WHERE provider = %s AND sync_batch_id = %s
            """,
            (rows[0]["provider"], BATCH_ID),
        )
        assert cur.fetchone()[0] == 5


def test_rolls_back_previous_batches_when_later_batch_fails(dsn, cleanup_ods_rows):
    rows = [
        _a_share_row(f"TEST-ROLLBACK-BATCH-{index}", close=float(index))
        for index in range(5)
    ]
    rows[3]["raw_payload"] = object()

    with pytest.raises((TypeError, psycopg.Error)):
        upsert_ods_rows(dsn, "a-share", rows, batch_size=2)

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)
            FROM ods_klines_a_share
            WHERE provider = %s AND sync_batch_id = %s
            """,
            (rows[0]["provider"], BATCH_ID),
        )
        assert cur.fetchone()[0] == 0
