"""무료 배포(0.1 CPU)에서 요청이 몰려도 전체·지수 갱신이 설정 주기보다 자주 돌지 않는지."""

import asyncio

import pytest
from app.core.config import settings
from app.services.market_data import MarketDataService


@pytest.fixture
def svc(monkeypatch):
    s = MarketDataService(refresh_interval=10, fast_interval=3)
    calls = {"full": 0, "index": 0}

    async def fake_refresh():
        calls["full"] += 1

    async def fake_refresh_indices():
        calls["index"] += 1
        await asyncio.sleep(0)
        return []

    monkeypatch.setattr(s, "refresh", fake_refresh)
    monkeypatch.setattr(s, "refresh_indices", fake_refresh_indices)
    s._calls = calls
    return s


@pytest.mark.asyncio
async def test_schedule_refresh_respects_configured_full_interval(svc, monkeypatch):
    monkeypatch.setattr(settings, "MARKET_REFRESH_FULL_SEC", 60)
    for _ in range(20):
        svc.schedule_refresh()  # 브라우저가 /market/refresh 를 연달아 호출하는 상황
        await asyncio.sleep(0)
    await asyncio.sleep(0.05)
    assert svc._calls["full"] == 1


@pytest.mark.asyncio
async def test_schedule_refresh_local_default_unchanged(svc, monkeypatch):
    monkeypatch.setattr(settings, "MARKET_REFRESH_FULL_SEC", None)
    assert svc._configured_full_gap() == 0.0
    svc.schedule_refresh(min_gap=0)
    await asyncio.sleep(0.05)
    svc.schedule_refresh(min_gap=0)
    await asyncio.sleep(0.05)
    assert svc._calls["full"] == 2


@pytest.mark.asyncio
async def test_index_refresh_runs_once_per_interval(svc):
    svc._index_interval = 30
    for _ in range(25):
        svc.schedule_index_refresh()  # 지수 요청·WS 루프가 동시에 갱신을 거는 상황
        await asyncio.sleep(0)
    await asyncio.sleep(0.05)
    assert svc._calls["index"] == 1
    assert svc.index_refresh_due() is False


@pytest.mark.asyncio
async def test_ensure_fresh_does_not_undercut_configured_interval(svc, monkeypatch):
    from datetime import timedelta

    from app.core.datetime_utils import utc_now

    monkeypatch.setattr(settings, "MARKET_REFRESH_FULL_SEC", 60)
    svc._korea_source = "yahoo"
    svc._us_source = "yahoo"
    svc._last_updated = utc_now() - timedelta(seconds=30)
    svc.ensure_fresh(max_age_sec=10)  # 지수 API 가 10초 기준으로 호출
    await asyncio.sleep(0.05)
    assert svc._calls["full"] == 0
