"""Domain indicators sanity tests."""
from domain.indicators import analyze, rsi, sma


def test_sma_requires_enough_values():
    assert sma([1.0, 2.0], 5) is None
    assert sma([1.0, 2.0, 3.0], 2) == 2.5


def test_rsi_basic():
    closes = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0,
              11.0, 12.0, 13.0, 14.0, 15.0]
    assert rsi(closes, 14) == 100.0


def test_analyze_requires_two_rows():
    result = analyze([{"close": 1.0}])
    assert result["error"] == "insufficient kline data"
