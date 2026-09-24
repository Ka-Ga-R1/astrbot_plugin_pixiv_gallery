"""Markup contracts; executable Bridge interactions live in page_smoke.mjs."""

from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
HTML = (ROOT / "pages" / "pixiv-gallery" / "index.html").read_text(encoding="utf-8")


class PageMarkup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.text.append(data)


PAGE = PageMarkup()
PAGE.feed(HTML)
SETTINGS = {
    "refresh_token": "password",
    "proxy": "text",
    "timeout_seconds": "number",
    "default_count": "number",
    "max_count": "number",
    "enable_natural_language_tool": "checkbox",
    "enable_fallback_command": "checkbox",
    "enable_artist_random": "checkbox",
    "enable_illust_id_send": "checkbox",
    "search_target": "select",
    "send_all_pages": "checkbox",
    "show_work_metadata": "checkbox",
    "show_pixiv_link": "checkbox",
    "filter_r18": "checkbox",
    "filter_r18g": "checkbox",
    "reject_when_safety_check_failed": "checkbox",
    "allow_private_r18": "checkbox",
    "allow_group_r18": "checkbox",
    "cache_ttl_minutes": "number",
    "max_file_size_mb": "number",
    "download_concurrency": "number",
    "cooldown_seconds": "number",
}


def setting(name):
    matches = [(tag, attrs) for tag, attrs in PAGE.elements if attrs.get("data-setting") == name]
    assert len(matches) == 1, f"{name} needs exactly one bound control"
    return matches[0]


@pytest.mark.parametrize("name,kind", SETTINGS.items())
def test_every_setting_has_an_editable_named_control(name, kind):
    tag, attrs = setting(name)
    assert (
        (tag == "select")
        if kind == "select"
        else (tag == "input" and attrs.get("type", "text") == kind)
    )
    assert "readonly" not in attrs
    assert "disabled" not in attrs
    labels = [item.get("for") for element, item in PAGE.elements if element == "label"]
    assert attrs.get("aria-label") or attrs.get("id") in labels, f"{name} needs an accessible name"


@pytest.mark.parametrize(
    "name,minimum,maximum",
    [
        ("timeout_seconds", 5, 120),
        ("default_count", 1, 10),
        ("max_count", 1, 20),
        ("cache_ttl_minutes", 1, 1440),
        ("max_file_size_mb", 1, 50),
        ("download_concurrency", 1, 5),
        ("cooldown_seconds", 0, 3600),
    ],
)
def test_numeric_controls_declare_backend_limits(name, minimum, maximum):
    _, attrs = setting(name)
    assert int(attrs["min"]) == minimum
    assert int(attrs["max"]) == maximum
    assert attrs.get("step", "1") == "1"


@pytest.mark.parametrize("name", ["filter_r18", "filter_r18g", "reject_when_safety_check_failed"])
def test_safety_controls_default_to_rejection(name):
    assert "checked" in setting(name)[1]


@pytest.mark.parametrize("name", ["allow_private_r18", "allow_group_r18"])
def test_adult_scope_permissions_default_to_denied(name):
    assert "checked" not in setting(name)[1]


def test_refresh_token_is_never_prefilled():
    _, attrs = setting("refresh_token")
    assert attrs.get("value", "") == ""
    assert attrs["autocomplete"] == "new-password"


def test_control_ids_are_unique_and_labels_point_to_real_controls():
    ids = [attrs["id"] for _, attrs in PAGE.elements if "id" in attrs]
    assert len(ids) == len(set(ids))
    assert all(
        attrs["for"] in ids for tag, attrs in PAGE.elements if tag == "label" and "for" in attrs
    )


def test_cache_clear_and_runtime_fields_are_present_without_static_success():
    by_id = {attrs["id"]: (tag, attrs) for tag, attrs in PAGE.elements if "id" in attrs}
    assert by_id["clear-cache"][0] == "button"
    for name in ("cache-entries", "cache-hits", "cache-misses", "stats-date", "runtime-status"):
        assert name in by_id
    for _, attrs in PAGE.elements:
        classes = attrs.get("class", "").split()
        if "status-badge" in classes:
            assert "success" not in classes, "Runtime success must come from Bridge responses"
        if "readiness-step" in classes:
            assert "done" not in classes, (
                "A static page cannot prove tool registration or connectivity"
            )


def test_page_no_longer_disclaims_implemented_settings():
    text = " ".join(PAGE.text)
    for obsolete in (
        "未接入能力",
        "未实现用户级限流",
        "未启用应用层缓存",
        "会话范围开关暂不可用",
        "尚未接入私聊",
        "Plugin ready",
    ):
        assert obsolete not in text


def test_ui_release_version_is_0_1_2():
    # Metadata is owned and checked by the release coordinator, not this UI task.
    assert "v0.1.2" in " ".join(PAGE.text)
    assert "v0.1.1" not in " ".join(PAGE.text)
