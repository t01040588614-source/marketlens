# DOCX 완전판 — 실행·경로 매핑

원문: [spec-from-docx-full.txt](./spec-from-docx-full.txt)

## Docker (DOCX §2)

```powershell
copy .env.example .env
docker compose up --build
```

| 서비스 | URL |
|--------|-----|
| Web | http://localhost:3000 |
| API | http://localhost:8000/docs |
| Postgres | localhost:5432 (krstock/krstockpass) |

로컬만 DB: `docker compose up -d db` 후 `주식대시보드_통합.bat` 메뉴 1

## ETL (DOCX §5)

PostgreSQL 필수:

```powershell
cd stock-backend
.\venv\Scripts\python.exe scripts\ingest_docx_all.py
```

| DOCX 스크립트 | 본 프로젝트 |
|---------------|-------------|
| ingest-stocks.ts | `app/data_ingest/ingest_stocks.py` |
| ingest-quotes.ts | `app/data_ingest/ingest_quotes.py` |
| ingest-fundamentals.ts | `app/data_ingest/ingest_fundamentals.py` |
| (일괄) | `scripts/ingest_docx_all.py` |

DB 테이블: `kr_stocks`, `kr_stock_quotes`, `kr_fundamental_snapshots`, `kr_stock_news`, `kr_consensus`, `user_screeners`, `user_accounts`, …

## 프론트 경로 (DOCX §4·§5)

| DOCX | URL |
|------|-----|
| /stocks | http://localhost:3000/stocks |
| /stocks/[code] | http://localhost:3000/stocks/005930 |
| /stocks/[code]/chart | http://localhost:3000/stocks/005930/chart |
| /accounts?ownerId=user1 | http://localhost:3000/accounts?ownerId=user1 |
| /accounts/new | http://localhost:3000/accounts/new |
| /accounts/1/trades/new | … |

## API 프록시

- `/api/stocks/*` → FastAPI `/api/v1/stocks/*`
- `/api/accounts/*` → FastAPI `/api/v1/accounts/*`

## NestJS → FastAPI (**M1: 의도적 대체**)

DOCX §3의 **NestJS 10 + TypeORM** `apps/api` monorepo는 **의도적으로 구현하지 않습니다.**  
동일 REST **API 계약**(stocks·quotes·news·consensus·screeners·accounts, Next rewrite 경로 포함)을 **`stock-backend/` FastAPI + SQLAlchemy**로 충족합니다. NestJS 코드·패키지는 저장소에 없으며, 이는 **누락이 아닌 대체**입니다.

- 매핑·경로: [DOCX_SPEC_MAPPING.md](./DOCX_SPEC_MAPPING.md)
- 체크리스트: [SPEC_STATUS.md](./SPEC_STATUS.md) **M1**

## 실시간 시세 (**M2: HTS 틱 ❌**)

DOCX·HTS 수준 **체결 틱**은 **미구현(유일 ❌)** 입니다. MarketLens 「실시간」은 **캐시 기반 준실시간 WebSocket** — 장중 약 **0.35초** 캐시 푸시. 상세: [SPEC_STATUS.md](./SPEC_STATUS.md) **M2**, [REQUIREMENTS.md](./REQUIREMENTS.md) §3.
