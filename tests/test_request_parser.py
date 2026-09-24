import pytest

from pixiv_gallery.request_parser import parse_pixiv_request


def test_parser_extracts_illust_url_with_priority():
    intent = parse_pixiv_request("\u53d1\u9001 https://www.pixiv.net/artworks/123456789 3\u5f20")
    assert intent.illust_id == 123456789
    assert intent.count == 3


def test_parser_extracts_artist_id():
    intent = parse_pixiv_request("/pixiv artist 98765 2")
    assert intent.artist_id == 98765
    assert intent.count == 2


def test_parser_keeps_tag_query():
    intent = parse_pixiv_request("/pixiv \u9ec4\u660f \u6d77\u8fb9")
    assert intent.keywords == "\u9ec4\u660f \u6d77\u8fb9"


def test_parser_supports_chinese_illustration_ids_and_unspaced_counts():
    assert parse_pixiv_request("\u53d1\u9001 Pixiv \u63d2\u753b 123456789").illust_id == 123456789
    assert parse_pixiv_request("\u627e3\u5f20\u661f\u7a7a\u63d2\u753b").count == 3


def test_parser_preserves_default_count_and_never_consumes_ids_as_counts():
    assert parse_pixiv_request("\u661f\u7a7a").count is None
    assert parse_pixiv_request("\u753b\u5e08 12").artist_id == 12
    assert parse_pixiv_request("\u753b\u5e08 12").count is None


def test_parser_accepts_localized_and_legacy_pixiv_links_not_lookalike_hosts():
    assert parse_pixiv_request("https://www.pixiv.net/en/artworks/123").illust_id == 123
    assert (
        parse_pixiv_request(
            "https://www.pixiv.net/member_illust.php?mode=medium&illust_id=123"
        ).illust_id
        == 123
    )
    assert parse_pixiv_request("https://evil.test/pixiv.net/artworks/123").illust_id is None
    assert parse_pixiv_request("https://www.pixiv.net/users/123").artist_id == 123


@pytest.mark.parametrize(
    "text",
    [
        "illustration id abc",
        "https://www.pixiv.net/artworks/not-a-number",
        "https://www.pixiv.net/member_illust.php?illust_id=abc",
        "artist id abc",
        "https://www.pixiv.net/users/not-a-number",
    ],
)
def test_parser_rejects_malformed_explicit_ids(text):
    with pytest.raises(ValueError, match="ID"):
        parse_pixiv_request(text)
