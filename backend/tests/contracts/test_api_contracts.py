"""API response contract tests via TestClient."""
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from application.config import AppConfig
from app import app, build_container
from domain.models import KlineRow
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
    routes.container = build_container(
        AppConfig(db_path=Path(tempfile.mkdtemp()) / "test.db"),
        datasource=datasource,
    )
    yield routes.container


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
