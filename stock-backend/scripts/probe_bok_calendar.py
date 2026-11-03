import re

import httpx

ym = "2026-10"
url = f"https://www.bok.or.kr/portal/stats/statsPublictSchdul/listCldr.do?date={ym}&menuNo=200775"
r = httpx.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
print("status", r.status_code, len(r.text))
for u in re.findall(r"statsPublictSchdul/[a-zA-Z0-9_.?=&]+", r.text):
    if "list" in u.lower() or "json" in u.lower():
        print("path", u[:100])

candidates = [
    f"https://www.bok.or.kr/portal/stats/statsPublictSchdul/listCldrJson.do?date={ym}",
    f"https://www.bok.or.kr/portal/stats/statsPublictSchdul/selectStatsPublictSchdulList.do?searchDate={ym}",
    f"https://www.bok.or.kr/portal/stats/statsPublictSchdul/selectStatsPublictSchdulList.do?date={ym}",
]
idx = r.text.find("view.json")
print("view.json ctx", r.text[idx : idx + 500] if idx >= 0 else "none")

for u in candidates:
    rr = httpx.get(
        u,
        headers={"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest"},
        timeout=15,
    )
    print(u.split("/")[-1][:60], rr.status_code, rr.text[:250].replace("\n", " "))
