import asyncio
import logging
from datetime import datetime, timedelta

from app.core.datetime_utils import utc_now
from app.data.asia_universe import ASIA_UNIVERSE
from app.data.europe_universe import EUROPE_UNIVERSE
from app.data.korea_universe import KOREA_UNIVERSE
from app.data.seed_stocks import (
    build_asia_seed_stocks,
    build_europe_seed_stocks,
    build_korea_seed_stocks,
    build_us_seed_stocks,
)
from app.data.stock_display_names import apply_display_name, registry_name
from app.services import index_service
from app.services.korea_valuation_cache import (
    apply_valuation_to_rows,
    merge_korea_fundamentals,
    warm_valuation_cache_async,
)
from app.services.krx_listing_cache import apply_krx_mcap_to_rows
from app.services.market_session import is_any_regular_session, refresh_profile, session_status
from app.services.stock_providers.kis_korea_provider import KisKoreaProvider
from app.services.stock_providers.korea_fdr_provider import KoreaFdrProvider
from app.services.stock_providers.premium_us_provider import PremiumUsProvider
from app.services.stock_providers.yahoo_intl_provider import YahooIntlProvider
from app.services.stock_providers.yahoo_korea_provider import YahooKoreaProvider
from app.services.stock_providers.yahoo_provider import YahooFinanceProvider

logger = logging.getLogger(__name__)

KOREA_SYMBOLS = {m["symbol"] for m in KOREA_UNIVERSE}
ASIA_SYMBOLS = {m["symbol"] for m in ASIA_UNIVERSE}
EUROPE_SYMBOLS = {m["symbol"] for m in EUROPE_UNIVERSE}
INTL_SYMBOLS = ASIA_SYMBOLS | EUROPE_SYMBOLS

# Yahoo 429·네트워크 지연 시 전체 refresh가 멈추지 않도록 (FDR·캐시 WS 푸시 유지)
YAHOO_FETCH_TIMEOUT_SEC = 38.0


