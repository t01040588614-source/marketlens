import pytest
from httpx import AsyncClient

from app.services.chart_service import ChartService


def test_patch_last_close_keeps_historical_bars():
    """실시간가 반영 시 과거 봉을 스케일하지 않음 (전 구간 anchor 왜곡 방지)."""
    svc = ChartService()
    points = [
        {
            "open": 255_500,
            "high": 256_000,
            "low": 255_000,
            "close": 255_500,
            "volume": 1_000_000,
        },
        {
            "open": 214_000,
            "high": 215_000,
            "low": 213_500,
            "close": 214_500,
            "volume": 1_200_000,
        },
    ]
    out = svc._patch_last_close(points, 268_000)
    assert out[0]["close"] == 255_500
    assert out[-1]["close"] == 268_000


@pytest.mark.anyio
async def test_kosdaq_index_1w_ordinal_day_labels(client: AsyncClient):
    response = await client.get(
        "/api/v1/stocks/history",
        params={"symbol": "kosdaq", "market": "index", "period": "1w"},
    )
    assert response.status_code == 200
    points = response.json().get("points") or []
    assert len(points) == 7
    assert [p["time"] for p in points] == [
        "1일",
        "2일",
        "3일",
        "4일",
        "5일",
        "6일",
        "7일",
    ]


@pytest.mark.anyio
async def test_kosdaq_index_1m_ordinal_day_labels(client: AsyncClient):
    response = await client.get(
        "/api/v1/stocks/history",
        params={"symbol": "kosdaq", "market": "index", "period": "1m"},
    )
    assert response.status_code == 200
    points = response.json().get("points") or []
    assert len(points) == 31
    assert points[0]["time"] == "1일"
    assert points[-1]["time"] == "31일"


@pytest.mark.anyio
async def test_kosdaq_index_1w_summary_matches_series(client: AsyncClient):
    response = await client.get(
        "/api/v1/stocks/history",
        params={"symbol": "kosdaq", "market": "index", "period": "1w"},
    )
    assert response.status_code == 200
    data = response.json()
    points = data.get("points") or []
    summary = data.get("summary") or {}
    assert len(points) >= 2
    assert data.get("source") in ("yahoo", "fdr", "synthetic")
    assert summary["open"] == points[0]["open"]
    assert summary["close"] == points[-1]["close"]
    assert summary["high"] >= max(p["high"] for p in points) - 0.02
    assert summary["low"] <= min(p["low"] for p in points) + 0.02


@pytest.mark.anyio
async def test_korea_stock_1m_has_31_daily_bars(client: AsyncClient):
    response = await client.get(
        "/api/v1/stocks/history",
        params={"symbol": "005930", "market": "korea", "period": "1m"},
    )
    assert response.status_code == 200
    data = response.json()
    points = data.get("points") or []
    assert len(points) == 31
    assert points[0]["time"] == "1일"
    assert points[-1]["time"] == "31일"
    assert data.get("interval") == "1d"


@pytest.mark.anyio
async def test_us_stock_1m_has_31_daily_bars(client: AsyncClient):
    response = await client.get(
        "/api/v1/stocks/history",
        params={"symbol": "AAPL", "market": "us", "period": "1m"},
    )
    assert response.status_code == 200
    data = response.json()
    points = data.get("points") or []
    assert len(points) == 31
    assert points[0]["time"] == "1일"
    assert data.get("interval") == "1d"


@pytest.mark.anyio
async def test_kosdaq_index_1m_has_enough_daily_bars(client: AsyncClient):
    response = await client.get(
        "/api/v1/stocks/history",
        params={"symbol": "kosdaq", "market": "index", "period": "1m"},
    )
    assert response.status_code == 200
    data = response.json()
    points = data.get("points") or []
    assert len(points) == 31
    assert data.get("interval") in ("1d", "1wk", "1h", "60m", "5m", "15m", "30m")
