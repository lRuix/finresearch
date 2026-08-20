"""API 端点测试。"""
from fastapi.testclient import TestClient

from app import app

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
