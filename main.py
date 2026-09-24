from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__:
    from .pixiv_gallery.config import Settings, valid_proxy
    from .pixiv_gallery.downloader import ImageDownloader
    from .pixiv_gallery.pixiv_client import PixivAPIError, PixivClient
    from .pixiv_gallery.request_parser import parse_pixiv_request
    from .pixiv_gallery.runtime import (
        CachedPixivClient,
        CooldownLimiter,
        MetadataCache,
        RateLimitError,
    )
    from .pixiv_gallery.sender import MessageSender
    from .pixiv_gallery.service import (
        FeatureDisabledError,
        PixivService,
        RequestIntent,
        SafetyRejectedError,
    )
else:
    from pixiv_gallery.config import Settings, valid_proxy
    from pixiv_gallery.downloader import ImageDownloader
    from pixiv_gallery.pixiv_client import PixivAPIError, PixivClient
    from pixiv_gallery.request_parser import parse_pixiv_request
    from pixiv_gallery.runtime import (
        CachedPixivClient,
        CooldownLimiter,
        MetadataCache,
        RateLimitError,
    )
    from pixiv_gallery.sender import MessageSender
    from pixiv_gallery.service import (
        FeatureDisabledError,
        PixivService,
        RequestIntent,
        SafetyRejectedError,
    )

PLUGIN_NAME = "astrbot_plugin_pixiv_gallery"
ASTRBOT_AVAILABLE = False

try:
    from astrbot.api import AstrBotConfig, logger
    from astrbot.api.event import AstrMessageEvent, MessageChain, filter
    from astrbot.api.star import Context, Star

    ASTRBOT_AVAILABLE = True
except ModuleNotFoundError as exc:
    if exc.name != "astrbot":
        raise
    logger = None
    AstrMessageEvent = Any
    MessageChain = None
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

WEB_AVAILABLE = False
try:
    from astrbot.api.web import error_response, json_response, request

    WEB_AVAILABLE = True
