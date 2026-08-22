"""SQLite repository tests using a temporary database file."""
import sqlite3

from domain.models import Instrument, KlineRow
from infrastructure.repository.sqlite import SqliteMarketDataRepository


def _rows():
    return [
        KlineRow("2026-08-20", 1.0, 2.0, 0.5, 1.5, 100),
        KlineRow("2026-08-21", 1.5, 2.5, 1.2, 2.2, 120),
    ]


def test_upsert_and_read_klines(tmp_path):
    repo = SqliteMarketDataRepository(tmp_path / "research.db")
    repo.upsert_klines("us", "AAPL", "d", _rows())
    rows = repo.get_klines("us", "AAPL", "d")
    assert [r.time for r in rows] == ["2026-08-20", "2026-08-21"]
    assert rows[1].close == 2.2


def test_upsert_replaces_same_key(tmp_path):
    repo = SqliteMarketDataRepository(tmp_path / "research.db")
    repo.upsert_klines("us", "AAPL", "d", _rows())
    repo.upsert_klines("us", "AAPL", "d", [
        KlineRow("2026-08-21", 1.5, 2.5, 1.2, 9.9, 120),
    ])
    rows = repo.get_klines("us", "AAPL", "d")
    assert len(rows) == 2
    assert rows[1].close == 9.9


def test_get_klines_with_range(tmp_path):
    repo = SqliteMarketDataRepository(tmp_path / "research.db")
    repo.upsert_klines("us", "AAPL", "d", _rows())
    rows = repo.get_klines("us", "AAPL", "d", start="2026-08-21")
    assert [r.time for r in rows] == ["2026-08-21"]


def test_watermark_progress(tmp_path):
    repo = SqliteMarketDataRepository(tmp_path / "research.db")
    assert repo.get_watermark("us", "AAPL", "d") is None
    repo.set_watermark("us", "AAPL", "d", "2026-08-21")
    assert repo.get_watermark("us", "AAPL", "d") == "2026-08-21"


def test_snapshot_upsert_and_read(tmp_path):
    repo = SqliteMarketDataRepository(tmp_path / "research.db")
    repo.upsert_snapshot("2026-08-23", "us", [
        {"symbol": "AAPL", "name": "Apple", "turnover": 1e9, "market_cap": 3e12},
        {"symbol": "MSFT", "name": "Microsoft", "turnover": 8e8, "market_cap": 3e12},
    ])
    items = repo.get_snapshot("2026-08-23", "us")
    assert [item["symbol"] for item in items] == ["AAPL", "MSFT"]


def test_evaluation_same_day_replace(tmp_path):
    repo = SqliteMarketDataRepository(tmp_path / "research.db")
    repo.save_evaluation("2026-08-23", "us", "AAPL", 80.0, {"score": 80.0})
    payload = repo.get_evaluation("2026-08-23", "us", "AAPL")
    assert payload == {"score": 80.0}


def test_instruments_upsert_uses_timestamp(tmp_path):
    repo = SqliteMarketDataRepository(tmp_path / "research.db")
    repo.upsert_instruments([
        Instrument(
            market="us", symbol="AAPL", name="Apple", currency="USD",
            sector="tech", base_risk=0.3, liquidity=0.9,
        ),
    ])
    conn = sqlite3.connect(tmp_path / "research.db")
    row = conn.execute(
        "SELECT updated_at FROM instruments WHERE market = ? AND symbol = ?",
        ("us", "AAPL"),
    ).fetchone()
    conn.close()
    assert row is not None
    assert "+00:00" in row[0]


def test_snapshot_upsert_replaces_full_day(tmp_path):
    repo = SqliteMarketDataRepository(tmp_path / "research.db")
    repo.upsert_snapshot("2026-08-23", "us", [
        {"symbol": "AAPL", "name": "Apple", "turnover": 1e9, "market_cap": 3e12},
        {"symbol": "MSFT", "name": "Microsoft", "turnover": 8e8, "market_cap": 3e12},
    ])
    repo.upsert_snapshot("2026-08-23", "us", [
        {"symbol": "TSLA", "name": "Tesla", "turnover": 7e8, "market_cap": 1e12},
    ])
    items = repo.get_snapshot("2026-08-23", "us")
    assert [item["symbol"] for item in items] == ["TSLA"]


def test_get_evaluation_tolerates_corrupt_payload(tmp_path):
    repo = SqliteMarketDataRepository(tmp_path / "research.db")
    repo.save_evaluation("2026-08-23", "us", "AAPL", 80.0, {"score": 80.0})
    conn = sqlite3.connect(tmp_path / "research.db")
    conn.execute(
        "UPDATE evaluations SET payload = ? WHERE evaluated_on = ? AND market = ? AND symbol = ?",
        ("{broken", "2026-08-23", "us", "AAPL"),
    )
    conn.commit()
    conn.close()
    assert repo.get_evaluation("2026-08-23", "us", "AAPL") is None
