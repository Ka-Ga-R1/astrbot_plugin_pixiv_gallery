import asyncio
import inspect
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

import main
from pixiv_gallery.models import Illustration
from pixiv_gallery.pixiv_client import PixivAPIError


class RecordingEvent:
    def __init__(self, user="alice", private=True):
        self.user = user
        self.private = private
        self.unified_msg_origin = "test:private:session" if private else "test:group:room"
        self.message_str = "/pixiv sky"
        self.sent = []
        self.paths = []
        self.fail_images = False

    def get_sender_id(self):
        return self.user

    def is_private_chat(self):
        return self.private

    def plain_result(self, text):
        return {"kind": "text", "text": text}

    def image_result(self, path):
        return {"kind": "image", "path": path}

    async def send(self, result):
        if result["kind"] == "image":
            path = Path(result["path"])
            assert path.is_file(), "image was cleaned up before platform send"
            await asyncio.sleep(0)
            assert path.read_bytes() == b"test-image"
            self.paths.append(path)
            if self.fail_images:
                raise RuntimeError("platform-secret failure")
        self.sent.append(result)


class FakeClient:
    def __init__(self, works=None):
        self.refresh_token = "test-refresh"
        self.works = (
            works
            if works is not None
            else [
                Illustration(id=i, title=f"Work {i}", image_urls=[f"https://i.pximg.net/{i}.jpg"])
                for i in range(1, 5)
            ]
        )
        self.calls = []
        self.error = None

    async def authenticate(self):
        if self.error:
            raise self.error
        return {"access_token": "test-access"}

    async def search_illustrations(self, word, target):
        self.calls.append((word, target))
        if self.error:
            raise self.error
        return list(self.works)

    async def user_illustrations(self, user_id):
        self.calls.append(user_id)
        return list(self.works)

    async def illustration_detail(self, illust_id):
        self.calls.append(illust_id)
        return self.works[0]


class FakeDownloader:
    temporary_directory = staticmethod(lambda: tempfile.TemporaryDirectory(prefix="yumeiro-test-"))

    async def download(self, url, target):
        target.write_bytes(b"test-image")
        return target


def make_plugin(**settings):
    plugin = main.YumeiroPlugin(
        SimpleNamespace(), {"refresh_token": "test-refresh", "cooldown_seconds": 0, **settings}
    )
    plugin._client = FakeClient()
    plugin.downloader = FakeDownloader()
    return plugin


def run(coro):
    return asyncio.run(coro)


def test_llm_tool_is_a_coroutine_with_a_return_value_not_an_async_generator():
    assert inspect.iscoroutinefunction(main.YumeiroPlugin.pixiv_search_tool)
    assert not inspect.isasyncgenfunction(main.YumeiroPlugin.pixiv_search_tool)


def test_tool_returns_summary_and_awaits_images_before_temporary_cleanup():
    async def check():
        plugin, event = make_plugin(), RecordingEvent()
        result = await plugin.pixiv_search_tool(
            event, keywords="温水佳树 負けヒロインが多すぎる", count=3
        )
        assert isinstance(result, str) and "3" in result
        assert len(event.paths) == 3
        assert all(not path.exists() for path in event.paths)
        assert plugin.stats["images_sent_today"] == 3
        assert plugin.stats["requests_today"] == 1

    run(check())


@pytest.mark.parametrize(
    "settings,phrase", [({"enable_natural_language_tool": False}, "关闭"), ({}, "没有找到")]
)
def test_disabled_and_empty_tool_paths_return_explanations(settings, phrase):
    async def check():
        plugin, event = make_plugin(**settings), RecordingEvent()
        plugin._client.works = []
        result = await plugin.pixiv_search_tool(event, keywords="sky", count=1)
        assert isinstance(result, str) and phrase in result

    run(check())


def test_tool_errors_are_reported_without_secret_or_raw_exception():
    async def check():
        plugin, event = make_plugin(), RecordingEvent()
        plugin._client.error = PixivAPIError("test-refresh https://private.test/token secret")
        result = await plugin.pixiv_search_tool(event, keywords="sky")
        assert isinstance(result, str) and "失败" in result
        assert "test-refresh" not in str([result, event.sent, plugin.stats])
        assert "private.test" not in str([result, event.sent, plugin.stats])

    run(check())


@pytest.mark.parametrize(
    "kwargs",
    [
        {"count": "oops"},
        {"count": -2},
        {"count": True},
        {"artist_id": "oops"},
        {"illust_id": -1},
        {"illust_id": True},
    ],
)
def test_invalid_tool_parameters_fail_before_network(kwargs):
    async def check():
        plugin, event = (
            make_plugin(enable_artist_random=True, enable_illust_id_send=True),
            RecordingEvent(),
        )
        result = await plugin.pixiv_search_tool(event, keywords="sky", **kwargs)
        assert isinstance(result, str) and result
        assert not plugin._client.calls
        assert not event.paths

    run(check())


def test_configured_default_and_total_multipage_cap_are_effective():
    async def check():
        plugin, event = make_plugin(default_count=2, max_count=3), RecordingEvent()
        plugin._client.works[0].image_urls *= 4
        await plugin.pixiv_search_tool(event, keywords="sky")
        assert len(event.paths) == 3
        assert plugin.stats["images_sent_today"] == 3

    run(check())


