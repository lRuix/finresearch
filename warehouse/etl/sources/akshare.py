"""akshare kline source."""
from __future__ import annotations

from etl.sources.common import aggregate_weekly, parse_ts


def _ak():
    import akshare  # lazy: heavy dependency

    return akshare


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _period_name(period):
    if period == "h":
        raise ValueError("akshare does not provide hourly klines")
    return {"d": "daily", "w": "weekly"}[period]


def _ohlcv_rows(frame):
    rows = []
    for _, row in frame.iterrows():
        rows.append(
            {
                "time": str(row["日期"]),
                "open": _to_float(row.get("开盘")),
                "high": _to_float(row.get("最高")),
                "low": _to_float(row.get("最低")),
                "close": _to_float(row.get("收盘")),
                "volume": _to_float(row.get("成交量")),
                "amount": _to_float(row.get("成交额")),
                "amplitude": _to_float(row.get("振幅")),
                "change_pct": _to_float(row.get("涨跌幅")),
                "change_amount": _to_float(row.get("涨跌额")),
                "turnover_rate": _to_float(row.get("换手率")),
            }
        )
    return rows


def _raw_klines(market, symbol, period, limit):
    ak = _ak()
    if market == "a-share":
        frame = ak.stock_zh_a_hist(
            symbol=symbol,
            period=_period_name(period),
            adjust="qfq",
        )
        return _ohlcv_rows(frame)[-limit:]
    if market == "fund":
        if symbol.isdigit() and symbol.startswith(("15", "51")):
            frame = ak.fund_etf_hist_em(
                symbol=symbol,
                period=_period_name(period),
                adjust="qfq",
            )
            return _ohlcv_rows(frame)[-limit:]
        frame = ak.fund_open_fund_info_em(
            symbol=symbol,
            indicator="单位净值走势",
        )
        rows = []
        for _, row in frame.iterrows():
            nav = _to_float(row.get("单位净值"))
            rows.append(
                {
                    "time": str(row.get("净值日期", "")),
                    "nav": nav,
                    "accum_nav": _to_float(row.get("累计净值")),
                    "daily_growth_pct": _to_float(row.get("日增长率")),
                    "purchase_status": str(row.get("申购状态", "")),
                    "redeem_status": str(row.get("赎回状态", "")),
                    "open": nav,
                    "high": nav,
                    "low": nav,
                    "close": nav,
                    "volume": 0.0,
                }
            )
        if period == "w":
            features = {
                row["time"]: {
                    "nav": row["nav"],
                    "accum_nav": row["accum_nav"],
                    "daily_growth_pct": row["daily_growth_pct"],
                    "purchase_status": row["purchase_status"],
                    "redeem_status": row["redeem_status"],
                }
                for row in rows
            }
            rows = aggregate_weekly(rows)
            for row in rows:
                row.update(features.get(row["time"], {}))
        return rows[-limit:]
    raise ValueError(f"akshare does not support market {market}")


def fetch_klines(market, symbol, period="d", start=None, end=None, limit=1000):
    rows = _raw_klines(market, symbol, period, limit)
    if start:
        rows = [r for r in rows if parse_ts(r["time"]) >= parse_ts(start)]
    if end:
        rows = [r for r in rows if parse_ts(r["time"]) <= parse_ts(end)]
    return rows
