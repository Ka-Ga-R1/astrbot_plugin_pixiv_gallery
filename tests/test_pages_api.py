from types import SimpleNamespace

import main


def test_page_settings_save_persists_refresh_token_and_returns_confirmation(monkeypatch):
    config = {}
    plugin = main.YumeiroPlugin(SimpleNamespace(), config)

    async def payload(default=None):
        return {"refresh_token": "  usable-token  ", "proxy": "http://127.0.0.1:7890"}

    monkeypatch.setattr(main, "request", SimpleNamespace(json=payload))
    result = awaitable(plugin.page_save_settings())

    assert result["saved"] is True
    assert result["message"] == "设置已保存"
    assert config["refresh_token"] == "usable-token"
    assert result["refresh_token_configured"] is True
    assert "refresh_token" not in result
    assert plugin.stats["last_saved_at"] == result["saved_at"]
    assert plugin.stats["activities"][-1]["title"] == "设置已保存"


def test_page_settings_exposes_save_timestamp_without_secret():
    plugin = main.YumeiroPlugin(SimpleNamespace(), {"refresh_token": "secret"})
    result = awaitable(plugin.page_settings())

    assert result["refresh_token_configured"] is True
    assert result["last_saved_at"] is None
    assert "refresh_token" not in result


def test_page_test_connection_persists_rotated_refresh_token(monkeypatch):
    config = {"refresh_token": "old-token"}
    plugin = main.YumeiroPlugin(SimpleNamespace(), config)

    class RotatingClient:
        refresh_token = "old-token"

        async def authenticate(self):
            self.refresh_token = "new-token"

    plugin._client = RotatingClient()
    result = awaitable(plugin.page_test_connection())

    assert result["ok"] is True
    assert config["refresh_token"] == "new-token"
    assert plugin.settings.refresh_token == "new-token"
    assert "new-token" not in awaitable(plugin.page_settings()).__str__()


def test_page_test_connection_activity_does_not_expose_raw_exception(monkeypatch):
    plugin = main.YumeiroPlugin(SimpleNamespace(), {"refresh_token": "secret-token"})

    class FailingClient:
        refresh_token = "secret-token"

        async def authenticate(self):
            raise RuntimeError("secret-token https://example.test/private")

    plugin._client = FailingClient()
    result = awaitable(plugin.page_test_connection())

    assert result["status"] == "error"
    stats = awaitable(plugin.page_stats())
    assert "secret-token" not in str(stats)
    assert "example.test" not in str(stats)


def test_page_diagnostics_marks_dependent_checks_not_run_after_auth_failure():
    plugin = main.YumeiroPlugin(SimpleNamespace(), {"refresh_token": "configured"})

    class FailingClient:
        async def authenticate(self):
            raise RuntimeError("offline test")

    plugin._client = FailingClient()
    result = awaitable(plugin.page_diagnostics())

    assert result["ok"] is False
    assert all(item["status"] in {"not_run", "fail"} for item in result["checks"])


def test_page_diagnostics_does_not_claim_pixiv_api_pass_without_token():
    plugin = main.YumeiroPlugin(SimpleNamespace(), {})
    result = awaitable(plugin.page_diagnostics())

    assert result["ok"] is False
    pixiv_check = next(item for item in result["checks"] if item["key"] == "pixiv_api")
    assert pixiv_check["ok"] is False
    assert pixiv_check["status"] == "fail"
    assert "通过" not in pixiv_check["message"]


def test_page_clear_cache_really_removes_cached_entries():
    plugin = main.YumeiroPlugin(SimpleNamespace(), {})
    plugin.cache.set("test", [1])
    result = awaitable(plugin.page_clear_cache())
    assert result["cleared"] is True
    assert result["removed_entries"] == 1
    assert plugin.cache.size == 0


def awaitable(coro):
    import asyncio

    return asyncio.run(coro)


def test_partial_page_save_preserves_unsubmitted_settings(monkeypatch):
    config = {
        "refresh_token": "keep-token",
        "proxy": "http://127.0.0.1:7890",
        "default_count": 8,
        "max_file_size_mb": 24,
        "filter_r18": True,
    }
    plugin = main.YumeiroPlugin(SimpleNamespace(), config)

    async def payload(default=None):
        return {"filter_r18": False}

    monkeypatch.setattr(main, "request", SimpleNamespace(json=payload))
    result = awaitable(plugin.page_save_settings())

    assert result["saved"] is True
    assert plugin.settings.refresh_token == "keep-token"
    assert plugin.settings.proxy == "http://127.0.0.1:7890"
    assert plugin.settings.default_count == 8
    assert plugin.settings.max_file_size_mb == 24
    assert plugin.settings.filter_r18 is False


def test_page_save_can_clear_refresh_token_without_returning_secret(monkeypatch):
    config = {"refresh_token": "secret-token"}
    plugin = main.YumeiroPlugin(SimpleNamespace(), config)

    async def payload(default=None):
        return {"refresh_token": ""}

    monkeypatch.setattr(main, "request", SimpleNamespace(json=payload))
    result = awaitable(plugin.page_save_settings())

    assert config["refresh_token"] == ""
    assert result["refresh_token_configured"] is False
    assert "secret-token" not in str(result)


