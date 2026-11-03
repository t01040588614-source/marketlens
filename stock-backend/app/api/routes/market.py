import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from app.services import index_service
from app.services.exchange_calendar import export_holiday_dates_for_frontend
from app.services.market_data import market_data
from app.services.market_session import full_session_response, is_any_regular_session
from app.services.stock_logo_service import fetch_stock_logo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/market", tags=["시장"])


class IndexQuote(BaseModel):
    id: str
    name: str
    country: str
    category: str = "indices"
    price: float
    change: float
    change_percent: float
    status: str = "live"


class SectorItem(BaseModel):
    id: str
    label: str
    count: int


def _filter_index_rows(
    rows: list[dict],
    id_list: list[str] | None,
    category: str | None,
) -> list[dict]:
    out = rows
    if id_list:
        allowed = set(id_list)
        out = [i for i in out if i.get("id") in allowed]
    if category:
        out = [i for i in out if i.get("category") == category]
    return out


def _merge_indices_cache(rows: list[dict], id_list: list[str] | None, category: str | None) -> None:
    if not rows:
        return
    if id_list or category:
        merged = {i["id"]: i for i in market_data.get_indices()}
        for row in rows:
            merged[row["id"]] = row
        market_data.replace_indices_cache(list(merged.values()))
    else:
        market_data.replace_indices_cache(rows)


@router.get("/indices", response_model=list[IndexQuote])
async def list_indices(
    ids: str | None = Query(None, description="쉼표 구분 id (kospi,kosdaq,...)"),
    category: str | None = Query(None, description="indices|forex|commodity"),
):
    id_list = [s.strip() for s in ids.split(",")] if ids else None
    market_data.ensure_fresh(max_age_sec=10 if is_any_regular_session() else 25)

    cached = _filter_index_rows(market_data.get_indices(), id_list, category)
    if cached:
        # 캐시가 있으면 바로 응답. 백그라운드 갱신은 지수 주기에 한 번만
        # (요청마다 Yahoo 호출하면 무료 서버 CPU 과부하)
        if market_data.index_refresh_due():
            market_data.run_index_refresh(_refresh_indices_background(id_list, category))
        return cached

    # 캐시가 비어 있음(서버가 막 깨어남 등): Yahoo 응답을 최대 12초 기다리지 않고
    # 참고 시세로 바로 응답 + 실시세는 백그라운드에서 한 번만 받아 캐시·WebSocket 으로 반영
    fallback = index_service.static_indices(id_list, category=category)
    if market_data.index_refresh_due():
        market_data.run_index_refresh(_refresh_indices_background(id_list, category))
    if fallback:
        return fallback

    try:
        rows = await asyncio.wait_for(
            index_service.get_indices(id_list, category=category),
            timeout=12.0,
        )
        if rows:
            _merge_indices_cache(rows, id_list, category)
            return rows
    except Exception as exc:
        logger.warning("Index API fetch failed: %s", exc)

    raise HTTPException(
        status_code=503,
        detail="Index data temporarily unavailable. Start backend on port 8000.",
    )


async def _refresh_indices_background(id_list: list[str] | None, category: str | None) -> None:
    try:
        rows = await index_service.get_indices(id_list, category=category)
        if rows:
            _merge_indices_cache(rows, id_list, category)
    except Exception as exc:
        logger.debug("Background index refresh skipped: %s", exc)


@router.get("/sectors", response_model=list[SectorItem])
async def list_sectors():
    return index_service.SECTOR_COUNTS


@router.get("/session")
async def market_session():
    """한국·미국 장 상태 (휴장 캘린더·조기 마감 반영)."""
    return full_session_response()


@router.get("/holidays")
async def market_holidays():
    """프론트 오프라인 fallback용 휴장일 목록 (KRX·NYSE CSV와 동기)."""
    return export_holiday_dates_for_frontend()


@router.get("/symbols")
async def list_cached_symbols():
    """캐시에 있는 전 종목 코드 — WebSocket 전역 구독·갱신용."""
    market_data.ensure_fresh()
    symbols = market_data.get_all_symbols()
    return {
        "symbols": symbols,
        "count": len(symbols),
        "korea": len(market_data.get_by_type("korea")),
        "us": len(market_data.get_by_type("us")),
        "asia": len(market_data.get_by_type("asia")),
        "europe": len(market_data.get_by_type("europe")),
    }


@router.get("/kis-realtime")
async def kis_realtime_status():
    """KIS H0STCNT0 WebSocket PoC 상태 (HTS급 체결 틱 — 키·장중 필요)."""
    from app.services.kis_realtime_service import kis_realtime

    return kis_realtime.status()


@router.get("/cache-status")
async def cache_status():
    """시세 캐시 상태 (Yahoo 실패·참고 시세 여부)"""
    from app.services.websocket_manager import ws_manager

    body = market_data.status()
    body.update(ws_manager.broadcast_status())
    return body


@router.post("/refresh")
async def trigger_refresh():
    """시세 캐시 갱신 요청 (백그라운드, 즉시 상태 반환)"""
    market_data.schedule_refresh()
    return market_data.status()


@router.get("/stock-logo/{market}/{symbol}")
async def stock_logo(market: str, symbol: str):
    """종목 로고 (FnGuide·FMP 등 다중 소스, 브라우저 핫링크 회피)."""
    if market not in ("korea", "us"):
        raise HTTPException(status_code=400, detail="market must be korea or us")
    try:
        data, media_type = await fetch_stock_logo(market, symbol)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.warning("Stock logo fetch failed %s/%s: %s", market, symbol, exc)
        raise HTTPException(status_code=404, detail="logo not found") from exc
    return Response(
        content=data,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
