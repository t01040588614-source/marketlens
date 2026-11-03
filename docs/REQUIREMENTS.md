# 요구사항 정리 (DOCX/README + 대화 반영)

> 공식 PDF/DOCX가 `docs/`에 추가되면 이 문서를 갱신합니다.

## 1. 실행·환경

- Windows **원클릭** 실행 (`주식대시보드_통합.bat` → 메뉴 1)
- 백엔드 **8000**, 프론트 **3000**
- CORS/프록시: `localhost` · `127.0.0.1` 혼용 시에도 API 연동
- CSS/레이아웃 깨짐 방지 (critical CSS, `.next` 선택적 `-Clean`)

## 2. 브랜딩·UI

- 서비스명 **MarketLens** (Investing.com 클론 아님)
- 와이드 레이아웃, 좁은 사이드 여백, 시장 보드 2열(본문+사이드바)
- 업종 그리드 5열, 섹터 필터
- 반응형: 데스크톱/모바일 헤더, 하단 네비, 다크 모드

## 3. 시장·실시간

- 한국/미국 종목 목록, 상세(quote), 차트
- **WebSocket** 1연결(Provider), `quotes` + `ticks` + `indices`
- **「실시간」 정의 (M2):** KIS **HTS급 체결 틱**은 **미구현**(DOCX 대비 유일 ❌). 제공하는 것은 **캐시 기반 준실시간 WS** — FDR/Yahoo/KIS fast_info 등으로 갱신한 **시세 캐시**를 장중 정규 세션에서 약 **0.35초** 주기로 푸시 (`stock-backend` `market_session` / `websocket_manager`). 휴장·Yahoo 429 시 주기는 완화(최대 ~1초대). **HTS 틱·체결 단위 스트림과 동일하지 않음** — 투자·데모 설명 시 명시.
- 표·지수 스트rip·사이드바 **가격 플래시** (위 캐시·WS 기준)
- 한국 시세: **FDR(KRX)** 우선, Yahoo 일괄 fallback
- Yahoo 429 시 **참고 시세(seed)** + 자동 재시도

## 3-b. 백엔드 스택 (M1)

- DOCX **NestJS monorepo**(`apps/api`)는 **의도적 미구현** → **`stock-backend/` FastAPI**로 **동일 REST API 계약** 충족. [SPEC_STATUS.md](./SPEC_STATUS.md) M1, [DOCX_SPEC_MAPPING.md](./DOCX_SPEC_MAPPING.md)

## 4. 기능 페이지

- 포트폴리오 CRUD + 로그인
- 관심목록(로컬 ★ + 계정)
- 뉴스·캘린더 (API + mock fallback)
- 분석·도구 (mock)
- **종목 검색** (헤더 + 검색 결과 페이지)

## 5. API (stock-backend)

- `GET /stocks/korea`, `/us`, `/search`, `/history`
- `GET /market/indices`, `/sectors`, `/cache-status`
- `POST /market/refresh`
- `WS /ws/stocks`
