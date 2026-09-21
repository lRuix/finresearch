"""Indicator model build tests."""
from __future__ import annotations

import uuid

import psycopg
import pytest

from etl.build_indicator import build_indicators
from etl.db import connect
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
              SELECT indicator_id FROM dim_indicator
              WHERE source IN ('crypto','cn-balance','cn-daily')
            )
            """
        )
        cur.execute(
            "DELETE FROM dim_indicator WHERE source IN ('crypto','cn-balance','cn-daily')"
        )
        cur.execute("DELETE FROM ods_cn_balance WHERE sync_batch_id LIKE 'test-%'")
        cur.execute("DELETE FROM ods_cn_daily_metrics WHERE sync_batch_id LIKE 'test-%'")
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


def test_build_indicators_reads_cn_balance(dsn, cleanup_indicator):
    import psycopg

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ods_cn_balance
              (symbol, report_date, indicator_name, indicator_value, raw_payload, sync_batch_id)
            VALUES ('600519', '2026-06-30', '总资产', 309050784569.31, '{}', 'test-bi-balance')
            ON CONFLICT DO NOTHING
            """
        )
        conn.commit()

    with connect(dsn) as conn:
        affected = build_indicators(conn, "cn-balance")
        conn.commit()
    assert affected >= 1

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FROM fact_indicator f
            JOIN dim_indicator d ON d.indicator_id = f.indicator_id
            WHERE d.source = 'cn-balance' AND d.name = '总资产'
              AND f.ref_key = '600519' AND f.value = 309050784569.31
            """
        )
        assert cur.fetchone()[0] == 1
        cur.execute("DELETE FROM ods_cn_balance WHERE sync_batch_id = 'test-bi-balance'")
        conn.commit()
