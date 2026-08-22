"""Ports and config import tests."""
from pathlib import Path

from application.config import AppConfig
from application.ports import (
    FxRateProvider,
    MacroNewsProvider,
    MarketDataSource,
    MarketDataRepository,
)


def test_ports_importable():
    assert MarketDataRepository is not None
    assert MarketDataSource is not None
    assert FxRateProvider is not None
    assert MacroNewsProvider is not None


def test_default_config_uses_backend_data_dir():
    cfg = AppConfig()
    assert str(cfg.db_path).endswith("backend/data/research.db")
    assert isinstance(cfg.db_path, Path)
