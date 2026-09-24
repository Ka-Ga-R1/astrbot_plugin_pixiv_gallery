from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from .config import Settings
from .models import Illustration

class FeatureDisabledError(RuntimeError): pass
class SafetyRejectedError(RuntimeError): pass

@dataclass(frozen=True)
class RequestIntent:
    keywords: str = ""
    count: int = 5
    artist_id: int | None = None
    illust_id: int | None = None
    search_target: str | None = None

class PixivService:
    def __init__(self, client: Any, settings: Settings, *, rng: random.Random | None = None) -> None:
        self.client, self.settings, self.rng = client, settings, rng or random.Random()

    async def fetch(self, intent: RequestIntent) -> list[Illustration]:
        count = max(1, min(int(intent.count or self.settings.default_count), self.settings.max_count))
        if intent.illust_id is not None:
            if not self.settings.enable_illust_id_send: raise FeatureDisabledError("指定插画 ID 发送未启用")
            works = [await self.client.illustration_detail(int(intent.illust_id))]
        elif intent.artist_id is not None:
            if not self.settings.enable_artist_random: raise FeatureDisabledError("画师 ID 随机选图未启用")
            candidates = await self.client.user_illustrations(int(intent.artist_id))
            candidates = self._safe(candidates)
            self.rng.shuffle(candidates); works = candidates[:count]
        else:
            works = await self.client.search_illustrations(intent.keywords.strip(), intent.search_target or self.settings.search_target)
            works = self._safe(works)[:count]
        safe = self._safe(works)
        if not safe and works: raise SafetyRejectedError("作品被内容安全策略过滤")
        return safe[:count]

    def _safe(self, works: list[Illustration]) -> list[Illustration]:
        return [work for work in works if not ((self.settings.filter_r18 and work.is_r18) or (self.settings.filter_r18g and work.is_r18g))]
