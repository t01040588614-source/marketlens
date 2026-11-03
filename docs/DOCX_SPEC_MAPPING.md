# DOCX 명세 ↔ 주식대시 구현 매핑

원본: `docs/spec-from-docx-full.txt` (완전판), `docs/spec-from-docx.txt` (초판)

| DOCX (NestJS/monorepo) | 본 프로젝트 (FastAPI + Next.js) |
|------------------------|----------------------------------|
| `apps/web` Next.js 14 | `my-frontend/` |
| `apps/api` NestJS + TypeORM | `stock-backend/` FastAPI + SQLAlchemy |
| `GET /stocks` 필터·정렬 | **`GET /api/v1/stocks`** (+ `/api/v1/kr/stocks`) |
| `GET /stocks/:code` | **`GET /api/v1/stocks/{code}`** (6자리) |
| `GET /stocks/:code/quotes` | `GET /api/v1/stocks/{code}/quotes` |
| `GET /stocks/:code/news` | `GET /api/v1/stocks/{code}/news` |
| `GET /stocks/:code/consensus` | `GET /api/v1/stocks/{code}/consensus` |
| `POST/GET/DELETE screeners` | **`/api/v1/stocks/screeners`** |
| Next rewrite `/api/stocks` | `next.config.mjs` → `:8000/api/v1/stocks` |
| `/stocks` UI | `/korea` + `/stocks` → redirect |
| `/stocks/[code]` | `/quote/korea/[code]` + redirect |
| ingest-stocks/quotes/fundamentals | `scripts/ingest_kr_analytics.py` + startup seed |
| docker-compose Postgres 16 | `docker-compose.yml` (DB만, 선택) |
| entities 6종 | `app/models/kr_analytics.py` + 기존 User |

| DOCX Accounts | 본 프로젝트 |
|---------------|-------------|
| `GET/POST /accounts` | **`/api/v1/accounts`** (+ `/api/accounts` rewrite) |
| positions / trades / snapshots | 동일 경로, `ownerId` 쿼리 (기본 `user1`) |
| 매매 PATCH/DELETE | 구현 + 포지션 재계산 |
| `/accounts/...` 페이지 | Investing 톤 UI |

## 미적용 / 차이

### M1 — NestJS monorepo → FastAPI (**의도적 대체**)

DOCX의 `kr-stock-dashboard` monorepo(`apps/api` NestJS 10 + TypeORM)는 **별도 구현하지 않습니다.**  
REST 리소스·필터·스크리너·계좌 등 **동일 API 계약**을 `stock-backend/` **FastAPI + SQLAlchemy**로 제공합니다 (`/api/v1/stocks`, `/api/v1/kr/*`, `/api/v1/accounts` 등).  
이는 누락이 아니라 **스택 선택의 의도적 대체**이며, 구현 상태는 [SPEC_STATUS.md](./SPEC_STATUS.md) **M1**을 따릅니다.

### M2 — KIS HTS 틱 (**명세 대비 유일 ❌**)

- **미구현:** KIS(또는 타 증권사) **HTS급 체결 틱** WebSocket — DOCX가 가정하는 틱 단위 실시간 스트림.
- **대신 제공:** **캐시 기반 준실시간 WS** — `GET`/`fast` 갱신으로 쌓인 캐시를 `WS /ws/stocks`로 브로드캐스트. **장중 정규 세션** 기준 푸시 주기 약 **0.35초** (`ws_broadcast_interval`; Yahoo 429 시 완화).
- **투자·QA 주의:** 화면의 「실시간」·가격 플래시는 **HTS 틱과 동일하지 않습니다.** 일봉·재무 ingest는 FDR/Yahoo·시드; 유료 재무 API 전면 대체는 별도 한계.

### 기타

- 실시간 WS·미국 시장·포트폴리오는 기존 **MarketLens(주식대시)** 기능 유지
- 계좌 기능은 **PostgreSQL** 필요 (SQLite만이면 시세·로컬 스크리너만)
