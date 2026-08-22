"""Screening helpers: translating analysis results into user-facing reasons."""
from __future__ import annotations

from application.ports import MacroNewsProvider


REASON_LABELS = {
    "technical": "技术指标",
    "macro": "宏观分析",
    "geopolitics": "地缘政治",
    "fund_flow": "资金流向",
    "policy": "政策事件",
    "industry": "行业事件",
    "risk": "风险提示",
}


def asset_type(item: dict) -> str:
    market = item["market"]
    symbol = item["symbol"]
    if market == "fx":
        return "外汇对"
    if market == "crypto":
        return "数字货币对"
    if market == "fund":
        return "指数ETF" if symbol.startswith(("15", "51")) else "场外基金"
    if market == "us" and symbol == "SPY":
        return "股票ETF"
    return "股票"


def market_name(market_id: str) -> str:
    return {
        "a-share": "A股", "fund": "基金", "us": "美股", "kr": "韩股",
        "hk": "港股", "fx": "外汇", "crypto": "数字货币",
    }.get(market_id, market_id)


def _reason_from_news(news: dict, market_name: str) -> dict:
    tags = set(news["tags"])
    if tags & {"政策", "利率"}:
        reason_type = "policy"
        base_weight = 68
    elif tags & {"资金流", "南向资金", "ETF"}:
        reason_type = "fund_flow"
        base_weight = 66
    elif tags & {"半导体", "原油"}:
        reason_type = "industry"
        base_weight = 62
    else:
        reason_type = "geopolitics"
        base_weight = 55
    weight = round(base_weight + float(news.get("sentiment", 0)) * 40)
    weight = max(35, min(weight, 96))
    return {
        "type": reason_type,
        "label": REASON_LABELS[reason_type],
        "title": news["title"],
        "detail": f"事件来自{news['source']}，与{market_name}的{('、'.join(sorted(tags)[:2]))}主题相关。",
        "weight": weight,
    }


def build_reasons(item: dict, analysis: dict, macro_news: MacroNewsProvider) -> list[dict]:
    market_id = item["market"]
    market_label = market_name(market_id)
    reasons: list[dict] = []
    if analysis["trend_score"] >= 60:
        reasons.append({
            "type": "technical", "label": REASON_LABELS["technical"],
            "title": "趋势结构占优",
            "detail": "短期与中期均线呈多头排列，价格运行于 20 日均线上方。",
            "weight": round(52 + analysis["trend_score"] * 0.35),
        })
    if analysis["macd_hist"] is not None and analysis["macd_hist"] > 0:
        reasons.append({
            "type": "technical", "label": REASON_LABELS["technical"],
            "title": "MACD 动能转强",
            "detail": f"MACD 柱值为 {analysis['macd_hist']:.3f}，短周期动能位于零轴上方。",
            "weight": round(42 + analysis["momentum_score"] * 0.42),
        })
    rsi = analysis["rsi14"]
    if rsi is not None:
        if 45 <= rsi <= 65:
            reasons.append({
                "type": "technical", "label": REASON_LABELS["technical"],
                "title": "RSI 强势但不超买",
                "detail": f"RSI14 为 {rsi:.1f}，处于趋势偏强且未过热的位置。",
                "weight": 63,
            })
        elif rsi > 70:
            reasons.append({
                "type": "risk", "label": REASON_LABELS["risk"],
                "title": "短线动能偏热",
                "detail": f"RSI14 达到 {rsi:.1f}，若追高需要关注回撤风险。",
                "weight": 54,
            })
    if analysis["change_20d"] > 3:
        reasons.append({
            "type": "technical", "label": REASON_LABELS["technical"],
            "title": "20 日动量为正",
            "detail": f"近 20 个交易日上涨 {analysis['change_20d']:.1f}%。",
            "weight": round(45 + min(analysis["change_20d"] * 1.1, 28)),
        })
    bias = macro_news.market_bias(market_id)
    if bias:
        reasons.append({
            "type": "macro", "label": REASON_LABELS["macro"],
            "title": f"{market_label}宏观因子占优",
            "detail": bias["label"],
            "weight": round(float(bias["score"]) * 0.92),
        })
    used_titles = {reason["title"] for reason in reasons}
    for news in macro_news.news_items(market_id):
        reason = _reason_from_news(news, market_label)
        if reason["title"] in used_titles:
            continue
        used_titles.add(reason["title"])
        reasons.append(reason)
        if len(reasons) >= 7:
            break
    if not reasons:
        reasons.append({
            "type": "technical", "label": REASON_LABELS["technical"],
            "title": "波动水平适配",
            "detail": "当前波动率与标的类型匹配，适合纳入观察组合。",
            "weight": 42,
        })
    reasons.sort(key=lambda reason: reason["weight"], reverse=True)
    return reasons[:7]
