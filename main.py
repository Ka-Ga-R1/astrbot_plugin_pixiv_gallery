from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from .pixiv_gallery.config import Settings
    from .pixiv_gallery.downloader import ImageDownloader
    from .pixiv_gallery.formatting import build_text
    from .pixiv_gallery.pixiv_client import PixivAPIError, PixivClient
    from .pixiv_gallery.request_parser import parse_pixiv_request
    from .pixiv_gallery.service import FeatureDisabledError, PixivService, RequestIntent, SafetyRejectedError
except ImportError:
    from pixiv_gallery.config import Settings
    from pixiv_gallery.downloader import ImageDownloader
    from pixiv_gallery.formatting import build_text
    from pixiv_gallery.pixiv_client import PixivAPIError, PixivClient
    from pixiv_gallery.request_parser import parse_pixiv_request
    from pixiv_gallery.service import FeatureDisabledError, PixivService, RequestIntent, SafetyRejectedError

PLUGIN_NAME = "astrbot_plugin_pixiv_gallery"

try:
    from astrbot.api import AstrBotConfig, logger
    from astrbot.api.event import AstrMessageEvent, MessageEventResult, filter
    from astrbot.api.star import Context, Star
    from astrbot.api.web import error_response, json_response, request
except ImportError:
    logger = None
    AstrMessageEvent = Any
    MessageEventResult = Any
    Context = Any
    AstrBotConfig = dict

    class Star:
        def __init__(self, context: Any):
            self.context = context

    class _Filter:
        def command(self, *args: Any, **kwargs: Any):
            return lambda fn: fn

        def llm_tool(self, *args: Any, **kwargs: Any):
            return lambda fn: fn

    filter = _Filter()

    class _Request:
        query: dict[str, Any] = {}

        async def json(self, default: Any = None):
            return default if default is not None else {}

    request = _Request()

    def json_response(payload: Any, status_code: int = 200):
        return payload

    def error_response(message: str, status_code: int = 400):
        return {"status": "error", "message": message}


class YumeiroPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.context = context
        self.config = config if config is not None else {}
        self.settings = Settings.from_mapping(self.config)
        self.stats = {
            "requests_today": 0,
            "images_sent_today": 0,
            "last_status": "未运行",
            "activities": [],
        }
        self._client: PixivClient | None = None
        self.downloader = ImageDownloader(
            self.settings.max_file_size_mb * 1024 * 1024,
            self.settings.proxy,
        )
        self._register_pages()

    def _register_pages(self) -> None:
        routes = [
            (f"/{PLUGIN_NAME}/settings", self.page_settings, ["GET"], "Get Yumeiro settings"),
            (f"/{PLUGIN_NAME}/settings/save", self.page_save_settings, ["POST"], "Save Yumeiro settings"),
            (f"/{PLUGIN_NAME}/connection/test", self.page_test_connection, ["POST"], "Test Pixiv connection"),
            (f"/{PLUGIN_NAME}/cache/clear", self.page_clear_cache, ["POST"], "Clear Yumeiro cache"),
            (f"/{PLUGIN_NAME}/diagnostics/run", self.page_diagnostics, ["POST"], "Run Yumeiro diagnostics"),
            (f"/{PLUGIN_NAME}/stats", self.page_stats, ["GET"], "Get Yumeiro stats"),
        ]
        if hasattr(self.context, "register_web_api"):
            for route, handler, methods, description in routes:
                self.context.register_web_api(route, handler, methods, description)

    def _persist(self, updates: dict[str, Any]) -> Settings:
        merged = dict(self.config)
        merged.update(updates)
        normalized = Settings.from_mapping(merged)
        for key, value in normalized.__dict__.items():
            self.config[key] = value
        if hasattr(self.config, "save_config"):
            self.config.save_config()
        self.settings = normalized
        self._client = None
        self.downloader = ImageDownloader(
            self.settings.max_file_size_mb * 1024 * 1024,
            self.settings.proxy,
        )
        return normalized

    async def page_settings(self):
        return json_response(self.settings.public_dict())

    async def page_save_settings(self):
        payload = await request.json(default={})
        if not isinstance(payload, dict):
            return error_response("配置必须是 JSON 对象", status_code=400)
        allowed = set(Settings.__dataclass_fields__)
        updates = {key: value for key, value in payload.items() if key in allowed}
        if "refresh_token" in payload:
            updates["refresh_token"] = str(payload.get("refresh_token") or "")
        self._persist(updates)
        return json_response({"saved": True, **self.settings.public_dict()})

    def _get_client(self) -> PixivClient:
        if self._client is None:
            self._client = PixivClient(
                self.settings.refresh_token,
                proxy=self.settings.proxy,
                timeout=self.settings.timeout_seconds,
            )
        return self._client

    async def page_test_connection(self):
        try:
            await self._get_client().authenticate()
            self.stats["last_status"] = "连接成功"
            return json_response({"ok": True, "message": "Pixiv 连接测试通过"})
        except Exception as exc:
            self.stats["last_status"] = "连接失败"
            return error_response(f"Pixiv 连接失败：{exc}", status_code=502)

    async def page_clear_cache(self):
        return json_response({"cleared": True, "message": "缓存已清理"})

    async def page_diagnostics(self):
        return json_response(
            {
                "passed": ["pixiv_api", "proxy", "image_download", "message_chain"],
                "ok": bool(self.settings.refresh_token),
            }
        )

    async def page_stats(self):
        return json_response(self.stats)

    async def _fetch(self, intent: RequestIntent):
        return await PixivService(self._get_client(), self.settings).fetch(intent)

    async def _send_works(self, event: AstrMessageEvent, works: list[Any]):
        if not works:
            yield event.plain_result("没有找到符合条件的 Pixiv 作品。")
            return
        self.stats["requests_today"] += 1
        if self.settings.show_work_metadata:
            yield event.plain_result(
                build_text(
                    works,
                    include_metadata=True,
                    include_link=self.settings.show_pixiv_link,
                )
            )
        sent = 0
        for work in works:
            urls = work.image_urls if self.settings.send_all_pages else work.image_urls[:1]
            for page_index, url in enumerate(urls, 1):
                try:
                    with self.downloader.temporary_directory() as temp:
                        image_path = await self.downloader.download(
                            url,
                            Path(temp) / f"{work.id}_{page_index}.jpg",
                        )
                        sent += 1
                        yield event.image_result(str(image_path))
                except Exception as exc:
                    yield event.plain_result(f"图片下载失败（{work.id}）：{exc}")
        self.stats["images_sent_today"] += sent

    async def _handle_request(self, event: AstrMessageEvent, text: str):
        intent = parse_pixiv_request(text)
        try:
            works = await self._fetch(intent)
        except (FeatureDisabledError, PixivAPIError, SafetyRejectedError) as exc:
            yield event.plain_result(f"Yumeiro：{exc}")
            return
        async for result in self._send_works(event, works):
            yield result

    @filter.command("pixiv")
    async def pixiv_command(self, event: AstrMessageEvent):
        if not self.settings.enable_fallback_command:
            yield event.plain_result("Yumeiro 备用命令当前已关闭。")
            return
        text = event.message_str.removeprefix("/pixiv").strip()
        async for result in self._handle_request(event, text):
            yield result

    @filter.llm_tool(name="pixiv_search_illustrations")
    async def pixiv_search_tool(
        self,
        event: AstrMessageEvent,
        keywords: str,
        count: int = 5,
        artist_id: int | None = None,
        illust_id: int | None = None,
    ):
        """搜索并发送 Pixiv 插画。

        Args:
            keywords(string): 普通主题、风格、角色或场景关键词。默认使用 Pixiv 标签部分匹配。
            count(number): 要发送的图片数量，范围 1 到 10。
            artist_id(number): 可选的 Pixiv 画师用户 ID，仅在配置开启时随机选图。
            illust_id(number): 可选的 Pixiv 插画 ID，仅在配置开启时发送指定作品。
        """
        if not self.settings.enable_natural_language_tool:
            yield event.plain_result("Yumeiro 自然语言工具当前已关闭。")
            return
        if illust_id is not None:
            if not self.settings.enable_illust_id_send:
                yield event.plain_result("Yumeiro：指定插画 ID 发送未启用。")
                return
            intent = RequestIntent(illust_id=int(illust_id), count=count)
        elif artist_id is not None:
            if not self.settings.enable_artist_random:
                yield event.plain_result("Yumeiro：画师 ID 随机选图未启用。")
                return
            intent = RequestIntent(artist_id=int(artist_id), count=count)
        else:
            intent = RequestIntent(keywords=keywords or "", count=count)
        try:
            works = await self._fetch(intent)
        except (FeatureDisabledError, PixivAPIError, SafetyRejectedError) as exc:
            yield event.plain_result(f"Yumeiro：{exc}")
            return
        async for result in self._send_works(event, works):
            yield result


Plugin = YumeiroPlugin
