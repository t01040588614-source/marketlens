"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { getStockHistory, type OhlcPoint } from "@/services/chartApi";
import { formatCompactVolume, formatPercent, formatPrice, priceClass } from "@/lib/format";

/**
 * 종목 개요 — 차트·주요 통계 아래 영역.
 * 우측 사이드(당일 시세·기간 수익률·뉴스·재무 등)에 없는 내용만 1년 일봉으로 계산해서 보여 줌.
 */

type Props = {
  symbol: string;
  market: "korea" | "us";
};

type DayRow = OhlcPoint & { changePercent: number | null };

const RECENT_DAYS = 10;
const VOLUME_BUCKETS = 10;

/** API는 time="11/03"(표시용), timestamp="2026-11-03T00:00:00"(실제 날짜)를 줌 */
function isoDate(p: OhlcPoint): string | null {
  const s = p.timestamp ?? p.time;
  return /^\d{4}-\d{2}-\d{2}/.test(s) ? s.slice(0, 10) : null;
}

function dayLabel(p: OhlcPoint): string {
  const d = isoDate(p);
  return d ? d.replace(/-/g, ".") : p.time;
}

function withDailyChange(points: OhlcPoint[]): DayRow[] {
  return points.map((p, i) => {
    const prev = i > 0 ? points[i - 1].close : null;
    return {
      ...p,
      changePercent: prev && prev > 0 ? ((p.close - prev) / prev) * 100 : null,
    };
  });
}

function monthlyReturns(points: OhlcPoint[]) {
  const months = new Map<string, { first: OhlcPoint; last: OhlcPoint; prevClose: number | null }>();
  let prevClose: number | null = null;
  let prevKey = "";
  for (const p of points) {
    const d = isoDate(p);
    if (!d) return [];
    const key = d.slice(0, 7);
    if (key !== prevKey) {
      months.set(key, { first: p, last: p, prevClose });
      prevKey = key;
    } else {
      const m = months.get(key)!;
      m.last = p;
    }
    prevClose = p.close;
  }
  return Array.from(months.entries())
    .slice(-12)
    .map(([key, m]) => {
      const base = m.prevClose ?? m.first.open;
      return {
        key,
        label: `${Number(key.slice(5, 7))}월`,
        year: key.slice(0, 4),
        pct: base > 0 ? ((m.last.close - base) / base) * 100 : 0,
      };
    });
}

function yearStats(rows: DayRow[]) {
  const changes = rows.filter((r) => r.changePercent != null) as (DayRow & { changePercent: number })[];
  if (!changes.length) return null;
  const up = changes.filter((r) => r.changePercent > 0).length;
  const down = changes.filter((r) => r.changePercent < 0).length;
  const best = changes.reduce((a, b) => (b.changePercent > a.changePercent ? b : a));
  const worst = changes.reduce((a, b) => (b.changePercent < a.changePercent ? b : a));
  const avgRange =
    rows.reduce((s, r) => s + (r.close > 0 ? ((r.high - r.low) / r.close) * 100 : 0), 0) / rows.length;
  const mean = changes.reduce((s, r) => s + r.changePercent, 0) / changes.length;
  const variance = changes.reduce((s, r) => s + (r.changePercent - mean) ** 2, 0) / changes.length;
  const yearlyVol = Math.sqrt(variance) * Math.sqrt(252);
  const top = rows.reduce((a, b) => (b.high > a.high ? b : a));
  const bottom = rows.reduce((a, b) => (b.low < a.low ? b : a));
  return { up, down, total: changes.length, best, worst, avgRange, yearlyVol, top, bottom };
}

