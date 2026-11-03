from app.services.korea_valuation_cache import merge_korea_fundamentals


def test_merge_korea_fundamentals_keeps_fdr_mcap_when_yahoo_zero():
    base = {"symbol": "005930", "market_cap": 100.0, "pe_ratio": 12.0, "price": 1.0}
    live = {"symbol": "005930", "market_cap": 0.0, "pe_ratio": 0.0, "price": 2.0}
    merged = merge_korea_fundamentals(base, live)
    assert merged["price"] == 2.0
    assert merged["market_cap"] == 100.0
    assert merged["pe_ratio"] == 12.0
