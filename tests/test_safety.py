import asyncio

import pytest

from pixiv_gallery.config import Settings
from pixiv_gallery.models import Illustration
from pixiv_gallery.safety import policy_allows
from pixiv_gallery.service import PixivService, RequestIntent, SafetyRejectedError


@pytest.mark.parametrize("restricted", [1, 2])
def test_enabled_global_filters_cannot_be_overridden_by_context_permission(restricted):
    settings = Settings.from_mapping({"allow_private_r18": True, "allow_group_r18": True})
    work = Illustration(id=1, x_restrict=restricted)
    assert not policy_allows(work, settings, is_private=True)
    assert not policy_allows(work, settings, is_private=False)


@pytest.mark.parametrize("private", [True, False, None])
def test_disabling_global_filter_still_requires_the_actual_context_permission(private):
    settings = Settings.from_mapping({"filter_r18": False, "allow_private_r18": True})
    work = Illustration(id=1, x_restrict=1)
    assert policy_allows(work, settings, is_private=private) is (private is True)


@pytest.mark.parametrize("restriction", [None, -1, 3, "bad", True])
def test_unknown_safety_is_rejected_by_default(restriction):
    assert not policy_allows(
        Illustration(id=1, x_restrict=restriction), Settings(), is_private=True
    )


def test_unknown_safety_can_only_be_allowed_by_explicit_fail_open_setting():
    settings = Settings.from_mapping({"reject_when_safety_check_failed": False})
    assert policy_allows(Illustration(id=1, x_restrict=None), settings, is_private=True)


@pytest.mark.parametrize("tag", ["R-18", "r18", "R-18G", "r18g"])
def test_restricted_tags_cannot_be_hidden_by_a_safe_numeric_flag(tag):
    assert not policy_allows(
        Illustration(id=1, tags=[tag], x_restrict=0), Settings(), is_private=True
    )


def test_id_and_search_use_the_same_content_policy_and_no_empty_success():
    class Client:
        async def illustration_detail(self, illust_id):
            return Illustration(id=illust_id, x_restrict=1)

        async def search_illustrations(self, word, target):
            return [Illustration(id=1, x_restrict=1)]

    async def check():
        service = PixivService(Client(), Settings.from_mapping({"enable_illust_id_send": True}))
        for intent in [RequestIntent(illust_id=1), RequestIntent(keywords="sky")]:
            with pytest.raises(SafetyRejectedError):
                await service.fetch(intent, is_private=True)

    asyncio.run(check())
