import asyncio
import hashlib
import traceback
from datetime import datetime, timezone
from urllib.parse import parse_qs

import httpx
import pytest

import pixiv_gallery.pixiv_client as client_module
from pixiv_gallery.pixiv_client import PixivAPIError, PixivClient


class FakeTransport:
    def __init__(self):
        self.calls = []

    async def __call__(self, method, url, *, headers=None, params=None, data=None):
        self.calls.append((method, url, headers, params, data))
        if url.endswith("/auth/token"):
            return {
                "response": {
                    "access_token": "access",
                    "refresh_token": "refresh",
                    "user": {"id": 42},
                }
            }
        if url.endswith("/v1/search/illust"):
            return {
                "illusts": [
                    {
                        "id": 1,
                        "title": "Sunset",
                        "user": {"id": 7, "name": "Artist"},
                        "tags": [{"name": "sunset"}],
                        "x_restrict": 0,
                        "meta_single_page": {"original_image_url": "https://img/1.jpg"},
                    }
                ]
            }
        if url.endswith("/v1/user/illusts"):
            return {"illusts": [], "next_url": None}
        if url.endswith("/v1/illust/detail"):
            return {
                "illust": {
                    "id": 9,
                    "title": "Detail",
                    "user": {"id": 7, "name": "Artist"},
                    "tags": [],
                    "x_restrict": 0,
                    "meta_single_page": {"original_image_url": "https://img/9.jpg"},
                }
            }
        raise AssertionError(url)


def test_pixiv_client_auth_and_search():
    async def run():
        transport = FakeTransport()
        client = PixivClient("refresh-token", transport=transport)
        works = await client.search_illustrations("sunset", "partial_match_for_tags")
        assert works[0].id == 1
        assert transport.calls[0][0] == "POST"
        assert transport.calls[1][3]["search_target"] == "partial_match_for_tags"

    asyncio.run(run())


def test_pixiv_client_artist_and_detail():
    async def run():
        transport = FakeTransport()
        client = PixivClient("refresh-token", transport=transport)
        assert await client.user_illustrations(7) == []
        work = await client.illustration_detail(9)
        assert work.title == "Detail"

    asyncio.run(run())


def test_pixiv_client_wraps_missing_token():
    async def run():
        with pytest.raises(PixivAPIError):
            await PixivClient("", transport=FakeTransport()).authenticate()

    asyncio.run(run())


AUTH_URL = "https://oauth.secure.pixiv.net/auth/token"
SEARCH_URL = "https://app-api.pixiv.net/v1/search/illust"
USER_URL = "https://app-api.pixiv.net/v1/user/illusts"
SECRET = "private-token-or-server-payload"


def token_payload(access="access", refresh="rotated-refresh", *, expires=3600, nested=True):
    payload = {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": expires,
        "user": {"id": 42},
    }
    return {"response": payload} if nested else payload


def illust(illust_id=1, **changes):
    item = {
        "id": illust_id,
        "title": "Sunset",
        "user": {"id": 7, "name": "Artist"},
        "tags": [{"name": "sunset"}],
        "x_restrict": 0,
        "type": "illust",
        "meta_single_page": {
            "original_image_url": f"https://i.pximg.net/img-original/{illust_id}.jpg"
        },
        "meta_pages": [],
    }
    item.update(changes)
    return item


