from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlparse

SEARCH_TARGETS = {"partial_match_for_tags", "exact_match_for_tags", "title_and_caption"}


def as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return default

@dataclass(frozen=True)
class Settings:
    refresh_token: str = ""
    proxy: str = ""
    timeout_seconds: int = 20
    default_count: int = 5
    max_count: int = 10
    enable_natural_language_tool: bool = True
    enable_fallback_command: bool = True
    enable_artist_random: bool = False
    enable_illust_id_send: bool = False
    search_target: str = "partial_match_for_tags"
    send_all_pages: bool = True
    show_work_metadata: bool = True
    show_pixiv_link: bool = True
    filter_r18: bool = True
    filter_r18g: bool = True
    reject_when_safety_check_failed: bool = True
    allow_private_r18: bool = False
    allow_group_r18: bool = False
    cache_ttl_minutes: int = 30
    max_file_size_mb: int = 12
    download_concurrency: int = 3
    cooldown_seconds: int = 30

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> "Settings":
        values = dict(raw or {})
        def integer(name: str, default: int, low: int, high: int) -> int:
            value = values.get(name, default)
            try: value = int(value)
            except (TypeError, ValueError): value = default
            return max(low, min(high, value))
        proxy = str(values.get("proxy", "") or "").strip()
        if proxy:
            parsed = urlparse(proxy)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc: proxy = ""
        target = values.get("search_target", cls.search_target)
        if target not in SEARCH_TARGETS: target = cls.search_target
        return cls(
            refresh_token=str(values.get("refresh_token", "") or "").strip(), proxy=proxy,
            timeout_seconds=integer("timeout_seconds", 20, 5, 120), default_count=integer("default_count", 5, 1, 10), max_count=integer("max_count", 10, 1, 20),
            enable_natural_language_tool=as_bool(values.get("enable_natural_language_tool", True), True), enable_fallback_command=as_bool(values.get("enable_fallback_command", True), True),
            enable_artist_random=as_bool(values.get("enable_artist_random", False), False), enable_illust_id_send=as_bool(values.get("enable_illust_id_send", False), False), search_target=target,
            send_all_pages=as_bool(values.get("send_all_pages", True), True), show_work_metadata=as_bool(values.get("show_work_metadata", True), True), show_pixiv_link=as_bool(values.get("show_pixiv_link", True), True),
            filter_r18=as_bool(values.get("filter_r18", True), True), filter_r18g=as_bool(values.get("filter_r18g", True), True), reject_when_safety_check_failed=as_bool(values.get("reject_when_safety_check_failed", True), True),
            allow_private_r18=as_bool(values.get("allow_private_r18", False), False), allow_group_r18=as_bool(values.get("allow_group_r18", False), False), cache_ttl_minutes=integer("cache_ttl_minutes", 30, 1, 1440),
            max_file_size_mb=integer("max_file_size_mb", 12, 1, 50), download_concurrency=integer("download_concurrency", 3, 1, 5), cooldown_seconds=integer("cooldown_seconds", 30, 0, 3600),
        )

    def public_dict(self) -> dict[str, Any]:
        data = self.__dict__.copy(); data["refresh_token_configured"] = bool(self.refresh_token); data.pop("refresh_token", None); return data