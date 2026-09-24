from __future__ import annotations

import re
from .service import RequestIntent

ILLUST_URL = re.compile(r"(?:pixiv\.net/(?:artworks|en/artworks)/|illust(?:ration)?\s*(?:id|ID)?\s*[:：]?\s*)(\d+)", re.I)
ARTIST_RE = re.compile(r"(?:artist|画师|作者)\s*(?:id|ID)?\s*[:：]?\s*(\d+)", re.I)
COUNT_RE = re.compile(r"(?:^|\s)(\d{1,2})\s*(?:张|幅|个|枚)?(?:\s|$)")

def parse_pixiv_request(text: str) -> RequestIntent:
    raw = text.strip()
    count_match = COUNT_RE.search(raw)
    count = int(count_match.group(1)) if count_match else 5
    illust_match = ILLUST_URL.search(raw)
    illust_id = int(illust_match.group(1)) if illust_match else None
    artist_match = ARTIST_RE.search(raw)
    artist_id = int(artist_match.group(1)) if artist_match else None
    keywords = raw
    if illust_match: keywords = keywords.replace(illust_match.group(0), "")
    if artist_match: keywords = keywords.replace(artist_match.group(0), "")
    if count_match: keywords = keywords.replace(count_match.group(0), " ")
    if keywords.lower().startswith('/pixiv'): keywords = keywords[6:]
    if artist_id is not None: keywords = re.sub(r'^\s*(artist|画师|作者)\s*', '', keywords, flags=re.I)
    return RequestIntent(keywords=' '.join(keywords.split()), count=count, artist_id=artist_id, illust_id=illust_id)
