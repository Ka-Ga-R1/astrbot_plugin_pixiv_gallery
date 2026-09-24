from pixiv_gallery.request_parser import parse_pixiv_request

def test_parser_extracts_illust_url_with_priority():
    intent = parse_pixiv_request('发送 https://www.pixiv.net/artworks/123456789 3张')
    assert intent.illust_id == 123456789
    assert intent.count == 3

def test_parser_extracts_artist_id():
    intent = parse_pixiv_request('/pixiv artist 98765 2')
    assert intent.artist_id == 98765
    assert intent.count == 2

def test_parser_keeps_tag_query():
    intent = parse_pixiv_request('/pixiv 黄昏 海边')
    assert intent.keywords == '黄昏 海边'
