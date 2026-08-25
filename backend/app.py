"""FastAPI composition root: build services, register routes."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from application.config import AppConfig
from application.ports import MarketDataRepository, MarketDataSource
from application.services.analysis_service import AnalysisService
from application.services.catalog_service import CatalogService
from application.services.comparison_service import ComparisonService
from application.services.macro_service import MacroService
from application.services.recommendation_service import RecommendationService
from application.services.search_service import SearchService
from application.services.screening_service import ScreeningService
from application.services.symbol_resolver import SymbolResolver
from infrastructure.datasources.macro_provider import MacroNewsProvider
from infrastructure.datasources.provider_datasource import ProviderDataSource
from infrastructure.repository.postgres import PostgresMarketDataRepository
from infrastructure.repository.sqlite import SqliteMarketDataRepository
from presentation.api.routes import router


@dataclass
class ServiceContainer:
    config: AppConfig
    repository: MarketDataRepository
    datasource: MarketDataSource
    macro_news: MacroNewsProvider
    symbol_resolver: SymbolResolver
    catalog_service: CatalogService
    screening_service: ScreeningService
    recommendation_service: RecommendationService
    comparison_service: ComparisonService
    analysis_service: AnalysisService
    search_service: SearchService
    macro_service: MacroService


def build_container(
    config: AppConfig | None = None,
    datasource: MarketDataSource | None = None,
    repository: MarketDataRepository | None = None,
) -> ServiceContainer:
    config = config or AppConfig()
    if repository is None:
        repository = (
            PostgresMarketDataRepository(config.warehouse_dsn)
            if config.warehouse_dsn
            else SqliteMarketDataRepository(config.db_path)
        )
    datasource = datasource or ProviderDataSource()
    macro_news = MacroNewsProvider()
    symbol_resolver = SymbolResolver(datasource)
    catalog = CatalogService()
    screening = ScreeningService(repository, macro_news, datasource)
    recommendation = RecommendationService(repository, screening)
    comparison = ComparisonService(repository, symbol_resolver, datasource)
    analysis = AnalysisService(
        repository, symbol_resolver, macro_news, datasource,
    )
    search_service = SearchService(datasource)
    macro_service = MacroService(macro_news)
    return ServiceContainer(
        config=config, repository=repository, datasource=datasource,
        macro_news=macro_news, symbol_resolver=symbol_resolver,
        catalog_service=catalog, screening_service=screening,
        recommendation_service=recommendation,
        comparison_service=comparison, analysis_service=analysis,
        search_service=search_service, macro_service=macro_service,
    )


app = FastAPI(
    title="Global Finance Research Terminal",
    description="全球投资标的筛选与 K 线研究 API",
    version="0.2.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from presentation.api import routes as routes_module
routes_module.container = build_container()
app.include_router(router)
