"""Macro service: snapshot, news and market bias payload."""
from __future__ import annotations

from application.ports import MacroNewsProvider
from domain.universe_data import UNIVERSE


class MacroService:
    def __init__(self, macro_news: MacroNewsProvider):
        self._macro_news = macro_news

    def macro_payload(self, live_news: bool = False) -> dict:
        payload = self._macro_news.macro_payload(live_news)
        payload["universe_size"] = len(UNIVERSE)
        return payload
