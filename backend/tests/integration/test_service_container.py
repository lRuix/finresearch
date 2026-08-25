"""Service container wiring smoke test."""
from unittest.mock import MagicMock

from application.config import AppConfig
from application.services.analysis_service import AnalysisService
from application.services.catalog_service import CatalogService
from application.services.comparison_service import ComparisonService
from application.services.macro_service import MacroService
from application.services.recommendation_service import RecommendationService
from application.services.screening_service import ScreeningService
from application.services.search_service import SearchService
from application.services.symbol_resolver import SymbolResolver
from app import build_container
from domain.models import KlineRow
from infrastructure.datasources.macro_provider import MacroNewsProvider
from infrastructure.repository.postgres import PostgresMarketDataRepository
from infrastructure.repository.sqlite import SqliteMarketDataRepository


def test_container_wires_all_services(tmp_path, monkeypatch):
    monkeypatch.delenv("WAREHOUSE_DSN", raising=False)
    datasource = MagicMock()
    rows = [
        KlineRow(
            time=f"2026-08-{i:02d}", open=1.0, high=2.0,
            low=0.5, close=100.0 + i, volume=1000,
        )
        for i in range(1, 61)
    ]
    datasource.get_klines.return_value = rows
    datasource.get_klines_with_source.return_value = (rows, "live")
    datasource.reference_fx_rate.return_value = 7.18
    datasource.get_live_fx_rates.return_value = None

    container = build_container(
        AppConfig(db_path=tmp_path / "test.db"),
        datasource=datasource,
    )

    assert isinstance(container.repository, SqliteMarketDataRepository)
    assert container.datasource is datasource
    assert isinstance(container.macro_news, MacroNewsProvider)
    assert isinstance(container.symbol_resolver, SymbolResolver)
    assert isinstance(container.catalog_service, CatalogService)
    assert isinstance(container.search_service, SearchService)
    assert isinstance(container.macro_service, MacroService)
    assert isinstance(container.screening_service, ScreeningService)
    assert isinstance(container.recommendation_service, RecommendationService)
    assert isinstance(container.comparison_service, ComparisonService)
    assert isinstance(container.analysis_service, AnalysisService)

    assert container.recommendation_service._screening is container.screening_service

    # 走一条依赖注入链路：kline 直接读仓库（SQLite 空库 → 空数据，不补齐）。
    items, source = container.analysis_service.kline("us", "AAPL", "d", 30)
    assert source == "local"
    assert items == []


def test_container_uses_postgres_repository_when_dsn_set(monkeypatch):
    monkeypatch.setenv(
        "WAREHOUSE_DSN",
        "postgresql://warehouse:warehouse@127.0.0.1:5432/warehouse_test",
    )
    container = build_container()
    assert isinstance(container.repository, PostgresMarketDataRepository)
