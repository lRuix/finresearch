"""API 端点测试。"""

from pathlib import Path
import tempfile

import pytest
from fastapi.testclient import TestClient

from application.config import AppConfig
from app import app, build_container
from domain.models import KlineRow
from infrastructure.repository.sqlite import SqliteMarketDataRepository
from presentation.api import routes


@pytest.fixture(scope="module", autouse=True)
def wired_api_container():
    """预置 SQLite 仓库 K 线数据：缺数据不补齐，接口测试需有数据可读。"""
    config = AppConfig(db_path=Path(tempfile.mkdtemp()) / "api-test.db")
    repo = SqliteMarketDataRepository(config.db_path)
    rows = [
        KlineRow(
            time=f"2026-08-{i:02d}", open=1.0, high=2.0,
            low=0.5, close=100.0 + i, volume=1000,
        )
        for i in range(1, 61)
    ]
    for symbol in ("600519", "000001", "AAPL", "MSFT", "NVDA", "GOOG", "TSLA"):
        market = "a-share" if symbol.isdigit() else "us"
        repo.upsert_klines(market, symbol, "d", rows)
    container = build_container(config, repository=repo)
    routes.container = container
    yield container
    routes.container = build_container(
        AppConfig(db_path=Path(tempfile.mkdtemp()) / "restore.db")
    )


client = TestClient(app)


def test_search_endpoint_returns_structure():
    resp = client.get("/api/search", params={"q": "600519"})
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert "total" in body


def test_search_endpoint_empty_query():
    resp = client.get("/api/search", params={"q": ""})
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_compare_endpoint_empty_returns_empty():
    resp = client.get("/api/compare", params={"symbols": ""})
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_recommend_uses_algorithm_layer():
    resp = client.get("/api/recommend", params={"market": "a-share", "symbol": "600519"})
    assert resp.status_code == 200
    body = resp.json()
    # 新结构：因子分 + 情绪 + 总分（而非旧的 analysis 字段）
    assert "factor_scores" in body
    assert "sentiment" in body
    assert "total_score" in body
    assert 0 <= body["total_score"] <= 100
    assert set(body["factor_scores"].keys()) == {"trend", "momentum", "volatility", "risk", "macro"}


def test_analyze_accepts_arbitrary_symbol():
    resp = client.get("/api/analyze", params={"market": "us", "symbol": "GOOG"})
    assert resp.status_code == 200
    body = resp.json()
    assert "error" not in body
    assert body["meta"]["symbol"] == "GOOG"
    assert body["meta"]["auto"] is True
    assert "total_score" in body["analysis"]