except ModuleNotFoundError as exc:
    if exc.name not in {"astrbot", "astrbot.api.web"}:
        raise

    class _Request:
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
            "date": self._today(),
            "requests_today": 0,
            "images_sent_today": 0,
            "last_status": "未运行",
            "activities": [],
            "last_saved_at": None,
            "last_connection_test_at": None,
        }
        self.cache = MetadataCache(self.settings.cache_ttl_minutes * 60)
        self.limiter = CooldownLimiter()
        self._client: PixivClient | None = None
        self.downloader = self._make_downloader()
        self._tasks: set[asyncio.Task] = set()
        self._register_pages()

    @staticmethod
    def _today() -> str:
        return datetime.now().astimezone().date().isoformat()

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _rollover_stats(self) -> None:
        today = self._today()
        if self.stats["date"] != today:
            self.stats.update(date=today, requests_today=0, images_sent_today=0)

    def _record_activity(self, title: str, detail: str, kind: str = "") -> None:
        self.stats["activities"].append(
            {"title": title, "detail": detail, "kind": kind, "at": self._timestamp()}
        )
        self.stats["activities"] = self.stats["activities"][-20:]

    def _make_downloader(self) -> ImageDownloader:
        return ImageDownloader(
            self.settings.max_file_size_mb * 1024 * 1024,
            self.settings.proxy,
            timeout=self.settings.timeout_seconds,
            concurrency=self.settings.download_concurrency,
        )

    def _register_pages(self) -> None:
        if ASTRBOT_AVAILABLE and not WEB_AVAILABLE:
            if logger:
                logger.warning("Yumeiro: 当前 AstrBot 不支持 Plugin Pages API，聊天功能仍可使用。")
            return
        routes = [
            ("settings", self.page_settings, ["GET"], "Get Yumeiro settings"),
            ("settings/save", self.page_save_settings, ["POST"], "Save Yumeiro settings"),
            ("connection/test", self.page_test_connection, ["POST"], "Test Pixiv connection"),
            ("cache/clear", self.page_clear_cache, ["POST"], "Clear Yumeiro cache"),
            ("diagnostics/run", self.page_diagnostics, ["POST"], "Run Yumeiro diagnostics"),
            ("stats", self.page_stats, ["GET"], "Get Yumeiro stats"),
        ]
        if hasattr(self.context, "register_web_api"):
            for route, handler, methods, description in routes:
                self.context.register_web_api(
                    f"/{PLUGIN_NAME}/{route}", handler, methods, description
                )

    def _save_config_values(self, values: dict[str, Any]) -> None:
        old = dict(self.config)
        try:
            self.config.update(values)
            if hasattr(self.config, "save_config"):
                self.config.save_config()
        except Exception:
            self.config.clear()
            self.config.update(old)
            raise

    async def _persist(self, updates: dict[str, Any]) -> Settings:
        merged = {**self.config, **updates}
        normalized = Settings.from_mapping(merged)
        self._save_config_values(normalized.__dict__)
        self.settings = normalized
        self._client = None
        self.cache.clear()
        self.cache.ttl_seconds = self.settings.cache_ttl_minutes * 60
        await self.downloader.reconfigure(
            max_size_bytes=self.settings.max_file_size_mb * 1024 * 1024,
            proxy=self.settings.proxy,
            timeout=self.settings.timeout_seconds,
            concurrency=self.settings.download_concurrency,
        )
        self.stats["last_status"] = "配置已更新，等待验证"
        return normalized

    async def page_settings(self):
        return json_response(
            {
                **self.settings.public_dict(),
                "last_saved_at": self.stats["last_saved_at"],
                "last_connection_test_at": self.stats["last_connection_test_at"],
            }
        )

    async def page_save_settings(self):
        try:
            payload = await request.json(default={})
        except Exception:
            return error_response("配置必须是有效的 JSON 对象", status_code=400)
        if not isinstance(payload, dict):
            return error_response("配置必须是 JSON 对象", status_code=400)
        updates = {
            key: value for key, value in payload.items() if key in Settings.__dataclass_fields__
        }
        if "refresh_token" in updates and not isinstance(updates["refresh_token"], str):
            return error_response("Refresh Token 必须是字符串", status_code=400)
        if "proxy" in updates and (
            not isinstance(updates["proxy"], str) or not valid_proxy(updates["proxy"].strip())
        ):
            return error_response("代理必须是有效的 HTTP 或 HTTPS 地址", status_code=400)
        try:
            await self._persist(updates)
        except Exception:
            return error_response("配置保存失败，请检查 AstrBot 配置文件权限。", status_code=500)
        saved_at = self._timestamp()
        self.stats["last_saved_at"] = saved_at
        self._record_activity("设置已保存", "插件配置已写入 AstrBot。", "success")
        return json_response(
            {
                "saved": True,
                "message": "设置已保存",
                "saved_at": saved_at,
                "last_saved_at": saved_at,
                **self.settings.public_dict(),
            }
        )

    def _get_client(self) -> PixivClient:
        if self._client is None:
            self._client = PixivClient(
                self.settings.refresh_token,
                proxy=self.settings.proxy,
                timeout=self.settings.timeout_seconds,
            )
        return self._client

    def _sync_rotated_token(self, client: Any) -> None:
        # A request started before an account/settings change may finish afterwards.
        if client is not self._client:
            return
        rotated = getattr(client, "refresh_token", "")
        if (
            isinstance(rotated, str)
            and rotated.strip()
            and rotated.strip() != self.settings.refresh_token
        ):
            rotated = rotated.strip()
            self._save_config_values({"refresh_token": rotated})
            self.settings = replace(self.settings, refresh_token=rotated)

    async def page_test_connection(self):
        tested_at = self._timestamp()
        self.stats["last_connection_test_at"] = tested_at
        try:
            client = self._get_client()
            await client.authenticate()
            self._sync_rotated_token(client)
        except Exception:
            self.stats["last_status"] = "连接失败"
            self._record_activity("Pixiv 连接验证失败", "Pixiv 鉴权或网络请求失败。", "warning")
            return error_response(
                "Pixiv 连接失败：请检查 Refresh Token、代理或网络设置", status_code=502
            )
        self.stats["last_status"] = "连接成功"
        self._record_activity("Pixiv 连接验证成功", "Refresh Token 验证通过。", "success")
        return json_response({"ok": True, "message": "Pixiv 连接测试通过", "tested_at": tested_at})

    async def page_clear_cache(self):
        removed = self.cache.clear()
        message = f"已清理 {removed} 条 Pixiv 元数据缓存。"
        self._record_activity("缓存已清理", message, "success")
        return json_response({"cleared": True, "removed_entries": removed, "message": message})

    async def page_diagnostics(self):
        tested_at = self._timestamp()
        checks = []

        def add(key: str, status: str, message: str):
            checks.append(
                {"key": key, "status": status, "ok": status == "pass", "message": message}
            )

        try:
            if not self.settings.refresh_token:
                raise PixivAPIError("missing token")
            client = self._get_client()
            await client.authenticate()
            self._sync_rotated_token(client)
            # Use a fresh API probe rather than a cache hit for network diagnostics.
            works = await PixivService(client, self.settings).fetch(
                RequestIntent(keywords="風景", count=1)
            )
            add("pixiv_api", "pass", "Pixiv 鉴权和搜索接口请求成功。")
            add(
                "proxy",
                "pass",
                "已通过配置的代理完成 API 请求。"
                if self.settings.proxy
                else "已通过直连完成 API 请求。",
            )
        except Exception:
            add(
                "pixiv_api",
                "fail",
                "未配置 Refresh Token。"
                if not self.settings.refresh_token
                else "Pixiv 鉴权或 API 探测失败，请检查凭据和网络。",
            )
            add("proxy", "not_run", "API 探测未通过，无法确认代理或直连状态。")
            add("image_download", "not_run", "未获得安全的测试图片，未执行下载。")
        else:
            if not works or not works[0].image_urls:
                add("image_download", "not_run", "本次 API 未返回可用的安全图片，未执行下载。")
            else:
                try:
                    with self.downloader.temporary_directory() as temp:
                        await self.downloader.download(
                            works[0].image_urls[0], Path(temp) / "diagnostic.jpg"
                        )
                    add("image_download", "pass", "已实际下载安全图片，并清理临时文件。")
                except Exception:
                    add(
                        "image_download",
                        "fail",
                        "图片下载探测失败，请检查代理、网络和文件大小限制。",
                    )
        if ASTRBOT_AVAILABLE and MessageChain is not None:
            try:
                MessageChain().message("Yumeiro diagnostics")
                add("message_chain", "pass", "消息链构造正常；没有聊天事件，未验证实际平台投递。")
            except Exception:
                add("message_chain", "fail", "AstrBot 消息链构造失败。")
        else:
            add("message_chain", "not_run", "当前不在 AstrBot 运行环境，未验证消息链或平台投递。")
        passed = [check["key"] for check in checks if check["ok"]]
        self._record_activity(
            "诊断已完成", f"{len(passed)}/{len(checks)} 项检查通过；实际聊天投递需在聊天中验证。"
        )
        return json_response(
            {
                "checks": checks,
                "passed": passed,
                "ok": len(passed) == len(checks),
                "tested_at": tested_at,
                "actual_message_delivery": "not_run",
            }
        )

    async def page_stats(self):
        self._rollover_stats()
        return json_response(
            {
                **self.stats,
                "cache_entries": self.cache.size,
                "cache_hits": self.cache.hits,
                "cache_misses": self.cache.misses,
            }
        )

    async def _fetch(
        self,
        intent: RequestIntent,
        *,
        settings: Settings | None = None,
        is_private: bool | None = None,
    ):
        client = self._get_client()
        try:
            return await PixivService(
                CachedPixivClient(client, self.cache), settings or self.settings
            ).fetch(intent, is_private=is_private)
        finally:
            self._sync_rotated_token(client)

    @staticmethod
    def _private_context(event: AstrMessageEvent) -> bool | None:
        method = getattr(event, "is_private_chat", None)
        if callable(method):
            value = method()
            if isinstance(value, bool):
                return value
        return None

    @staticmethod
    def _caller_key(event: AstrMessageEvent) -> tuple[str, str]:
        method = getattr(event, "get_sender_id", None)
        sender = str(method() or "unknown") if callable(method) else "unknown"
        return str(getattr(event, "unified_msg_origin", "unknown")), sender

    async def _notify(self, event: AstrMessageEvent, text: str) -> str:
        try:
            await event.send(event.plain_result(text))
        except Exception:
            if logger:
                logger.warning("Yumeiro: 提示消息投递失败，详细内容已保留在工具返回值中。")
        return text

    def _count_image(self) -> None:
        self._rollover_stats()
        self.stats["images_sent_today"] += 1

    async def _handle_intent(self, event: AstrMessageEvent, intent: RequestIntent) -> str:
        settings, downloader = self.settings, self.downloader
        try:
            intent = intent.validated(settings)
            key = self._caller_key(event)
            self.limiter.start(key, settings.cooldown_seconds)
        except (ValueError, FeatureDisabledError, RateLimitError) as exc:
            return await self._notify(event, f"Yumeiro：{exc}")
        task = asyncio.current_task()
        if task is not None:
            self._tasks.add(task)
        self._rollover_stats()
        self.stats["requests_today"] += 1
        try:
            works = await self._fetch(
                intent, settings=settings, is_private=self._private_context(event)
            )
            if not works:
                self.stats["last_status"] = "没有找到作品"
                self._record_activity("Pixiv 搜索无结果", "没有找到符合条件的作品。")
                return await self._notify(event, "没有找到符合条件的 Pixiv 作品，请尝试其他标签。")
            report = await MessageSender(downloader, settings, on_sent=self._count_image).send(
                event, works
            )
            summary = report.summary()
            self.stats["last_status"] = f"已发送 {report.sent} 张" if report.sent else "发送失败"
            self._record_activity(
                "Pixiv 请求完成",
                summary,
                "success" if report.sent and not report.failed else "warning",
            )
            if report.failed or not report.sent:
                await self._notify(event, summary)
            return summary
        except SafetyRejectedError as exc:
            message = f"Yumeiro：{exc}"
            self.stats["last_status"] = "内容安全拦截"
            self._record_activity("内容安全拦截", "本次请求未通过内容安全策略。", "warning")
            return await self._notify(event, message)
        except Exception:
            self.stats["last_status"] = "请求失败"
            self._record_activity(
                "Pixiv 请求失败", "请检查 Refresh Token、代理、网络和插件配置。", "warning"
            )
            if logger:
                logger.warning(
                    "Yumeiro: Pixiv 请求失败，请使用管理页诊断。异常正文已隐藏以保护凭据。"
                )
            return await self._notify(
                event,
                "Yumeiro：Pixiv 请求失败，请检查 Refresh Token、代理或网络设置，并运行管理页诊断。",
            )
        finally:
            self.limiter.finish(key)
            if task is not None:
                self._tasks.discard(task)

    @filter.command("pixiv")
    async def pixiv_command(self, event: AstrMessageEvent):
        if not self.settings.enable_fallback_command:
            await self._notify(event, "Yumeiro 备用命令当前已关闭。")
            return
        try:
            intent = parse_pixiv_request(event.message_str)
        except ValueError as exc:
            await self._notify(event, f"Yumeiro：{exc}")
            return
        await self._handle_intent(event, intent)

    @filter.llm_tool(name="pixiv_search_illustrations")
    async def pixiv_search_tool(
        self,
        event: AstrMessageEvent,
        keywords: str = "",
        count: int | None = None,
        artist_id: int | None = None,
        illust_id: int | None = None,
    ) -> str:
        """搜索并直接向用户发送 Pixiv 插画，返回真实发送结果；不要重复发送图片。

        Args:
            keywords(string): 角色、主题或场景的 Pixiv 标签关键词，也支持 Pixiv 作品链接；指定 ID 时可省略。
            count(number): 可选的作品数量，省略时使用插件默认值；总图片页数仍受插件上限约束。
            artist_id(number): 可选的正整数画师 ID，仅在画师随机功能开启时使用。
            illust_id(number): 可选的正整数插画 ID，仅在指定作品功能开启时使用，优先于画师 ID。
        """
        if not self.settings.enable_natural_language_tool:
            return await self._notify(event, "Yumeiro 自然语言工具当前已关闭。")
        if not isinstance(keywords, str):
            return await self._notify(event, "Yumeiro：搜索关键词必须是字符串。")
        try:
            parsed = parse_pixiv_request(keywords)
        except ValueError as exc:
            return await self._notify(event, f"Yumeiro：{exc}")
        intent = RequestIntent(
            parsed.keywords,
            count if count is not None else parsed.count,
            artist_id if artist_id is not None else parsed.artist_id,
            illust_id if illust_id is not None else parsed.illust_id,
        )
        return await self._handle_intent(event, intent)

    async def terminate(self):
        current = asyncio.current_task()
        tasks = [task for task in self._tasks if task is not current and not task.done()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.cache.clear()


Plugin = YumeiroPlugin
