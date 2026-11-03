"""아시아·유럽·엣지 티커 로고 점검."""
from __future__ import annotations

import asyncio

from app.data.asia_universe import ASIA_UNIVERSE
from app.data.europe_universe import EUROPE_UNIVERSE
from app.services.stock_logo_service import fetch_stock_logo


async def try_markets(label: str, symbol: str) -> None:
    for market in ("korea", "us"):
        try:
            await fetch_stock_logo(market, symbol)
            print(f"OK {label} market={market} sym={symbol}")
            return
        except ValueError:
            pass
    print(f"FAIL {label} sym={symbol}")


async def main() -> None:
    for meta in ASIA_UNIVERSE[:8]:
        await try_markets(f"asia/{meta['name']}", meta["symbol"])
    for meta in EUROPE_UNIVERSE[:8]:
        await try_markets(f"eu/{meta['name']}", meta["symbol"])
    # FMP yahoo-style tickers as US path
    for meta in ASIA_UNIVERSE[:5]:
        y = meta["yahoo"]
        try:
            await fetch_stock_logo("us", y)
            print(f"OK fmp-yahoo {y}")
        except ValueError:
            print(f"FAIL fmp-yahoo {y}")


if __name__ == "__main__":
    asyncio.run(main())
