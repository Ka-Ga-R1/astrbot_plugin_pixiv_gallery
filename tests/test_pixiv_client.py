import asyncio
import pytest
from pixiv_gallery.pixiv_client import PixivClient, PixivAPIError

class FakeTransport:
    def __init__(self): self.calls=[]
    async def __call__(self, method, url, *, headers=None, params=None, data=None):
        self.calls.append((method,url,headers,params,data))
        if url.endswith('/auth/token'): return {"response":{"access_token":"access","refresh_token":"refresh","user":{"id":42}}}
        if url.endswith('/v1/search/illust'): return {"illusts":[{"id":1,"title":"Sunset","user":{"id":7,"name":"Artist"},"tags":[{"name":"sunset"}],"x_restrict":0,"meta_single_page":{"original_image_url":"https://img/1.jpg"}}]}
        if url.endswith('/v1/user/7/illusts'): return {"illusts":[],"next_url":None}
        if url.endswith('/v1/illust/detail'): return {"illust":{"id":9,"title":"Detail","user":{"id":7,"name":"Artist"},"tags":[],"x_restrict":0,"meta_single_page":{"original_image_url":"https://img/9.jpg"}}}
        raise AssertionError(url)

def test_pixiv_client_auth_and_search():
    async def run():
        transport=FakeTransport(); client=PixivClient('refresh-token', transport=transport)
        works=await client.search_illustrations('sunset', 'partial_match_for_tags')
        assert works[0].id == 1
        assert transport.calls[0][0] == 'POST'
        assert transport.calls[1][3]['search_target'] == 'partial_match_for_tags'
    asyncio.run(run())

def test_pixiv_client_artist_and_detail():
    async def run():
        transport=FakeTransport(); client=PixivClient('refresh-token', transport=transport)
        assert await client.user_illustrations(7) == []
        work=await client.illustration_detail(9)
        assert work.title == 'Detail'
    asyncio.run(run())

def test_pixiv_client_wraps_missing_token():
    async def run():
        with pytest.raises(PixivAPIError): await PixivClient('', transport=FakeTransport()).authenticate()
    asyncio.run(run())
