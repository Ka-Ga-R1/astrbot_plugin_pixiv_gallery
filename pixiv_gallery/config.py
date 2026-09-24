from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from typing import Any
from urllib.parse import urlsplit

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


def valid_proxy(value: str) -> bool:
    if not value:
        return True
    try:
        parsed = urlsplit(value)
        return bool(
            parsed.scheme in {"http", "https"}
            and parsed.hostname
            and parsed.port != 0
            and not parsed.fragment
            and not any(char.isspace() for char in value)
        )
    except ValueError:
        return False


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
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> Settings:
        values = dict(raw or {})
        bounds = {
            "timeout_seconds": (5, 120),
            "default_count": (1, 10),
            "max_count": (1, 20),
            "cache_ttl_minutes": (1, 1440),
            "max_file_size_mb": (1, 50),
            "download_concurrency": (1, 5),
            "cooldown_seconds": (0, 3600),
        }
        normalized = {}
        for field in fields(cls):
            value = values.get(field.name, field.default)
            if isinstance(field.default, bool):
                normalized[field.name] = as_bool(value, field.default)
            elif field.name in bounds:
                try:
                    number = int(value) if not isinstance(value, bool) else field.default
                except (TypeError, ValueError, OverflowError):
                    number = field.default
                low, high = bounds[field.name]
                normalized[field.name] = max(low, min(high, number))
            else:
                normalized[field.name] = value
        normalized["refresh_token"] = str(values.get("refresh_token") or "").strip()
        proxy = str(values.get("proxy") or "").strip()
        normalized["proxy"] = proxy if valid_proxy(proxy) else ""
        target = values.get("search_target", cls.search_target)
        normalized["search_target"] = (
            target if isinstance(target, str) and target in SEARCH_TARGETS else cls.search_target
        )
        return cls(**normalized)

    def public_dict(self) -> dict[str, Any]:
        data = self.__dict__.copy()
        data["refresh_token_configured"] = bool(self.refresh_token)
        data.pop("refresh_token", None)
        return data
