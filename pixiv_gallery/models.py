from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Illustration:
    id: int
    title: str = ""
    user_id: int | None = None
    user_name: str = ""
    tags: list[str] = field(default_factory=list)
    image_urls: list[str] = field(default_factory=list)
    x_restrict: int | None = 0
    type: str = "illust"
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_r18(self) -> bool:
        return self.x_restrict == 1

    @property
    def is_r18g(self) -> bool:
        return self.x_restrict == 2
