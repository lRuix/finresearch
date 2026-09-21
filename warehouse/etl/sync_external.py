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
from etl.sources import akshare_cn, coingecko, eastmoney_cn, sec_edgar, sina_cn, worldbank


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


def iso_week(today: date | None = None) -> str:
    """返回 ISO 周标识，如 '2026-W39'，用作周粒度的水位线值。"""
    iso = (today or date.today()).isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


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
    week = iso_week()
    for cik in ciks:
        scope = f"sec:cik:{cik}"
        if get_watermark(conn, scope) == week:
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
        set_watermark(conn, scope, week)
    if submissions_rows:
        upsert_external_rows(conn, "sec_submissions", submissions_rows)
    if facts_rows:
        upsert_external_rows(conn, "sec_facts", facts_rows)
        build_indicators(conn, "sec")
    return {"submissions": len(submissions_rows), "facts": len(facts_rows)}


def sync_worldbank(conn: Any, batch_id: str) -> dict[str, Any]:
    indicators = ["NY.GDP.MKTP.CD", "FP.CPI.TOTL.ZG", "FR.INR.LEND"]
    rows = []
    week = iso_week()
    for code in indicators:
        scope = f"worldbank:series:{code}"
        if get_watermark(conn, scope) == week:
            continue
        rows.extend(
            {**row, "raw_payload": {}, "sync_batch_id": batch_id}
            for row in worldbank.parse_indicator(worldbank.fetch_indicator("CN", code))
        )
        set_watermark(conn, scope, week)
    if rows:
        upsert_external_rows(conn, "macro_indicators", rows)
        build_indicators(conn, "macro")
    return {"rows": len(rows)}


def sync_akshare(conn: Any, batch_id: str) -> dict[str, Any]:
    symbols = ["600519", "000001", "300750", "601318", "600036"]
    finance_rows = []
    week = iso_week()
    for symbol in symbols:
        scope = f"akshare:finance:{symbol}"
        if get_watermark(conn, scope) == week:
            continue
        finance_rows.extend(
            {**row, "raw_payload": {}, "sync_batch_id": batch_id}
            for row in akshare_cn.parse_financials(
                akshare_cn.fetch_financials(symbol), symbol
            )
        )
        set_watermark(conn, scope, week)
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


METRICS_SCOPE = "cn-daily:metrics"


def _rewind_metrics_watermark(conn: Any, earliest_change: str) -> None:
    """股本回填历史日期时回退派生指标水位线，强制重算受影响区间。

    否则该区间内的市值/换手率会沿用变更前的股本，静默算错。
    """
    last = get_watermark(conn, METRICS_SCOPE)
    if last is None or earliest_change < last:
        set_watermark(conn, METRICS_SCOPE, earliest_change)


def _new_change_dates(conn: Any, rows: list[dict[str, Any]]) -> set[str]:
    """返回 rows 中表内尚不存在的变更日期集合（本次真正新增/回填）。

    全市场每周重抓完整变更历史，rows 含大量已存在记录；回退目标只能取
    本次新增的最小日期，否则会把派生指标水位线打到远古上市日。
    """
    pairs = {(row["symbol"], row["change_date"]) for row in rows}
    if not pairs:
        return set()
    existing: set[tuple[str, str]] = set()
    pair_list = list(pairs)
    with conn.cursor() as cur:
        for start in range(0, len(pair_list), 500):
            chunk = pair_list[start : start + 500]
            placeholders = ", ".join("(%s, %s)" for _ in chunk)
            params: list[Any] = []
            for symbol, change_date in chunk:
                params.extend((symbol, change_date))
            cur.execute(
                f"SELECT symbol, change_date FROM ods_cn_share_structure "
                f"WHERE (symbol, change_date) IN ({placeholders})",
                params,
            )
            existing.update((row[0], row[1]) for row in cur.fetchall())
    return {change_date for symbol, change_date in pairs if (symbol, change_date) not in existing}


def _a_share_universe() -> list[str]:
    """全 A 股 6 位代码清单。改用 akshare 代码表而非东财快照（后者当前不可用）。"""
    import akshare  # lazy: heavy dependency

    frame = akshare.stock_info_a_code_name()
    return [str(code).strip() for code in frame["code"].tolist()]


def sync_balance_sheet(conn: Any, batch_id: str) -> dict[str, Any]:
    week = iso_week()
    rows: list[dict[str, Any]] = []
    failed = 0
    for symbol in _a_share_universe():
        scope = f"cn-balance:{symbol}"
        if get_watermark(conn, scope) == week:
            continue
        try:
            parsed = list(
                sina_cn.parse_balance_sheet(sina_cn.fetch_balance_sheet(symbol), symbol)
            )
        except Exception as exc:  # noqa: BLE001 - 单只失败不阻塞全市场
            failed += 1
            logger.warning("balance sheet failed for %s: %s", symbol, exc)
            continue
        rows.extend(
            {**row, "raw_payload": {}, "sync_batch_id": batch_id} for row in parsed
        )
        set_watermark(conn, scope, week)
    if rows:
        upsert_external_rows(conn, "cn_balance", rows)
        build_indicators(conn, "cn-balance")
    return {"rows": len(rows), "failed": failed}


def sync_share_structure(conn: Any, batch_id: str) -> dict[str, Any]:
    week = iso_week()
    rows: list[dict[str, Any]] = []
    failed = 0
    for symbol in _a_share_universe():
        scope = f"cn-share:{symbol}"
        if get_watermark(conn, scope) == week:
            continue
        try:
            parsed = list(
                eastmoney_cn.parse_share_structure(
                    eastmoney_cn.fetch_share_structure(symbol), symbol
                )
            )
        except Exception as exc:  # noqa: BLE001 - 单只失败不阻塞全市场
            failed += 1
            logger.warning("share structure failed for %s: %s", symbol, exc)
            continue
        rows.extend(
            {**row, "raw_payload": {}, "sync_batch_id": batch_id} for row in parsed
        )
        set_watermark(conn, scope, week)
    if rows:
        new_dates = _new_change_dates(conn, rows)
        upsert_external_rows(conn, "cn_share_structure", rows)
        if new_dates:
            _rewind_metrics_watermark(conn, min(new_dates))
    return {"rows": len(rows), "failed": failed}


def sync_external(dsn: str, batch_id: str | None = None) -> dict[str, Any]:
    batch_id = batch_id or _new_batch_id()
    stats = {
        "coingecko": _run_source(dsn, batch_id, sync_coingecko),
        "sec": _run_source(dsn, batch_id, sync_sec),
        "worldbank": _run_source(dsn, batch_id, sync_worldbank),
        "akshare": _run_source(dsn, batch_id, sync_akshare),
        "cn-balance": _run_source(dsn, batch_id, sync_balance_sheet),
        "cn-share": _run_source(dsn, batch_id, sync_share_structure),
    }
    with connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("REFRESH MATERIALIZED VIEW dws_indicator_daily")
        conn.commit()
    return stats


def main() -> None:
    dsn = os.environ.get("WAREHOUSE_DSN", DEFAULT_DSN)
    stats = sync_external(dsn)
    for source, result in stats.items():
        print(f"{source}: {result}")


if __name__ == "__main__":
    main()
