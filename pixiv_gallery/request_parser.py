from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

from .service import RequestIntent

URL_RE = re.compile(r"https?://[^\s<>]+", re.I)
ILLUST_RE = re.compile(r"(?:插画|作品|illust(?:ration)?)\s*(?:id)?\s*[:：#]?\s*(\d+)", re.I)
ILLUST_ID_TOKEN_RE = re.compile(
    r"(?:插画|作品|illust(?:ration)?)\s*id\s*[:：#]?\s*([^\s,，。]+)", re.I
)
ARTIST_ID_TOKEN_RE = re.compile(r"(?:artist|画师|作者)\s*id\s*[:：#]?\s*([^\s,，。]+)", re.I)
ARTIST_RE = re.compile(r"(?:artist|画师|作者)\s*(?:id)?\s*[:：#]?\s*(\d+)", re.I)
COUNT_RE = re.compile(r"(?<!\d)(\d{1,4})\s*(?:张|幅|枚|images?\b|pictures?\b|works?\b)", re.I)
BARE_COUNT_RE = re.compile(r"(?<!\S)(\d{1,2})(?!\S)")


def parse_pixiv_request(text: str) -> RequestIntent:
    raw = re.sub(r"^/?pixiv(?:\s+|$)", "", text.strip(), count=1, flags=re.I)
    illust_id = artist_id = None
    spans = []
    for match in URL_RE.finditer(raw):
        # Mask all URLs from loose ID matching, including non-Pixiv lookalikes.
        spans.append(match.span())
        try:
            url = urlsplit(match.group().rstrip(".,\uff0c\u3002)\uff09"))
            port = url.port
        except ValueError:
            continue
        if (
            url.hostname not in {"pixiv.net", "www.pixiv.net"}
            or url.username
            or url.password
            or port not in (None, 80, 443)
        ):
            continue
        path = re.fullmatch(r"/(?:[a-z]{2}/)?(artworks|users)/(\d+)/?", url.path)
        if path:
            if path[1] == "artworks":
                illust_id = int(path[2])
            else:
                artist_id = int(path[2])
        elif re.fullmatch(r"/(?:[a-z]{2}/)?artworks(?:/.*)?", url.path):
            raise ValueError(
                "Pixiv \u63d2\u753b ID \u65e0\u6548\uff0c\u8bf7\u63d0\u4f9b\u6570\u5b57\u4f5c\u54c1 ID\u3002"
            )
        elif re.fullmatch(r"/(?:[a-z]{2}/)?users(?:/.*)?", url.path):
            raise ValueError(
                "Pixiv \u753b\u5e08 ID \u65e0\u6548\uff0c\u8bf7\u63d0\u4f9b\u6570\u5b57 ID\u3002"
            )
        elif url.path == "/member_illust.php":
            query = parse_qs(url.query)
            if "illust_id" in query:
                value = query["illust_id"][0]
                if not value.isascii() or not value.isdigit():
                    raise ValueError(
                        "Pixiv \u63d2\u753b ID \u65e0\u6548\uff0c\u8bf7\u63d0\u4f9b\u6570\u5b57\u4f5c\u54c1 ID\u3002"
                    )
                illust_id = int(value)
    masked = list(raw)
    for start, end in spans:
        masked[start:end] = " " * (end - start)
    keywords = "".join(masked)
    for pattern, label in (
        (ILLUST_ID_TOKEN_RE, "\u63d2\u753b ID"),
        (ARTIST_ID_TOKEN_RE, "\u753b\u5e08 ID"),
    ):
        malformed_id = pattern.search(keywords)
        if malformed_id:
            token = malformed_id[1]
            if not token.isascii() or not token.isdigit():
                raise ValueError(
                    f"{label} \u65e0\u6548\uff0c\u8bf7\u63d0\u4f9b\u6b63\u6574\u6570 ID\u3002"
                )
    for pattern, kind in [(ILLUST_RE, "illust"), (ARTIST_RE, "artist")]:
        match = pattern.search(keywords)
        if match:
            if kind == "illust" and illust_id is None:
                illust_id = int(match[1])
            elif kind == "artist" and artist_id is None:
                artist_id = int(match[1])
            keywords = keywords[: match.start()] + " " + keywords[match.end() :]
    count_match = COUNT_RE.search(keywords) or BARE_COUNT_RE.search(keywords)
    count = int(count_match[1]) if count_match else None
    if count_match:
        keywords = keywords[: count_match.start()] + " " + keywords[count_match.end() :]
    keywords = re.sub(
        r"^(?:请)?(?:帮我)?(?:找|来|发|发送|搜索)(?:一下|一些|几张)?\s*", "", keywords
    )
    keywords = re.sub(r"(?:的)?(?:插画|图片|作品)$", "", keywords).strip()
    if spans and illust_id is None and artist_id is None and not keywords:
        # Leave an invalid/non-Pixiv link as a plain query; never reinterpret it as an ID.
        keywords = raw
    return RequestIntent(" ".join(keywords.split()), count, artist_id, illust_id)
