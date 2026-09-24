from __future__ import annotations

import asyncio
import hashlib
import json
import math
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from time import monotonic
from typing import Any
from urllib.parse import SplitResult, urlsplit

import httpx

from .models import Illustration

Transport = Callable[..., Awaitable[dict[str, Any]]]


class PixivAPIError(RuntimeError):
    """A public error containing only locally generated, credential-free text."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class PixivClient:
    CLIENT_ID = "MOBrBDS8blbauoSck0ZfDbtuzpyT"
    CLIENT_SECRET = "lsACyCD94FhDUtGTXi3QzcFE2uU1hqtDaKeqrdwj"
    HASH_SECRET = "28c1fdd170a5204386cb1313c7077b34f83e4aaf4aa829ce78c231e05b0bae2c"
    AUTH_URL = "https://oauth.secure.pixiv.net/auth/token"
    MAX_PAGES = 5
    MAX_CANDIDATES = 200
    MAX_TOKEN_TTL = 86400.0

    def __init__(
        self,
        refresh_token: str,
        *,
        transport: Transport | None = None,
        proxy: str = "",
        timeout: float = 20,
    ) -> None:
        self.refresh_token = refresh_token.strip()
        self.proxy = proxy
        self.timeout = timeout
        self._transport = transport
        self.access_token: str | None = None
        self._expires_at = 0.0
        self._auth_lock = asyncio.Lock()
        self._auth_generation = 0
        self._auth_response: dict[str, Any] = {}

    @staticmethod
    def _http_error(status_code: int | None) -> PixivAPIError:
        if type(status_code) is int and 100 <= status_code <= 599:
            return PixivAPIError(f"Pixiv API returned HTTP {status_code}", status_code=status_code)
        return PixivAPIError("Pixiv request failed")

    @staticmethod
    def _validate_payload(payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise PixivAPIError("Pixiv returned an invalid response")
        if payload.get("error") is not None or payload.get("has_error") or payload.get("errors"):
            raise PixivAPIError("Pixiv reported an API error")
        return payload

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        auth_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        headers = self._headers(include_auth=url != self.AUTH_URL)
        if auth_headers:
            headers.update(auth_headers)
        response = None
        try:
            if self._transport is not None:
                payload = await self._transport(
                    method, url, headers=headers, params=params, data=data
                )
            else:
                async with httpx.AsyncClient(
                    timeout=self.timeout,
                    proxy=self.proxy or None,
                    follow_redirects=False,
                ) as client:
                    response = await client.request(
                        method,
                        url,
                        headers=headers,
                        params=params,
                        data=data,
                        follow_redirects=False,
                    )
        except httpx.HTTPStatusError as exc:
            raise self._http_error(exc.response.status_code) from None
        except PixivAPIError as exc:
            # Injected transports have the same redaction boundary as httpx.
            raise self._http_error(exc.status_code) from None
        except (httpx.HTTPError, OSError):
            raise PixivAPIError("Pixiv network request failed") from None
        except Exception:
            # Includes invalid proxy/URL errors. Never surface their raw text.
            # CancelledError is a BaseException and must propagate unchanged.
            raise PixivAPIError("Pixiv request failed") from None

        if response is not None:
            if not 200 <= response.status_code < 300:
                raise self._http_error(response.status_code)
            try:
                payload = response.json()
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise PixivAPIError("Pixiv returned invalid JSON") from None
        return self._validate_payload(payload)

    def _headers(self, *, include_auth: bool = True) -> dict[str, str]:
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        headers = {
            "Accept": "application/json",
            "App-OS": "ios",
            "App-OS-Version": "14.6",
            "App-Version": "7.13.3",
            "User-Agent": "PixivIOSApp/7.13.3 (iOS 14.6; iPhone13,2)",
            "X-Client-Time": timestamp,
            "X-Client-Hash": hashlib.md5(
                (timestamp + self.HASH_SECRET).encode("utf-8")
            ).hexdigest(),
        }
        if include_auth and self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    @staticmethod
    def _valid_token(token: Any) -> bool:
        return (
            isinstance(token, str)
            and bool(token)
            and token.isascii()
            and token.isprintable()
            and not any(character.isspace() for character in token)
        )

    async def _authenticate_locked(self) -> dict[str, Any]:
        if not self.refresh_token:
            raise PixivAPIError("Pixiv refresh token is not configured")
        payload = await self._request(
            "POST",
            self.AUTH_URL,
            data={
                "client_id": self.CLIENT_ID,
                "client_secret": self.CLIENT_SECRET,
                "get_secure_url": 1,
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
            },
        )
        response = self._validate_payload(payload.get("response", payload))
        token = response.get("access_token")
        refresh_token = response.get("refresh_token", self.refresh_token)
        if not self._valid_token(token) or not self._valid_token(refresh_token):
            raise PixivAPIError("Pixiv authentication returned invalid credentials")
        expires = response.get("expires_in", 3600)
        try:
            if isinstance(expires, bool):
                raise ValueError
            expires = float(expires)
            if not math.isfinite(expires) or expires < 0:
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            raise PixivAPIError("Pixiv authentication returned an invalid expiry") from None

        expires = min(expires, self.MAX_TOKEN_TTL)

        # Commit credentials together only after the complete response is valid.
        self.access_token = token
        self.refresh_token = refresh_token
        self._expires_at = monotonic() + expires - min(60, expires / 10)
        self._auth_generation += 1
        self._auth_response = dict(response)
        return dict(response)

    async def authenticate(self) -> dict[str, Any]:
        generation = self._auth_generation
        async with self._auth_lock:
            if generation != self._auth_generation:
                return dict(self._auth_response)
            return await self._authenticate_locked()

    def _token_is_fresh(self) -> bool:
        return bool(self.access_token) and monotonic() < self._expires_at

    async def ensure_authenticated(self) -> None:
        if self._token_is_fresh():
            return
        generation = self._auth_generation
        async with self._auth_lock:
            if generation == self._auth_generation and not self._token_is_fresh():
                await self._authenticate_locked()

    async def _api_request(
        self, method: str, url: str, *, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        await self.ensure_authenticated()
        generation = self._auth_generation
        try:
            return await self._request(method, url, params=params)
        except PixivAPIError as exc:
            if exc.status_code != 401:
                raise
        async with self._auth_lock:
            # A late 401 for an old token must not rotate a newer token again.
            if generation == self._auth_generation:
                await self._authenticate_locked()
        # Retry once only: OAuth failures and a second 401 propagate to the caller.
        return await self._request(method, url, params=params)

    async def search_illustrations(
        self,
        word: str,
        search_target: str = "partial_match_for_tags",
        *,
        limit: int = 60,
    ) -> list[Illustration]:
        return await self._illustrations(
            "https://app-api.pixiv.net/v1/search/illust",
            params={
                "word": word,
                "search_target": search_target,
                "sort": "date_desc",
                "filter": "for_ios",
            },
            limit=limit,
        )

    async def user_illustrations(self, user_id: int, *, limit: int = 60) -> list[Illustration]:
        return await self._illustrations(
            "https://app-api.pixiv.net/v1/user/illusts",
            params={"user_id": int(user_id), "type": "illust", "filter": "for_ios"},
            limit=limit,
        )

    @staticmethod
    def _https_url(value: Any) -> SplitResult | None:
        if not isinstance(value, str) or not value:
            return None
        # urlsplit strips some control characters: reject them before parsing.
        if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value):
            return None
        try:
            parsed = urlsplit(value)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.port not in (None, 443)
                or parsed.fragment
            ):
                return None
        except ValueError:
            return None
        return parsed

    def _next_page_url(self, value: Any, endpoint: str) -> str:
        parsed = self._https_url(value)
        if parsed is None or parsed.netloc != "app-api.pixiv.net" or parsed.path != endpoint:
            raise PixivAPIError("Pixiv returned an untrusted pagination URL")
        return value

    async def _illustrations(
        self, url: str, *, params: dict[str, Any], limit: int
    ) -> list[Illustration]:
        if type(limit) is not int:
            raise PixivAPIError("Pixiv candidate limit must be an integer")
        limit = max(0, min(limit, self.MAX_CANDIDATES))
        if limit == 0:
            return []
        endpoint = urlsplit(url).path
        visited = {url, str(httpx.URL(url, params=params))}
        seen_ids: set[int] = set()
        works: list[Illustration] = []
        examined = 0
        request_params: dict[str, Any] | None = params
        for _ in range(self.MAX_PAGES):
            payload = await self._api_request("GET", url, params=request_params)
            entries = payload.get("illusts")
            if not isinstance(entries, list):
                raise PixivAPIError("Pixiv returned invalid illustration data")
            for item in entries:
                # Duplicates and malformed records still cost a candidate slot.
                if examined >= self.MAX_CANDIDATES or len(works) >= limit:
                    return works
                examined += 1
                work = self._parse(item)
                if work is not None and work.id not in seen_ids:
                    seen_ids.add(work.id)
                    works.append(work)
            if examined >= self.MAX_CANDIDATES or len(works) >= limit:
                break
            next_url = payload.get("next_url")
            if next_url is None or next_url == "":
                break
            url = self._next_page_url(next_url, endpoint)
            if url in visited:
                break
            visited.add(url)
            request_params = None
        return works

    async def illustration_detail(self, illust_id: int) -> Illustration:
        payload = await self._api_request(
            "GET",
            "https://app-api.pixiv.net/v1/illust/detail",
            params={"illust_id": int(illust_id)},
        )
        work = self._parse(payload.get("illust"))
        if work is None:
            raise PixivAPIError("Pixiv illustration was not found or is invalid")
        return work

    @staticmethod
    def _positive_id(value: Any) -> int | None:
        if isinstance(value, str) and value.isascii() and value.isdigit():
            try:
                value = int(value)
            except ValueError:
                return None
        return value if type(value) is int and value > 0 else None

    @classmethod
    def _parse(cls, item: Any) -> Illustration | None:
        if not isinstance(item, dict):
            return None
        illust_id = cls._positive_id(item.get("id"))
        if illust_id is None or item.get("visible") is False or item.get("is_deleted") is True:
            return None

        user = item.get("user")
        user = user if isinstance(user, dict) else {}
        tags = item.get("tags")
        tags = tags if isinstance(tags, list) else []
        single = item.get("meta_single_page")
        single = single if isinstance(single, dict) else {}
        pages = item.get("meta_pages")
        pages = pages if isinstance(pages, list) else []
        originals = [single.get("original_image_url")]
        for page in pages:
            if isinstance(page, dict) and isinstance(page.get("image_urls"), dict):
                originals.append(page["image_urls"].get("original"))
        image_urls: list[str] = []
        for url in originals:
            if cls._https_url(url) is not None and url not in image_urls:
                image_urls.append(url)

        restriction = item.get("x_restrict")
        if type(restriction) is not int or restriction not in (0, 1, 2):
            restriction = None
        return Illustration(
            id=illust_id,
            title=item.get("title") if isinstance(item.get("title"), str) else "",
            user_id=cls._positive_id(user.get("id")),
            user_name=user.get("name") if isinstance(user.get("name"), str) else "",
            tags=[
                tag["name"]
                for tag in tags
                if isinstance(tag, dict) and isinstance(tag.get("name"), str) and tag["name"]
            ],
            image_urls=image_urls,
            x_restrict=restriction,
            type=item.get("type") if isinstance(item.get("type"), str) else "",
            raw=item,
        )
