# 구현 상태 (DOCX 명세 반영)

원본: [spec-from-docx-full.txt](./spec-from-docx-full.txt) (Downloads DOCX 완전판), [spec-from-docx.txt](./spec-from-docx.txt)  
매핑: [DOCX_SPEC_MAPPING.md](./DOCX_SPEC_MAPPING.md)

## DOCX 대비 의도적 차이 (투자·검수용)

| ID | 요약 |
|----|------|
| **M1** | DOCX의 **NestJS + TypeORM monorepo**(`apps/api`)는 **구현하지 않습니다.** 동일한 REST **API 계약**(경로·리소스·DOCX `/api/v1/stocks` 호환)을 **FastAPI + SQLAlchemy**(`stock-backend/`)로 **의도적으로 대체**했습니다. 프론트는 DOCX의 `apps/web`에 해당하는 `my-frontend/`만 유지합니다. |
| **M2** | **KIS HTS급 체결 틱 — PoC 추가**( `H0STCNT0` WS, 키·한국 정규장·구독 종목). 키 없거나 휴장이면 **캐시 기반 준실시간 WS**(~0.35초)만 동작. PoC는 구독 40종·단일 연결·운영 SLA 미포함 — HTS와 동일 수준으로 보지 마세요. |

| ID | DOCX 항목 | 상태 | 구현 |
|----|-----------|------|------|
| S1 | GET /stocks 필터·정렬 | ✅ | `GET /api/v1/kr/stocks` |
| S2 | 종목 상세+재무 | ✅ | `GET /api/v1/kr/stocks/{code}` |
| S3 | 일봉 quotes | ✅ | `GET /api/v1/kr/stocks/{code}/quotes` |
| S4 | 뉴스 | ✅ | `GET /api/v1/kr/stocks/{code}/news` |
| S5 | 컨센서스 | ✅ | `GET /api/v1/kr/stocks/{code}/consensus` |
| S6 | 스크리너 CRUD | ✅ | `/api/v1/kr/screeners` (+ 로컬 저장) |
| S7 | /stocks UI | ✅ | `/korea` 스크리너 + `/stocks` redirect |
| S8 | 상세 UI 차트·재무·뉴스 | ✅ | `/quote/korea/…` + `KrQuoteExtras` |
| S9 | ingest ETL | ✅ | `scripts/ingest_kr_analytics.py` + startup seed |
| S10 | PostgreSQL 16 krstock | ✅ | `docker-compose.yml` + `.env.example` |
| S11 | DOCX `/api/v1/stocks` 경로 | ✅ | `stocks_docx_compat.py` |
| E1 | 원클릭 bat | ✅ | `주식대시보드_통합.bat` |
| R1 | WS 실시간 | ✅ | 기존 주식대시 |
| M1 | NestJS monorepo | ➡️ **의도적 대체** | NestJS/TypeORM **미구현** → **`stock-backend/` FastAPI** 동일 REST·DOCX 호환 경로 |
| M2 | KIS HTS 틱 | ⏳ **PoC** (HTS SLA ❌) | `H0STCNT0` WS + 캐시 WS 병행; 키·구독·휴장 시 캐시 ~0.35s만 |
| A1 | 계좌 CRUD | ✅ | `GET/POST/PATCH/DELETE /api/v1/accounts` |
| A2 | 보유·매매·현금·포지션 재계산 | ✅ | `recalculate_all` + BUY 잔고 검증 |
| A3 | 매매 수정/삭제 | ✅ | `PATCH/DELETE .../trades/:id` |
| A4 | 일별 스냅샷·자산 차트 | ✅ | `scripts/daily_snapshot_job.py` + Lightweight |
| A5 | 포트폴리오·계좌 UI | ✅ | `/portfolio#docx-accounts` + `/accounts/*` |
| A6 | Next `/api/accounts` 프록시 | ✅ | `next.config.mjs` |
| D1 | docker-compose db+api+web | ✅ | `docker-compose.yml`, Dockerfiles |
| D2 | Stock + StockQuote DB | ✅ | `kr_stock_catalog.py` + ingest |
| D3 | ingest 3종 + 일괄 | ✅ | `ingest_docx_all.py --max-codes 0`, `daily-docx.ps1` |
| D4 | `/stocks` 보드·상세·chart | ✅ | Lightweight Charts |
| D5 | 뉴스 sentiment·컨센 고/저 | ✅ | `KrQuoteExtras` |
| D6 | 스크리너 sector/PBR/배당 | ✅ | `KoreaScreenerPanel` |
| D7 | `.env.example` (루트) | ✅ | Docker env |
| I1 | API 키 연동 허브 | ✅ | `/tools/integrations`, `PUT /integrations/keys` |
| I2 | KIS·Finnhub·Alpha 시세 | ✅ | 키 시 `market_data` 소스 전환 |
| I3 | Google/Kakao OAuth | ✅ | 키 시 `/auth/oauth/*` |
| I4 | NewsAPI·FCM | ✅ | FCM **HTTP v1**(서비스 계정) + Legacy 키 폴백, `POST .../fcm/test` |
| P1 | SMTP 비밀번호 재설정 | ✅ | `SMTP_*` + DB 토큰, DEBUG 시 `dev_reset_token` |
| P2 | Refresh JWT | ✅ | `POST /auth/refresh`, `POST /auth/logout` |
| P3 | Redis (선택) | ✅ | `REDIS_URL`, Docker `redis` 서비스, 로그인 rate limit |
| P4 | 관심·알림 서버 동기화 | ✅ | 로그인 시 **서버 관심 우선**(`watchlistFacade`), `/me/*`, FCM 워커 |
| P5 | 도구 API | ✅ | `GET /api/v1/tools` |
| P6 | Firebase Web FCM | ✅ | `GET /config/firebase-public` + SW + `/watchlist` 자동 등록 |
| P7 | KIS WS 견고화 | ✅ | `H0STCNT0`+`H0STASP0`, 구독 diff·재연결, DB 관심 우선(`kis_subscription_planner`) |
| P8 | KIS 잔고 동기화 | ✅ | `GET/POST /auth/me/broker/kis/snapshot|sync`, 15분 워커, `/portfolio` UI |
| P9 | Playwright E2E | ✅ | `my-frontend/e2e/smoke.spec.ts`, `npm run test:e2e` |

**범례:** ✅ 완료 · ⏳ 선택 · ❌ 미구현 · ➡️ DOCX 스택과 다르나 **의도적 대체**(기능·API 계약으로 충족)
