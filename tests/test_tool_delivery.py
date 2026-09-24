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
        if self.error:
            raise self.error
        return list(self.works)

    async def illustration_detail(self, illust_id):
        self.calls.append(illust_id)
        return self.works[0]


class FakeDownloader:
    temporary_directory = staticmethod(lambda: tempfile.TemporaryDirectory(prefix="yumeiro-test-"))

    def __init__(self):
        self.urls = []

    async def download(self, url, target):
        self.urls.append(url)
        target.write_bytes(b"test-image")
        return target


def make_plugin(**settings):
    plugin = main.YumeiroPlugin(
        SimpleNamespace(), {"refresh_token": "test-refresh", "cooldown_seconds": 0, **settings}
    )
    plugin._client = FakeClient()
    plugin.downloader = FakeDownloader()
    plugin.lolicon_client = FakeLolicon(candidate=None)
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
        plugin.lolicon_client = FakeLolicon(candidate=None)
        event.message_str = "pixiv 星空"
        await plugin.pixiv_command(event)
        assert len(event.paths) == 2
        assert plugin.lolicon_client.calls[0] == ["星空"]
        assert plugin._client.calls[0][0] == "星空 100users入り"

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
        result = await plugin.pixiv_search_tool(event, keywords=keywords)
        assert "ID" in result
        assert not plugin._client.calls

    run(check())


@pytest.mark.parametrize(
    "arguments,expected_call",
    [
        ({"artist_id": 1893126}, 1893126),
        ({"illust_id": 128997681}, 128997681),
    ],
)
def test_supplied_pixiv_ids_use_their_matching_endpoint_without_keyword_search(
    arguments, expected_call
):
    async def check():
        plugin = make_plugin(enable_artist_random=True, enable_illust_id_send=True)
        event = RecordingEvent()
        result = await plugin.pixiv_search_tool(event, keywords="", count=2, **arguments)
        assert result
        assert plugin._client.calls == [expected_call]
        assert len(event.paths) == (2 if "artist_id" in arguments else 1)

    run(check())


def test_id_api_failure_reports_safe_status_and_operation():
    async def check():
        plugin, event = make_plugin(enable_artist_random=True), RecordingEvent()
        plugin._client.error = PixivAPIError("private response must not escape", status_code=400)
        result = await plugin.pixiv_search_tool(event, keywords="", artist_id=1893126)
        assert "400" in result
        assert "画师" in result or "artist" in result.lower()
        assert "private response" not in result

    run(check())


class FakeLolicon:
    def __init__(self, candidate=None, error=None):
        self.candidate = candidate
        self.error = error
        self.calls = []

    async def find_random(self, tags):
        self.calls.append(tags)
        if self.error:
            raise self.error
        return self.candidate


def test_lolicon_hit_uses_pixiv_detail_and_never_searches_or_downloads_lolicon_url():
    async def check():
        from pixiv_gallery.lolicon_client import LoliconCandidate

        work = Illustration(
            id=128997681,
            user_id=1893126,
            image_urls=["https://i.pximg.net/img-original/128997681.jpg"],
        )
        plugin = make_plugin(bookmark_threshold=500)
        plugin._client = FakeClient([work])
        plugin.lolicon_client = FakeLolicon(LoliconCandidate(uid=1893126, pid=128997681))
        event = RecordingEvent()
        result = await plugin.pixiv_search_tool(event, keywords="星空, 青髪", count=2)
        assert result
        assert plugin.lolicon_client.calls[0] == ["星空", "青髪"]
        assert plugin._client.calls == [128997681]
        assert len(event.paths) == 1
        assert plugin.downloader.urls == ["https://i.pximg.net/img-original/128997681.jpg"]

    run(check())


