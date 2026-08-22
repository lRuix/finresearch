"""Cross-market symbol resolution without direct network access."""
from __future__ import annotations

from application.ports import MarketDataSource
from domain.models import KlineRow
from domain.universe_data import find_symbol


_A_SHARE_SH = ("5", "6", "9")
_CRYPTO_SUFFIXES = ("USDT", "USDC", "BUSD")
_SHORT_CRYPTO = {"BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "AVAX", "LINK"}
_FX_PAIRS = {
    "USDCNY", "USDCNH", "EURUSD", "GBPUSD", "USDJPY", "USDHKD", "USDSGD",
    "AUDUSD", "NZDUSD", "USDCAD", "USDCHF", "EURGBP", "EURJPY", "GBPJPY",
}


class SymbolResolver:
    def __init__(self, datasource: MarketDataSource):
        self._datasource = datasource

    def detect_market(self, query: str) -> str | None:
        q = (query or "").strip().upper()
        if not q:
            return None
        if q.endswith(".KS") or q.endswith(".KQ"):
            return "kr"
        if q.endswith(".HK"):
            return "hk"
        if q.endswith((".SS", ".SH", ".SZ")):
            digits = q.split(".")[0]
            if digits.isdigit() and len(digits) == 6:
                if digits.startswith(("1", "5")):
                    return "fund"
                return "a-share"
            return "a-share"
        if q.endswith("=X") or q in _FX_PAIRS:
            return "fx"
        if q.endswith(_CRYPTO_SUFFIXES):
            return "crypto"
        if q in _SHORT_CRYPTO:
            return "crypto"
        if q.isdigit():
            if len(q) == 6:
                if q.startswith(_A_SHARE_SH):
                    return "fund" if q.startswith("5") else "a-share"
                return "fund" if q.startswith(("1", "5")) else "a-share"
            return None
        if q.isascii() and q.isalpha():
            return "us"
        return None

    def normalize_symbol(self, market: str, symbol: str) -> str:
        sym = symbol.strip().upper()
        if market == "kr":
            code = sym.split(".")[0]
            suffix = ".KQ" if sym.endswith(".KQ") else ".KS"
            return f"{code}{suffix}"
        if market == "hk":
            code = sym.split(".")[0]
            return f"{code}.HK"
        if market in ("a-share", "fund"):
            return sym.split(".")[0]
        if market == "fx":
            code = sym.split("=")[0]
            return f"{code}=X"
        if market == "crypto":
            code = sym.split("_")[0].split("-")[0].split("/")[0]
            if code.endswith(_CRYPTO_SUFFIXES):
                return code
            return f"{code}USDT"
        return sym

    def currency_for(self, market: str) -> str:
        return {
            "a-share": "CNY", "fund": "CNY", "us": "USD", "kr": "KRW",
            "hk": "HKD", "fx": "MULTI", "crypto": "USDT",
        }.get(market, "USD")

    def resolve_meta(self, market: str, symbol: str) -> dict | None:
        curated = find_symbol(market, symbol)
        if curated is not None:
            return {**curated, "auto": False}
        rows = self._datasource.get_klines(market, symbol, "d", limit=60)
        if not rows:
            return None
        closes = [row.close for row in rows]
        name = self._fallback_name(market, symbol)
        sector = self._fallback_sector(market, symbol)
        return {
            "symbol": symbol,
            "name": name,
            "market": market,
            "currency": self.currency_for(market),
            "sector": sector,
            "base_risk": self._derive_risk(len(closes)),
            "liquidity": self._derive_liquidity(rows),
            "auto": True,
            "_probe_price": closes[-1],
        }

    @staticmethod
    def _derive_risk(row_count: int) -> float:
        return 0.58 if row_count >= 21 else 0.65

    @staticmethod
    def _derive_liquidity(rows: list[KlineRow]) -> float:
        volumes = [row.volume for row in rows[-20:]]
        if not volumes:
            return 0.7
        mean_volume = sum(volumes) / len(volumes)
        for floor, score in [(5e7, 0.95), (1e7, 0.85), (3e6, 0.7), (8e5, 0.5)]:
            if mean_volume >= floor:
                return score
        return 0.35

    @staticmethod
    def _fallback_name(market: str, symbol: str) -> str:
        names = {
            "a-share": "A股", "fund": "基金", "us": "美股", "kr": "韩股",
            "hk": "港股", "fx": "外汇", "crypto": "数字货币",
        }
        return f"{symbol} ({names.get(market, '标的')})"

    @staticmethod
    def _fallback_sector(market: str, symbol: str) -> str:
        return {
            "fx": "汇率", "crypto": "加密资产", "fund": "基金",
            "kr": "韩股", "hk": "港股",
        }.get(market, "未分类")
