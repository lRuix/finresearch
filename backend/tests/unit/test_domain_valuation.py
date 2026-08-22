"""Domain valuation purity and behavior tests."""
import inspect

import pytest

from domain.valuation import currency, metrics


def test_to_rmb_closes():
    assert currency.to_rmb_closes([10.0, 11.0], 7.18) == pytest.approx([71.8, 78.98])


def test_currency_module_has_no_provider_import():
    source = inspect.getsource(currency)
    assert "providers" not in source


def test_calmar_ratio():
    closes = [100.0, 110.0, 105.0, 120.0, 118.0]
    calmar = metrics.calmar_ratio(closes)
    assert calmar is not None
    assert calmar > 0
