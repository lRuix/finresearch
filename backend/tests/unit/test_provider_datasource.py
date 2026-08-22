"""ProviderDataSource adapter tests (network paths mocked)."""
from unittest.mock import patch

from domain.models import KlineRow
from infrastructure.datasources.provider_datasource import ProviderDataSource


def test_get_klines_converts_rows_and_source():
    fake_rows = [
        {"time": "2026-08-22", "open": 1.0, "high": 2.0, "low": 0.5,
         "close": 1.5, "volume": 100},
        {"time": "2026-08-23", "open": 1.5, "high": 2.5, "low": 1.2,
         "close": 2.2, "volume": 120},
    ]
    with patch("infrastructure.datasources.provider_datasource.providers.get_kline_with_source",
               return_value=(fake_rows, "live")):
        rows = ProviderDataSource().get_klines("us", "AAPL", "d", limit=30)
    assert rows == [
        KlineRow("2026-08-22", 1.0, 2.0, 0.5, 1.5, 100),
        KlineRow("2026-08-23", 1.5, 2.5, 1.2, 2.2, 120),
    ]


def test_get_klines_with_source_filters_exclusive_start():
    fake_rows = [
        {"time": "2026-08-22", "open": 1.0, "high": 2.0, "low": 0.5,
         "close": 1.5, "volume": 100},
        {"time": "2026-08-23", "open": 1.5, "high": 2.5, "low": 1.2,
         "close": 2.2, "volume": 120},
    ]
    with patch("infrastructure.datasources.provider_datasource.providers.get_kline_with_source",
               return_value=(fake_rows, "live")):
        rows, source = ProviderDataSource().get_klines_with_source(
            "us", "AAPL", "d", start="2026-08-22",
        )
    assert source == "live"
    assert [row.time for row in rows] == ["2026-08-23"]


def test_reference_fx_rate_falls_back_to_static():
    with patch("infrastructure.datasources.provider_datasource.providers.get_live_fx_rates",
               return_value=None):
        rate = ProviderDataSource().reference_fx_rate("USD")
    assert rate == 7.18
