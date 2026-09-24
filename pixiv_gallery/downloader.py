from __future__ import annotations

import asyncio
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx


class DownloadError(RuntimeError):
    pass


def _is_image(prefix: bytes) -> bool:
    return (
        prefix.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"GIF87a", b"GIF89a"))
        or (prefix.startswith(b"RIFF") and prefix[8:12] == b"WEBP")
        or (prefix[4:8] == b"ftyp" and prefix[8:12] in {b"avif", b"avis"})
    )


class _DownloadLimiter:
    """One adjustable concurrency gate shared for the lifetime of a downloader."""

    def __init__(self, limit: int):
        self.limit = max(1, int(limit))
        self.active = 0
        self._condition = asyncio.Condition()

    @asynccontextmanager
    async def slot(self):
        async with self._condition:
            await self._condition.wait_for(lambda: self.active < self.limit)
            self.active += 1
        try:
            yield
        finally:
            async with self._condition:
                self.active -= 1
                self._condition.notify_all()

    async def set_limit(self, limit: int) -> None:
        async with self._condition:
            self.limit = max(1, int(limit))
            self._condition.notify_all()


class ImageDownloader:
    def __init__(
        self,
        max_size_bytes: int = 12 * 1024 * 1024,
        proxy: str = "",
        *,
        timeout: float = 20,
        concurrency: int = 3,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.max_size_bytes = max_size_bytes
        self.proxy = proxy
        self.timeout = timeout
        self._limiter = _DownloadLimiter(concurrency)
        self._transport = transport

    async def reconfigure(
        self,
        *,
        max_size_bytes: int,
        proxy: str,
        timeout: float,
        concurrency: int,
    ) -> None:
        """Update settings without replacing the gate used by active downloads."""
        self.max_size_bytes = max_size_bytes
        self.proxy = proxy
        self.timeout = timeout
        await self._limiter.set_limit(concurrency)

    @staticmethod
    def validate_url(url: str) -> None:
        try:
            parsed = urlsplit(url)
            host = parsed.hostname or ""
            valid = (
                parsed.scheme == "https"
                and (host == "pximg.net" or host.endswith(".pximg.net"))
                and parsed.username is None
                and parsed.password is None
                and parsed.port in (None, 443)
                and not parsed.fragment
                and not any(char.isspace() for char in url)
            )
        except (TypeError, ValueError):
            valid = False
        if not valid:
            raise DownloadError("仅允许 Pixiv 图片域名的 HTTPS 下载地址。")

    def write_bytes(self, payload: bytes, target: Path) -> Path:
        if not payload or len(payload) > self.max_size_bytes:
            raise DownloadError("图片为空或超过大小限制。")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        return target

    async def download(self, url: str, target: Path) -> Path:
        self.validate_url(url)
        try:
            async with self._limiter.slot():
                async with httpx.AsyncClient(
                    timeout=self.timeout,
                    proxy=self.proxy or None,
                    transport=self._transport,
                    follow_redirects=False,
                    trust_env=False,
                ) as client:
                    for _ in range(4):
                        async with client.stream(
                            "GET",
                            url,
                            headers={
                                "Referer": "https://www.pixiv.net/",
                                "User-Agent": "Mozilla/5.0",
                            },
                        ) as response:
                            if response.is_redirect:
                                location = response.headers.get("location")
                                if not location:
                                    raise DownloadError("图片重定向缺少地址。")
                                url = urljoin(url, location)
                                self.validate_url(url)
                                continue
                            if response.status_code != 200:
                                raise DownloadError(
                                    f"Pixiv 图片请求失败（HTTP {response.status_code}）。"
                                )
                            content_type = (
                                response.headers.get("content-type", "").split(";", 1)[0].lower()
                            )
                            if not (
                                content_type.startswith("image/")
                                or content_type == "application/octet-stream"
                            ):
                                raise DownloadError("下载结果不是图片。")
                            length = response.headers.get("content-length")
                            if length is not None:
                                if not length.isdigit():
                                    raise DownloadError("图片响应长度无效。")
                                if int(length) > self.max_size_bytes:
                                    raise DownloadError("图片超过大小限制。")
                            target.parent.mkdir(parents=True, exist_ok=True)
                            size = 0
                            prefix = b""
                            with target.open("wb") as output:
                                async for chunk in response.aiter_bytes(chunk_size=65536):
                                    size += len(chunk)
                                    if size > self.max_size_bytes:
                                        raise DownloadError("图片超过大小限制。")
                                    if len(prefix) < 16:
                                        prefix = (prefix + chunk)[:16]
                                    output.write(chunk)
                            if not _is_image(prefix):
                                raise DownloadError("下载内容不是受支持的图片。")
                            return target
                    raise DownloadError("图片重定向次数过多。")
        except BaseException as exc:
            target.unlink(missing_ok=True)
            if isinstance(exc, (httpx.HTTPError, OSError)):
                raise DownloadError("图片下载失败，请检查网络、代理和临时目录权限。") from None
            raise

    @staticmethod
    def temporary_directory() -> tempfile.TemporaryDirectory[str]:
        return tempfile.TemporaryDirectory(prefix="yumeiro-")
