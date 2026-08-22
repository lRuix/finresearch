"""Domain valuation purity and behavior tests."""
import ast
import inspect
from types import MappingProxyType

import pytest

from domain.valuation import currency, metrics


def test_to_rmb_closes():
    assert currency.to_rmb_closes([10.0, 11.0], 7.18) == pytest.approx([71.8, 78.98])


def test_to_rmb_returns_applies_fx_change():
    assert currency.to_rmb_returns([0.10], 0.05) == pytest.approx([0.155])


def test_to_rmb_returns_no_fx_change():
    assert currency.to_rmb_returns([0.10], 0.0) == pytest.approx([0.10])


def test_currency_module_has_no_provider_import():
    tree = ast.parse(inspect.getsource(currency))
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
    assert not (imported_modules & {"providers", "core"})


def test_static_fx_rates_readonly():
    assert isinstance(currency.STATIC_FX_RATES, MappingProxyType)


def test_metrics_extra():
    assert metrics.max_drawdown([100.0, 110.0]) == 0.0
    assert metrics.annualized_return([100.0, 110.0]) > 0
    assert metrics.sharpe_ratio([100.0, 110.0, 120.0]) > 0


def test_constraints_quota():
    from domain.valuation import constraints

    assert constraints.requires_quota("us") is True
    assert constraints.requires_quota("a-share") is False


def test_calmar_ratio():
    closes = [100.0, 110.0, 105.0, 120.0, 118.0]
    calmar = metrics.calmar_ratio(closes)
    assert calmar is not None
    assert calmar > 0
