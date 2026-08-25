"""Daily incremental sync for external indicator sources."""
from __future__ import annotations

from datetime import date, timedelta
import logging
import os
from typing import Any, Callable

from etl.build_indicator import build_indicators
from etl.db import connect
from etl.load_external import upsert_external_rows
from etl.migrate_seed import _new_batch_id, DEFAULT_DSN
from etl.sources import akshare_cn, coingecko, sec_edgar, worldbank


logger = logging.getLogger(__name__)


def get_watermark(conn: Any, scope: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute("SELECT last_value FROM etl_watermarks WHERE scope = %s", (scope,))
        row = cur.fetchone()
    return row[0] if row else None


def set_watermark(conn: Any, scope: str, value: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO etl_watermarks (scope, last_value, updated_at)
            VALUES (%s, %s, now())
            ON CONFLICT (scope) DO UPDATE SET
              last_value = EXCLUDED.last_value, updated_at = now()
            """,
            (scope, value),
        )


def _run_source(
    dsn: str, batch_id: str, fn: Callable[[Any, str], dict[str, Any]]
) -> dict[str, Any]:
    with connect(dsn) as conn:
        try:
            stats = fn(conn, batch_id)
            conn.commit()
            return {**stats, "status": "ok"}
        except Exception as exc:  # noqa: BLE001 - 单源失败不阻塞其他源
            conn.rollback()
            logger.warning("external source failed: %s", exc)
            return {"status": "error", "error": str(exc)}


def sync_coingecko(conn: Any, batch_id: str) -> dict[str, Any]:
    today = date.today().isoformat()
    scope = f"coingecko:snapshot:{today}"
    if get_watermark(conn, scope) is not None:
        return {"rows": 0}
    coin_ids = ["bitcoin", "ethereum", "solana", "binancecoin"]
    rows = [
        {**row, "raw_payload": {}, "sync_batch_id": batch_id}
        for row in coingecko.parse_markets(coingecko.fetch_markets(coin_ids), today)
    ]
    if rows:
        upsert_external_rows(conn, "crypto_meta", rows)
        build_indicators(conn, "crypto")
    set_watermark(conn, scope, today)
    return {"rows": len(rows)}


def sync_sec(conn: Any, batch_id: str) -> dict[str, Any]:
    ciks = ["0000320193", "0001045810", "0000789019", "0001318605"]  # AAPL NVDA MSFT TSLA
    submissions_rows = []
    facts_rows = []
    for cik in ciks:
        scope = f"sec:cik:{cik}"
        if get_watermark(conn, scope) is not None:
            continue
        submissions_rows.append(
            {
                **sec_edgar.parse_submissions(sec_edgar.fetch_submissions(cik)),
                "raw_payload": {},
                "sync_batch_id": batch_id,
            }
        )
        facts_rows.extend(
            {**row, "raw_payload": {}, "sync_batch_id": batch_id}
            for row in sec_edgar.parse_facts(sec_edgar.fetch_company_facts(cik))
        )
        set_watermark(conn, scope, date.today().isoformat())
    if submissions_rows:
        upsert_external_rows(conn, "sec_submissions", submissions_rows)
    if facts_rows:
        upsert_external_rows(conn, "sec_facts", facts_rows)
        build_indicators(conn, "sec")
    return {"submissions": len(submissions_rows), "facts": len(facts_rows)}


def sync_worldbank(conn: Any, batch_id: str) -> dict[str, Any]:
    indicators = ["NY.GDP.MKTP.CD", "FP.CPI.TOTL.ZG", "FR.INR.LEND"]
    rows = []
    for code in indicators:
        scope = f"worldbank:series:{code}"
        if get_watermark(conn, scope) is not None:
            continue
        rows.extend(
            {**row, "raw_payload": {}, "sync_batch_id": batch_id}
            for row in worldbank.parse_indicator(worldbank.fetch_indicator("CN", code))
        )
        set_watermark(conn, scope, date.today().isoformat())
    if rows:
        upsert_external_rows(conn, "macro_indicators", rows)
        build_indicators(conn, "macro")
    return {"rows": len(rows)}


def sync_akshare(conn: Any, batch_id: str) -> dict[str, Any]:
    symbols = ["600519", "000001", "300750", "601318", "600036"]
    finance_rows = []
    for symbol in symbols:
        scope = f"akshare:finance:{symbol}"
        if get_watermark(conn, scope) is not None:
            continue
        finance_rows.extend(
            {**row, "raw_payload": {}, "sync_batch_id": batch_id}
            for row in akshare_cn.parse_financials(
                akshare_cn.fetch_financials(symbol), symbol
            )
        )
        set_watermark(conn, scope, date.today().isoformat())
    if finance_rows:
        upsert_external_rows(conn, "cn_financials", finance_rows)
        build_indicators(conn, "cn-finance")

    lhb_rows = []
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=29)
    lhb_scope = "akshare:lhb"
    last = get_watermark(conn, lhb_scope)
    if last:
        start = max(start, date.fromisoformat(last) + timedelta(days=1))
    if start <= end:
        lhb_rows.extend(
            {**row, "raw_payload": {}, "sync_batch_id": batch_id}
            for row in akshare_cn.parse_lhb(
                akshare_cn.fetch_lhb(
                    start.isoformat().replace("-", ""),
                    end.isoformat().replace("-", ""),
                )
            )
        )
        if lhb_rows:
            upsert_external_rows(conn, "cn_lhb", lhb_rows)
            build_indicators(conn, "cn-lhb")
        set_watermark(conn, lhb_scope, end.isoformat())
    return {"finance": len(finance_rows), "lhb": len(lhb_rows)}


def sync_external(dsn: str, batch_id: str | None = None) -> dict[str, Any]:
    batch_id = batch_id or _new_batch_id()
    return {
        "coingecko": _run_source(dsn, batch_id, sync_coingecko),
        "sec": _run_source(dsn, batch_id, sync_sec),
        "worldbank": _run_source(dsn, batch_id, sync_worldbank),
        "akshare": _run_source(dsn, batch_id, sync_akshare),
    }


def main() -> None:
    dsn = os.environ.get("WAREHOUSE_DSN", DEFAULT_DSN)
    stats = sync_external(dsn)
    for source, result in stats.items():
        print(f"{source}: {result}")


if __name__ == "__main__":
    main()
