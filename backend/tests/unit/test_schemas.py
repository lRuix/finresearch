"""Presentation schema tests."""
from presentation.api.schemas import ScreenQuery, symbols_list


def test_screen_query_defaults():
    q = ScreenQuery()
    assert q.market == "all"
    assert q.min_score == 0


def test_symbols_list_parser():
    assert symbols_list("AAPL,600519,,BTCUSDT") == ["AAPL", "600519", "BTCUSDT"]
