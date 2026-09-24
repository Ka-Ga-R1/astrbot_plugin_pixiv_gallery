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


def test_page_diagnostics_uses_not_run_state_for_unexecuted_checks():
    plugin = main.YumeiroPlugin(SimpleNamespace(), {"refresh_token": "configured"})
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


def test_page_clear_cache_is_honest_when_cache_is_not_implemented():
    plugin = main.YumeiroPlugin(SimpleNamespace(), {})
    result = awaitable(plugin.page_clear_cache())

    assert result["cleared"] is False
    assert "未启用" in result["message"]


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
