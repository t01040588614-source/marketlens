from app.services.krx_listing_cache import get_krx_fundamentals


def test_samsung_market_cap_from_krx_listing():
    row = get_krx_fundamentals("005930")
    assert row is not None
    assert row.market_cap > 1_000_000_000_000
