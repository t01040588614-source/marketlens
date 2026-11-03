import pytest
from httpx import AsyncClient

CHART_PERIODS = ("1w", "1m", "3m", "5mo", "6m", "1y", "5y", "max")

MIN_DAILY_BARS: dict[str, int] = {
    "1w": 7,
    "1m": 31,
    "3m": 48,
    "5mo": 80,
    "6m": 95,
    "1y": 180,
    "5y": 450,
    "max": 450,
}


@pytest.mark.anyio
@pytest.mark.parametrize("period", CHART_PERIODS)
async def test_korea_stock_history_covers_period(client: AsyncClient, period: str):
    response = await client.get(
        "/api/v1/stocks/history",
        params={"symbol": "005930", "market": "korea", "period": period},
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("period") == period
    points = data.get("points") or []
    assert len(points) >= MIN_DAILY_BARS[period]
    assert data.get("interval") in ("1d", "1wk", "1mo", "5m", "1h", "60m", "15m", "30m", "1m", "2m")
    if period in ("5y", "max"):
        assert data.get("interval") == "1d"


@pytest.mark.anyio
@pytest.mark.parametrize("period", ("3m", "6m", "1y", "5y", "max"))
async def test_us_stock_history_covers_period(client: AsyncClient, period: str):
    response = await client.get(
        "/api/v1/stocks/history",
        params={"symbol": "AAPL", "market": "us", "period": period},
    )
    assert response.status_code == 200
    data = response.json()
    points = data.get("points") or []
    assert len(points) >= MIN_DAILY_BARS[period] // 2
