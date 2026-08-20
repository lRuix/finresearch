"""Cross-market symbol resolution and arbitrary-instrument search.

Turns the fixed universe into an open search surface: any symbol can be
resolved to a market, probed against the live providers, and enriched with
auto-derived metadata (name, sector, risk, liquidity) so analysis and
screening never depend on a hand-maintained candidate pool.
"""

from __future__ import annotations

import re
import threading
import time

from core import providers
from core.universe import MARKETS, UNIVERSE, find_symbol


# ---------------------------------------------------------------------------
# Symbol → market detection
# ---------------------------------------------------------------------------

#: A-share prefixes by exchange: sh (6/5/9/688 科创), sz (0/2/3/1)
_A_SHARE_SH = ("5", "6", "9")
_A_SHARE_SZ = ("0", "1", "2", "3")

_CRYPTO_SUFFIXES = ("USDT", "USDC", "BUSD", "BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "AVAX", "LINK")

_FX_PAIRS = {
    "USDCNY", "USDCNH", "EURUSD", "GBPUSD", "USDJPY", "USDHKD", "USDSGD",
    "AUDUSD", "NZDUSD", "USDCAD", "USDCHF", "EURGBP", "EURJPY", "GBPJPY",
}


def detect_market(query: str) -> str | None:
    """Best-effort market detection for a bare symbol string.

    Order matters: the most specific suffix rules run first, then numeric
    ranges for the Chinese exchanges, then ASCII alphabetic fallbacks
    (US equities / crypto).
    """
    q = (query or "").strip().upper()
    if not q:
        return None

    # Explicit suffix rules
    if q.endswith(".KS") or q.endswith(".KQ"):
        return "kr"
    if q.endswith(".HK"):
        return "hk"
    if q.endswith(".SS") or q.endswith(".SH"):
        return "a-share"
    if q.endswith(".SZ"):
        return "a-share"
    if q.endswith("=X") or q in _FX_PAIRS or (len(q) == 6 and q.endswith("=X")):
        return "fx"
    if any(q.endswith(s) for s in _CRYPTO_SUFFIXES):
        return "crypto"

    # Numeric: Chinese exchanges + funds
    if q.isdigit():
        if len(q) == 6:
            if q.startswith(_A_SHARE_SH):
                return "fund" if q.startswith("5") else "a-share"
            return "fund" if q.startswith(("1", "5")) else "a-share"
        return None

    # Alphabetic fallback: US equity / ETF, or crypto pair without suffix
    if q.isalpha():
        return "us"
    return None


def normalize_symbol(market: str, symbol: str) -> str:
    """Normalize a user-entered symbol for the given market."""
    sym = symbol.strip().upper()
    if market == "kr":
        code = sym.split(".")[0]
        return f"{code}.KS"
    if market == "hk":
        code = sym.split(".")[0]
        return f"{code}.HK"
    if market == "fx":
        code = sym.split("=")[0]
        return f"{code}=X"
    if market == "crypto":
        code = sym.split("_")[0].split("-")[0].split("/")[0]
        return f"{code}USDT"
    return sym


# ---------------------------------------------------------------------------
# Auto-derived metadata
# ---------------------------------------------------------------------------

def derive_risk(analysis: dict, market: str) -> float:
    """Derive a base_risk 0..1 from realized volatility when no hand-curated
    value exists. Anchored to the market's volatility target so a normal
    asset lands near the middle of the band."""
    vol = analysis.get("volatility20")
    if vol is None:
        return 0.65
    target = {"fx": 0.06, "fund": 0.14, "a-share": 0.22}.get(market, 0.28)
    ratio = vol / target if target else 1.0
    if ratio <= 0.6:
        risk = 0.35
    elif ratio <= 0.9:
        risk = 0.45
    elif ratio <= 1.2:
        risk = 0.58
    elif ratio <= 1.7:
        risk = 0.72
    elif ratio <= 2.4:
        risk = 0.84
    else:
        risk = 0.93
    return round(risk, 2)


def derive_liquidity(klines: list[dict], market: str) -> float:
    """Derive a liquidity 0..1 from recent mean dollar-ish volume."""
    volumes = [row.get("volume", 0) or 0 for row in klines[-20:]]
    if not volumes or market in ("fx",):
        return 0.7
    mean_volume = sum(volumes) / len(volumes)
    if market == "crypto":
        thresholds = [(2e7, 0.95), (5e6, 0.85), (1e6, 0.7), (2e5, 0.5)]
    else:
        thresholds = [(5e7, 0.95), (1e7, 0.85), (3e6, 0.7), (8e5, 0.5)]
    for floor, score in thresholds:
        if mean_volume >= floor:
            return round(score, 2)
    return 0.35


# ---------------------------------------------------------------------------
# Resolution + search
# ---------------------------------------------------------------------------

def resolve_meta(market: str, symbol: str) -> dict | None:
    """Resolve a (market, symbol) pair to enriched metadata.

    Checks the curated universe first; otherwise probes the live providers
    for a K-line and derives name/sector/risk/liquidity from market data.
    Returns None when the symbol is unknown to both layers.
    """
    curated = find_symbol(market, symbol)
    if curated is not None:
        return dict(curated)

    rows = providers.get_kline(market, symbol, "d", 60, prefer_real=True)
    if not rows:
        return None

    closes = [row["close"] for row in rows]
    price = closes[-1]
    name = _fallback_name(market, symbol)
    sector = _fallback_sector(market, symbol)
    risk = derive_risk({"volatility20": None}, market)
    liquidity = derive_liquidity(rows, market)

    # Refine risk with a quick volatility estimate (cheap: reuse closes)
    if len(closes) >= 21:
        returns = [closes[i] / closes[i - 1] - 1 for i in range(len(closes) - 19, len(closes)) if closes[i - 1]]
        if returns:
            mean = sum(returns) / len(returns)
            variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
            vol20 = (variance ** 0.5) * (252 ** 0.5) if variance >= 0 else None
            risk = derive_risk({"volatility20": vol20}, market)

    return {
        "symbol": symbol,
        "name": name,
        "market": market,
        "currency": currency_for(market),
        "sector": sector,
        "base_risk": risk,
        "liquidity": liquidity,
        "auto": True,
        "_probe_price": price,
    }


def search(query: str, limit: int = 10) -> dict:
    """Search the curated universe by symbol/name, then resolve the query as
    an arbitrary cross-market symbol. Returns {query, items, total}."""
    q = (query or "").strip()
    items: list[dict] = []

    # 1) curated universe: symbol prefix or name substring
    q_upper = q.upper()
    for item in UNIVERSE:
        if q_upper and (
            item["symbol"].upper().startswith(q_upper)
            or q_upper in item["name"].upper()
        ):
            items.append({**item, "matched": "universe"})
        if len(items) >= limit:
            break

    # 2) arbitrary symbol resolution (skip when the query is a name, not a code)
    if q and not _looks_like_name_only(q):
        market = detect_market(q)
        if market is not None:
            symbol = normalize_symbol(market, q)
            try:
                meta = resolve_meta(market, symbol)
                if meta is not None and not any(i["symbol"] == meta["symbol"] for i in items):
                    items.append({**meta, "matched": "auto"})
            except Exception:
                pass

    return {"query": q, "items": items[:limit], "total": len(items)}


def _looks_like_name_only(query: str) -> bool:
    """Chinese/English names are not symbols; don't probe providers for them."""
    if re.search(r"[\u4e00-\u9fff]", query):
        return True
    return False


def _fallback_name(market: str, symbol: str) -> str:
    codes = {
        "a-share": "A股", "fund": "基金", "us": "美股", "kr": "韩股",
        "hk": "港股", "fx": "外汇", "crypto": "数字货币",
    }
    return f"{symbol} ({codes.get(market, '标的')})"


def _fallback_sector(market: str, symbol: str) -> str:
    sector_map = {
        "fx": "汇率", "crypto": "加密资产", "fund": "基金",
        "kr": "韩股", "hk": "港股",
    }
    return sector_map.get(market, "未分类")


def currency_for(market: str) -> str:
    """市场 → 本币币种。a-share/fund 为 CNY，us 为 USD，kr 为 KRW，
    hk 为 HKD，fx 为 MULTI，crypto 为 USDT；未知市场回落 USD。"""
    currency_map = {
        "a-share": "CNY", "fund": "CNY", "us": "USD", "kr": "KRW",
        "hk": "HKD", "fx": "MULTI", "crypto": "USDT",
    }
    return currency_map.get(market, "USD")


# ---------------------------------------------------------------------------
# Daily evaluation cache
# ---------------------------------------------------------------------------

_DAILY_CACHE: dict[str, tuple[str, dict]] = {}
_DAILY_LOCK = threading.Lock()


def daily_cache_get(key: str) -> dict | None:
    """Return a cached payload only when it was produced on today's date."""
    import datetime as _dt

    today = _dt.date.today().isoformat()
    with _DAILY_LOCK:
        hit = _DAILY_CACHE.get(key)
    if hit is None:
        return None
    produced, payload = hit
    return payload if produced == today else None


def daily_cache_set(key: str, payload: dict) -> dict:
    """Store a payload stamped with today's date (one evaluation per day)."""
    import datetime as _dt

    today = _dt.date.today().isoformat()
    with _DAILY_LOCK:
        _DAILY_CACHE[key] = (today, payload)
    return payload