class MarketDataService:
    """실시간 시세 캐시 — FDR(한국) + Yahoo 일괄(미국), WS는 캐시 푸시."""

    def __init__(self, refresh_interval: int = 15, fast_interval: int = 4):
        self.korea_kis = KisKoreaProvider()
        self.korea_fdr = KoreaFdrProvider()
        self.korea_yahoo = YahooKoreaProvider()
        self.us_premium = PremiumUsProvider()
        self.us_provider = YahooFinanceProvider()
        self.asia_yahoo = YahooIntlProvider(ASIA_UNIVERSE)
        self.europe_yahoo = YahooIntlProvider(EUROPE_UNIVERSE)
        self._cache: dict[str, dict] = {}
        self._indices_cache: list[dict] = []
        self._last_updated: datetime | None = None
        self._refresh_interval = refresh_interval
        self._fast_interval = fast_interval
        self._running = False
        self._task: asyncio.Task | None = None
        self._fast_task: asyncio.Task | None = None
        self._index_task: asyncio.Task | None = None
        self._korea_source: str = "none"
        self._us_source: str = "none"
        self._last_error: str | None = None
        self._subscribed_symbols: set[str] = set()
        self._refresh_lock = asyncio.Lock()
        self._fast_rotation = 0
        self._fast_batch_size = 24
        self._stale_push_sec = 12
        self._ensure_fresh_default = 18
        self._index_interval = 25
        self._background_tasks: set[asyncio.Task] = set()
        self._index_refresh_task: asyncio.Task | None = None
        self._last_index_scheduled: datetime | None = None
        self._last_ws_driven_refresh: datetime | None = None
        self._last_full_scheduled: datetime | None = None
        self._symbol_last_refresh: dict[str, datetime] = {}
        self._symbol_refresh_in_flight: set[str] = set()
        self._pending_symbol_refresh: set[str] = set()
        self._symbol_refresh_worker: asyncio.Task | None = None
        self._full_refresh_running = False
        self._yahoo_skip_until: datetime | None = None
        self._yahoo_fetch_lock = asyncio.Lock()
        self._sync_refresh_profile()

    def set_subscribed_symbols(self, symbols: set[str]) -> None:
        self._subscribed_symbols = set(symbols)

    def _apply_stocks(self, stocks: list[dict], stock_type: str) -> None:
        if stock_type == "korea" and stocks:
            apply_krx_mcap_to_rows(stocks)
        for stock in stocks:
            stock["type"] = stock_type
            stock.pop("data_source", None)
            sym = stock["symbol"]
            prev = self._cache.get(sym)
            if prev and stock.get("volume") is not None:
                try:
                    stock["volume"] = max(
                        int(prev.get("volume") or 0),
                        int(stock["volume"]),
                    )
                except (TypeError, ValueError):
                    pass
            self._sync_change_from_close(stock)
            apply_display_name(stock)
            self._cache[sym] = stock

    def _sync_change_from_close(self, row: dict) -> None:
        try:
            price = float(row.get("price") or 0)
            prev = float(row.get("previous_close") or 0)
            if prev <= 0:
                prev = price - float(row.get("change") or 0)
            if price <= 0 or prev <= 0:
                return
            ch = price - prev
            dec = 4 if prev < 100 else 2
            row["change"] = round(ch, dec)
            row["change_percent"] = round((ch / prev) * 100, 2)
            row["previous_close"] = round(prev, dec)
        except (TypeError, ValueError):
            return

    def _merge_patch(self, patch: dict, stock_type: str) -> None:
        sym = patch["symbol"]
        prev_row = self._cache.get(sym, {})
        merged = {
            **prev_row,
            **patch,
            "type": stock_type,
            "symbol": sym,
        }
        if patch.get("previous_close"):
            merged["previous_close"] = patch["previous_close"]
        elif prev_row.get("previous_close"):
            merged["previous_close"] = prev_row["previous_close"]
        if "volume" in patch and patch.get("volume") is not None:
            try:
                new_vol = int(patch["volume"])
                prev_vol = int(prev_row.get("volume") or 0)
                merged["volume"] = max(prev_vol, new_vol)
            except (TypeError, ValueError):
                pass
        if "price" in patch and patch.get("price") is not None:
            self._sync_change_from_close(merged)
        apply_display_name(merged)
        self._cache[sym] = merged

    def _yahoo_in_cooldown(self) -> bool:
        return self._yahoo_skip_until is not None and utc_now() < self._yahoo_skip_until

    @staticmethod
    def _yahoo_failure_reason(exc: BaseException | None = None, text: str | None = None) -> str:
        blob = f"{exc or ''} {text or ''}".lower()
        if "429" in blob or "too many" in blob or "rate limit" in blob:
            return "yahoo_rate_limit"
        return "yahoo_timeout"

    def yahoo_refresh_throttled(self) -> bool:
        """Yahoo 429·타임아웃 시 갱신·WS 주기 자동 완화."""
        if self._yahoo_in_cooldown():
            return True
        return self._last_error in ("yahoo_rate_limit", "yahoo_timeout")

    def _mark_yahoo_cooldown(
        self,
        minutes: float = 3.0,
        *,
        reason: str = "yahoo_timeout",
    ) -> None:
        if reason == "yahoo_rate_limit":
            minutes = max(minutes, 5.0)
        self._yahoo_skip_until = utc_now() + timedelta(minutes=minutes)
        self._last_error = reason

    def _mark_yahoo_failure(
        self, exc: BaseException | None = None, *, minutes: float = 3.0
    ) -> None:
        reason = self._yahoo_failure_reason(exc)
        self._mark_yahoo_cooldown(minutes, reason=reason)

    def _reconcile_last_error(self) -> None:
        """Yahoo만 실패하고 FDR·프리미엄 등으로 캐시가 갱신된 경우 UI 오류를 내리지 않음."""
        err = self._last_error
        if err not in ("yahoo_timeout", "yahoo_rate_limit"):
            return
        if not self._last_updated:
            return
        age = (utc_now() - self._last_updated).total_seconds()
        if age > self._refresh_interval * 3:
            return
        kr_ok = self._korea_source in ("fdr", "yahoo", "yahoo+kis_watch", "kis")
        us_ok = self._us_source not in ("none",) and bool(self.get_by_type("us"))
        if kr_ok and us_ok:
            self._last_error = None

    async def _yahoo_korea_stocks(self) -> list[dict]:
        if self._yahoo_in_cooldown():
            return []
        try:
            async with self._yahoo_fetch_lock:
                if self._yahoo_in_cooldown():
                    return []
                return await asyncio.wait_for(
                    self.korea_yahoo.get_stocks(),
                    timeout=YAHOO_FETCH_TIMEOUT_SEC,
                )
        except TimeoutError:
            logger.warning(
                "Korea Yahoo fetch timed out (%.0fs) — FDR·캐시 폴백",
                YAHOO_FETCH_TIMEOUT_SEC,
            )
            self._mark_yahoo_failure(minutes=3.0)
            return []
        except Exception as exc:
            logger.warning("Korea Yahoo fetch failed: %s", exc)
            self._mark_yahoo_failure(exc)
            return []

    async def _fetch_korea(self) -> list[dict]:
        """Yahoo fast_info(장중 현재가) 우선 — KIS는 구독 종목 refresh_symbols 에서만."""
        yahoo_rows, fdr_rows = await asyncio.gather(
            self._yahoo_korea_stocks(),
            self.korea_fdr.get_stocks(),
        )
        by_sym: dict[str, dict] = {r["symbol"]: r for r in fdr_rows if r.get("symbol")}
        if yahoo_rows:
            for row in yahoo_rows:
                sym = row.get("symbol")
                if not sym:
                    continue
                by_sym[sym] = merge_korea_fundamentals(by_sym.get(sym), row)
            self._korea_source = "yahoo"
            if self.korea_kis.is_configured():
                self._korea_source = "yahoo+kis_watch"
            rows = list(by_sym.values())
            apply_valuation_to_rows(rows)
            return rows
        if fdr_rows:
            apply_valuation_to_rows(fdr_rows)
            self._korea_source = "fdr"
            return fdr_rows
        if self.korea_kis.is_configured() and self._subscribed_symbols:
            kr_sub = [s for s in self._subscribed_symbols if s in KOREA_SYMBOLS]
            if kr_sub:
                patches = await self.korea_kis.get_quote_patches(kr_sub[:40])
                if patches:
                    self._korea_source = "kis"
                    return list(patches.values())
        return []

    async def _yahoo_us_stocks(self) -> list[dict]:
        if self._yahoo_in_cooldown():
            return []
        try:
            async with self._yahoo_fetch_lock:
                if self._yahoo_in_cooldown():
                    return []
                return await asyncio.wait_for(
                    self.us_provider.get_stocks(),
                    timeout=YAHOO_FETCH_TIMEOUT_SEC,
                )
        except TimeoutError:
            logger.warning(
                "US Yahoo fetch timed out (%.0fs)",
                YAHOO_FETCH_TIMEOUT_SEC,
            )
            self._mark_yahoo_failure(minutes=3.0)
            return []
        except Exception as exc:
            logger.warning("US Yahoo fetch failed: %s", exc)
            self._mark_yahoo_failure(exc)
            return []

    async def _fetch_us(self) -> list[dict]:
        premium = await self.us_premium.get_stocks()
        if premium:
            src = premium[0].get("data_source") or "premium"
            self._us_source = str(src)
            return premium
        rows = await self._yahoo_us_stocks()
        if rows:
            self._us_source = "yahoo"
        return rows

    async def _fetch_intl(self, provider: YahooIntlProvider) -> list[dict]:
        if self._yahoo_in_cooldown():
            return []
        try:
            async with self._yahoo_fetch_lock:
                if self._yahoo_in_cooldown():
                    return []
                return await asyncio.wait_for(
                    provider.get_stocks(),
                    timeout=YAHOO_FETCH_TIMEOUT_SEC,
                )
        except TimeoutError:
            logger.warning("Intl Yahoo fetch timed out (%.0fs)", YAHOO_FETCH_TIMEOUT_SEC)
            self._mark_yahoo_failure(minutes=3.0)
            return []
        except Exception as exc:
            logger.warning("Intl Yahoo fetch failed: %s", exc)
            self._mark_yahoo_failure(exc)
            return []

    async def _fetch_asia(self) -> list[dict]:
        return await self._fetch_intl(self.asia_yahoo)

    async def _fetch_europe(self) -> list[dict]:
        return await self._fetch_intl(self.europe_yahoo)

    async def refresh_symbols(self, symbols: list[str]) -> None:
        if not symbols:
            return
        pending = [s for s in symbols if s not in self._symbol_refresh_in_flight]
        if not pending:
            return
        for s in pending:
            self._symbol_refresh_in_flight.add(s)

        try:
            symbols = pending
            kr = [s for s in symbols if s in KOREA_SYMBOLS]
            asia = [s for s in symbols if s in ASIA_SYMBOLS]
            europe = [s for s in symbols if s in EUROPE_SYMBOLS]
            us = [s for s in symbols if s not in KOREA_SYMBOLS and s not in INTL_SYMBOLS]

            patches: dict[str, dict] = {}
            if kr:
                yahoo_rows: list[dict] = []
                if not self._yahoo_in_cooldown():
                    try:
                        async with self._yahoo_fetch_lock:
                            if self._yahoo_in_cooldown():
                                yahoo_rows = []
                            else:
                                yahoo_rows = await asyncio.wait_for(
                                    self.korea_yahoo.get_quotes_full(kr),
                                    timeout=YAHOO_FETCH_TIMEOUT_SEC,
                                )
                    except TimeoutError:
                        logger.warning("Korea Yahoo symbol batch timed out")
                        self._mark_yahoo_failure(minutes=3.0)
                        yahoo_rows = []
                    except Exception as exc:
                        logger.warning("Korea Yahoo symbol batch failed: %s", exc)
                        self._mark_yahoo_failure(exc)
                        yahoo_rows = []
                fdr_patches = await self.korea_fdr.get_quote_patches(kr)
                for row in yahoo_rows:
                    patches[row["symbol"]] = row
                if self.korea_kis.is_configured():
                    patches.update(await self.korea_kis.get_quote_patches(kr))
                for sym, fp in fdr_patches.items():
                    if sym not in patches:
                        patches[sym] = fp
                        continue
                    cur = patches[sym]
                    if not int(cur.get("volume") or 0) and fp.get("volume"):
                        cur["volume"] = fp["volume"]
                    if not float(cur.get("open") or 0) and fp.get("open"):
                        cur["open"] = fp["open"]
                    if not float(cur.get("high") or 0) and fp.get("high"):
                        cur["high"] = fp["high"]
                    if not float(cur.get("low") or 0) and fp.get("low"):
                        cur["low"] = fp["low"]
                if len(patches) < len(kr):
                    patches.update(fdr_patches)

            asia_rows: list[dict] = []
            europe_rows: list[dict] = []
            if asia and not self._yahoo_in_cooldown():
                try:
                    async with self._yahoo_fetch_lock:
                        if not self._yahoo_in_cooldown():
                            asia_rows = await asyncio.wait_for(
                                self.asia_yahoo.get_quotes_full(asia),
                                timeout=YAHOO_FETCH_TIMEOUT_SEC,
                            )
                except TimeoutError:
                    self._mark_yahoo_failure(minutes=3.0)
                except Exception as exc:
                    logger.warning("Asia Yahoo symbol batch failed: %s", exc)
                    self._mark_yahoo_failure(exc)
            if europe and not self._yahoo_in_cooldown():
                try:
                    async with self._yahoo_fetch_lock:
                        if not self._yahoo_in_cooldown():
                            europe_rows = await asyncio.wait_for(
                                self.europe_yahoo.get_quotes_full(europe),
                                timeout=YAHOO_FETCH_TIMEOUT_SEC,
                            )
                except TimeoutError:
                    self._mark_yahoo_failure(minutes=3.0)
                except Exception as exc:
                    logger.warning("Europe Yahoo symbol batch failed: %s", exc)
                    self._mark_yahoo_failure(exc)

            us_rows: list[dict] = []
            if us:
                us_rows = await self.us_premium.get_quotes_full(us)
                if len(us_rows) < len(us):
                    have = {r["symbol"] for r in us_rows}
                    missing = [s for s in us if s not in have]
                    if missing:
                        us_rows.extend(await self.us_provider.get_quotes_full(missing))

            if not patches and not us_rows and not asia_rows and not europe_rows:
                return

            async with self._refresh_lock:
                for patch in patches.values():
                    self._merge_patch(patch, "korea")
                for row in asia_rows:
                    self._merge_patch(row, "asia")
                for row in europe_rows:
                    self._merge_patch(row, "europe")
                for row in us_rows:
                    self._merge_patch(row, "us")
                if self._cache:
                    self._last_updated = utc_now()
            now = utc_now()
            for sym in symbols:
                self._symbol_last_refresh[sym] = now
            self._reconcile_last_error()
        except Exception as exc:
            logger.warning("refresh_symbols failed: %s", exc)
        finally:
            for s in pending:
                self._symbol_refresh_in_flight.discard(s)

    def schedule_symbol_fresh(self, symbol: str, max_age_sec: float | None = None) -> None:
        """HTTP 응답을 막지 않고 백그라운드 갱신 (WS·fast 루프 보조)."""
        if not symbol:
            return
        limit = max_age_sec
        if limit is None:
            limit = 0.65 if is_any_regular_session() else 10.0
        last = self._symbol_last_refresh.get(symbol)
        if last is not None and (utc_now() - last).total_seconds() < limit:
            return
        self.schedule_refresh_symbols([symbol])

    async def ensure_symbol_fresh(self, symbol: str, max_age_sec: float | None = None) -> None:
        """캐시 없을 때만 동기 갱신 — 있으면 schedule만."""
        if not symbol:
            return
        row = self._cache.get(symbol)
        if row and float(row.get("price") or 0) > 0:
            self.schedule_symbol_fresh(symbol, max_age_sec)
            return
        limit = max_age_sec
        if limit is None:
            limit = 1.2 if is_any_regular_session() else 10.0
        last = self._symbol_last_refresh.get(symbol)
        if last is not None and (utc_now() - last).total_seconds() < limit:
            return
        await self.refresh_symbols([symbol])

    async def refresh(self):
        """전체 유니버스 갱신"""
        if self._full_refresh_running:
            return
        self._full_refresh_running = True
        self._last_error = None
        try:
            korea_stocks, us_stocks, asia_stocks, europe_stocks = await asyncio.gather(
                self._fetch_korea(),
                self._fetch_us(),
                self._fetch_asia(),
                self._fetch_europe(),
            )
        except Exception as exc:
            logger.exception("Stock fetch failed: %s", exc)
            self._last_error = str(exc)
            korea_stocks = []
            us_stocks = []
            asia_stocks = []
            europe_stocks = []

        indices: list[dict] = []
        try:
            indices = await index_service.get_indices()
        except Exception as exc:
            logger.warning("Index fetch failed: %s", exc)

        try:
            async with self._refresh_lock:
                if korea_stocks:
                    self._apply_stocks(korea_stocks, "korea")
                    apply_valuation_to_rows(self.get_by_type("korea"))
                else:
                    fdr_retry = await self.korea_fdr.get_stocks()
                    if fdr_retry:
                        self._apply_stocks(fdr_retry, "korea")
                        self._korea_source = "fdr"
                        logger.info("Korea FDR fallback applied (%s symbols)", len(fdr_retry))
                    elif not self.get_by_type("korea"):
                        seed = build_korea_seed_stocks()
                        self._korea_source = "reference"
                        self._apply_stocks(seed, "korea")
                        self._last_error = "yahoo_empty"
                        logger.info("Using reference Korea seed (%s symbols)", len(seed))

                if us_stocks:
                    self._apply_stocks(us_stocks, "us")
                elif not self.get_by_type("us"):
                    seed = build_us_seed_stocks()
                    self._us_source = "reference"
                    self._apply_stocks(seed, "us")
                    self._last_error = self._last_error or "yahoo_empty"
                    logger.info("Using reference US seed (%s symbols)", len(seed))

                if asia_stocks:
                    self._apply_stocks(asia_stocks, "asia")
                elif not self.get_by_type("asia"):
                    self._apply_stocks(build_asia_seed_stocks(), "asia")

                if europe_stocks:
                    self._apply_stocks(europe_stocks, "europe")
                elif not self.get_by_type("europe"):
                    self._apply_stocks(build_europe_seed_stocks(), "europe")

                if indices:
                    self._indices_cache = indices

                if self._cache:
                    self._last_updated = utc_now()
            self._reconcile_last_error()
        except Exception as exc:
            logger.exception("Market refresh merge failed: %s", exc)
            self._last_error = str(exc)
        finally:
            self._full_refresh_running = False

    def _ensure_seed_cache(self) -> None:
        """API·헬스체크가 Yahoo 응답을 기다리지 않도록 기본 시드로 즉시 채움."""
        if not self.get_by_type("korea"):
            self._apply_stocks(build_korea_seed_stocks(), "korea")
            self._korea_source = "reference"
        if not self.get_by_type("us"):
            self._apply_stocks(build_us_seed_stocks(), "us")
            self._us_source = "reference"
        if not self.get_by_type("asia"):
            self._apply_stocks(build_asia_seed_stocks(), "asia")
        if not self.get_by_type("europe"):
            self._apply_stocks(build_europe_seed_stocks(), "europe")
        # 참고 시드만 있을 때 last_updated를 찍지 않음 → ensure_fresh가 즉시 실시간 갱신 예약

    async def start_refresh_loop(self):
        if self._running:
            return
        self._running = True
        self._ensure_seed_cache()

        async def _initial_refresh() -> None:
            try:
                await self.refresh()
            except Exception as exc:
                logger.exception("Initial market refresh failed: %s", exc)

        init_task = asyncio.create_task(_initial_refresh())
        self._background_tasks.add(init_task)
        init_task.add_done_callback(self._background_tasks.discard)

        async def _warm_korea_valuation() -> None:
            try:
                await warm_valuation_cache_async()
                apply_valuation_to_rows(self.get_by_type("korea"))
            except Exception as exc:
                logger.warning("Korea valuation warm failed: %s", exc)

        warm_task = asyncio.create_task(_warm_korea_valuation())
        self._background_tasks.add(warm_task)
        warm_task.add_done_callback(self._background_tasks.discard)

        self._task = asyncio.create_task(self._refresh_loop())
        self._fast_task = asyncio.create_task(self._fast_refresh_loop())
        self._index_task = asyncio.create_task(self._index_refresh_loop())

    async def stop_refresh_loop(self):
        self._running = False
        for task in (self._task, self._fast_task, self._index_task):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    def _sync_refresh_profile(self) -> None:
        p = refresh_profile(yahoo_throttled=self.yahoo_refresh_throttled())
        self._refresh_interval = p["full_interval"]
        self._fast_interval = p["fast_interval"]
        self._fast_batch_size = p["fast_batch"]
        self._stale_push_sec = p["stale_push_sec"]
        self._ensure_fresh_default = p["ensure_fresh_sec"]
        self._index_interval = p.get("index_interval", 25)

    async def _refresh_loop(self):
        while self._running:
            self._sync_refresh_profile()
            await asyncio.sleep(self._refresh_interval)
            try:
                await self.refresh()
            except Exception as exc:
                logger.exception("Background refresh failed: %s", exc)

    def _universe_refresh_symbols(self) -> list[str]:
        """구독·캐시 전체 — 보드에 없는 종목도 fast 루프에 포함."""
        cached = sorted(self._cache.keys())
        if cached:
            return cached
        return sorted(self._subscribed_symbols)

    def _fast_refresh_batch(self) -> list[str]:
        symbols = self._universe_refresh_symbols()
        if not symbols:
            return []
        if is_any_regular_session() and len(symbols) <= self._fast_batch_size:
            return symbols
        n = len(symbols)
        start = int(self._fast_rotation % n)
        batch_end = start + int(self._fast_batch_size)
        self._fast_rotation = (start + int(self._fast_batch_size)) % n
        if batch_end <= n:
            return symbols[start:batch_end]
        wrap = batch_end - n
        return symbols[start:] + symbols[:wrap]

    async def _fast_refresh_loop(self):
        """WebSocket 구독 종목 우선 갱신 (배치 로테이션)"""
        while self._running:
            self._sync_refresh_profile()
            await asyncio.sleep(self._fast_interval)
            batch = self._fast_refresh_batch()
            if not batch:
                continue
            age = self.cache_age_seconds()
            if is_any_regular_session() and age is not None and age > 4:
                self.schedule_refresh(min_gap=1.0)
            try:
                self.schedule_refresh_symbols(batch)
            except Exception as exc:
                logger.warning("Fast refresh batch failed: %s", exc)

    async def _index_refresh_loop(self):
        """지수·FX — Yahoo fast_info 주기 갱신 (WS 캐시 최신화)."""
        while self._running:
            self._sync_refresh_profile()
            await asyncio.sleep(self._index_interval)
            try:
                await self.refresh_indices()
            except Exception as exc:
                logger.warning("Index refresh loop failed: %s", exc)

    def get_all_symbols(self) -> list[str]:
        return list(self._cache.keys())

    def get_all(self) -> list[dict]:
        return list(self._cache.values())

    def get_by_type(self, stock_type: str) -> list[dict]:
        rows = [s for s in self._cache.values() if s.get("type") == stock_type]
        for row in rows:
            apply_display_name(row)
        return rows

    def apply_kis_tick(self, symbol: str, price: float) -> None:
        """KIS WS 체결 틱 → 캐시 즉시 반영 (PoC)."""
        sym = symbol.strip().zfill(6)
        row = self._cache.get(sym)
        if not row:
            row = {
                "symbol": sym,
                "name": registry_name(sym) or sym,
                "price": price,
                "change": 0.0,
                "change_percent": 0.0,
                "volume": 0,
                "type": "korea",
                "data_source": "kis_ws",
            }
            self._cache[sym] = row
        else:
            prev = float(row.get("price") or price)
            row["price"] = price
            row["change"] = price - float(row.get("previous_close") or prev)
            if row.get("previous_close"):
                pc = float(row["previous_close"])
                row["change_percent"] = ((price - pc) / pc * 100) if pc else 0.0
            row["data_source"] = "kis_ws"
        from app.core.datetime_utils import utc_now

        self._last_updated = utc_now()

    def get_by_symbol(self, symbol: str) -> dict | None:
        row = self._cache.get(symbol)
        if row:
            apply_display_name(row)
        return row

    def get_cached_quotes(self, symbols: list[str]) -> dict:
        out = {}
        for s in symbols:
            row = self._cache.get(s)
            if row and row.get("price") is not None:
                out[s] = float(row["price"])
        return out

    def get_cached_ticks(self, symbols: list[str]) -> list[dict]:
        ticks = []
        for s in symbols:
            row = self._cache.get(s)
            if not row:
                continue
            ticks.append(
                {
                    "symbol": s,
                    "price": row.get("price", 0),
                    "change": row.get("change", 0),
                    "change_percent": row.get("change_percent", 0),
                    "volume": row.get("volume", 0),
                }
            )
        return ticks

    async def get_quotes(self, symbols: list[str]) -> dict:
        """WebSocket 호환 — 캐시 우선 (외부 API 직접 호출 없음)."""
        return self.get_cached_quotes(symbols)

    def last_updated(self) -> datetime | None:
        return self._last_updated

    def get_indices(self) -> list[dict]:
        return list(self._indices_cache)

    def replace_indices_cache(self, rows: list[dict]) -> None:
        if rows:
            self._indices_cache = list(rows)

    async def refresh_indices(self) -> list[dict]:
        self._indices_cache = await index_service.get_indices()
        return self._indices_cache

    def ensure_fresh(self, max_age_sec: int | None = None) -> None:
        """캐시가 오래되면 백그라운드 전체 갱신."""
        if self._korea_source == "reference" or self._us_source == "reference":
            self.schedule_refresh()
            return
        limit = max_age_sec if max_age_sec is not None else self._ensure_fresh_default
        limit = max(limit, self._configured_full_gap())
        lu = self._last_updated
        if lu is None:
            self.schedule_refresh()
            return
        age = (utc_now() - lu).total_seconds()
        if age > limit:
            self.schedule_refresh()

    def schedule_refresh_symbols_debounced(self, symbols: list[str], min_gap: float = 2.0) -> None:
        now = utc_now()
        if self._last_ws_driven_refresh is not None:
            if (now - self._last_ws_driven_refresh).total_seconds() < min_gap:
                return
        self._last_ws_driven_refresh = now
        self.schedule_refresh_symbols(symbols)

    def schedule_refresh_symbols(self, symbols: list[str]) -> None:
        """WS·HTTP에서 연속 호출 시 심볼을 합쳐 한 워커로 처리 (Yahoo lock 폭주 방지)."""
        if not symbols:
            return
        self._pending_symbol_refresh.update(symbols)
        worker = self._symbol_refresh_worker
        if worker is not None and not worker.done():
            return

        async def _drain():
            try:
                await asyncio.sleep(0.08)
                while self._pending_symbol_refresh:
                    batch = list(self._pending_symbol_refresh)
                    self._pending_symbol_refresh.clear()
                    await self.refresh_symbols(batch)
            except Exception as exc:
                logger.warning("Scheduled symbol refresh failed: %s", exc)
            finally:
                self._symbol_refresh_worker = None
                if self._pending_symbol_refresh:
                    more = list(self._pending_symbol_refresh)
                    self.schedule_refresh_symbols(more)

        self._symbol_refresh_worker = asyncio.create_task(_drain())
        self._background_tasks.add(self._symbol_refresh_worker)
        self._symbol_refresh_worker.add_done_callback(self._background_tasks.discard)

    def cache_age_seconds(self) -> float | None:
        lu = self._last_updated
        if not lu:
            return None
        return (utc_now() - lu).total_seconds()

    def index_refresh_due(self) -> bool:
        """지수 갱신을 새로 걸어도 되는지 — 진행 중이거나 지수 주기 안이면 False."""
        task = self._index_refresh_task
        if task is not None and not task.done():
            return False
        last = self._last_index_scheduled
        if last is None:
            return True
        return (utc_now() - last).total_seconds() >= max(5, int(self._index_interval))

    def run_index_refresh(self, coro) -> None:
        """지수 갱신 코루틴을 하나만 돌게 등록 (index_refresh_due 와 짝)."""
        self._last_index_scheduled = utc_now()
        task = asyncio.create_task(coro)
        self._index_refresh_task = task
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def schedule_index_refresh(self) -> None:
        """지수 캐시만 백그라운드 갱신 (WS 루프 블로킹 방지). 중복·과다 호출은 건너뜀."""
        if not self.index_refresh_due():
            return

        async def _run():
            try:
                await self.refresh_indices()
            except Exception as exc:
                logger.warning("Scheduled index refresh failed: %s", exc)

        self.run_index_refresh(_run())

    @staticmethod
    def _configured_full_gap() -> float:
        """MARKET_REFRESH_FULL_SEC 가 있으면(저사양 배포) 그보다 자주 전체 갱신하지 않음."""
        from app.core.config import settings

        full = settings.MARKET_REFRESH_FULL_SEC
        return float(full) if full else 0.0

    def schedule_refresh(self, min_gap: float = 3.0) -> None:
        """전체 갱신을 백그라운드로 요청 (HTTP 응답 지연 방지)."""
        if self._refresh_lock.locked():
            return
        min_gap = max(min_gap, self._configured_full_gap())
        now = utc_now()
        if self._last_full_scheduled is not None:
            if (now - self._last_full_scheduled).total_seconds() < min_gap:
                return
        self._last_full_scheduled = now

        async def _run():
            try:
                await self.refresh()
            except Exception as exc:
                logger.exception("Scheduled refresh failed: %s", exc)

        task = asyncio.create_task(_run())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def status(self) -> dict:
        korea = self.get_by_type("korea")
        us = self.get_by_type("us")
        message = None
        if self._korea_source == "reference" or self._us_source == "reference":
            message = (
                "일부 시세는 참고가입니다. Yahoo·FDR에서 갱신 중이며 "
                "WebSocket으로 캐시가 약 1초마다 푸시됩니다."
            )
        elif self._last_error in ("yahoo_timeout", "yahoo_rate_limit"):
            message = (
                "Yahoo Finance 응답 지연·제한(429) — 갱신 주기·폴링을 자동 완화합니다. "
                "복구되면 실시간 설정으로 돌아갑니다."
            )
        elif self._last_error:
            message = "시세 소스 일시 오류 — 자동 재시도 중입니다."
        from app.integrations.registry import list_integrations

        active = [i["id"] for i in list_integrations() if i.get("active")]
        sess = session_status()
        age = self.cache_age_seconds()
        if sess.get("krMarketOpen") or sess.get("usMarketOpen"):
            message = (
                message
                or "장중: Yahoo/KIS fast 갱신 + WebSocket 1초 푸시 (HTS 틱급은 KIS WS 별도 계약)"
            )
        throttled = self.yahoo_refresh_throttled()
        prof = refresh_profile(yahoo_throttled=throttled)
        from app.core.redis_store import redis_status
        from app.integrations import kis_client

        kis = kis_client.fetch_stats()
        from app.services.kis_realtime_service import kis_realtime

        kis_ws = kis_realtime.status()
        realtime_mode = (
            "kis_hts_tick_poc" if kis_ws.get("connected") else "quasi_realtime_cache_ws"
        )
        return {
            "realtime_mode": realtime_mode,
            "kis_realtime": kis_ws,
            "realtime_disclaimer": (
                "준실시간(시세 캐시 + WebSocket 푸시). HTS급 체결 틱 스트림은 아닙니다."
            ),
            "kis_configured": kis.get("configured"),
            "kis_last_fetch_ms": kis.get("last_fetch_ms"),
            "kis_last_fetch_at": kis.get("last_fetch_at"),
            "kis_last_batch_count": kis.get("last_batch_count"),
            "redis": redis_status(),
            "korea_count": len(korea),
            "us_count": len(us),
            "korea_source": self._korea_source,
            "us_source": self._us_source,
            "last_updated": self._last_updated.isoformat() if self._last_updated else None,
            "cache_age_seconds": age,
            "refresh_interval_sec": self._refresh_interval,
            "fast_refresh_interval_sec": self._fast_interval,
            "index_refresh_interval_sec": self._index_interval,
            "ws_push_interval_sec": prof.get("ws_broadcast_interval", 1),
            "yahoo_throttled": throttled,
            "refresh_mode": "yahoo_throttled" if throttled else "normal",
            "last_error": self._last_error,
            "message": message,
            "subscribed_symbols": len(self._subscribed_symbols),
            "integrations_active": active,
            **sess,
        }


market_data = MarketDataService(refresh_interval=10, fast_interval=3)
market_data._ensure_seed_cache()
