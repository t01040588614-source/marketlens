declare global {
  interface Window {
    __ML_API_BASE?: string;
    __ML_WS_URL?: string;
  }
}

/**
 * Render 배포 주소 규칙 (무료 요금제 기준)
 * - Blueprint `fromService.host` 는 짧은 이름만 준다 (예: marketlens-api-h3h9).
 * - 무료 서비스는 Render 내부망(private network) 요청을 "받을 수 없다" → 웹→API도 공개 HTTPS 로 연결.
 *   https://render.com/docs/private-network
 * - 공개 주소가 짧은 이름과 다르면 NEXT_PUBLIC_API_URL 에 API 공개 URL 전체(https://…)를 넣으면 그 값이 우선.
 */

/** 스킴·경로·포트를 뗀 호스트만 */
function parseServiceHost(raw: string): string {
  return raw
    .trim()
    .replace(/^[a-z]+:\/\//i, "")
    .replace(/^\/\//, "")
    .split("/")[0]
    .split(":")[0];
}

/** Render 짧은 서비스 이름인가 (localhost·docker 내부 이름 api 같은 스킴 붙은 값은 제외) */
function isBareRenderHost(raw: string): boolean {
  const v = raw.trim();
  if (/^[a-z]+:\/\//i.test(v)) return false;
  const host = parseServiceHost(v);
  return /^[a-z0-9-]+$/i.test(host) && host !== "localhost";
}

/** 브라우저가 열 수 있는 공개 origin. 공개 주소로 바꿀 수 없으면 "" */
function renderPublicOrigin(raw: string): string {
  const v = raw.trim().replace(/\/$/, "");
  if (!v) return "";
  const host = parseServiceHost(v);
  if (!host) return "";
  if (/^https?:\/\//i.test(v)) {
    // http://api:8000 같은 내부 이름은 브라우저에서 못 엶
    return host.includes(".") ? v.replace(/\/api\/v1\/?$/, "") : "";
  }
  if (isBareRenderHost(v)) return `https://${host}.onrender.com`;
  return host.includes(".") ? `https://${host}` : "";
}

function apiBaseFromOrigin(origin: string): string {
  const base = origin.replace(/\/$/, "");
  return base.endsWith("/api/v1") ? base : `${base}/api/v1`;
}

function isOnRender(origin: string): boolean {
  try {
    return new URL(origin).hostname.endsWith(".onrender.com");
  } catch {
    return false;
  }
}

/** API 공개 URL을 찾을 env 순서 — 전체 URL(NEXT_PUBLIC_API_URL)이 가장 정확하므로 먼저 */
function renderEnvCandidates(): string[] {
  return [
    process.env.NEXT_PUBLIC_API_URL,
    process.env.NEXT_PUBLIC_WS_URL,
    process.env.STOCK_API_PROXY,
  ]
    .map((v) => v?.trim() ?? "")
    .filter(Boolean);
}

function renderPublicOriginFromEnv(): string | null {
  for (const raw of renderEnvCandidates()) {
    const origin = renderPublicOrigin(raw.replace(/^wss?:/i, "https:"));
    if (origin && isOnRender(origin)) return origin;
  }
  return null;
}

/** 서버 layout → 브라우저 주입용. Render 배포일 때만 값이 있고, 로컬·Docker 에선 null */
export function buildRenderPublicApiBaseFromEnv(): string | null {
  const origin = renderPublicOriginFromEnv();
  return origin ? apiBaseFromOrigin(origin) : null;
}

export function buildRenderPublicWsFromEnv(): string | null {
  const origin = renderPublicOriginFromEnv();
  return origin ? `wss://${new URL(origin).host}/api/v1/ws/stocks` : null;
}

/** 브라우저: 지금 페이지가 Render 위일 때 API 공개 origin */
function resolveRenderApiOrigin(pageHost: string): string | null {
  if (!pageHost.endsWith(".onrender.com")) return null;
  return renderPublicOriginFromEnv();
}

/** SSR·서버 컴포넌트용 백엔드 직접 URL */
export function getServerApiBaseUrl(): string {
  const proxy = process.env.STOCK_API_PROXY?.trim();
  if (proxy) {
    // docker-compose(http://api:8000)·로컬은 그대로, Render 짧은 이름만 공개 HTTPS 로
    if (/^https?:\/\//i.test(proxy)) return apiBaseFromOrigin(proxy);
    // Render 짧은 이름이면 NEXT_PUBLIC_API_URL(공개 URL 직접 지정)을 먼저 따름
    const origin = (isBareRenderHost(proxy) && renderPublicOriginFromEnv()) || renderPublicOrigin(proxy);
    if (origin) return apiBaseFromOrigin(origin);
  }
  const env = process.env.NEXT_PUBLIC_API_URL?.trim();
  if (env) {
    if (/^https?:\/\//i.test(env)) return apiBaseFromOrigin(env);
    const origin = renderPublicOrigin(env);
    if (origin) return apiBaseFromOrigin(origin);
  }
  return "http://127.0.0.1:8000/api/v1";
}

/**
 * 브라우저: 로컬은 Next rewrites(`/api/v1`). Render는 API 공개 URL 직접(CORS).
 */
export function getApiBaseUrl(): string {
  if (typeof window !== "undefined") {
    if (window.__ML_API_BASE) {
      return window.__ML_API_BASE;
    }
    const pageHost = window.location.hostname;
    const localDev =
      (pageHost === "localhost" || pageHost === "127.0.0.1") &&
      (window.location.port === "3000" || window.location.port === "");

    if (!localDev) {
      const renderOrigin = resolveRenderApiOrigin(pageHost);
      if (renderOrigin) {
        return `${renderOrigin}/api/v1`;
      }
    }
    return "/api/v1";
  }
  return getServerApiBaseUrl();
}

function resolvePublicWsUrl(env: string, pageProto: "http:" | "https:"): string | null {
  try {
    const wsProto = pageProto === "https:" ? "wss:" : "ws:";
    let wsUrl = env;
    if (!/^wss?:\/\//i.test(wsUrl)) {
      wsUrl = `${wsProto}//${wsUrl.replace(/^\/\//, "")}`;
    }
    const parsed = new URL(wsUrl);
    if (
      !parsed.hostname.includes(".") &&
      parsed.hostname !== "localhost" &&
      typeof window !== "undefined" &&
      window.location.hostname.endsWith(".onrender.com")
    ) {
      parsed.hostname = `${parsed.hostname}.onrender.com`;
      parsed.protocol = "wss:";
      parsed.port = "";
    }
    if (!parsed.pathname.includes("/ws/")) {
      parsed.pathname = "/api/v1/ws/stocks";
    }
    if (parsed.hostname === "localhost") {
      parsed.hostname = "127.0.0.1";
    }
    return parsed.toString();
  } catch {
    return null;
  }
}

/** WebSocket — Render: wss://{service}.onrender.com / Caddy: same-origin */
export function getWsStocksUrl(): string {
  const env = process.env.NEXT_PUBLIC_WS_URL?.trim();
  if (typeof window !== "undefined") {
    if (window.__ML_WS_URL) {
      return window.__ML_WS_URL;
    }
    const pageHost = window.location.hostname;
    const localDev =
      (pageHost === "localhost" || pageHost === "127.0.0.1") &&
      window.location.port === "3000";
    const pageProto = window.location.protocol as "http:" | "https:";

    if (!localDev) {
      const renderOrigin = resolveRenderApiOrigin(pageHost);
      if (renderOrigin) {
        return `wss://${new URL(renderOrigin).host}/api/v1/ws/stocks`;
      }
    }

    if (env && !localDev) {
      const crossHost = resolvePublicWsUrl(env, pageProto);
      if (crossHost) {
        return crossHost;
      }
    }

    if (!localDev) {
      const proto = pageProto === "https:" ? "wss:" : "ws:";
      return `${proto}//${window.location.host}/api/v1/ws/stocks`;
    }

    const port = process.env.NEXT_PUBLIC_WS_PORT || "8000";
    const proto = pageProto === "https:" ? "wss:" : "ws:";
    if (env) {
      const local = resolvePublicWsUrl(env, pageProto);
      if (local) {
        return local;
      }
    }
    return `${proto}//127.0.0.1:${port}/api/v1/ws/stocks`;
  }
  if (env) {
    if (/^wss?:\/\//i.test(env)) return env;
    if (isBareRenderHost(env)) {
      return `wss://${parseServiceHost(env)}.onrender.com/api/v1/ws/stocks`;
    }
    return `ws://${env.replace(/^\/\//, "")}/api/v1/ws/stocks`;
  }
  return "ws://127.0.0.1:8000/api/v1/ws/stocks";
}
