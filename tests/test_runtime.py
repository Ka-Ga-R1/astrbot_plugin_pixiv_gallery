import asyncio

import pytest

from pixiv_gallery.runtime import CachedPixivClient, CooldownLimiter, MetadataCache, RateLimitError


def test_metadata_cache_expires_evicts_and_copies_mutable_results():
    now = [0.0]
    cache = MetadataCache(ttl_seconds=10, max_entries=2, clock=lambda: now[0])
    cache.set("a", [1])
    cache.get("a").append(2)
    assert cache.get("a") == [1]
    cache.set("b", [2])
    cache.set("c", [3])
    assert cache.get("a") is None
    assert cache.size == 2
    now[0] = 10
    assert cache.get("b") is None
    assert cache.size == 0
    assert cache.hits == 2


def test_cache_clear_reports_removed_entries_and_rejects_stale_inflight_fill():
    async def check():
        started, finish = asyncio.Event(), asyncio.Event()

        class Client:
            async def search_illustrations(self, word, target):
                started.set()
                await finish.wait()
                return [word]

        cache = MetadataCache(60)
        cache.set("old", [1])
        cached = CachedPixivClient(Client(), cache)
        task = asyncio.create_task(cached.search_illustrations("sky", "tags"))
        await started.wait()
        assert cache.clear() == 1
        finish.set()
        assert await task == ["sky"]
        assert cache.size == 0

    asyncio.run(check())


def test_cached_client_reuses_results_and_does_not_cache_errors():
    async def check():
        class Client:
            def __init__(self):
                self.calls = 0

            async def illustration_detail(self, illust_id):
                self.calls += 1
                if illust_id == 9:
                    raise RuntimeError("test")
                return [illust_id]

        client, cache = Client(), MetadataCache(60)
        cached = CachedPixivClient(client, cache)
        assert await cached.illustration_detail(3) == [3]
        assert await cached.illustration_detail(3) == [3]
        assert client.calls == 1
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await cached.illustration_detail(9)
        assert client.calls == 3

    asyncio.run(check())


def test_cooldown_blocks_inflight_even_when_interval_zero_and_expires():
    now = [10.0]
    limiter = CooldownLimiter(clock=lambda: now[0])
    limiter.start("alice", 0)
    with pytest.raises(RateLimitError):
        limiter.start("alice", 0)
    limiter.finish("alice")
    limiter.start("alice", 5)
    limiter.finish("alice")
    with pytest.raises(RateLimitError) as error:
        limiter.start("alice", 5)
    assert error.value.retry_after == 5
    limiter.start("bob", 5)
    limiter.finish("bob")
    now[0] += 5
    limiter.start("alice", 5)


def test_cooldown_state_is_bounded_without_evicting_active_requests():
    limiter = CooldownLimiter(max_entries=1)
    limiter.start("a", 30)
    with pytest.raises(RateLimitError):
        limiter.start("b", 30)
    with pytest.raises(RateLimitError):
        limiter.start("a", 0)
