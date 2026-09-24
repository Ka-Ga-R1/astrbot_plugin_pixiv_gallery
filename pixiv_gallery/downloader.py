from __future__ import annotations

import asyncio
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

class DownloadError(RuntimeError): pass

class ImageDownloader:
    def __init__(self, max_size_bytes: int = 12 * 1024 * 1024, proxy: str = "") -> None:
        self.max_size_bytes = max_size_bytes
        self.proxy = proxy

    def validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc: raise DownloadError("图片 URL 必须使用 http 或 https")

    def write_bytes(self, payload: bytes, target: Path) -> Path:
        if len(payload) > self.max_size_bytes: raise DownloadError("图片超过大小限制")
        target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(payload); return target

    def _download_sync(self, url: str, target: Path) -> Path:
        self.validate_url(url)
        request = urllib.request.Request(url, headers={"Referer":"https://app-api.pixiv.net/", "User-Agent":"Mozilla/5.0"})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": self.proxy, "https": self.proxy}) if self.proxy else urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=30) as response:
            content_length = int(response.headers.get("Content-Length", "0") or 0)
            if content_length > self.max_size_bytes: raise DownloadError("图片超过大小限制")
            payload = response.read(self.max_size_bytes + 1)
        return self.write_bytes(payload, target)

    async def download(self, url: str, target: Path) -> Path:
        return await asyncio.to_thread(self._download_sync, url, target)

    @staticmethod
    def temporary_directory() -> tempfile.TemporaryDirectory[str]: return tempfile.TemporaryDirectory(prefix="yumeiro-")
