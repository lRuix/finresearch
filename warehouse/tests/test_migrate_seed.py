"""Seed migration helper tests."""
from __future__ import annotations

from datetime import datetime, timedelta

from etl.migrate_seed import (
    _CN_TIMEZONE,
    _new_batch_id,
    _parse_news_time,
    _split_fx_currency,
)


def test_fx_currency_parsing_supports_common_symbol_formats():
    assert _split_fx_currency("AUDUSD=X") == ("AUD", "USD")
    assert _split_fx_currency("EUR/USD") == ("EUR", "USD")
    assert _split_fx_currency("usdcny=x") == ("USD", "CNY")


def test_fx_currency_parsing_rejects_unrecognized_symbol():
    assert _split_fx_currency("INVALID") == (None, None)


def test_news_time_uses_current_year_and_cn_timezone():
    parsed = _parse_news_time("08-19 09:12")
    now = datetime.now(_CN_TIMEZONE)

    assert parsed.tzinfo == _CN_TIMEZONE
    assert parsed.year == now.year
    assert parsed.month == 8
    assert parsed.day == 19
    assert parsed.hour == 9
    assert parsed.minute == 12


def test_news_time_falls_back_to_previous_year_when_far_in_future():
    future = (datetime.now(_CN_TIMEZONE) + timedelta(days=30)).strftime("%m-%d %H:%M")
    parsed = _parse_news_time(future)
    now = datetime.now(_CN_TIMEZONE)

    assert parsed.year == now.year - 1


def test_rss_news_time_uses_now():
    before = datetime.now(_CN_TIMEZONE) - timedelta(seconds=1)
    parsed = _parse_news_time("RSS")
    after = datetime.now(_CN_TIMEZONE) + timedelta(seconds=1)

    assert before <= parsed <= after


def test_batch_ids_are_unique():
    assert _new_batch_id() != _new_batch_id()
    assert _new_batch_id().startswith("seed-")
