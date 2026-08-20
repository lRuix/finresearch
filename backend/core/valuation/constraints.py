"""硬约束：购汇额度与合规。"""
from __future__ import annotations

# 个人便利化购汇额度：每人每年等值 5 万美元
QUOTA_USD_YEARLY = 50_000

# 需购汇的市场（本币非人民币）
_QUOTA_MARKETS = {"us", "hk", "kr", "fx", "crypto"}


def requires_quota(market: str) -> bool:
    return market in _QUOTA_MARKETS


def quota_note(cumulative_quota_usd: float) -> str:
    """根据累计占用购汇额度生成提示。"""
    if cumulative_quota_usd > QUOTA_USD_YEARLY:
        over = cumulative_quota_usd - QUOTA_USD_YEARLY
        return f"已超出年度购汇额度（5 万美元），超出约 {over:,.0f} 美元"
    remaining = QUOTA_USD_YEARLY - cumulative_quota_usd
    return f"占用购汇额度（年度限额 5 万美元），剩余约 {remaining:,.0f} 美元"
