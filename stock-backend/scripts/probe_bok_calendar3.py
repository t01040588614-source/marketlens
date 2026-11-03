import re

import httpx

ym = "2026-10"
url = f"https://www.bok.or.kr/portal/stats/statsPublictSchdul/listCldr.do?date={ym}&menuNo=200775"
r = httpx.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
text = r.text

# find list in script var
for key in ("publictDe", "trgetStats", "publictTm", "listData", "resultList"):
    print(key, text.count(key))

# try view.json POST
post_urls = [
    "https://www.bok.or.kr/portal/stats/statsPublictSchdul/view.json",
    "https://www.bok.or.kr/portal/stats/statsPublictSchdul/list.json",
]
for u in post_urls:
    for payload in [
        {"date": ym, "menuNo": "200775"},
        {"searchDate": ym},
        {"publictYm": ym.replace("-", "")},
    ]:
        rr = httpx.post(
            u,
            data=payload,
            headers={
                "User-Agent": "Mozilla/5.0",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": url,
            },
            timeout=15,
        )
        if rr.status_code == 200 and "html" not in rr.text[:80].lower():
            print("POST OK", u, payload, rr.text[:300])

# extract dates near trgetStats in raw html
chunks = re.findall(r"publictDe[^,]{0,80}", text)
print("chunks", len(chunks), chunks[:3])