@pytest.mark.parametrize("mode", ["empty", "error", "pixiv_mismatch"])
def test_lolicon_empty_or_failure_falls_back_to_same_pixiv_tags(mode):
    async def check():
        from pixiv_gallery.lolicon_client import LoliconAPIError, LoliconCandidate

        plugin = make_plugin(bookmark_threshold=1000)
        if mode == "pixiv_mismatch":
            plugin._client.works[0].user_id = 123
            plugin.lolicon_client = FakeLolicon(LoliconCandidate(uid=1893126, pid=12345))
        elif mode == "error":
            plugin.lolicon_client = FakeLolicon(error=LoliconAPIError("safe"))
        else:
            plugin.lolicon_client = FakeLolicon(candidate=None)
        event = RecordingEvent()
        await plugin.pixiv_search_tool(event, keywords="星空, 青髪", count=1)
        expected = [("星空 青髪 1000users入り", "partial_match_for_tags")]
        if mode == "pixiv_mismatch":
            expected.insert(0, 12345)
        assert plugin._client.calls == expected
        assert len(event.paths) == 1

    run(check())


def test_explicit_ids_bypass_lolicon():
    async def check():
        plugin = make_plugin(enable_artist_random=True, enable_illust_id_send=True)
        plugin.lolicon_client = FakeLolicon()
        await plugin.pixiv_search_tool(RecordingEvent(), keywords="", artist_id=1893126)
        assert plugin.lolicon_client.calls == []
        assert plugin._client.calls == [1893126]

    run(check())


def test_llm_tool_contract_requires_japanese_pixiv_tags():
    doc = main.YumeiroPlugin.pixiv_search_tool.__doc__ or ""
    assert "日文 Pixiv 标签" in doc
    assert "以逗号分隔" in doc


def test_filtered_lolicon_candidate_is_never_sent_and_pixiv_fallback_rechecks_safety():
    async def check():
        from pixiv_gallery.lolicon_client import LoliconCandidate

        plugin = make_plugin()
        plugin._client.works[0].id = 128997681
        plugin._client.works[0].user_id = 1893126
        for work in plugin._client.works:
            work.x_restrict = 1
        plugin.lolicon_client = FakeLolicon(LoliconCandidate(uid=1893126, pid=128997681))
        event = RecordingEvent()
        result = await plugin.pixiv_search_tool(event, keywords="星空")
        assert "安全" in result
        assert plugin._client.calls == [128997681, ("星空 100users入り", "partial_match_for_tags")]
        assert not event.paths

    run(check())


def test_pixiv_fallback_forces_tag_search_even_if_configured_for_title_caption():
    async def check():
        plugin = make_plugin(search_target="title_and_caption")
        plugin.lolicon_client = FakeLolicon(candidate=None)
        await plugin.pixiv_search_tool(RecordingEvent(), keywords="星空, 青髪")
        assert plugin._client.calls == [("星空 青髪 100users入り", "partial_match_for_tags")]

    run(check())


def test_config_schema_publishes_exact_bookmark_tiers():
    import json
    from pathlib import Path

    schema = json.loads(
        (Path(__file__).parents[1] / "_conf_schema.json").read_text(encoding="utf-8")
    )
    assert schema["bookmark_threshold"]["default"] == 100
    assert schema["bookmark_threshold"]["options"] == [100, 500, 1000, 5000, 10000, 50000, 100000]


def test_lolicon_candidate_without_bookmark_metadata_is_still_sent():
    async def check():
        from pixiv_gallery.lolicon_client import LoliconCandidate

        work = Illustration(
            id=128997681,
            user_id=1893126,
            image_urls=["https://i.pximg.net/img-original/128997681.jpg"],
        )
        plugin = make_plugin(bookmark_threshold=500)
        plugin._client = FakeClient([work])
        plugin.lolicon_client = FakeLolicon(LoliconCandidate(uid=1893126, pid=128997681))
        event = RecordingEvent()
        await plugin.pixiv_search_tool(event, keywords="星空", count=1)
        assert plugin._client.calls == [128997681]
        assert len(event.paths) == 1

    run(check())


def test_pixiv_command_explicit_artist_id_still_bypasses_lolicon():
    async def check():
        plugin = make_plugin(enable_artist_random=True)
        plugin.lolicon_client = FakeLolicon()
        event = RecordingEvent()
        event.message_str = "/pixiv artist 1893126"
        await plugin.pixiv_command(event)
        assert plugin.lolicon_client.calls == []
        assert plugin._client.calls == [1893126]

    run(check())
