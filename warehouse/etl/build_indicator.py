"""Build dim_indicator / fact_indicator from external ODS tables."""
from __future__ import annotations

from datetime import date
from typing import Any, Iterator

from psycopg.rows import dict_row


def _parse_date(value: str) -> date:
    text = str(value).strip()
    if len(text) == 4:  # World Bank 年份
        return date(int(text), 1, 1)
    return date.fromisoformat(text)


def _iter_rows(cur: Any, source: str) -> Iterator[tuple[str, str, str | None, str, date, float]]:
    """Yield (source_key, name, unit, ref_key, as_of_date, value)."""
    if source == "crypto":
        cur.execute(
            """
            SELECT coin_id, snapshot_date, current_price, market_cap, total_volume
            FROM ods_crypto_meta
            """
        )
        for row in cur.fetchall():
            coin_id = row["coin_id"]
            snapshot = row["snapshot_date"]
            price = row["current_price"]
            cap = row["market_cap"]
            volume = row["total_volume"]
            for source_key, name, value in (
                ("current_price", "当前价格", price),
                ("market_cap", "市值", cap),
                ("total_volume", "24h 成交量", volume),
            ):
                if value is None:
                    continue
                yield source_key, name, "USD", coin_id, snapshot, value
    elif source == "macro":
        cur.execute(
            """
            SELECT indicator_code, indicator_name, country_code, date, value
            FROM ods_macro_indicators
            """
        )
        for row in cur.fetchall():
            code = row["indicator_code"]
            name = row["indicator_name"]
            country = row["country_code"]
            period = row["date"]
            value = row["value"]
            yield code, name, None, country, _parse_date(period), value
    elif source == "sec":
        cur.execute(
            "SELECT concept, unit, cik, period_end, value FROM ods_sec_facts"
        )
        for row in cur.fetchall():
            concept = row["concept"]
            unit = row["unit"]
            cik = row["cik"]
            period_end = row["period_end"]
            value = row["value"]
            yield concept, concept, unit, cik, period_end, value
    elif source == "cn-finance":
        cur.execute(
            """
            SELECT indicator_name, symbol, report_date, indicator_value
            FROM ods_cn_financials
            """
        )
        for row in cur.fetchall():
            name = row["indicator_name"]
            symbol = row["symbol"]
            period = row["report_date"]
            value = row["indicator_value"]
            yield name, name, None, symbol, _parse_date(period), value
    elif source == "cn-lhb":
        cur.execute(
            "SELECT code, trade_date, close_price, change_pct FROM ods_cn_lhb"
        )
        for row in cur.fetchall():
            code = row["code"]
            trade_date = row["trade_date"]
            close_price = row["close_price"]
            change_pct = row["change_pct"]
            for source_key, name, value in (
                ("close_price", "龙虎榜收盘价", close_price),
                ("change_pct", "龙虎榜涨跌幅", change_pct),
            ):
                if value is None:
                    continue
                yield source_key, name, None, code, _parse_date(trade_date), value
    else:
        raise ValueError(f"unknown indicator source: {source}")


def build_indicators(conn: Any, source: str) -> int:
    """Upsert dim/fact indicators from one ODS source on an open connection."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT indicator_id, source_key FROM dim_indicator WHERE source = %s",
            (source,),
        )
        cache = {row["source_key"]: row["indicator_id"] for row in cur.fetchall()}
        affected = 0
        for source_key, name, unit, ref_key, as_of_date, value in _iter_rows(cur, source):
            indicator_id = cache.get(source_key)
            if indicator_id is None:
                cur.execute(
                    """
                    INSERT INTO dim_indicator (source, source_key, name, unit)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (source, source_key) DO UPDATE SET
                      name = EXCLUDED.name, unit = EXCLUDED.unit
                    RETURNING indicator_id
                    """,
                    (source, source_key, name, unit),
                )
                indicator_id = cur.fetchone()["indicator_id"]
                cache[source_key] = indicator_id
            cur.execute(
                """
                INSERT INTO fact_indicator (indicator_id, ref_key, as_of_date, value)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (indicator_id, ref_key, as_of_date) DO UPDATE SET
                  value = EXCLUDED.value
                """,
                (indicator_id, ref_key, as_of_date, value),
            )
            affected += cur.rowcount
        return affected