function volumeProfile(rows: OhlcPoint[]) {
  const lo = Math.min(...rows.map((r) => r.low));
  const hi = Math.max(...rows.map((r) => r.high));
  if (!Number.isFinite(lo) || !Number.isFinite(hi) || hi <= lo) return [];
  const step = (hi - lo) / VOLUME_BUCKETS;
  const buckets = Array.from({ length: VOLUME_BUCKETS }, (_, i) => ({
    from: lo + step * i,
    to: lo + step * (i + 1),
    volume: 0,
  }));
  for (const r of rows) {
    const mid = (r.high + r.low + r.close) / 3;
    const idx = Math.min(VOLUME_BUCKETS - 1, Math.max(0, Math.floor((mid - lo) / step)));
    buckets[idx].volume += r.volume || 0;
  }
  return buckets.reverse();
}

export default function EquityOverviewExtras({ symbol, market }: Props) {
  const decimals = market === "korea" ? 0 : 2;

  const { data: hist, isLoading } = useQuery({
    queryKey: ["quote52w", market, symbol],
    queryFn: () => getStockHistory({ symbol, market, period: "1y" }),
    staleTime: 120_000,
  });

  const rows = useMemo(() => withDailyChange(hist?.points ?? []), [hist]);
  const recent = useMemo(() => rows.slice(-RECENT_DAYS).reverse(), [rows]);
  const months = useMemo(() => monthlyReturns(hist?.points ?? []), [hist]);
  const stats = useMemo(() => yearStats(rows), [rows]);
  const profile = useMemo(() => (rows.length ? volumeProfile(rows) : []), [rows]);
  const lastClose = rows.length ? rows[rows.length - 1].close : null;
  const maxBucket = Math.max(1, ...profile.map((b) => b.volume));
  const maxMonthAbs = Math.max(1, ...months.map((m) => Math.abs(m.pct)));

  if (isLoading) {
    return <p className="inv-overview-extra-empty">1년 시세를 불러오는 중…</p>;
  }
  if (rows.length < 2) return null;

  return (
    <div className="inv-overview-extras">
      <section className="inv-overview-extra">
        <header className="inv-overview-extra-head">
          <h2 className="inv-overview-extra-title">최근 {recent.length}거래일 시세</h2>
          <a href="#historical" className="inv-overview-extra-more">
            과거 데이터 전체
          </a>
        </header>
        <div className="inv-overview-extra-table-wrap">
          <table className="inv-overview-extra-table">
            <thead>
              <tr>
                <th>일자</th>
                <th>종가</th>
                <th>등락률</th>
                <th>시가</th>
                <th>고가</th>
                <th>저가</th>
                <th>거래량</th>
              </tr>
            </thead>
            <tbody>
              {recent.map((r) => (
                <tr key={r.timestamp ?? r.time}>
                  <td className="tabular">{dayLabel(r)}</td>
                  <td className="tabular">{formatPrice(r.close, decimals)}</td>
                  <td className={`tabular ${priceClass(r.changePercent ?? 0)}`}>
                    {r.changePercent == null ? "—" : formatPercent(r.changePercent)}
                  </td>
                  <td className="tabular">{formatPrice(r.open, decimals)}</td>
                  <td className="tabular">{formatPrice(r.high, decimals)}</td>
                  <td className="tabular">{formatPrice(r.low, decimals)}</td>
                  <td className="tabular">{formatCompactVolume(r.volume)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className="inv-overview-extra-pair">
        {months.length > 0 && (
          <section className="inv-overview-extra">
            <header className="inv-overview-extra-head">
              <h2 className="inv-overview-extra-title">월별 수익률</h2>
              <span className="inv-overview-extra-sub">최근 {months.length}개월</span>
            </header>
            <ul className="inv-overview-months">
              {months.map((m) => (
                <li key={m.key} className="inv-overview-month">
                  <span className="inv-overview-month-label">
                    {m.label}
                    <small>{m.year}</small>
                  </span>
                  <span className="inv-overview-month-bar">
                    <span
                      className={`inv-overview-month-fill ${m.pct >= 0 ? "is-up" : "is-down"}`}
                      style={{ width: `${(Math.abs(m.pct) / maxMonthAbs) * 100}%` }}
                    />
                  </span>
                  <span className={`tabular inv-overview-month-pct ${priceClass(m.pct)}`}>
                    {formatPercent(m.pct)}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {profile.length > 0 && (
          <section className="inv-overview-extra">
            <header className="inv-overview-extra-head">
              <h2 className="inv-overview-extra-title">가격대별 거래량</h2>
              <span className="inv-overview-extra-sub">1년 · 많이 거래된 가격대</span>
            </header>
            <ul className="inv-overview-profile">
              {profile.map((b) => {
                const isNow = lastClose != null && lastClose >= b.from && lastClose <= b.to;
                return (
                  <li key={b.from} className={`inv-overview-profile-row${isNow ? " is-now" : ""}`}>
                    <span className="tabular inv-overview-profile-range">
                      {formatPrice(b.from, decimals)} ~ {formatPrice(b.to, decimals)}
                    </span>
                    <span className="inv-overview-profile-bar">
                      <span style={{ width: `${(b.volume / maxBucket) * 100}%` }} />
                    </span>
                    <span className="tabular inv-overview-profile-vol">
                      {isNow ? "현재가 · " : ""}
                      {formatCompactVolume(b.volume)}
                    </span>
                  </li>
                );
              })}
            </ul>
          </section>
        )}
      </div>

      {stats && (
        <section className="inv-overview-extra">
          <header className="inv-overview-extra-head">
            <h2 className="inv-overview-extra-title">1년 가격 기록</h2>
            <span className="inv-overview-extra-sub">최근 {stats.total}거래일 기준</span>
          </header>
          <div className="inv-overview-records">
            <div className="inv-overview-record">
              <span className="inv-overview-record-label">오른 날 · 내린 날</span>
              <strong className="tabular">
                <span className="price-up">{stats.up}일</span> · <span className="price-down">{stats.down}일</span>
              </strong>
              <span className="inv-overview-updown">
                <span className="is-up" style={{ flex: stats.up }} />
                <span className="is-down" style={{ flex: stats.down }} />
              </span>
            </div>
            <div className="inv-overview-record">
              <span className="inv-overview-record-label">하루 최대 상승</span>
              <strong className={`tabular ${priceClass(stats.best.changePercent)}`}>
                {formatPercent(stats.best.changePercent)}
              </strong>
              <span className="inv-overview-record-date tabular">{dayLabel(stats.best)}</span>
            </div>
            <div className="inv-overview-record">
              <span className="inv-overview-record-label">하루 최대 하락</span>
              <strong className={`tabular ${priceClass(stats.worst.changePercent)}`}>
                {formatPercent(stats.worst.changePercent)}
              </strong>
              <span className="inv-overview-record-date tabular">{dayLabel(stats.worst)}</span>
            </div>
            <div className="inv-overview-record">
              <span className="inv-overview-record-label">최고가 찍은 날</span>
              <strong className="tabular">{formatPrice(stats.top.high, decimals)}</strong>
              <span className="inv-overview-record-date tabular">{dayLabel(stats.top)}</span>
            </div>
            <div className="inv-overview-record">
              <span className="inv-overview-record-label">최저가 찍은 날</span>
              <strong className="tabular">{formatPrice(stats.bottom.low, decimals)}</strong>
              <span className="inv-overview-record-date tabular">{dayLabel(stats.bottom)}</span>
            </div>
            <div className="inv-overview-record">
              <span className="inv-overview-record-label">하루 평균 움직임</span>
              <strong className="tabular">{stats.avgRange.toFixed(2)}%</strong>
              <span className="inv-overview-record-date">고가와 저가 차이</span>
            </div>
            <div className="inv-overview-record">
              <span className="inv-overview-record-label">1년 변동성</span>
              <strong className="tabular">{stats.yearlyVol.toFixed(1)}%</strong>
              <span className="inv-overview-record-date">클수록 가격이 크게 출렁임</span>
            </div>
          </div>
        </section>
      )}

      <p className="inv-overview-extra-note">
        위 내용은 1년 일봉({hist?.source === "synthetic" || hist?.source === "mock" ? "예시 데이터" : "실제 시세"})으로 계산했습니다.
      </p>
    </div>
  );
}
