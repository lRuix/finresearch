"""API response contract tests via TestClient."""
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from application.config import AppConfig
from app import app, build_container
from domain.models import KlineRow
from infrastructure.repository.sqlite import SqliteMarketDataRepository
from presentation.api import routes


@pytest.fixture(scope="module", autouse=True)
def wired_container():
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
    datasource.list_instruments.return_value = []
    datasource.reference_fx_rate.return_value = 7.18
    datasource.get_live_fx_rates.return_value = None
    config = AppConfig(db_path=Path(tempfile.mkdtemp()) / "test.db")
    repo = SqliteMarketDataRepository(config.db_path)
    for symbol in ("AAPL", "NVDA", "MSFT", "TSLA", "600519"):
        market = "a-share" if symbol == "600519" else "us"
        repo.upsert_klines(market, symbol, "d", rows)
    routes.container = build_container(
        config,
        datasource=datasource,
        repository=repo,
    )
    yield routes.container
    routes.container = build_container(AppConfig(db_path=Path(tempfile.mkdtemp()) / "restore.db"))


def test_health_and_markets():
    client = TestClient(app)
    assert client.get("/api/health").json()["status"] == "ok"
    payload = client.get("/api/markets").json()
    assert payload["total"] > 0


def test_universe_contract_shape():
    client = TestClient(app)
    payload = client.get("/api/universe?market=us").json()
    assert set(payload) >= {"items", "total"}


def test_kline_contract_shape():
    client = TestClient(app)
    payload = client.get("/api/kline?market=us&symbol=AAPL&limit=30").json()
    assert "source" in payload
    assert "items" in payload
    assert "count" in payload


def test_screen_contract_shape():
    client = TestClient(app)
    payload = client.get("/api/screen?market=us&limit=5").json()
    assert set(payload) >= {"items", "count", "total_universe", "updated_at"}


def test_recommendations_contract_shape():
    client = TestClient(app)
    payload = client.get("/api/recommendations?limit=5").json()
    assert set(payload) >= {"items", "count", "total_universe", "updated_at"}


def test_analyze_contract_shape():
    client = TestClient(app)
    payload = client.get("/api/analyze?market=us&symbol=AAPL").json()
    assert set(payload) >= {"meta", "macro_bias", "analysis", "kline_count"}


def test_recommend_contract_shape():
    client = TestClient(app)
    payload = client.get("/api/recommend?market=us&symbol=AAPL").json()
    assert set(payload) >= {
        "factor_scores", "factor_details", "sentiment", "total_score", "detail",
    }


def test_compare_contract_shape():
    client = TestClient(app)
    payload = client.get("/api/compare?symbols=AAPL,600519").json()
    assert set(payload) >= {"items", "total"}


def test_macro_contract_shape():
    client = TestClient(app)
    payload = client.get("/api/macro").json()
    assert set(payload) >= {"snapshot", "news", "bias", "universe_size"}


def test_search_contract_shape():
    client = TestClient(app)
    payload = client.get("/api/search?q=AAPL").json()
    assert set(payload) >= {"query", "items", "total"}


def test_recommendations_forwards_query_params():
    from unittest.mock import patch

    client = TestClient(app)
    payload = {"items": [], "count": 0, "total_universe": 0}
    with patch.object(
        routes.container.recommendation_service,
        "recommend",
        return_value=payload,
    ) as mock_rec:
        client.get("/api/recommendations", params={"limit": 8, "candidates_per_market": 30})
    assert mock_rec.call_args.args == (8, 30)
