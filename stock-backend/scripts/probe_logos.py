"""로고 소스별 성공률 빠른 점검 (로컬 실행용)."""
from __future__ import annotations

import asyncio
import sys

import httpx
from app.data.korea_universe import KOREA_UNIVERSE
from app.data.seed_stocks import US_SYMBOLS
from app.services.stock_logo_service import fetch_stock_logo, logo_candidate_urls


async def probe_fetch(market: str, symbol: str) -> str:
    try:
        await fetch_stock_logo(market, symbol)
        return "ok"
    except ValueError as exc:
        return str(exc)
    except Exception as exc:
        return type(exc).__name__


async def main() -> None:
    market = (sys.argv[1] if len(sys.argv) > 1 else "korea").lower()
    if market == "korea":
        symbols = [m["symbol"] for m in KOREA_UNIVERSE]
    elif market == "us":
        symbols = list(US_SYMBOLS)
    else:
        print("usage: probe_logos.py [korea|us]")
        return

    fails: list[tuple[str, str]] = []
    for sym in symbols:
        status = await probe_fetch(market, sym)
        if status != "ok":
            fails.append((sym, status))

    print(f"{market}: total={len(symbols)} fails={len(fails)}")
    for sym, status in fails[:60]:
        urls = logo_candidate_urls(market, sym)
        print(sym, status, "candidates=", len(urls))

    # 개별 URL HEAD/GET 샘플 (첫 실패 종목)
    if fails:
        sym = fails[0][0]
        print("\n--- per-url probe for", sym, "---")
        async with httpx.AsyncClient(follow_redirects=True, timeout=12.0) as client:
            for url in logo_candidate_urls(market, sym):
                try:
                    r = await client.get(url)
                    ct = r.headers.get("content-type", "")
                    print(r.status_code, len(r.content), ct[:40], url[:80])
                except Exception as exc:
                    print("ERR", exc, url[:80])


if __name__ == "__main__":
    asyncio.run(main())
