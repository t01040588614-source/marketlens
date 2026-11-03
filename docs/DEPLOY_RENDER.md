# Render 무료 완전 배포 (24/7 클라우드 URL)

로컬 PC·Cloudflare 터널 없이 **팀이 항상 접속할 URL**을 쓰려면 Render Blueprint를 적용합니다.

## 1. Blueprint 적용 (최초 1회)

1. [Render Dashboard](https://dashboard.render.com) 로그인
2. **New → Blueprint**
3. GitHub 연결 후 저장소 **`t01040588614-source/scp-698`** 선택
4. **Apply** → `marketlens-db`, `marketlens-api`, `marketlens-web` 생성 대기 (빌드 15~25분)

## 2. 팀 공유 주소

| 서비스 | 용도 |
|--------|------|
| **marketlens-web** | 브라우저 접속 — `https://marketlens-web.onrender.com` (이름은 대시보드에 표시된 URL) |
| marketlens-api | API·WebSocket (프론트가 자동 연결) |

**팀에게는 `marketlens-web` URL만 보내면 됩니다.**

## 3. 무료 플랜 한계

- 15분 미접속 시 **슬립** → 첫 로딩 30~60초
- Postgres free DB **90일** 후 만료 가능 → [Render Docs](https://render.com/docs/free) 참고
- Redis 없음 → rate limit 등은 메모리 폴백

## 4. API 키

배포 후 `https://…/tools/integrations` 에서 KIS·Finnhub 등 입력 (선택).

## 5. API가 «오프라인»일 때 (프론트만 살아 있음)

도구 페이지 **시스템 · 연결 상태**에서 API **오프라인** / WebSocket **끊김**이면:

1. 브라우저에서 API URL 직접 열기 (대시보드 → `marketlens-api` → URL).  
   **«Service Suspended by its owner»** 가 보이면 **코드 문제가 아니라 API 서비스가 중지된 상태**입니다.
2. Render → **marketlens-api** → 우측 **Resume** (또는 Suspend 해제) → **Manual Deploy** → Deploy latest commit.
3. `https://<api-host>.onrender.com/api/v1/health` 가 JSON으로 **healthy** 인지 확인.
4. **marketlens-web** 도 **Manual Deploy** (프록시·브라우저 WS 주소 갱신).

> **API 주소가 안 맞을 때:** Blueprint는 API의 짧은 이름(예: `marketlens-api-h3h9`)만 넘겨 주고, 코드가 이것을 `https://marketlens-api-h3h9.onrender.com` 으로 바꿔 씁니다.
> 대시보드에 보이는 API 공개 URL이 이와 다르면 **marketlens-web → Environment** 에서 `NEXT_PUBLIC_API_URL` 을 API 공개 URL 전체(`https://….onrender.com`)로 바꾼 뒤 **Manual Deploy** 하세요. 이 값이 가장 먼저 쓰입니다.
> 무료 서비스는 Render 내부망 요청을 받을 수 없어서(`render.com/docs/private-network`), 웹 → API 연결도 공개 HTTPS 주소를 씁니다.

무료 Web은 15분 미사용 시 **슬립**만 됩니다. **Suspended** 는 슬립과 다르고, Resume 전까지는 프론트가 아무리 맞아도 API는 503입니다.

## 6. 재배포

GitHub `main`/`master`에 push하면 Render가 **자동 재빌드** (Auto Deploy 켜진 경우).

## 7. 로컬 Docker와의 차이

| | 로컬 + Caddy 80 / Cloudflare | Render |
|--|------------------------------|--------|
| PC 켜 둘 필요 | 예 | 아니오 |
| 고정 HTTPS URL | 터널/도메인 필요 | web 서비스 URL |
| 완전 상용 | 아님 | 무료 한도 내 **상시 호스팅** |
