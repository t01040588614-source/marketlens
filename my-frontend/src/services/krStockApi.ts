import axios from "axios";
import { api, attachAuthSessionResponseInterceptor, setAuthToken } from "@/lib/api";
import { getApiBaseUrl, getServerApiBaseUrl } from "@/lib/apiBase";

function toCamelCase(obj: unknown): unknown {
  if (Array.isArray(obj)) return obj.map(toCamelCase);
  if (obj !== null && typeof obj === "object") {
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

/**
 * DOCX 명세 /api/stocks → 백엔드 /api/v1/stocks.
 * 브라우저도 다른 API와 같은 주소(getApiBaseUrl)를 씀 — 로컬은 /api/v1 프록시,
 * Render는 API 직접 호출 (웹 서버를 한 번 더 거치면 무료 서버에서 10초 가까이 걸림).
 */
const docxApi = axios.create({ headers: { "Content-Type": "application/json" } });

docxApi.interceptors.request.use((config) => {
  config.baseURL = typeof window !== "undefined" ? getApiBaseUrl() : getServerApiBaseUrl();
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("token");
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

docxApi.interceptors.response.use((response) => {
  if (response.data) response.data = toCamelCase(response.data);
  return response;
});
attachAuthSessionResponseInterceptor(docxApi);

export type KrScreenerConditions = {
  query?: string;
  market?: string;
  sector?: string;
  industry?: string;
  marketCapGte?: number;
  marketCapLte?: number;
  perGte?: number;
  perLte?: number;
  pbrGte?: number;
  pbrLte?: number;
  dividendYieldGte?: number;
  sortBy?: string;
  sortOrder?: "ASC" | "DESC";
};

export type KrStockListItem = {
  code: string;
  name: string;
  market?: string;
  sector?: string;
  industry?: string;
  marketCap?: number;
  price?: number;
  change?: number;
  changePercent?: number;
  per?: number;
  pbr?: number;
  dividendYield?: number;
};

export type KrScreener = {
  id: number;
  name: string;
  conditions: KrScreenerConditions;
  createdBy?: string | null;
};

function qs(params: Record<string, string | number | undefined>) {
  const sp = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== "") sp.set(k, String(v));
  });
  const s = sp.toString();
  return s ? `?${s}` : "";
}

/** DOCX /api/v1/stocks (+ alias /api/stocks 프록시) */
export const krStockApi = {
  listStocks: (conditions: KrScreenerConditions & { limit?: number; offset?: number }) =>
    docxApi.get<{ stocks: KrStockListItem[]; total: number }>(
      `/stocks${qs(conditions as Record<string, string | number | undefined>)}`
    ),

  getDetail: (code: string) => docxApi.get(`/stocks/${code}`),

  getQuotes: (code: string, limit = 200) =>
    docxApi.get<
      Array<{
        date: string;
        open: number;
        high: number;
        low: number;
        close: number;
        volume: number;
      }>
    >(`/stocks/${code}/quotes?limit=${limit}`),

  getNews: (code: string, limit = 10) =>
    docxApi.get<Array<{ id: number; title: string; summary?: string; url?: string; source?: string }>>(
      `/stocks/${code}/news?limit=${limit}`
    ),

  getConsensus: (code: string) =>
    docxApi.get<{
      date: string;
      targetPriceAvg?: number;
      targetPriceHigh?: number;
      targetPriceLow?: number;
      buyCount?: number;
      holdCount?: number;
      sellCount?: number;
    } | null>(`/stocks/${code}/consensus`),

  saveScreener: (name: string, conditions: KrScreenerConditions) =>
    docxApi.post<KrScreener>("/stocks/screeners", { name, conditions }),

  listScreeners: (createdBy?: string) =>
    docxApi.get<KrScreener[]>(
      createdBy
        ? `/stocks/screeners?createdBy=${encodeURIComponent(createdBy)}`
        : "/stocks/screeners"
    ),

  deleteScreener: (id: number) => docxApi.delete(`/stocks/screeners/${id}`),

  /** 레거시 /api/v1/kr/* (동일 백엔드) */
  legacy: {
    listStocks: (conditions: KrScreenerConditions & { limit?: number; offset?: number }) =>
      api.get<{ stocks: KrStockListItem[]; total: number }>(
        `/kr/stocks${qs(conditions as Record<string, string | number | undefined>)}`
      ),
  },
};

export { setAuthToken };

const LOCAL_KEY = "kr-local-screeners";

export function loadLocalScreeners(): KrScreener[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(localStorage.getItem(LOCAL_KEY) || "[]") as KrScreener[];
  } catch {
    return [];
  }
}

export function saveLocalScreener(name: string, conditions: KrScreenerConditions): KrScreener[] {
  const list = loadLocalScreeners();
  const next: KrScreener = {
    id: Date.now(),
    name,
    conditions,
    createdBy: "local",
  };
  const updated = [next, ...list].slice(0, 20);
  localStorage.setItem(LOCAL_KEY, JSON.stringify(updated));
  return updated;
}
