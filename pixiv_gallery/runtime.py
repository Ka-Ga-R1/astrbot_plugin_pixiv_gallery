"""Bounded, process-local metadata caching and per-caller request admission."""

from __future__ import annotations

import copy
import math
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Hashable
from typing import Any


class MetadataCache:
    def __init__(
        self,
        ttl_seconds: float,
        max_entries: int = 128,
        *,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.ttl_seconds = max(0, ttl_seconds)
        self.max_entries = max(1, max_entries)
        self.clock = clock
        self._entries: OrderedDict[Hashable, tuple[float, Any]] = OrderedDict()
        self.hits = 0
        self.misses = 0
        self.generation = 0

    def _prune(self) -> None:
        now = self.clock()
        for key, (expires, _) in list(self._entries.items()):
            if expires <= now:
                del self._entries[key]

    @property
    def size(self) -> int:
        self._prune()
        return len(self._entries)

    def get(self, key: Hashable) -> Any | None:
        self._prune()
        entry = self._entries.get(key)
        if entry is None:
            self.misses += 1
            return None
        self.hits += 1
        self._entries.move_to_end(key)
        return copy.deepcopy(entry[1])

    def set(self, key: Hashable, value: Any) -> None:
        self._prune()
        self._entries[key] = (self.clock() + self.ttl_seconds, copy.deepcopy(value))
        self._entries.move_to_end(key)
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)

    def clear(self) -> int:
        count = self.size
        self._entries.clear()
        self.generation += 1
        return count


class CachedPixivClient:
    """Cache raw metadata, so service-level safety is rechecked on every read."""

    def __init__(self, client: Any, cache: MetadataCache):
        self.client = client
        self.cache = cache

    async def _cached(self, key: Hashable, fetch: Callable[[], Awaitable[Any]]) -> Any:
        value = self.cache.get(key)
        if value is not None:
            return value
        generation = self.cache.generation
        value = await fetch()
        # Clearing/settings changes must not be undone by an old in-flight request.
        if generation == self.cache.generation:
            self.cache.set(key, value)
        return value

    async def search_illustrations(self, word: str, search_target: str):
        return await self._cached(
            ("search", word, search_target),
            lambda: self.client.search_illustrations(word, search_target),
        )

    async def user_illustrations(self, user_id: int):
        return await self._cached(
            ("artist", user_id), lambda: self.client.user_illustrations(user_id)
        )

    async def illustration_detail(self, illust_id: int):
        return await self._cached(
            ("detail", illust_id), lambda: self.client.illustration_detail(illust_id)
        )


class RateLimitError(RuntimeError):
    def __init__(self, message: str, retry_after: int = 0):
        super().__init__(message)
        self.retry_after = retry_after


class CooldownLimiter:
    def __init__(self, max_entries: int = 4096, *, clock: Callable[[], float] = time.monotonic):
        self.clock = clock
        self.max_entries = max(1, max_entries)
        self._deadlines: dict[Hashable, float] = {}
        self._active: set[Hashable] = set()

    def start(self, key: Hashable, seconds: float) -> None:
        now = self.clock()
        for previous, deadline in list(self._deadlines.items()):
            if deadline <= now and previous not in self._active:
                del self._deadlines[previous]
        if key in self._active:
            raise RateLimitError("上一个 Pixiv 请求仍在处理，请等待完成。")
        remaining = self._deadlines.get(key, now) - now
        if remaining > 0:
            retry_after = math.ceil(remaining)
            raise RateLimitError(f"Pixiv 请求冷却中，请等待 {retry_after} 秒后重试。", retry_after)
        if key not in self._deadlines and len(self._deadlines) >= self.max_entries:
            raise RateLimitError("Pixiv 请求繁忙，请稍后重试。")
        self._deadlines[key] = now + max(0, seconds)
        self._active.add(key)

    def finish(self, key: Hashable) -> None:
        self._active.discard(key)
        if self._deadlines.get(key, 0) <= self.clock():
            self._deadlines.pop(key, None)
