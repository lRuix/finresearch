"""Gate kline source tests."""
from __future__ import annotations

from etl.sources import gate


def test_fetch_klines_preserves_gate_fields_and_filters(monkeypatch):
    payload = [
        ["1787356800", "808872838.726", "77078", "78835.1", "76500", "78336", "10439.731", "12345", "0.0001"],
        ["1787443200", "808900000", "77100", "78900", "76600", "78400", "10450", "12346", "0.0002"],
        ["1787529600", "809000000", "77200", "79000", "76700", "78500", "10460", "12347", "0.0003"],
    ]
    monkeypatch.setattr(gate, "get_json", lambda url, **kw: payload)

    rows = gate.fetch_klines(
        "crypto",
        "BTCUSDT",
        "d",
        start="2026-08-23",
        end="2026-08-23",
    )

    assert len(rows) == 1
    assert rows[0]["time"] == "2026-08-23T00:00:00+00:00"
    assert rows[0]["quote_volume"] == 808900000
    assert rows[0]["trades_count"] == 12346
    assert rows[0]["funding_rate"] == 0.0002
