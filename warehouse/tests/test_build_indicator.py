"""Indicator model build tests."""
from __future__ import annotations

import uuid

import psycopg
import pytest

from etl.build_indicator import build_indicators
from etl.load_external import upsert_external_rows


BATCH = f"test-ind-{uuid.uuid4()}"


@pytest.fixture
def cleanup_indicator(dsn):
    yield
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM ods_crypto_meta WHERE sync_batch_id LIKE 'test-ind-%'")
        cur.execute(
            """
            DELETE FROM fact_indicator WHERE indicator_id IN (
              SELECT indicator_id FROM dim_indicator WHERE source = 'crypto'
            )
            """
        )
        cur.execute("DELETE FROM dim_indicator WHERE source = 'crypto'")
        conn.commit()


def _seed_crypto(dsn: str) -> None:
    rows = [
        {
            "coin_id": "bitcoin",
            "symbol": "btc",
            "name": "Bitcoin",
            "snapshot_date": "2026-08-25",
            "current_price": 79000.0,
            "market_cap": 1.5e12,
            "total_volume": 5.0e10,
            "high_24h": 80000.0,
            "low_24h": 78000.0,
            "market_cap_rank": 1,
            "raw_payload": {},
            "sync_batch_id": BATCH,
        }
    ]
    with psycopg.connect(dsn) as conn:
        upsert_external_rows(conn, "crypto_meta", rows)
        conn.commit()


def test_build_indicators_creates_dim_and_fact(dsn, cleanup_indicator):
    _seed_crypto(dsn)
    with psycopg.connect(dsn) as conn:
        affected = build_indicators(conn, "crypto")
        conn.commit()

    assert affected == 3
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM dim_indicator WHERE source = 'crypto'")
        assert cur.fetchone()[0] == 3
        cur.execute(
            """
            SELECT i.source_key, f.ref_key, f.value
            FROM fact_indicator f
            JOIN dim_indicator i ON i.indicator_id = f.indicator_id
            WHERE i.source = 'crypto' AND i.source_key = 'current_price'
            """
        )
        assert cur.fetchone() == ("current_price", "bitcoin", 79000.0)


def test_build_indicators_is_idempotent(dsn, cleanup_indicator):
    _seed_crypto(dsn)
    with psycopg.connect(dsn) as conn:
        build_indicators(conn, "crypto")
        build_indicators(conn, "crypto")
        conn.commit()
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM dim_indicator WHERE source = 'crypto'")
        assert cur.fetchone()[0] == 3
        cur.execute("SELECT count(*) FROM fact_indicator")
        assert cur.fetchone()[0] == 3
