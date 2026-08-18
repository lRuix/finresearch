"""Global screener combining technical and macro factors."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from core import macro
from core.indicators import analyze
from core.providers import get_kline
from core.universe import universe_for


def _asset_type(item: dict) -> str:
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


REASON_LABELS = {
    "technical": "技术指标",
    "macro": "宏观分析",
    "geopolitics": "地缘政治",
    "fund_flow": "资金流向",
    "policy": "政策事件",
    "industry": "行业事件",
    "risk": "风险提示",
}


def _news_for_market(market_id: str) -> list[dict]:
    tags = {
        "a-share": {"A股", "政策", "信用"},
        "fund": {"A股", "政策", "ETF"},
        "us": {"美股", "利率", "美元", "全球"},
        "kr": {"韩股", "半导体", "汇率", "全球"},
        "hk": {"港股", "南向资金", "政策"},
        "fx": {"汇率", "美元", "利率", "全球"},
        "crypto": {"数字货币", "ETF", "全球"},
    }
    wanted = tags.get(market_id, {"全球"})
    return [news for news in macro.NEWS_ITEMS if set(news["tags"]) & wanted]


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
    matched_tags = sorted(tags)
    return {
        "type": reason_type,
        "label": REASON_LABELS[reason_type],
        "title": news["title"],
        "detail": f"事件来自{news['source']}，与{market_name}的{('、'.join(matched_tags[:2]))}主题相关。",
        "weight": weight,
    }


def _build_reasons(item: dict, analysis: dict) -> list[dict]:
    market_id = item["market"]
    market_name = _market_name(market_id)
    reasons: list[dict] = []

    if analysis["trend_score"] >= 60:
        reasons.append(
            {
                "type": "technical",
                "label": REASON_LABELS["technical"],
                "title": "趋势结构占优",
                "detail": "短期与中期均线呈多头排列，价格运行于 20 日均线上方。",
                "weight": round(52 + analysis["trend_score"] * 0.35),
            }
        )
    if analysis["macd_hist"] is not None and analysis["macd_hist"] > 0:
        reasons.append(
            {
                "type": "technical",
                "label": REASON_LABELS["technical"],
                "title": "MACD 动能转强",
                "detail": f"MACD 柱值为 {analysis['macd_hist']:.3f}，短周期动能位于零轴上方。",
                "weight": round(42 + analysis["momentum_score"] * 0.42),
            }
        )

    rsi = analysis["rsi14"]
    if rsi is not None:
        if 45 <= rsi <= 65:
            reasons.append(
                {
                    "type": "technical",
                    "label": REASON_LABELS["technical"],
                    "title": "RSI 强势但不超买",
                    "detail": f"RSI14 为 {rsi:.1f}，处于趋势偏强且未过热的位置。",
                    "weight": 63,
                }
            )
        elif rsi > 70:
            reasons.append(
                {
                    "type": "risk",
                    "label": REASON_LABELS["risk"],
                    "title": "短线动能偏热",
                    "detail": f"RSI14 达到 {rsi:.1f}，若追高需要关注回撤风险。",
                    "weight": 54,
                }
            )

    if analysis["change_20d"] > 3:
        reasons.append(
            {
                "type": "technical",
                "label": REASON_LABELS["technical"],
                "title": "20 日动量为正",
                "detail": f"近 20 个交易日上涨 {analysis['change_20d']:.1f}%。",
                "weight": round(45 + min(analysis["change_20d"] * 1.1, 28)),
            }
        )

    bias = macro.MARKET_BIAS.get(market_id)
    if bias:
        reasons.append(
            {
                "type": "macro",
                "label": REASON_LABELS["macro"],
                "title": f"{market_name}宏观因子占优",
                "detail": bias["label"],
                "weight": round(float(bias["score"]) * 0.92),
            }
        )

    used_titles = {reason["title"] for reason in reasons}
    event_reasons: list[dict] = []
    for news in _news_for_market(market_id):
        reason = _reason_from_news(news, market_name)
        if reason["title"] in used_titles:
            continue
        used_titles.add(reason["title"])
        event_reasons.append(reason)
        if len(event_reasons) >= 3:
            break

    reasons.extend(event_reasons)

    if len(reasons) == 0:
        reasons.append(
            {
                "type": "technical",
                "label": REASON_LABELS["technical"],
                "title": "波动水平适配",
                "detail": "当前波动率与标的类型匹配，适合纳入观察组合。",
                "weight": 42,
            }
        )

    reasons.sort(key=lambda reason: reason["weight"], reverse=True)
    return reasons[:7]


def _compute_results(
    market: str = "all",
    min_score: float = 0,
    max_risk: float = 100,
    min_trend: float = 0,
    min_momentum: float = 0,
    min_rsi: float = 0,
    max_rsi: float = 100,
) -> tuple[list[dict], int]:
    items = universe_for(market)

    def build_candidate(item: dict) -> dict | None:
        klines = get_kline(item["market"], item["symbol"], "d", 180, prefer_real=True)
        enriched = dict(item)
        enriched["macro_score"] = macro.macro_score_for(item["market"])
        analysis = analyze(klines, enriched)
        if "error" in analysis:
            return None

        rsi = analysis["rsi14"] or 50
        risk = (1 - item["base_risk"]) * 100
        if (
            analysis["total_score"] < min_score
            or risk > max_risk
            or analysis["trend_score"] < min_trend
            or analysis["momentum_score"] < min_momentum
            or rsi < min_rsi
            or rsi > max_rsi
        ):
            return None

        return {
            "symbol": item["symbol"],
            "name": item["name"],
            "market": item["market"],
            "market_name": _market_name(item["market"]),
            "asset_type": _asset_type(item),
            "sector": item["sector"],
            "currency": item["currency"],
            "price": analysis["price"],
            "change_1d": analysis["change_1d"],
            "change_20d": analysis["change_20d"],
            "rsi14": analysis["rsi14"],
            "trend_score": analysis["trend_score"],
            "momentum_score": analysis["momentum_score"],
            "volatility20": analysis["volatility20"],
            "macro_score": analysis["macro_score"],
            "total_score": analysis["total_score"],
            "signals": analysis["signals"][:3],
            "reasons": _build_reasons(item, analysis),
        }

    with ThreadPoolExecutor(max_workers=5) as executor:
        candidates = list(executor.map(build_candidate, items))
    results = [candidate for candidate in candidates if candidate is not None]

    return results, len(items)


def screen(
    market: str = "all",
    min_score: float = 0,
    max_risk: float = 100,
    min_trend: float = 0,
    min_momentum: float = 0,
    min_rsi: float = 0,
    max_rsi: float = 100,
    sort_by: str = "total_score",
    limit: int = 60,
) -> dict:
    results, total_universe = _compute_results(
        market=market,
        min_score=min_score,
        max_risk=max_risk,
        min_trend=min_trend,
        min_momentum=min_momentum,
        min_rsi=min_rsi,
        max_rsi=max_rsi,
    )

    allowed_sort = {
        "total_score": "total_score",
        "change_20d": "change_20d",
        "rsi14": "rsi14",
        "trend_score": "trend_score",
    }
    key = allowed_sort.get(sort_by, "total_score")
    results.sort(key=lambda item: item[key], reverse=True)
    return {"items": results[:limit], "count": len(results), "total_universe": total_universe}


def recommend(limit: int = 10) -> dict:
    results, total_universe = _compute_results(market="all")
    quotas = {
        "a-share": 2,
        "us": 2,
        "kr": 1,
        "hk": 1,
        "fund": 1,
        "fx": 1,
        "crypto": 2,
    }

    picked: list[dict] = []
    picked_keys: set[tuple[str, str]] = set()

    for market_id, quota in quotas.items():
        group = [item for item in results if item["market"] == market_id]
        group.sort(key=lambda item: item["total_score"], reverse=True)
        for item in group[:quota]:
            picked.append(item)
            picked_keys.add((item["market"], item["symbol"]))

    remaining = [
        item
        for item in results
        if (item["market"], item["symbol"]) not in picked_keys
    ]
    remaining.sort(key=lambda item: item["total_score"], reverse=True)
    for item in remaining:
        if len(picked) >= limit:
            break
        picked.append(item)
        picked_keys.add((item["market"], item["symbol"]))

    # 保证首页始终同时出现具体股票、外汇对与数字货币对
    market_presence = {item["market"] for item in picked}
    for required in ("fx", "crypto"):
        if required in market_presence:
            continue
        fallback = next(
            (item for item in results if item["market"] == required),
            None,
        )
        if fallback is not None:
            lowest = min(picked, key=lambda item: item["total_score"])
            picked.remove(lowest)
            picked.append(fallback)
            market_presence.add(required)

    picked.sort(key=lambda item: item["total_score"], reverse=True)
    return {"items": picked[:limit], "count": len(picked[:limit]), "total_universe": total_universe}


def _market_name(market_id: str) -> str:
    names = {
        "a-share": "A股",
        "fund": "基金",
        "us": "美股",
        "kr": "韩股",
        "hk": "港股",
        "fx": "外汇",
        "crypto": "数字货币",
    }
    return names.get(market_id, market_id)
