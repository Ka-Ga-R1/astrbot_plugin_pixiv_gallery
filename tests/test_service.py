import asyncio

from pixiv_gallery.config import Settings
from pixiv_gallery.models import Illustration
from pixiv_gallery.service import FeatureDisabledError, PixivService, RequestIntent


class FakeClient:
    def __init__(self):
        self.search_calls = []

    async def search_illustrations(self, word, target):
        self.search_calls.append((word, target))
        return [Illustration(id=1, title="safe"), Illustration(id=2, title="adult", x_restrict=1)]

    async def user_illustrations(self, user_id):
        return [Illustration(id=3, user_id=user_id), Illustration(id=4, user_id=user_id)]

    async def illustration_detail(self, illust_id):
        return Illustration(id=illust_id, title="specified")


def test_keyword_search_uses_partial_tag_target_and_filters():
    async def run():
        client = FakeClient()
        service = PixivService(client, Settings.from_mapping({}))
        result = await service.fetch(RequestIntent(keywords="sunset", count=5))
        assert [item.id for item in result] == [1]
        assert client.search_calls == [("sunset", "partial_match_for_tags")]

    asyncio.run(run())


def test_artist_random_requires_feature_flag():
    async def run():
        service = PixivService(FakeClient(), Settings.from_mapping({}))
        try:
            await service.fetch(RequestIntent(artist_id=123))
        except FeatureDisabledError:
            return
        raise AssertionError("expected feature disabled")

    asyncio.run(run())


def test_artist_random_and_illust_id_priority():
    async def run():
        settings = Settings.from_mapping(
            {"enable_artist_random": True, "enable_illust_id_send": True}
        )
        service = PixivService(FakeClient(), settings)
        artist = await service.fetch(RequestIntent(artist_id=123, count=1))
        specified = await service.fetch(RequestIntent(artist_id=123, illust_id=9, count=1))
        assert len(artist) == 1 and artist[0].user_id == 123
        assert specified[0].id == 9

    asyncio.run(run())


def test_candidate_work_selection_is_independent_of_total_image_page_cap():
    async def run():
        client = FakeClient()

        async def search_works(word, target):
            return [Illustration(id=1, x_restrict=0), Illustration(id=2, x_restrict=0)]

        client.search_illustrations = search_works
        settings = Settings.from_mapping({"default_count": 2, "max_count": 1})
        result = await PixivService(client, settings).fetch(
            RequestIntent(keywords="sunset", count=2)
        )
        assert [work.id for work in result] == [1, 2]

    asyncio.run(run())


def test_explicit_candidate_count_is_bounded_independently_of_image_page_cap():
    settings = Settings.from_mapping({"max_count": 1})
    intent = RequestIntent(keywords="sunset", count=10_000).validated(settings)
    assert intent.count == 60
