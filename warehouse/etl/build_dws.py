"""DWS materialized view refresh helpers."""
from __future__ import annotations

from etl.db import connect


def refresh_dws(dsn: str) -> None:
    """Refresh DWS materialized views in dependency order."""
    with connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("REFRESH MATERIALIZED VIEW dws_instrument_daily")
        cur.execute("REFRESH MATERIALIZED VIEW dws_market_daily")
        conn.commit()
