"""封面图选取：基于 entry_images 与正文链接，不由 LLM 生成。"""

from __future__ import annotations

import re
from typing import Dict, List

from src.markdown_utils import extract_first_url, lookup_entry_image

_H3_RE = re.compile(r"^###\s+", re.MULTILINE)


def select_cover_image(
    entry_images: Dict[str, str],
    body: str,
    highlights: List[str] | None = None,
) -> str:
    """按正文 ### 块顺序选取第一条可配图 URL 对应的封面。"""
    del highlights  # 预留扩展；v1 以正文顺序为准
    if not entry_images:
        return ""

    text = body or ""
    matches = list(_H3_RE.finditer(text))
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[start:end]
        url = extract_first_url(block)
        image = lookup_entry_image(entry_images, url)
        if image:
            return image

    for image_url in sorted(entry_images.values()):
        if image_url:
            return image_url
    return ""


def enrich_image_metadata(metadata: dict, body: str) -> None:
    """为 push metadata 补充 cover_image（就地修改）。"""
    entry_images = metadata.get("entry_images") or {}
    if not isinstance(entry_images, dict) or not entry_images:
        return
    if not metadata.get("cover_image"):
        highlights = metadata.get("highlights")
        hl_list = highlights if isinstance(highlights, list) else []
        metadata["cover_image"] = select_cover_image(entry_images, body, hl_list)
