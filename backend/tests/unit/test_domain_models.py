"""Domain value object tests."""
from dataclasses import FrozenInstanceError

import pytest

from domain.models import Instrument, KlineRow


def test_instrument_defaults():
    item = Instrument(market="us", symbol="AAPL", name="Apple", currency="USD")
    assert item.sector is None
    assert item.base_risk is None
    assert item.liquidity is None


def test_instrument_is_frozen():
    item = Instrument(market="us", symbol="AAPL", name="Apple", currency="USD")
    with pytest.raises(FrozenInstanceError):
        item.name = "Other"


def test_kline_row_fields():
    row = KlineRow(time="2026-08-23", open=1.0, high=2.0, low=0.5, close=1.5, volume=100)
    assert row.close == 1.5
    assert row.volume == 100
