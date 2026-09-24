import asyncio

import httpx
import pytest

from pixiv_gallery.downloader import DownloadError, ImageDownloader


def test_downloader_rejects_non_https():
    downloader = ImageDownloader(max_size_bytes=100)
    try:
        downloader.validate_url("ftp://example.com/a.jpg")
    except DownloadError:
        return
    raise AssertionError("expected rejection")


def test_downloader_rejects_oversized_payload(tmp_path):
    downloader = ImageDownloader(max_size_bytes=3)
    try:
        downloader.write_bytes(b"1234", tmp_path / "a.jpg")
    except DownloadError:
        return
    raise AssertionError("expected rejection")


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.test/a.jpg",
        "http://i.pximg.net/a.jpg",
        "https://i.pximg.net.evil.test/a.jpg",
        "https://user:password@i.pximg.net/a.jpg",
        "https://i.pximg.net:8443/a.jpg",
        "https://127.0.0.1/a.jpg",
    ],
)
def test_downloader_only_accepts_trusted_pixiv_https_origins(url):
    with pytest.raises(DownloadError):
        ImageDownloader().validate_url(url)


def test_downloader_streaming_enforces_limits_without_leaving_partial_file(tmp_path):
    async def check():
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200, headers={"content-type": "image/jpeg"}, content=b"\xff\xd8\xff" + b"x" * 30
            )
        )
        target = tmp_path / "image.jpg"
        downloader = ImageDownloader(max_size_bytes=10, transport=transport)
        with pytest.raises(DownloadError):
            await downloader.download("https://i.pximg.net/test.jpg", target)
        assert not target.exists()

    asyncio.run(check())


def test_downloader_rejects_redirect_to_private_or_foreign_host_before_request(tmp_path):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})

    async def check():
        downloader = ImageDownloader(transport=httpx.MockTransport(handler))
        with pytest.raises(DownloadError):
            await downloader.download("https://i.pximg.net/test.jpg", tmp_path / "test.jpg")
        assert len(calls) == 1

    asyncio.run(check())


@pytest.mark.parametrize(
    "headers,content",
    [
        ({"content-type": "text/html"}, b"<html>error</html>"),
        ({"content-type": "image/jpeg"}, b"<html>error</html>"),
        ({"content-type": "image/jpeg", "content-length": "nonsense"}, b"\xff\xd8\xff"),
    ],
)
def test_downloader_rejects_nonimages_and_invalid_headers(headers, content, tmp_path):
    async def check():
        downloader = ImageDownloader(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, headers=headers, content=content)
            )
        )
        with pytest.raises(DownloadError):
            await downloader.download("https://i.pximg.net/test.jpg", tmp_path / "test.jpg")
        assert not (tmp_path / "test.jpg").exists()

    asyncio.run(check())


def test_download_concurrency_limit_is_global_to_downloader_and_timeout_applies(tmp_path):
    async def check():
        active = peak = 0

        async def handler(request):
            nonlocal active, peak
            assert request.extensions["timeout"]["read"] == 7
            assert request.headers["referer"].startswith("https://")
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1
            return httpx.Response(
                200, headers={"content-type": "image/jpeg"}, content=b"\xff\xd8\xfftest"
            )

        downloader = ImageDownloader(
            concurrency=2, timeout=7, transport=httpx.MockTransport(handler)
        )
        paths = await asyncio.gather(
            *(
                downloader.download(f"https://i.pximg.net/{i}.jpg", tmp_path / f"{i}.jpg")
                for i in range(6)
            )
        )
        assert peak == 2
        assert all(path.read_bytes() == b"\xff\xd8\xfftest" for path in paths)

    asyncio.run(check())


def test_downloader_rejects_even_empty_userinfo():
    with pytest.raises(DownloadError):
        ImageDownloader().validate_url("https://@i.pximg.net/a.jpg")
