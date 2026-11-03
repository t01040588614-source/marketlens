import axios, { type AxiosInstance } from 'axios';
import type {
  KoreaStock,
  USStock,
  IntlStock,
  PortfolioItem,
  MarketIndexQuote,
  MarketSectorItem,
} from '@/types/stock';

export type MarketRegionSessionPayload = {
  session: 'open' | 'closed' | 'pre' | 'after';
  label: string;
  regularOpen: boolean;
  holiday: boolean;
  holidayName: string | null;
  earlyClose: string | null;
  detail: string;
  tooltip: string;
  localDate: string;
  timezone: string;
};

export type MarketSessionResponse = {
  serverTime: string;
  kr: MarketRegionSessionPayload;
  us: MarketRegionSessionPayload;
};
import type {
  AuthResponse,
  LoginCredentials,
  PhoneSendResult,
  PhoneVerifyResult,
  RegisterCredentials,
  User,
} from '@/types/auth';

import { getApiBaseUrl } from '@/lib/apiBase';

function toCamelCase(obj: unknown): unknown {
  if (Array.isArray(obj)) {
    return obj.map(toCamelCase);
  }
  if (obj !== null && typeof obj === 'object') {
    const record = obj as Record<string, unknown>;
    return Object.fromEntries(
      Object.entries(record).map(([key, value]) => {
        const camelKey = key.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase());
        return [camelKey, toCamelCase(value)];
      })
    );
  }
  return obj;
}

