from __future__ import annotations
import asyncio
from pathlib import Path
from typing import Any
from pixiv_gallery.models import Illustration

class MessageSender:
    def __init__(self, downloader, settings): self.downloader=downloader; self.settings=settings
    async def send(self, event: Any, works: list[Illustration]):
        for work in works:
            for index, url in enumerate(work.image_urls[:1], 1):
                with self.downloader.temporary_directory() as temp:
                    path=await self.downloader.download(url, Path(temp)/f'{work.id}_{index}.jpg')
                    if hasattr(event,'image_result'): yield event.image_result(str(path))
