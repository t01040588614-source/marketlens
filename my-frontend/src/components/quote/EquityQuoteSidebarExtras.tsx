"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import LoadingState from "@/components/common/LoadingState";
import WatchlistStar from "@/components/market/WatchlistStar";
import { stockApi } from "@/lib/api";
import { addPriceAlert, inferDirection } from "@/lib/priceAlerts";
import {
  buildSymbolTrendPrompt,
  openMarketAiChat,
} from "@/lib/marketAiChatEvents";
import { formatPercent, formatPrice, priceClass } from "@/lib/format";
import { krxBidAsk } from "@/lib/krxTickSize";
import { krStockApi } from "@/services/krStockApi";
import {
  getStockChartEvents,
  getStockPeriodReturns,
  type ChartMarket,
} from "@/services/chartApi";

const PERIOD_LABELS: { key: string; label: string }[] = [
  { key: "1d", label: "1일" },
  { key: "1w", label: "1주" },
  { key: "1m", label: "1달" },
  { key: "3m", label: "3달" },
  { key: "6m", label: "6달" },
  { key: "1y", label: "1년" },
  { key: "ytd", label: "YTD" },
];

type Props = {
  symbol: string;
  market: "korea" | "us";
  quoteName?: string;
  currentPrice: number;
  changePercent: number;
  open?: number;
  high?: number;
  low?: number;
  previousClose?: number;
  volume?: number;
};

function WidgetShell({
  title,
  moreHref,
  moreLabel,
  children,
}: {
  title: string;
  moreHref?: string;
  moreLabel?: string;
  children: ReactNode;
}) {
  return (
    <section className="inv-widget inv-equity-sidebar-extra">
      <header className="inv-widget-head">
        <h3 className="inv-widget-title">{title}</h3>
        {moreHref ? (
          <Link href={moreHref} className="inv-widget-more">
            {moreLabel ?? "더보기"}
          </Link>
        ) : null}
      </header>
      <div className="inv-equity-sidebar-extra-body">{children}</div>
    </section>
  );
}