function toSnakeCase(obj: unknown): unknown {
  if (Array.isArray(obj)) {
    return obj.map(toSnakeCase);
  }
  if (obj !== null && typeof obj === 'object' && !(obj instanceof URLSearchParams) && !(obj instanceof FormData)) {
    const record = obj as Record<string, unknown>;
    return Object.fromEntries(
      Object.entries(record).map(([key, value]) => {
        const snakeKey = key.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`);
        return [snakeKey, toSnakeCase(value)];
      })
    );
  }
  return obj;
}

export const api = axios.create({
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 90_000,
});

function formatApiError(error: unknown): string {
  if (!axios.isAxiosError(error)) {
    return error instanceof Error ? error.message : "알 수 없는 오류";
  }
  if (!error.response) {
    return "백엔드에 연결할 수 없습니다. 주식대시보드_통합.bat(메뉴 1)으로 서버(8000·3000)를 시작하세요.";
  }
  const detail = error.response.data as { detail?: unknown };
  if (typeof detail?.detail === "string") return detail.detail;
  if (Array.isArray(detail?.detail)) {
    return detail.detail
      .map((item) => (typeof item === "object" && item && "msg" in item ? String((item as { msg: string }).msg) : ""))
      .filter(Boolean)
      .join(", ");
  }
  return error.message || `요청 실패 (${error.response.status})`;
}

function isAuthEndpoint(url: string | undefined): boolean {
  if (!url) return false;
  return (
    url.includes("/auth/login") ||
    url.includes("/auth/register") ||
    url.includes("/auth/password/") ||
    url.includes("/auth/refresh") ||
    url.includes("/auth/logout")
  );
}

const REFRESH_STORAGE_KEY = "refresh_token";

export const setRefreshToken = (token: string | null) => {
  if (typeof window === "undefined") return;
  if (token) localStorage.setItem(REFRESH_STORAGE_KEY, token);
  else localStorage.removeItem(REFRESH_STORAGE_KEY);
};

export const getRefreshToken = (): string | null => {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(REFRESH_STORAGE_KEY);
};

export const setAuthToken = (token: string | null) => {
  if (token) {
    api.defaults.headers.common['Authorization'] = `Bearer ${token}`;
    if (typeof window !== 'undefined') {
      localStorage.setItem('token', token);
    }
  } else {
    delete api.defaults.headers.common['Authorization'];
    if (typeof window !== 'undefined') {
      localStorage.removeItem('token');
    }
  }
};

export const clearAuthSession = () => {
  setAuthToken(null);
  setRefreshToken(null);
};

let refreshInFlight: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const refresh = getRefreshToken();
  if (!refresh) return null;
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const base = getApiBaseUrl();
        const res = await axios.post(
          `${base}/auth/refresh`,
          { refresh_token: refresh },
          { headers: { "Content-Type": "application/json" }, timeout: 15_000 }
        );
        const body = toCamelCase(res.data) as {
          accessToken?: string;
          refreshToken?: string;
        };
        const access = body.accessToken;
        if (!access) return null;
        setAuthToken(access);
        if (body.refreshToken) setRefreshToken(body.refreshToken);
        return access;
      } catch {
        return null;
      } finally {
        refreshInFlight = null;
      }
    })();
  }
  return refreshInFlight;
}

let sessionExpiredDispatched = false;

export function handleUnauthorizedResponse(error: unknown): void {
  if (!axios.isAxiosError(error) || error.response?.status !== 401 || typeof window === "undefined") {
    return;
  }
  const reqUrl = error.config?.url ?? "";
  const hadToken = Boolean(localStorage.getItem("token"));
  if (!hadToken || reqUrl.includes("/auth/me") || isAuthEndpoint(reqUrl)) return;
  if (sessionExpiredDispatched) return;
  sessionExpiredDispatched = true;
  clearAuthSession();
  window.dispatchEvent(new Event("auth:session-expired"));
  window.setTimeout(() => {
    sessionExpiredDispatched = false;
  }, 3000);
}

export function attachAuthSessionResponseInterceptor(client: AxiosInstance): void {
  client.interceptors.response.use(
    (response) => response,
    (error) => {
      handleUnauthorizedResponse(error);
      return Promise.reject(error);
    }
  );
}

api.interceptors.response.use(
  (response) => {
    if (response.data) {
      response.data = toCamelCase(response.data);
    }
    return response;
  },
  async (error) => {
    error.message = formatApiError(error);
    const original = error.config as { _retried?: boolean; url?: string; headers?: Record<string, string> };
    if (
      axios.isAxiosError(error) &&
      error.response?.status === 401 &&
      original &&
      !original._retried &&
      !isAuthEndpoint(original.url)
    ) {
      original._retried = true;
      const access = await refreshAccessToken();
      if (access) {
        original.headers = original.headers ?? {};
        original.headers.Authorization = `Bearer ${access}`;
        return api.request(original);
      }
    }
    handleUnauthorizedResponse(error);
    return Promise.reject(error);
  }
);

api.interceptors.request.use((config) => {
  config.baseURL = getApiBaseUrl();
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('token');
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  if (config.data) {
    config.data = toSnakeCase(config.data);
  }
  return config;
});

// 인증 관련 API
export type PhoneSmsStatus = {
  configured: boolean;
  provider: string;
  demoFallback: boolean;
  label: string;
};

export const authApi = {
  getPhoneSmsStatus: () => api.get<PhoneSmsStatus>('/auth/phone/status').then((r) => r.data),
  sendPhoneCode: (phone: string) =>
    api.post<PhoneSendResult>('/auth/phone/send', { phone }).then((r) => r.data),
  verifyPhoneCode: (phone: string, code: string) =>
    api.post<PhoneVerifyResult>('/auth/phone/verify', { phone, code }).then((r) => r.data),
  register: (data: RegisterCredentials) => api.post<User>('/auth/register', data),
  login: (data: LoginCredentials) => {
    const formData = new URLSearchParams();
    formData.append('username', data.email);
    formData.append('password', data.password);
    return api.post<AuthResponse>('/auth/login', formData, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    });
  },
  getMe: () => api.get<User>('/auth/me'),
  requestPasswordReset: (email: string) =>
    api
      .post<{ message: string; devResetToken?: string | null }>('/auth/password/forgot', { email })
      .then((r) => r.data),
  resetPassword: (token: string, password: string) =>
    api.post<{ message: string }>('/auth/password/reset', { token, password }).then((r) => r.data),
  refresh: (refreshToken: string) =>
    api
      .post<{ accessToken: string; refreshToken: string; tokenType: string }>('/auth/refresh', {
        refreshToken,
      })
      .then((r) => r.data),
  logout: (refreshToken: string) =>
    api.post<{ ok: boolean }>('/auth/logout', { refreshToken }).then((r) => r.data),
  syncMyKisSnapshot: () =>
    api
      .post<{
        ok: boolean;
        cashBalance?: number | null;
        holdings?: { symbol: string; name: string; quantity: number; avgPrice: number }[];
        holdingsCount?: number;
        syncedAt?: string;
      }>("/auth/me/broker/kis/sync")
      .then((r) => r.data),
  getMyKisSnapshot: () =>
    api
      .get<{
        ok: boolean;
        cashBalance?: number | null;
        holdings?: { symbol: string; name: string; quantity: number; avgPrice: number }[];
        syncedAt?: string;
      }>("/auth/me/broker/kis/snapshot")
      .then((r) => r.data),
  saveMyKisBroker: (body: {
    appKey: string;
    appSecret: string;
    accountNo?: string;
    accountProductCode?: string;
    useMock?: boolean;
  }) =>
    api
      .put<{ configured: boolean; accountMasked?: string | null; useMock?: boolean; verifiedAt?: string | null }>(
        '/auth/me/broker/kis',
        body
      )
      .then((r) => r.data),
};

// 주식 관련 API
export const stockApi = {
  // 한국주식
  getKoreaStocks: () => api.get<KoreaStock[]>('/stocks/korea'),
  getKoreaStockDetail: (symbol: string) => api.get<KoreaStock>(`/stocks/korea/${symbol}`),

  // 미국주식
  getUSStocks: () => api.get<USStock[]>('/stocks/us'),
  getUSStockDetail: (symbol: string) => api.get<USStock>(`/stocks/us/${symbol}`),

  getAsiaStocks: () => api.get<IntlStock[]>('/stocks/asia'),
  getEuropeStocks: () => api.get<IntlStock[]>('/stocks/europe'),

  // 검색
  searchStocks: (query: string) => api.get<(KoreaStock | USStock)[]>(`/stocks/search?q=${query}`),

  // 포트폴리오
  getPortfolio: () => api.get<PortfolioItem[]>('/portfolio'),
  addToPortfolio: (data: Partial<PortfolioItem>) => api.post<PortfolioItem>('/portfolio', data),
  updatePortfolio: (id: number, data: Partial<PortfolioItem>) => api.put<PortfolioItem>(`/portfolio/${id}`, data),
  deleteFromPortfolio: (id: number) => api.delete(`/portfolio/${id}`),

  getMarketIndices: (ids?: string, category?: string) => {
    const params = new URLSearchParams();
    if (ids) params.set("ids", ids);
    if (category) params.set("category", category);
    const qs = params.toString();
    return api.get<MarketIndexQuote[]>(qs ? `/market/indices?${qs}` : "/market/indices", {
      timeout: 12_000,
    });
  },
  getMarketSectors: () => api.get<MarketSectorItem[]>('/market/sectors'),
  getMarketSymbols: () =>
    api.get<{
      symbols: string[];
      count: number;
      korea: number;
      us: number;
      asia: number;
      europe: number;
    }>('/market/symbols'),
  getHealth: () => api.get<{ status: string; message?: string }>('/health'),
  getMarketSession: () => api.get<MarketSessionResponse>('/market/session'),
  getMarketCacheStatus: () =>
    api.get<{
      koreaCount: number;
      usCount: number;
      koreaSource: string;
      usSource: string;
      lastUpdated: string | null;
      cacheAgeSeconds: number | null;
      krMarketOpen?: boolean;
      usMarketOpen?: boolean;
      krSession?: string;
      usSession?: string;
      krHoliday?: boolean;
      usHoliday?: boolean;
      krHolidayName?: string | null;
      usHolidayName?: string | null;
      wsPushIntervalSec?: number;
      /** 백엔드 전체 시세 갱신 주기(초) — 무료 배포는 60 */
      refreshIntervalSec?: number;
      yahooThrottled?: boolean;
      refreshMode?: string;
      wsBroadcastAlive?: boolean;
      wsConnections?: number;
      wsLoopErrors?: number;
      lastError: string | null;
      message: string | null;
      realtimeMode?: string;
      realtimeDisclaimer?: string | null;
      kisConfigured?: boolean;
      kisLastFetchMs?: number | null;
      kisLastFetchAt?: string | null;
      redis?: { enabled?: boolean };
      kisRealtime?: {
        connected?: boolean;
        tickCount?: number;
        liveCount?: number;
        desiredCount?: number;
        reconnectAttempts?: number;
        lastError?: string | null;
      };
    }>('/market/cache-status'),
  refreshMarketCache: () =>
    api.post<{
      koreaCount: number;
      usCount: number;
      koreaSource: string;
      usSource: string;
      lastUpdated: string | null;
      cacheAgeSeconds: number | null;
      lastError: string | null;
      message: string | null;
    }>('/market/refresh'),
};
