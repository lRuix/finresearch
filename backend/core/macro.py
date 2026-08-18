"""Macro snapshot, news feed adapter and market bias mapping."""

from __future__ import annotations

from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


MACRO_SNAPSHOT = [
    {"key": "dxy", "name": "美元指数", "value": "103.82", "change": "+0.14", "direction": "up", "kind": "index"},
    {"key": "us10y", "name": "美国 10Y", "value": "4.18%", "change": "-0.03", "direction": "down", "kind": "rate"},
    {"key": "gold", "name": "黄金", "value": "2418", "change": "-0.5%", "direction": "down", "kind": "commodity"},
    {"key": "wti", "name": "WTI 原油", "value": "78.4", "change": "+1.1%", "direction": "up", "kind": "commodity"},
    {"key": "vix", "name": "VIX 恐慌指数", "value": "13.6", "change": "-1.2%", "direction": "down", "kind": "index"},
    {"key": "spx", "name": "标普 500", "value": "5880", "change": "+0.3%", "direction": "up", "kind": "equity"},
    {"key": "cpi", "name": "美国 CPI 同比", "value": "2.9%", "change": "-0.1", "direction": "down", "kind": "macro"},
    {"key": "pmi", "name": "中国制造业 PMI", "value": "49.8", "change": "+0.2", "direction": "up", "kind": "macro"},
]

NEWS_ITEMS = [
    {
        "time": "08-19 09:12",
        "title": "美联储官员表态谨慎，市场仍押注年内降息窗口",
        "source": "宏观快讯",
        "tags": ["利率", "美股", "美元"],
        "sentiment": 0.2,
    },
    {
        "time": "08-19 08:40",
        "title": "中国 7 月金融数据低于预期，稳增长政策预期升温",
        "source": "宏观快讯",
        "tags": ["A股", "政策", "信用"],
        "sentiment": -0.15,
    },
    {
        "time": "08-18 22:10",
        "title": "韩元汇率企稳，半导体出口数据支撑韩股风险偏好",
        "source": "市场综述",
        "tags": ["韩股", "半导体", "汇率"],
        "sentiment": 0.35,
    },
    {
        "time": "08-18 20:05",
        "title": "数字资产 ETF 资金连续五日净流入",
        "source": "资金流",
        "tags": ["数字货币", "ETF"],
        "sentiment": 0.45,
    },
    {
        "time": "08-18 17:30",
        "title": "中东局势边际缓和，油价回落利好风险资产",
        "source": "国际局势",
        "tags": ["原油", "全球"],
        "sentiment": 0.3,
    },
    {
        "time": "08-18 16:20",
        "title": "南向资金连续加仓港股互联网龙头",
        "source": "资金流",
        "tags": ["港股", "南向资金"],
        "sentiment": 0.28,
    },
]

MARKET_BIAS = {
    "a-share": {
        "score": 58,
        "label": "政策预期升温，总量信用仍待修复",
        "direction": "neutral",
    },
    "fund": {
        "score": 56,
        "label": "宽基估值处于历史中低位，风险偏好温和回升",
        "direction": "neutral",
    },
    "us": {
        "score": 68,
        "label": "利率回落与 AI 盈利预期共振，风险资产占优",
        "direction": "up",
    },
    "kr": {
        "score": 71,
        "label": "半导体周期上行，韩元企稳改善外资流入",
        "direction": "up",
    },
    "hk": {
        "score": 62,
        "label": "南向资金流入叠加估值修复，互联网权重占优",
        "direction": "up",
    },
    "fx": {
        "score": 55,
        "label": "美元指数震荡，关注央行利差与套息交易",
        "direction": "neutral",
    },
    "crypto": {
        "score": 66,
        "label": "ETF 资金流入与风险偏好回升，波动率仍高",
        "direction": "up",
    },
}

RSS_FEEDS = [
    "https://www.ftchinese.com/rss/news",
    "https://feeds.bbci.co.uk/news/business/rss.xml",
]


def _parse_rss_channel(element: ET.Element, items: list[dict]) -> None:
    for item in list(element.iter("item"))[:6]:
        title = item.findtext("title")
        if not title:
            continue
        items.append(
            {
                "time": "RSS",
                "title": title.strip(),
                "source": "开源 RSS",
                "tags": ["新闻"],
                "sentiment": 0.0,
            }
        )


def fetch_rss_news(limit: int = 6) -> list[dict]:
    items: list[dict] = []
    for url in RSS_FEEDS:
        if len(items) >= limit:
            break
        try:
            request = Request(url, headers={"User-Agent": "finresearch-terminal/0.1"})
            with urlopen(request, timeout=4) as response:
                root = ET.fromstring(response.read(512 * 1024))
            _parse_rss_channel(root, items)
        except Exception:
            continue
    return items[:limit]


def macro_payload(live_news: bool = False) -> dict:
    news = fetch_rss_news() if live_news else NEWS_ITEMS
    return {
        "snapshot": MACRO_SNAPSHOT,
        "news": news,
        "bias": MARKET_BIAS,
        "mode": "live" if live_news and news else "cache",
    }


def macro_score_for(market: str) -> float:
    return float(MARKET_BIAS.get(market, {}).get("score", 55))

