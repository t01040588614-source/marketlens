"use client";

import { Suspense, useEffect, useMemo } from "react";
import { recordRecentEquityView } from "@/lib/recentEquityViews";
import { pickWsQuote, pickWsTick } from "@/lib/wsSymbolKey";
import { useQuery } from "@tanstack/react-query";
import { stockApi } from "@/lib/api";
import { getStockHistory } from "@/services/chartApi";
import MarketPageShell from "@/components/market/MarketPageShell";
import MarketsSplitLayout from "@/components/market/MarketsSplitLayout";
import ChartPanel from "@/components/chart/ChartPanel";
import LoadingState from "@/components/common/LoadingState";
import { useLiveSymbols } from "@/hooks/useLiveSymbols";
import { mergeLiveStockQuote, mergeSessionOhlcWithLivePrice } from "@/lib/liveQuoteMerge";
import { quoteDetailRefetchMs } from "@/lib/marketRefreshSettings";
import { priceDecimalsForEquity } from "@/lib/format";
import InvestingEquityInstrumentHeader from "@/components/quote/InvestingEquityInstrumentHeader";
import InvestingEquityPageTabs from "@/components/quote/InvestingEquityPageTabs";
import EquityQuoteSidebarColumn from "@/components/quote/EquityQuoteSidebarColumn";
import {
  EquityFinancialsPanel,
  EquityNewsPanel,
  EquitySubTabPanel,
} from "@/components/quote/InvestingEquityTabPanels";
import { useEquityPageHash } from "@/hooks/useEquityPageHash";
import EquityOverviewExtras from "@/components/quote/EquityOverviewExtras";
import EquityOverviewMarket from "@/components/quote/EquityOverviewMarket";
type QuotePageContentProps = {
  market: "korea" | "us";
  symbol: string;
};

