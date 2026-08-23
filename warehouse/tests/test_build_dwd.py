"""DWD build tests."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import uuid
from typing import Any

import psycopg
import pytest

from etl.build_dwd import build_dwd
from etl.load_ods import upsert_ods_rows


ODS_TABLES = [
    "ods_klines_a_share",
    "ods_klines_fund",
    "ods_klines_us",
    "ods_klines_kr",
    "ods_klines_hk",
    "ods_klines_fx",
    "ods_klines_crypto",
]


@dataclass
class DwdCleanupContext:
    batch_id: str
    provider_id: str
    symbols: list[str] = field(default_factory=list)


@pytest.fixture
def dwd_cleanup(dsn):
    batch_id = f"test-build-dwd-{uuid.uuid4()}"
    provider_id = f"test-build-dwd-{uuid.uuid4().hex}"
    symbols: list[str] = []

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT market_id FROM dim_market")
        before_markets = {row[0] for row in cur.fetchall()}
        cur.execute("SELECT provider_id FROM dim_provider")
        before_providers = {row[0] for row in cur.fetchall()}
        cur.execute("SELECT date_key FROM dim_date")
        before_dates = {row[0] for row in cur.fetchall()}
        cur.execute("SELECT instrument_id FROM dim_instrument")
        before_instruments = {row[0] for row in cur.fetchall()}

    yield DwdCleanupContext(batch_id, provider_id, symbols)

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        for table in ODS_TABLES:
            cur.execute(
                f"DELETE FROM {table} WHERE sync_batch_id = %s",
                (batch_id,),
            )

        if symbols:
            cur.execute(
                """
                SELECT instrument_id
                FROM dim_instrument
                WHERE symbol = ANY(%s)
                  AND instrument_id != ALL(%s)
                """,
                (symbols, list(before_instruments)),
            )
            created_instrument_ids = [row[0] for row in cur.fetchall()]
            if created_instrument_ids:
                cur.execute(
                    """
                    DELETE FROM fact_kline
                    WHERE provider_id = %s
                      AND instrument_id = ANY(%s)
                    """,
                    (provider_id, created_instrument_ids),
                )
                cur.execute(
                    "DELETE FROM dim_instrument WHERE instrument_id = ANY(%s)",
                    (created_instrument_ids,),
                )

        cur.execute(
            "DELETE FROM dim_provider WHERE provider_id = %s AND provider_id != ALL(%s)",
            (provider_id, list(before_providers)),
        )
        cur.execute(
            """
            DELETE FROM dim_date
            WHERE date_key != ALL(%s)
            """,
            (list(before_dates),),
        )
        cur.execute(
            """
            DELETE FROM dim_market
            WHERE market_id != ALL(%s)
            """,
            (list(before_markets),),
        )
        conn.commit()


def _unique_symbol(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


def _base_row(
    provider_id: str,
    market: str,
    symbol: str,
    batch_id: str,
    interval: str = "1d",
    ts: str = "2099-01-05T12:00:00+08:00",
    **overrides: Any,
) -> dict[str, Any]:
    row = {
        "provider": provider_id,
        "market": market,
        "symbol": symbol,
        "interval": interval,
        "ts": ts,
        "raw_payload": {"source": "unit-test"},
        "sync_batch_id": batch_id,
    }
    row.update(overrides)
    return row


def _a_share_row(
    provider_id: str,
    symbol: str,
    batch_id: str,
    **overrides: Any,
) -> dict[str, Any]:
    row = _base_row(
        provider_id,
        "a-share",
        symbol,
        batch_id,
    )
    row.update(
        {
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 10.0,
            "volume": 100.0,
            "amount": 200.0,
            "change_pct": 1.5,
        }
    )
    row.update(overrides)
    return row


def _fx_row(
    provider_id: str,
    symbol: str,
    batch_id: str,
    **overrides: Any,
) -> dict[str, Any]:
    return _base_row(
        provider_id,
        "fx",
        symbol,
        batch_id,
        base_currency="USD",
        quote_currency="CNY",
        close_rate=7.2,
        prev_rate=7.1,
        open_rate=7.05,
        high_rate=7.25,
        low_rate=7.01,
        **overrides,
    )


def _fund_row(
    provider_id: str,
    symbol: str,
    batch_id: str,
    **overrides: Any,
) -> dict[str, Any]:
    return _base_row(
        provider_id,
        "fund",
        symbol,
        batch_id,
        nav=2.8960,
        **overrides,
    )


def _fact_row(dsn: str, market_id: str, symbol: str, period: str | None = None):
    sql = """
        SELECT f.market_id, f.instrument_id, f.provider_id, f.date_key,
               f.period, f.time, f.open, f.high, f.low, f.close, f.volume
        FROM fact_kline f
        JOIN dim_instrument i ON i.instrument_id = f.instrument_id
        WHERE i.market_id = %s AND i.symbol = %s
    """
    params = [market_id, symbol]
    if period is not None:
        sql += " AND f.period = %s"
        params.append(period)
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def test_a_share_ohlcv_maps_to_fact_kline(dsn, dwd_cleanup):
    symbol = _unique_symbol("TEST-A")
    dwd_cleanup.symbols.append(symbol)
    row = _a_share_row(dwd_cleanup.provider_id, symbol, dwd_cleanup.batch_id)

    upsert_ods_rows(dsn, "a-share", [row])
    affected = build_dwd(dsn, "a-share")

    rows = _fact_row(dsn, "a-share", symbol)
    assert affected >= 1
    assert len(rows) == 1
    (
        market_id,
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
    ) = rows[0]
    assert market_id == "a-share"
    assert instrument_id > 0
    assert provider_id == row["provider"]
    assert date_key == date(2099, 1, 5)
    assert period == "d"
    assert time == datetime(2099, 1, 5, 4, 0, tzinfo=timezone.utc)
    assert time.tzinfo is not None
    assert open_ == pytest.approx(1.0)
    assert high == pytest.approx(2.0)
    assert low == pytest.approx(0.5)
    assert close == pytest.approx(10.0)
    assert volume == pytest.approx(100.0)


def test_fx_rates_map_to_ohlc_and_volume_is_zero(dsn, dwd_cleanup):
    symbol = _unique_symbol("TEST-FX")
    dwd_cleanup.symbols.append(symbol)
    row = _fx_row(dwd_cleanup.provider_id, symbol, dwd_cleanup.batch_id)

    upsert_ods_rows(dsn, "fx", [row])
    build_dwd(dsn, "fx")

    rows = _fact_row(dsn, "fx", symbol)
    assert len(rows) == 1
    (
        market_id,
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
    ) = rows[0]
    assert market_id == "fx"
    assert provider_id == row["provider"]
    assert open_ == pytest.approx(row["open_rate"])
    assert high == pytest.approx(row["high_rate"])
    assert low == pytest.approx(row["low_rate"])
    assert close == pytest.approx(row["close_rate"])
    assert volume == 0.0


def test_fund_nav_backfills_ohlc(dsn, dwd_cleanup):
    symbol = _unique_symbol("TEST-FUND")
    dwd_cleanup.symbols.append(symbol)
    row = _fund_row(dwd_cleanup.provider_id, symbol, dwd_cleanup.batch_id)

    upsert_ods_rows(dsn, "fund", [row])
    build_dwd(dsn, "fund")

    rows = _fact_row(dsn, "fund", symbol)
    assert len(rows) == 1
    (
        market_id,
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
    ) = rows[0]
    assert market_id == "fund"
    assert open_ == pytest.approx(row["nav"])
    assert high == pytest.approx(row["nav"])
    assert low == pytest.approx(row["nav"])
    assert close == pytest.approx(row["nav"])
    assert volume == 0.0


def test_periods_are_normalized(dsn, dwd_cleanup):
    symbol = _unique_symbol("TEST-PERIOD")
    dwd_cleanup.symbols.append(symbol)
    provider_id = dwd_cleanup.provider_id
    batch_id = dwd_cleanup.batch_id
    rows = [
        _base_row(
            provider_id,
            "crypto",
            symbol,
            batch_id,
            interval="1d",
            open=1.0,
            high=2.0,
            low=0.5,
            close=10.0,
            volume=100.0,
        ),
        _base_row(
            provider_id,
            "crypto",
            symbol,
            batch_id,
            interval="1h",
            open=1.0,
            high=2.0,
            low=0.5,
            close=11.0,
            volume=110.0,
        ),
        _base_row(
            provider_id,
            "crypto",
            symbol,
            batch_id,
            interval="1w",
            open=1.0,
            high=2.0,
            low=0.5,
            close=12.0,
            volume=120.0,
        ),
    ]

    upsert_ods_rows(dsn, "crypto", rows)
    build_dwd(dsn, "crypto")

    rows = _fact_row(dsn, "crypto", symbol)
    assert [row[4] for row in rows] == ["d", "h", "w"]


def test_build_dwd_is_idempotent_and_updates_business_fields(dsn, dwd_cleanup):
    symbol = _unique_symbol("TEST-IDEMPOTENT")
    dwd_cleanup.symbols.append(symbol)
    row = _a_share_row(
        dwd_cleanup.provider_id,
        symbol,
        dwd_cleanup.batch_id,
    )
    updated_row = _a_share_row(
        dwd_cleanup.provider_id,
        symbol,
        dwd_cleanup.batch_id,
        close=12.0,
        volume=120.0,
        amount=240.0,
        open=1.2,
        high=2.2,
        low=0.6,
    )

    upsert_ods_rows(dsn, "a-share", [row])
    first = build_dwd(dsn, "a-share")
    upsert_ods_rows(dsn, "a-share", [updated_row])
    second = build_dwd(dsn, "a-share")

    rows = _fact_row(dsn, "a-share", symbol)
    assert first == 1
    assert second == 1
    assert len(rows) == 1
    (
        market_id,
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
    ) = rows[0]
    assert open_ == pytest.approx(1.2)
    assert high == pytest.approx(2.2)
    assert low == pytest.approx(0.6)
    assert close == pytest.approx(12.0)
    assert volume == pytest.approx(120.0)


def test_dimensions_are_backfilled_without_duplicates(dsn, dwd_cleanup):
    symbol = _unique_symbol("TEST-DIM")
    dwd_cleanup.symbols.append(symbol)
    provider_id = dwd_cleanup.provider_id
    row = _a_share_row(provider_id, symbol, dwd_cleanup.batch_id)

    upsert_ods_rows(dsn, "a-share", [row])
    first_instrument_id = build_dwd(dsn, "a-share")
    second_instrument_id = build_dwd(dsn, "a-share")

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM dim_market WHERE market_id = %s", ("a-share",))
        market_count = cur.fetchone()[0]
        cur.execute(
            "SELECT count(*) FROM dim_provider WHERE provider_id = %s",
            (provider_id,),
        )
        provider_count = cur.fetchone()[0]
        cur.execute(
            "SELECT count(*) FROM dim_date WHERE date_key = %s",
            (date(2099, 1, 5),),
        )
        date_count = cur.fetchone()[0]
        cur.execute(
            """
            SELECT count(*)
            FROM dim_instrument
            WHERE market_id = %s AND symbol = %s
            """,
            ("a-share", symbol),
        )
        instrument_count = cur.fetchone()[0]

    assert first_instrument_id == 1
    assert second_instrument_id == 1
    assert market_count == 1
    assert provider_count == 1
    assert date_count == 1
    assert instrument_count == 1


def test_unknown_market_raises_value_error(dsn, dwd_cleanup):
    with pytest.raises(ValueError, match="unknown market"):
        build_dwd(dsn, "unknown")
