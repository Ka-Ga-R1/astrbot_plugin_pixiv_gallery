from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .config import Settings
from .formatting import build_text
from .models import Illustration


@dataclass
class SendReport:
    attempted: int = 0
    sent: int = 0
    failed: int = 0
    metadata_failed: bool = False

    def summary(self) -> str:
        if self.attempted == 0:
            return "没有找到可发送的 Pixiv 静态图片。"
        if self.sent == 0:
            return f"Pixiv 图片发送失败：{self.failed} 张未能下载或投递，请检查网络、文件大小限制和平台状态。"
        result = f"已直接向用户发送 {self.sent} 张 Pixiv 图片。"
        if self.failed:
            result += f"另外 {self.failed} 张下载或发送失败。"
        if self.metadata_failed:
            result += "作品文字信息发送失败。"
        return result


class MessageSender:
    def __init__(self, downloader: Any, settings: Settings, *, on_sent=None):
        self.downloader = downloader
        self.settings = settings
        self.on_sent = on_sent

    async def send(self, event: Any, works: list[Illustration]) -> SendReport:
        jobs = []
        selected = []
        for work in works:
            urls = work.image_urls if self.settings.send_all_pages else work.image_urls[:1]
            included = False
            for index, url in enumerate(urls, 1):
                if len(jobs) >= self.settings.max_count:
                    break
                jobs.append((work.id, index, url))
                included = True
            if included:
                selected.append(work)
        report = SendReport(attempted=len(jobs))
        if not jobs:
            return report
        if self.settings.show_work_metadata or self.settings.show_pixiv_link:
            try:
                text = build_text(
                    selected,
                    include_metadata=self.settings.show_work_metadata,
                    include_link=self.settings.show_pixiv_link,
                )
                await event.send(event.plain_result(text))
            except Exception:
                report.metadata_failed = True
        with self.downloader.temporary_directory() as directory:

            async def download(job):
                work_id, index, url = job
                try:
                    suffix = Path(urlsplit(url).path).suffix.lower()
                    if suffix not in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif"}:
                        suffix = ".jpg"
                    target = Path(directory) / f"{work_id}_{index}{suffix}"
                    return await self.downloader.download(url, target)
                except Exception:
                    return None

            tasks = [asyncio.create_task(download(job)) for job in jobs]
            try:
                paths = await asyncio.gather(*tasks)
                for path in paths:
                    if path is None:
                        report.failed += 1
                        continue
                    try:
                        # File stays alive until the platform has finished consuming it.
                        await event.send(event.image_result(str(path)))
                    except Exception:
                        report.failed += 1
                    else:
                        report.sent += 1
                        if self.on_sent is not None:
                            self.on_sent()
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
        return report
