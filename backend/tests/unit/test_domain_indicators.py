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


def test_analyze_tolerates_none_base_risk():
    rows = [
        {"time": f"2026-08-{i:02d}", "open": 1.0, "high": 2.0,
         "low": 0.5, "close": 100.0 + i, "volume": 1000}
        for i in range(1, 61)
    ]
    result = analyze(rows, {"market": "us", "base_risk": None})
    assert "error" not in result
    assert result["risk_score"] == 35.0
