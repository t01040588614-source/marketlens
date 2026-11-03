"""종목 표시명 — 티커 그대로 노출 방지."""

from app.data.seed_stocks import US_NAMES, US_SYMBOLS
from app.data.stock_display_names import resolve_display_name


def test_us_universe_has_official_names():
    for sym in US_SYMBOLS:
        name = US_NAMES.get(sym)
        assert name, f"missing US_NAMES for {sym}"
        assert name.upper() != sym
        assert len(name) > len(sym) / 2


def test_resolve_us_replaces_ticker_fallback():
    assert resolve_display_name("JPM", stock_type="us", current="JPM") == US_NAMES["JPM"]
    assert resolve_display_name("AAPL", stock_type="us", current="AAPL") == US_NAMES["AAPL"]


def test_resolve_korea_from_registry():
    assert resolve_display_name("005930", stock_type="korea") == "삼성전자"
    assert resolve_display_name("000660", stock_type="korea") == "SK하이닉스"
