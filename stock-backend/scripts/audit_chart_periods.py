"""기간별 history 감사 — 터미널에서 직접 실행해 백엔드 반영 여부 확인.

Usage (stock-backend):
  set PYTHONPATH=.
  venv\\Scripts\\python.exe scripts\\audit_chart_periods.py
  venv\\Scripts\\python.exe scripts\\audit_chart_periods.py --http http://127.0.0.1:8000
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.chart_service import (  # noqa: E402
    CHART_HUB_PERIODS,
    PERIOD_BAR_CAP,
    PERIOD_LOOKBACK_DAYS,
    chart_service,
)

CASES = (
    ("005930", "korea"),
    ("AAPL", "us"),
    ("kospi", "index"),
)

INTRADAY_PERIODS = {"1d"}

EXPECTED_BARS: dict[str, tuple[int, int]] = {
    "1d": (3, PERIOD_BAR_CAP["1d_intraday"]),
    "1w": (7, 7),
    "1m": (31, 31),
    "3m": (45, PERIOD_BAR_CAP["3m"]),
    "5mo": (75, PERIOD_BAR_CAP["5mo"]),
    "6m": (90, PERIOD_BAR_CAP["6m"]),
    "1y": (150, PERIOD_BAR_CAP["1y"]),
    "5y": (400, PERIOD_BAR_CAP["5y"]),
    "max": (400, PERIOD_BAR_CAP["max"]),
}


def _parse_ts(p: dict) -> datetime | None:
    ts = p.get("timestamp")
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _span_days(points: list[dict]) -> int | None:
    dts = [_parse_ts(p) for p in points]
    dts = [d for d in dts if d]
    if len(dts) < 2:
        return None
    return (max(dts) - min(dts)).days


def _check_row(period: str, data: dict) -> list[str]:
    issues: list[str] = []
    points = data.get("points") or []
    n = len(points)
    lo, hi = EXPECTED_BARS.get(period, (2, 9999))
    if n < lo:
        issues.append(f"bars={n} < min {lo}")
    if period in INTRADAY_PERIODS:
        if n > PERIOD_BAR_CAP["1d_intraday"] + 5:
            issues.append(f"intraday bars={n} > cap {PERIOD_BAR_CAP['1d_intraday']}")
    elif period in PERIOD_BAR_CAP and n > PERIOD_BAR_CAP[period] + 2:
        issues.append(f"bars={n} > cap {PERIOD_BAR_CAP[period]}")
    if period in ("1w", "1m"):
        if n != hi:
            issues.append(f"expected exactly {hi} calendar bars, got {n}")
        labels = [str(p.get("time") or "") for p in points]
        if labels and not all(l.endswith("일") for l in labels):
            issues.append("1w/1m labels not N일")
    src = str(data.get("source") or "")
    if src == "synthetic":
        issues.append("source=synthetic (실데이터 아님)")
    iv = str(data.get("interval") or "")
    if period not in ("1d",) and iv and iv not in ("1d",):
        issues.append(f"long period should be 1d, got interval={iv}")
    lookback = PERIOD_LOOKBACK_DAYS.get(period)
    span = _span_days(points)
    if span is not None and lookback is not None and period not in ("1w", "1m"):
        if span < int(lookback * 0.55):
            issues.append(f"span_days={span} << lookback={lookback}")
    return issues


async def _audit_inprocess() -> list[dict]:
    rows: list[dict] = []
    for symbol, market in CASES:
        for period in CHART_HUB_PERIODS:
            data = await chart_service.get_history(symbol, market, period)
            pts = data.get("points") or []
            row = {
                "symbol": symbol,
                "market": market,
                "period": period,
                "bars": len(pts),
                "cap": PERIOD_BAR_CAP.get(period),
                "lookback_days": PERIOD_LOOKBACK_DAYS.get(period),
                "span_days": _span_days(pts),
                "source": data.get("source"),
                "interval": data.get("interval"),
                "first_time": pts[0].get("time") if pts else None,
                "last_time": pts[-1].get("time") if pts else None,
                "issues": _check_row(period, data),
            }
            rows.append(row)
    return rows


async def _audit_http(base: str) -> list[dict]:
    import httpx

    rows: list[dict] = []
    async with httpx.AsyncClient(base_url=base.rstrip("/"), timeout=120.0) as client:
        for symbol, market in CASES:
            for period in CHART_HUB_PERIODS:
                r = await client.get(
                    "/api/v1/stocks/history",
                    params={"symbol": symbol, "market": market, "period": period},
                )
                data = r.json() if r.status_code == 200 else {"points": [], "source": f"http_{r.status_code}"}
                pts = data.get("points") or []
                rows.append(
                    {
                        "symbol": symbol,
                        "market": market,
                        "period": period,
                        "bars": len(pts),
                        "cap": PERIOD_BAR_CAP.get(period),
                        "source": data.get("source"),
                        "interval": data.get("interval"),
                        "issues": _check_row(period, data) if r.status_code == 200 else [f"HTTP {r.status_code}"],
                        "via": "http",
                    }
                )
    return rows


def _print_report(rows: list[dict], title: str) -> int:
    print(f"\n=== {title} ===")
    fail = 0
    for row in rows:
        flag = "OK" if not row["issues"] else "FAIL"
        if row["issues"]:
            fail += 1
        print(
            f"{flag} {row['market']:6} {row['symbol']:8} {row['period']:4} "
            f"bars={row['bars']:4} cap={row.get('cap')} src={row.get('source')} iv={row.get('interval')} "
            f"span={row.get('span_days')}d"
        )
        for iss in row["issues"]:
            print(f"     ! {iss}")
    print(f"\n{title}: {len(rows) - fail}/{len(rows)} passed, {fail} failed")
    return fail


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--http", help="Also compare running API (e.g. http://127.0.0.1:8000)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    inproc = await _audit_inprocess()
    fail = _print_report(inproc, "In-process ChartService (현재 코드)")

    if args.http:
        try:
            http_rows = await _audit_http(args.http)
            fail_http = _print_report(http_rows, f"HTTP {args.http} (실행 중 프로세스)")
            for a, b in zip(inproc, http_rows, strict=False):
                if a["bars"] != b["bars"] or a.get("source") != b.get("source"):
                    print(
                        f"MISMATCH {a['market']} {a['symbol']} {a['period']}: "
                        f"inproc bars={a['bars']} src={a.get('source')} vs "
                        f"http bars={b['bars']} src={b.get('source')}"
                    )
                    fail += 1
            fail += fail_http
        except Exception as exc:
            print(f"HTTP audit skipped: {exc}")

    if args.json:
        print(json.dumps(inproc, ensure_ascii=False, indent=2))

    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
