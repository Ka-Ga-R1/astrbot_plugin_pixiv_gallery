from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from .models import Illustration

Transport = Callable[..., Awaitable[dict[str, Any]]]

class PixivAPIError(RuntimeError):
    pass

class PixivClient:
    CLIENT_ID = 'MOBrBDS8blbauoSck0ZfDbtuzpyT'
    CLIENT_SECRET = 'lsACyCD94FhDUtGTXi3QzcFE2uU1hqtDaKeqrdwj'
    HASH_SECRET = '28c1fdd170a5204386cb1313c7077b34f83e4aaf4aa829ce78c231e05b0bae2c'

    def __init__(self, refresh_token: str, *, transport: Transport | None = None, proxy: str = "", timeout: float = 20) -> None:
        self.refresh_token = refresh_token.strip()
        self.proxy = proxy
        self.timeout = timeout
        self._transport = transport
        self.access_token: str | None = None

    async def _request(self, method: str, url: str, *, params: dict[str, Any] | None = None, data: dict[str, Any] | None = None, auth_headers: dict[str, str] | None = None) -> dict[str, Any]:
        headers = self._headers()
        if auth_headers: headers.update(auth_headers)
        if self._transport is not None:
            return await self._transport(method, url, headers=headers, params=params, data=data)
        try:
            import httpx
        except ImportError as exc:
            raise PixivAPIError("httpx is required for Pixiv requests") from exc
        async with httpx.AsyncClient(timeout=self.timeout, proxy=self.proxy or None) as client:
            response = await client.request(method, url, headers=headers, params=params, data=data)
            if response.status_code >= 400:
                raise PixivAPIError(f"Pixiv API returned HTTP {response.status_code}")
            try: return response.json()
            except json.JSONDecodeError as exc: raise PixivAPIError("Pixiv returned invalid JSON") from exc

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "User-Agent": "PixivIOSApp/7.13.3"}
        if self.access_token: headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    async def authenticate(self) -> dict[str, Any]:
        if not self.refresh_token: raise PixivAPIError("Pixiv refresh token is not configured")
        payload = await self._request("POST", "https://oauth.secure.pixiv.net/auth/token", data={"grant_type":"refresh_token", "refresh_token":self.refresh_token})
        response = payload.get("response") or {}
        token = response.get("access_token")
        if not token: raise PixivAPIError("Pixiv authentication response did not include an access token")
        self.access_token = token
        if response.get("refresh_token"): self.refresh_token = response["refresh_token"]
        return response

    async def ensure_authenticated(self) -> None:
        if not self.access_token: await self.authenticate()

    async def search_illustrations(self, word: str, search_target: str = "partial_match_for_tags") -> list[Illustration]:
        await self.ensure_authenticated()
        payload = await self._request("GET", "https://app-api.pixiv.net/v1/search/illust", params={"word": word, "search_target": search_target})
        return [self._parse(item) for item in payload.get("illusts", [])]

    async def user_illustrations(self, user_id: int) -> list[Illustration]:
        await self.ensure_authenticated()
        payload = await self._request("GET", f"https://app-api.pixiv.net/v1/user/{int(user_id)}/illusts", params={"filter":"for_ios"})
        return [self._parse(item) for item in payload.get("illusts", [])]

    async def illustration_detail(self, illust_id: int) -> Illustration:
        await self.ensure_authenticated()
        payload = await self._request("GET", "https://app-api.pixiv.net/v1/illust/detail", params={"illust_id": int(illust_id)})
        item = payload.get("illust")
        if not item: raise PixivAPIError("Pixiv illustration was not found")
        return self._parse(item)

    @staticmethod
    def _parse(item: dict[str, Any]) -> Illustration:
        single = item.get("meta_single_page") or {}
        image_urls = []
        if single.get("original_image_url"): image_urls.append(single["original_image_url"])
        for page in item.get("meta_pages") or []:
            url = ((page.get("image_urls") or {}).get("original"))
            if url and url not in image_urls: image_urls.append(url)
        return Illustration(id=int(item["id"]), title=item.get("title", ""), user_id=((item.get("user") or {}).get("id")), user_name=((item.get("user") or {}).get("name", "")), tags=[tag.get("name", "") for tag in item.get("tags", []) if tag.get("name")], image_urls=image_urls, x_restrict=int(item.get("x_restrict", 0) or 0), type=item.get("type", "illust"), raw=item)