def test_failed_platform_sends_are_not_counted_or_reported_as_success():
    async def check():
        plugin, event = make_plugin(), RecordingEvent()
        event.fail_images = True
        result = await plugin.pixiv_search_tool(event, keywords="sky", count=2)
        assert "失败" in result
        assert plugin.stats["images_sent_today"] == 0
        assert "platform-secret" not in str([result, event.sent, plugin.stats])
        assert all(not path.exists() for path in event.paths)

    run(check())


def test_links_can_be_sent_without_work_metadata():
    async def check():
        plugin, event = (
            make_plugin(show_work_metadata=False, show_pixiv_link=True),
            RecordingEvent(),
        )
        await plugin.pixiv_search_tool(event, keywords="sky", count=1)
        text = str(event.sent)
        assert "https://www.pixiv.net/artworks/1" in text
        assert "Work 1" not in text

    run(check())


def test_cooldown_is_per_session_and_user_and_prevents_second_fetch():
    async def check():
        plugin = make_plugin(cooldown_seconds=30)
        first, other = RecordingEvent(private=False), RecordingEvent("bob", private=False)
        await plugin.pixiv_search_tool(first, keywords="sky", count=1)
        second_result = await plugin.pixiv_search_tool(first, keywords="sky", count=1)
        assert "冷却" in second_result or "等待" in second_result
        await plugin.pixiv_search_tool(other, keywords="different", count=1)
        assert len(plugin._client.calls) == 2

    run(check())


def test_command_and_tool_use_same_delivery_path_and_configured_default():
    async def check():
        plugin, event = make_plugin(default_count=2), RecordingEvent()
        event.message_str = "pixiv 星空"
        await plugin.pixiv_command(event)
        assert len(event.paths) == 2
        assert plugin._client.calls[0][0] == "星空"

    run(check())


def test_regular_requests_persist_rotated_token_without_resetting_client():
    async def check():
        plugin, event = make_plugin(), RecordingEvent()
        client = plugin._client
        client.refresh_token = "rotated-test-token"
        await plugin.pixiv_search_tool(event, keywords="sky", count=1)
        assert plugin.config["refresh_token"] == "rotated-test-token"
        assert plugin._client is client
        assert "rotated-test-token" not in str(event.sent)

    run(check())


def test_cached_raw_results_are_rechecked_for_each_chat_context():
    async def check():
        plugin = make_plugin(filter_r18=False, allow_private_r18=True, allow_group_r18=False)
        plugin._client.works = [
            Illustration(id=1, x_restrict=1, image_urls=["https://i.pximg.net/1.jpg"])
        ]
        private, group = RecordingEvent(private=True), RecordingEvent(private=False)
        await plugin.pixiv_search_tool(private, keywords="same", count=1)
        result = await plugin.pixiv_search_tool(group, keywords="same", count=1)
        assert len(private.paths) == 1
        assert not group.paths
        assert "安全" in result
        assert len(plugin._client.calls) == 1

    run(check())


def test_one_malformed_image_does_not_abort_other_deliveries():
    async def check():
        plugin, event = make_plugin(), RecordingEvent()
        plugin._client.works[0].image_urls = ["https://[invalid"]
        result = await plugin.pixiv_search_tool(event, keywords="sky", count=2)
        assert len(event.paths) == 1
        assert "失败" in result
        assert plugin.stats["images_sent_today"] == 1

    run(check())


def test_termination_cancels_downloads_and_releases_files_and_admission():
    async def check():
        plugin, event = make_plugin(), RecordingEvent()
        started = asyncio.Event()
        folders = []

        class BlockingDownloader:
            @staticmethod
            def temporary_directory():
                directory = tempfile.TemporaryDirectory(prefix="yumeiro-cancel-test-")
                folders.append(Path(directory.name))
                return directory

            async def download(self, url, target):
                target.write_bytes(b"temporary")
                started.set()
                await asyncio.Event().wait()

        plugin.downloader = BlockingDownloader()
        task = asyncio.create_task(plugin.pixiv_search_tool(event, keywords="sky", count=2))
        await started.wait()
        await plugin.terminate()
        assert task.cancelled()
        assert all(not folder.exists() for folder in folders)
        assert not plugin.limiter._active
        assert not plugin._tasks

    run(check())


def test_single_page_setting_and_empty_query():
    async def check():
        plugin, event = make_plugin(send_all_pages=False), RecordingEvent()
        empty_result = await plugin.pixiv_search_tool(event)
        assert "关键词" in empty_result
        assert not plugin._client.calls
        plugin._client.works[0].image_urls *= 3
        await plugin.pixiv_search_tool(event, keywords="sky", count=1)
        assert len(event.paths) == 1

    run(check())


def test_successful_images_are_counted_even_if_later_send_is_cancelled():
    async def check():
        plugin = make_plugin()
        second = asyncio.Event()

        class Event(RecordingEvent):
            async def send(self, result):
                if result["kind"] == "image" and len(self.paths) == 1:
                    second.set()
                    await asyncio.Event().wait()
                await super().send(result)

        event = Event()
        task = asyncio.create_task(plugin.pixiv_search_tool(event, keywords="sky", count=2))
        await second.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert plugin.stats["images_sent_today"] == 1
        assert all(not path.exists() for path in event.paths)

    run(check())


@pytest.mark.parametrize("keywords", ["illustration id abc", "artist id abc"])
def test_malformed_illustration_id_is_reported_without_searching(keywords):
    async def check():
        plugin, event = make_plugin(), RecordingEvent()
        result = await plugin.pixiv_search_tool(event, keywords="illustration id abc")
        assert "ID" in result
        assert not plugin._client.calls

    run(check())
