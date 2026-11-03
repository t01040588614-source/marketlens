"""기간별 history — 상수(PERIOD_BAR_CAP·캘린더 7/31)와 실제 API 응답 일치 검증."""
import pytest
from httpx import AsyncClient

from app.services.chart_service import CHART_HUB_PERIODS, PERIOD_BAR_CAP, PERIOD_LOOKBACK_DAYS

HUB = CHART_HUB_PERIODS


@pytest.mark.anyio
@pytest.mark.parametrize("period", HUB)
async def test_samsung_all_hub_periods_shape(client: AsyncClient, period: str):
    r = await client.get(
        "/api/v1/stocks/history",
        params={"symbol": "005930", "market": "korea", "period": period},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["period"] == period
    points = data["points"] or []
    assert len(points) >= 2
    assert data.get("source") != "synthetic", f"{period} fell back to synthetic"

    if period == "1w":
        assert len(points) == 7
        assert all(str(p.get("time", "")).endswith("일") for p in points)
        assert data.get("interval") == "1d"
    elif period == "1m":
        assert len(points) == 31
        assert points[0].get("time") == "1일"
        assert points[-1].get("time") == "31일"
        assert data.get("interval") == "1d"
    elif period != "1d":
        cap = PERIOD_BAR_CAP[period]
        assert len(points) <= cap
        lookback = PERIOD_LOOKBACK_DAYS.get(period)
        if lookback is not None:
            assert len(points) >= min(cap, lookback // 3)
        assert data.get("interval") == "1d"


@pytest.mark.anyio
@pytest.mark.parametrize("period", ("3m", "6m", "1y", "5y", "max"))
async def test_aapl_long_period_daily_not_synthetic(client: AsyncClient, period: str):
    r = await client.get(
        "/api/v1/stocks/history",
        params={"symbol": "AAPL", "market": "us", "period": period},
    )
    assert r.status_code == 200
    data = r.json()
    points = data["points"] or []
    assert data.get("source") != "synthetic"
    assert data.get("interval") == "1d"
    cap = PERIOD_BAR_CAP[period]
    assert len(points) <= cap
    assert len(points) >= cap // 3
