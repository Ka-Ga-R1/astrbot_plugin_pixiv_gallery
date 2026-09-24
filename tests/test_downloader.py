from pathlib import Path
from pixiv_gallery.downloader import ImageDownloader, DownloadError

def test_downloader_rejects_non_https():
    downloader=ImageDownloader(max_size_bytes=100)
    try: downloader.validate_url('ftp://example.com/a.jpg')
    except DownloadError: return
    raise AssertionError('expected rejection')

def test_downloader_rejects_oversized_payload(tmp_path):
    downloader=ImageDownloader(max_size_bytes=3)
    try: downloader.write_bytes(b'1234', tmp_path/'a.jpg')
    except DownloadError: return
    raise AssertionError('expected rejection')
