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


def test_kline_row_is_frozen():
    row = KlineRow(time="2026-08-23", open=1.0, high=2.0, low=0.5, close=1.5, volume=100)
    with pytest.raises(FrozenInstanceError):
        row.close = 2.0


def test_kline_row_equality_and_hash():
    left = KlineRow("2026-08-23", 1.0, 2.0, 0.5, 1.5, 100)
    right = KlineRow("2026-08-23", 1.0, 2.0, 0.5, 1.5, 100)
    assert left == right
    assert hash(left) == hash(right)


def test_kline_row_rejects_negative_volume():
    with pytest.raises(ValueError):
        KlineRow("2026-08-23", 1.0, 2.0, 0.5, 1.5, -1)


def test_kline_row_rejects_high_below_low():
    with pytest.raises(ValueError):
        KlineRow("2026-08-23", 1.0, 0.5, 2.0, 1.5, 100)
