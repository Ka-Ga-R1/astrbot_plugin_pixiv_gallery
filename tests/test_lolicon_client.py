import asyncio

import httpx
import pytest

from pixiv_gallery.lolicon_client import LoliconAPIError, LoliconCandidate, LoliconClient


def test_lolicon_queries_sfw_one_result_and_repeated_tags():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "error": "",
                "data": [
                    {
                        "uid": 1893126,
                        "pid": 128997681,
                        "urls": {"original": "https://i.pixiv.re/not-for-download.jpg"},
                    }
                ],
            },
        )

    async def run():
        client = LoliconClient(transport=httpx.MockTransport(handler))
        result = await client.find_random(["星空", "青髪"])
        assert result == LoliconCandidate(uid=1893126, pid=128997681)
        assert not hasattr(result, "proxy_url")
        params = dict(requests[0].url.params.multi_items())
        assert params["r18"] == "0"
        assert params["num"] == "1"
        assert requests[0].url.params.get_list("tag") == ["星空", "青髪"]

    asyncio.run(run())


def test_lolicon_empty_data_returns_none():
    async def handler(request):
        return httpx.Response(200, json={"error": "", "data": []})

    async def run():
        client = LoliconClient(transport=httpx.MockTransport(handler))
        assert await client.find_random(["星空"]) is None

    asyncio.run(run())


@pytest.mark.parametrize(
    "payload",
    [
        {"error": "private server details", "data": []},
        {"error": "", "data": [{"uid": "bad", "pid": 12}]},
        {"error": "", "data": {}},
    ],
)
def test_lolicon_bad_responses_are_sanitized(payload):
    async def handler(request):
        return httpx.Response(200, json=payload)

    async def run():
        client = LoliconClient(transport=httpx.MockTransport(handler))
        with pytest.raises(LoliconAPIError) as error:
            await client.find_random(["星空"])
        assert "private server details" not in str(error.value)

    asyncio.run(run())


def test_lolicon_http_errors_do_not_expose_response_bodies():
    async def handler(request):
        return httpx.Response(429, text="private response body")

    async def run():
        client = LoliconClient(transport=httpx.MockTransport(handler))
        with pytest.raises(LoliconAPIError) as error:
            await client.find_random(["星空"])
        assert error.value.status_code == 429
        assert "private response body" not in str(error.value)

    asyncio.run(run())