function EquityQuotePageContent({
  symbol,
  market,
}: {
  symbol: string;
  market: "korea" | "us";
}) {
  const { quotes, ticks, flash, isConnected } = useLiveSymbols([symbol]);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["quote", market, symbol],
    queryFn: async () => {
      const res =
        market === "korea"
          ? await stockApi.getKoreaStockDetail(symbol)
          : await stockApi.getUSStockDetail(symbol);
      return res.data;
    },
    refetchInterval: quoteDetailRefetchMs(isConnected),
    staleTime: 0,
  });

  const { data: hist1y } = useQuery({
    queryKey: ["quote52w", market, symbol],
    queryFn: () => getStockHistory({ symbol, market, period: "1y" }),
    staleTime: 120_000,
  });

  const marketLabel = market === "korea" ? "한국 주식" : "미국 주식";
  const boardHref = market === "korea" ? "/korea" : "/us";

  const live = pickWsQuote(symbol, quotes);
  const tick = pickWsTick(symbol, ticks);
  const quoteView = useMemo(() => {
    if (!data) return null;
    const merged = mergeLiveStockQuote(
      {
        price: data.price,
        change: data.change,
        changePercent: data.changePercent,
        previousClose: data.previousClose,
        volume: data.volume,
      },
      live,
      tick
    );
    const session = mergeSessionOhlcWithLivePrice(
      {
        price: merged.price,
        open: data.open,
        high: data.high,
        low: data.low,
      },
      merged.price,
    );
    return { ...data, ...merged, ...session };
  }, [data, live, tick]);

  const decimals = priceDecimalsForEquity(market, quoteView?.price ?? data?.price);
  const priceFlash = flash[symbol];
  const week52Low = hist1y?.summary?.low;
  const week52High = hist1y?.summary?.high;
  const { tabs, navigate } = useEquityPageHash();

  const showChart =
    (tabs.primary === "general" && tabs.sub === "overview") ||
    tabs.primary === "chart" ||
    tabs.primary === "technical";

  const showSubPanel =
    tabs.primary === "general" && tabs.sub !== "overview";

  const panelProps = {
    symbol,
    market,
    quoteName: quoteView?.name,
  };

  useEffect(() => {
    if (!quoteView?.name) return;
    recordRecentEquityView({
      symbol,
      market,
      name: quoteView.name,
    });
  }, [symbol, market, quoteView?.name]);

  return (
    <MarketPageShell
      compactHead
      fullWidth
      breadcrumbs={[
        { label: "홈", href: "/" },
        { label: "시장", href: "/markets" },
        { label: marketLabel, href: boardHref },
        { label: data?.name ?? symbol },
      ]}
      title=""
      description=""
    >
      {isLoading && <LoadingState rows={4} />}
      {isError && (
        <p className="inv-page-desc">종목을 불러오지 못했습니다. 심볼을 확인해주세요.</p>
      )}
      {quoteView && (
        <div className="inv-equity-page inv-equity-page--toss" id="overview">
          <MarketsSplitLayout
            showToolRail={false}
            sidebarStackClassName="inv-sidebar-stack--equity-quote"
            main={
              <>
                <InvestingEquityInstrumentHeader
                  tossLayout
                  boardBackHref={boardHref}
                  boardBackLabel={market === "korea" ? "한국 종목" : "미국 종목"}
                  name={quoteView.name}
                  symbol={symbol}
                  market={market}
                  price={quoteView.price}
                  change={quoteView.change}
                  changePercent={quoteView.changePercent}
                  open={quoteView.open ?? quoteView.price}
                  high={quoteView.high ?? quoteView.price}
                  low={quoteView.low ?? quoteView.price}
                  previousClose={
                    quoteView.previousClose ?? quoteView.price - quoteView.change
                  }
                  volume={quoteView.volume ?? 0}
                  priceDecimals={decimals}
                  priceFlash={priceFlash}
                  exchangeLabel={
                    market === "korea"
                      ? "market" in quoteView
                        ? String(quoteView.market)
                        : "KOSPI"
                      : "exchange" in quoteView
                        ? String(quoteView.exchange)
                        : "NASDAQ"
                  }
                  isLive={isConnected}
                  week52Low={week52Low}
                  week52High={week52High}
                  showTradeButtons
                />

                <InvestingEquityPageTabs
                  primary={tabs.primary}
                  sub={tabs.sub}
                  onNavigate={navigate}
                />

                <div className="inv-equity-page-main" id="chart">
                  {tabs.primary === "news" && <EquityNewsPanel {...panelProps} />}
                  {tabs.primary === "financials" && (
                    <EquityFinancialsPanel {...panelProps} />
                  )}
                  {showSubPanel && <EquitySubTabPanel sub={tabs.sub} {...panelProps} />}
                  {showChart && (
                    <Suspense fallback={<LoadingState rows={3} />}>
                      <ChartPanel
                        investingEmbed
                        investingEquityPage
                        initialSymbol={symbol}
                        initialMarket={market}
                        parentQuote={quoteView}
                      />
                    </Suspense>
                  )}
                  {tabs.primary === "general" && tabs.sub === "overview" && (
                    <>
                      <EquityOverviewExtras symbol={symbol} market={market} />
                      <EquityOverviewMarket symbol={symbol} market={market} />
                    </>
                  )}
                </div>
              </>
            }
            sidebar={
              <EquityQuoteSidebarColumn
                symbol={symbol}
                market={market}
                changePercent={quoteView.changePercent}
                currentPrice={quoteView.price}
                quoteName={quoteView.name}
                liveVolume={quoteView.volume}
                open={quoteView.open ?? quoteView.price}
                high={quoteView.high ?? quoteView.price}
                low={quoteView.low ?? quoteView.price}
                previousClose={
                  quoteView.previousClose ?? quoteView.price - quoteView.change
                }
              />
            }
          />
        </div>
      )}
    </MarketPageShell>
  );
}

export default function QuotePageContent({ market, symbol }: QuotePageContentProps) {
  return <EquityQuotePageContent symbol={symbol} market={market} />;
}
