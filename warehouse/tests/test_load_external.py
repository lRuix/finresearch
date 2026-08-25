"""Generic external ODS upsert tests."""
from __future__ import annotations

import uuid

import psycopg
import pytest
from psycopg.types.json import Jsonb

from etl.load_external import upsert_external_rows


BATCH = f"test-ext-{uuid.uuid4()}"


@pytest.fixture
def cleanup_external(dsn):
    yield
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM ods_crypto_meta WHERE sync_batch_id LIKE 'test-ext-%'"
        )
        conn.commit()


def _coin_row(coin_id: str, price: float) -> dict:
    return {
        "coin_id": coin_id,
        "symbol": coin_id.upper()[:4],
        "name": coin_id.title(),
        "snapshot_date": "2026-08-25",
        "current_price": price,
        "market_cap": price * 1000,
        "total_volume": price * 10,
        "high_24h": price * 1.1,
        "low_24h": price * 0.9,
        "market_cap_rank": 1,
        "raw_payload": {"source": "unit-test"},
        "sync_batch_id": BATCH,
    }


def test_external_upsert_is_idempotent_and_updates(dsn, cleanup_external):
    row = _coin_row("testcoin", 100.0)
    with psycopg.connect(dsn) as conn:
        upsert_external_rows(conn, "crypto_meta", [row])
        conn.commit()
        upsert_external_rows(conn, "crypto_meta", [_coin_row("testcoin", 120.0)])
        conn.commit()

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*), max(current_price) FROM ods_crypto_meta WHERE coin_id = %s",
            ("testcoin",),
        )
        count, price = cur.fetchone()
    assert count == 1
    assert price == 120.0


def test_external_upsert_rolls_back_on_bad_row(dsn, cleanup_external):
    first = _coin_row("rollback-coin", 1.0)
    second = _coin_row("bad-coin", 2.0)
    second["raw_payload"] = object()

    with psycopg.connect(dsn) as conn:
        with pytest.raises((TypeError, psycopg.Error)):
            upsert_external_rows(conn, "crypto_meta", [first, second])
        conn.rollback()

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM ods_crypto_meta WHERE sync_batch_id = %s",
            (BATCH,),
        )
        assert cur.fetchone()[0] == 0


def test_external_upsert_defaults_missing_raw_payload(dsn, cleanup_external):
    row = _coin_row("nopayload-coin", 1.0)
    row.pop("raw_payload")
    with psycopg.connect(dsn) as conn:
        upsert_external_rows(conn, "crypto_meta", [row])
        conn.commit()
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT raw_payload = %s FROM ods_crypto_meta WHERE coin_id = %s",
            (Jsonb({}), "nopayload-coin"),
        )
        assert cur.fetchone()[0] is True
