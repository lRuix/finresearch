"""Adapter wrapping the existing core.providers network layer."""
from __future__ import annotations

from core import providers
from domain.models import Instrument, KlineRow
from domain.valuation.currency import STATIC_FX_RATES


def _to_kline_rows(rows: list[dict]) -> list[KlineRow]:
    return [
        KlineRow(
            time=row["time"],
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            volume=row["volume"],
        )
        for row in rows
    ]


class ProviderDataSource:
    def list_instruments(self, market: str, top_n: int) -> list[Instrument]:
        items = providers.list_candidates(market, top_n)
        return [
            Instrument(
                market=item.get("market", market),
                symbol=item["symbol"],
                name=item.get("name", item["symbol"]),
                currency=item.get("currency", "USD"),
                sector=item.get("sector"),
                base_risk=item.get("base_risk"),
                liquidity=item.get("liquidity"),
            )
            for item in items
        ]

    def get_klines(self, market: str, symbol: str, period: str,
                   start: str | None = None, end: str | None = None,
                   limit: int = 180, prefer_real: bool = True) -> list[KlineRow]:
        rows, _ = self.get_klines_with_source(
            market, symbol, period, start, end, limit, prefer_real,
        )
        return rows

    def get_klines_with_source(self, market: str, symbol: str, period: str,
                               start: str | None = None, end: str | None = None,
                               limit: int = 180,
                               prefer_real: bool = True) -> tuple[list[KlineRow], str]:
        rows, source = providers.get_kline_with_source(
            market, symbol, period, limit, prefer_real=prefer_real,
        )
        if start:
            rows = [row for row in rows if row["time"] > start]
        if end:
            rows = [row for row in rows if row["time"] <= end]
        return _to_kline_rows(rows), source

    def get_live_fx_rates(self) -> dict[str, float] | None:
        return providers.get_live_fx_rates()

    def reference_fx_rate(self, currency: str) -> float:
        try:
            live = providers.get_live_fx_rates()
            if live and currency in live:
                return live[currency]
        except Exception:
            pass
        return STATIC_FX_RATES.get(currency, 1.0)
