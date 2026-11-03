from xml.etree import ElementTree as ET

import httpx

r = httpx.get(
    "https://news.google.com/rss/search?q=%EC%A6%9D%EC%8B%9C&hl=ko&gl=KR&ceid=KR:ko",
    headers={"User-Agent": "Mozilla/5.0"},
    follow_redirects=True,
)
it = ET.fromstring(r.content).find(".//item")
for c in it:
    tag = c.tag.split("}")[-1]
    print(tag, c.attrib, (c.text or "")[:80])
