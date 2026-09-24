from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .models import Illustration


def metadata_lines(work: Illustration, *, include_link: bool = True) -> list[str]:
    lines = [
        f"《{work.title or 'Pixiv 作品'}》",
        f"作者：{work.user_name or work.user_id or '未知'}",
    ]
    if work.tags:
        lines.append("标签：" + " / ".join(work.tags[:8]))
    if include_link:
        lines.append(f"Pixiv：https://www.pixiv.net/artworks/{work.id}")
    return lines


def build_text(
    works: Iterable[Illustration], *, include_metadata: bool = True, include_link: bool = True
) -> str:
    items = list(works)
    if not items:
        return "没有找到符合条件的 Pixiv 作品。"
    if not include_metadata:
        summary = f"为你找到 {len(items)} 张 Pixiv 插画。"
        if include_link:
            summary += "\n" + "\n".join(
                f"https://www.pixiv.net/artworks/{work.id}" for work in items
            )
        return summary
    blocks = [f"为你找到 {len(items)} 张 Pixiv 插画："]
    for index, work in enumerate(items, 1):
        blocks.append(f"\n{index}. " + "\n".join(metadata_lines(work, include_link=include_link)))
    return "\n".join(blocks)


def image_paths(
    work: Illustration, root: Path, *, all_pages: bool, max_count: int
) -> list[tuple[str, str]]:
    urls = work.image_urls if all_pages else work.image_urls[:1]
    return [
        (url, str(root / f"{work.id}_{idx}.jpg")) for idx, url in enumerate(urls[:max_count], 1)
    ]
