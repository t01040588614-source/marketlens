"use client";

import ResearchSidebar from "@/components/layout/ResearchSidebar";
import InvestingEquitySidebar from "@/components/quote/InvestingEquitySidebar";

/** 종목 개요 맨 아래 — 시장 전체 랭킹·뉴스·일정 (예전엔 우측 사이드 「더보기」 안에 있던 것) */
export default function EquityOverviewMarket({
  symbol,
  market,
}: {
  symbol: string;
  market: "korea" | "us";
}) {
  return (
    <section className="inv-overview-market" aria-label="시장 한눈에">
      <header className="inv-overview-market-head">
        <h2 className="inv-overview-extra-title">시장 한눈에</h2>
        <span className="inv-overview-extra-sub">
          {market === "korea" ? "한국" : "미국"} 시장 랭킹 · 주요 뉴스 · 경제 일정
        </span>
      </header>
      <div className="inv-overview-market-grid">
        <InvestingEquitySidebar symbol={symbol} market={market} />
        <ResearchSidebar
          market={market}
          showIndicesWidget={false}
          showWatchlist={false}
          compactSidebar
          showNews
          showCalendar
        />
      </div>
    </section>
  );
}
