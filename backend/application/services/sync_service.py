"""Sync orchestration: fill data gaps through repository + datasource."""
from __future__ import annotations

from application.ports import MarketDataSource, MarketDataRepository
from domain.models import KlineRow


class SyncService:
    def __init__(self, repository: MarketDataRepository,
                 datasource: MarketDataSource):
        self._repository = repository
        self._datasource = datasource

    def sync(self, market: str, symbol: str, period: str,
             start: str | None = None, end: str | None = None,
             prefer_real: bool = True) -> tuple[list[KlineRow], str]:
        watermark = self._repository.get_watermark(market, symbol, period)
        if end and watermark and watermark >= end:
            return [], "local"
        gap_start = start
        if watermark and (gap_start is None or watermark > gap_start):
            gap_start = watermark
        rows, source = self._datasource.get_klines_with_source(
            market, symbol, period, start=gap_start, end=end, limit=1000,
            prefer_real=prefer_real,
        )
        if rows:
            self._repository.upsert_klines(market, symbol, period, rows)
            self._repository.set_watermark(market, symbol, period, rows[-1].time)
        return rows, source