export default function EquityQuoteSidebarExtras({
  symbol,
  market,
  quoteName,
  currentPrice,
  changePercent,
  open,
  high,
  low,
  previousClose,
  volume,
}: Props) {
  const name = quoteName ?? symbol;
  const decimals = market === "korea" ? 0 : 2;

  const { data: periodReturns } = useQuery({
    queryKey: ["periodReturns", symbol, market],
    queryFn: () => getStockPeriodReturns({ symbol, market: market as ChartMarket }),
    staleTime: 120_000,
  });

  const { data: chartEvents } = useQuery({
    queryKey: ["chartEventsSidebar", symbol, market],
    queryFn: () =>
      getStockChartEvents({ symbol, market: market as ChartMarket, period: "1y" }),
    staleTime: 300_000,
  });

  const { data: krDetail, isLoading: detailLoading } = useQuery({
    queryKey: ["kr-detail-sidebar", symbol],
    queryFn: () => krStockApi.getDetail(symbol).then((r) => r.data),
    enabled: market === "korea",
    staleTime: 60_000,
  });

  const { data: consensus } = useQuery({
    queryKey: ["kr-consensus-panel", symbol],
    queryFn: () => krStockApi.getConsensus(symbol).then((r) => r.data),
    enabled: market === "korea",
    staleTime: 120_000,
  });

  const { data: news, isLoading: newsLoading } = useQuery({
    queryKey: ["kr-news-sidebar", symbol],
    queryFn: () => krStockApi.getNews(symbol, 6).then((r) => r.data),
    enabled: market === "korea",
    staleTime: 60_000,
  });

  const { data: koreaList } = useQuery({
    queryKey: ["koreaStocks"],
    queryFn: () => stockApi.getKoreaStocks().then((r) => r.data),
    enabled: market === "korea",
    staleTime: 30_000,
  });

  const { data: usList } = useQuery({
    queryKey: ["usStocks"],
    queryFn: () => stockApi.getUSStocks().then((r) => r.data),
    enabled: market === "us",
    staleTime: 30_000,
  });

  const fund = krDetail?.fundamental as Record<string, number | string | null> | undefined;

  const selfRow =
    market === "korea"
      ? koreaList?.find((s) => s.symbol === symbol)
      : usList?.find((s) => s.symbol === symbol);

  const sector = selfRow?.sector?.trim();

  const { bid, ask } =
    market === "korea" ? krxBidAsk(currentPrice) : { bid: currentPrice, ask: currentPrice };

  const todayIso = new Date().toISOString().slice(0, 10);
  const upcomingEvents =
    chartEvents?.events
      ?.filter((e) => e.future || e.date >= todayIso)
      .sort((a, b) => a.date.localeCompare(b.date))
      .slice(0, 4) ?? [];

  const dayRangePct =
    high != null && low != null && high > low
      ? Math.min(100, Math.max(0, ((currentPrice - low) / (high - low)) * 100))
      : null;

  const onPriceAlert = () => {
    const raw = window.prompt(`${name} 알림 가격`, String(Math.round(currentPrice)));
    if (!raw) return;
    const target = Number(raw.replace(/,/g, ""));
    if (!Number.isFinite(target) || target <= 0) return;
    addPriceAlert({
      symbol,
      market,
      name,
      targetPrice: target,
      direction: inferDirection(currentPrice, target),
    });
    window.alert("가격 알림이 저장되었습니다 (로컬).");
  };

  const goHash = (hash: string) => {
    window.location.hash = hash;
    document.querySelector(hash)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <>
      <WidgetShell title="빠른 도구">
        <div className="inv-equity-sidebar-tools">
          <button
            type="button"
            className="inv-equity-sidebar-tool inv-equity-sidebar-tool--ai"
            onClick={() =>
              openMarketAiChat({
                symbol,
                market,
                message: buildSymbolTrendPrompt(symbol),
                autoSend: true,
              })
            }
          >
            ✦ AI {symbol} 분석
          </button>
          <button type="button" className="inv-equity-sidebar-tool" onClick={onPriceAlert}>
            🔔 가격 알림
          </button>
          <button type="button" className="inv-equity-sidebar-tool" onClick={() => goHash("#chart")}>
            📈 차트로
          </button>
          <button type="button" className="inv-equity-sidebar-tool" onClick={() => goHash("#financials")}>
            📊 재무 탭
          </button>
        </div>
        <div className="inv-equity-sidebar-tool-row">
          <WatchlistStar symbol={symbol} market={market} name={name} />
          <span className="inv-equity-sidebar-spread tabular">
            매수/매도 {formatPrice(bid, decimals)} / {formatPrice(ask, decimals)}
          </span>
        </div>
      </WidgetShell>

      {dayRangePct != null && high != null && low != null && (
        <WidgetShell title="당일 가격대">
          <div className="inv-equity-day-range">
            <div className="inv-equity-day-range-labels">
              <span className="tabular text-muted-sm">{formatPrice(low, decimals)}</span>
              <span className={`tabular ${priceClass(changePercent)}`}>
                {formatPercent(changePercent)}
              </span>
              <span className="tabular text-muted-sm">{formatPrice(high, decimals)}</span>
            </div>
            <div className="inv-equity-day-range-track" aria-hidden>
              <span className="inv-equity-day-range-fill" style={{ width: `${dayRangePct}%` }} />
              <span className="inv-equity-day-range-marker" style={{ left: `${dayRangePct}%` }} />
            </div>
            <p className="inv-equity-day-range-hint text-muted-sm">
              현재가 {formatPrice(currentPrice, decimals)} · 당일 구간{" "}
              {Math.round(dayRangePct)}% 지점
            </p>
          </div>
        </WidgetShell>
      )}

      {(open != null || high != null || low != null) && (
        <WidgetShell title="당일 시세">
          <dl className="inv-equity-sidebar-dl">
            <div>
              <dt>당일 등락</dt>
              <dd className={`tabular ${priceClass(changePercent)}`}>
                {formatPercent(changePercent)}
              </dd>
            </div>
            {previousClose != null && (
              <div>
                <dt>전일 종가</dt>
                <dd className="tabular">{formatPrice(previousClose, decimals)}</dd>
              </div>
            )}
            {open != null && (
              <div>
                <dt>시가</dt>
                <dd className="tabular">{formatPrice(open, decimals)}</dd>
              </div>
            )}
            {high != null && low != null && (
              <div>
                <dt>고가 / 저가</dt>
                <dd className="tabular">
                  {formatPrice(high, decimals)} / {formatPrice(low, decimals)}
                </dd>
              </div>
            )}
            {volume != null && volume > 0 && (
              <div>
                <dt>거래량</dt>
                <dd className="tabular">{volume.toLocaleString("ko-KR")}</dd>
              </div>
            )}
          </dl>
        </WidgetShell>
      )}

      {upcomingEvents.length > 0 && (
        <WidgetShell title="배당·실적 일정">
          <ul className="inv-equity-sidebar-events">
            {upcomingEvents.map((ev) => (
              <li key={`${ev.type}-${ev.date}`}>
                <span className="inv-equity-sidebar-event-badge">{ev.label}</span>
                <span className="inv-equity-sidebar-event-body">
                  <strong>{ev.title ?? ev.type}</strong>
                  <span className="text-muted-sm tabular">{ev.date}</span>
                </span>
              </li>
            ))}
          </ul>
        </WidgetShell>
      )}

      {periodReturns && Object.keys(periodReturns.returns).length > 0 && (
        <WidgetShell title="기간 수익률">
          <ul className="inv-equity-sidebar-returns">
            {PERIOD_LABELS.map(({ key, label }) => {
              const v = periodReturns.returns[key];
              if (v == null || !Number.isFinite(v)) return null;
              return (
                <li key={key}>
                  <span>{label}</span>
                  <span className={`tabular ${priceClass(v)}`}>{formatPercent(v)}</span>
                </li>
              );
            })}
          </ul>
        </WidgetShell>
      )}

      {market === "korea" && (
        <WidgetShell title="재무·업종" moreHref="#financials" moreLabel="재무 탭">
          {detailLoading && <LoadingState rows={3} />}
          {!detailLoading && fund && (
            <dl className="inv-equity-sidebar-dl">
              <div>
                <dt>PER</dt>
                <dd>{fund.per ?? "—"}</dd>
              </div>
              <div>
                <dt>PBR</dt>
                <dd>{fund.pbr ?? "—"}</dd>
              </div>
              <div>
                <dt>ROE</dt>
                <dd>{fund.roe != null ? `${fund.roe}%` : "—"}</dd>
              </div>
              <div>
                <dt>배당수익</dt>
                <dd>{fund.dividendYield != null ? `${fund.dividendYield}%` : "—"}</dd>
              </div>
              <div>
                <dt>업종</dt>
                <dd>{fund.industry ?? sector ?? "—"}</dd>
              </div>
            </dl>
          )}
        </WidgetShell>
      )}

      {consensus && (
        <WidgetShell title="컨센서스">
          <dl className="inv-equity-sidebar-dl">
            <div>
              <dt>목표가(평균)</dt>
              <dd className="tabular">{formatPrice(consensus.targetPriceAvg ?? 0, 0)}</dd>
            </div>
            <div>
              <dt>매수/보유/매도</dt>
              <dd className="tabular">
                {consensus.buyCount ?? 0}/{consensus.holdCount ?? 0}/{consensus.sellCount ?? 0}
              </dd>
            </div>
          </dl>
        </WidgetShell>
      )}

      {market === "korea" && (
        <WidgetShell title={`${symbol} 뉴스`} moreHref="#news" moreLabel="뉴스 탭">
          {newsLoading && <LoadingState rows={2} />}
          {!newsLoading && (
            <ul className="inv-widget-list inv-equity-sidebar-news">
              {(news ?? []).map((n) => (
                <li key={n.id}>
                  {n.url ? (
                    <a href={n.url} className="inv-widget-row" target="_blank" rel="noreferrer">
                      <span className="inv-widget-name inv-equity-sidebar-news-title">{n.title}</span>
                      <span className="text-muted-sm">{n.source}</span>
                    </a>
                  ) : (
                    <span className="inv-widget-row">
                      <span className="inv-widget-name">{n.title}</span>
                    </span>
                  )}
                </li>
              ))}
              {!news?.length && <p className="inv-widget-empty">등록된 종목 뉴스가 없습니다.</p>}
            </ul>
          )}
        </WidgetShell>
      )}

      <WidgetShell title="분석·도구">
        <ul className="inv-equity-quote-link-list">
          <li>
            <Link href={`/analysis?symbol=${symbol}&market=${market}`}>기술·밸류 분석</Link>
          </li>
          <li>
            <Link href={`/tools`}>MarketLens 도구</Link>
          </li>
          <li>
            <Link href="/portfolio">포트폴리오</Link>
          </li>
        </ul>
      </WidgetShell>
    </>
  );
}