def test_diagnostics_actually_authenticates_fetches_and_downloads(monkeypatch):
    import tempfile

    from pixiv_gallery.models import Illustration

    calls = []

    class Client:
        refresh_token = "test"

        async def authenticate(self):
            calls.append("auth")

        async def search_illustrations(self, word, target):
            calls.append("search")
            return [Illustration(id=1, image_urls=["https://i.pximg.net/1.jpg"])]

    class Downloader:
        temporary_directory = staticmethod(tempfile.TemporaryDirectory)

        async def download(self, url, path):
            calls.append("download")
            path.write_bytes(b"image")
            return path

    plugin = main.YumeiroPlugin(SimpleNamespace(), {"refresh_token": "test"})
    plugin._client = Client()
    plugin.downloader = Downloader()
    result = awaitable(plugin.page_diagnostics())
    assert calls == ["auth", "search", "download"]
    assert all(
        check["status"] == "pass"
        for check in result["checks"]
        if check["key"] in {"pixiv_api", "proxy", "image_download"}
    )
    chain = next(check for check in result["checks"] if check["key"] == "message_chain")
    assert chain["status"] == "not_run"
    assert "test" not in str(result.get("refresh_token", ""))
    assert plugin.stats["requests_today"] == 0


def test_stats_roll_over_on_local_day_change_and_expose_real_cache(monkeypatch):
    plugin = main.YumeiroPlugin(SimpleNamespace(), {})
    plugin.stats["date"] = "2026-09-23"
    plugin.stats["requests_today"] = 4
    plugin.stats["images_sent_today"] = 7
    plugin.cache.set("entry", [1])
    monkeypatch.setattr(plugin, "_today", lambda: "2026-09-24")
    result = awaitable(plugin.page_stats())
    assert result["date"] == "2026-09-24"
    assert result["requests_today"] == result["images_sent_today"] == 0
    assert result["cache_entries"] == 1


def test_old_client_rotation_cannot_overwrite_newly_saved_account_token():
    plugin = main.YumeiroPlugin(SimpleNamespace(), {"refresh_token": "new-account"})
    stale_client = SimpleNamespace(refresh_token="old-account-rotation")
    plugin._client = SimpleNamespace(refresh_token="new-account")
    plugin._sync_rotated_token(stale_client)
    assert plugin.config["refresh_token"] == "new-account"


def test_invalid_proxy_save_is_rejected_without_mutating_existing_config(monkeypatch):
    plugin = main.YumeiroPlugin(SimpleNamespace(), {"proxy": "http://127.0.0.1:7890"})

    async def payload(default=None):
        return {"proxy": "not a proxy"}

    monkeypatch.setattr(main, "request", SimpleNamespace(json=payload))
    result = awaitable(plugin.page_save_settings())
    assert result["status"] == "error"
    assert plugin.settings.proxy == "http://127.0.0.1:7890"


def test_failed_disk_save_rolls_back_config_and_returns_sanitized_error(monkeypatch):
    class Config(dict):
        def save_config(self):
            raise OSError("secret-token disk path")

    config = Config(refresh_token="secret-token", default_count=5)
    plugin = main.YumeiroPlugin(SimpleNamespace(), config)

    async def payload(default=None):
        return {"default_count": 2}

    monkeypatch.setattr(main, "request", SimpleNamespace(json=payload))
    result = awaitable(plugin.page_save_settings())
    assert result["status"] == "error"
    assert config["default_count"] == plugin.settings.default_count == 5
    assert "secret-token" not in str(result)


def test_settings_save_preserves_global_download_limit_during_active_request(monkeypatch, tmp_path):
    import asyncio

    import httpx

    from pixiv_gallery.downloader import ImageDownloader

    async def check():
        active = peak = 0
        first_started = asyncio.Event()
        release = asyncio.Event()

        async def handler(request):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            first_started.set()
            await release.wait()
            active -= 1
            return httpx.Response(
                200, headers={"content-type": "image/jpeg"}, content=b"\xff\xd8\xffx"
            )

        transport = httpx.MockTransport(handler)
        plugin = main.YumeiroPlugin(SimpleNamespace(), {"download_concurrency": 1})
        plugin.downloader = ImageDownloader(concurrency=1, transport=transport)
        original_downloader = plugin.downloader
        monkeypatch.setattr(
            main,
            "ImageDownloader",
            lambda max_size, proxy, *, timeout, concurrency: ImageDownloader(
                max_size, proxy, timeout=timeout, concurrency=concurrency, transport=transport
            ),
        )

        first = asyncio.create_task(
            original_downloader.download("https://i.pximg.net/first.jpg", tmp_path / "first.jpg")
        )
        await first_started.wait()

        async def payload(default=None):
            return {"timeout_seconds": 30}

        monkeypatch.setattr(main, "request", SimpleNamespace(json=payload))
        await plugin.page_save_settings()
        second_downloader = plugin.downloader
        second = asyncio.create_task(
            second_downloader.download("https://i.pximg.net/second.jpg", tmp_path / "second.jpg")
        )
        await asyncio.sleep(0.02)
        assert peak == 1, "saving settings must not create a second concurrent download slot"
        release.set()
        await asyncio.gather(first, second)
        assert peak == 1

    awaitable(check())
