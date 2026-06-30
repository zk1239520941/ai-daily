"""Push markdown 正文解析：sentinel 分段、栏目标签等。"""

from __future__ import annotations

from typing import Dict, List, Tuple

from src.storage import _SECTION_ORDER, extract_section

SECTION_LABELS: Dict[str, str] = {
    "rss": "RSS 精选",
    "github": "GitHub 趋势",
    "hackernews": "Hacker News",
    "insights": "今日洞察",
}


def has_sentinels(body: str) -> bool:
    """正文是否包含 SECTION sentinel。"""
    return "<!-- SECTION:" in (body or "")


def split_sentinel_sections(body: str) -> List[Tuple[str, str]]:
    """按固定顺序切分早报四段，返回 (section_id, markdown) 列表。"""
    results: List[Tuple[str, str]] = []
    for key in _SECTION_ORDER:
        section_md = extract_section(body or "", key).strip()
        if section_md:
            results.append((key, section_md))
    return results


def strip_leading_h2(md: str) -> str:
    """去掉段内首个 ## 标题，避免与栏目标题重复。"""
    lines = (md or "").strip().splitlines()
    if lines and lines[0].startswith("## "):
        return "\n".join(lines[1:]).strip()
    return (md or "").strip()


def build_sections_manifest(sections: Dict[str, str]) -> List[Dict[str, object]]:
    """根据各段 markdown 生成 frontmatter sections 清单（代码写入，非 LLM）。"""
    manifest: List[Dict[str, object]] = []
    for key in _SECTION_ORDER:
        body = (sections.get(key) or "").strip()
        if not body:
            continue
        manifest.append(
            {
                "id": key,
                "label": SECTION_LABELS.get(key, key),
                "entry_count": body.count("###"),
            }
        )
    return manifest
