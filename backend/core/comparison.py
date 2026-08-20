"""跨资产比较编排：RMB 口径风险调整后收益排序。"""
from __future__ import annotations

from core.valuation.constraints import QUOTA_USD_YEARLY, quota_note, requires_quota
from core.valuation.metrics import (
    annualized_return, calmar_ratio, max_drawdown, sharpe_ratio,
)


def compare_assets(assets: list[dict]) -> list[dict]:
    """对已折算 RMB 的资产序列做风险调整后收益排序。

    assets 每项需含：symbol/name/market/currency/rmb_closes（RMB 口径收盘价序列）。
    返回按 calmar_ratio 降序（None 置底），附额度提示。
    """
    results = []
    for a in assets:
        closes = a["rmb_closes"]
        calmar = calmar_ratio(closes)
        item = {
            "symbol": a["symbol"],
            "name": a["name"],
            "market": a["market"],
            "currency": a["currency"],
            "rmb_annual_return": round(annualized_return(closes), 4),
            "max_drawdown": round(max_drawdown(closes), 4),
            "calmar_ratio": round(calmar, 4) if calmar is not None else None,
            "sharpe_ratio": round(sharpe_ratio(closes), 4),
            "requires_quota": requires_quota(a["market"]),
            "quota_note": quota_note(0.0) if requires_quota(a["market"]) else "",
        }
        results.append(item)

    # 按卡玛降序，None 置底
    results.sort(key=lambda r: (r["calmar_ratio"] is None, -(r["calmar_ratio"] or 0)))
    return results
