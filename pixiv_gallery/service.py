from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from .config import SEARCH_TARGETS, Settings
from .models import Illustration
from .safety import policy_allows


class FeatureDisabledError(RuntimeError):
    pass


class SafetyRejectedError(RuntimeError):
    pass


def positive_integer(value: Any, label: str) -> int:
    try:
        number = int(value)
        if (
            isinstance(value, bool)
            or number <= 0
            or (isinstance(value, float) and not value.is_integer())
        ):
            raise ValueError
        if isinstance(value, str) and not value.strip().isdigit():
            raise ValueError
        return number
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label}必须是正整数。") from exc


@dataclass(frozen=True)
class RequestIntent:
    keywords: str = ""
    count: int | None = None
    artist_id: int | None = None
    illust_id: int | None = None
    search_target: str | None = None

    def validated(self, settings: Settings) -> RequestIntent:
        count = (
            settings.default_count if self.count is None else positive_integer(self.count, "数量")
        )
        illust_id = None if self.illust_id is None else positive_integer(self.illust_id, "插画 ID")
        artist_id = None if self.artist_id is None else positive_integer(self.artist_id, "画师 ID")
        if illust_id is not None and not settings.enable_illust_id_send:
            raise FeatureDisabledError("指定插画 ID 发送未启用。")
        if illust_id is None and artist_id is not None and not settings.enable_artist_random:
            raise FeatureDisabledError("画师 ID 随机选图未启用。")
        keywords = self.keywords.strip() if isinstance(self.keywords, str) else ""
        if illust_id is None and artist_id is None and not keywords:
            raise ValueError("请输入搜索关键词、画师 ID 或 Pixiv 作品链接，例如 /pixiv 星空。")
        if len(keywords) > 500:
            raise ValueError("搜索关键词过长，请缩短到 500 个字符以内。")
        target = self.search_target or settings.search_target
        if not isinstance(target, str) or target not in SEARCH_TARGETS:
            raise ValueError("搜索范围无效。")
        return RequestIntent(keywords, min(count, 60), artist_id, illust_id, target)


class PixivService:
    def __init__(
        self, client: Any, settings: Settings, *, rng: random.Random | None = None
    ) -> None:
        self.client = client
        self.settings = settings
        self.rng = rng or random.Random()

    async def fetch(
        self, intent: RequestIntent, *, is_private: bool | None = None
    ) -> list[Illustration]:
        intent = intent.validated(self.settings)
        if intent.illust_id is not None:
            candidates = [await self.client.illustration_detail(intent.illust_id)]
        elif intent.artist_id is not None:
            candidates = await self.client.user_illustrations(intent.artist_id)
        else:
            candidates = await self.client.search_illustrations(
                intent.keywords, intent.search_target
            )
        safe = [
            work for work in candidates if policy_allows(work, self.settings, is_private=is_private)
        ]
        if candidates and not safe:
            raise SafetyRejectedError("作品被内容安全策略过滤（或安全信息不完整）。")
        if intent.illust_id is None and intent.artist_id is not None:
            self.rng.shuffle(safe)
        return safe[: intent.count]

    async def fetch_lolicon_candidate(
        self,
        illust_id: int,
        expected_user_id: int,
        *,
        is_private: bool | None = None,
    ) -> Illustration | None:
        """Resolve Lolicon IDs through Pixiv, verify author identity, and reapply safety."""
        illust_id = positive_integer(illust_id, "插画 ID")
        expected_user_id = positive_integer(expected_user_id, "画师 ID")
        work = await self.client.illustration_detail(illust_id)
        if work.id != illust_id or work.user_id != expected_user_id or not work.image_urls:
            return None
        if not policy_allows(work, self.settings, is_private=is_private):
            return None
        return work