@pytest.fixture
def mock_http(monkeypatch):
    real_client = httpx.AsyncClient

    def install(handler):
        transport = httpx.MockTransport(handler)

        def factory(**kwargs):
            return real_client(transport=transport, **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", factory)

    return install


def assert_sanitized(error):
    rendered = "".join(traceback.format_exception(error))
    assert SECRET not in str(error)
    assert SECRET not in rendered
    assert error.__cause__ is None


def test_oauth_form_signing_and_app_headers_reach_real_http_request(mock_http):
    calls = []

    def handler(request):
        calls.append(request)
        if str(request.url) == AUTH_URL:
            return httpx.Response(200, json=token_payload())
        return httpx.Response(200, json={"illusts": [illust()]})

    mock_http(handler)

    async def run():
        client = PixivClient(" refresh-token ")
        works = await client.search_illustrations("blue sky")
        await client.authenticate()
        assert works[0].id == 1

    asyncio.run(run())
    auth_request, api_request, second_auth = calls
    assert auth_request.method == "POST"
    assert parse_qs(auth_request.content.decode()) == {
        "client_id": [PixivClient.CLIENT_ID],
        "client_secret": [PixivClient.CLIENT_SECRET],
        "get_secure_url": ["1"],
        "grant_type": ["refresh_token"],
        "refresh_token": ["refresh-token"],
    }
    assert auth_request.headers["content-type"].startswith("application/x-www-form-urlencoded")
    assert "authorization" not in auth_request.headers
    assert "authorization" not in second_auth.headers
    assert api_request.headers["authorization"] == "Bearer access"
    assert api_request.url.params["word"] == "blue sky"
    for request in calls:
        assert request.headers["app-os"] == "ios"
        assert request.headers["app-os-version"] == "14.6"
        assert request.headers["user-agent"].startswith("PixivIOSApp/7.13.3 (")
    timestamp = auth_request.headers["X-Client-Time"]
    signed_at = datetime.fromisoformat(timestamp)
    assert signed_at.utcoffset().total_seconds() == 0
    assert abs((datetime.now(timezone.utc) - signed_at).total_seconds()) < 10
    assert (
        auth_request.headers["X-Client-Hash"]
        == hashlib.md5((timestamp + PixivClient.HASH_SECRET).encode()).hexdigest()
    )


@pytest.mark.parametrize("nested", [False, True])
def test_modern_and_nested_tokens_rotate_and_remain_cached(nested):
    calls = []

    async def transport(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return token_payload(nested=nested)

    async def run():
        client = PixivClient("old-refresh", transport=transport)
        response = await client.authenticate()
        await client.ensure_authenticated()
        assert response["access_token"] == "access"
        assert response["user"]["id"] == 42
        assert client.access_token == "access"
        assert client.refresh_token == "rotated-refresh"
        assert len(calls) == 1

    asyncio.run(run())


@pytest.mark.parametrize("expires", [120, "120"])
def test_expired_access_token_refreshes_using_rotated_refresh_token(monkeypatch, expires):
    now = [1000.0]
    monkeypatch.setattr(client_module, "monotonic", lambda: now[0], raising=False)
    auth_forms = []

    async def transport(method, url, **kwargs):
        if url == AUTH_URL:
            auth_forms.append(kwargs["data"])
            number = len(auth_forms)
            return token_payload(f"access-{number}", f"refresh-{number}", expires=expires)
        return {"illusts": [illust()]}

    async def run():
        client = PixivClient("initial-refresh", transport=transport)
        await client.search_illustrations("sky")
        now[0] += 10
        await client.search_illustrations("sky")
        assert len(auth_forms) == 1
        now[0] += 111
        await client.search_illustrations("sky")
        assert len(auth_forms) == 2
        assert auth_forms[1]["refresh_token"] == "refresh-1"
        assert client.access_token == "access-2"

    asyncio.run(run())


@pytest.mark.parametrize("entrypoint", ["authenticate", "ensure_authenticated", "search"])
def test_concurrent_authentication_is_coalesced(entrypoint):
    async def run():
        started = asyncio.Event()
        release = asyncio.Event()
        auth_calls = []

        async def transport(method, url, **kwargs):
            if url == AUTH_URL:
                auth_calls.append(kwargs)
                started.set()
                await release.wait()
                return token_payload()
            return {"illusts": [illust()]}

        client = PixivClient("refresh", transport=transport)

        async def invoke():
            if entrypoint == "search":
                return await client.search_illustrations("sky")
            return await getattr(client, entrypoint)()

        tasks = [asyncio.create_task(invoke()) for _ in range(8)]
        await asyncio.wait_for(started.wait(), 2)
        await asyncio.sleep(0)
        release.set()
        await asyncio.wait_for(asyncio.gather(*tasks), 2)
        assert len(auth_calls) == 1
        assert client.access_token == "access"

    asyncio.run(run())


def test_http_401_refreshes_and_retries_exactly_once(mock_http):
    auth_forms = []
    authorizations = []

    def handler(request):
        if str(request.url) == AUTH_URL:
            auth_forms.append(parse_qs(request.content.decode()))
            number = len(auth_forms)
            return httpx.Response(200, json=token_payload(f"access-{number}", f"refresh-{number}"))
        authorizations.append(request.headers["authorization"])
        if len(authorizations) == 1:
            return httpx.Response(401, json={"error": {"message": SECRET}})
        return httpx.Response(200, json={"illusts": [illust()]})

    mock_http(handler)
    works = asyncio.run(PixivClient("initial-refresh").search_illustrations("sky"))
    assert [work.id for work in works] == [1]
    assert authorizations == ["Bearer access-1", "Bearer access-2"]
    assert len(auth_forms) == 2
    assert auth_forms[1]["refresh_token"] == ["refresh-1"]


def test_persistent_http_401_is_bounded_and_sanitized(mock_http, caplog):
    auth_calls = []
    api_calls = []

    def handler(request):
        if str(request.url) == AUTH_URL:
            auth_calls.append(request)
            return httpx.Response(200, json=token_payload(SECRET, SECRET))
        api_calls.append(request)
        return httpx.Response(401, text=SECRET)

    mock_http(handler)
    with pytest.raises(PixivAPIError, match="401") as caught:
        asyncio.run(PixivClient(SECRET).search_illustrations("sky"))
    assert len(auth_calls) == 2
    assert len(api_calls) == 2
    assert_sanitized(caught.value)
    assert SECRET not in caplog.text


def test_late_stale_401_uses_token_already_refreshed_by_another_request(mock_http):
    async def run():
        both_started = asyncio.Event()
        first_finished = asyncio.Event()
        auth_count = 0
        api_headers = []

        async def handler(request):
            nonlocal auth_count
            if str(request.url) == AUTH_URL:
                auth_count += 1
                return httpx.Response(200, json=token_payload(f"access-{auth_count}"))
            header = request.headers["authorization"]
            word = request.url.params["word"]
            api_headers.append((word, header))
            if header == "Bearer access-1":
                if word == "first":
                    await both_started.wait()
                else:
                    both_started.set()
                    await first_finished.wait()
                return httpx.Response(401, text=SECRET)
            return httpx.Response(200, json={"illusts": [illust()]})

        mock_http(handler)
        client = PixivClient("refresh")
        await client.authenticate()
        first = asyncio.create_task(client.search_illustrations("first"))
        first.add_done_callback(lambda task: first_finished.set())
        second = asyncio.create_task(client.search_illustrations("second"))
        results = await asyncio.wait_for(asyncio.gather(first, second, return_exceptions=True), 2)
        assert all(isinstance(result, list) for result in results), results
        assert auth_count == 2
        assert len(api_headers) == 4
        assert api_headers[-1] == ("second", "Bearer access-2")

    asyncio.run(run())


def test_callable_transport_http_status_errors_follow_the_same_retry_policy():
    auth_calls = []
    api_calls = []

    async def transport(method, url, **kwargs):
        if url == AUTH_URL:
            auth_calls.append(kwargs)
            return token_payload(f"access-{len(auth_calls)}")
        api_calls.append(kwargs)
        if len(api_calls) == 1:
            request = httpx.Request(method, url)
            response = httpx.Response(401, request=request, text=SECRET)
            raise httpx.HTTPStatusError(SECRET, request=request, response=response)
        return {"illusts": [illust()]}

    works = asyncio.run(PixivClient("refresh", transport=transport).search_illustrations("sky"))
    assert [work.id for work in works] == [1]
    assert len(auth_calls) == 2
    assert len(api_calls) == 2


@pytest.mark.parametrize("status", [301, 302, 307, 308, 400, 403, 404, 429, 500])
def test_http_errors_do_not_follow_redirects_or_leak_server_body(mock_http, status):
    calls = []

    def handler(request):
        calls.append(request)
        if str(request.url) == AUTH_URL:
            return httpx.Response(200, json=token_payload(SECRET, SECRET))
        return httpx.Response(
            status, text=SECRET, headers={"Location": f"https://evil.test/{SECRET}"}
        )

    mock_http(handler)
    with pytest.raises(PixivAPIError) as caught:
        asyncio.run(PixivClient(SECRET).search_illustrations("sky"))
    assert len(calls) == 2
    assert_sanitized(caught.value)


@pytest.mark.parametrize("at_auth", [True, False])
@pytest.mark.parametrize(
    "error_type", [httpx.ConnectError, httpx.ReadTimeout, OSError, RuntimeError]
)
def test_network_errors_are_sanitized_at_both_request_boundaries(mock_http, at_auth, error_type):
    calls = []

    def handler(request):
        calls.append(request)
        if not at_auth and str(request.url) == AUTH_URL:
            return httpx.Response(200, json=token_payload(SECRET, SECRET))
        raise error_type(SECRET)

    mock_http(handler)
    with pytest.raises(PixivAPIError) as caught:
        asyncio.run(PixivClient(SECRET).search_illustrations("sky"))
    assert len(calls) == (1 if at_auth else 2)
    assert_sanitized(caught.value)


@pytest.mark.parametrize(
    "api_payload",
    [
        {"error": {"message": SECRET}},
        {"error": {}},
        {"has_error": True, "errors": {"system": {"message": SECRET}}},
        {"errors": {"system": {"message": SECRET}}},
        [],
        None,
    ],
)
def test_http_200_api_errors_are_not_empty_results(mock_http, api_payload):
    def handler(request):
        if str(request.url) == AUTH_URL:
            return httpx.Response(200, json=token_payload())
        return (
            httpx.Response(200, content=b"null")
            if api_payload is None
            else httpx.Response(200, json=api_payload)
        )

    mock_http(handler)
    with pytest.raises(PixivAPIError) as caught:
        asyncio.run(PixivClient("refresh").search_illustrations("sky"))
    assert_sanitized(caught.value)


def test_invalid_json_has_no_raw_exception_chain(mock_http):
    def handler(request):
        return httpx.Response(200, content=f"not json: {SECRET}".encode())

    mock_http(handler)
    with pytest.raises(PixivAPIError) as caught:
        asyncio.run(PixivClient(SECRET).authenticate())
    assert_sanitized(caught.value)


@pytest.mark.parametrize(
    "response",
    [
        {"access_token": 123},
        {"access_token": ""},
        {"access_token": "bad\r\nheader"},
        {"access_token": "access", "refresh_token": [SECRET]},
        {"access_token": "access", "expires_in": SECRET},
        {"access_token": "access", "expires_in": float("inf")},
        {"access_token": "access", "expires_in": float("nan")},
        {"access_token": "access", "expires_in": -5},
        {"access_token": "access", "expires_in": False},
        {"access_token": "access", "error": {"message": SECRET}},
    ],
)
def test_malformed_authentication_does_not_install_partial_credentials(response):
    async def transport(method, url, **kwargs):
        return {"response": response}

    async def run():
        client = PixivClient("original-refresh", transport=transport)
        with pytest.raises(PixivAPIError) as caught:
            await client.authenticate()
        assert client.access_token is None
        assert client.refresh_token == "original-refresh"
        assert_sanitized(caught.value)

    asyncio.run(run())


def test_cancellation_is_not_wrapped_as_a_network_failure():
    async def transport(method, url, **kwargs):
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(PixivClient("refresh", transport=transport).authenticate())


def payload_client(payload):
    async def transport(method, url, **kwargs):
        return token_payload() if url == AUTH_URL else payload

    return PixivClient("refresh", transport=transport)


async def fetch_listing(client, kind, **kwargs):
    if kind == "search":
        return await client.search_illustrations("blue sky", **kwargs)
    return await client.user_illustrations(7, **kwargs)


def test_artist_request_uses_real_endpoint_and_query_parameters(mock_http):
    calls = []

    def handler(request):
        calls.append(request)
        if str(request.url) == AUTH_URL:
            return httpx.Response(200, json=token_payload())
        return httpx.Response(200, json={"illusts": [illust()]})

    mock_http(handler)
    works = asyncio.run(PixivClient("refresh").user_illustrations(7))
    assert [work.id for work in works] == [1]
    assert calls[1].method == "GET"
    assert str(calls[1].url.copy_with(query=None)) == USER_URL
    assert dict(calls[1].url.params) == {"user_id": "7", "type": "illust", "filter": "for_ios"}


@pytest.mark.parametrize("kind", ["search", "user"])
def test_pagination_follows_cursor_and_deduplicates_in_order(mock_http, kind):
    endpoint = SEARCH_URL if kind == "search" else USER_URL
    next_url = f"{endpoint}?offset=30&word=blue%20sky&filter=for_ios"
    api_requests = []

    def handler(request):
        if str(request.url) == AUTH_URL:
            return httpx.Response(200, json=token_payload())
        api_requests.append(request)
        if len(api_requests) == 1:
            return httpx.Response(
                200, json={"illusts": [illust(1), illust(2)], "next_url": next_url}
            )
        assert str(request.url) == next_url
        return httpx.Response(200, json={"illusts": [illust(2), illust(3)], "next_url": None})

    mock_http(handler)
    works = asyncio.run(fetch_listing(PixivClient("refresh"), kind))
    assert [work.id for work in works] == [1, 2, 3]
    assert len(api_requests) == 2
    assert all(request.headers["authorization"] == "Bearer access" for request in api_requests)


@pytest.mark.parametrize("kind", ["search", "user"])
def test_pagination_stops_at_five_pages_even_if_server_always_supplies_a_cursor(kind):
    pages = []
    endpoint = SEARCH_URL if kind == "search" else USER_URL

    async def transport(method, url, **kwargs):
        if url == AUTH_URL:
            return token_payload()
        pages.append(url)
        return {"illusts": [illust(len(pages))], "next_url": f"{endpoint}?offset={len(pages)}"}

    works = asyncio.run(fetch_listing(PixivClient("refresh", transport=transport), kind))
    assert [work.id for work in works] == [1, 2, 3, 4, 5]
    assert len(pages) == 5


@pytest.mark.parametrize("kind", ["search", "user"])
@pytest.mark.parametrize("limit, expected, page_count", [(None, 60, 2), (3, 3, 1), (500, 200, 5)])
def test_pagination_limits_default_sixty_and_maximum_two_hundred(kind, limit, expected, page_count):
    pages = []
    endpoint = SEARCH_URL if kind == "search" else USER_URL

    async def transport(method, url, **kwargs):
        if url == AUTH_URL:
            return token_payload()
        pages.append(url)
        start = (len(pages) - 1) * 45 + 1
        return {
            "illusts": [illust(number) for number in range(start, start + 45)],
            "next_url": f"{endpoint}?offset={len(pages) * 45}",
        }

    options = {} if limit is None else {"limit": limit}
    works = asyncio.run(fetch_listing(PixivClient("refresh", transport=transport), kind, **options))
    assert [work.id for work in works] == list(range(1, expected + 1))
    assert len(pages) == page_count


@pytest.mark.parametrize("kind", ["search", "user"])
def test_duplicate_and_malformed_candidates_still_consume_the_scan_budget(kind):
    calls = []
    endpoint = SEARCH_URL if kind == "search" else USER_URL

    async def transport(method, url, **kwargs):
        if url == AUTH_URL:
            return token_payload()
        calls.append(url)
        return {
            "illusts": [illust(1)] * 100 + [None] * 100 + [illust(2)],
            "next_url": f"{endpoint}?offset=201",
        }

    works = asyncio.run(fetch_listing(PixivClient("refresh", transport=transport), kind))
    assert [work.id for work in works] == [1]
    assert len(calls) == 1


@pytest.mark.parametrize("kind", ["search", "user"])
@pytest.mark.parametrize("limit", [0, -1])
def test_nonpositive_candidate_limit_does_not_authenticate_or_request(kind, limit):
    calls = []

    async def transport(method, url, **kwargs):
        calls.append(url)
        return token_payload()

    works = asyncio.run(
        fetch_listing(PixivClient("refresh", transport=transport), kind, limit=limit)
    )
    assert works == []
    assert calls == []


@pytest.mark.parametrize("kind", ["search", "user"])
def test_repeated_next_url_terminates_without_fetching_the_same_page_again(kind):
    calls = []
    endpoint = SEARCH_URL if kind == "search" else USER_URL
    next_url = f"{endpoint}?offset=1"

    async def transport(method, url, **kwargs):
        if url == AUTH_URL:
            return token_payload()
        calls.append(url)
        return {"illusts": [illust(1)], "next_url": next_url}

    works = asyncio.run(fetch_listing(PixivClient("refresh", transport=transport), kind))
    assert [work.id for work in works] == [1]
    assert len(calls) == 2


@pytest.mark.parametrize(
    "next_url",
    [
        "http://app-api.pixiv.net/v1/search/illust?offset=1",
        "https://evil.test/v1/search/illust?offset=1",
        "https://app-api.pixiv.net.evil.test/v1/search/illust",
        "https://app-api.pixiv.net@evil.test/v1/search/illust",
        "https://user:password@app-api.pixiv.net/v1/search/illust",
        "https://app-api.pixiv.net:8443/v1/search/illust",
        "https://app-api.pixiv.net:80/v1/search/illust",
        "https://app-api.pixiv.net./v1/search/illust",
        "//app-api.pixiv.net/v1/search/illust?offset=1",
        "/v1/search/illust?offset=1",
        "https://app-api.pixiv.net/v1/illust/detail?illust_id=1",
        "https://app-api.pixiv.net/v1/user/illusts?user_id=7",
        "https://app-api.pixiv.net/v1/search/illust/../illust/detail",
        "https://app-api.pixiv.net/v1/search/%69llust",
        "https://app-api.pixiv.net/v1/search/illust#fragment",
        "https://app-api.pixiv.net/v1/search/illust\r\n?offset=1",
        " https://app-api.pixiv.net/v1/search/illust",
        "https://[invalid/v1/search/illust",
        {"url": SECRET},
        123,
    ],
)
def test_untrusted_next_urls_are_rejected_before_any_request(mock_http, next_url):
    calls = []

    def handler(request):
        calls.append(request)
        if str(request.url) == AUTH_URL:
            return httpx.Response(200, json=token_payload(SECRET, SECRET))
        return httpx.Response(200, json={"illusts": [illust()], "next_url": next_url})

    mock_http(handler)
    with pytest.raises(PixivAPIError) as caught:
        asyncio.run(PixivClient(SECRET).search_illustrations("sky"))
    assert len(calls) == 2
    assert_sanitized(caught.value)


def test_artist_cursor_cannot_switch_to_a_different_endpoint():
    client = payload_client({"illusts": [], "next_url": SEARCH_URL})
    with pytest.raises(PixivAPIError):
        asyncio.run(client.user_illustrations(7))


def test_pagination_errors_on_later_pages_do_not_become_partial_success(mock_http):
    api_calls = []

    def handler(request):
        if str(request.url) == AUTH_URL:
            return httpx.Response(200, json=token_payload())
        api_calls.append(request)
        if len(api_calls) == 1:
            return httpx.Response(
                200, json={"illusts": [illust()], "next_url": f"{SEARCH_URL}?offset=1"}
            )
        return httpx.Response(200, json={"error": {"message": SECRET}})

    mock_http(handler)
    with pytest.raises(PixivAPIError) as caught:
        asyncio.run(PixivClient("refresh").search_illustrations("sky"))
    assert len(api_calls) == 2
    assert_sanitized(caught.value)


@pytest.mark.parametrize("payload", [{}, {"illusts": None}, {"illusts": {}}, {"illusts": SECRET}])
@pytest.mark.parametrize("kind", ["search", "user"])
def test_malformed_collection_envelopes_are_errors_not_empty_results(payload, kind):
    with pytest.raises(PixivAPIError) as caught:
        asyncio.run(fetch_listing(payload_client(payload), kind))
    assert_sanitized(caught.value)


@pytest.mark.parametrize(
    "restriction", [None, "", "0", "1", "garbage", False, True, [], {}, 0.0, -1, 3]
)
def test_malformed_safety_restriction_is_unknown_not_safe(restriction):
    client = payload_client({"illusts": [illust(x_restrict=restriction)]})
    works = asyncio.run(client.search_illustrations("sky"))
    assert len(works) == 1
    assert works[0].x_restrict is None


def test_missing_safety_metadata_and_type_are_not_fabricated():
    item = {"id": 1}
    works = asyncio.run(payload_client({"illusts": [item]}).search_illustrations("sky"))
    work = works[0]
    assert work.x_restrict is None
    assert work.type == ""
    assert work.image_urls == []
    assert work.raw == item
    assert "x_restrict" not in item


@pytest.mark.parametrize("restriction", [0, 1, 2])
def test_known_safety_restrictions_are_preserved(restriction):
    works = asyncio.run(
        payload_client({"illusts": [illust(x_restrict=restriction)]}).search_illustrations("sky")
    )
    assert works[0].x_restrict == restriction


def test_deleted_and_malformed_work_entries_are_skipped_without_losing_valid_entries():
    entries = [
        None,
        "deleted",
        {},
        [],
        {"id": None},
        {"id": "bad"},
        {"id": True},
        {"id": -1},
        {"id": 0},
        {"id": 1.5},
        illust(8, visible=False),
        illust(9, is_deleted=True),
        illust("7"),
        illust(10),
    ]
    works = asyncio.run(payload_client({"illusts": entries}).search_illustrations("sky"))
    assert [work.id for work in works] == [7, 10]


def test_malformed_optional_fields_neither_crash_nor_invent_metadata_or_urls():
    item = illust(
        user=[SECRET],
        title={"text": SECRET},
        type=["illust"],
        tags=[None, "sunset", {}, {"name": 5}, {"name": "valid"}],
        meta_single_page={"original_image_url": {"url": SECRET}},
        meta_pages=[
            None,
            [],
            {"image_urls": []},
            {"image_urls": {"original": 123}},
            {"image_urls": {"original": "javascript:alert(1)"}},
            {"image_urls": {"original": "https://i.pximg.net/real.jpg"}},
        ],
        image_urls={"large": "https://i.pximg.net/not-an-original.jpg"},
    )
    work = asyncio.run(payload_client({"illusts": [item]}).search_illustrations("sky"))[0]
    assert work.user_id is None
    assert work.user_name == ""
    assert work.title == ""
    assert work.type == ""
    assert work.tags == ["valid"]
    assert work.image_urls == ["https://i.pximg.net/real.jpg"]


@pytest.mark.parametrize(
    "fields",
    [
        {"user": None, "tags": None, "meta_single_page": "bad", "meta_pages": 1},
        {"user": {"id": [], "name": 3}, "tags": "sunset", "meta_single_page": [], "meta_pages": {}},
    ],
)
def test_noncontainer_optional_fields_are_normalized_without_fallback_urls(fields):
    work = asyncio.run(payload_client({"illusts": [illust(**fields)]}).search_illustrations("sky"))[
        0
    ]
    assert work.user_id is None
    assert work.user_name == ""
    assert work.tags == []
    assert work.image_urls == []


def test_multipage_originals_keep_their_order_and_are_deduplicated():
    item = illust(
        meta_pages=[
            {"image_urls": {"original": "https://i.pximg.net/img-original/1.jpg"}},
            {"image_urls": {"original": "https://i.pximg.net/img-original/2.jpg"}},
            {"image_urls": {"original": "https://i.pximg.net/img-original/2.jpg"}},
        ]
    )
    work = asyncio.run(payload_client({"illust": item}).illustration_detail(1))
    assert work.image_urls == [
        "https://i.pximg.net/img-original/1.jpg",
        "https://i.pximg.net/img-original/2.jpg",
    ]


@pytest.mark.parametrize("item", [None, {}, {"id": "bad"}, "deleted", illust(1, visible=False)])
def test_missing_deleted_or_malformed_detail_is_a_sanitized_error(item):
    with pytest.raises(PixivAPIError) as caught:
        asyncio.run(payload_client({"illust": item}).illustration_detail(1))
    assert_sanitized(caught.value)


def test_zero_expiry_is_one_authentication_per_operation_not_a_refresh_loop():
    calls = []

    async def transport(method, url, **kwargs):
        calls.append(url)
        return token_payload(expires=0) if url == AUTH_URL else {"illusts": [illust()]}

    works = asyncio.run(PixivClient("refresh", transport=transport).search_illustrations("sky"))
    assert [work.id for work in works] == [1]
    assert calls == [AUTH_URL, SEARCH_URL]


def test_unreasonably_long_server_expiry_is_bounded(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(client_module, "monotonic", lambda: now[0])
    calls = []

    async def transport(method, url, **kwargs):
        calls.append(url)
        return token_payload(expires=1e300)

    async def run():
        client = PixivClient("refresh", transport=transport)
        await client.ensure_authenticated()
        now[0] += 86401
        await client.ensure_authenticated()
        assert len(calls) == 2

    asyncio.run(run())
