import pytest
from app.services import news_feed_service as svc


@pytest.mark.asyncio
async def test_get_finance_news_returns_many_per_category():
    payload = await svc.get_finance_news(force_refresh=True)
    assert payload["status"] in ("live", "empty")
    data = payload.get("data") or []
    if not data:
        pytest.skip("RSS unreachable in this environment")
    counts = payload.get("counts") or {}
    assert counts.get("시장", 0) >= 5
    assert counts.get("경제", 0) >= 5
    assert counts.get("기업", 0) >= 5
    assert counts.get("미국", 0) >= 5
    first = data[0]
    assert first.get("title")
    assert first.get("category") in ("시장", "경제", "기업", "미국")
