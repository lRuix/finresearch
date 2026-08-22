"""Macro service: snapshot, news and market bias payload."""
from __future__ import annotations

from core import macro
from domain.universe_data import UNIVERSE


class MacroService:
    def macro_payload(self, live_news: bool = False) -> dict:
        payload = macro.macro_payload(live_news=live_news)
        payload["universe_size"] = len(UNIVERSE)
        return payload
